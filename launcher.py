from __future__ import annotations

import threading
import webbrowser
import sys
import ctypes
from pathlib import Path


_instance_mutex: int | None = None
_INSTANCE_MUTEX_NAME = "Local\\JavSP-WEB-Control-Plane"


def _acquire_single_instance() -> bool:
    """Keep one tray-hosted control plane per Windows desktop session."""
    global _instance_mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, _INSTANCE_MUTEX_NAME)
    if not handle:
        # Do not make a Windows API failure prevent a user from launching the app.
        return True
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    return True


def _run_embedded_javsp() -> bool:
    if "--run-javsp" not in sys.argv:
        return False
    bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "vendor" / "JavSP"
    sys.path.insert(0, str(bundle))
    sys.javsp_version = "1.8.0"
    index = sys.argv.index("--run-javsp")
    sys.argv = [str(bundle / "javsp" / "__main__.py"), *sys.argv[index + 1:]]
    from javsp.__main__ import entry

    entry()
    return True


def main() -> None:
    if _run_embedded_javsp():
        return
    if not _acquire_single_instance():
        webbrowser.open("http://127.0.0.1:8090/login")
        return
    import uvicorn

    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise SystemExit("托盘版本需要安装 pystray 和 Pillow") from exc

    from javsp_web.server import app

    # Windowed PyInstaller builds have no stdout/stderr TTY. Uvicorn's default
    # formatter calls isatty() during logging setup, so disable that setup for
    # the tray-hosted server.
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=8090,
            log_config=None,
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    logo_path = bundle_root / "javsp_web" / "web" / "assets" / "javsp-logo.ico"
    if logo_path.exists():
        image = Image.open(logo_path)
        image.load()
    else:
        image = Image.new("RGBA", (64, 64), "#175cd3")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill="#2e90fa")
        draw.text((25, 17), "J", fill="white")

    def open_web(_: object, __: object) -> None:
        webbrowser.open("http://127.0.0.1:8090/login")

    def exit_app(icon: object, _: object) -> None:
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon("JavSP WEB", image, "JavSP WEB", menu=pystray.Menu(pystray.MenuItem("打开控制端", open_web, default=True), pystray.MenuItem("退出", exit_app)))
    webbrowser.open("http://127.0.0.1:8090/login")
    icon.run()


if __name__ == "__main__":
    main()
