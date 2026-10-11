import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from javsp_web import storage
from javsp_web import server

class ProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='profile-test-')
        self.addCleanup(directory.cleanup)
        folder = Path(directory.name)
        self.temp = folder
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(storage.ROOT_DIR / 'data'):
                self.enterContext(patch.object(storage, name, folder / value.relative_to(storage.ROOT_DIR / 'data')))
        storage.upsert_user('alice', 'test-password', 'operator')
        storage.upsert_user('bob', 'test-password', 'operator')
        self.client = TestClient(server.app)
        self.previous = dict(server.app.dependency_overrides)
        self.addCleanup(lambda: (server.app.dependency_overrides.clear(), server.app.dependency_overrides.update(self.previous)))

    def as_user(self, name):
        server.app.dependency_overrides[server.current_user] = lambda: {'username': name, 'role': 'operator'}

    def test_profile_identity_survives_name_and_login_rename_without_leaking(self):
        self.as_user('alice')
        first = self.client.get('/api/profile')
        self.assertEqual(first.headers['cache-control'], 'no-store')
        token = first.json()['comment_token']
        self.assertGreaterEqual(len(token), 40)
        reply = self.client.put('/api/profile', json={'display_name': '新名字', 'avatar_id': '', 'role': 'admin', 'comment_token': 'forged'})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()['comment_token'], token)
        self.assertEqual(storage.find_user('alice')['role'], 'operator')
        self.as_user('bob')
        self.assertNotEqual(self.client.get('/api/profile').json()['comment_token'], token)
        self.assertNotIn(token, str(storage.list_users()))
        storage.upsert_user('renamed', None, 'operator', old_username='alice')
        self.as_user('renamed')
        self.assertEqual(self.client.get('/api/profile').json()['comment_token'], token)

    def test_profile_validation_and_authentication(self):
        server.app.dependency_overrides.pop(server.current_user, None)
        self.assertEqual(self.client.get('/api/profile').status_code, 401)
        self.as_user('alice')
        for body in [{'display_name':'  '}, {'display_name':'name','avatar_id':'../../private'}, {'display_name':'a'*33}]:
            self.assertEqual(self.client.put('/api/profile', json=body).status_code, 422)
        import json
        catalog = json.loads((server.WEB_DIR/'assets/avatar-catalog.json').read_text(encoding='utf-8'))
        avatar = catalog[0]['id']
        self.assertEqual(self.client.put('/api/profile',json={'display_name':'新名字','avatar_id':avatar}).json()['avatar_id'],avatar)
        self.assertTrue((server.WEB_DIR/'assets/avatars'/f'{avatar}.webp').is_file())

if __name__ == '__main__': unittest.main()
