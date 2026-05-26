import re
import sys

from tqdm import tqdm


def tqdm_write(*args, **kwargs):
    kwargs.setdefault("file", sys.stdout)
    tqdm.write(*args, **kwargs)


def sanitize_filename(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*]', "_", nombre)
    nombre = nombre.replace("\0", "")
    nombre = nombre.strip(". ")
    return nombre


def is_playlist_url(text: str) -> bool:
    return bool(re.match(
        r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.*(\?|&)list=",
        text,
    ))
