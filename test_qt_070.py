#!/usr/bin/env python3
"""l10n-guard 0.7.0: Qt Linguist .ts files. QString::arg() place markers
(%1, %L2) checked by what arg() would show, and the count (%n) of plural
messages written with a percent sign Qt does not read (٪n, ％n) or a space.
Standard library only.

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


def ts(messages, language="ar"):
    """A .ts file. messages: (context, source, translation) where translation
    is a string, a list of plural forms, or None; an optional 4th item is the
    translation's type attribute."""
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<!DOCTYPE TS>",
           '<TS version="2.1" language="%s">' % language]
    for item in messages:
        context, source, translation = item[:3]
        kind = ' type="%s"' % item[3] if len(item) > 3 else ""
        numerus = ' numerus="yes"' if isinstance(translation, list) else ""
        out.append("<context><name>%s</name><message%s><source>%s</source>" % (context, numerus, source))
        if translation is None:
            out.append('<translation type="unfinished"></translation>')
        elif isinstance(translation, list):
            out.append("<translation%s>%s</translation>" % (
                kind, "".join("<numerusform>%s</numerusform>" % f for f in translation)))
        else:
            out.append("<translation%s>%s</translation>" % (kind, translation))
        out.append("</message></context>")
    out.append("</TS>")
    return "\n".join(out)


def codes(problems):
    return [(p["code"], p["level"]) for p in problems]


