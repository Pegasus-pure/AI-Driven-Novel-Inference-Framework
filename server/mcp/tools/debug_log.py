from __future__ import annotations
import re
from pathlib import Path
from mcp.server.fastmcp import FastMCP


_DEFAULT_LOG = Path("logs/rain.log")

# Matches: [HH:MM:SS] [LEVEL] [LoggerName] message
_LOG_PATTERN = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(.*)$"
)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_debug_log(
        lines: int = 50,
        level: str = "all",
        source: str = "",
    ) -> dict:
        """Read and filter the Rain debug log file.

        Args:
            lines: Number of lines to read from the end of the log
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR) or "all"
            source: Log file path; defaults to "logs/rain.log"
        """
        log_path = Path(source) if source else _DEFAULT_LOG

        if not log_path.is_file():
            return {
                "source": str(log_path),
                "total_lines": 0,
                "returned": 0,
                "entries": [],
                "error": "Log file not found",
            }

        try:
            raw_lines = _tail(log_path, lines)
        except Exception as e:
            return {
                "source": str(log_path),
                "total_lines": 0,
                "returned": 0,
                "entries": [],
                "error": f"Read error: {e}",
            }

        entries: list[dict] = []
        for line in raw_lines:
            entry = _parse_line(line)
            if entry is None:
                continue
            if level != "all" and entry["level"].upper() != level.upper():
                continue
            entries.append(entry)

        return {
            "source": str(log_path),
            "total_lines": len(raw_lines),
            "returned": len(entries),
            "entries": entries,
        }


def _tail(path: Path, n: int) -> list[str]:
    """Read the last N lines of a file efficiently."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return all_lines[-n:] if n > 0 else all_lines


def _parse_line(line: str) -> dict | None:
    """Parse a log line into structured dict."""
    line = line.strip()
    if not line:
        return None

    m = _LOG_PATTERN.match(line)
    if m:
        return {
            "timestamp": m.group(1),
            "level": m.group(2),
            "logger": m.group(3),
            "message": m.group(4),
        }

    # Fallback: return raw line
    return {
        "timestamp": "",
        "level": "UNKNOWN",
        "logger": "",
        "message": line,
    }
