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


ANDROID_EN = '''<?xml version="1.0" encoding="utf-8"?>
<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">
    <string name="app_name" translatable="false">Pocket</string>
    <string name="welcome">Hello <xliff:g id="user">%1$s</xliff:g>, you have <b>%2$d</b> new messages</string>
    <string name="saved">Saved</string>
    <plurals name="songs">
        <item quantity="one">%d song</item>
        <item quantity="other">%d songs</item>
    </plurals>
    <string-array name="sizes">
        <item>Small</item>
        <item>Large</item>
    </string-array>
</resources>
'''

ANDROID_FR = '''<?xml version="1.0" encoding="utf-8"?>
<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">
    <string name="welcome">Bonjour <xliff:g id="user">%1$s</xliff:g>, vous avez <b>%2$d</b> nouveaux messages</string>
    <string name="saved">Enregistré dans l'application</string>
    <plurals name="songs">
        <item quantity="one">Une chanson</item>
        <item quantity="many">%d de chansons</item>
        <item quantity="other">%d chansons</item>
    </plurals>
    <string-array name="sizes">
        <item>Petit</item>
    </string-array>
    <string name="legacy">Ancien</string>
</resources>
'''

ANDROID_JAVA_EN = '''<resources>
    <string name="done">%1$d%% done</string>
    <string name="raw" formatted="false">%s and %d</string>
    <string name="who">Shared by %1$s</string>
    <plurals name="left"><item quantity="one">One left</item><item quantity="other">%d left</item></plurals>
</resources>
'''

ANDROID_JAVA_FR = '''<resources>
    <string name="done">%1$d % terminé</string>
    <string name="raw">%s et %</string>
    <string name="who">Partagé par %2$s</string>
    <plurals name="left"><item quantity="one">Il en reste un</item><item quantity="many">%d restants</item><item quantity="other">%d %restants</item></plurals>
</resources>
'''

# KDE Connect's pattern: the one form shows only the name, but the app passes
# the name, the file number and the total to every quantity.
ANDROID_PLURAL_EN = '''<resources>
    <plurals name="got"><item quantity="one">File from %1$s</item><item quantity="other">%2$d of %3$d files from %1$s</item></plurals>
    <plurals name="n"><item quantity="one">One file</item><item quantity="other">%d files</item></plurals>
</resources>
'''

ANDROID_PLURAL_RU = '''<resources>
    <plurals name="got"><item quantity="one">Файл %2$d из %3$d от %1$s</item><item quantity="few">%2$d из %4$d файлов от %1$s</item><item quantity="other">%2$d из %3$d файлов от %1$s</item></plurals>
    <plurals name="n"><item quantity="one">Один файл, 100%</item><item quantity="other">%d файлов</item></plurals>
</resources>
'''


