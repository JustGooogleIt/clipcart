import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[2]  # services/api
_HERE = Path(__file__).resolve().parent
for p in (_API, _HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest  # noqa: E402
from app.media.service import MediaService  # noqa: E402
from app.media.storage import LocalAssetStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return LocalAssetStore(tmp_path / "assets")


@pytest.fixture
def media(store):
    return MediaService(store)
