#!/usr/bin/env python3
"""Tests for l10n-guard 0.22.0: gettext spellings. linguas-unlisted names the spelling glibc
looks up when a file's territory is in lower case (zh_cn.po -> zh_CN.po), and the new
linguas-spelling warning reports a listed language that is installed under a name glibc never
looks up (zh_cn, pt-BR).

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g

MESON = "i18n.gettext(meson.project_name(), preset: 'glib')\n"
AUTOTOOLS = "AC_INIT([x], [1])\nAM_GNU_GETTEXT([external])\n"
HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def po_text(done=1):
    return HEADER + "".join('msgid "a%d"\nmsgstr "b%d"\n\n' % (i, i) for i in range(done))


def check(files):
    data = dict((k, v.encode("utf-8")) for k, v in files.items())
    return g.check_linguas(sorted(data), data.get)


def codes(problems):
    return [(p["code"], p["key"]) for p in problems]


class GettextNameTest(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 22, 0))

    def test_gettext_name(self):
        cases = {"zh_cn": "zh_CN", "pt-br": "pt_BR", "nb-NO": "nb_NO", "pt_BR": "pt_BR",
                 "de": "de", "ast": "ast", "es_419": "es_419", "sr@latin": "sr@latin",
                 "ca@valencia": "ca@valencia", "de_ch@euro": "de_CH@euro",
                 "sr-Latn": "sr_Latn", "zh_Hant": "zh_Hant"}
        for stem, want in cases.items():
            self.assertEqual(g._lg_gettext_name(stem), want, stem)

    def test_has_script(self):
        self.assertTrue(g._lg_has_script("zh_Hant"))
        self.assertTrue(g._lg_has_script("sr-Latn"))
        self.assertTrue(g._lg_has_script("uz_Cyrl@x"))
        for stem in ("zh_CN", "zh_cn", "sr@latin", "es_419", "ast", "de"):
            self.assertFalse(g._lg_has_script(stem), stem)

    def test_why(self):
        self.assertEqual(g._lg_why("nb-NO", "nb_NO"), "gettext locale names use '_'")
        self.assertEqual(g._lg_why("zh_cn", "zh_CN"),
                         "gettext locale names write the territory in capitals")
        self.assertEqual(g._lg_why("nb-no", "nb_NO"),
                         "gettext locale names use '_' and write the territory in capitals")


class UnlistedTest(unittest.TestCase):
    def test_lowercase_territory_gets_the_gettext_spelling(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/zh_cn.po": po_text(2)})
        self.assertEqual(codes(problems), [("linguas-unlisted", "zh_cn")])
        msg = problems[0]["message"]
        self.assertEqual(
            msg,
            "po/zh_cn.po has 2 of 2 messages translated, but po/LINGUAS does not list 'zh_cn', "
            "so Meson never compiles or installs it; gettext locale names write the territory "
            "in capitals, so a catalog installed as 'zh_cn' is never looked up; rename "
            "po/zh_cn.po to po/zh_CN.po and add 'zh_CN' to po/LINGUAS if the translation is "
            "ready")
        self.assertNotIn("add 'zh_cn'", msg)

    def test_hyphen_and_lowercase(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/nb-no.po": po_text()})
        self.assertEqual(codes(problems), [("linguas-unlisted", "nb-no")])
        self.assertIn("gettext locale names use '_' and write the territory in capitals, so a "
                      "catalog installed as 'nb-no' is never looked up; rename po/nb-no.po to "
                      "po/nb_NO.po and add 'nb_NO' to po/LINGUAS", problems[0]["message"])

    def test_hyphen_message_is_unchanged(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/nb-NO.po": po_text(3)})
        self.assertEqual(
            problems[0]["message"],
            "po/nb-NO.po has 3 of 3 messages translated, but po/LINGUAS does not list 'nb-NO', "
            "so Meson never compiles or installs it; gettext locale names use '_', so a catalog "
            "installed as 'nb-NO' is never looked up; rename po/nb-NO.po to po/nb_NO.po and add "
            "'nb_NO' to po/LINGUAS if the translation is ready")

    def test_listed_other_case_still_wins(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "zh_CN\n", "po/zh_cn.po": po_text()})
        unlisted = [p for p in problems if p["code"] == "linguas-unlisted"]
        self.assertEqual(len(unlisted), 1)
        self.assertIn("po/LINGUAS lists 'zh_CN', and the name must match the file name exactly",
                      unlisted[0]["message"])
        self.assertNotIn("rename", unlisted[0]["message"])

    def test_plain_name_message_is_unchanged(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/pt_BR.po": po_text()})
        self.assertEqual(codes(problems), [("linguas-unlisted", "pt_BR")])
        self.assertTrue(problems[0]["message"].endswith(
            "; add 'pt_BR' to po/LINGUAS if the translation is ready"))


class SpellingTest(unittest.TestCase):
    def test_listed_lowercase_territory(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\nzh_cn\n", "po/de.po": po_text(),
            "po/zh_cn.po": po_text()})
        self.assertEqual(codes(problems), [("linguas-spelling", "zh_cn")])
        self.assertEqual(problems[0]["level"], g.WARNING)
        self.assertEqual(
            problems[0]["message"],
            "po/LINGUAS lists 'zh_cn', so po/zh_cn.po is installed as 'zh_cn', but gettext "
            "locale names write the territory in capitals, so it is never looked up for a "
            "'zh_CN' locale; rename po/zh_cn.po to po/zh_CN.po and list 'zh_CN' instead")

    def test_listed_hyphen(self):
        problems, _ = check({
            "configure.ac": AUTOTOOLS, "po/LINGUAS": "de pt-BR\n", "po/de.po": po_text(),
            "po/pt-BR.po": po_text()})
        self.assertEqual(codes(problems), [("linguas-spelling", "pt-BR")])
        self.assertIn("but gettext locale names use '_', so it is never looked up for a 'pt_BR' "
                      "locale; rename po/pt-BR.po to po/pt_BR.po and list 'pt_BR' instead",
                      problems[0]["message"])

    def test_good_names_are_quiet(self):
        names = ["de", "pt_BR", "es_419", "sr@latin", "ca@valencia", "zh_Hant", "ast", "en_GB"]
        files = {"po/meson.build": MESON, "po/LINGUAS": " ".join(names) + "\n"}
        for n in names:
            files["po/%s.po" % n] = po_text()
        problems, _ = check(files)
        self.assertEqual(problems, [])

    def test_script_codes_are_left_alone(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "sr-Latn\n", "po/sr-Latn.po": po_text()})
        self.assertEqual(problems, [])

    def test_both_spellings_listed(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "zh_CN\nzh_cn\n", "po/zh_CN.po": po_text(),
            "po/zh_cn.po": po_text()})
        self.assertEqual(problems, [])

    def test_missing_file_is_still_linguas_missing(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\nzh_cn\n", "po/de.po": po_text()})
        self.assertEqual(codes(problems), [("linguas-missing", "zh_cn")])

    def test_not_a_locale_is_left_alone(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\nit_complete\n", "po/de.po": po_text(),
            "po/it_complete.po": po_text()})
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
