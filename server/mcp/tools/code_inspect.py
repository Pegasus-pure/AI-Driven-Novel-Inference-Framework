from __future__ import annotations
import ast
from pathlib import Path
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_code_inspect(module: str, detail_level: str = "summary") -> dict:
        """Inspect a Python module under server/ using AST analysis.

        Args:
            module: Module name (e.g. "data/novel_loader") or full file path
            detail_level: "summary" (class/function names) or "full" (signatures too)
        """
        # Resolve the file path
        if module.endswith(".py"):
            file_path = Path(module)
        else:
            file_path = Path(f"server/{module}.py")

        if not file_path.is_file():
            return {"module": module, "error": f"File not found: {file_path}"}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception as e:
            return {"module": module, "error": f"Read error: {e}"}

        size = len(source.encode("utf-8"))
        line_count = source.count("\n") + (0 if source.endswith("\n") else 1)

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            return {
                "module": module,
                "file": str(file_path),
                "error": f"Syntax error: {e}",
            }

        classes: list[str] = []
        functions: list[str] = []
        imports: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in ast.iter_child_nodes(node)
                    if isinstance(n, ast.FunctionDef)
                ]
                if detail_level == "full":
                    classes.append(f"class {node.name} (methods: {', '.join(methods)})")
                else:
                    classes.append(f"{node.name} ({len(methods)} methods)")

            elif isinstance(node, ast.FunctionDef):
                # Only top-level functions (not methods inside classes)
                if _is_toplevel(node, tree):
                    if detail_level == "full":
                        sig = _get_signature(node)
                        functions.append(sig)
                    else:
                        functions.append(node.name)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"{module_name}.{alias.name} as {alias.asname}")
                    else:
                        imports.append(f"{module_name}.{alias.name}")

        return {
            "module": module,
            "file": str(file_path),
            "size": size,
            "classes": classes,
            "functions": functions,
            "imports": sorted(set(imports)),
            "line_count": line_count,
        }


def _is_toplevel(func_node: ast.FunctionDef, tree: ast.AST) -> bool:
    """Check if a function is defined at module level (not inside a class)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if child is func_node:
                    return False
    return True


def _get_signature(node: ast.FunctionDef) -> str:
    """Build a human-readable function signature string."""
    args: list[str] = []
    for arg in node.args.args:
        annotation = ""
        if arg.annotation:
            annotation = f": {ast.unparse(arg.annotation)}"
        default = ""
        args.append(f"{arg.arg}{annotation}{default}")
    return_str = ""
    if node.returns:
        return_str = f" -> {ast.unparse(node.returns)}"
    return f"def {node.name}({', '.join(args)}){return_str}"
