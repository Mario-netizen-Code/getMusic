from dataclasses import dataclass


@dataclass
class DownloadJob:
    url: str
    salida: str
    query: str
    titulo: str
    channel: str
