"""Owner-scoped local asset store.

Bytes live on disk under ``root``; a JSON sidecar records owner, kind and
metadata. IDs are random and opaque (not derived from content), so knowing a
file's hash does not reveal another user's asset ID. Every read checks
ownership and returns the same ``AssetNotFoundError`` for "missing" and "not
yours".
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from .errors import AssetNotFoundError

_ID_RE = re.compile(r"^(med|frm|crp)_[A-Za-z0-9_-]{16,64}$")
_PREFIX = {"media": "med", "frame": "frm", "crop": "crp"}


class LocalAssetStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_id(kind: str) -> str:
        return f"{_PREFIX[kind]}_{secrets.token_urlsafe(18)}"

    def _paths(self, asset_id: str) -> tuple[Path, Path]:
        if not _ID_RE.match(asset_id):
            raise AssetNotFoundError("asset not found")
        return self.root / f"{asset_id}.bin", self.root / f"{asset_id}.json"

    def temp_file(self) -> tuple[int, str]:
        return tempfile.mkstemp(prefix="upload_", suffix=".part", dir=self.root)

    def put_file(self, asset_id: str, src_path: str | os.PathLike[str], meta: dict[str, Any]) -> str:
        data_path, meta_path = self._paths(asset_id)
        os.replace(src_path, data_path)
        self._write_meta(meta_path, meta)
        return str(data_path.name)

    def put_bytes(self, asset_id: str, data: bytes, meta: dict[str, Any]) -> str:
        data_path, meta_path = self._paths(asset_id)
        tmp = data_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, data_path)
        self._write_meta(meta_path, meta)
        return str(data_path.name)

    @staticmethod
    def _write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
        tmp = meta_path.with_suffix(".jsontmp")
        tmp.write_text(json.dumps(meta, default=str))
        os.replace(tmp, meta_path)

    def meta(self, asset_id: str, owner_id: str) -> dict[str, Any]:
        _, meta_path = self._paths(asset_id)
        try:
            meta = json.loads(meta_path.read_text())
        except FileNotFoundError:
            raise AssetNotFoundError("asset not found") from None
        if not secrets.compare_digest(str(meta.get("owner_id", "")), str(owner_id)):
            raise AssetNotFoundError("asset not found")
        return meta

    def path(self, asset_id: str, owner_id: str) -> Path:
        self.meta(asset_id, owner_id)
        data_path, _ = self._paths(asset_id)
        if not data_path.exists():
            raise AssetNotFoundError("asset not found")
        return data_path

    def read_bytes(self, asset_id: str, owner_id: str) -> bytes:
        return self.path(asset_id, owner_id).read_bytes()

    def delete(self, asset_id: str, owner_id: str) -> None:
        self.meta(asset_id, owner_id)
        for p in self._paths(asset_id):
            p.unlink(missing_ok=True)
