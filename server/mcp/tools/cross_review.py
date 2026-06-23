from __future__ import annotations
from mcp.server.fastmcp import FastMCP
import os, subprocess

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_cross_review(target: str = "changed", depth: str = "summary") -> dict:
        """Cross-review recent code changes from two perspectives: architect (structure) and QA (correctness).
        
        Args:
            target: What to review: 'changed' (git diff), 'file:<path>', or 'module:<name>'  
            depth: 'summary' or 'detailed'
        """
        project_root = os.getcwd()
        
        perspectives = {
            "architect": {
                "focus": ["module coupling", "import chain", "circular dependency risk", "single responsibility", "naming consistency"],
                "checklist": [
                    "Are new imports in the right package (app/data/network/config)?",
                    "Does this change increase coupling between packages?",
                    "Is any file exceeding 800 lines?",
                    "Are new classes in the correct sub-package?"
                ]
            },
            "qa": {
                "focus": ["edge cases", "error handling", "test coverage", "backward compatibility"],
                "checklist": [
                    "Are all new raise/assert statements descriptive?",
                    "Do except blocks have logging?",
                    "Are API changes reflected in frontend WS handlers?",
                    "Is there a regression risk for existing flows?"
                ]
            }
        }
        
        # Get changed files
        changed_files = []
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1"],
                cwd=project_root, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                changed_files = [f for f in result.stdout.strip().split("\n") if f]
        except:
            try:
                # Fallback: git status
                result = subprocess.run(
                    ["git", "status", "--short"],
                    cwd=project_root, capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    changed_files = [l[3:] for l in result.stdout.strip().split("\n") if l]
            except:
                changed_files = ["cannot detect - no git history"]

        return {
            "target": target,
            "depth": depth,
            "changed_files": changed_files[:20],
            "file_count": len(changed_files),
            "perspectives": perspectives,
            "instruction": "Cross-review the changed files above through both architect and QA lenses. Report findings per checklist item."
        }
