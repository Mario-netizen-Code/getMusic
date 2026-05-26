import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

import yt_dlp
from tqdm import tqdm

from models import DownloadJob
from storage import register_search, register_download
from utils import sanitize_filename, tqdm_write


def descargar_mp3(url: str, salida: str, progress_callback=None) -> str:
    salida_path = Path(salida)

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        raw_title = info.get("title", url)

    max_stem = 100
    stem = sanitize_filename(raw_title)
    if len(stem) > max_stem:
        stem = stem[:max_stem].rstrip(". ")

    safe_stem = stem.replace("%", "%%")
    nombre_base = f"{safe_stem}.%(ext)s"

    hooks = [progress_callback] if progress_callback else []

    opciones = {
        "format": "bestaudio/best",
        "outtmpl": str(salida_path / nombre_base),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            },
            {"key": "FFmpegMetadata"},
        ],
        "postprocessor_args": ["-ab", "320k"],
        "prefer_ffmpeg": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": hooks,
    }

    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url])

    return url


def download_batch(jobs: list[DownloadJob], max_workers: int = 3, descargadas: set[str] | None = None) -> tuple[int, int, float]:
    total = len(jobs)
    done = 0
    start_time = time.time()
    ncols = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
    tqdm_write("")
    with tqdm(total=total, desc="Progreso", unit="archivo", ncols=ncols, file=sys.stdout) as pbar:
        def _hook(job):
            def _progreso(d):
                label = job.titulo[:40] if job.titulo else job.url.rsplit("/", 1)[-1][:40]
                if d["status"] == "downloading":
                    pct = d.get("_percent_str", "").strip()
                    pbar.set_postfix_str(f"{label} {pct}")
                elif d["status"] == "finished":
                    pbar.set_postfix_str(f"{label} - convirtiendo...")
            return _progreso

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = {}
            for job in jobs:
                futuros[executor.submit(descargar_mp3, job.url, job.salida, _hook(job))] = job
            pending = set(futuros.keys())
            try:
                while pending:
                    done_set, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for futuro in done_set:
                        job = futuros[futuro]
                        done += 1
                        try:
                            futuro.result()
                            if job.query:
                                register_search(job.query)
                            register_download(job.url, job.titulo, job.channel, job.query)
                            if descargadas is not None:
                                descargadas.add(job.url)
                            label = job.titulo[:40] if job.titulo else job.url.rsplit("/", 1)[-1][:40]
                            pbar.set_postfix_str(label)
                        except Exception as e:
                            label = job.titulo[:30] if job.titulo else job.url.rsplit("/", 1)[-1][:30]
                            pbar.set_postfix_str(f"Error: {label}")
                        pbar.update(1)
            except KeyboardInterrupt:
                tqdm_write("\n  Interrumpiendo descargas restantes...")
                for f in pending:
                    f.cancel()
                raise
    elapsed = time.time() - start_time
    return done, total, elapsed
