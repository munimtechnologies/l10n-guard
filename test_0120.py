#!/usr/bin/env python3
"""l10n-guard 0.12.0: antonym-collision, two keys whose source texts differ
only by antonyms but share one translation. The unit cases are U1-U10 of the
census's antonym-collision/GUARD-PREREG.md, written before the code ran; the
translations are real ones from NocoBase (10810697) and Mastodon (cab53a59)
unless marked "written for the test". Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

import l10n_guard as g

EN_NOCO = {"Default collapse": "Default collapse", "Default expanded": "Default expanded"}
EN_MASTO = {"video.mute": "Mute", "video.unmute": "Unmute"}


def collisions(problems):
    return [(p["level"], p["key"], p.get("other_key")) for p in problems if p["code"] == "antonym-collision"]


class AntonymCollision0120Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 12, 0))

    def test_nocobase_de(self):
        # U1: NocoBase packages/core/client/src/locale/de-DE.json.
        de = {"Default collapse": "Standardmäßig eingeklappt", "Default expanded": "Standardmäßig eingeklappt"}
        found = [p for p in g.check_catalog(EN_NOCO, de) if p["code"] == "antonym-collision"]
        self.assertEqual(collisions(found), [(g.WARNING, "Default collapse", "Default expanded")])
        self.assertIn("Standardmäßig eingeklappt", found[0]["message"])
        self.assertIn("Default expanded", found[0]["message"])

    def test_mastodon_it(self):
        # U2: Mastodon app/javascript/mastodon/locales/it.json.
        it = {"video.mute": "Muta", "video.unmute": "Muta"}
        self.assertEqual(collisions(g.check_catalog(EN_MASTO, it)),
                         [(g.WARNING, "video.mute", "video.unmute")])

    def test_different_values(self):
        # U3: written for the test.
        de = {"Default collapse": "Standardmäßig eingeklappt", "Default expanded": "Standardmäßig ausgeklappt"}
        self.assertEqual(collisions(g.check_catalog(EN_NOCO, de)), [])

    def test_copy_is_not_a_collision(self):
        # U4: shaped like NocoBase pt-BR and tr-TR, which keep an English text
        # for both (written for the test); a copy, not a collision.
        pt = {"Default collapse": "Default collapse", "Default expanded": "Default collapse"}
        self.assertEqual(collisions(g.check_catalog(EN_NOCO, pt)), [])
        # Written for the test: case doesn't make a copy a collision.
        self.assertEqual(collisions(g.check_catalog(EN_MASTO, {"video.mute": "MUTE", "video.unmute": "MUTE"})), [])

    def test_empty_or_missing(self):
        # U5: written for the test.
        self.assertEqual(collisions(g.check_catalog(EN_MASTO, {"video.mute": "", "video.unmute": ""})), [])
        self.assertEqual(collisions(g.check_catalog(EN_MASTO, {"video.mute": "Muta"})), [])

    def test_whitespace(self):
        # U6: written for the test.
        it = {"video.mute": " Muta", "video.unmute": "Muta "}
        self.assertEqual(collisions(g.check_catalog(EN_MASTO, it)), [(g.WARNING, "video.mute", "video.unmute")])

    def test_not_pairs(self):
        # U7: written for the test. Two flips, one side's inflections, and
        # antonyms outside the word list are not pairs.
        self.assertEqual(g.antonym_pairs({"a": "Show before", "b": "Hide after"}), [])
        self.assertEqual(g.antonym_pairs({"a": "Expand", "b": "Expanded"}), [])
        self.assertEqual(g.antonym_pairs({"a": "Visible", "b": "Hidden"}), [])
        self.assertEqual(g.antonym_pairs({"a": "Show all", "b": "Hide"}), [])
        self.assertEqual(g.antonym_pairs({"a": "Show", "b": "Hide", "c": 3}), [("a", "b")])

    def test_three_keys(self):
        # U8: written for the test. Hide and Hidden are one side, so two pairs.
        en = {"a": "Show", "b": "Hide", "c": "Hidden"}
        fr = {"a": "Masquer", "b": "Masquer", "c": "Masquer"}
        self.assertEqual(collisions(g.check_catalog(en, fr)),
                         [(g.WARNING, "a", "b"), (g.WARNING, "a", "c")])

    def test_arb(self):
        # U9: written for the test.
        en = {"@@locale": "en", "mute": "Mute", "unmute": "Unmute"}
        it = {"@@locale": "it", "mute": "Muta", "unmute": "Muta"}
        self.assertEqual(collisions(g.check_arb(en, it)), [(g.WARNING, "mute", "unmute")])

    def test_cli(self):
        # U10: the json kind prints it as a warning; --strict fails on it.
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, data in (("en.json", EN_MASTO), ("it.json", {"video.mute": "Muta", "video.unmute": "Muta"})):
                paths[name] = os.path.join(tmp, name)
                with open(paths[name], "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = g.run(["json", paths["en.json"], paths["it.json"]])
            self.assertEqual(code, 0)
            self.assertIn("WARNING antonym-collision [video.mute]: same translation as video.unmute",
                          out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = g.run(["--strict", "json", paths["en.json"], paths["it.json"]])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
