"""AI Studio (Infinite-Canvas) — Zeabur / Docker 启动入口。

职责：
1. 读取平台注入的 PORT（Zeabur 默认 8080），未注入时回落 3000，保持本地行为不变。
2. 可通过环境变量给公网实例加一层 HTTP Basic 访问保护（可选）。
3. 其余逻辑全部复用 main.py 的 app，不修改任何业务代码。

环境变量：
  PORT                 监听端口，默认 3000
  AISTUDIO_USER        开启访问保护的用户名（与 AISTUDIO_PASS 同时存在才生效）
  AISTUDIO_PASS        访问保护密码
  COMFYUI_INSTANCES    逗号分隔的 ComfyUI 地址，如 10.0.0.5:8188，默认 127.0.0.1:8188
"""
import base64
import os
import secrets
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 嵌入式/精简解释器可能不把脚本目录加入 sys.path，显式补上，保证 main 可导入
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response

from main import app

_USER = (os.getenv("AISTUDIO_USER") or "").strip()
_PASS = (os.getenv("AISTUDIO_PASS") or "").strip()


class BasicAuthGuard(BaseHTTPMiddleware):
    """极简 HTTP Basic 鉴权。仅当同时配置用户名与密码时启用。"""

    async def dispatch(self, request, call_next):
        # 健康检查放行，便于平台探活
        if request.url.path in ("/healthz", "/health"):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                raw = base64.b64decode(header[6:].strip()).decode("utf-8", "ignore")
                user, _, pwd = raw.partition(":")
                if secrets.compare_digest(user, _USER) and secrets.compare_digest(pwd, _PASS):
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            content="需要登录",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="AI Studio"'},
            media_type="text/plain; charset=utf-8",
        )


@app.get("/healthz")
async def _healthz():
    return PlainTextResponse("ok")


if _USER and _PASS:
    app.add_middleware(BasicAuthGuard)
    print("[server] 已启用 HTTP Basic 访问保护", flush=True)
else:
    print("[server] 未配置 AISTUDIO_USER / AISTUDIO_PASS，实例为公开访问", flush=True)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    print(f"[server] listening on 0.0.0.0:{port}", flush=True)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ws_ping_interval=None,
        ws_ping_timeout=None,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
