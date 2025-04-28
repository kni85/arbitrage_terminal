# backend/vendor_bootstrap.py  (создайте, чтобы один раз прописать путь)
import sys
from pathlib import Path

vendor_path = Path(__file__).resolve().parent / "vendor"
if str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))