class Android(unittest.TestCase):
    def test_parse(self):
        strings = g.parse_android(ANDROID_EN)
        self.assertNotIn("app_name", strings)
        self.assertEqual(strings["welcome"],
                         "Hello <g>%1$s</g>, you have <b>%2$d</b> new messages")
        self.assertEqual(strings["songs[other]"], "%d songs")
        self.assertEqual(strings["sizes[1]"], "Large")

    def test_check(self):
        problems = g.check_android(ANDROID_EN, ANDROID_FR)
        self.assertEqual(sorted((p["code"], p["level"], p["key"]) for p in problems),
                         [("android-apostrophe", g.ERROR, "saved"),
                          ("extra-key", g.WARNING, "legacy"),
                          ("missing-key", g.WARNING, "sizes[1]"),
                          ("placeholder-missing", g.WARNING, "songs[one]")])

    def test_apostrophes(self):
        self.assertTrue(g._android_apostrophe("dans l'application"))
        self.assertFalse(g._android_apostrophe("dans l\\'application"))
        self.assertFalse(g._android_apostrophe('"dans l\'application"'))
        self.assertFalse(g._android_apostrophe("dans l’application"))

    def test_japanese_other_only(self):
        ja = ANDROID_EN.replace('<item quantity="one">%d song</item>', "")
        ja = ja.replace('translatable="false">Pocket', 'translatable="false">ポケット')
        problems = g.check_android(ANDROID_EN, ja)
        self.assertNotIn("missing-key", codes(problems))

    def test_java_format_crashes(self):
        self.assertEqual(g.android_unformatted(ANDROID_JAVA_EN), {"raw"})
        problems = g.check_android(ANDROID_JAVA_EN, ANDROID_JAVA_FR)
        self.assertEqual(sorted((p["code"], p["key"]) for p in problems),
                         [("java-format", "done"), ("java-format", "left[other]"),
                          ("java-format", "who"), ("placeholder-extra", "who"),
                          ("placeholder-missing", "raw"), ("placeholder-missing", "who")])

    def test_plural_forms_share_arguments(self):
        src = g.parse_android(ANDROID_PLURAL_EN)
        self.assertEqual(g._plural_format_source(src, "got"), "%2$d of %3$d files from %1$s")
        self.assertEqual(g._plural_format_source(src, "n"), "%d files")
        problems = g.check_android(ANDROID_PLURAL_EN, ANDROID_PLURAL_RU)
        errors = sorted((p["code"], p["key"]) for p in problems if p["level"] == g.ERROR)
        # got[one] may use %2$d and %3$d: the other form shows the app passes them.
        # got[few] uses a fourth argument nobody passes; n[one] has a stray %.
        self.assertEqual(errors, [("java-format", "got[few]"), ("java-format", "n[one]"),
                                  ("placeholder-extra", "got[few]"),
                                  ("placeholder-missing", "got[few]")])
        few = [p for p in problems if p["code"] == "java-format" and p["key"] == "got[few]"][0]
        self.assertIn("uses argument 4 but the source passes 3", few["message"])


