import base64
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


STORE_PATH = Path(__file__).parent.parent / "data" / "store.dat"


def _clave_fernet() -> bytes:
    material = f"{os.environ.get('USERNAME','')}-{os.environ.get('COMPUTERNAME','')}"
    return base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())


class _Store:
    def __init__(self, path: Path):
        self._path = path
        self._cache: dict | None = None

    def _load_raw(self) -> dict:
        if self._cache is not None:
            return self._cache
        if not self._path.is_file():
            self._cache = {"search_history": [], "download_history": []}
            return self._cache
        try:
            raw = self._path.read_bytes()
            if not raw:
                self._cache = {"search_history": [], "download_history": []}
                return self._cache
            clave = _clave_fernet()
            descifrado = Fernet(clave).decrypt(raw)
            data = json.loads(descifrado.decode("utf-8"))
            self._cache = data if isinstance(data, dict) else {"search_history": [], "download_history": []}
            return self._cache
        except (InvalidToken, Exception):
            self._cache = {"search_history": [], "download_history": []}
            return self._cache

    def _save_raw(self, data: dict) -> None:
        self._cache = data
        self._path.parent.mkdir(parents=True, exist_ok=True)
        clave = _clave_fernet()
        cifrado = Fernet(clave).encrypt(json.dumps(data).encode("utf-8"))
        self._path.write_bytes(cifrado)


_store = _Store(STORE_PATH)


def _cargar_historial() -> list[dict]:
    return _store._load_raw()["search_history"]


def _guardar_historial(entries: list[dict]) -> None:
    data = _store._load_raw()
    data["search_history"] = entries
    _store._save_raw(data)


def search_history_suggestions(query: str) -> list[str]:
    query_lower = query.lower()
    result = []
    for e in _cargar_historial():
        q = e.get("query", "")
        if query_lower in q.lower():
            result.append(q)
    return result


def register_search(query: str) -> None:
    if not query.strip():
        return
    entries = _cargar_historial()
    now = date.today().isoformat()
    for e in entries:
        if e["query"].lower() == query.lower():
            e["count"] = e.get("count", 0) + 1
            e["last_download"] = now
            break
    else:
        entries.append({"query": query, "count": 1, "last_download": now})
    _guardar_historial(entries)


def load_downloads() -> list[dict]:
    return _store._load_raw()["download_history"]


def _guardar_descargas(entries: list[dict]) -> None:
    data = _store._load_raw()
    data["download_history"] = entries
    _store._save_raw(data)


def register_download(url: str, titulo: str, channel: str, query: str) -> None:
    if not url:
        return
    entries = load_downloads()
    now = datetime.now().isoformat()
    for e in entries:
        if e["url"] == url:
            e["count"] = e.get("count", 0) + 1
            e["last_download"] = now
            break
    else:
        entries.append({
            "url": url,
            "title": titulo,
            "channel": channel,
            "query": query,
            "downloaded_at": now,
            "count": 1,
        })
    _guardar_descargas(entries)
