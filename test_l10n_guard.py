import contextlib
import io
import json
import os
import tempfile
import unittest
from collections import Counter

import l10n_guard as g

HERE = os.path.dirname(os.path.abspath(__file__))


def codes(problems, level=None):
    return {p["code"] for p in problems if level is None or p["level"] == level}


class Placeholders(unittest.TestCase):
    def test_common_styles(self):
        found = g.placeholders("Hello {{name}}, you have %d items and %(count)s files")
        self.assertEqual(found, Counter({"{{name}}": 1, "%d": 1, "%(count)s": 1}))

    def test_positional_and_template(self):
        found = g.placeholders("%1$s sent ${total} to %2$s")
        self.assertEqual(found, Counter({"%1$s": 1, "%2$s": 1, "${total}": 1}))

    def test_icu_counts_argument_not_branches(self):
        src = "{count, plural, one {# file} other {# files}}"
        self.assertEqual(g.placeholders(src), Counter({"{count}": 1}))
        de = "{count, plural, one {# Datei} other {# Dateien}}"
        self.assertEqual(g.check_pair(src, de), [])

    def test_percent_prose_is_not_a_placeholder(self):
        self.assertEqual(g.placeholders("50 % de remise"), Counter())
        self.assertEqual(g.placeholders("100%% done %s"), Counter({"%s": 1}))

    def test_missing_placeholder_is_error(self):
        problems = g.check_pair("Hello {name}", "Hallo")
        self.assertEqual(codes(problems, g.ERROR), {"placeholder-missing"})

    def test_renamed_placeholder(self):
        problems = g.check_pair("Hello %(name)s", "Cześć %(imie)s")
        self.assertEqual(codes(problems, g.ERROR), {"placeholder-missing", "placeholder-extra"})

    def test_broken_tag_is_error(self):
        problems = g.check_pair("Click <b>here</b>", "Klicken Sie <b>hier")
        self.assertEqual(codes(problems, g.ERROR), {"tags"})

    def test_trans_slots(self):
        problems = g.check_pair("Read <0>the docs</0>", "Lies <0>die Doku")
        self.assertEqual(codes(problems, g.ERROR), {"tags"})

    def test_identical_is_warning(self):
        problems = g.check_pair("Settings saved", "Settings saved")
        self.assertEqual(codes(problems, g.WARNING), {"untranslated"})
        self.assertEqual(codes(problems, g.ERROR), set())


class Catalogs(unittest.TestCase):
    def test_japanese_plurals_and_missing_key(self):
        src = {"greeting": "Hello {{name}}", "items_one": "{{count}} item",
               "items_other": "{{count}} items", "nested": {"title": "Settings"}}
        tgt = {"greeting": "こんにちは {{name}}", "items_other": "{{count}} 件", "nested": {}}
        problems = g.check_catalog(src, tgt)
        self.assertEqual([(p["code"], p["key"], p["level"]) for p in problems],
                         [("missing-key", "nested.title", g.WARNING)])

    def test_polish_extra_plural_forms_checked_against_other(self):
        src = {"files_one": "{{count}} file", "files_other": "{{count}} files"}
        tgt = {"files_one": "{{count}} plik", "files_few": "{{count}} pliki",
               "files_many": "{{count}} plików", "files_other": "{{count}} pliku"}
        self.assertEqual(g.check_catalog(src, tgt), [])
        tgt["files_few"] = "pliki"
        problems = g.check_catalog(src, tgt)
        self.assertEqual([(p["code"], p["key"]) for p in problems],
                         [("placeholder-missing", "files_few")])

    def test_type_change(self):
        problems = g.check_catalog({"n": 3}, {"n": "3"})
        self.assertEqual(codes(problems, g.ERROR), {"type"})

    def test_extra_key_warning(self):
        problems = g.check_catalog({"a": "Yes"}, {"a": "Ja", "b": "Nein"})
        self.assertEqual([(p["code"], p["key"]) for p in problems], [("extra-key", "b")])


PO = r'''msgid ""
msgstr ""
"Language: pl\n"
"Plural-Forms: nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);\n"

#: app.py:10
#, python-format
msgid "Hello %(name)s"
msgstr "Cześć %(imie)s"

msgid "One file"
msgid_plural "%d files"
msgstr[0] "Jeden plik"
msgstr[1] "%d pliki"

#, fuzzy
msgid "Save"
msgstr "Zapisz"

msgctxt "menu"
msgid "Open"
msgstr ""

msgid ""
"A long "
"line"
msgstr ""
"Długa "
"linia"

#~ msgid "Old"
#~ msgstr "Stary"
'''