class JavaFormat(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(g.java_format("%1$s has %2$d files, %3$.1f%% full"),
                         [(1, "any"), (2, "int"), (3, "float")])
        self.assertEqual(g.java_format("%s and %s, again %<s"),
                         [(1, "any"), (2, "any"), (2, "any")])
        self.assertEqual(g.java_format("%,d km at %tH:%tM%n"),
                         [(1, "int"), (2, "date"), (3, "date")])
        self.assertEqual(g.java_format("100%% done"), [])

    def test_what_java_refuses(self):
        cases = {
            "Téléchargé à 50%": "UnknownFormatConversionException",
            "50%ige Ermäßigung für %1$s": "UnknownFormatConversionException",
            "%1$s ф%ф": "UnknownFormatConversionException",
            "%tq": "UnknownFormatConversionException",
            "100 % sûr, %1$s": "FormatFlagsConversionMismatchException",
            "%1$d % terminé": "FormatFlagsConversionMismatchException",
            "%-d": "MissingFormatWidthException",
            "%.2d": "IllegalFormatPrecisionException",
            "%<s": "MissingFormatArgumentException",
        }
        for text, exception in cases.items():
            with self.assertRaises(g.JavaFormatError, msg=text) as ctx:
                g.java_format(text)
            self.assertEqual(ctx.exception.exception, exception, text)

    def test_formatted_or_prose(self):
        self.assertIsNone(g.java_formatted("50% off"))
        self.assertIsNone(g.java_formatted("Saved"))
        self.assertIsNone(g.java_formatted("Use %USERPROFILE%"))
        self.assertEqual(g.java_formatted("%d%% done"), [(1, "int")])

    def test_check_java_format(self):
        self.assertEqual(g.check_java_format("%d files", "%s fichiers"), [])
        self.assertEqual(g.check_java_format("50% off", "50 % de remise"), [])
        missing = g.check_java_format("%1$s of %2$s", "%1$s de %3$s")
        self.assertEqual([(p["code"], p["level"]) for p in missing], [("java-format", g.ERROR)])
        self.assertIn("MissingFormatArgumentException", missing[0]["message"])
        decimal = g.check_java_format("%.1f MB", "%d Mo")
        self.assertIn("IllegalFormatConversionException", decimal[0]["message"])
        text = g.check_java_format("Hello %s", "Hallo %d")
        self.assertEqual([(p["code"], p["level"]) for p in text], [("java-format-type", g.WARNING)])
        prose = g.check_java_format("%1$d%% done", "%1$d % terminé")
        self.assertIn("FormatFlagsConversionMismatchException", prose[0]["message"])

    def test_android_text(self):
        self.assertEqual(g._android_text("Hello <b>%1$s</b>\\n  next"), "Hello %1$s\n next")
        self.assertEqual(g._android_text('"  two  spaces "'), "  two  spaces ")
        self.assertEqual(g._android_text("l\\'appli \\u00e0 50%\n    de %1$s"),
                         "l'appli à 50% de %1$s")

    def test_surrogate_escapes(self):
        # Emoji written as two \u escapes, as some translation tools export them.
        text = g._android_text("\\uD83D\\uDE00 %1$s")
        self.assertEqual(text, "\U0001F600 %1$s")
        self.assertEqual(text.encode("utf-8"), b"\xf0\x9f\x98\x80 %1$s")
        self.assertEqual(g._android_text("\\uD83D alone"), "\ufffd alone")
        self.assertEqual(g.parse_properties("smile=\\uD83D\\uDE00\n"), {"smile": "\U0001F600"})


XLIFF12 = '''<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="de" datatype="plaintext" original="app">
    <body>
      <trans-unit id="greet">
        <source>Hello <x id="INTERPOLATION" equiv-text="{{ name }}"/>!</source>
        <target state="translated">Hallo <x id="INTERPOLATION" equiv-text="{{ name }}"/>!</target>
      </trans-unit>
      <trans-unit id="link">
        <source>Read <g id="1">the docs</g></source>
        <target>Lies die Doku</target>
      </trans-unit>
      <trans-unit id="count">
        <source>{count} files</source>
        <target>Dateien</target>
      </trans-unit>
      <trans-unit id="todo">
        <source>Delete %s?</source>
        <target state="needs-translation"/>
      </trans-unit>
      <trans-unit id="brand" translate="no">
        <source>ACME</source>
      </trans-unit>
    </body>
  </file>
</xliff>
'''

XLIFF20 = '''<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0" srcLang="en" trgLang="ja">
  <file id="f1">
    <unit id="welcome">
      <segment state="translated">
        <source>Welcome, <pc id="1">%1$s</pc></source>
        <target>ようこそ、<pc id="1">%1$s</pc></target>
      </segment>
    </unit>
    <unit id="two">
      <segment><source>First.</source><target>最初。</target></segment>
      <segment><source>Second <ph id="2"/>.</source><target>二番目。</target></segment>
    </unit>
  </file>
</xliff>
'''


class Xliff(unittest.TestCase):
    def test_xliff_12(self):
        problems, stats = g.check_xliff(XLIFF12)
        self.assertEqual(sorted((p["code"], p["level"], p["key"]) for p in problems),
                         [("inline-codes", g.ERROR, "unit link"),
                          ("placeholder-missing", g.ERROR, "unit count")])
        self.assertEqual(stats, {"units": 4, "translated": 3, "untranslated": 1})

    def test_xliff_20_segments(self):
        problems, stats = g.check_xliff(XLIFF20)
        self.assertEqual([(p["code"], p["key"]) for p in problems],
                         [("inline-codes", "unit two#2")])
        self.assertIn("<ph id=2>", problems[0]["message"])
        self.assertEqual(stats, {"units": 3, "translated": 3, "untranslated": 0})


STRINGS_EN = '''/* Greeting */
"greeting" = "Hello %@, you have %lld messages";
"url" = "See https://example.org/help"; // trailing comment
"quote" = "Say \\"hi\\"";
'''

STRINGS_DE = '''"greeting" = "Hallo %@, du hast Nachrichten";
"url" = "Siehe https://example.org/help";
"quote" = "Sag \\"hallo\\"";
"extra" = "Extra";
'''


class AppleStrings(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(g.parse_strings(STRINGS_EN),
                         {"greeting": "Hello %@, you have %lld messages",
                          "url": "See https://example.org/help",
                          "quote": 'Say \\"hi\\"'})
        with self.assertRaises(ValueError):
            g.parse_strings('"a" = "b"')

    def test_check(self):
        problems = g.check_catalog(g.parse_strings(STRINGS_EN), g.parse_strings(STRINGS_DE))
        self.assertEqual([(p["code"], p["level"], p["key"]) for p in problems],
                         [("placeholder-missing", g.ERROR, "greeting"),
                          ("extra-key", g.WARNING, "extra")])

    def test_cli_reads_utf16(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "en.lproj/Localizable.strings", STRINGS_EN)
            path = os.path.join(d, "de.strings")
            with open(path, "wb") as f:
                f.write(STRINGS_DE.encode("utf-16"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["strings", src, path]), 1)
            self.assertIn("placeholder-missing [greeting]", out.getvalue())


XCSTRINGS = {
    "sourceLanguage": "en",
    "version": "1.0",
    "strings": {
        "Hello %@": {
            "localizations": {
                "de": {"stringUnit": {"state": "translated", "value": "Hallo %@"}},
                "fr": {"stringUnit": {"state": "translated", "value": "Bonjour"}},
            }
        },
        "%lld items": {
            "localizations": {
                "en": {"variations": {"plural": {
                    "one": {"stringUnit": {"state": "translated", "value": "One item"}},
                    "other": {"stringUnit": {"state": "translated", "value": "%lld items"}}}}},
                "de": {"variations": {"plural": {
                    "one": {"stringUnit": {"state": "translated", "value": "Ein Artikel"}},
                    "other": {"stringUnit": {"state": "translated", "value": "Artikel"}}}}},
            }
        },
        "Brand": {"shouldTranslate": False},
    },
}


class StringCatalog(unittest.TestCase):
    def test_check(self):
        problems, stats = g.check_xcstrings(XCSTRINGS)
        self.assertEqual(sorted((p["key"], p["code"], p["level"]) for p in problems),
                         [("%lld items [de plural.other]", "placeholder-missing", g.ERROR),
                          ("Hello %@ [fr]", "placeholder-missing", g.ERROR)])
        self.assertEqual(stats, {"strings": 2, "checked": 4, "untranslated": 1})

    def test_not_a_catalog(self):
        with self.assertRaises(ValueError):
            g.check_xcstrings({"version": "1.0"})


PROPS_EN = r'''# Shown after login
welcome = Welcome back, {0}!
deleted: {0} files were deleted from {1}
multi = First part \
        second part
path=C:\\Users\\{0}
plain Just text
unicode=Caf\u00e9
'''

PROPS_FR = r'''welcome = Bon retour, {0} !
deleted: {0} fichiers ont été supprimés de l'archive {1}
multi = Première partie \
        deuxième partie
path=C:\\Utilisateurs\\{0}
plain C'est du texte
'''


class JavaProperties(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(g.parse_properties(PROPS_EN),
                         {"welcome": "Welcome back, {0}!",
                          "deleted": "{0} files were deleted from {1}",
                          "multi": "First part second part",
                          "path": "C:\\Users\\{0}",
                          "plain": "Just text",
                          "unicode": "Café"})
        self.assertEqual(g.parse_properties("! note\na:b\n  c  =  d e\nlast = x\\"),
                         {"a": "b", "c": "d e", "last": "x"})

    def test_check(self):
        problems = g.check_properties(PROPS_EN, PROPS_FR)
        self.assertEqual(sorted((p["code"], p["level"], p["key"]) for p in problems),
                         [("messageformat-apostrophe", g.ERROR, "deleted"),
                          ("missing-key", g.WARNING, "unicode")])
        fixed = PROPS_FR.replace("l'archive", "l''archive")
        self.assertEqual(codes(g.check_properties(PROPS_EN, fixed), g.ERROR), set())

    def test_messageformat_quote(self):
        self.assertTrue(g._messageformat_quote("Delete {0}?", "Supprimer l'élément {0} ?"))
        self.assertFalse(g._messageformat_quote("Delete {0}?", "Supprimer l''élément {0} ?"))
        self.assertFalse(g._messageformat_quote("Delete {0}?", "Supprimer l’élément {0} ?"))
        self.assertFalse(g._messageformat_quote("Saved", "Enregistré dans l'application"))
        self.assertFalse(g._messageformat_quote("It''s {0}", "C''est {0}"))


ARB_EN = {
    "@@locale": "en",
    "hello": "Hello {name}",
    "@hello": {"description": "Greeting", "placeholders": {"name": {"type": "String"}}},
    "inbox": "{count, plural, =0{No messages} =1{One message} other{{count} messages}}",
    "@inbox": {"placeholders": {"count": {"type": "int"}}},
    "bye": "Bye <b>{name}</b>",
}

ARB_JA = {
    "@@locale": "ja",
    "hello": "こんにちは {name}",
    "inbox": "{count, plural, other{{count} 件のメッセージ}}",
    "bye": "さようなら {name}",
}


class FlutterArb(unittest.TestCase):
    def test_check(self):
        problems = g.check_arb(ARB_EN, ARB_JA)
        self.assertEqual([(p["code"], p["level"], p["key"]) for p in problems],
                         [("tags", g.ERROR, "bye")])
        dropped = dict(ARB_JA, inbox="{n, plural, other{メッセージ}}")
        self.assertIn("placeholder-missing", codes(g.check_arb(ARB_EN, dropped), g.ERROR))

    def test_metadata_ignored_and_locale(self):
        same_locale = dict(ARB_JA)
        same_locale["@@locale"] = "en"
        same_locale["bye"] = "さようなら <b>{name}</b>"
        problems = g.check_arb(ARB_EN, same_locale)
        self.assertEqual([(p["code"], p["level"]) for p in problems], [("locale", g.WARNING)])
        with self.assertRaises(ValueError):
            g.check_arb(ARB_EN, ["not", "an", "object"])


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

    def test_apple_lproj_dir(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "en.lproj/Localizable.strings", STRINGS_EN)
            _write(d, "de.lproj/Localizable.strings", STRINGS_DE)
            problems, stats = g.check_dir(os.path.join(d, "en.lproj"), os.path.join(d, "de.lproj"))
        self.assertEqual(stats, {"checked": 1, "unmatched": 0})
        self.assertEqual(sorted(p["key"] for p in problems),
                         ["Localizable.strings extra", "Localizable.strings greeting"])


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

    def test_mobile_and_xliff_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            en = _write(d, "values/strings.xml", ANDROID_EN)
            fr = _write(d, "values-fr/strings.xml", ANDROID_FR)
            xlf = _write(d, "messages.de.xlf", XLIFF12)
            cat = _write(d, "Localizable.xcstrings", json.dumps(XCSTRINGS))
            broken = _write(d, "values-de/strings.xml", "<resources><string name=")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["android", en, fr]), 1)
                self.assertEqual(g.run(["xliff", xlf]), 1)
                self.assertEqual(g.run(["xcstrings", cat]), 1)
            text = out.getvalue()
            self.assertIn("android-apostrophe [saved]", text)
            self.assertIn("4 units, 3 translated, 1 untranslated", text)
            self.assertIn("2 strings, 4 checked, 1 untranslated", text)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(g.run(["android", en, broken]), 2)

    def test_android_java_format_cli(self):
        with tempfile.TemporaryDirectory() as d:
            en = _write(d, "values/strings.xml", ANDROID_JAVA_EN)
            fr = _write(d, "values-fr/strings.xml", ANDROID_JAVA_FR)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["android", en, fr]), 1)
            self.assertIn("java-format [done]: String.format would throw "
                          "FormatFlagsConversionMismatchException", out.getvalue())

    def test_properties_and_arb_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            en = _write(d, "messages.properties", PROPS_EN)
            fr = _write(d, "messages_fr.properties", PROPS_FR)
            de = os.path.join(d, "messages_de.properties")
            with open(de, "wb") as f:
                f.write("welcome = Willkommen zurück, {0}!\n".encode("latin-1"))
            arb_en = _write(d, "app_en.arb", json.dumps(ARB_EN))
            arb_ja = _write(d, "app_ja.arb", json.dumps(ARB_JA, ensure_ascii=False))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["properties", en, fr]), 1)
                self.assertEqual(g.run(["properties", en, de]), 0)
                self.assertEqual(g.run(["arb", arb_en, arb_ja]), 1)
            text = out.getvalue()
            self.assertIn("messageformat-apostrophe [deleted]", text)
            self.assertIn("tags [bye]", text)


if __name__ == "__main__":
    unittest.main()
