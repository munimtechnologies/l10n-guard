#!/usr/bin/env python3
"""l10n-guard 0.14.0: FormatJS descriptor files ({"id": {"defaultMessage",
"description"}}, the shape of Mattermost's en.json) are read as
{id: defaultMessage} before any check, as pre-registered in the census's
antonym-collision/FORMATJS-PREREG.md. The fixture copies the shape of the
first entries of Mattermost's webapp/channels/src/i18n/en.json (read on
2026-10-19); descriptions and translations here are written for the test.
Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g

EN = {
    "about.buildnumber": {"defaultMessage": "Build Number:", "description": "Label in the About dialog"},
    "about.copyright": {"defaultMessage": "Copyright 2015 - {currentYear} Mattermost, Inc. All rights reserved",
                        "description": "Copyright line; {currentYear} is the current year"},
    "channel.mute": {"defaultMessage": "Mute Channel", "description": "Channel menu item"},
    "channel.unmute": {"defaultMessage": "Unmute Channel", "description": "Channel menu item"},
}
DE = {
    "about.buildnumber": "Buildnummer:",
    "about.copyright": "Copyright 2015 - {currentYear} Mattermost, Inc. Alle Rechte vorbehalten",
    "channel.mute": "Kanal stummschalten",
    "channel.unmute": "Stummschaltung des Kanals aufheben",
}


def codes(problems):
    return sorted((p["code"], p["key"]) for p in problems)


def collisions(source, target):
    return [(p["key"], p.get("other_key")) for p in g.check_catalog(source, target)
            if p["code"] == "antonym-collision"]


class Descriptor0140Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 14, 0))

    def test_unwrap_descriptor_file(self):
        self.assertEqual(g.unwrap_descriptors(EN), {k: v["defaultMessage"] for k, v in EN.items()})

    def test_unwrap_leaves_other_shapes_alone(self):
        flat = {"a": "Save"}
        nested = {"menu": {"save": "Save", "open": "Open"}}
        mixed = {"a": {"defaultMessage": "Save", "description": ""}, "b": "Open"}
        ast = {"a": {"defaultMessage": [{"type": 0, "value": "Save"}]}}
        no_message = {"a": {"description": "only a note"}}
        for data in (flat, nested, mixed, ast, no_message, {}, [], "Save", None):
            with self.subTest(data=data):
                self.assertIs(g.unwrap_descriptors(data), data)

    def test_flatten_alone_still_splits_descriptors(self):
        # The 0.13.0 behaviour this release works around: flattened, the
        # English keys end in .defaultMessage and match no translated key.
        flat = g.flatten(EN)
        self.assertIn("channel.mute.defaultMessage", flat)
        self.assertNotIn("channel.mute", flat)

    def test_descriptor_source_against_flat_translation(self):
        problems = g.check_catalog(EN, DE)
        found = {code for code, key in codes(problems)}
        self.assertFalse(found & {"missing-key", "extra-key"}, codes(problems))
        self.assertEqual([p for p in problems if p["level"] == g.ERROR], [])

    def test_both_sides_descriptors(self):
        de = {k: {"defaultMessage": v, "description": ""} for k, v in DE.items()}
        problems = g.check_catalog(EN, de)
        found = {code for code, key in codes(problems)}
        self.assertFalse(found & {"missing-key", "extra-key"}, codes(problems))
        self.assertEqual([p for p in problems if p["level"] == g.ERROR], [])

    def test_placeholder_checked_through_descriptors(self):
        de = dict(DE, **{"about.copyright": "Copyright 2015 Mattermost, Inc. Alle Rechte vorbehalten"})
        self.assertIn(("placeholder-missing", "about.copyright"), codes(g.check_catalog(EN, de)))

    def test_missing_key_still_reported(self):
        de = {k: v for k, v in DE.items() if k != "channel.unmute"}
        self.assertIn(("missing-key", "channel.unmute"), codes(g.check_catalog(EN, de)))

    def test_antonym_collision_through_descriptors(self):
        bg = dict(DE, **{"channel.mute": "Заглушаване на канала", "channel.unmute": "Заглушаване на канала"})
        self.assertEqual(collisions(EN, bg), [("channel.mute", "channel.unmute")])
        self.assertEqual(collisions(EN, DE), [])

    def test_descriptions_are_not_compared(self):
        en = {"save.a": {"defaultMessage": "Save", "description": "Mute button"},
              "save.b": {"defaultMessage": "Save", "description": "Unmute button"}}
        # Flattened, the two descriptions form an antonym pair (the second
        # held-out test's 1,083 Mattermost "pairs"); unwrapped, they don't.
        self.assertEqual(g.antonym_pairs(g.flatten(en)), [("save.a.description", "save.b.description")])
        self.assertEqual(g.antonym_pairs(g.unwrap_descriptors(en)), [])
        self.assertEqual(collisions(en, {"save.a": "Speichern", "save.b": "Speichern"}), [])


if __name__ == "__main__":
    unittest.main()
