#!/usr/bin/env python3
"""l10n-guard 0.15.0: invisible format characters (Unicode category Cf) in a
translation that its source doesn't have are an `invisible-char` warning,
except where the script needs them: U+200B in Thai, Lao, Tibetan, Myanmar
and Khmer, directional marks and bidi controls in right-to-left text,
zero-width (non-)joiners anywhere, and soft hyphens between two letters.
The strings here are written for the test, except the soft-hyphen ones,
which follow shipped catalogs found by the census. Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g


def codes(problems):
    return [p["code"] for p in problems]


class Invisible0150Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 15, 0))

    def test_zero_width_space(self):
        problems = g.check_pair("Save", "Speich​ern", "save")
        self.assertEqual(problems, [{
            "level": g.WARNING, "code": "invisible-char", "key": "save",
            "message": "invisible character(s) not in source: U+200B (zero-width space)"}])

    def test_one_warning_lists_every_character(self):
        problems = g.check_pair("Save", "Speichern­​")
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["message"], "invisible character(s) not in source: "
                         "U+00AD (soft hyphen), U+200B (zero-width space)")

    def test_character_in_source_too(self):
        self.assertEqual(g.check_pair("Save­it", "Spei­chern"), [])
        self.assertEqual(g.check_pair("⁨%s⁩ saved", "⁨%s⁩ gespeichert"), [])

    def test_byte_order_mark_and_word_joiner(self):
        self.assertEqual(codes(g.check_pair("Save", "﻿Speichern")), ["invisible-char"])
        self.assertIn("U+FEFF (byte-order mark)", g.check_pair("Save", "﻿Speichern")[0]["message"])
        self.assertEqual(codes(g.check_pair("Save", "Spei⁠chern")), ["invisible-char"])

    def test_zero_width_space_in_scripts_without_spaces(self):
        self.assertEqual(g.check_pair("Save file", "บันทึก​ไฟล์"), [])
        self.assertEqual(g.check_pair("Save file", "រក្សា​ឯកសារ"), [])
        # Chinese and Japanese don't use U+200B, so it is still reported there.
        self.assertEqual(codes(g.check_pair("Save", "保存​")), ["invisible-char"])

    def test_marks_and_bidi_controls(self):
        # Right-to-left text: normal.
        self.assertEqual(g.check_pair("Delete file", "حذف‏ الملف"), [])
        self.assertEqual(g.check_pair("Hello", "⁨שלום⁩"), [])
        self.assertEqual(g.check_pair("Hello", "‫שלום‬؜"), [])
        # Left-to-right text: reported.
        problems = g.check_pair("Delete file", "Datei‏ löschen")
        self.assertEqual(codes(problems), ["invisible-char"])
        self.assertIn("U+200F (right-to-left mark)", problems[0]["message"])
        problems = g.check_pair("Hello", "⁨Bonjour⁩")
        self.assertEqual(problems[0]["message"], "invisible character(s) not in source: U+2068, U+2069")

    def test_joiners_are_normal(self):
        self.assertEqual(g.check_pair("Hindi", "हिन्‍दी"), [])
        self.assertEqual(g.check_pair("Settings", "تنظیم‌ات"), [])
        self.assertEqual(g.check_pair("Settings", "Einstel‌lungen"), [])

    def test_soft_hyphens(self):
        # Between two letters: a hyphenation point in a compound word.
        self.assertEqual(g.check_pair("Default video format", "Standaard­videoformaat"), [])
        self.assertEqual(g.check_pair("Start playing in the background", "Op de achter­grond afspelen"), [])
        # At either end, after a space, or in Chinese text: reported.
        self.assertEqual(codes(g.check_pair("Change view", "­Cambiar vista")), ["invisible-char"])
        self.assertEqual(codes(g.check_pair("Cancel", "Annulla­")), ["invisible-char"])
        self.assertEqual(codes(g.check_pair("Anonymous analytics", "启用匿名­分析")), ["invisible-char"])
        self.assertEqual(codes(g.check_pair("Default video", "Standaard­video­")), ["invisible-char"])

    def test_arabic_signs_tags_and_mongolian(self):
        self.assertEqual(g.check_pair("Number 5", "رقم ؀5"), [])
        flag = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
        self.assertEqual(g.check_pair("Flag", "Flagge " + flag), [])
        mongolia = "ᠮᠣᠩᠭᠣᠯ᠎ᠤᠯᠤᠰ"
        self.assertEqual(g.check_pair("Mongolia", mongolia), [])
        self.assertEqual(codes(g.check_pair("Mongolia", "Mongo᠎lei")), ["invisible-char"])

    def test_other_issues_unchanged(self):
        self.assertEqual(codes(g.check_pair("Save", "")), ["empty"])
        self.assertEqual(codes(g.check_pair("Settings", "Settings")), ["untranslated"])
        self.assertEqual(sorted(codes(g.check_pair("%d files", "​Dateien"))),
                         ["invisible-char", "placeholder-missing"])

    def test_json_catalog(self):
        problems = g.check_catalog({"a": "Save", "b": "Open"}, {"a": "Speichern​", "b": "Öffnen"})
        self.assertEqual([(p["code"], p.get("key")) for p in problems], [("invisible-char", "a")])

    def test_android_raw_character(self):
        src = '<resources><string name="save">Save</string></resources>'
        tgt = '<resources><string name="save">Speich​ern</string></resources>'
        result = g.check_android(src, tgt)
        problems = result[0] if isinstance(result, tuple) else result
        self.assertIn("invisible-char", codes(problems))


if __name__ == "__main__":
    unittest.main()
