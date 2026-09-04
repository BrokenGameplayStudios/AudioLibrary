# Audio Library

A local browser for a folder of game audio packs.

Scan a root folder and its subfolders, then search, filter, and preview wav / mp3 / ogg / flac from your machine. No cloud, no installers, no pip packages.

**Maintained by:** [Broken Gameplay Studios](https://github.com/BrokenGameplayStudios)

## Features

* Recursively indexes a folder you choose (music, voice, SFX packs)
* Search by name, pack, folder, or tag
* Filter by type (music / voice / SFX), tags, and pack
* In-page preview player with seek and volume
* Open the file in Explorer
* Works from a mapped drive or a UNC share (`\\server\share`)
* Remembers the last library folder in `config.json`
* Cached index in `catalog.json` so the next launch is instant

## Installation

1. Install **Python 3.12+** from [python.org](https://www.python.org/downloads/)
   - Enable **Add python.exe to PATH**
   - Enable the **py launcher**
   - Do **not** use the Microsoft Store Python stub
2. Clone this repo (or copy `server.py`, `index.html`, and `start-library.bat` into a folder):

```powershell
git clone https://github.com/BrokenGameplayStudios/AudioLibrary.git
```

3. Double-click `start-library.bat`

That is the whole install. There are no extra Python packages.

### Optional layout

You can drop the repo (or just `server.py`, `index.html`, and `start-library.bat`) into a `_library` folder next to your audio packs:

```
Audio/
  _library/          ← this repo
  MyMusicPack/
  MyVoicePack/
  MySfxPack/
  packkind.json      ← optional tags next to the packs, not inside _library
```

On first launch it will use the parent folder as the library root if you have not picked one yet.

## Quick Start

1. Double-click `start-library.bat`
2. The browser opens on `http://127.0.0.1:8765/` (or the next free port if 8765 is taken)
3. Click **Library folder…** and pick the root of your audio
4. Wait for the scan to finish — the header shows a live file count
5. Search, filter, and click a row to preview

**Rescan** re-indexes the current folder. **Library folder…** points the app at a different root.

Stop the server with Ctrl+C in the console window.

The first scan of tens of thousands of files on a UNC share can take a few minutes. After that, `catalog.json` makes the next launch instant.

## Requirements

| | |
|---|---|
| OS | Windows (launcher). macOS / Linux can run `python3 server.py` |
| Python | 3.12+ from python.org |
| Extra packages | None (stdlib only: `http.server`, `tkinter` for the folder dialog) |
| Audio formats | `.wav` `.mp3` `.ogg` `.flac` `.aiff` `.aif` `.m4a` `.aac` |

## Keyboard

| Key | Action |
|---|---|
| `/` | Focus search |
| Space | Play / pause |
| ↑ ↓ | Select row |
| Enter | Play selected |
| O | Open folder of selected / playing file |
| ← → | Seek 5 seconds |

## How it works

The bat starts a local HTTP server on `127.0.0.1`. The page talks to:

* `GET /api/catalog` — current index (never blocks on a disk walk)
* `GET /api/status` — scan progress
* `POST /api/browse-root` — native folder picker, then a background scan
* `POST /api/rescan` — scan the current root again
* `POST /api/open` — open the file in Explorer
* `GET /media/<id>` — ranged audio for the player

`catalog.json` and `config.json` are generated next to `server.py` and are not part of the git repo.

Skipped while scanning: `_library`, `_ZIP`, `_export`, hidden folders, and `._*` AppleDouble files. `packkind.json` is a sidecar, not a pack.

## How it stores tags

A file named `packkind.json` lives **next to the packs**, not inside `_library`. The app reads it when it scans. Filenames also add tags automatically.

An editor exporter can write a starter `packkind.json`; the library uses that file plus filename clues.

## Troubleshooting

**`start-library.bat` flashes and says `py -3` failed**
Install Python from python.org. In a new Command Prompt, `py -3 --version` should print a 3.x version. The Store `python.exe` stub cannot read network shares.

If the bat is missing, open a Command Prompt in this folder and run:

```
py -3 server.py
```

**CMD does not support UNC paths**
The launcher uses `pushd` so a share such as `\\server\Audio\_library` is mapped to a drive letter. Run the bat; do not `cd` to the UNC path yourself.

**Browser opens but the list is empty**
Click **Library folder…** and pick the folder that *contains* your packs (not a single wav). Subfolders are included. Files sitting in that root folder are indexed too.

**Port already in use**
The server tries 8765, then 8766–8784. The console prints the URL it actually bound.

**Scan looks stuck**
The header should count up (`Found 1,240 files in …`). If it errors, the message stays on screen instead of spinning. A first scan of tens of thousands of files on a UNC share can take several minutes; later launches load `catalog.json` and skip that wait.

## About

A local, no-dependency audio pack browser for game audio on a disk or share.

## License

MIT — see [LICENSE](LICENSE).
