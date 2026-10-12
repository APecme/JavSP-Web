"""Build a minimal F10 overlay from a copy of the current f08 server source."""
import argparse
import ast
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = '''
def login(body: LoginBody, response: Response) -> dict:
    user = find_user(body.username)
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    response.set_cookie(SESSION_COOKIE, create_session(user), httponly=True, samesite="lax", max_age=43200)
    return {"username": user["username"], "role": user.get("role", "operator")}

def logout(response: Response, cookie_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    remove_session(cookie_token)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}

def run() -> None:
    import uvicorn
    uvicorn.run(
        "javsp_web.server:app",
        host=os.environ.get("JAVSP_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("JAVSP_WEB_PORT", "8090")),
        reload=False,
    )
'''


def functions(source):
    return {node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def signature(node):
    node.decorator_list = []
    return ast.dump(node, include_attributes=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('live_source', type=Path)
    parser.add_argument('stage', type=Path)
    parser.add_argument('--public-url', required=True)
    args = parser.parse_args()
    from urllib.parse import urlsplit
    url = urlsplit(args.public_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise SystemExit('Public URL must be an HTTPS entrypoint without credentials/query/fragment')
    live = args.live_source.read_text(encoding='utf-8-sig')
    local = (ROOT / 'javsp_web/server.py').read_text(encoding='utf8')
    actual, expected, patched = functions(live), functions(EXPECTED), functions(local)
    lines = live.splitlines(keepends=True)
    for name in sorted(expected, key=lambda name: actual[name].lineno, reverse=True):
        if signature(actual[name]) != signature(expected[name]):
            raise SystemExit('Live function changed; inspect before patching: ' + name)
        replacement = local.splitlines(keepends=True)[patched[name].lineno - 1:patched[name].end_lineno]
        lines[actual[name].lineno - 1:actual[name].end_lineno] = replacement
    source = ''.join(lines)
    anchor = 'from .auth import SESSION_COOKIE, create_session, current_user, remove_session, require_admin\n'
    assert source.count(anchor) == 1
    source = source.replace(anchor, anchor + 'from .login_security import login_context, login_limiter\n')
    ast.parse(source)
    args.stage.mkdir(parents=True, exist_ok=False)
    (args.stage / 'server.py').write_text(source, encoding='utf8')
    shutil.copyfile(ROOT / 'javsp_web/login_security.py', args.stage / 'login_security.py')
    report = Path(__file__).resolve().parent
    shutil.copyfile(report / 'deploy_main_patch.py', args.stage / 'deploy_main_patch.py')
    acceptance = (report / 'f10_acceptance.py').read_text(encoding='utf8')
    acceptance = acceptance.replace("PUBLIC = os.environ['F10_PUBLIC_URL'].rstrip('/')", 'PUBLIC = ' + repr(args.public_url.rstrip('/')))
    (args.stage / 'acceptance.py').write_text(acceptance, encoding='utf8')
    (args.stage / 'tests').mkdir()
    (args.stage / 'tests/__init__.py').touch()
    for name in ('test_auth_sessions.py', 'test_login_security.py', 'test_config_access.py', 'test_profile.py'):
        shutil.copyfile(ROOT / 'tests' / name, args.stage / 'tests' / name)
    files = {'javsp_web/server.py': 'server.py', 'javsp_web/login_security.py': 'login_security.py'}
    (args.stage / 'files.json').write_text(json.dumps(files, indent=2), encoding='utf8')
    (args.stage / 'bundle-evidence.json').write_text(json.dumps({
        'base': 'javsp-web-security:f08', 'live_source_sha256': hashlib.sha256(live.encode()).hexdigest(),
        'replaced_functions': sorted(expected), 'trusted_proxy': '192.168.0.1', 'public_url': args.public_url,
        'files': {name: hashlib.sha256((args.stage / file).read_bytes()).hexdigest() for name, file in files.items()},
    }, indent=2), encoding='utf8')
    print(json.dumps({'stage': str(args.stage), 'files': files, 'ready': True}))


if __name__ == '__main__':
    main()
