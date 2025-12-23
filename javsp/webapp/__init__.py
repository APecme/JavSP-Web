from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .auth import router as auth_router
from .tasks import router as tasks_router
from .rules import router as rules_router

@lru_cache
def get_web_version() -> str:
    """读取 JavSP-web 的版本号。"""
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


ROOT_DIR = Path(__file__).resolve().parent
app = FastAPI(title="JavSP-web")

app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")
app.include_router(auth_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(rules_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/version")
async def api_version() -> dict:
    return {"version": get_web_version()}


@app.get("/login")
async def login_page() -> FileResponse:
    return FileResponse(ROOT_DIR / "login.html")


@app.get("/")
async def index_page() -> FileResponse:
    return FileResponse(ROOT_DIR / "index.html")


# Provide a favicon to avoid 404 in browser console. Prefer project-level image if available.
@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    # image directory is two levels up from this package
    try:
        img_path = Path(__file__).resolve().parents[2] / "image" / "JavSP.ico"
        if img_path.exists():
            return FileResponse(img_path)
    except Exception:
        pass
    # fallback: serve a static placeholder if present in webapp/static
    try:
        static_fav = ROOT_DIR / "static" / "favicon.ico"
        if static_fav.exists():
            return FileResponse(static_fav)
    except Exception:
        pass
    # If not found, raise 404 so caller gets proper response
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="favicon not found")


@app.get("/api/files")
async def serve_file(
    path: str,
) -> FileResponse:
    """提供文件服务，用于显示封面图片、NFO文件等。
    
    仅允许访问 /video 目录下的文件，防止越权访问。
    """
    from fastapi import HTTPException
    from urllib.parse import unquote
    import os
    
    if not path:
        raise HTTPException(status_code=400, detail="必须提供路径")
    
    # URL解码路径
    try:
        decoded_path = unquote(path)
    except Exception:
        decoded_path = path
    
    # 确保是绝对路径
    if not os.path.isabs(decoded_path):
        raise HTTPException(status_code=400, detail="必须提供绝对路径")
    
    try:
        real = os.path.realpath(decoded_path)
    except OSError:
        raise HTTPException(status_code=400, detail="路径无效")
    
    # 仅允许访问 /video 映射卷内的内容
    root_allowed = os.path.realpath("/video")
    if not real.startswith(root_allowed):
        raise HTTPException(status_code=403, detail="只能访问 /video 目录下的文件")
    
    if not os.path.exists(real):
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.isfile(real):
        raise HTTPException(status_code=400, detail="目标不是文件")
    
    return FileResponse(real)