#!/usr/bin/env python3
"""l10n-guard 0.16.0: a space followed by two U+200B is an `invisible-char`
warning in every language, including Thai, Lao, Myanmar, Khmer and Tibetan,
where a lone U+200B stays exempt, and the message names the shape. The
strings here are written for the test; the Thai, Burmese and Tibetan ones
follow the shape of the four found by the census's zwsp-langs study.
Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g

Z = chr(0x200B)
PAIR = " " + Z + Z
NOTE = "invisible character(s) not in source: U+200B (zero-width space); a space followed by two U+200B"


def codes(problems):
    return [p["code"] for p in problems]


def invisible(problems):
    """The invisible-char message, or None."""
    found = [p["message"] for p in problems if p["code"] == "invisible-char"]
    return found[0] if found else None


class ZwspPair0160Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 16, 0))

    def test_pair_in_scripts_without_spaces(self):
        problems = g.check_pair("Clean and modern font", "ฟอนต์ทันสมัย" + PAIR + "อ่านง่าย", "font")
        self.assertEqual(problems, [{"level": g.WARNING, "code": "invisible-char", "key": "font",
                                     "message": NOTE}])
        self.assertEqual(invisible(g.check_pair("Use your IP", "IP ကို" + PAIR + "အသုံးပြုပါ")), NOTE)
        self.assertEqual(invisible(g.check_pair("H.264 or H.265", "H.264 དང་།" + PAIR + "H.265")), NOTE)

    def test_word_break_hints_still_exempt(self):
        self.assertEqual(g.check_pair("Save file", "บันทึก" + Z + "ไฟล์"), [])
        self.assertEqual(g.check_pair("Save file", "រក្សា" + Z + "ឯកសារ"), [])
        # One U+200B after a space, or two between letters: not the shape, still exempt.
        self.assertEqual(g.check_pair("Save file", "บันทึก " + Z + "ไฟล์"), [])
        self.assertEqual(g.check_pair("Save file", "ບັນທຶກ" + Z + Z + "ໄຟລ໌"), [])

    def test_pair_in_other_languages(self):
        self.assertEqual(invisible(g.check_pair("EXIF data", "EXIF" + PAIR + "bilgileri")), NOTE)
        # Without the shape the 0.15.0 message is unchanged.
        self.assertEqual(invisible(g.check_pair("Save", "Speich" + Z + "ern")),
                         "invisible character(s) not in source: U+200B (zero-width space)")

    def test_pair_listed_with_other_characters(self):
        problems = g.check_pair("Save", "Speichern" + chr(0x00AD) + PAIR + "x")
        self.assertEqual(invisible(problems), "invisible character(s) not in source: "
                         "U+00AD (soft hyphen), U+200B (zero-width space); a space followed by two U+200B")

    def test_source_has_it_too(self):
        self.assertIsNone(invisible(g.check_pair("A" + PAIR + "b", "ก" + PAIR + "ข")))

    def test_android_catalog(self):
        src = '<resources><string name="m">Use your own IP</string></resources>'
        tgt = '<resources><string name="m">IP ကို' + PAIR + 'အသုံးပြုပါ</string></resources>'
        result = g.check_android(src, tgt)
        problems = result[0] if isinstance(result, tuple) else result
        self.assertIn("invisible-char", codes(problems))


if __name__ == "__main__":
    unittest.main()
