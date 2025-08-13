from __future__ import annotations

# Temporary re-export while moving low-level connector into infra package
from backend.quik_connector.core.quik_connector import QuikConnector  # type: ignore

__all__ = ["QuikConnector"]
