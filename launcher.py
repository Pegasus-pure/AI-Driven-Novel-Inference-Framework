# -*- coding: utf-8 -*-
"""AI-Driven-Novel-Inference-Framework — 根入口

两种启动模式:
  1. Web 模式: python launcher.py → 启动 uvicorn，浏览器访问 localhost:8000
  2. 桌面模式: python launcher.py --desktop → pywebview 窗口嵌入

用法:
  python launcher.py                      # Web 模式（默认）
  python launcher.py --host 0.0.0.0      # Web 模式，允许局域网访问
  python launcher.py --port 8080          # Web 模式，指定端口
  python launcher.py --desktop            # 桌面模式（pywebview 窗口）
  python launcher.py --build              # 打包模式（PyInstaller 兼容）
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from pathlib import Path

# 确保项目根目录在 sys.path 中
_PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(str(_PROJECT_DIR))
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

_log = logging.getLogger("AINovelFramework.Launcher")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="AI-Driven-Novel-Inference-Framework",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="绑定地址（默认: 127.0.0.1）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务端口（默认: 8000）",
    )
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="以桌面模式启动（pywebview 窗口）",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="打包模式（PyInstaller 兼容）",
    )
    return parser.parse_args()


def load_config() -> dict:
    """加载 config.yaml"""
    import yaml
    config_path = _PROJECT_DIR / "config.yaml"
    if config_path.is_file():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def run_web_mode(host: str, port: int) -> None:
    """启动 Web 模式：uvicorn + FastAPI"""
    import uvicorn

    _log.info("═" * 50)
    _log.info("AI-Driven-Novel-Inference-Framework — Web 模式启动中...")
    _log.info("═" * 50)

    # 将 server.main:app 作为 uvicorn 目标
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


def run_desktop_mode(host: str, port: int) -> None:
    """启动桌面模式：uvicorn (后台) + pywebview 窗口"""
    try:
        import webview
    except ImportError:
        _log.error("pywebview 未安装。运行: pip install pywebview")
        sys.exit(1)

    import uvicorn

    cfg = load_config()
    desktop_cfg = cfg.get("desktop", {}) or {}
    app_cfg = cfg.get("app", {}) or {}

    window_title = app_cfg.get("title", "AI-Driven-Novel-Inference-Framework")
    window_width = int(desktop_cfg.get("window_width", 1280))
    window_height = int(desktop_cfg.get("window_height", 800))
    resizable = bool(desktop_cfg.get("resizable", True))

    # 在后台线程启动 uvicorn
    uvicorn_config = uvicorn.Config(
        "server.main:app",
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(uvicorn_config)

    def run_server() -> None:
        server.run()

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    # 等待服务器就绪
    import time
    time.sleep(1.5)

    url = f"http://{host}:{port}"
    _log.info("桌面模式: %s", url)

    # 启动 pywebview 窗口
    webview.create_window(
        title=window_title,
        url=url,
        width=window_width,
        height=window_height,
        resizable=resizable,
        fullscreen=False,
    )
    webview.start()


def main() -> None:
    """主入口"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    args = parse_args()

    host = args.host
    port = args.port

    # 从 config.yaml 读取默认值
    if not args.host or args.host == "127.0.0.1":
        cfg = load_config()
        app_cfg = cfg.get("app", {}) or {}
        host = app_cfg.get("host", args.host)
        port = int(app_cfg.get("port", args.port))

    _log.info("AI-Driven-Novel-Inference-Framework 启动: host=%s, port=%d", host, port)

    if args.desktop:
        run_desktop_mode(host, port)
    else:
        run_web_mode(host, port)


if __name__ == "__main__":
    main()
