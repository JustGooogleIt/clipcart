import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[2]
for p in (_API, _API / "tests", _API / "tests" / "media"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from api.conftest import app_factory  # noqa: E402,F401