class Gettext(unittest.TestCase):
    def test_parse(self):
        entries = g.parse_po(PO)
        self.assertEqual(len(entries), 7)
        self.assertIn("nplurals=3", entries[0]["msgstr"])
        self.assertEqual(entries[1]["flags"], {"python-format"})
        self.assertEqual(entries[2]["msgstr_plural"], {0: "Jeden plik", 1: "%d pliki"})
        self.assertEqual(entries[4]["msgctxt"], "menu")
        self.assertEqual(entries[5]["msgid"], "A long line")
        self.assertEqual(entries[5]["msgstr"], "Długa linia")
        self.assertTrue(entries[6]["obsolete"])

    def test_check(self):
        problems, stats = g.check_po(PO)
        self.assertEqual(codes(problems, g.ERROR),
                         {"placeholder-missing", "placeholder-extra", "plural-count"})
        self.assertEqual(stats, {"entries": 5, "translated": 3, "fuzzy": 1, "untranslated": 1})

    def test_single_plural_form_language(self):
        po = ('msgid ""\nmsgstr "Plural-Forms: nplurals=1; plural=0;\\n"\n\n'
              'msgid "One file"\nmsgid_plural "%d files"\nmsgstr[0] "%d 個のファイル"\n')
        problems, stats = g.check_po(po)
        self.assertEqual(problems, [])
        self.assertEqual(stats["translated"], 1)


SRC_HTML = ('<html lang="en"><body><p>Run <code>ollama serve</code> on port 11434.</p>'
            '<pre>docker run -p 127.0.0.1:11434:11434 ollama/ollama</pre>'
            '<a href="https://buy.stripe.com/x">Pay</a> <a href="other.html">More</a></body></html>')


class Documents(unittest.TestCase):
    def test_good_html(self):
        tgt = ('<html lang="de"><body><p>Führen Sie <code>ollama serve</code> auf Port 11434 aus.</p>'
               '<pre>docker run -p 127.0.0.1:11434:11434 ollama/ollama</pre>'
               '<a href="https://buy.stripe.com/x">Zahlen</a> <a href="../other.html">Mehr</a>'
               '</body></html>')
        self.assertEqual(g.check_document(SRC_HTML, tgt), [])

    def test_bad_html(self):
        tgt = ('<html lang="en"><body><p>Führen Sie <code>ollama dienen</code> aus.</p>'
               '<pre>docker run -p 11434:11434 ollama/ollama</pre>'
               '<a href="https://buy.stripe.com/y">Zahlen</a></body></html>')
        problems = g.check_document(SRC_HTML, tgt)
        self.assertEqual(codes(problems, g.ERROR),
                         {"code-block-changed", "inline-code-missing", "link-missing"})
        self.assertTrue({"lang", "inline-code-extra", "link-extra", "numbers"}
                        <= codes(problems, g.WARNING))

    def test_markdown(self):
        src = "Run `npm i`.\n\n```sh\nnpm test\n```\n[docs](https://x.org/docs)\n"
        good = "Führe `npm i` aus.\n\n```sh\nnpm test\n```\n[Doku](https://x.org/docs)\n"
        self.assertEqual(g.check_document(src, good, "md"), [])
        bad = "Führe `npm install` aus.\n\n```sh\nnpm tests\n```\n"
        self.assertEqual(codes(g.check_document(src, bad, "md"), g.ERROR),
                         {"code-block-changed", "inline-code-missing", "link-missing"})


EXAMPLES = os.path.join(HERE, "examples", "secure-ollama")


@unittest.skipUnless(os.path.exists(os.path.join(EXAMPLES, "en.html")), "examples not present")
class RealTranslations(unittest.TestCase):
    """The five translations of munimv2.github.io/secure-ollama.html keep every
    command, code block and external link (including both payment links)."""

    def test_no_errors(self):
        with open(os.path.join(EXAMPLES, "en.html"), encoding="utf-8") as f:
            src = f.read()
        checked = 0
        for lang in ("de", "es", "fr", "ja", "pt-br"):
            path = os.path.join(EXAMPLES, lang + ".html")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                problems = g.check_document(src, f.read())
            errors = [p for p in problems if p["level"] == g.ERROR]
            self.assertEqual(errors, [], lang)
            checked += 1
        self.assertGreater(checked, 0)


class Cli(unittest.TestCase):
    def _write(self, folder, name, text):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_json_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._write(d, "en.json", json.dumps({"hi": "Hi {{name}}"}))
            ok = self._write(d, "de.json", json.dumps({"hi": "Hallo {{name}}"}))
            bad = self._write(d, "fr.json", json.dumps({"hi": "Salut"}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["json", src, ok]), 0)
                self.assertEqual(g.run(["json", src, bad]), 1)
            self.assertIn("placeholder-missing", out.getvalue())

    def test_po_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "pl.po", PO)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["--json", "po", path]), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(report["stats"]["fuzzy"], 1)
            self.assertEqual(report["errors"], 3)

    def test_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            src = self._write(d, "en.json", "{not json")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(g.run(["json", src, src]), 2)


if __name__ == "__main__":
    unittest.main()
