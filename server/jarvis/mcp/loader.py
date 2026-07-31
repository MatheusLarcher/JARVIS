"""Carrega servidores MCP declarados em config/mcp.yml como ferramentas do agente ADK.

Formato do config/mcp.yml:
    servers:
      home_assistant:
        enabled: false
        command: mcp-proxy          # stdio
        args: ["http://homeassistant.local:8123/mcp_server/sse"]
      windows:
        enabled: false
        command: npx
        args: ["-y", "@executeautomation/windows-mcp"]

Cada servidor habilitado vira um MCPToolset passado ao Agent em agents/agent.py.
"""
import logging
from pathlib import Path

import yaml

from ..config import CONFIG_DIR

log = logging.getLogger("jarvis.mcp")


def load_toolsets() -> list:
    cfg_path = Path(CONFIG_DIR) / "mcp.yml"
    if not cfg_path.exists():
        return []
    servers = (yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}).get("servers", {})
    toolsets = []
    for name, s in servers.items():
        if not s.get("enabled"):
            continue
        try:
            from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
            toolsets.append(MCPToolset(connection_params=StdioServerParameters(
                command=s["command"], args=s.get("args", []), env=s.get("env"))))
            log.info("MCP habilitado: %s", name)
        except Exception:
            log.exception("falha carregando MCP %s", name)
    return toolsets
