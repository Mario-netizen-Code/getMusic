# GetMusic

Console tool to download YouTube audio as MP3, with interactive search mode.

## Requirements

- **Python 3.10+**
- **ffmpeg** in system PATH (for MP3 conversion)
- Internet connection

## Setup

```powershell
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

### Batch download from URLs file

```powershell
.\venv\Scripts\python main.py
.\venv\Scripts\python main.py -o "C:\salida" -j 5 urls.txt
.\venv\Scripts\python main.py --skip-downloaded urls.txt
```

### Interactive mode — search and download directly

```powershell
.\venv\Scripts\python main.py --add
.\venv\Scripts\python main.py --add -j 5
```

Type a song name, get autocomplete suggestions in real time, choose from results via checkbox, and it downloads on the spot. Use `←`/`→` arrows in the checkbox to navigate pages. All items are pre-selected by default — uncheck the ones you don't want.

Prefixes in interactive mode:

| Prefix   | Example                             | Behavior                                                                                                       |
| -------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| *(none)* | `Bohemian Rhapsody`                 | Searches with " audio" suffix, checkbox multi-select                                                           |
| `!`      | `!Bohemian Rhapsody`                | Raw search (no suffix), checkbox multi-select                                                                  |
| `@`      | `@Queen`                            | Artist mode — up to 50 results per page, checkbox multi-select, concurrent download to `downloads/ArtistName/` |
| `/(URL)` | `/https://youtube.com/playlist?...` | Playlist mode — extract all videos, checkbox selection, concurrent download                                    |
| *(URL)*  | `https://youtube.com/playlist?...`  | Auto-detected playlist — same as `/` prefix                                                                    |

### Arguments

| Arg                 | Default     | Description                                                     |
| ------------------- | ----------- | --------------------------------------------------------------- |
| `archivo`           | `urls.txt`  | Text file with one YouTube URL per line                         |
| `-o, --output`      | `downloads` | Base output directory                                           |
| `-j, --jobs`        | `3`         | Number of concurrent downloads (used for batch and artist mode) |
| `--add`             | —           | Interactive mode with autocomplete and checkbox selection       |
| `--skip-downloaded` | —           | Skip URLs already present in download history                   |

### Input file format

```
https://www.youtube.com/watch?v=VIDEO_ID
# Lines starting with # are ignored
https://youtu.be/OTHER_ID
```

## Features

- **Concurrent downloads** — parallel downloads with `-j` (default 3)
- **Progress bars** — one bar per download with speed and ETA, stays visible after completion
- **320 kbps MP3** — extracts best audio with ffmpeg
- **Metadata** — title, artist, album, etc. embedded via FFmpegMetadata
- **Smart filenames** — truncated to 100 chars, invalid characters sanitized
- **Interactive search** — `--add` mode with real-time YouTube + history autocomplete
- **Checkbox selection** — pick multiple results per page, pre-selected by default
- **Pagination** — press `Cancel` in checkbox to load next page (new search each time)
- **Artist mode** — `@ArtistName` shows up to 50 results, browse pages, download many in parallel. Saves to `downloads/ArtistName/`
- **Playlist mode** — paste a playlist URL (auto-detected or with `/` prefix), select videos via checkbox (all pre-selected), concurrent download
- **Search history** — encrypted history (`search_history.dat`) with autocomplete suggestions
- **Download memory** — encrypted log (`download_history.dat`), shows `✓` next to already-downloaded songs in checkbox, skip with `--skip-downloaded`
- **Smart spinner** — shows elapsed time and "aún buscando..." warning after 5s
- **Keyboard interrupt** — Ctrl+C handled gracefully in both batch and interactive modes
- **Organized output** — saved to `{output}/{YYYY-MM-DD}/`; artist downloads to `{output}/ArtistName/`; `urls.txt` renamed on completion
- **Summary stats** — `✓ X/Y canciones en Zs` after each batch

## Dependencies

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download engine
- [tqdm](https://github.com/tqdm/tqdm) — progress bars
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — interactive input, autocomplete, checkbox dialogs
- [cryptography](https://github.com/pyca/cryptography) — encrypted search/download history
