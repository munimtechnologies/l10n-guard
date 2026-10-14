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
GOOD_DE_HTML = ('<html lang="de"><body><p>Führen Sie <code>ollama serve</code> auf Port 11434 aus.</p>'
                '<pre>docker run -p 127.0.0.1:11434:11434 ollama/ollama</pre>'
                '<a href="https://buy.stripe.com/x">Zahlen</a> <a href="../other.html">Mehr</a>'
                '</body></html>')


def _alternates(*langs):
    return "".join('<link rel="alternate" hreflang="%s" href="https://example.org/%s/a.html">'
                   % (lang, lang) for lang in langs)


class Documents(unittest.TestCase):
    def test_good_html(self):
        self.assertEqual(g.check_document(SRC_HTML, GOOD_DE_HTML), [])

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

    def test_hreflang_cluster(self):
        head = "<html lang=\"%s\"><head>%s</head>"
        src = head % ("en", _alternates("en", "de", "ja")) + SRC_HTML[16:]
        same = head % ("de", _alternates("ja", "de", "en")) + GOOD_DE_HTML[16:]
        self.assertEqual(g.check_document(src, same), [])
        short = head % ("de", _alternates("en", "de")) + GOOD_DE_HTML[16:]
        problems = g.check_document(src, short)
        self.assertEqual([(p["code"], p["level"]) for p in problems], [("hreflang", g.WARNING)])
        self.assertIn("missing ja", problems[0]["message"])

    def test_expected_lang(self):
        self.assertEqual(g.check_document(SRC_HTML, GOOD_DE_HTML, "html", "de"), [])
        pt = GOOD_DE_HTML.replace('lang="de"', 'lang="pt-BR"')
        self.assertEqual(g.check_document(SRC_HTML, pt, "html", "pt_br"), [])
        problems = g.check_document(SRC_HTML, GOOD_DE_HTML, "html", "fr")
        self.assertEqual([(p["code"], p["level"]) for p in problems], [("lang", g.WARNING)])


def _write(folder, name, text):
    path = os.path.join(folder, *name.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class Folders(unittest.TestCase):
    def _site(self, d):
        _write(d, "site/guide.html", SRC_HTML)
        _write(d, "site/locales/app.json", json.dumps({"hi": "Hi {{name}}"}))
        _write(d, "site/de/guide.html", GOOD_DE_HTML.replace('lang="de"', 'lang="fr"'))
        _write(d, "site/de/locales/app.json", json.dumps({"hi": "Hallo"}))
        _write(d, "site/de/extra.html", GOOD_DE_HTML)
        _write(d, "site/de/notes.txt", "not checked")
        return os.path.join(d, "site"), os.path.join(d, "site", "de")

    def test_check_dir(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = self._site(d)
            problems, stats = g.check_dir(source, target)
        self.assertEqual(stats, {"checked": 2, "unmatched": 1})
        found = sorted((p["code"], p["level"], p["key"]) for p in problems)
        self.assertEqual(found, [("lang", g.WARNING, "guide.html"),
                                 ("no-source", g.WARNING, "extra.html"),
                                 ("placeholder-missing", g.ERROR, "locales/app.json hi")])

    def test_cli_dir(self):
        with tempfile.TemporaryDirectory() as d:
            source, target = self._site(d)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["dir", source, target]), 1)
            self.assertIn("2 file(s) checked, 1 without a source file", out.getvalue())
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(g.run(["dir", source, os.path.join(d, "missing")]), 2)


EXAMPLES = os.path.join(HERE, "examples")


@unittest.skipUnless(os.path.isdir(EXAMPLES), "examples not present")
class RealTranslations(unittest.TestCase):
    """Translations of munimv2.github.io pages (examples/<page>/<lang>.html) keep
    every command, code block and external link, both payment links included."""

    def test_no_errors(self):
        checked = 0
        for page in sorted(os.listdir(EXAMPLES)):
            folder = os.path.join(EXAMPLES, page)
            source = os.path.join(folder, "en.html")
            if not os.path.isfile(source):
                continue
            src = g._read(source)
            for name in sorted(os.listdir(folder)):
                if name == "en.html" or not name.endswith(".html"):
                    continue
                lang = name[:-len(".html")]
                problems = g.check_document(src, g._read(os.path.join(folder, name)), "html", lang)
                errors = [p for p in problems if p["level"] == g.ERROR]
                self.assertEqual(errors, [], "%s/%s" % (page, name))
                checked += 1
        self.assertGreater(checked, 0)


class Cli(unittest.TestCase):
    def test_json_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "en.json", json.dumps({"hi": "Hi {{name}}"}))
            ok = _write(d, "de.json", json.dumps({"hi": "Hallo {{name}}"}))
            bad = _write(d, "fr.json", json.dumps({"hi": "Salut"}))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["json", src, ok]), 0)
                self.assertEqual(g.run(["json", src, bad]), 1)
            self.assertIn("placeholder-missing", out.getvalue())

    def test_po_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "pl.po", PO)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["--json", "po", path]), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(report["stats"]["fuzzy"], 1)
            self.assertEqual(report["errors"], 3)

    def test_bad_input(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "en.json", "{not json")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(g.run(["json", src, src]), 2)


if __name__ == "__main__":
    unittest.main()
