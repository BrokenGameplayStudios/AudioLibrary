#!/usr/bin/env python3
"""Local audio library browser for a folder of game audio packs."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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

FORBIDDEN_PARENTS = {"_library", "_zip", "_export"}
PACKKIND_NAME = "packkind.json"
BACKUP_NAME = "packkind.json.bak"
SNAPSHOT_PATH = ROOT / "packkind.snapshot.json"
VALID_KINDS = {KIND_MUSIC, KIND_VOICE, KIND_SFX}
SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+$")
TAG_RE = re.compile(r"^[a-z0-9_][a-z0-9+\-._]{0,31}$")
MAX_EXTRA_TAGS = 24
MAX_VOCABULARY = 256
MAX_TITLE_LEN = 80
MAX_BODY = 64 * 1024
KIND_LABELS = {KIND_MUSIC: "Music", KIND_VOICE: "Voice", KIND_SFX: "SFX"}
_OMIT = object()

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
_packkind_write_lock = threading.Lock()
_write_running = False
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


class PackkindReadError(Exception):
    """Unparseable sidecar or packs is not an object. Do not write."""


def load_packkind(audio_root: Path) -> None:
    """Scan/startup only. Missing or garbage sidecar → empty extras (fail-open)."""
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


def read_packkind_document(path: Path) -> dict:
    """Save/Restore/GET only. Missing file → empty doc. Garbage → raise."""
    if not path.exists():
        return {"version": 1, "packs": {}}
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise PackkindReadError(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("packs"), dict):
        raise PackkindReadError("packs is not an object")
    return data


def optional_packkind_document(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return read_packkind_document(path)
    except PackkindReadError:
        return None


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, obj, *, indent: int | None) -> None:
    if indent is None:
        text = json.dumps(obj, ensure_ascii=False)
    else:
        text = json.dumps(obj, ensure_ascii=False, indent=indent) + "\n"
    write_text_atomic(path, text)


def persist_catalog_compact() -> None:
    with _catalog_lock:
        text = json.dumps(_catalog, ensure_ascii=False)
    write_text_atomic(CATALOG_PATH, text)


def begin_packkind_write() -> str | None:
    """Return an error message, or None if this thread now owns the write."""
    global _write_running
    with _scan_ctl:
        if snapshot_scan()["running"]:
            return "Scan already running"
        if _write_running:
            return "Saving tags, wait then Rescan"
        _write_running = True
        return None


def end_packkind_write() -> None:
    global _write_running
    with _scan_ctl:
        _write_running = False


def forbidden_packkind_parent(audio_root: Path) -> bool:
    return audio_root.name.lower() in FORBIDDEN_PARENTS


def packkind_dest_paths() -> tuple[Path, Path, Path]:
    assert _audio_root is not None
    dest = _audio_root / PACKKIND_NAME
    bak = _audio_root / BACKUP_NAME
    return dest, bak, SNAPSHOT_PATH


def slug_ok(slug: str) -> bool:
    return bool(slug) and ".." not in slug and "/" not in slug and "\\" not in slug and bool(SLUG_RE.fullmatch(slug))


def slug_is_known(slug: str, dest_doc: dict | None = None) -> bool:
    if dest_doc and slug in (dest_doc.get("packs") or {}):
        return True
    if slug in _packkind:
        return True
    with _catalog_lock:
        for it in _catalog.get("items") or []:
            if it.get("pack") == slug:
                return True
    if _audio_root is not None:
        try:
            folder = _audio_root / slug
            if folder.is_dir() and not should_skip_dir(slug):
                return True
        except OSError:
            pass
    return False


def parse_tag_name(raw) -> tuple[str | None, str | None]:
    s = str(raw).strip().lower()
    if not s:
        return None, "Type a tag name."
    if any(ch.isspace() for ch in s):
        return None, "Use a hyphen, like sci-fi"
    if s in VALID_KINDS:
        return None, "Use the Type dropdown for music, voice, or sfx."
    if not TAG_RE.fullmatch(s):
        return None, "That tag name isn’t allowed."
    return s, None


def parse_extra_tags(raw) -> tuple[list[str] | None, str | None]:
    if not isinstance(raw, list):
        return None, "tags must be a list"
    extras: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not str(t).strip():
            continue
        s, err = parse_tag_name(t)
        if err:
            return None, err
        assert s is not None
        if s in seen:
            continue
        seen.add(s)
        extras.append(s)
    if len(extras) > MAX_EXTRA_TAGS:
        return None, "That’s enough tags for this pack."
    return extras, None


def parse_stored_vocabulary(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        s, err = parse_tag_name(t)
        if err or s is None or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def extras_in_packs(packs) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(packs, dict):
        return out
    for meta in packs.values():
        if not isinstance(meta, dict):
            continue
        for t in meta.get("tags") or []:
            s = str(t).strip().lower()
            if not s or s in VALID_KINDS or s in seen:
                continue
            if not TAG_RE.fullmatch(s):
                continue
            seen.add(s)
            out.append(s)
    return out


def vocabulary_from_document(doc: dict) -> list[str]:
    stored = parse_stored_vocabulary(doc.get("vocabulary") if isinstance(doc, dict) else None)
    seen = set(stored)
    out = list(stored)
    packs = doc.get("packs") if isinstance(doc, dict) else None
    for t in extras_in_packs(packs or {}):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def union_vocabulary(vocab: list[str], extras: list[str]) -> list[str]:
    seen = set(vocab)
    out = list(vocab)
    for t in extras:
        if t and t not in VALID_KINDS and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def strip_tag_from_pack_obj(obj: dict, tag: str) -> bool:
    """Remove tag from a pack object. Returns True if tags changed."""
    kind = str(obj.get("kind") or "").lower()
    if kind not in VALID_KINDS:
        kind = KIND_SFX
        obj["kind"] = kind
    existing = obj.get("tags")
    if not isinstance(existing, list):
        obj["tags"] = [kind]
        return False
    extras = [str(t) for t in existing if str(t) not in VALID_KINDS and str(t) != tag]
    new_tags = tags_for_sidecar(kind, extras)
    if new_tags == [str(t) for t in existing]:
        return False
    obj["tags"] = new_tags
    return True


def tags_for_sidecar(kind: str, extras: list[str]) -> list[str]:
    out = [kind]
    seen = {kind}
    for t in extras:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def display_title(slug: str, meta: dict | None = None) -> str:
    if isinstance(meta, dict) and meta.get("title"):
        return str(meta["title"])
    return pack_title(slug)


def restore_source(dest, snapshot, bak, slug):
    d = (dest.get("packs") or {}).get(slug) if dest else None
    s = (snapshot.get("packs") or {}).get(slug) if snapshot else None
    b = (bak.get("packs") or {}).get(slug) if bak else None
    if s is not None and s != d:
        return snapshot, "snapshot"
    if b is not None and b != d:
        return bak, "bak"
    return None, None


def pack_file_count(slug: str) -> int:
    with _catalog_lock:
        return sum(1 for it in (_catalog.get("items") or []) if it.get("pack") == slug)


def catalog_extra_tags(slug: str) -> set[str]:
    extras: set[str] = set()
    with _catalog_lock:
        for it in _catalog.get("items") or []:
            if it.get("pack") != slug:
                continue
            for t in it.get("tags") or []:
                if t not in VALID_KINDS:
                    extras.add(str(t))
    return extras


def sidecar_extra_tags(tags) -> set[str]:
    return {str(t) for t in (tags or []) if str(t) not in VALID_KINDS}


def catalog_ahead_of_sidecar(slug: str, sidecar_tags, restore_would_change: bool) -> bool:
    if not restore_would_change:
        return False
    side = sidecar_extra_tags(sidecar_tags)
    cat = catalog_extra_tags(slug)
    return side < cat


def patch_catalog_for_pack(slug: str) -> list[dict]:
    """Re-run detect_* on items of this pack. Mutates catalog in place.
    Returns compact [{id, kind, packTitle, tags}, ...] for the client."""
    out: list[dict] = []
    with _catalog_lock:
        items = _catalog.get("items") or []
        for it in items:
            if it.get("pack") != slug:
                continue
            rel = it.get("rel") or ""
            name = it.get("name") or ""
            kind = detect_kind(slug, rel, name)
            it["kind"] = kind
            it["packTitle"] = pack_title(slug)
            it["tags"] = detect_tags(slug, rel, name, kind)
            out.append({
                "id": it["id"],
                "kind": it["kind"],
                "packTitle": it["packTitle"],
                "tags": it["tags"],
            })
    return out


def ensure_packkind_snapshot() -> None:
    """First launch only: copy dest → snapshot if snapshot is missing. Never refresh later."""
    if SNAPSHOT_PATH.exists() or _audio_root is None:
        return
    dest = _audio_root / PACKKIND_NAME
    if not dest.exists():
        return
    try:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, SNAPSHOT_PATH)
    except OSError:
        pass


def _io_save_error(exc: BaseException) -> str:
    if isinstance(exc, OSError):
        return "Could not save — is the share still connected?"
    return str(exc)


def commit_packkind_document(
    merged: dict,
    message: str,
    dest: Path,
    bak: Path,
    snap: Path,
    slugs: list[str],
    *,
    return_items: bool = True,
) -> tuple[int, dict]:
    """Write dest + bak + catalog + snapshot. Caller holds the write gate."""
    global _packkind
    sidecar_saved = False
    if not isinstance(merged.get("version"), int):
        merged["version"] = 1
    merged.setdefault("packs", {})
    merged["vocabulary"] = vocabulary_from_document(merged)
    try:
        if dest.exists():
            shutil.copy2(dest, bak)
        write_json_atomic(dest, merged, indent=2)
        sidecar_saved = True
        _packkind = merged["packs"]
        patched_items: list[dict] = []
        patched_n = 0
        for slug in slugs:
            chunk = patch_catalog_for_pack(slug)
            patched_n += len(chunk)
            if return_items:
                patched_items.extend(chunk)
        persist_catalog_compact()
        write_json_atomic(snap, merged, indent=2)
    except OSError as exc:
        err: dict = {"ok": False, "error": _io_save_error(exc)}
        if sidecar_saved:
            err["sidecarSaved"] = True
        return 500, err
    except Exception as exc:
        err = {"ok": False, "error": _io_save_error(exc)}
        if sidecar_saved:
            err["sidecarSaved"] = True
        return 500, err
    body: dict = {
        "ok": True,
        "vocabulary": list(merged.get("vocabulary") or []),
        "patched": patched_n,
        "message": message,
    }
    if return_items:
        body["items"] = patched_items
    else:
        body["reloadCatalog"] = True
    print(f"packkind: saved {len(slugs)} pack(s) ({patched_n} items) -> {dest}", flush=True)
    return 200, body


def commit_packkind(
    slug: str,
    new_obj: dict,
    message: str,
    dest: Path,
    bak: Path,
    snap: Path,
) -> tuple[int, dict]:
    """Write dest + bak + catalog + snapshot. Caller holds the write gate.
    Paths are captured at write start so a mid-Save folder switch cannot retarget dest."""
    try:
        dest_doc = read_packkind_document(dest)
    except PackkindReadError:
        return 422, {"ok": False, "error": "Could not read tags file."}
    packs = dest_doc.setdefault("packs", {})
    packs[slug] = new_obj
    extras = [str(t) for t in (new_obj.get("tags") or []) if str(t) not in VALID_KINDS]
    dest_doc["vocabulary"] = union_vocabulary(vocabulary_from_document(dest_doc), extras)
    code, body = commit_packkind_document(dest_doc, message, dest, bak, snap, [slug])
    if code != 200:
        return code, body
    src_doc, _src = restore_source(
        dest_doc,
        optional_packkind_document(snap),
        optional_packkind_document(bak),
        slug,
    )
    would = src_doc is not None
    title = display_title(slug, new_obj)
    body.update({
        "pack": slug,
        "kind": new_obj.get("kind"),
        "title": title,
        "tags": list(new_obj.get("tags") or []),
        "hasBackup": would,
        "restoreWouldChange": would,
    })
    return code, body


def field_patch_pack(existing: dict | None, slug: str, kind=_OMIT, title=_OMIT, tags=_OMIT) -> tuple[dict | None, str | None]:
    obj = dict(existing) if isinstance(existing, dict) else {}
    if kind is not _OMIT:
        k = str(kind).lower()
        if k not in VALID_KINDS:
            return None, "bad kind"
        obj["kind"] = k
    else:
        k = str(obj.get("kind") or "").lower()
        if k not in VALID_KINDS:
            obj["kind"] = detect_kind(slug, "", "")
        else:
            obj["kind"] = k
    if title is not _OMIT:
        t = str(title).strip()
        if len(t) > MAX_TITLE_LEN:
            return None, "title too long"
        if t:
            obj["title"] = t
        else:
            obj.pop("title", None)
    if tags is not _OMIT:
        extras, err = parse_extra_tags(tags)
        if err:
            return None, err
        obj["tags"] = tags_for_sidecar(obj["kind"], extras)
    elif kind is not _OMIT:
        existing_tags = obj.get("tags")
        if not isinstance(existing_tags, list):
            obj["tags"] = [obj["kind"]]
        else:
            extras = [str(t) for t in existing_tags if str(t) not in VALID_KINDS]
            obj["tags"] = tags_for_sidecar(obj["kind"], extras)
    elif not isinstance(obj.get("tags"), list):
        obj["tags"] = [obj["kind"]]
    return obj, None


def get_packkind_response(slug: str) -> tuple[int, dict]:
    if _audio_root is None:
        return 400, {"ok": False, "error": "No library folder selected"}
    if not slug:
        return 400, {"ok": False, "error": "missing pack"}
    dest, bak, snap = packkind_dest_paths()
    try:
        dest_doc = read_packkind_document(dest)
    except PackkindReadError:
        return 422, {"ok": False, "error": "Could not read tags file."}
    if not slug_ok(slug) or not slug_is_known(slug, dest_doc):
        return 404, {"ok": False, "error": "Unknown pack."}
    meta = (dest_doc.get("packs") or {}).get(slug)
    if isinstance(meta, dict):
        source = "sidecar"
        kind = str(meta.get("kind") or "").lower()
        if kind not in VALID_KINDS:
            kind = detect_kind(slug, "", "")
        title = display_title(slug, meta)
        tags = meta.get("tags") if isinstance(meta.get("tags"), list) else [kind]
        tags = [str(t) for t in tags]
    else:
        source = "heuristic"
        kind = detect_kind(slug, "", "")
        title = pack_title(slug)
        tags = [kind]
        meta = {"kind": kind, "title": title, "tags": tags}
    snap_doc = optional_packkind_document(snap)
    bak_doc = optional_packkind_document(bak)
    src_doc, _src = restore_source(dest_doc, snap_doc, bak_doc, slug)
    would = src_doc is not None
    return 200, {
        "ok": True,
        "pack": slug,
        "kind": kind,
        "title": title,
        "tags": tags,
        "vocabulary": vocabulary_from_document(dest_doc),
        "fileCount": pack_file_count(slug),
        "hasBackup": would,
        "restoreWouldChange": would,
        "catalogAheadOfSidecar": catalog_ahead_of_sidecar(slug, tags, would),
        "source": source,
    }


def get_vocabulary_response() -> tuple[int, dict]:
    if _audio_root is None:
        return 400, {"ok": False, "error": "No library folder selected"}
    dest, _bak, _snap = packkind_dest_paths()
    try:
        dest_doc = read_packkind_document(dest)
    except PackkindReadError:
        return 422, {"ok": False, "error": "Could not read tags file."}
    return 200, {"ok": True, "vocabulary": vocabulary_from_document(dest_doc)}


def save_vocabulary_response(payload: dict) -> tuple[int, dict]:
    if _audio_root is None:
        return 400, {"ok": False, "error": "No library folder selected"}
    if forbidden_packkind_parent(_audio_root):
        return 400, {"ok": False, "error": "Cannot save tags in this folder."}
    add_raw = payload["add"] if "add" in payload else _OMIT
    remove_raw = payload["remove"] if "remove" in payload else _OMIT
    if (add_raw is _OMIT) == (remove_raw is _OMIT):
        return 400, {"ok": False, "error": "Send add or remove."}
    gate = begin_packkind_write()
    if gate:
        return 409, {"ok": False, "error": gate}
    try:
        with _packkind_write_lock:
            dest, bak, snap = packkind_dest_paths()
            try:
                dest_doc = read_packkind_document(dest)
            except PackkindReadError:
                return 422, {"ok": False, "error": "Could not read tags file."}
            vocab = vocabulary_from_document(dest_doc)
            if add_raw is not _OMIT:
                tag, err = parse_tag_name(add_raw)
                if err:
                    return 400, {"ok": False, "error": err}
                assert tag is not None
                if tag in vocab:
                    return 200, {
                        "ok": True,
                        "vocabulary": vocab,
                        "patched": 0,
                        "message": f"“{tag}” is already in the library.",
                    }
                if len(vocab) >= MAX_VOCABULARY:
                    return 400, {"ok": False, "error": "That’s enough tags for the library."}
                vocab.append(tag)
                dest_doc["vocabulary"] = vocab
                return commit_packkind_document(
                    dest_doc,
                    f"Added “{tag}”. Select a pack, then Modify tags to put it on that pack.",
                    dest,
                    bak,
                    snap,
                    [],
                )
            tag, err = parse_tag_name(remove_raw)
            if err:
                return 400, {"ok": False, "error": err}
            assert tag is not None
            packs = dest_doc.setdefault("packs", {})
            stripped: list[str] = []
            for slug, obj in list(packs.items()):
                if not isinstance(obj, dict):
                    continue
                if strip_tag_from_pack_obj(obj, tag):
                    stripped.append(slug)
            dest_doc["vocabulary"] = [t for t in vocab if t != tag]
            stayed = False
            code, body = commit_packkind_document(
                dest_doc,
                f"Removed “{tag}” from the library.",
                dest,
                bak,
                snap,
                stripped,
                return_items=len(stripped) <= 1,
            )
            if code != 200:
                return code, body
            with _catalog_lock:
                for it in _catalog.get("items") or []:
                    if tag in (it.get("tags") or []):
                        stayed = True
                        break
            body["strippedPacks"] = stripped
            body["stayedOnFiles"] = stayed
            if stayed:
                body["message"] = (
                    f"Removed “{tag}” from the library. "
                    "Some files still show it because it is in the name."
                )
            elif not stripped and tag not in vocab:
                body["message"] = f"“{tag}” was not in the library."
            return code, body
    finally:
        end_packkind_write()


def save_packkind_response(payload: dict) -> tuple[int, dict]:
    if _audio_root is None:
        return 400, {"ok": False, "error": "No library folder selected"}
    if forbidden_packkind_parent(_audio_root):
        return 400, {"ok": False, "error": "Cannot save tags in this folder."}
    slug = payload.get("pack")
    if not slug or not isinstance(slug, str):
        return 400, {"ok": False, "error": "missing pack"}
    gate = begin_packkind_write()
    if gate:
        return 409, {"ok": False, "error": gate}
    try:
        with _packkind_write_lock:
            dest, _bak, _snap = packkind_dest_paths()
            try:
                dest_doc = read_packkind_document(dest)
            except PackkindReadError:
                return 422, {"ok": False, "error": "Could not read tags file."}
            if not slug_ok(slug) or not slug_is_known(slug, dest_doc):
                return 404, {"ok": False, "error": "Unknown pack."}
            existing = (dest_doc.get("packs") or {}).get(slug)
            kind = payload["kind"] if "kind" in payload else _OMIT
            title = payload["title"] if "title" in payload else _OMIT
            tags = payload["tags"] if "tags" in payload else _OMIT
            new_obj, err = field_patch_pack(
                existing if isinstance(existing, dict) else None, slug, kind, title, tags
            )
            if err:
                return 400, {"ok": False, "error": err}
            assert new_obj is not None
            old_kind = None
            if isinstance(existing, dict):
                old_kind = str(existing.get("kind") or "").lower() or None
            shown = display_title(slug, new_obj)
            new_kind = new_obj.get("kind")
            kind_changed = (
                kind is not _OMIT
                and new_kind in VALID_KINDS
                and old_kind in VALID_KINDS
                and new_kind != old_kind
            )
            if kind_changed:
                label = KIND_LABELS.get(new_kind, str(new_kind))
                message = f"Saved. {shown} is now {label}. It will show under the {label} button."
            else:
                message = f"Saved tags for {shown}. Other files in this pack will show them too."
            return commit_packkind(slug, new_obj, message, dest, _bak, _snap)
    finally:
        end_packkind_write()


def restore_packkind_response(payload: dict) -> tuple[int, dict]:
    if _audio_root is None:
        return 400, {"ok": False, "error": "No library folder selected"}
    if forbidden_packkind_parent(_audio_root):
        return 400, {"ok": False, "error": "Cannot save tags in this folder."}
    slug = payload.get("pack")
    if not slug or not isinstance(slug, str):
        return 400, {"ok": False, "error": "missing pack"}
    gate = begin_packkind_write()
    if gate:
        return 409, {"ok": False, "error": gate}
    try:
        with _packkind_write_lock:
            dest, bak, snap = packkind_dest_paths()
            try:
                dest_doc = read_packkind_document(dest)
            except PackkindReadError:
                return 422, {"ok": False, "error": "Could not read tags file."}
            if not slug_ok(slug) or not slug_is_known(slug, dest_doc):
                return 404, {"ok": False, "error": "Unknown pack."}
            snap_doc = optional_packkind_document(snap)
            bak_doc = optional_packkind_document(bak)
            src_doc, src_name = restore_source(dest_doc, snap_doc, bak_doc, slug)
            shown = display_title(slug, (dest_doc.get("packs") or {}).get(slug))
            if src_doc is None:
                return 404, {"ok": False, "error": f"No previous tags for {shown}."}
            src_obj = (src_doc.get("packs") or {}).get(slug)
            if not isinstance(src_obj, dict):
                return 404, {"ok": False, "error": f"No previous tags for {shown}."}
            new_obj = dict(src_obj)
            if isinstance(new_obj.get("tags"), list):
                new_obj["tags"] = list(new_obj["tags"])
            message = f"Restored the last saved tags for {display_title(slug, new_obj)}."
            code, body = commit_packkind(slug, new_obj, message, dest, bak, snap)
            if code == 200:
                print(f"packkind: restored {slug} from {src_name} -> {dest}", flush=True)
            return code, body
    finally:
        end_packkind_write()


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
        if _write_running:
            return False, "Saving tags, wait then Rescan"
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
            persist_catalog_compact()
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
        if path == "/api/packkind":
            slug = (parse_qs(parsed.query).get("pack") or [""])[0]
            code, body = get_packkind_response(slug)
            self._json(code, body)
            return
        if path == "/api/tags":
            code, body = get_vocabulary_response()
            self._json(code, body)
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

    def _bound_port(self) -> int:
        return int(self.server.server_address[1])

    def _root_change_blocked(self) -> str | None:
        with _scan_ctl:
            if snapshot_scan()["running"]:
                return "Scan already running"
            if _write_running:
                return "Saving tags, wait then Rescan"
            return None

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        port = self._bound_port()
        if host in ("127.0.0.1", "localhost"):
            return True
        m = re.fullmatch(r"(127\.0\.0\.1|localhost):(\d+)", host)
        if not m:
            return False
        p = int(m.group(2))
        return p == port or 8765 <= p <= 8784

    def _origin_allowed(self, origin: str) -> bool:
        port = self._bound_port()
        allowed = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
        return origin.rstrip("/") in allowed

    def _csrf_ok(self) -> bool:
        if not self._host_allowed():
            return False
        origin = (self.headers.get("Origin") or "").strip()
        referer = (self.headers.get("Referer") or "").strip()
        if origin:
            return self._origin_allowed(origin)
        if referer:
            try:
                u = urlparse(referer)
                if (u.scheme or "").lower() not in ("http", "https"):
                    return False
                host = (u.hostname or "").lower()
                if host not in ("127.0.0.1", "localhost"):
                    return False
                ref_origin = f"{u.scheme}://{u.hostname}"
                if u.port:
                    ref_origin += f":{u.port}"
                elif u.scheme == "http":
                    ref_origin += ":80"
                return self._origin_allowed(ref_origin)
            except Exception:
                return False
        return True

    def _read_json_post(self) -> tuple[dict | None, tuple[int, dict] | None]:
        if not self._csrf_ok():
            return None, (403, {"ok": False, "error": "Forbidden"})
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return None, (400, {"ok": False, "error": "Content-Type must be application/json"})
        cl = self.headers.get("Content-Length")
        if cl is None:
            return None, (400, {"ok": False, "error": "Content-Length required"})
        try:
            length = int(cl)
        except (TypeError, ValueError):
            return None, (400, {"ok": False, "error": "Content-Length required"})
        if length < 0 or length > MAX_BODY:
            return None, (400, {"ok": False, "error": "Request too large"})
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return None, (400, {"ok": False, "error": "Invalid JSON"})
        if not isinstance(payload, dict):
            return None, (400, {"ok": False, "error": "Invalid JSON"})
        return payload, None

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        payload, err = self._read_json_post()
        if err:
            self.close_connection = True
            self._json(err[0], err[1])
            return
        assert payload is not None
        if path == "/api/packkind":
            code, body = save_packkind_response(payload)
            self._json(code, body)
            return
        if path == "/api/packkind/restore":
            code, body = restore_packkind_response(payload)
            self._json(code, body)
            return
        if path == "/api/tags":
            code, body = save_vocabulary_response(payload)
            self._json(code, body)
            return
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
                low = message.lower()
                code = 409 if ("already" in low or "saving tags" in low) else 400
                self._json(code, {"ok": False, "error": message})
                return
            self._json(200, {"ok": True, "message": message})
            return
        if path == "/api/browse-root":
            blocked = self._root_change_blocked()
            if blocked:
                self._json(409, {"ok": False, "error": blocked})
                return
            try:
                chosen = pick_directory(_audio_root)
            except Exception as e:
                self._json(500, {"ok": False, "error": f"Folder dialog failed: {e}"})
                return
            if chosen is None:
                self._json(200, {"ok": False, "cancelled": True})
                return
            blocked = self._root_change_blocked()
            if blocked:
                self._json(409, {"ok": False, "error": blocked})
                return
            set_audio_root(chosen)
            try:
                save_config(chosen)
            except OSError as e:
                self._json(500, {"ok": False, "error": f"Could not save folder: {e}"})
                return
            load_packkind(chosen)
            ensure_packkind_snapshot()
            ok, message = start_scan(clear_catalog=True)
            if not ok:
                low = message.lower()
                code = 409 if ("already" in low or "saving tags" in low) else 400
                self._json(code, {"ok": False, "error": message, "root": str(chosen)})
                return
            self._json(
                200,
                {
                    "ok": True,
                    "root": str(chosen),
                    "scanning": True,
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
        load_packkind(_audio_root)
        ensure_packkind_snapshot()
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
