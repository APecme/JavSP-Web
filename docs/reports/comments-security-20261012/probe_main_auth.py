"""Exercise actual auth/storage and extracted HTTP handlers in a temporary app."""
import ast
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
with tempfile.TemporaryDirectory(prefix='javsp-auth-audit-') as directory:
    os.environ['JAVSP_WEB_DATA_DIR'] = directory
    from fastapi import Depends, FastAPI, HTTPException, Response, status
    from fastapi.testclient import TestClient
    from pydantic import BaseModel, Field
    from javsp_web import auth, storage
    source = ast.parse((root/'javsp_web/server.py').read_text(encoding='utf8'))
    names = {'LoginBody', 'login', 'get_config'}
    selected = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    for node in selected:
        node.decorator_list = []
    namespace = {**vars(storage), **vars(auth), 'BaseModel':BaseModel, 'Field':Field, 'Response':Response,
                 'HTTPException':HTTPException, 'status':status, 'Depends':Depends}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(root/'javsp_web/server.py'),'exec'),namespace)
    app=FastAPI()
    app.post('/api/auth/login')(namespace['login'])
    app.get('/api/config')(namespace['get_config'])
    client=TestClient(app)
    storage.ensure_seed_data()
    result={'default_admin_password':storage.verify_password('admin',storage.find_user('admin')['password'])}
    storage.upsert_user('audit','old-test-password','operator')
    failures=[client.post('/api/auth/login',json={'username':'audit','password':'wrong'}).status_code for _ in range(25)]
    result['unthrottled_login']={'attempts':len(failures),'all_401':all(x==401 for x in failures)}
    response=client.post('/api/auth/login',json={'username':'audit','password':'old-test-password'})
    token=client.cookies.get(auth.SESSION_COOKIE)
    result['session_cookie_secure']='; secure' in response.headers['set-cookie'].lower()
    storage.write_config('network:\n  proxy: http://user:synthetic-secret@127.0.0.1:8080\n')
    response=client.get('/api/config')
    result['operator_can_read_config_secret']={'status':response.status_code,'secret_returned':'synthetic-secret' in response.text}
    storage.upsert_user('audit','new-test-password','operator')
    result['session_after_password_change']=auth.current_user(token)['role']
    storage.delete_user('audit')
    storage.upsert_user('audit','another-test-password','admin')
    result['old_session_after_username_recreated']=auth.current_user(token)['role']
    print(json.dumps(result,indent=2))
