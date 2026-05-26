# TUI Interactive Mode — Design Spec

## Overview
Replace the current `--add` interactive mode (prompt_toolkit dialogs + print) with a full terminal UI built on [Textual](https://textual.textualize.io/). Single-screen app with search, checkbox selection, concurrent download progress bars, and post-download flow.

## Layout

```
┌─────────────────────────────────────────────────────────┐
│ getMusic — Modo interactivo                              │
├─────────────────────────────────────────────────────────┤
│ Buscar: [___________________________________]           │
│                                                         │
│ Resultados — Página 1                                   │
│ ┌─────────────────────────────────────────────────────┐ │
│ │   │ # │ Título              │ Artista   │ Dur   Vistas│ │
│ │ ──┼───┼────────────────────┼───────────┼────────────│ │
│ │ ✓ │ 1 │ Bohemian Rhapsody  │ Queen      │ 5:55  1.2M │ │
│ │   │ 2 │ Don't Stop Me Now  │ Queen      │ 3:29  800K │ │
│ └─────────────────────────────────────────────────────┘ │
│ ← → páginas  [Espacio] toggle  [a] todo/nada  [Enter] bajar │
│                                                         │
│ [Descargar (1)]  [Salir]                                 │
├─────────────────────────────────────────────────────────┤
│ [Ctrl+Q] Salir                                          │
└─────────────────────────────────────────────────────────┘
```

## Key bindings

| Key | Action |
|---|---|
| `Espacio` | Toggle selection on current row |
| `a` | Select / deselect all |
| `→` / `←` | Next / previous page |
| `Enter` | Start download |
| `Ctrl+Q` / `q` | Quit |
| `Tab` | Focus next widget |

## States

| State | Widget visibility | Behavior |
|---|---|---|
| **Empty** | Input visible, empty results | Help text in results area |
| **Searching** | Input + loading indicator | Debounced yt-dlp search |
| **Results** | Input + DataTable | Results with checkboxes |
| **No results** | Input + "no results" message | User can try again |
| **Downloading** | Progress area replaces table | Per-song ProgressBars |
| **Complete** | Summary + action buttons | "New search" / "Quit" |

## Architecture

### Files

| File | Role |
|---|---|
| `src/tui_app.py` | **NEW** — `MusicApp(Textual.App)` |
| `src/main.py` | Modified: imports `MusicApp` instead of `modo_agregar` for `--add` |
| `src/ui.py` | Kept as fallback, no longer imported by default |

### Integration

- `downloader.descargar_mp3(url, salida, callback)` — called in `run_in_executor`
- Callback receives yt-dlp progress dicts → updates `ProgressBar` widget via `call_from_thread`
- `storage.*` — called directly for history/logging
- Search uses yt-dlp `YoutubeDL.extract_info` with `extract_flat=False` to get view counts

### Dependencies

- Add `textual` to `requirements.txt`

## Data flow

### Search
1. User types in Input widget
2. On change (debounced 300ms), submit search to executor
3. yt-dlp `ytsearch{N}:query` fetches results
4. Parse entries → populate DataTable rows
5. Track selected URLs in `self.selected: set[str]`

### Download
1. User presses Enter → collect selected `DownloadJob` objects
2. Switch view: hide DataTable, show progress container
3. For each job: create `ProgressBar` widget, submit `descargar_mp3` to executor
4. Callback updates ProgressBar via `call_from_thread`
5. When all done: show summary with counts

## Error handling

- Individual download failures shown inline (ProgressBar turns red)
- Other downloads continue unaffected
- Summary shows `✓ N/M completadas  ✗ K errores`
- Network/search errors shown in status bar
- KeyboardInterrupt cancels pending futures

## Implementation steps

1. Add `textual` to requirements.txt and install
2. Create `src/tui_app.py` with MusicApp class
3. Wire search → yt-dlp → DataTable population
4. Add toggle selection (Space, A key)
5. Implement pagination (→ / ←)
6. Build download phase with ProgressBar widgets
7. Add post-download summary + navigation
8. Update main.py to use tui_app in --add mode
9. Test all modes: normal, artist (@), raw (!), playlist