class Qt070Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 7, 0))

    def test_parse(self):
        text = ts([("Intro", "(of %n GB needed)", ["a %n", "b %n"]),
                   ("Main", "Open", "فتح"),
                   ("Main", "Old", "قديم", "vanished"),
                   ("Main", "New", None),
                   ("Main", "Draft", "مسودة", "unfinished")])
        msgs = g.parse_qt_ts(text)
        self.assertEqual([(m["context"], m["numerus"], m["state"]) for m in msgs],
                         [("Intro", True, "finished"), ("Main", False, "finished"), ("Main", False, "obsolete"),
                          ("Main", False, "untranslated"), ("Main", False, "unfinished")])
        self.assertEqual(msgs[0]["forms"], ["a %n", "b %n"])

    def test_length_variants(self):
        text = ('<TS version="2.1" language="de"><context><name>C</name><message><source>%1 files</source>'
                '<translation variants="yes"><lengthvariant>%1 Dateien</lengthvariant>'
                '<lengthvariant>%2</lengthvariant></translation></message></context></TS>')
        self.assertEqual(g.parse_qt_ts(text)[0]["forms"], ["%1 Dateien", "%2"])
        problems, _ = g.check_qt(text)
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])

    def test_not_ts(self):
        with self.assertRaises(ValueError):
            g.parse_qt_ts("<xliff/>")

    def test_arabic_percent_count(self):
        # Bitcoin Core's Arabic file writes every form of "%n day(s)" as ٪n.
        problems, stats = g.check_qt(ts([("QObject", "%n day(s)", ["٪n يوم"] * 6)]))
        self.assertEqual(codes(problems), [("qt-count", g.ERROR)] * 6)
        self.assertIn("form 1: '٪n' is not %n", problems[0]["message"])
        self.assertIn("ASCII %n or %Ln", problems[0]["message"])
        self.assertEqual(problems[0]["key"], "QObject: %n day(s)")
        self.assertEqual(stats["finished"], 1)

    def test_fullwidth_percent_count(self):
        problems, _ = g.check_qt(ts([("Intro", "(%n GB needed for full chain)", ["（完整區塊鏈需要％n GB）"])],
                                    "zh_TW"))
        self.assertEqual(codes(problems), [("qt-count", g.ERROR)])
        self.assertIn("'％n'", problems[0]["message"])

    def test_some_forms_fake(self):
        # KeePassXC's Arabic file: forms 1-5 use ٪n, form 6 an ASCII %n.
        forms = ["[%d ٪n]" % i for i in range(5)] + ["[%n]"]
        problems, _ = g.check_qt(ts([("CsvImportWidget", "[%n more message(s) skipped]", forms)]))
        self.assertEqual(codes(problems), [("qt-count", g.ERROR)] * 5)
        self.assertEqual([p["message"].split(":")[0] for p in problems], ["form %d" % i for i in range(1, 6)])

    def test_spaced_and_small_percent(self):
        for form, fake in (("٪ n عام", "٪ n"), ("% n Tage", "% n"), ("﹪n 個", "﹪n"), ("٪Ln ملف", "٪Ln")):
            problems, _ = g.check_qt(ts([("C", "%n file(s)", [form])]))
            self.assertEqual(codes(problems), [("qt-count", g.ERROR)], form)
            self.assertIn("'%s'" % fake, problems[0]["message"])

    def test_marker_for_count(self):
        # KeePassXC's Finnish "Purged %n icon(s)" (found by miguelaguiar01/corpus #1102).
        problems, _ = g.check_qt(ts([("C", "Purged %n icon(s)", ["Poistettu %1 kuvake", "Poistettu %1 kuvaketta"])],
                                    "fi"))
        self.assertEqual(codes(problems), [("qt-count", g.ERROR)] * 2)
        self.assertIn("'%1' is not %n; the source has no place marker", problems[0]["message"])
        for forms in (["%n dosya, %50"], ["%n Dateien in %1"], ["%50 indirim", "%n dosya"]):
            problems, _ = g.check_qt(ts([("C", "%n file(s)", forms)], "tr"))
            self.assertEqual([p for p in problems if p["code"] == "qt-count"], [], forms)

    def test_real_count_and_prose(self):
        for forms in (["%n Datei", "%n Dateien"], ["%Ln Dateien"], ["eine Datei", "%n Dateien"],
                      ["50% netto, %n Dateien"]):
            problems, _ = g.check_qt(ts([("C", "%n file(s)", forms)], "de"))
            self.assertEqual(problems, [], forms)

    def test_count_never_shown(self):
        problems, _ = g.check_qt(ts([("C", "%n note(s)", ["メモ"])], "ja"))
        self.assertEqual(codes(problems), [("qt-count-missing", g.WARNING)])
        problems, _ = g.check_qt(ts([("C", "File(s)", ["ملف"] * 6)]))
        self.assertEqual(problems, [])

    def test_arg_same_numbers_any_order(self):
        for target in ("%1 / %2", "%2 の %1", "%L1 / %2", "%1 %50 tamam %2"):
            self.assertEqual(g.check_qt(ts([("C", "%1 of %2", target)], "ja"))[0], [], target)

    def test_arg_renumbered(self):
        problems, _ = g.check_qt(ts([("C", "%1 of %2", "%2 の %3")], "ja"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])
        message = problems[0]["message"]
        self.assertIn("lowest-numbered marker first", message)
        self.assertIn("%2 shows the value of the source's %1", message)
        self.assertIn("%3 shows the value of the source's %2", message)

    def test_arg_left_as_text(self):
        problems, _ = g.check_qt(ts([("C", "%1 and %2", "%0 %1 %2")], "de"))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR)])
        self.assertIn("%2 is left as text", problems[0]["message"])
        self.assertIn("%0 shows the value of the source's %1", problems[0]["message"])

    def test_arg_dropped(self):
        problems, _ = g.check_qt(ts([("C", "%1 of %2", "%1")], "de"))
        self.assertEqual(codes(problems), [("qt-arg-missing", g.ERROR)])
        self.assertIn("source's %2 is never shown", problems[0]["message"])

    def test_arg_hints(self):
        cases = (("تم نسخ ٪1 ملفات", "percent sign Qt does not read"),
                 ("% 1 filer kopieret", "a space after the %"),
                 ("1% kopyalandı", "the % after the number"),
                 ("%১ ফাইল", "Qt 6.6"))
        for target, hint in cases:
            problems, _ = g.check_qt(ts([("C", "Copied %1 files", target)]))
            self.assertEqual(codes(problems), [("qt-arg-missing", g.ERROR)], target)
            self.assertIn(hint, problems[0]["message"], target)

    def test_hint_goes_to_missing(self):
        problems, _ = g.check_qt(ts([("C", "%1 of %2", "٪1 من %2")]))
        self.assertEqual(codes(problems), [("qt-arg-order", g.ERROR), ("qt-arg-missing", g.ERROR)])
        self.assertNotIn("looks like", problems[0]["message"])
        self.assertIn("'٪1' looks like %1", problems[1]["message"])

    def test_numerus_args(self):
        problems, _ = g.check_qt(ts([("C", "%n file(s) in %1", ["%n Datei in %1", "%n Dateien"])], "de"))
        self.assertEqual(codes(problems), [("qt-arg-missing", g.ERROR)])
        self.assertEqual(problems[0]["key"], "C: %n file(s) in %1 (form 2)")

    def test_unfinished_warns_obsolete_skipped(self):
        problems, stats = g.check_qt(ts([("C", "%n day(s)", ["٪n يوم"], "unfinished"),
                                         ("C", "%1 of %2", "%1", "obsolete"),
                                         ("C", "Copied %1", None)]))
        self.assertEqual(codes(problems), [("qt-count", g.WARNING)])
        self.assertEqual(stats, {"messages": 3, "finished": 0, "unfinished": 1, "untranslated": 1,
                                 "obsolete": 1})

    def test_long_key(self):
        source = "Successfully removed permissions from %n entry(s) of the database."
        problems, _ = g.check_qt(ts([("Browser", source, ["٪n"])]))
        self.assertEqual(problems[0]["key"], "Browser: " + source[:47] + "...")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "app_ar.ts")
            good = os.path.join(d, "app_de.ts")
            notts = os.path.join(d, "x.ts")
            for path, text in ((bad, ts([("QObject", "%n day(s)", ["٪n يوم"] * 6)])),
                               (good, ts([("QObject", "%n day(s)", ["%n Tag", "%n Tage"])], "de")),
                               (notts, "export const x = 1;\n")):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["qt", bad]), 1)
                self.assertEqual(g.run(["qt", good]), 0)
            self.assertIn("ERROR qt-count [QObject: %n day(s)]", out.getvalue())
            self.assertIn("1 messages, 1 finished", out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["--json", "qt", bad]), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(report["errors"], 6)
            self.assertEqual(report["stats"]["messages"], 1)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(g.run(["qt", notts]), 2)


if __name__ == "__main__":
    unittest.main()
