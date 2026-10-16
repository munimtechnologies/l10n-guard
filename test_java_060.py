#!/usr/bin/env python3
"""l10n-guard 0.6.0: unnumbered placeholders in a new order, swapped
argument numbers, %1$d broken up as 1%d, percent signs Java reads as a
placeholder without throwing, the source's %d written "% d", and the
"write it as %%" hint. Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g


def levels(problems):
    return [(p["code"], p["level"]) for p in problems]


class Java060Test(unittest.TestCase):
    def test_version(self):
        self.assertEqual(g.__version__, "0.6.0")

    def test_parse_keeps_matches(self):
        specs = g._java_specs("%s and %d, %<d")
        self.assertEqual([(n, kind, m.group(0)) for n, kind, m in specs],
                         [(1, "any", "%s"), (2, "int", "%d"), (2, "int", "%<d")])
        self.assertEqual(g.java_format("%s and %d, %<d"), [(1, "any"), (2, "int"), (2, "int")])

    def test_error_position(self):
        text = "%1$s: 100 % sûr"
        with self.assertRaises(g.JavaFormatError) as ctx:
            g.java_format(text)
        self.assertEqual(ctx.exception.pos, text.index("% s"))
        with self.assertRaises(g.JavaFormatError) as ctx:
            g.java_format("Téléchargé à 50%")
        self.assertEqual(ctx.exception.pos, len("Téléchargé à 50"))

    def test_lone_percent(self):
        for text, pos in (("50 % de", 3), ("50%ige", 2), ("25% adicional", 2), ("100%.", 3),
                          ("100%", 3), ("x %ф", 2)):
            self.assertTrue(g._lone_percent(text, pos), text)
        for text, pos in (("%1$ x", 0), ("a %r b", 2), ("%%", 0), ("%-5d", 0)):
            self.assertFalse(g._lone_percent(text, pos), text)

    def test_hint_on_stray_percent_errors(self):
        problems = g.check_java_format("%1$s done", "%1$s terminé à 100%")
        self.assertEqual(levels(problems), [("java-format", g.ERROR)])
        self.assertIn("UnknownFormatConversionException", problems[0]["message"])
        self.assertIn("100%", problems[0]["message"])
        self.assertIn("write it as %%", problems[0]["message"])
        flags = g.check_java_format("%1$d%% done", "%1$d % terminé")
        self.assertIn("FormatFlagsConversionMismatchException", flags[0]["message"])
        self.assertIn("write it as %%", flags[0]["message"])

    def test_no_hint_on_other_errors(self):
        problems = g.check_java_format("%d left", "%d %restants")
        self.assertEqual(len(problems), 1)
        self.assertNotIn("percent sign", problems[0]["message"])

    def test_percent_read_as_placeholder(self):
        # Flashy's habit: "25% adicionais" reads as "% a", a hex float.
        flashy = g.check_java_format("%1$d dits, 25%% longer", "%1$d pontos, 25% adicionais")
        self.assertEqual(levels(flashy), [("java-format", g.ERROR)])
        self.assertIn('"% a"', flashy[0]["message"])
        self.assertIn("IllegalFormatConversionException", flashy[0]["message"])
        self.assertIn("write %% for a percent sign", flashy[0]["message"])
        # "% d" throws nothing: it prints the number a second time.
        silent = g.check_java_format("%1$d%% done", "%1$d % done")
        self.assertEqual(levels(silent), [("java-format", g.ERROR)])
        self.assertIn("print argument 1 there", silent[0]["message"])
        extra = g.check_java_format("%d%% done", "%d% fertig")
        self.assertEqual(levels(extra), [("java-format", g.ERROR)])
        self.assertIn("MissingFormatArgumentException", extra[0]["message"])

    def test_space_flag_on_the_source_placeholder(self):
        # ownCloud's Uyghur strings write the source's %d as "% d": Java
        # prints " 5", so this is a warning, not "write %%".
        for target in ("% d يېڭى رەسىم يۈكلىنىدۇ.", "ھۆججەت ئىسمى% d ھەرپتىن ئېشىپ كەتمەسلىكى كېرەك."):
            problems = g.check_java_format("%d new pictures will be uploaded.", target)
            self.assertEqual(levels(problems), [("java-format-flag", g.WARNING)], target)
            self.assertIn("leading space", problems[0]["message"])
            self.assertNotIn("write %%", problems[0]["message"])
        # Still a stray percent: a number before it, a Latin letter after it,
        # one placeholder more than the source has, or a source without %d
        # (J2ME Loader's Portuguese "a% de" for the English %s).
        for source, target in (("%d off", "50 % de remise"), ("%d off", "Remise % de"),
                               ("%d files", "%d Dateien, % d neu"),
                               ("Please check storage device %savailability",
                                "Verifique a% de disponibilidade")):
            problems = g.check_java_format(source, target)
            self.assertIn(("java-format", g.ERROR), levels(problems), (source, target))

    def test_unnumbered_reorder(self):
        problems = g.check_java_format("Copying %d files to %s", "Nach %s: %d Dateien")
        self.assertEqual(levels(problems), [("java-format", g.ERROR)])
        self.assertIn("new order", problems[0]["message"])
        self.assertIn("%2$s ... %1$d", problems[0]["message"])
        three = g.check_java_format("%s: %d of %s", "%d / %s (%s)")
        self.assertEqual(levels(three), [("java-format", g.ERROR)])
        self.assertIn("%2$d ... %1$s ... %3$s", three[0]["message"])

    def test_swapped_numbers(self):
        problems = g.check_java_format("And %1$d others reacted with %2$s",
                                       "%1$s and %2$d others")
        self.assertEqual(levels(problems), [("java-format", g.ERROR)])
        self.assertIn("look swapped", problems[0]["message"])

    def test_moved_percent(self):
        problems = g.check_java_format("%1$d files", "1%d Dateien")
        self.assertEqual(levels(problems), [("java-format", g.ERROR)])
        self.assertIn('"1%d" looks like %1$d', problems[0]["message"])

    def test_correct_translations_pass(self):
        for source, target in (("Copying %d files to %s", "Kopiere %d Dateien nach %s"),
                               ("%1$s of %2$d", "%2$d de %1$s"),
                               ("And %1$d others reacted with %2$s", "%2$s : %1$d autres"),
                               ("%d%% done", "%d%% fertig"),
                               ("%1$d%% done", "%1$d %% fait"),
                               ("% d items", "% d Elemente"),
                               ("%s and %s", "%s et %s"),
                               ("50% off", "50 % de remise"),
                               ("Day %1$d", "Tag %1$d, 2%%")):
            self.assertEqual(g.check_java_format(source, target), [], (source, target))

    def test_single_type_change_is_still_a_warning(self):
        problems = g.check_java_format("Hello %s", "Hallo %d")
        self.assertEqual(levels(problems), [("java-format-type", g.WARNING)])

    def test_android_plural_reorder(self):
        en = ('<resources><plurals name="copy"><item quantity="one">Copying %d APK to %s</item>'
              '<item quantity="other">Copying %d APKs to %s</item></plurals></resources>')
        ur = ('<resources><plurals name="copy"><item quantity="other">%s میں %d APK کاپی ہو رہی ہیں'
              '</item></plurals></resources>')
        java = [p for p in g.check_android(en, ur) if p["code"] == "java-format"]
        self.assertEqual([p["key"] for p in java], ["copy[other]"])
        self.assertIn("%2$s ... %1$d", java[0]["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
