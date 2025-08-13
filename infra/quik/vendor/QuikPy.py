"""Shim module that re-exports QuikPy from legacy backend package.
Will be replaced by actual vendor code when backend/quik_connector is removed.
"""
from backend.quik_connector.vendor.QuikPy import *  # type: ignore # noqa
