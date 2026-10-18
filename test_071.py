#!/usr/bin/env python3
"""l10n-guard 0.7.1: Qt markers that are only renumbered are a warning
(qt-arg-renumbered), and placeholders written with a look-alike percent sign
(٪s, ％d) are named (lookalike-percent). The Qt cases are rows of the qt-args
census and the Android ones strings of the lookalike-percent findings
(2026-10-17). Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import contextlib
import io
import os
import tempfile
import unittest

import l10n_guard as g
from test_qt_070 import codes, ts


class Qt071Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 7, 1))

    def test_renumbered_is_warning(self):
        cases = (("to %1", "nach %2"),  # Deepin dde-file-manager, de
                 ("Rejecting failed torrent file: %1", "Mislukt torrentbestand verwerpen: %11"),  # qBittorrent, nl
                 ("Search plugin '%1' contains invalid version string ('%2')",
                  "Meklētāja spraudnis '%1' satur nederīgus datus par versiju ('%22')"),  # qBittorrent, lv
                 ("End of %1", "%2:n loppuun"))  # MuseScore, fi
        for source, target in cases:
            problems, _ = g.check_qt(ts([("C", source, target)], "de"))
            self.assertEqual(codes(problems), [("qt-arg-renumbered", g.WARNING)], target)
            self.assertIn("still lands where the translator put it", problems[0]["message"])
        problems, _ = g.check_qt(ts([("C", "to %1", "nach %2")], "de"))
        self.assertIn("%2 shows the value of the source's %1", problems[0]["message"])

    def test_renumbered_keeps_hint(self):
        # Subsurface, nb: the stray "1" before %11 is still shown ("Fant 15" for 5 files).
        problems, _ = g.check_qt(ts([("C", "Found %1 media files at new locations:",
                                      "Fant 1%11 mediefiler på nytt sted:")], "nb"))
        self.assertEqual(codes(problems), [("qt-arg-renumbered", g.WARNING)])
        self.assertIn("'1%' looks like %1", problems[0]["message"])

    def test_real_moves_stay_errors(self):
        # LibreCAD, tr: %3 written %34 moves every later value.
        problems, _ = g.check_qt(ts([("C", "A %1 B %2 C %3 D %4", "A %1 B %2 C %34 D %4")], "tr"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])
        self.assertIn("%4 shows the value of the source's %3", problems[0]["message"])
        # LibreCAD, gl: %0 takes the first value.
        problems, _ = g.check_qt(ts([("C", "A %1 B %2", "A %0 B %1")], "gl"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])
        # LibreCAD, he: one marker renumbered and the second value lost.
        problems, _ = g.check_qt(ts([("C", "Area: %1 %2^2", "שטח: %12")], "he"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR), ("qt-arg-missing", g.ERROR)])
        problems, _ = g.check_qt(ts([("C", "%1 of %2", "%2 の %3")], "ja"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])

    def test_marker_beyond_the_values_not_reported(self):
        # Every value lands where the source puts it and %5 gets none, so it
        # is shown as written, like Turkish "%50" (50 percent): not reported,
        # as in 0.7.0 (test_arg_same_numbers_any_order).
        problems, _ = g.check_qt(ts([("C", "Copied %1", "%1 kopiert %5")], "de"))
        self.assertEqual(problems, [])

    def test_renumbered_unfinished_and_cli(self):
        problems, _ = g.check_qt(ts([("C", "to %1", "nach %2", "unfinished")], "de"))
        self.assertEqual(codes(problems), [("qt-arg-renumbered", g.WARNING)])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "app_de.ts")
            with open(path, "w", encoding="utf-8") as f:
                f.write(ts([("C", "to %1", "nach %2")], "de"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["qt", path]), 0)
                self.assertEqual(g.run(["--strict", "qt", path]), 1)
            self.assertIn("WARNING qt-arg-renumbered [C: to %1]", out.getvalue())


class Lookalike071Test(unittest.TestCase):
    def test_lost_value(self):
        problems = g.check_pair("%s files", "٪s ملفات", "k")
        self.assertEqual(codes(problems), [("lookalike-percent", g.ERROR)])
        self.assertIn('%s is written "٪s"', problems[0]["message"])
        self.assertIn("U+066A", problems[0]["message"])

    def test_upper_case_and_space(self):
        # Windscribe, fa: ping_time writes %d as ٪D.
        for source, target, seen in (("%d ms", "پینگ ٪D", "٪D"), ("%1$s", "٪ 1$s", "٪ 1$s")):
            problems = g.check_pair(source, target)
            self.assertEqual(codes(problems), [("lookalike-percent", g.ERROR)], target)
            self.assertIn('"%s"' % seen, problems[0]["message"])

    def test_fullwidth_two_values(self):
        problems = g.check_pair("Delete %1$s from %2$s?", "从％2$s删除％1$s？")
        self.assertEqual(codes(problems), [("lookalike-percent", g.ERROR)] * 2)
        self.assertIn("U+FF05", problems[0]["message"])
        self.assertIn('%1$s is written "％1$s"', problems[0]["message"])
        self.assertIn('%2$s is written "％2$s"', problems[1]["message"])

    def test_mixed_is_warning(self):
        # EventFahrplan, ja: a stray ％s before the real %s.
        problems = g.check_pair("Parsing error for schedule version %s", "スケジュール％sの解析エラー（バージョン %s）")
        self.assertEqual(codes(problems), [("lookalike-percent", g.WARNING)])
        self.assertIn("ASCII %s", problems[0]["message"])

    def test_other_missing_still_reported(self):
        problems = g.check_pair("%1$s %2$s", "٪1$s")
        self.assertEqual(codes(problems), [("lookalike-percent", g.ERROR), ("placeholder-missing", g.ERROR)])
        self.assertIn("%2$s", problems[1]["message"])
        self.assertNotIn("%1$s", problems[1]["message"])

    def test_percent_signs_in_prose(self):
        for source, target in (("50% off", "خصم ٪50"), ("%d%% done", "٪%d تم"), ("{count} files", "٪{count}"),
                               ("%s files", "%s ملفات ٪")):
            self.assertEqual(g.check_pair(source, target), [], target)

    def test_android_plural_one_stays_error(self):
        # Threema zh-rCN and TrackerControl ja-rJP write the count of a plural as ％d.
        source = ('<resources><plurals name="files"><item quantity="one">%d file</item>'
                  '<item quantity="other">%d files</item></plurals></resources>')
        target = ('<resources><plurals name="files"><item quantity="one">٪d ملف</item>'
                  '<item quantity="other">%d ملفات</item></plurals></resources>')
        problems = g.check_android(source, target)
        self.assertEqual([(p["code"], p["level"], p["key"]) for p in problems],
                         [("lookalike-percent", g.ERROR, "files[one]")])


if __name__ == "__main__":
    unittest.main()
