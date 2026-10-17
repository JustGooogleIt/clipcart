import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[2]
_MEDIA_TESTS = _API / "tests" / "media"
for p in (_API, _MEDIA_TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest  # noqa: E402
from app.media.service import MediaService  # noqa: E402
from app.media.storage import LocalAssetStore  # noqa: E402


@pytest.fixture
def media(tmp_path):
    return MediaService(LocalAssetStore(tmp_path / "assets"))
