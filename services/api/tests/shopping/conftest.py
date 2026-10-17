import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[2]
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))
