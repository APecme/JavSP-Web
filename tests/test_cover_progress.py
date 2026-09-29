"""Offline regressions for actual cover filenames emitted by the scraper."""
import ast
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/JavSP'))

from PIL import Image
from javsp_web import tasks


class CoverProgressTests(unittest.TestCase):
    def run_scraper(self, folder, extension, poster_error=False, move_files=False):
        info = SimpleNamespace(dvdid='TEST-001', cid=None, title='Test', actress=[], director=None,
                               producer=None, publisher=None, publish_date=None, big_covers=[],
                               covers=['https://example.test/cover'], preview_pics=[], cover=None)
        movie = SimpleNamespace(files=[str(folder / 'TEST-001.mp4')], dvdid='TEST-001', cid=None,
                                data_src='normal', info=info, save_dir=str(folder),
                                fanart_file=str(folder / 'fanart.jpg'), poster_file=str(folder / 'poster.jpg'),
                                nfo_file=str(folder / 'movie.nfo'), new_paths=[], rename_files=Mock())
        config = SimpleNamespace(translator=SimpleNamespace(engine=None),
                                 summarizer=SimpleNamespace(cover=SimpleNamespace(highres=False),
                                     extra_fanarts=SimpleNamespace(enabled=False), move_files=move_files,
                                     path=SimpleNamespace(hard_link=False)),
                                 crawler=SimpleNamespace(selection={'normal': []}))
        events = []
        def download_cover(*args, **kwargs):
            path = folder / ('fanart' + extension)
            Image.new('RGB', (24, 36), 'blue').save(path)
            return info.covers[0], str(path)
        def process_poster(movie):
            self.assertFalse(any(stage == 'images' and event.get('status') == 'completed'
                                 for stage, event in events))
            if poster_error:
                raise OSError('poster write failed')
            with Image.open(movie.fanart_file) as image:
                image.save(movie.poster_file)
        namespace = dict(os=os, Cfg=lambda: config, logger=logging.getLogger('cover-test'),
                         tqdm=lambda *args, **kwargs: args[0] if args else Mock(),
                         progress_enabled=lambda: True,
                         progress_event=lambda stage, **kwargs: events.append((stage, kwargs)),
                         fallback_media_type_id=lambda: 'normal', parallel_crawler=lambda *args: [info],
                         info_summary=lambda *args: True, generate_names=lambda *args: None,
                         download_cover=download_cover, process_poster=process_poster, write_nfo=Mock())
        tree = ast.parse((ROOT / 'vendor/JavSP/javsp/__main__.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'RunNormalMode')
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'RunNormalMode', 'exec'), namespace)
        if poster_error:
            with self.assertRaises(RuntimeError):
                namespace['RunNormalMode']([movie])
        else:
            self.assertEqual(namespace['RunNormalMode']([movie]), [movie])
        return events

    def test_actual_paths_are_persisted_before_completion_with_or_without_move(self):
        import json
        for extension in ('.png', '.jpg', '.webp'):
            for move_files in (False, True):
                with self.subTest(extension=extension, move_files=move_files), tempfile.TemporaryDirectory() as temporary:
                    folder = Path(temporary)
                    events = self.run_scraper(folder, extension, move_files=move_files)
                    completed = next(i for i, (stage, event) in enumerate(events)
                                     if stage == 'images' and event.get('status') == 'completed')
                    output = [event for stage, event in events[:completed] if stage == 'output'][-1]
                    self.assertEqual(output['poster_file'], str(folder / ('poster' + extension)))
                    self.assertEqual(output['fanart_file'], str(folder / ('fanart' + extension)))
                    record = {}
                    for stage, event in events:
                        tasks._capture_task_artwork_event(record, 'JAVSP_PROGRESS ' + json.dumps(event | {'stage': stage}))
                    self.assertEqual(record['image_output'], output)
                    self.assertTrue(Path(output['poster_file']).is_file())

    def test_poster_failure_never_reports_completed_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = self.run_scraper(Path(temporary), '.png', poster_error=True)
        statuses = [event['status'] for stage, event in events if stage == 'images' and event.get('kind') == 'cover']
        self.assertEqual(statuses, ['downloading', 'failed'])


if __name__ == '__main__':
    unittest.main()
