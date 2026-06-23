from __future__ import annotations
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Rain Dev")

# Register tools
from server.mcp.tools.canon_list import register as _reg_canon_list
_reg_canon_list(mcp)

from server.mcp.tools.canon_read import register as _reg_canon_read
_reg_canon_read(mcp)

from server.mcp.tools.health import register as _reg_health
_reg_health(mcp)

from server.mcp.tools.memory_query import register as _reg_memory
_reg_memory(mcp)

from server.mcp.tools.config_view import register as _reg_config
_reg_config(mcp)

from server.mcp.tools.debug_log import register as _reg_debug_log
_reg_debug_log(mcp)

from server.mcp.tools.code_inspect import register as _reg_code_inspect
_reg_code_inspect(mcp)

from server.mcp.tools.code_review import register as _reg_code_review
_reg_code_review(mcp)

from server.mcp.tools.ui_audit import register as _reg_ui_audit
_reg_ui_audit(mcp)

from server.mcp.tools.cross_review import register as _reg_cross_review
_reg_cross_review(mcp)

from server.mcp.tools.task_route import register as _reg_task_route
_reg_task_route(mcp)

from server.mcp.tools.terminal_log import register as _reg_terminal_log
_reg_terminal_log(mcp)


def run() -> None:
    """stdio mode entry point."""
    mcp.run()
