from __future__ import annotations
from mcp.server.fastmcp import FastMCP
import ast, re, os

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_code_review(filepath: str, checks: str = "all") -> dict:
        """Run K1-K15 coding habits checks on a Python file.
        
        Args:
            filepath: Relative path from project root, e.g. server/app/game_session.py
            checks: Which checks to run: 'all' | 'k1,k4,k9' (comma-separated)
        """
        full_path = os.path.join(os.getcwd(), filepath)
        if not os.path.isfile(full_path):
            return {"error": f"File not found: {full_path}"}
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.splitlines()
        
        wanted = set(checks.split(",")) if checks != "all" else None
        
        results = {}
        
        # K1: from __future__ import annotations
        if not wanted or "k1" in wanted:
            results["k1_annotations"] = {
                "pass": content.startswith("from __future__ import annotations"),
                "desc": "File must start with 'from __future__ import annotations'"
            }
        
        # K2: File size
        if not wanted or "k2" in wanted:
            line_count = len(lines)
            status = "good" if line_count <= 800 else ("warn" if line_count <= 1200 else "bad")
            results["k2_file_size"] = {
                "pass": line_count <= 800,
                "desc": f"File size: {line_count} lines (threshold: 800)",
                "status": status
            }
        
        # K4: Type annotations on all functions
        if not wanted or "k4" in wanted:
            funcs = [l for l in lines if l.strip().startswith("def ")]
            total = len(funcs)
            annotated = sum(1 for f in funcs if "->" in f)
            results["k4_type_annotations"] = {
                "pass": annotated == total,
                "desc": f"Functions with return types: {annotated}/{total}",
                "unannotated": [f.strip()[:60] for f in funcs if "->" not in f][:5]
            }
        
        # K6: raise/assert with messages
        if not wanted or "k6" in wanted:
            raises = [l.strip() for l in lines if l.strip().startswith(("raise ", "assert "))]
            bare = [r for r in raises if '"' not in r and "'" not in r]
            results["k6_error_messages"] = {
                "pass": len(bare) == 0,
                "desc": f"raise/assert without message: {len(bare)}",
                "bare": bare[:5]
            }
        
        # K7: Docstrings
        if not wanted or "k7" in wanted:
            tree = ast.parse(content)
            funcs_ast = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            public = [f for f in funcs_ast if not f.name.startswith("_")]
            with_doc = sum(1 for f in public if ast.get_docstring(f))
            results["k7_docstrings"] = {
                "pass": with_doc == max(len(public), 1),
                "desc": f"Public functions with docstrings: {with_doc}/{max(len(public), 1)}"
            }
        
        # K9: Function length
        if not wanted or "k9" in wanted:
            tree = ast.parse(content)
            funcs_ast = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            long_funcs = [(f.name, f.end_lineno - f.lineno) for f in funcs_ast if (f.end_lineno - f.lineno) > 60]
            results["k9_func_length"] = {
                "pass": len(long_funcs) == 0,
                "desc": f"Functions > 60 lines: {len(long_funcs)}",
                "long_funcs": [{"name": n, "lines": l} for n, l in long_funcs[:5]]
            }
        
        # K11: Dataclass usage (heuristic: count @dataclass vs class with __init__)
        if not wanted or "k11" in wanted:
            dc = content.count("@dataclass")
            normal_classes = len(re.findall(r"^class \w+.*:$", content, re.MULTILINE))
            results["k11_dataclasses"] = {
                "pass": True,
                "desc": f"{dc} dataclass(es) out of {normal_classes} class(es)",
                "dataclass_count": dc,
                "total_classes": normal_classes
            }
        
        # K14: print() usage (should use logger)
        if not wanted or "k14" in wanted:
            prints = [i + 1 for i, l in enumerate(lines) if re.match(r"^\s*print\(", l)]
            results["k14_no_print"] = {
                "pass": len(prints) == 0,
                "desc": f"print() calls found: {len(prints)}",
                "lines": prints[:10]
            }
        
        passed = sum(1 for v in results.values() if v["pass"])
        total = len(results)
        
        return {
            "file": filepath,
            "line_count": len(lines),
            "score": f"{passed}/{total}",
            "percent": round(passed / total * 100),
            "results": results
        }
