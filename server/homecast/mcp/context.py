"""
MCP request context management.

Stores the current home_id for MCP requests so tools can access it.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable for the current MCP home_id (8-char prefix, lowercase)
_home_id_var: ContextVar[Optional[str]] = ContextVar("mcp_home_id", default=None)


def get_mcp_home_id() -> Optional[str]:
    """Get the current MCP home_id from context."""
    return _home_id_var.get()


def set_mcp_home_id(home_id: Optional[str]):
    """Set the MCP home_id in context."""
    _home_id_var.set(home_id)
