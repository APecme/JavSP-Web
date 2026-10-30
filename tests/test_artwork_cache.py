import io
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from javsp_web import artwork, storage, tasks


class StubRequest:
    """Request double exposing only the attributes image_response consumes."""

    def __init__(self, if_none_match=None, version=None):
        self.headers = {'if-none-match': if_none_match} if if_none_match is not None else {}
        self.query_params = {'v': version} if version is not None else {}


class ImageResponseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.enterContext(patch.object(artwork, 'DATA_DIR', self.folder))
        self.path = self.folder / 'poster.jpg'
        self.path.write_bytes(self.jpeg('red'))

    @staticmethod
    def jpeg(color):
        buffer = io.BytesIO()
        Image.new('RGB', (60, 90), color).save(buffer, 'JPEG', quality=90)
        return buffer.getvalue()

    @staticmethod
    def pixel(body):
        with Image.open(io.BytesIO(body)) as image:
            return image.convert('RGB').getpixel((5, 5))

    def request(self, **kwargs):
        return artwork.image_response(self.path, StubRequest(**kwargs))

    def test_unversioned_requests_keep_revalidation_only_cache(self):
        response = self.request()
        self.assertEqual(response.headers['cache-control'], 'private, no-cache')

    def test_versioned_requests_get_short_private_cache(self):
        response = self.request(version='2026-10-23T12:00:00Z')
        self.assertEqual(response.headers['cache-control'], 'private, max-age=300')
        self.assertNotIn('public', response.headers['cache-control'])
        self.assertTrue(response.headers['etag'])

    def test_conditional_304_supports_weak_strong_list_and_star(self):
        etag = self.request(version='v1').headers['etag']
        for header in (etag, 'W/' + etag, '"other-etag", ' + etag, '*'):
            with self.subTest(header=header):
                response = self.request(version='v1', if_none_match=header)
                self.assertEqual(response.status_code, 304)
                self.assertEqual(response.headers['cache-control'], 'private, max-age=300')
                self.assertEqual(response.headers['etag'], etag)

    def test_unversioned_conditional_304_stays_no_cache(self):
        etag = self.request().headers['etag']
        response = self.request(if_none_match='W/' + etag)
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.headers['cache-control'], 'private, no-cache')

    def test_replaced_source_rotates_etag_and_regenerates_thumbnail(self):
        thumbnail_before = artwork.image_response(self.path, StubRequest(version='v1'), thumbnail=True)
        etag_before = thumbnail_before.headers['etag']
        pixel_before = self.pixel(thumbnail_before.body)
        time.sleep(0.02)
        self.path.write_bytes(self.jpeg('blue'))
        stale = self.request(version='v1', if_none_match=etag_before)
        self.assertEqual(stale.status_code, 200)
        self.assertNotEqual(stale.headers['etag'], etag_before)
        thumbnail_after = artwork.image_response(self.path, StubRequest(version='v1', if_none_match=etag_before), thumbnail=True)
        self.assertEqual(thumbnail_after.status_code, 200)
        self.assertNotEqual(thumbnail_after.headers['etag'], etag_before)
        self.assertNotEqual(thumbnail_after.body, thumbnail_before.body)
        self.assertNotEqual(self.pixel(thumbnail_after.body), pixel_before)

    def test_same_length_inplace_edit_with_preserved_mtime_is_detected(self):
        red, blue = self.jpeg('red'), self.jpeg('blue')
        length = max(len(red), len(blue))
        red += b'\x00' * (length - len(red))
        blue += b'\x00' * (length - len(blue))
        self.path.write_bytes(red)
        before = artwork.image_response(self.path, StubRequest(version='v1'), thumbnail=True)
        etag_before = before.headers['etag']
        pixel_before = self.pixel(before.body)
        stat = self.path.stat()
        with open(self.path, 'r+b') as handle:
            handle.write(blue)
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        after = artwork.image_response(self.path, StubRequest(version='v1', if_none_match=etag_before), thumbnail=True)
        self.assertEqual(after.status_code, 200)
        self.assertNotEqual(after.headers['etag'], etag_before)
        self.assertNotEqual(after.body, before.body)
        self.assertNotEqual(self.pixel(after.body), pixel_before)


class ArtworkRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.object(tasks, 'DATA_DIR', self.folder))
        self.enterContext(patch.object(tasks, '_TASK_COVERS_DIR', self.folder / 'task-covers'))
        self.enterContext(patch.object(tasks, '_logs', {}))
        self.enterContext(patch.object(artwork, 'DATA_DIR', self.folder))

    def item(self, task_id='one', status='succeeded', **kw):
        return dict(id=task_id, created_at='2026-09-23T12:00:00+00:00', status=status,
                    input_directory=str(self.folder / (task_id + '.mp4')), file_name=task_id,
                    size_bytes=1024**3, log_tail=['JAVSP_PROGRESS ' + '{"stage": "metadata", "title": "t"}'], **kw)

    def cover_record(self):
        poster = self.folder / 'poster.jpg'
        Image.new('RGB', (24, 36), 'red').save(poster)
        record = self.item(image_output={'poster_file': str(poster), 'fanart_file': str(poster), 'save_dir': str(self.folder)})
        storage.upsert_task(record)
        return record, poster

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.server = server
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def test_cover_route_cache_headers_follow_version_param(self):
        client = self.client()
        self.cover_record()
        plain = client.get('/api/tasks/one/cover/0')
        self.assertEqual(plain.status_code, 200)
        self.assertEqual(plain.headers['cache-control'], 'private, no-cache')
        versioned = client.get('/api/tasks/one/cover/0?v=1729684800')
        self.assertEqual(versioned.status_code, 200)
        self.assertEqual(versioned.headers['cache-control'], 'private, max-age=300')
        conditional = client.get('/api/tasks/one/cover/0?v=1729684800', headers={'If-None-Match': 'W/' + versioned.headers['etag']})
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.headers['cache-control'], 'private, max-age=300')

    def test_cover_route_still_requires_authentication(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        plain = TestClient(server.app)
        self.addCleanup(plain.close)
        response = plain.get('/api/tasks/one/cover/0?v=1')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('cache-control', response.headers)

    def test_artwork_upload_and_delete_rotate_updated_at_for_versioning(self):
        client = self.client()
        self.cover_record()
        self.assertIsNone(tasks.get_task('one').get('updated_at'))
        buffer = io.BytesIO()
        Image.new('RGB', (24, 36), 'blue').save(buffer, 'JPEG')
        replaced = client.put('/api/tasks/one/artwork/cover/0',
                              files={'file': ('cover.jpg', buffer.getvalue(), 'image/jpeg')})
        self.assertEqual(replaced.status_code, 200, replaced.text)
        after_upload = tasks.get_task('one')['updated_at']
        self.assertTrue(after_upload)
        summary = client.get('/api/tasks?limit=10&view=manual').json()['items'][0]
        self.assertEqual(summary['updated_at'], after_upload)
        time.sleep(0.02)
        removed = client.delete('/api/tasks/one/artwork/cover/0')
        self.assertEqual(removed.status_code, 200, removed.text)
        after_delete = tasks.get_task('one')['updated_at']
        self.assertNotEqual(after_delete, after_upload)


class FanartThumbnailRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        old = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(old):
                self.enterContext(patch.object(storage, name, self.folder / value.relative_to(old)))
        self.enterContext(patch.object(tasks, 'DATA_DIR', self.folder))
        self.enterContext(patch.object(tasks, '_TASK_COVERS_DIR', self.folder / 'task-covers'))
        self.enterContext(patch.object(tasks, '_logs', {}))
        self.enterContext(patch.object(artwork, 'DATA_DIR', self.folder))

    def setUpFanart(self):
        fanart_dir = self.folder / 'extrafanart'
        fanart_dir.mkdir()
        source = fanart_dir / '01.jpg'
        Image.new('RGB', (1200, 1800), 'red').save(source, 'JPEG')
        record = dict(id='one', created_at='2026-09-23T12:00:00+00:00', status='succeeded',
                      input_directory=str(self.folder / 'one.mp4'), file_name='one', size_bytes=1024,
                      log_tail=['JAVSP_PROGRESS ' + '{"stage": "metadata", "title": "t"}'],
                      image_output={'save_dir': str(self.folder)})
        storage.upsert_task(record)
        return source

    def client(self):
        from fastapi.testclient import TestClient
        with patch('threading.Thread.start'):
            from javsp_web import server
        self.enterContext(patch.dict(server.app.dependency_overrides, {server.current_user: lambda: {'username': 'test', 'role': 'admin'}}))
        client = TestClient(server.app)
        self.addCleanup(client.close)
        return client

    def test_thumbnail_returns_bounded_jpeg(self):
        self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0?thumbnail=true')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'image/jpeg')
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertLessEqual(image.width, 360)
            self.assertLessEqual(image.height, 540)

    def test_without_thumbnail_returns_original_image(self):
        source = self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('thumbnail', response.headers.get('content-type', ''))
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertEqual((image.width, image.height), (1200, 1800))
        self.assertEqual(response.content, source.read_bytes())

    def test_thumbnail_cache_headers_and_conditional_304(self):
        self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0?thumbnail=true')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'private, no-cache')
        etag = response.headers['etag']
        self.assertTrue(etag)
        conditional = client.get('/api/tasks/one/fanart/0?thumbnail=true',
                                headers={'If-None-Match': 'W/' + etag})
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.headers['etag'], etag)
        self.assertEqual(conditional.headers['cache-control'], 'private, no-cache')

    def test_view_returns_bounded_jpeg(self):
        self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0?size=view')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'image/jpeg')
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertLessEqual(max(image.size), 1600)
            # 竖版 1200x1800 → 等比缩到 1066x1600，而不是简单的截断。
            self.assertEqual(image.width, 1067)

    def test_view_does_not_affect_original_request(self):
        source = self.setUpFanart()
        client = self.client()
        self.client().get('/api/tasks/one/fanart/0?size=view')
        response = client.get('/api/tasks/one/fanart/0')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, source.read_bytes())

    def test_view_etag_and_conditional_304(self):
        self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0?size=view&v=abc')
        self.assertEqual(response.headers['cache-control'], 'private, max-age=300')
        etag = response.headers['etag']
        self.assertTrue(etag)
        conditional = client.get('/api/tasks/one/fanart/0?size=view&v=abc',
                                headers={'If-None-Match': etag})
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.headers['etag'], etag)

    def test_view_cache_hit_avoids_reencoding(self):
        self.setUpFanart()
        client = self.client()
        first = client.get('/api/tasks/one/fanart/0?size=view')
        self.assertEqual(first.status_code, 200)
        cached = (self.folder / 'view-cache')
        with patch.object(artwork, 'Image') as mock_image:
            second = client.get('/api/tasks/one/fanart/0?size=view')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.content, first.content)
        mock_image.open.assert_not_called()

    def test_thumbnail_takes_priority_over_view(self):
        self.setUpFanart()
        client = self.client()
        response = client.get('/api/tasks/one/fanart/0?thumbnail=true&size=view')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['content-type'], 'image/jpeg')
        with Image.open(io.BytesIO(response.content)) as image:
            self.assertLessEqual(image.width, 360)
            self.assertLessEqual(image.height, 540)


if __name__ == '__main__':
    unittest.main()
