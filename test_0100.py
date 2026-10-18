#!/usr/bin/env python3
"""l10n-guard 0.10.0: the YAML reader, Rails locale files (kind: rails),
Symfony translations paired by key (kind: symfony), and look-alike percent
signs in both. The translations are real ones from open-source projects
(2026-10-18) unless marked "written for the test"; the file layouts around
them are written for the test. Standard library only.

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

# Written for the test: every feature the YAML reader takes.
YAML = r"""# a comment
---
en:
  plain: Hello world   # trailing comment
  single: 'It''s %{name}'
  double: "Tab\tand \"quotes\" \u00e9"
  'yes': quoted key
  "a.b": dotted key
  empty:
  tilde: ~
  folded_plain: first line
    second line

    after a blank
  multi_quoted: 'one
    two'
  literal: |
    line 1
      indented
    line 3
  folded: >-
    joined
    words

    new paragraph
  keep: |+
    kept

  list:
  - first
  - "second: quoted"
  - key: value
    other: more
  nested:
    deep:
      deeper: x
  flow: [a, 'b, c']
  none: {}
"""

# GOV.UK Publishing Components config/locales (05d2fbe8): the English and
# Japanese strings; the nesting is written for the test.
RAILS_EN = """---
en:
  common:
    toggle_more: "%{show} %{number} more"
  components:
    attachment:
      page:
        one: 1 page
        other: "%{count} pages"
    character_count:
      body: You can enter up to %{number} %{type}
    cookie_banner:
      confirmation_message:
        html: You can %{link} at any time.
"""
RAILS_JA = """---
ja:
  common:
    toggle_more: さらに ％{number}
  components:
    attachment:
      page:
        other: "％{count}ページ"
    character_count:
      body: 最大 ％{number} ％{type} を入力できます
    cookie_banner:
      confirmation_message:
        html: いつでも ％{link} できます。
"""

# SonataAdminBundle src/Resources/translations (4.x, 0b360302): the
# flash_lock_error strings are real; title_edit is written for the test.
SONATA_EN = """<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">
  <file source-language="en" datatype="plaintext" original="file.ext">
    <body>
      <trans-unit id="title_edit">
        <source>title_edit</source>
        <target>Edit "%name%"</target>
      </trans-unit>
      <trans-unit id="flash_lock_error">
        <source>flash_lock_error</source>
        <target>Another user has modified item "%name%". Please %link_start%click here%link_end% to reload the page and apply the changes again.</target>
      </trans-unit>
    </body>
  </file>
</xliff>
"""
SONATA_JA = """<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">
  <file source-language="en" datatype="plaintext" original="file.ext">
    <body>
      <trans-unit id="title_edit">
        <source>title_edit</source>
        <target>"%name%" の編集</target>
      </trans-unit>
      <trans-unit id="flash_lock_error">
        <source>flash_lock_error</source>
        <target>別のユーザーがアイテム "％name％" を変更しました。 ％link_start％ここをクリック％link_end％ して、ページを再読み込みして変更を再度適用してください。</target>
      </trans-unit>
    </body>
  </file>
</xliff>
"""

# Akeneo PIM validators.en_US.yml and validators.zh_TW.yml (cfc810e6),
# family_variant_no_axis; the nesting is written for the test.
AKENEO_EN = """pim_catalog:
    constraint:
        family_variant_no_axis: There should be at least one attribute defined as axis for the attribute set for level "%level%"
"""
AKENEO_ZH_TW = """pim_catalog:
    constraint:
        family_variant_no_axis: 級別“％level％”的屬性z组應至少定義一個屬性作為軸
"""
# Written for the test, with the translated %Seviye% the Turkish file has.
AKENEO_TR = """pim_catalog:
    constraint:
        family_variant_no_axis: Seviye "%Seviye%" için en az bir eksen özelliği tanımlanmalıdır
