from __future__ import annotations
from mcp.server.fastmcp import FastMCP

from server.manana.memory.persist import MemoryPersister


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_memory_query(
        novel_title: str,
        agent_id: str = "director",
        query: str = "",
        top_k: int = 10,
        memory_type: str = "all",
    ) -> dict:
        """Query agent memory entries from JSONL persistence.

        Args:
            novel_title: Novel title directory name (e.g. "女主角们都想杀掉我")
            agent_id: Agent identifier (e.g. "director", "author", "editor")
            query: Fuzzy match filter on entry content (case-insensitive)
            top_k: Maximum number of entries to return
            memory_type: Filter by memory type field, or "all" for no filter
        """
        persister = MemoryPersister()
        all_entries = persister.load_agent(novel_title, agent_id)

        # Filter by query
        query_lower = query.lower()
        filtered = all_entries
        if query:
            filtered = [
                e for e in all_entries
                if query_lower in str(e.get("content", "")).lower()
                   or query_lower in str(e.get("summary", "")).lower()
                   or query_lower in str(e.get("role", "")).lower()
            ]

        # Filter by memory_type
        if memory_type != "all":
            filtered = [
                e for e in filtered
                if e.get("type", "") == memory_type
                   or e.get("memory_type", "") == memory_type
            ]

        # Apply top_k
        entries = filtered[:top_k]

        return {
            "novel_title": novel_title,
            "agent_id": agent_id,
            "total_entries": len(all_entries),
            "filtered": len(filtered),
            "entries": entries,
        }
