#!/usr/bin/env python3
"""Tests for l10n-guard 0.21.0: the linguas check (gettext .po files that po/LINGUAS leaves
out, so Meson or gettext's autotools rules never build them).

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import l10n_guard as g

MESON = "i18n.gettext(meson.project_name(), preset: 'glib')\n"
HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def po_text(done=1, todo=0, fuzzy=0):
    parts = [HEADER]
    for i in range(done):
        parts.append('msgid "a%d"\nmsgstr "b%d"\n\n' % (i, i))
    for i in range(todo):
        parts.append('msgid "t%d"\nmsgstr ""\n\n' % i)
    for i in range(fuzzy):
        parts.append('#, fuzzy\nmsgid "f%d"\nmsgstr "g%d"\n\n' % (i, i))
    return "".join(parts)


def check(files):
    data = dict((k, v.encode("utf-8")) for k, v in files.items())
    return g.check_linguas(sorted(data), data.get)


class LinguasTest(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 21, 0))

    def test_unlisted_translation_is_reported(self):
        problems, stats = check({
            "meson.build": "project('x')\n", "po/meson.build": MESON,
            "po/LINGUAS": "# languages\nde\nfr\n", "po/de.po": po_text(), "po/fr.po": po_text(),
            "po/cs.po": po_text(3, 1)})
        self.assertEqual([(p["code"], p["key"]) for p in problems], [("linguas-unlisted", "cs")])
        self.assertIn("po/cs.po has 3 of 4 messages translated", problems[0]["message"])
        self.assertIn("po/LINGUAS does not list 'cs'", problems[0]["message"])
        self.assertIn("Meson", problems[0]["message"])
        self.assertEqual(problems[0]["level"], "warning")
        self.assertEqual(stats["po folders checked"], 1)

    def test_untranslated_and_fuzzy_files_are_not_reported(self):
        problems, stats = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/cs.po": po_text(0, 2, 1)})
        self.assertEqual(problems, [])
        self.assertEqual(stats["untranslated files skipped"], 1)

    def test_names_that_are_not_locales(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/it_complete.po": po_text(), "po/en@quot.po": po_text(),
            "po/messages.po": po_text(), "po/xx.po": po_text()})
        self.assertEqual(problems, [])

    def test_language_of_a_file_name(self):
        for stem, lang in (("sr@latin", "sr"), ("zh_Hant", "zh"), ("es_419", "es"),
                           ("pt-BR", "pt"), ("ast", "ast"), ("ca@valencia", "ca"),
                           ("fi_FI", "fi")):
            self.assertEqual(g._lg_language(stem), lang, stem)
        for stem in ("it_complete", "en@quot", "en@boldquot", "xx", "messages", "PT"):
            self.assertIsNone(g._lg_language(stem), stem)

    def test_archived_and_vendored_folders_are_skipped(self):
        problems, stats = check({
            "old/app-0.8/configure.ac": "AM_GNU_GETTEXT([external])\n",
            "old/app-0.8/po/LINGUAS": "de\n", "old/app-0.8/po/de.po": po_text(),
            "old/app-0.8/po/el.po": po_text(),
            "subprojects/lib/po/meson.build": MESON, "subprojects/lib/po/LINGUAS": "de\n",
            "subprojects/lib/po/fr.po": po_text()})
        self.assertEqual(problems, [])
        self.assertEqual((stats["po folders checked"], stats["po folders skipped"]), (0, 0))

    def test_meson_languages_list_is_skipped(self):
        problems, stats = check({
            "po/meson.build": "i18n.gettext('x', languages: ['de'])\n", "po/LINGUAS": "de\n",
            "po/de.po": po_text(), "po/fr.po": po_text()})
        self.assertEqual(problems, [])
        self.assertEqual(stats["po folders skipped"], 1)

    def test_folder_without_a_build_rule_is_skipped(self):
        problems, stats = check({"po/LINGUAS": "de\n", "po/fr.po": po_text()})
        self.assertEqual(problems, [])
        self.assertEqual((stats["po folders checked"], stats["po folders skipped"]), (0, 1))

    def test_autotools_reads_hash_as_a_comment(self):
        problems, _ = check({
            "configure.ac": "AC_INIT([x], [1])\nAM_GNU_GETTEXT([external])\n",
            "po/LINGUAS": "de fr # cs\n", "po/de.po": po_text(), "po/fr.po": po_text(),
            "po/cs.po": po_text()})
        self.assertEqual([(p["code"], p["key"]) for p in problems], [("linguas-unlisted", "cs")])
        self.assertIn("gettext's build rules", problems[0]["message"])

    def test_spelling_variant_names_the_listed_entry(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "pt_BR\n", "po/pt-BR.po": po_text()})
        self.assertEqual(sorted(p["code"] for p in problems),
                         ["linguas-missing", "linguas-unlisted"])
        unlisted = [p for p in problems if p["code"] == "linguas-unlisted"][0]
        self.assertIn("po/LINGUAS lists 'pt_BR'", unlisted["message"])

    def test_listed_language_without_a_file(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\nes\n", "po/de.po": po_text()})
        self.assertEqual([(p["code"], p["key"]) for p in problems], [("linguas-missing", "es")])
        self.assertIn("there is no po/es.po", problems[0]["message"])


class LinguasCliTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        files = {"po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
                 "po/cs.po": po_text(2), "old/po/LINGUAS": "de\n", "old/po/meson.build": MESON,
                 "old/po/el.po": po_text()}
        for rel, text in files.items():
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(text.encode("utf-8"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = g.run(list(argv))
        return code, out.getvalue()

    def test_warnings_exit_zero_and_strict_exit_one(self):
        code, text = self.cli("linguas", self.root)
        self.assertEqual(code, 0)
        self.assertIn("WARNING linguas-unlisted [cs]", text)
        self.assertNotIn("el.po", text)
        code, _ = self.cli("--strict", "linguas", self.root)
        self.assertEqual(code, 1)

    def test_json_output(self):
        code, text = self.cli("--json", "linguas", self.root)
        data = json.loads(text)
        self.assertEqual([i["code"] for i in data["issues"]], ["linguas-unlisted"])
        self.assertEqual(data["stats"]["po folders checked"], 1)

    def test_missing_folder_is_bad_input(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self.cli("linguas", os.path.join(self.root, "nope"))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
