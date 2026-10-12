"""Exercise actual authentication handlers without starting application schedulers."""
import ast
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, WebSocket, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from javsp_web import auth, storage
from javsp_web.login_security import LoginLimiter, login_context


def handlers():
    names = {'LoginBody', 'UserBody', 'login', 'logout', 'me', '_validate_password_change',
             'update_user', 'remove_user', 'google_cover_browser'}
    path = Path(storage.__file__).with_name('server.py')
    source = ast.parse(path.read_text(encoding='utf8'))
    selected = [node for node in source.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in selected:
        node.decorator_list = []
    namespace = {**vars(storage), **vars(auth), 'BaseModel':BaseModel, 'Field':Field,
                 'Request':Request, 'Response':Response, 'HTTPException':HTTPException, 'status':status,
                 'login_limiter':LoginLimiter(), 'login_context':login_context,
                 'Depends':Depends, 'Cookie':Cookie, 'WebSocket':WebSocket, 'asyncio':asyncio,
                 'google_captcha_browser_active':lambda task_id:True,
                 'GOOGLE_VNC_HOST':'127.0.0.1', 'GOOGLE_VNC_PORT':5900}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


class SessionTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix='f02-auth-'))
        previous = storage.DATA_DIR
        for name, value in list(vars(storage).items()):
            if isinstance(value, Path) and value.is_relative_to(previous):
                self.enterContext(patch.object(storage, name, Path(directory)/value.relative_to(previous)))
        self.enterContext(patch.object(auth, '_sessions', {}))
        storage.upsert_user('alice','old-password','operator')
        storage.upsert_user('bob','bob-password','operator')
        self.ns = handlers()
        app = FastAPI()
        for method, path, function in [('post','/login','login'),('get','/me','me'),
                                       ('put','/users/{username}','update_user'),('delete','/users/{username}','remove_user')]:
            getattr(app,method)(path)(self.ns[function])
        app.websocket('/browser/{task_id}')(self.ns['google_cover_browser'])
        self.client = self.enterContext(TestClient(app))

    def token(self, username='alice'):
        return auth.create_session(storage.find_user(username))

    def assert_rejected(self, token):
        response = self.client.get('/me',headers={'Cookie':auth.SESSION_COOKIE+'='+token})
        self.assertEqual(response.status_code,401)
        self.assertNotIn(token,auth._sessions)

    def test_password_change_revokes_all_sessions_and_new_login_works(self):
        tokens = [self.token(),self.token()]
        bob = self.token('bob')
        admin = self.token('admin')
        response = self.client.put('/users/alice',headers={'Cookie':auth.SESSION_COOKIE+'='+admin},
            json={'username':'alice','role':'operator','password':'new-password','password_confirm':'new-password'})
        self.assertEqual(response.status_code,200)
        for token in tokens:
            self.assert_rejected(token)
        self.assertEqual(auth.current_user(bob)['username'],'bob')
        self.assertEqual(self.client.post('/login',json={'username':'alice','password':'old-password'}).status_code,401)
        self.assertEqual(self.client.post('/login',json={'username':'alice','password':'new-password'}).status_code,200)
        self.assertEqual(self.client.get('/me').status_code,200)

    def test_deleted_then_recreated_username_cannot_reuse_session(self):
        token = self.token()
        old_id = storage.find_user('alice')['user_id']
        response = self.client.delete('/users/alice',headers={'Cookie':auth.SESSION_COOKIE+'='+self.token('admin')})
        self.assertEqual(response.status_code,200)
        storage.upsert_user('alice','different-password','admin')
        self.assertNotEqual(old_id,storage.find_user('alice')['user_id'])
        self.assert_rejected(token)

    def test_role_changes_and_rename_revoke_even_if_changed_back(self):
        token = self.token()
        storage.upsert_user('alice',None,'admin')
        storage.upsert_user('alice',None,'operator')
        self.assert_rejected(token)
        token = self.token()
        old_id = storage.find_user('alice')['user_id']
        storage.upsert_user('renamed',None,'operator',old_username='alice')
        self.assertEqual(old_id,storage.find_user('renamed')['user_id'])
        self.assert_rejected(token)

    def test_profile_and_noop_updates_do_not_revoke(self):
        token = self.token()
        if hasattr(storage,'user_profile'):
            storage.user_profile('alice',{'display_name':'A','avatar_id':''})
        else:
            # The deployed stable release predates the profile endpoint.
            # Exercise the same non-security data update without adding it.
            with storage._lock:
                users=json.loads(storage.USERS_FILE.read_text())
                next(u for u in users if u['username']=='alice')['display_name']='A'
                storage._write_json(storage.USERS_FILE,users)
        storage.upsert_user('alice',None,'operator')
        self.assertEqual(auth.current_user(token)['username'],'alice')
        for item in storage.list_users():
            self.assertNotIn('user_id',item)
            self.assertNotIn('auth_version',item)

    def test_password_verification_race_cannot_mint_new_valid_session(self):
        verified = storage.find_user('alice')
        self.assertTrue(storage.verify_password('old-password',verified['password']))
        storage.upsert_user('alice','new-password','operator')
        self.assert_rejected(auth.create_session(verified))

    def test_legacy_accounts_migrate_once_without_changing_private_profile(self):
        users = json.loads(storage.USERS_FILE.read_text())
        for user in users:
            user.pop('user_id',None)
            user.pop('auth_version',None)
        users[0]['comment_token'] = 'private-comment-proof'
        storage.USERS_FILE.write_text(json.dumps(users))
        first = storage.find_user(users[0]['username'])
        storage.ensure_seed_data()
        again = storage.find_user(users[0]['username'])
        self.assertEqual(first,again)
        self.assertEqual(first['password'],users[0]['password'])
        self.assertEqual(first['comment_token'],'private-comment-proof')
        self.assertTrue(first['user_id'])
        self.assertTrue(first['auth_version'])

    def test_expired_logged_out_and_legacy_sessions_are_rejected(self):
        token = self.token()
        user_id, version, _ = auth._sessions[token]
        auth._sessions[token] = (user_id,version,0)
        self.assert_rejected(token)
        token = self.token()
        auth.remove_session(token)
        self.assert_rejected(token)
        auth._sessions['legacy'] = ('alice',9999999999)
        self.assert_rejected('legacy')

    def test_revoked_websocket_rejected_before_backend_connection(self):
        token = self.token()
        storage.upsert_user('alice','new-password','operator')
        with patch.object(asyncio,'open_connection') as connection:
            with self.assertRaises(WebSocketDisconnect) as raised:
                with self.client.websocket_connect('/browser/test',headers={'Cookie':auth.SESSION_COOKIE+'='+token}):
                    pass
            self.assertEqual(raised.exception.code,1008)
            connection.assert_not_called()

    def test_active_websocket_closes_after_revocation_and_releases_backend(self):
        class Reader:
            async def read(self, length):
                await asyncio.Event().wait()
        class Writer:
            closed = False
            def close(self): self.closed = True
            async def wait_closed(self): pass
        writer = Writer()
        async def connect(*args): return Reader(),writer
        token = self.token()
        with patch.object(asyncio,'open_connection',side_effect=connect):
            with self.client.websocket_connect('/browser/test',headers={'Cookie':auth.SESSION_COOKIE+'='+token}) as socket:
                storage.upsert_user('alice','new-password','operator')
                self.assertEqual(socket.receive()['code'],1008)
        self.assertTrue(writer.closed)


if __name__ == '__main__':
    unittest.main()
