from __future__ import annotations
from mcp.server.fastmcp import FastMCP
import os, re, json

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_ui_audit() -> dict:
        """Audit frontend-backend API consistency. 
        Scans static/js/ for WS sends and server/main.py for handlers, then reports gaps."""
        
        project_root = os.getcwd()
        frontend_calls = set()
        backend_handlers = set()
        
        # Scan frontend JS for WS message sends
        js_dir = os.path.join(project_root, "static", "js")
        if os.path.isdir(js_dir):
            for root, dirs, files in os.walk(js_dir):
                dirs[:] = [d for d in dirs if d not in ("node_modules",)]
                for f in files:
                    if f.endswith(".js"):
                        fp = os.path.join(root, f)
                        try:
                            with open(fp, "r", encoding="utf-8") as fh:
                                content = fh.read()
                            # Match: ws.send('message_type', ...) or send("message_type", ...)
                            sends = re.findall(r"send\([\"'](\w+)[\"']", content)
                            emits = re.findall(r"emit\([\"'](\w+)[\"']", content)
                            for s in sends + emits:
                                frontend_calls.add(s)
                        except:
                            pass
        
        # Scan backend main.py for msg_type handlers
        main_path = os.path.join(project_root, "server", "main.py")
        if os.path.isfile(main_path):
            with open(main_path, "r", encoding="utf-8") as f:
                content = f.read()
            handlers = re.findall(r"msg_type == \"(\w+)\"", content)
            backend_handlers = set(handlers)
        
        # Also check server.py routes
        routes = set()
        for root, dirs, files in os.walk(os.path.join(project_root, "server")):
            for f in files:
                if f.endswith(".py"):
                    fp = os.path.join(root, f)
                    try:
                        with open(fp, "r", encoding="utf-8") as fh:
                            c = fh.read()
                        # @app.get/post/put/delete routes
                        found = re.findall(r"@app\.\w+\([\"']([^\"']+)[\"']", c)
                        routes.update(found)
                    except:
                        pass
        
        # Compute gaps
        frontend_only = frontend_calls - backend_handlers
        backend_only = backend_handlers - frontend_calls
        matched = frontend_calls & backend_handlers
        
        return {
            "frontend_calls": sorted(frontend_calls),
            "backend_handlers": sorted(backend_handlers),
            "matched": sorted(matched),
            "frontend_only_gaps": sorted(frontend_only),
            "backend_only_unused": sorted(backend_only),
            "api_routes": sorted(routes),
            "summary": f"{len(matched)} matched, {len(frontend_only)} frontend gaps, {len(backend_only)} backend unused"
        }
