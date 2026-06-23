from __future__ import annotations
from mcp.server.fastmcp import FastMCP
import subprocess, os, tempfile


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_terminal_log(lines: int = 30, filter_warn: bool = True) -> dict:
        """Read the Rain Web server's terminal output (warnings/errors from the running uvicorn process).
        
        Captures the most recent terminal warnings and errors from the server process.
        Use this when you see warnings in VSCode terminal but can't access the text directly.

        Args:
            lines: Number of recent log lines to return
            filter_warn: If True, only show WARNING and ERROR level lines
        """
        project_root = os.getcwd()

        # Strategy 1: Check for piped log file
        log_paths = [
            os.path.join(project_root, "logs", "rain.log"),
            os.path.join(project_root, "server", "logs", "rain.log"),
            os.path.join(project_root, "rain.log"),
        ]
        
        entries = []
        for log_path in log_paths:
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    all_lines = f.readlines()
                start = max(0, len(all_lines) - lines)
                for line in all_lines[start:]:
                    line = line.strip()
                    if not line:
                        continue
                    if filter_warn and "WARNING" not in line.upper() and "ERROR" not in line.upper() and "Traceback" not in line:
                        continue
                    entries.append(line)
                if entries:
                    return {
                        "source": log_path,
                        "method": "log_file",
                        "total_lines": len(all_lines),
                        "entries": entries[-lines:],
                    }

        # Strategy 2: Check for running uvicorn process windows
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            python_pids = []
            for line in result.stdout.strip().split("\n"):
                if "python" in line.lower():
                    parts = line.replace('"', "").split(",")
                    if len(parts) >= 2:
                        python_pids.append(parts[1].strip())
            
            if python_pids:
                entries.append(f"Found {len(python_pids)} Python processes running")
                entries.append("To view live output, check VSCode terminal tab, or run:")
                entries.append("  tail -f logs/rain.log  (if logging to file)")
                entries.append("  Or redirect: python -m server.main 2>&1 | tee logs/rain.log")
                return {
                    "source": "process_list",
                    "method": "tasklist",
                    "python_processes": len(python_pids),
                    "entries": entries,
                    "hint": "No log file found. Start server with: python -m server.main 2>&1 | tee logs/rain.log"
                }
        except Exception:
            pass

        # Strategy 3: Try most recent temp output
        try:
            tmp_dir = tempfile.gettempdir()
            candidates = [f for f in os.listdir(tmp_dir) if "rain" in f.lower() and ("log" in f.lower() or "out" in f.lower())]
            if candidates:
                newest = sorted(candidates)[-1]
                entries.append(f"Found temp log: {os.path.join(tmp_dir, newest)}")
                return {
                    "source": os.path.join(tmp_dir, newest),
                    "method": "temp_file",
                    "entries": entries,
                }
        except Exception:
            pass

        return {
            "source": "none",
            "method": "none",
            "entries": [
                "No log file or running server detected.",
                "Start server with: python -m server.main 2>&1 | tee logs/rain.log",
                "Then the MCP can read warnings from logs/rain.log"
            ],
            "hint": "Run: mkdir -p logs && python -m server.main 2>&1 | tee logs/rain.log"
        }
