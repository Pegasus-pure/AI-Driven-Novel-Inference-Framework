from __future__ import annotations
from mcp.server.fastmcp import FastMCP

from server.data.novel_loader import NovelLoader


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_list_canons() -> list[dict]:
        """List all canon JSON files and novel directories in the novel/ folder.

        Returns a list of dicts with title, source_file, char_count, loc_count, and type.
        """
        loader = NovelLoader()
        # Use project-relative "novel" directory (resolved by NovelLoader via Path("novel"))
        result = loader.scan_novel_directory("novel")

        items: list[dict] = []

        # Canon JSON files
        for canon in result.get("canons", []) or []:
            items.append({
                "title": canon.get("title", ""),
                "source_file": canon.get("source_file", ""),
                "char_count": canon.get("char_count", 0),
                "loc_count": canon.get("loc_count", 0),
                "type": "canon",
            })

        # Running canons (subdirectories with meta.json)
        for rc in result.get("running_canons", []) or []:
            items.append({
                "title": rc.get("title", ""),
                "source_file": rc.get("dir", ""),
                "char_count": rc.get("char_count", 0),
                "loc_count": rc.get("loc_count", 0),
                "type": "running_canon",
            })

        return items
