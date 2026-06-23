from __future__ import annotations
import yaml
from mcp.server.fastmcp import FastMCP

from server.config.paths import CONFIG_PATH


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def rain_config_view(section: str = "all", hide_secrets: bool = True) -> dict:
        """Read and display project config.yaml contents.

        Args:
            section: Config section to return ("all", "app", "providers", etc.)
            hide_secrets: If True, replace api_key values with "sk-****"
        """
        if not CONFIG_PATH.exists():
            return {"section": section, "data": None, "error": "config.yaml not found"}

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = f.read()
            data = yaml.safe_load(raw)
        except Exception as e:
            return {"section": section, "data": None, "error": f"Parse error: {e}"}

        if data is None:
            return {"section": section, "data": None, "error": "Empty config"}

        if section == "all":
            result_data = data
        else:
            result_data = data.get(section)

        if hide_secrets and isinstance(result_data, dict):
            _mask_secrets(result_data)

        return {
            "section": section,
            "data": result_data,
        }


def _mask_secrets(data: dict) -> None:
    """Recursively replace api_key and similar fields with masked values."""
    for key, value in data.items():
        if isinstance(value, dict):
            _mask_secrets(value)
        elif isinstance(key, str) and _is_secret_key(key) and isinstance(value, str) and value:
            data[key] = "sk-****"


def _is_secret_key(key: str) -> bool:
    """Check if a key name looks like a secret/credential."""
    secret_names = {"api_key", "secret", "token", "password", "api_secret", "access_key"}
    return key.lower() in secret_names
