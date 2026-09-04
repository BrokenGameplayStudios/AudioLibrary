#!/usr/bin/env python3
"""Local audio library browser for a folder of game audio packs."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
CATALOG_PATH = ROOT / "catalog.json"
STATIC_HTML = ROOT / "index.html"
HOST = "127.0.0.1"
PORT = 8765

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".aiff", ".aif", ".m4a", ".aac"}
SKIP_DIRS = {"_zip", "_library", "__macosx", "_export"}
SKIP_FILES = {".ds_store", "ds_store", "thumbs.db", "desktop.ini", "packkind.json"}

KIND_MUSIC = "music"
KIND_VOICE = "voice"
KIND_SFX = "sfx"

TAG_RULES: list[tuple[tuple[str, ...], str]] = [
    (("8-bit", "8bit", "8 bit", "chiptune", "retro game", "retro"), "8-bit"),
    (("80s", "80's", "synthwave", "outrun"), "80s"),
    (("horror", "ghost", "creepy", "cursed", "cabin", "whisper", "demonic", "sinister", "stinger", "riser"), "horror"),
    (("rpg",), "rpg"),
    (("fantasy", "magical", "dragon", "lich", "goblin", "kobold", "bard"), "fantasy"),
    (("action", "fighter", "brutal", "aggressive", "destructive"), "action"),
    (("cinematic", "trailer", "teaser", "symphony"), "cinematic"),
    (("ambient", "relaxing", "close your eyes", "ambiance", "ambience"), "ambient"),
    (("cyberpunk", "high-tech", "high tech", "futuristic"), "cyberpunk"),
    (("electronic", "electronica", "techno", "hybrid electronic"), "electronic"),
    (("industrial",), "industrial"),
    (("metal", "heavy metal"), "metal"),
    (("rock", "riff"), "rock"),
    (("orchestral", "orchestra", "symphony"), "orchestral"),
    (("space", "aether", "star"), "space"),
    (("racing", "vector"), "racing"),
    (("survival",), "survival"),
    (("trap",), "trap"),
    (("acoustic", "guitar"), "acoustic"),
    (("casual", "funny", "positive"), "casual"),
    (("emotional", "melancholic"), "emotional"),
    (("percussion", "drum"), "percussion"),
    (("loop", "looped"), "loop"),
    (("voice", "voices", "whisper", "laughter", "follower", "fighter", "soldier", "swat", "character"), "voice"),
    (("monster",), "monster"),
    (("sfx", "sound effect", "soundeffect", "valentino"), "sfx"),
    (("reverse",), "reverse"),
    (("sci-fi", "scifi", "science fiction", "laser", "droid"), "sci-fi"),
    (("combat", "gun", "explosion", "bomb"), "combat"),
    (("animal", "dog", "farm", "jungle", "cat", "bird", "wolf", "horse", "lion"), "animals"),
    (("vehicle", "car", "truck", "train", "plane", "helicopter", "boat", "traffic", "engine"), "vehicles"),
    (("household", "phone", "clock", "office", "foley"), "foley"),
    (("audience", "applause"), "crowd"),
    (("stinger",), "stinger"),
    (("riser",), "riser"),
    (("footstep", "footsteps", "foostep", "foosteps"), "footsteps"),
    (("water", "splash", "splashes", "underwater"), "water"),
    (("flame", "campfire", "bonfire", "fireball"), "fire"),
    (("interface", "button", "menuui", "ui sound", "ui item"), "ui"),
    (("magic", "spell", "spells"), "magic"),
    (("whoosh", "whooshes", "sweep", "sweeps", "swish"), "whoosh"),
    (("door", "doors"), "door"),
    (("robot", "robots"), "robot"),
    (("zombie", "zombies", "undead"), "zombie"),
    (("punch", "punches", "melee", "smack", "scuffle", "sword", "swords"), "melee"),
    (("explosion", "explosions", "explode"), "explosion"),
    (("gore", "gory"), "gore"),
    (("glitch", "electric", "shock", "interference"), "electric"),
    (("pickup", "collect", "loot", "coin"), "pickup"),
    (("pistol", "rifle", "shotgun", "bullet", "gunshot"), "guns"),
    (("bow", "arrow", "arrows"), "weapons"),
    (("impact", "impacts"), "impact"),
    (("pirate", "pirates"), "pirate"),
    (("announcer", "announcement"), "announcer"),
    (("alien", "aliens"), "alien"),
    (("blacksmith", "anvil"), "blacksmith"),
    (("raining", "rainfall", "rainstorm"), "rain"),
    (("windy", "wind ambi", "wind sound"), "wind"),
]

CREATURES = (
    "basilisk", "bearranger", "behemoth", "chimera", "demon", "doll", "dragon",
    "droid", "ent", "frostdragon", "goblin", "golem", "kobold", "leviathan",
    "lich", "mimic", "oni", "phoenix", "skinwalker", "thunderdragon", "undead",
    "warlord", "wendigo", "wyvern", "zombies", "zombie",
)

PACK_TITLES = {
    "8-bitsoundtrack": "8-Bit Soundtrack",
    "80ssoundtrack": "80s Soundtrack",
    "abstractandstrangedrumloops": "Abstract and Strange Drum Loops",
    "abstracthybridelectronic": "Abstract Hybrid Electronic",
    "actionbeats": "Action Beats",
    "actioncinematicmusicpack": "Action Cinematic Music Pack",
    "aggressiveandbrutalsoundtrack": "Aggressive and Brutal Soundtrack",
    "aetherexpanse_rpgmusiccollection": "Aether Expanse RPG Music Collection",
    "ashensigil_rpgmusiccollection": "Ashen Sigil RPG Music Collection",
    "axionvector_racingmusiccollection": "Axion Vector Racing Music Collection",
    "brassfoundry_actionmusiccollection": "Brass Foundry Action Music Collection",
    "bushidoprotocol_actionmusiccollection": "Bushido Protocol Action Music Collection",
    "cinematicadventuresoundtrack": "Cinematic Adventure Soundtrack",
    "cinematicsynthsoundtrack": "Cinematic Synth Soundtrack",
    "cinematictrailerthemes": "Cinematic Trailer Themes",
    "closeyoureyesandflyrelaxingthemes": "Close Your Eyes and Fly Relaxing Themes",
    "creakingcradle_horrormusiccollection": "Creaking Cradle Horror Music Collection",
    "cursedcabin_horrormusiccollection": "Cursed Cabin Horror Music Collection",
    "cyberpunkambient": "Cyberpunk Ambient",
    "cyberpunkpulses": "Cyberpunk Pulses",
    "damneddrifter_rpgmusiccollection": "Damned Drifter RPG Music Collection",
    "darkmodernambient": "Dark Modern Ambient",
    "demonicwhispersvoicepack": "Demonic Whispers Voice Pack",
    "destructiveforceactioncinematicmusic": "Destructive Force Action Cinematic Music",
    "dramaticcinematicsymphony": "Dramatic Cinematic Symphony",
    "dramatictechnopulses": "Dramatic Techno Pulses",
    "electronica": "Electronica",
    "electronicactionmusic": "Electronic Action Music",
    "electronichigh-techsoundtrack": "Electronic High-Tech Soundtrack",
    "electronictechnosoundtrackpart1": "Electronic Techno Soundtrack Part 1",
    "electronictechnosoundtrackpart2": "Electronic Techno Soundtrack Part 2",
    "emberhearth_rpgmusiccollection": "Ember Hearth RPG Music Collection",
    "emberveil_rpgmusiccollection": "Ember Veil RPG Music Collection",
    "emotionalscene": "Emotional Scene",
    "epiccinematicsoundtrack": "Epic Cinematic Soundtrack",
    "fadingashes_survivalmusiccollection": "Fading Ashes Survival Music Collection",
    "funnycasualthemes": "Funny Casual Themes",
    "futuristicambient": "Futuristic Ambient",
    "ghostlywhispersvoicepack": "Ghostly Whispers Voice Pack",
    "harutogenzo_mfightervoicepack": "Haruto Genzo — M Fighter Voice Pack",
    "heavymetalmusic": "Heavy Metal Music",
    "horrorrisers_vol1": "Horror Risers Vol. 1",
    "horrorstingers_vol1": "Horror Stingers Vol. 1",
    "industrialtechno": "Industrial Techno",
    "infernalritual_rpgmusiccollection": "Infernal Ritual RPG Music Collection",
    "kylievance_ffightervoicepack": "Kylie Vance — F Fighter Voice Pack",
    "lockedinside_horrormusiccollection": "Locked Inside Horror Music Collection",
    "melancholicmusic": "Melancholic Music",
    "mobacharacter_soldier": "MOBA Character — Soldier",
    "oldschoolrockriffs": "Old School Rock Riffs",
    "orchestralsoundtrack": "Orchestral Soundtrack",
    "powerfulandbrutalrockmusicpack": "Powerful and Brutal Rock Music Pack",
    "powerfulheavymetal": "Powerful Heavy Metal",
    "retrogamemusicloops": "Retro Game Music Loops",
    "rhythmicdynamicpercussion": "Rhythmic Dynamic Percussion",
    "rockpower": "Rock Power",
    "rpgcharacter_finnkeepervoicepack": "RPG Character — Finn Keeper Voice Pack",
    "rpgfollower_marcher": "RPG Follower — M Archer",
    "rpgfollower_mbardvoicepack": "RPG Follower — M Bard Voice Pack",
    "rpgfollower_msummoner": "RPG Follower — M Summoner",
    "rpgsoundtrack": "RPG Soundtrack",
    "rpgsoundtrack2": "RPG Soundtrack 2",
    "rykercorvin_mfightervoicepack": "Ryker Corvin — M Fighter Voice Pack",
    "silverflagon_rpgmusiccollection": "Silver Flagon RPG Music Collection",
    "simpleacousticguitarthemes": "Simple Acoustic Guitar Themes",
    "simpleandpositivecasualmusicpack": "Simple and Positive Casual Music Pack",
    "sinisterintent_rpgmusiccollection": "Sinister Intent RPG Music Collection",
    "sinisterlaughtervoicepack": "Sinister Laughter Voice Pack",
    "soundof80s": "Sound of 80s",
    "spaceadventuresoundtrack": "Space Adventure Soundtrack",
    "spacejourneymusicpack": "Space Journey Music Pack",
    "spacethreatactioncinematicmusic": "Space Threat Action Cinematic Music",
    "sunadahikari_ffightervoicepack": "Sunada Hikari — F Fighter Voice Pack",
    "sunfirevale_rpgmusiccollection": "Sunfire Vale RPG Music Collection",
    "swatofficervoicepack": "SWAT Officer Voice Pack",
    "trapmusicpack": "Trap Music Pack",
    "twistedapostate_rpgmusiccollection": "Twisted Apostate RPG Music Collection",
    "valentinosoundeffectslibrary": "Valentino Sound Effects Library",
    "welcometothemagicalworldmajorversions": "Welcome to the Magical World (Major)",
    "welcometothemagicalworldminorversions": "Welcome to the Magical World (Minor)",
    "whisperswithin_horrormusiccollection": "Whispers Within Horror Music Collection",
}

CREATURE_TITLES = {
    "bearranger": "Bear Ranger",
    "frostdragon": "Frost Dragon",
    "thunderdragon": "Thunder Dragon",
    "demon2": "Demon 2",
    "demon4": "Demon 4",
    "oni2": "Oni 2",
    "zombies": "Zombies",
}

PACK_REPLACEMENTS = [
    ("monstervoices_", "Monster Voices — "),
    ("rpgfollower_", "RPG Follower — "),
    ("rpgcharacter_", "RPG Character — "),
    ("mobacharacter_", "MOBA Character — "),
    ("ffightervoicepack", "F Fighter Voice Pack"),
    ("mfightervoicepack", "M Fighter Voice Pack"),
    ("mbardvoicepack", "M Bard Voice Pack"),
    ("finnkeepervoicepack", "Finn Keeper Voice Pack"),
    ("rpgmusiccollection", "RPG Music Collection"),
    ("actionmusiccollection", "Action Music Collection"),
    ("horrormusiccollection", "Horror Music Collection"),
    ("racingmusiccollection", "Racing Music Collection"),
    ("survivalmusiccollection", "Survival Music Collection"),
    ("voicepack", "Voice Pack"),
    ("musicpack", "Music Pack"),
    ("soundtrack", "Soundtrack"),
    ("soundeffectslibrary", "Sound Effects Library"),
    ("drumloops", "Drum Loops"),
    ("marcher", "M Archer"),
    ("msummoner", "M Summoner"),
]

SPLIT_WORDS = tuple(
    sorted(
        {
            "creaking", "cradle", "horror", "risers", "stingers", "locked", "inside",
            "cursed", "cabin", "whispers", "within", "ghostly", "demonic", "sinister",
            "laughter", "intent", "infernal", "ritual", "ember", "veil", "hearth",
            "ashen", "sigil", "fading", "ashes", "twisted", "apostate", "damned",
            "drifter", "silver", "flagon", "sunfire", "vale", "aether", "expanse",
            "axion", "vector", "bushido", "protocol", "brass", "foundry", "kylie",
            "vance", "ryker", "corvin", "sunada", "hikari", "haruto", "genzo",
            "swat", "officer", "soldier", "abstract", "strange", "hybrid",
            "electronic", "electronica", "action", "beats", "cinematic", "adventure",
            "synth", "trailer", "themes", "close", "your", "eyes", "fly", "relaxing",
            "cyberpunk", "ambient", "pulses", "dark", "modern", "destructive",
            "force", "dramatic", "symphony", "techno", "high-tech", "emotional",
            "scene", "epic", "funny", "casual", "futuristic", "heavy", "metal",
            "industrial", "melancholic", "oldschool", "rock", "riffs", "orchestral",
            "powerful", "brutal", "retro", "game", "rhythmic", "dynamic",
            "percussion", "simple", "acoustic", "guitar", "positive", "space",
            "journey", "threat", "trap", "welcome", "magical", "world", "major",
            "minor", "versions", "valentino", "aggressive", "and", "8-bit", "80s",
            "vol",
        },
        key=len,
        reverse=True,
    )
)

_audio_root: Path | None = None
_catalog: dict = {"generated": 0, "items": [], "count": 0, "root": ""}
_by_id: dict[int, dict] = {}
_packkind: dict[str, dict] = {}
_catalog_lock = threading.Lock()
_scan_ctl = threading.Lock()
_state_lock = threading.Lock()
_scan_state = {
    "running": False,
    "message": "Idle",
    "found": 0,
    "root": "",
    "error": None,
}


def _split_concat(token: str) -> list[str]:
    raw = token
    lower = token.lower()
    out: list[str] = []
    i = 0
    while i < len(lower):
        matched = None
        for w in SPLIT_WORDS:
            if lower.startswith(w, i) and (i + len(w) == len(lower) or not lower[i + len(w)].isalpha() or len(w) >= 3):
                matched = w
                break
        if matched:
            out.append(matched)
            i += len(matched)
        else:
            j = i + 1
            while j < len(lower) and not any(lower.startswith(w, j) for w in SPLIT_WORDS):
                j += 1
            out.append(raw[i:j])
            i = j
    return out or [token]


def load_packkind(audio_root: Path) -> None:
    global _packkind
    _packkind = {}
    path = audio_root / "packkind.json"
    try:
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    packs = data.get("packs") if isinstance(data, dict) else None
    if isinstance(packs, dict):
        _packkind = packs


def pack_title(folder: str) -> str:
    meta = _packkind.get(folder) or {}
    if isinstance(meta, dict) and meta.get("title"):
        return str(meta["title"])
    if folder in PACK_TITLES:
        return PACK_TITLES[folder]
    lower = folder.lower()
    if lower.startswith("monstervoices_"):
        creature = folder.split("_", 1)[1]
        nice = CREATURE_TITLES.get(creature.lower(), creature[:1].upper() + creature[1:])
        return f"Monster Voices — {nice}"
    s = folder
    lower = s.lower()
    for old, new in PACK_REPLACEMENTS:
        if old in lower:
            idx = lower.find(old)
            s = s[:idx] + new + s[idx + len(old) :]
            lower = s.lower()
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    acronyms = {"rpg", "sfx", "moba", "swat"}
    words: list[str] = []
    for w in s.split(" "):
        if not w:
            continue
        if w == "—" or any(ch.isupper() for ch in w[1:]):
            words.append(w)
            continue
        pieces = _split_concat(w) if w.islower() or w.replace("-", "").isalnum() else [w]
        for piece in pieces:
            if piece == "—":
                words.append(piece)
            elif piece.lower() in acronyms:
                words.append(piece.upper())
            elif piece.lower() in {"m", "f"} and words:
                words.append(piece.upper())
            elif piece.isdigit():
                words.append(piece)
            else:
                words.append(piece[:1].upper() + piece[1:])
    return " ".join(words) or folder


def detect_kind(pack: str, rel: str, name: str) -> str:
    meta = _packkind.get(pack) or {}
    if isinstance(meta, dict):
        k = str(meta.get("kind", "")).lower()
        if k in (KIND_MUSIC, KIND_VOICE, KIND_SFX):
            return k
    p = pack.lower()
    if "valentino" in p or "soundeffect" in p:
        return KIND_SFX
    if "riser" in p or "stinger" in p:
        return KIND_SFX
    if any(
        k in p
        for k in (
            "voice",
            "whisper",
            "laughter",
            "follower",
            "fighter",
            "soldier",
            "swat",
            "monster",
            "character",
        )
    ):
        return KIND_VOICE
    return KIND_MUSIC


def detect_tags(pack: str, rel: str, name: str, kind: str) -> list[str]:
    blob = f"{pack} {rel} {name}".lower().replace("_", " ").replace("-", " ")
    tags: list[str] = [kind]
    for keys, tag in TAG_RULES:
        if tag in tags:
            continue
        if any(k in blob for k in keys):
            tags.append(tag)
    pack_l = pack.lower()
    if pack_l.startswith("monstervoices_"):
        creature = pack_l.split("_", 1)[1]
        creature = re.sub(r"\d+$", "", creature)
        tags.append(creature)
        if "monster" not in tags:
            tags.append("monster")
    meta = _packkind.get(pack) or {}
    extra = meta.get("tags") if isinstance(meta, dict) else None
    if isinstance(extra, list):
        for t in extra:
            if t:
                tags.append(str(t))
    # keep order, cap noise
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def should_skip_dir(name: str) -> bool:
    return name.lower() in SKIP_DIRS or name.startswith(".")


def is_audio_filename(filename: str) -> bool:
    lower = filename.lower()
    if lower in SKIP_FILES or filename.startswith("._"):
        return False
    return Path(filename).suffix.lower() in AUDIO_EXT


def _path_ok(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists() and path.is_dir()
    except OSError:
        return False


def snapshot_catalog() -> dict:
    with _catalog_lock:
        return _catalog


def snapshot_scan() -> dict:
    with _state_lock:
        return dict(_scan_state)


def set_scan(**kwargs) -> None:
    with _state_lock:
        _scan_state.update(kwargs)


def set_audio_root(path: Path | None) -> None:
    global _audio_root
    _audio_root = path


def set_catalog(data: dict) -> None:
    global _catalog, _by_id
    items = data.get("items") or []
    data.setdefault("count", len(items))
    with _catalog_lock:
        _catalog = data
        _by_id = {int(it["id"]): it for it in items}


def lookup_item(item_id: int) -> dict | None:
    with _catalog_lock:
        return _by_id.get(item_id)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(root: Path) -> None:
    CONFIG_PATH.write_text(json.dumps({"root": str(root)}, indent=2) + "\n", encoding="utf-8")


def load_catalog_file() -> dict | None:
    if not CATALOG_PATH.exists():
        return None
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    return data


def resolve_root(cached: dict | None) -> Path | None:
    candidates: list[Path] = []
    cfg = load_config()
    if cfg.get("root"):
        candidates.append(Path(cfg["root"]))
    if cached and cached.get("root"):
        candidates.append(Path(cached["root"]))
    candidates.append(ROOT.parent)
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if _path_ok(cand):
            return cand
    return None


def iter_audio_files(audio_root: Path):
    try:
        entries = sorted(audio_root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        raise

    for entry in entries:
        try:
            is_file = entry.is_file()
            is_dir = entry.is_dir()
        except OSError:
            continue
        if is_file:
            if is_audio_filename(entry.name):
                yield audio_root.name, entry.name, entry, True
            continue
        if not is_dir or should_skip_dir(entry.name):
            continue
        pack = entry.name
        for dirpath, dirnames, filenames in os.walk(entry):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            rel_dir = Path(dirpath)
            for filename in filenames:
                if not is_audio_filename(filename):
                    continue
                path = rel_dir / filename
                rel = path.relative_to(entry).as_posix()
                yield pack, rel, path, False


def build_catalog(audio_root: Path) -> dict:
    load_packkind(audio_root)
    items = []
    last_pack = ""
    for i, (pack, rel, path, in_root) in enumerate(iter_audio_files(audio_root), start=1):
        name = path.stem
        if in_root:
            parent = ""
            category = pack_title(pack)
        else:
            parent = path.parent.relative_to(audio_root / pack).as_posix()
            if parent == ".":
                parent = ""
            category = path.parent.name if path.parent != (audio_root / pack) else pack_title(pack)
        kind = detect_kind(pack, rel, name)
        tags = detect_tags(pack, rel, name, kind)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        rec = {
            "id": i,
            "name": name,
            "file": path.name,
            "pack": pack,
            "packTitle": pack_title(pack),
            "rel": rel,
            "folder": parent,
            "category": category,
            "ext": path.suffix.lower().lstrip("."),
            "kind": kind,
            "tags": tags,
            "bytes": size,
        }
        if in_root:
            rec["inRoot"] = True
        items.append(rec)
        if i == 1 or i % 25 == 0 or pack != last_pack:
            set_scan(found=i, message=f"Found {i:,} files in {pack_title(pack)}…")
            last_pack = pack
    return {
        "generated": int(time.time()),
        "root": str(audio_root),
        "count": len(items),
        "items": items,
    }


def start_scan(clear_catalog: bool = False) -> tuple[bool, str]:
    with _scan_ctl:
        if snapshot_scan()["running"]:
            return False, "Scan already running"
        if _audio_root is None:
            return False, "No library folder selected"
        if clear_catalog:
            set_catalog({"generated": 0, "items": [], "count": 0, "root": str(_audio_root)})
        root = _audio_root
        set_scan(
            running=True,
            error=None,
            found=0,
            root=str(root),
            message="Scanning audio files…",
        )
        threading.Thread(target=_scan_worker, args=(root,), daemon=True).start()
        return True, "Scan started"


def _scan_worker(root: Path) -> None:
    try:
        data = build_catalog(root)
        set_catalog(data)
        set_scan(found=data["count"], message=f"Saving catalog ({data['count']:,} files)…")
        try:
            CATALOG_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError as e:
            set_scan(
                running=False,
                error=f"Indexed {data['count']:,} files but failed to save catalog: {e}",
                message=f"Indexed {data['count']:,} files (catalog not saved)",
            )
            return
        set_scan(
            running=False,
            found=data["count"],
            error=None,
            message=f"Indexed {data['count']:,} files",
        )
    except Exception as e:
        set_scan(running=False, error=str(e), message=f"Scan failed: {e}")


def abs_path_for(item: dict) -> Path:
    if _audio_root is None:
        raise FileNotFoundError("no library folder selected")
    rel = Path(item["rel"])
    if item.get("inRoot"):
        return _audio_root / rel
    return _audio_root / item["pack"] / rel


def pick_directory(initial: Path | None) -> Path | None:
    initialdir = str(initial) if _path_ok(initial) else str(ROOT.parent)
    try:
        return _pick_directory_tk(initialdir)
    except Exception:
        return _pick_directory_powershell(initialdir)


def _pick_directory_tk(initialdir: str) -> Path | None:
    result: dict[str, str | None] = {"path": None}
    err: dict[str, BaseException | None] = {"e": None}

    def _run() -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            win = tk.Tk()
            win.withdraw()
            try:
                win.attributes("-topmost", True)
            except tk.TclError:
                pass
            try:
                chosen = filedialog.askdirectory(
                    title="Select audio library folder",
                    initialdir=initialdir,
                    mustexist=True,
                )
            finally:
                win.destroy()
            result["path"] = chosen or None
        except BaseException as e:
            err["e"] = e

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=600)
    if err["e"]:
        raise err["e"]
    path = result["path"]
    return Path(path) if path else None


def _pick_directory_powershell(initialdir: str) -> Path | None:
    escaped = initialdir.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = 'Select audio library folder'; "
        "$d.ShowNewFolderButton = $true; "
        f"$d.SelectedPath = '{escaped}'; "
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
        "  Write-Output $d.SelectedPath "
        "}"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        timeout=600,
    )
    path = (completed.stdout or "").strip()
    return Path(path) if path else None


def content_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def open_in_explorer(path: Path) -> None:
    target = str(path)
    subprocess.Popen(["explorer", f"/select,{target}"])


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioLibrary/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/index.html"):
            html = STATIC_HTML.read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if path == "/api/catalog":
            self._json(200, snapshot_catalog())
            return
        if path == "/api/status":
            st = snapshot_scan()
            cat = snapshot_catalog()
            self._json(
                200,
                {
                    "running": st["running"],
                    "message": st["message"],
                    "found": st["found"],
                    "error": st["error"],
                    "root": str(_audio_root) if _audio_root else st.get("root") or "",
                    "count": cat.get("count", 0),
                },
            )
            return
        if path.startswith("/media/"):
            self._serve_media(path)
            return
        self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        if path == "/api/open":
            item_id = payload.get("id")
            try:
                item = lookup_item(int(item_id)) if item_id is not None else None
            except (TypeError, ValueError):
                item = None
            if not item:
                self._json(404, {"ok": False, "error": "unknown id"})
                return
            p = abs_path_for(item)
            if not p.exists():
                self._json(404, {"ok": False, "error": "file missing"})
                return
            open_in_explorer(p)
            self._json(200, {"ok": True})
            return
        if path == "/api/rescan":
            ok, message = start_scan(clear_catalog=False)
            if not ok:
                code = 409 if "already" in message.lower() else 400
                self._json(code, {"ok": False, "error": message})
                return
            self._json(200, {"ok": True, "message": message})
            return
        if path == "/api/browse-root":
            if snapshot_scan()["running"]:
                self._json(409, {"ok": False, "error": "Scan already running"})
                return
            try:
                chosen = pick_directory(_audio_root)
            except Exception as e:
                self._json(500, {"ok": False, "error": f"Folder dialog failed: {e}"})
                return
            if chosen is None:
                self._json(200, {"ok": False, "cancelled": True})
                return
            set_audio_root(chosen)
            try:
                save_config(chosen)
            except OSError as e:
                self._json(500, {"ok": False, "error": f"Could not save folder: {e}"})
                return
            ok, message = start_scan(clear_catalog=True)
            self._json(
                200,
                {
                    "ok": True,
                    "root": str(chosen),
                    "scanning": ok,
                    "message": message,
                },
            )
            return
        self._json(404, {"ok": False, "error": "not found"})

    def _serve_media(self, path: str) -> None:
        try:
            item_id = int(path.rsplit("/", 1)[-1])
        except ValueError:
            self._send(400, b"bad id", "text/plain")
            return
        item = lookup_item(item_id)
        if not item:
            self._send(404, b"missing", "text/plain")
            return
        file_path = abs_path_for(item)
        if not file_path.exists() or not file_path.is_file():
            self._send(404, b"file missing", "text/plain")
            return
        file_size = file_path.stat().st_size
        ctype = content_type_for(file_path)
        range_header = self.headers.get("Range")
        start, end = 0, file_size - 1
        status = 200
        if range_header and range_header.startswith("bytes="):
            spec = range_header.split("=", 1)[1]
            a, _, b = spec.partition("-")
            try:
                if a:
                    start = int(a)
                if b:
                    end = int(b)
            except ValueError:
                start, end = 0, file_size - 1
            end = min(end, file_size - 1)
            if start > end or start >= file_size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    return
                remaining -= len(chunk)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            try:
                item_id = int(parsed.path.rsplit("/", 1)[-1])
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return
            item = lookup_item(item_id)
            if not item:
                self.send_response(404)
                self.end_headers()
                return
            p = abs_path_for(item)
            if not p.exists():
                self.send_response(404)
                self.end_headers()
                return
            size = p.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", content_type_for(p))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            return
        self.do_GET()


def main() -> int:
    cached = load_catalog_file()
    if cached:
        set_catalog(cached)
        print(f"Loaded cached catalog: {cached.get('count', 0)} files", flush=True)
    set_audio_root(resolve_root(cached))
    if _audio_root:
        print(f"Library root: {_audio_root}", flush=True)
        set_scan(root=str(_audio_root), message="Idle")
    else:
        print("No library folder selected yet.", flush=True)
        set_scan(message="No folder selected")
    httpd = None
    last_err: OSError | None = None
    for port in range(PORT, PORT + 20):
        try:
            httpd = ThreadingHTTPServer((HOST, port), Handler)
            break
        except OSError as e:
            last_err = e
    if httpd is None:
        raise last_err if last_err else OSError(f"Could not bind {HOST}:{PORT}")
    url = f"http://{HOST}:{httpd.server_address[1]}/"
    print(f"Audio library: {url}", flush=True)
    if _audio_root and not snapshot_catalog().get("items"):
        start_scan(clear_catalog=False)
        print("Scanning in the background…", flush=True)
    try:
        webbrowser.open(url)
    except OSError:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
