#!/usr/bin/env python3
# ============================================================
# AI Fishing — MCP wrapper server
# 把 tutusagi/ai-fishing-game 包成一个 MCP 工具,让聊天里的 AI
# (像调 breath/hold 一样) 直接调 fish("cast 10") 玩。
#
# 游戏本体是同目录的 fishing.py(盲玩版):只暴露 cmd()/new_game(),
# 鱼谱/概率在运行时解码进内存。AI 只能通过本服务器的 fish 工具
# 调 cmd(),碰不到模块内部 —— 天然盲玩,想剧透都没门。
#
# 启动:
#   本地 stdio:   python server.py
#   远程(Zeabur): FISHING_TRANSPORT=streamable-http python server.py
#
# 环境变量:
#   FISHING_TRANSPORT  stdio(默认) / streamable-http / sse
#   PORT               监听端口(Zeabur 会自动注入,默认 8000)
#   FISHING_SAVE_DIR   存档目录(默认脚本同目录)。想让进度跨重部署
#                      不丢,就挂个 Zeabur 卷并把它指到卷路径。
# ============================================================

import hmac
import logging
import os
import threading

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, PlainTextResponse
import fishing  # 游戏本体(盲玩版);只用 cmd() / new_game()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-fishing")

PORT = int(os.environ.get("PORT", "8000"))
TRANSPORT = os.environ.get("FISHING_TRANSPORT", "stdio").strip().lower()
MCP_TOKEN = os.environ.get("FISHING_MCP_TOKEN", "").strip()


def _allowed_hosts(raw: str) -> list[str]:
    values = [value.strip().lower() for value in raw.split(",") if value.strip()]
    result = []
    for value in values:
        if "://" in value or "/" in value:
            raise RuntimeError("FISHING_ALLOWED_HOSTS must contain hostnames only")
        result.append(value)
        if ":" not in value:
            result.append(value + ":*")
    return list(dict.fromkeys(result))


ALLOWED_HOSTS = _allowed_hosts(os.environ.get("FISHING_ALLOWED_HOSTS", "localhost,127.0.0.1"))
if TRANSPORT in ("sse", "streamable-http") and not MCP_TOKEN:
    raise RuntimeError("FISHING_MCP_TOKEN is required for remote transport")

mcp = FastMCP(
    "ai-fishing",
    host="0.0.0.0",
    port=PORT,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=[],
    ),
)
_game_lock = threading.Lock()


@mcp.tool()
def fish(command: str = "help") -> str:
    """文字钓鱼游戏(你是玩家)。把一条游戏指令字符串传进来,返回结果文字。

    常用指令:
      help                 看完整规则
      status               看点数/地点/季节/鱼饵/图鉴(每次返回末尾也有 📊 状态栏)
      shop                 看可买鱼饵
      buy <饵id> [数量]    买饵,如 buy glow_bait 2;buy oxygen 5 买氧气瓶
      cast [饵id] [N]      抛竿;N=连钓1~20竿只回一个汇总,省来回
      cast N stop=new,rare,event  连钓途中遇到新种/稀有/事件就提前停
      goto [地点id]        列钓点 / 前往(未解锁则花点数解锁)
      dive [氧气瓶数] / surface / choose <编号>   潜水远征(捕水下专属鱼)
      sell <实例id> | sell all | sell species <鱼id>   卖鱼换点数
      inventory / encyclopedia / look <鱼或地点名>

    可以用 ; 或换行把多条指令串成一批一次跑,如 "buy basic_worm 10; cast 10"。
    目标:用有限点数把图鉴里的鱼尽量集满。一开始并不知道有哪些鱼,靠抛竿发现。
    注意:只调这个工具玩,别去解码/读游戏文件里的数据 —— 那是盲玩,剧透就没意思了。"""
    try:
        with _game_lock:
            return fishing.cmd(command)
    except Exception as e:
        logger.warning(f"fish cmd failed: {e}")
        return f"游戏出错(指令没生效,存档没动): {e}"


# --- 健康检查 / Health ---
@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"ok": True, "service": "ai-fishing", "tools": 1})


class McpTokenMiddleware:
    """Protect only the MCP transport. /health remains public for Zeabur."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        path = str(scope.get("path", "")).rstrip("/")
        if scope.get("type") == "http" and path == "/mcp":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            supplied = headers.get(b"x-token", b"").decode("utf-8", "ignore")
            if not self.token or not hmac.compare_digest(supplied, self.token):
                await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


# --- 启动入口 / Entry point ---
if __name__ == "__main__":
    save_dir = os.environ.get("FISHING_SAVE_DIR", "").strip() or "bundled-default"
    logger.info(f"AI Fishing starting | transport: {TRANSPORT} | port: {PORT} | save: {save_dir}")

    if TRANSPORT in ("sse", "streamable-http"):
        import uvicorn

        if TRANSPORT == "streamable-http":
            _app = mcp.streamable_http_app()
        else:
            _app = mcp.sse_app()
        _app.add_middleware(McpTokenMiddleware, token=MCP_TOKEN)
        uvicorn.run(_app, host="0.0.0.0", port=PORT)
    else:
        mcp.run(transport=TRANSPORT)
