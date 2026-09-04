"""Packkind write API: fail-closed sidecar, CSRF, catalog patch."""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


def _door_item(**kw):
    rec = {
        "id": 1,
        "name": "Door_close_01",
        "file": "Door_close_01.wav",
        "pack": "door",
        "packTitle": "Door",
        "rel": "Door_close_01.wav",
        "folder": "",
        "category": "Door",
        "ext": "wav",
        "kind": "sfx",
        "tags": ["sfx", "door", "foley"],
        "bytes": 100,
    }
    rec.update(kw)
    return rec


class PackkindTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.audio = self.root / "Audio"
        self.lib = self.audio / "_library"
        self.audio.mkdir()
        self.lib.mkdir()
        (self.audio / "door").mkdir()
        self._orig = {
            "CATALOG_PATH": server.CATALOG_PATH,
            "SNAPSHOT_PATH": server.SNAPSHOT_PATH,
            "CONFIG_PATH": server.CONFIG_PATH,
            "ROOT": server.ROOT,
        }
        server.CATALOG_PATH = self.lib / "catalog.json"
        server.SNAPSHOT_PATH = self.lib / "packkind.snapshot.json"
        server.CONFIG_PATH = self.lib / "config.json"
        server._write_running = False
        server._packkind = {}
        server.set_audio_root(self.audio)
        server.set_catalog({"generated": 1, "items": [_door_item()], "count": 1, "root": str(self.audio)})
        server.set_scan(running=False, message="Idle", found=1, root=str(self.audio), error=None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        server._write_running = False
        server.set_scan(running=False, message="Idle", found=0, root="", error=None)
        server.set_audio_root(None)
        server._packkind = {}
        server.set_catalog({"generated": 0, "items": [], "count": 0, "root": ""})
        server.CATALOG_PATH = self._orig["CATALOG_PATH"]
        server.SNAPSHOT_PATH = self._orig["SNAPSHOT_PATH"]
        server.CONFIG_PATH = self._orig["CONFIG_PATH"]
        self._tmp.cleanup()

    def dest(self) -> Path:
        return self.audio / "packkind.json"

    def bak(self) -> Path:
        return self.audio / "packkind.json.bak"

    def write_sidecar(self, packs: dict, path: Path | None = None) -> None:
        p = path or self.dest()
        doc = {"version": 1, "packs": packs}
        p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def read_sidecar(self, path: Path | None = None) -> dict:
        return json.loads((path or self.dest()).read_text(encoding="utf-8"))

    def request(self, method: str, path: str, body=None, headers=None, content_type="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        hdrs = dict(headers or {})
        raw = None
        if method != "GET":
            if content_type is not None:
                hdrs.setdefault("Content-Type", content_type)
            raw = json.dumps(body if body is not None else {}).encode("utf-8")
        conn.request(method, path, body=raw, headers=hdrs)
        res = conn.getresponse()
        data = res.read()
        status = res.status
        conn.close()
        parsed = {}
        if data:
            try:
                parsed = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                parsed = {"_raw": data.decode("utf-8", "replace")}
        return status, parsed

    def save(self, payload: dict, **kw):
        return self.request("POST", "/api/packkind", payload, **kw)

    def test_create_empty_sidecar_on_save(self):
        self.assertFalse(self.dest().exists())
        status, body = self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["door", "foley"]})
        self.assertEqual(status, 200, body)
        self.assertTrue(body.get("ok"))
        self.assertTrue(self.dest().exists())
        doc = self.read_sidecar()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["packs"]["door"]["tags"], ["sfx", "door", "foley"])
        self.assertEqual(doc["packs"]["door"]["kind"], "sfx")
        self.assertEqual(doc["packs"]["door"]["title"], "Door")

    def test_tags_replace_not_union(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
            "other": {"kind": "music", "title": "Other", "tags": ["music"]},
        })
        status, body = self.save({"pack": "door", "tags": ["wood"]})
        self.assertEqual(status, 200, body)
        tags = self.read_sidecar()["packs"]["door"]["tags"]
        self.assertEqual(tags, ["sfx", "wood"])
        self.assertNotIn("foley", tags)
        self.assertEqual(self.read_sidecar()["packs"]["other"]["tags"], ["music"])

    def test_title_only_does_not_blank_tags(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.save({"pack": "door", "title": "Doors"})
        self.assertEqual(status, 200, body)
        pack = self.read_sidecar()["packs"]["door"]
        self.assertEqual(pack["title"], "Doors")
        self.assertEqual(pack["tags"], ["sfx", "door", "foley"])
        self.assertEqual(pack["kind"], "sfx")

    def test_refuse_write_under_forbidden_parents(self):
        for name in ("_library", "_export", "_ZIP"):
            with self.subTest(name=name):
                folder = self.root / name
                folder.mkdir(exist_ok=True)
                server.set_audio_root(folder)
                before = list(folder.glob("packkind.json*"))
                status, body = self.save({"pack": "door", "tags": ["wood"]})
                self.assertEqual(status, 400, body)
                self.assertFalse(body.get("ok"))
                self.assertEqual(list(folder.glob("packkind.json*")), before)
        server.set_audio_root(self.audio)

    def test_unparseable_sidecar_422_bytes_unchanged(self):
        garbage = "{not json, 92 other keys would be wiped if we fail-open\n"
        self.dest().write_text(garbage, encoding="utf-8")
        orig = self.dest().read_bytes()
        status, body = self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["wood"]})
        self.assertEqual(status, 422, body)
        self.assertEqual(self.dest().read_bytes(), orig)

    def test_packs_not_object_422(self):
        self.dest().write_text(json.dumps({"version": 1, "packs": []}), encoding="utf-8")
        orig = self.dest().read_bytes()
        status, body = self.save({"pack": "door", "tags": ["wood"]})
        self.assertEqual(status, 422, body)
        self.assertEqual(self.dest().read_bytes(), orig)

    def test_bak_exists_after_update(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.save({"pack": "door", "tags": ["wood"]})
        self.assertEqual(status, 200, body)
        self.assertTrue(self.bak().exists())
        bak = self.read_sidecar(self.bak())
        self.assertEqual(bak["packs"]["door"]["tags"], ["sfx", "door", "foley"])

    def test_snapshot_on_save_restore_snapshot_when_dest_differs(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["wood"]})
        self.assertEqual(status, 200, body)
        self.assertTrue(server.SNAPSHOT_PATH.exists())
        snap = self.read_sidecar(server.SNAPSHOT_PATH)
        self.assertEqual(snap["packs"]["door"]["tags"], ["sfx", "wood"])
        # Unreal-style clobber of dest only
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]},
        })
        status, body = self.request("POST", "/api/packkind/restore", {"pack": "door"})
        self.assertEqual(status, 200, body)
        self.assertIn("Restored the last saved tags", body.get("message", ""))
        self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "wood"])

    def test_restore_uses_bak_when_dest_equals_snapshot(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        self.assertEqual(self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["door", "foley"]})[0], 200)
        self.assertEqual(self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["wood"]})[0], 200)
        dest_tags = self.read_sidecar()["packs"]["door"]["tags"]
        snap_tags = self.read_sidecar(server.SNAPSHOT_PATH)["packs"]["door"]["tags"]
        self.assertEqual(dest_tags, snap_tags)
        self.assertEqual(dest_tags, ["sfx", "wood"])
        status, body = self.request("POST", "/api/packkind/restore", {"pack": "door"})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "door", "foley"])

    def test_reject_bad_slugs(self):
        for slug in ("..", "", "foo/bar", "foo\\bar"):
            with self.subTest(slug=slug):
                payload = {"pack": slug, "tags": ["wood"]} if slug != "" else {"tags": ["wood"]}
                if slug == "":
                    payload = {"pack": "", "tags": ["wood"]}
                status, body = self.save(payload)
                self.assertIn(status, (400, 404), body)
                self.assertFalse(self.dest().exists())

    def test_tag_re_accepts_test_rejects_spaces_and_kinds(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        status, body = self.save({"pack": "door", "tags": ["_test"]})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "_test"])
        for bad in (["sci fi"], ["music"], ["voice"], ["sfx"]):
            with self.subTest(bad=bad):
                st, resp = self.save({"pack": "door", "tags": bad})
                self.assertEqual(st, 400, resp)
                self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "_test"])

    def test_foreign_origin_403_body_not_applied(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.save(
            {"pack": "door", "tags": ["wood"]},
            headers={"Origin": "http://evil.example"},
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "door", "foley"])

    def test_missing_origin_and_referer_allowed(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        status, body = self.save({"pack": "door", "tags": ["wood"]})
        self.assertEqual(status, 200, body)

    def test_valid_origin_allowed(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        status, body = self.save(
            {"pack": "door", "tags": ["wood"]},
            headers={"Origin": f"http://127.0.0.1:{self.port}"},
        )
        self.assertEqual(status, 200, body)

    def test_non_json_content_type_400(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door"]},
        })
        status, body = self.save(
            {"pack": "door", "tags": ["wood"]},
            content_type="text/plain",
        )
        self.assertEqual(status, 400, body)
        self.assertEqual(self.read_sidecar()["packs"]["door"]["tags"], ["sfx", "door"])

    def test_content_length_too_large_rejected_before_read(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/api/packkind")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(server.MAX_BODY + 1))
        conn.endheaders()
        res = conn.getresponse()
        data = res.read()
        conn.close()
        self.assertEqual(res.status, 400)
        parsed = json.loads(data.decode("utf-8"))
        self.assertFalse(parsed.get("ok"))

    def test_compact_catalog_dump(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        status, body = self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["wood"]})
        self.assertEqual(status, 200, body)
        text = server.CATALOG_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(text, r'"pack":\n\s+')
        self.assertTrue(body.get("items"))

    def test_first_save_on_heuristic_pack_creates_key(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door"]},
        })
        extra = _door_item(
            id=2,
            name="loop_01",
            file="loop_01.wav",
            pack="someambientpack",
            packTitle="Some Ambient Pack",
            rel="loop_01.wav",
            kind="music",
            tags=["music"],
        )
        server.set_catalog({
            "generated": 1,
            "items": [_door_item(), extra],
            "count": 2,
            "root": str(self.audio),
        })
        status, body = self.save({
            "pack": "someambientpack",
            "kind": "music",
            "title": "Some Ambient Pack",
            "tags": ["ambient"],
        })
        self.assertEqual(status, 200, body)
        packs = self.read_sidecar()["packs"]
        self.assertIn("someambientpack", packs)
        self.assertEqual(packs["someambientpack"]["tags"], ["music", "ambient"])
        self.assertEqual(packs["door"]["tags"], ["sfx", "door"])

    def test_catalog_items_patched_without_iter_audio_files(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        orig = server.iter_audio_files

        def boom(*_a, **_k):
            raise AssertionError("iter_audio_files should not run on Save")

        server.iter_audio_files = boom
        try:
            status, body = self.save({"pack": "door", "kind": "sfx", "title": "Door", "tags": ["wood"]})
        finally:
            server.iter_audio_files = orig
        self.assertEqual(status, 200, body)
        self.assertEqual(body.get("patched"), 1)
        item = next(it for it in server.snapshot_catalog()["items"] if it["pack"] == "door")
        self.assertIn("wood", item["tags"])
        self.assertEqual(body["items"][0]["id"], 1)
        self.assertIn("wood", body["items"][0]["tags"])

    def test_409_when_scan_running(self):
        server.set_scan(running=True, message="Scanning…")
        try:
            status, body = self.save({"pack": "door", "tags": ["wood"]})
            self.assertEqual(status, 409, body)
            self.assertIn("Scan already running", body.get("error", ""))
        finally:
            server.set_scan(running=False, message="Idle")

    def test_409_start_scan_when_write_running(self):
        server._write_running = True
        try:
            ok, msg = server.start_scan()
            self.assertFalse(ok)
            self.assertIn("Saving tags", msg)
            status, body = self.request("POST", "/api/rescan", {})
            self.assertEqual(status, 409, body)
        finally:
            server._write_running = False

    def test_get_packkind_sidecar_and_heuristic(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.request("GET", "/api/packkind?pack=door")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["source"], "sidecar")
        self.assertEqual(body["tags"], ["sfx", "door", "foley"])
        extra = _door_item(id=2, pack="someambientpack", name="a", file="a.wav", rel="a.wav", kind="music", tags=["music"])
        server.set_catalog({
            "generated": 1,
            "items": [_door_item(), extra],
            "count": 2,
            "root": str(self.audio),
        })
        status, body = self.request("GET", "/api/packkind?pack=someambientpack")
        self.assertEqual(status, 200, body)
        self.assertEqual(body["source"], "heuristic")
        self.assertEqual(body["kind"], "music")

    def test_get_unparseable_422(self):
        self.dest().write_text("{nope", encoding="utf-8")
        status, body = self.request("GET", "/api/packkind?pack=door")
        self.assertEqual(status, 422, body)

    def test_write_path_does_not_call_load_packkind(self):
        self.write_sidecar({"door": {"kind": "sfx", "title": "Door", "tags": ["sfx"]}})
        orig = server.load_packkind

        def boom(*_a, **_k):
            raise AssertionError("load_packkind must not run on the write path")

        server.load_packkind = boom
        try:
            status, body = self.save({"pack": "door", "tags": ["wood"]})
            self.assertEqual(status, 200, body)
        finally:
            server.load_packkind = orig

    def test_detect_kind_still_ignores_rel_name(self):
        self.assertEqual(server.detect_kind("valentinosoundeffectslibrary", "", ""), "sfx")
        self.assertEqual(server.detect_kind("someambientpack", "voice.wav", "voice"), "music")

    def test_browse_root_409_when_write_running(self):
        called = {"n": 0}
        orig = server.pick_directory

        def boom(*_a, **_k):
            called["n"] += 1
            raise AssertionError("folder dialog should not open while saving")

        server.pick_directory = boom
        server._write_running = True
        try:
            status, body = self.request("POST", "/api/browse-root", {})
            self.assertEqual(status, 409, body)
            self.assertIn("Saving tags", body.get("error", ""))
            self.assertEqual(called["n"], 0)
        finally:
            server._write_running = False
            server.pick_directory = orig

    def test_browse_root_snapshots_when_missing(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        self.assertFalse(server.SNAPSHOT_PATH.exists())
        orig_pick = server.pick_directory
        orig_scan = server.start_scan
        server.pick_directory = lambda _initial: self.audio
        server.start_scan = lambda clear_catalog=False: (True, "Scan started")
        try:
            status, body = self.request("POST", "/api/browse-root", {})
            self.assertEqual(status, 200, body)
            self.assertTrue(body.get("ok"))
            self.assertTrue(server.SNAPSHOT_PATH.exists())
            snap = self.read_sidecar(server.SNAPSHOT_PATH)
            self.assertEqual(snap["packs"]["door"]["tags"], ["sfx", "door", "foley"])
        finally:
            server.pick_directory = orig_pick
            server.start_scan = orig_scan

    def test_browse_root_does_not_refresh_existing_snapshot(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "foley"]},
        })
        server.SNAPSHOT_PATH.write_text(
            json.dumps({"version": 1, "packs": {"door": {"kind": "sfx", "tags": ["sfx", "wood"]}}}, indent=2) + "\n",
            encoding="utf-8",
        )
        orig_pick = server.pick_directory
        orig_scan = server.start_scan
        server.pick_directory = lambda _initial: self.audio
        server.start_scan = lambda clear_catalog=False: (True, "Scan started")
        try:
            status, body = self.request("POST", "/api/browse-root", {})
            self.assertEqual(status, 200, body)
            snap = self.read_sidecar(server.SNAPSHOT_PATH)
            self.assertEqual(snap["packs"]["door"]["tags"], ["sfx", "wood"])
        finally:
            server.pick_directory = orig_pick
            server.start_scan = orig_scan

    def test_kind_only_rewrites_kind_token_in_tags(self):
        self.write_sidecar({
            "door": {"kind": "sfx", "title": "Door", "tags": ["sfx", "door", "foley"]},
        })
        status, body = self.save({"pack": "door", "kind": "music"})
        self.assertEqual(status, 200, body)
        pack = self.read_sidecar()["packs"]["door"]
        self.assertEqual(pack["kind"], "music")
        self.assertEqual(pack["title"], "Door")
        self.assertEqual(pack["tags"], ["music", "door", "foley"])


if __name__ == "__main__":
    unittest.main()
