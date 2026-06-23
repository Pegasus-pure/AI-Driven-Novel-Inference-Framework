from __future__ import annotations
from mcp.server.fastmcp import FastMCP

from server.config.paths import CONFIG_PATH, NOVEL_DIR, SAVES_DIR, STATIC_DIR
from server.data.novel_loader import NovelLoader


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_dev_health(verbose: bool = False) -> dict:
        """Check project health: paths, canon count, issues.

        Args:
            verbose: If True, include additional diagnostic details.
        """
        checks: dict[str, dict] = {}

        # Config check
        config_ok = CONFIG_PATH.exists()
        checks["config"] = {
            "ok": config_ok,
            "path": str(CONFIG_PATH),
        }

        # Novel directory check
        novel_ok = NOVEL_DIR.is_dir()
        checks["novel_dir"] = {
            "ok": novel_ok,
            "path": str(NOVEL_DIR),
        }

        # Saves directory check
        saves_ok = SAVES_DIR.is_dir()
        checks["saves_dir"] = {
            "ok": saves_ok,
            "path": str(SAVES_DIR),
        }

        # Static directory check
        static_ok = STATIC_DIR.is_dir()
        checks["static_dir"] = {
            "ok": static_ok,
            "path": str(STATIC_DIR),
        }

        # Canon count
        issues: list[str] = []
        canon_count = 0
        try:
            loader = NovelLoader()
            scan_result = loader.scan_novel_directory("novel")
            canons = scan_result.get("canons", []) or []
            running_canons = scan_result.get("running_canons", []) or []
            canon_count = len(canons) + len(running_canons)
            checks["canons"] = {
                "ok": canon_count > 0,
                "count": canon_count,
                "canon_files": len(canons),
                "running_canons": len(running_canons),
            }
        except Exception as e:
            canon_count = 0
            checks["canons"] = {"ok": False, "count": 0, "error": str(e)}
            issues.append(f"canon scan error: {e}")

        if not config_ok:
            issues.append("config.yaml not found")
        if not novel_ok:
            issues.append("novel/ directory not found")
        if not saves_ok:
            issues.append("saves/ directory not found")
        if canon_count == 0:
            issues.append("no canon files found")

        all_ok = config_ok and novel_ok and saves_ok and static_ok and len(issues) == 0
        status = "healthy" if all_ok else "degraded"

        result: dict = {
            "status": status,
            "checks": checks,
            "project_root": str(NOVEL_DIR.parent),
            "canon_count": canon_count,
            "issues": issues,
        }

        if verbose:
            import sys
            result["python_version"] = sys.version

        return result
