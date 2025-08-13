"""
TEMPORARY shim until backend/quik_connector is fully removed.
Provides QuikConnector in its new infra location but reuses implementation
from the legacy package so that imports keep working.
After S6-2b the original file will be deleted and the implementation
can be moved here or split further.
"""

from backend.quik_connector.core.quik_connector import *  # type: ignore # noqa
