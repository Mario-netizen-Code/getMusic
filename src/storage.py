import json
import shutil
from datetime import date, datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


STORE_PATH = Path(__file__).parent.parent / "data" / "store.dat"
KEY_PATH = Path(__file__).parent.parent / "data" / ".key"
BACKUP_PATH = STORE_PATH.with_suffix(".dat.bak")
MAX_HISTORY = 500
SCHEMA = {"search_history", "download_history"}


def _load_key() -> bytes:
    if KEY_PATH.is_file():
        return KEY_PATH.read_bytes()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    return key


def _validate_schema(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    return SCHEMA.issubset(data.keys())


def _trim_history(data: dict) -> dict:
    for key in ("search_history", "download_history"):
        lst = data.get(key, [])
        if len(lst) > MAX_HISTORY:
            data[key] = lst[-MAX_HISTORY:]
    return data


class _Store:
    def __init__(self, path: Path):
        self._path = path
        self._cache: dict | None = None
        self._dirty: bool = False
        self._fernet = Fernet(_load_key())

    def _try_load(self, path: Path) -> dict | None:
        if not path.is_file():
            return None
        raw = path.read_bytes()
        if not raw:
            return None
        try:
            descifrado = self._fernet.decrypt(raw)
            data = json.loads(descifrado.decode("utf-8"))
            if _validate_schema(data):
                return data
        except (InvalidToken, Exception):
            pass
        return None

    def _load_raw(self) -> dict:
        if self._cache is not None:
            return self._cache

        data = self._try_load(self._path)
        if data is not None:
            self._cache = data
            self._dirty = False
            return self._cache

        data = self._try_load(BACKUP_PATH)
        if data is not None:
            self._cache = data
            self._dirty = False
            return self._cache

        self._cache = {"search_history": [], "download_history": []}
        self._dirty = False
        return self._cache

    def _save_raw(self, data: dict) -> None:
        self._cache = data
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty or self._cache is None:
            return
        data = _trim_history(self._cache)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.is_file():
            shutil.copy2(self._path, BACKUP_PATH)
        cifrado = self._fernet.encrypt(json.dumps(data).encode("utf-8"))
        self._path.write_bytes(cifrado)
        self._cache = data
        self._dirty = False


_store = _Store(STORE_PATH)


def flush_store() -> None:
    _store.flush()


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
