import asyncio
import uvicorn

from javsp.webapp import app


def entry() -> None:
    """启动 JavSP-web 的 FastAPI 服务。"""
    try:
        # 启动 Uvicorn 服务器
        uvicorn.run(app, host="0.0.0.0", port=8090)
    except (KeyboardInterrupt, asyncio.exceptions.CancelledError):
        # 当收到 Ctrl+C 或 Docker stop 信号时，不做任何操作，直接静默退出
        pass
    except Exception as e:
        # 如果是其他未知的严重错误，简单打印错误信息，而不是抛出巨大的堆栈跟踪
        print(f"JavSP-Web stopped unexpected: {e}")

if __name__ == "__main__":
    entry()