"""

# OpenDXP admin.en.yaml and admin.zh_Hans.yaml (66f8e913); the quoting of
# the English line is written for the test.
OPENDXP_EN = ("workflow_change_email_notification_text: 'For %s with ID %s the action \"%s\" "
              "was triggered in workflow ''%s''.'\n")
OPENDXP_ZH = ("workflow_change_email_notification_text: "
              "'对于ID为％s的％s，在工作流''％s''中触发了操作“％s”。'\n")


def codes(problems):
    return [(p["level"], p["code"], p.get("key")) for p in problems]


class Yaml0100Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 10, 0))

    def test_parse(self):
        self.assertEqual(g.parse_yaml(YAML), {"en": {
            "plain": "Hello world",
            "single": "It's %{name}",
            "double": 'Tab\tand "quotes" \u00e9',
            "yes": "quoted key",
            "a.b": "dotted key",
            "empty": None,
            "tilde": None,
            "folded_plain": "first line second line\nafter a blank",
            "multi_quoted": "one two",
            "literal": "line 1\n  indented\nline 3\n",
            "folded": "joined words\nnew paragraph",
            "keep": "kept\n\n",
            "list": ["first", "second: quoted", {"key": "value", "other": "more"}],
            "nested": {"deep": {"deeper": "x"}},
            "flow": ["a", "b, c"],
            "none": {},
        }})

    def test_explicit_block_indent(self):
        # Written for the test, in the |2- form OpenStreetMap's files use.
        self.assertEqual(g.parse_yaml("a:\n  b: |2-\n     spaced\n    text\n  c: d\n"),
                         {"a": {"b": " spaced\ntext", "c": "d"}})

    def test_escaped_line_break(self):
        self.assertEqual(g.parse_yaml('a: "one \\\n  two"\n'), {"a": "one two"})

    def test_refused(self):
        for text in ("a: &x 1\nb: *x\n", "a: !tag x\n", "a: {b: c}\n", "a:\n\tb: c\n",
                     "a: 'open\n", "a: b\nc\n", 'a: "bad \\q"\n', "a: [b, [c]]\n",
                     "- a\nb: c\n"):
            with self.assertRaises(ValueError, msg=text):
                g.parse_yaml(text)

    def test_empty(self):
        self.assertEqual(g.parse_yaml("# nothing\n---\n"), {})


class Rails0100Test(unittest.TestCase):
    def test_govuk(self):
        found = g.check_rails(RAILS_EN, RAILS_JA)
        self.assertEqual(codes(found), [
            (g.ERROR, "lookalike-percent", "common.toggle_more"),
            (g.ERROR, "placeholder-missing", "common.toggle_more"),
            (g.ERROR, "lookalike-percent", "components.attachment.page.other"),
            (g.ERROR, "lookalike-percent", "components.character_count.body"),
            (g.ERROR, "lookalike-percent", "components.character_count.body"),
            (g.ERROR, "lookalike-percent", "components.cookie_banner.confirmation_message.html"),
        ])
        self.assertIn("%{number} is written \"％{number}\"", found[0]["message"])
        self.assertIn("U+FF05", found[0]["message"])
        self.assertIn("%{show}", found[1]["message"])
        self.assertEqual([p["message"].split()[0] for p in found[3:5]], ["%{number}", "%{type}"])

    def test_ascii_copy_is_a_warning(self):
        # OpenStreetMap config/locales/ar.yml (855cda76), site.about.heading_html;
        # the English is written for the test.
        found = g._rails_pair("%{copyright} OpenStreetMap %{br} contributors",
                              "٪ {copyright} OpenStreetMap٪ {br} من المساهمين%{copyright}%{br}",
                              "site.about.heading_html")
        self.assertEqual(codes(found), [(g.WARNING, "lookalike-percent", "site.about.heading_html")] * 2)
        self.assertIn("\"٪ {br}\" is written with the Arabic percent sign", found[0]["message"])
        self.assertIn("ASCII %{br}", found[0]["message"])

    def test_plural_forms(self):
        # Written for the test.
        en = "en:\n  files:\n    one: 1 file\n    other: \"%{count} files\"\n"
        ar = ("ar:\n  files:\n    zero: لا ملفات\n    few: \"%{count} ملفات\"\n"
              "    other: \"٪ {count} ملف\"\n")
        self.assertEqual(codes(g.check_rails(en, ar)),
                         [(g.ERROR, "lookalike-percent", "files.other"),
                          (g.WARNING, "placeholder-missing", "files.zero")])
        ja = "ja:\n  files:\n    other: \"%{count} 件のファイル\"\n"
        self.assertEqual(g.check_rails(en, ja), [])

    def test_named_format(self):
        found = g._rails_pair("%<count>d items", "％<count>d 件", "k")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent", "k")])
        self.assertEqual(g._rails_pair("%<count>d items", "%<count>d 件", "k"), [])

    def test_fullwidth_braces(self):
        found = g._rails_pair("Hello %{name}", "こんにちは %｛name｝", "k")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", "k")])

    def test_extra_placeholder_is_a_warning(self):
        found = g._rails_pair("Saved", "%{name} を保存しました", "k")
        self.assertEqual(codes(found), [(g.WARNING, "placeholder-extra", "k")])
        self.assertIn("MissingInterpolationArgument", found[0]["message"])

    def test_not_a_mapping(self):
        with self.assertRaises(ValueError):
            g.check_rails("- a\n", "- b\n")


class Symfony0100Test(unittest.TestCase):
    def test_sonata_by_key(self):
        found = g.check_symfony(SONATA_EN, SONATA_JA, "SonataAdminBundle.en.xliff",
                                "SonataAdminBundle.ja.xliff")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent", "flash_lock_error")] * 3)
        self.assertEqual([p["message"].split()[0] for p in found],
                         ["%link_end%", "%link_start%", "%name%"])
        self.assertIn("%name% is written \"％name％\" with the fullwidth percent sign",
                      found[2]["message"])

    def test_one_file_xliff_check_misses_it(self):
        # The blind spot: the Japanese file alone has no English to compare.
        self.assertEqual(g.check_xliff(SONATA_JA)[0], [])

    def test_akeneo(self):
        found = g.check_symfony(AKENEO_EN, AKENEO_ZH_TW, "validators.en_US.yml",
                                "validators.zh_TW.yml")
        key = "pim_catalog.constraint.family_variant_no_axis"
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent", key)])
        self.assertIn("%level% is written \"％level％\"", found[0]["message"])
        found = g.check_symfony(AKENEO_EN, AKENEO_TR, "validators.en_US.yml",
                                "validators.tr_TR.yml")
        self.assertEqual(codes(found), [(g.ERROR, "placeholder-missing", key),
                                        (g.WARNING, "placeholder-extra", key)])
        self.assertIn("%level%", found[0]["message"])
        self.assertIn("%Seviye%", found[1]["message"])

    def test_opendxp_printf(self):
        found = g.check_symfony(OPENDXP_EN, OPENDXP_ZH, "admin.en.yaml", "admin.zh_Hans.yaml")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent",
                                         "workflow_change_email_notification_text")] * 4)

    def test_spaced_arabic(self):
        # UVdesk community-skeleton translations/messages.ar.yml.
        found = g._symfony_pair("Learn more about %deliveryStatus%.",
                                "تعرف على المزيد حول٪ deliveryStatus٪.", "k")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent", "k")])
        self.assertIn("\"٪ deliveryStatus٪\"", found[0]["message"])
        self.assertIn("U+066A", found[0]["message"])

    def test_plurals(self):
        # Written for the test.
        self.assertEqual(g._symfony_pair("{0} No results|{1} One result|]1,Inf] %count% results",
                                         "%count% 件の結果", "k"), [])
        self.assertEqual(g._symfony_pair("%count% file|%count% files",
                                         "%count% plik|%count% pliki|%count% plików", "k"), [])
        self.assertEqual(codes(g._symfony_pair("%count% file|%count% files",
                                               "jeden plik|%count% pliki", "k")),
                         [(g.WARNING, "placeholder-missing", "k")])

    def test_validator_braces(self):
        source = ("This value is too short. It should have {{ limit }} character or more.|"
                  "This value is too short. It should have {{ limit }} characters or more.")
        self.assertEqual(g._symfony_pair(source, "{{ limit }}文字以上で入力してください。", "k"), [])
        # Written for the test.
        self.assertEqual(codes(g._symfony_pair(source, "｛｛ limit ｝｝文字以上で入力してください。", "k")),
                         [(g.ERROR, "lookalike-brace", "k")])

    def test_correct_and_copy(self):
        self.assertEqual(g._symfony_pair("Edit %name%", "%name% を編集", "k"), [])
        self.assertEqual(g._symfony_pair("Edit %name%", "%name%", "k"), [])
        found = g._symfony_pair("Edit %name%", "%name%（％name％）を編集", "k")
        self.assertEqual(codes(found), [(g.WARNING, "lookalike-percent", "k")])

    def test_parse_xliff_keys(self):
        xliff2 = ('<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0" version="2.0" '
                  'srcLang="en" trgLang="ja"><file id="f">'
                  '<unit id="1" name="greeting"><segment><source>Hello %name%</source>'
                  '<target>こんにちは ％name％</target></segment></unit>'
                  '<unit id="2"><segment><source>Bye</source></segment></unit>'
                  '</file></xliff>')
        self.assertEqual(g.parse_symfony(xliff2, "messages.ja.xlf"),
                         {"greeting": "こんにちは ％name％", "Bye": "Bye"})
        xliff1 = ('<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2"><file>'
                  '<body><trans-unit id="a" resname="key.one"><source>Text</source>'
                  '<target>T</target></trans-unit></body></file></xliff>')
        self.assertEqual(g.parse_symfony(xliff1, "messages.ja.xliff"), {"key.one": "T"})
        with self.assertRaises(ValueError):
            g.parse_symfony("{}", "messages.ja.json")

    def test_keys(self):
        found = g.check_symfony("a: Hello %name%\nb: Bye\n", "a: こんにちは %name%\nc: x\n")
        self.assertEqual(codes(found), [(g.WARNING, "missing-key", "b"),
                                        (g.WARNING, "extra-key", "c")])


class Laravel0100Test(unittest.TestCase):
    def test_spelling_kept(self):
        found = g._laravel_pair("Action :actionText was done", "：actionText が完了しました", "k")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-colon", "k")])
        self.assertIn(":actionText is written \"：actionText\"", found[0]["message"])
        found = g._laravel_pair("Hi :userName", "こんにちは", "k")
        self.assertEqual(found[-1]["message"], "placeholder(s) missing: :userName")

    def test_stub(self):
        # UNIT3D lang/pt_BR/*.php (8b88f4c8): six bytes, "<?php" and a newline.
        with self.assertRaises(ValueError) as cm:
            g.parse_laravel("<?php\n")
        self.assertIn("it is only \"<?php\"", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            g.parse_laravel("<?php echo 'x';")
        self.assertNotIn("only", str(cm.exception))


class Cli0100Test(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = g.run(argv)
        return code, out.getvalue()

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, text in (("en.yml", RAILS_EN), ("ja.yml", RAILS_JA),
                               ("m.en.xliff", SONATA_EN), ("m.ja.xliff", SONATA_JA),
                               ("bad.yml", "a: &x 1\n")):
                paths[name] = os.path.join(tmp, name)
                with open(paths[name], "w", encoding="utf-8") as f:
                    f.write(text)
            code, out = self.run_cli(["rails", paths["en.yml"], paths["ja.yml"]])
            self.assertEqual(code, 1)
            self.assertIn("ERROR lookalike-percent [common.toggle_more]: %{number} is written", out)
            code, out = self.run_cli(["symfony", paths["m.en.xliff"], paths["m.ja.xliff"]])
            self.assertEqual(code, 1)
            self.assertIn("ERROR lookalike-percent [flash_lock_error]: %name% is written", out)
            code, out = self.run_cli(["--json", "symfony", paths["m.en.xliff"], paths["m.en.xliff"]])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["errors"], 0)
            code, _ = self.run_cli(["rails", paths["bad.yml"], paths["bad.yml"]])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
