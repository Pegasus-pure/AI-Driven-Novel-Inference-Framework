from __future__ import annotations
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from server.data.novel_loader import NovelLoader


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_read_canon(source_file: str, section: str = "all") -> dict:
        """Read a canon JSON file and return its contents.

        Args:
            source_file: Path to the canon JSON file (e.g. "novel/canon_xxx.json")
            section: Which section to return — "all" returns everything;
                     use "characters", "locations", "world_rules", "timeline", "meta", "title"
        """
        path = Path(source_file)
        if not path.is_file():
            return {"source_file": source_file, "error": f"File not found: {source_file}"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return {"source_file": source_file, "error": f"Read error: {e}"}

        loader = NovelLoader()
        data = loader.import_canon_from_json(content)
        if data is None:
            return {"source_file": source_file, "error": "Failed to parse canon JSON"}

        title = data.get("title", path.stem)

        if section == "all":
            return {
                "source_file": source_file,
                "title": title,
                "section": "all",
                "data": data,
            }

        # Return specific section
        section_data = data.get(section)
        return {
            "source_file": source_file,
            "title": title,
            "section": section,
            "data": section_data,
        }
