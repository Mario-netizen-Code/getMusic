from typing import NamedTuple


class DownloadJob(NamedTuple):
    url: str
    salida: str
    query: str
    titulo: str
    channel: str
