#!/usr/bin/env python3
"""l10n-guard 0.8.0: placeholders written with fullwidth braces
(lookalike-brace) and .NET .resx files. The translations are real ones from
open-source projects (2026-10-18); the English sources marked "written for
the test" are not. Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import contextlib
import io
import os
import tempfile
import unittest

import l10n_guard as g

RESX = '''<?xml version="1.0" encoding="utf-8"?>
<root>
  <resheader name="resmimetype"><value>text/microsoft-resx</value></resheader>
  %s
</root>'''
# Rayman Control Panel, ModLoader_GameBanana_UploadInfo (zh-Hans).
RAYMAN_SRC = RESX % (
    '<data name="ModLoader_GameBanana_UploadInfo" xml:space="preserve">'
    '<value>Uploaded by {0} on {1}</value></data>'
    '<data name="Icon" type="System.Drawing.Bitmap, System.Drawing" '
    'mimetype="application/x-microsoft.net.object.bytearray.base64"><value>AAAA</value></data>'
    '<data name="&gt;&gt;label1.Name" xml:space="preserve"><value>label1</value></data>'
    '<data name="Other" xml:space="preserve"><value>Other</value><comment>note</comment></data>')
RAYMAN_ZH = RESX % (
    '<data name="ModLoader_GameBanana_UploadInfo" xml:space="preserve">'
    '<value>由｛0｝于｛1｝上传</value></data>')


def codes(problems):
    return [(p["level"], p["code"], p.get("key")) for p in problems]


class LookalikeBrace080Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 8, 0))

    def test_fullwidth_digits(self):
        # ONLYOFFICE CommunityServer AuditReportResource.ja.resx, FolderMoved
        # (source written for the test).
        found = g.check_pair("Folder [{0}]. Moved to folder: {1}",
                             "フォルダ[{0}]。フォルダ：｛１｝に移動されました。", "FolderMoved")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", "FolderMoved")])
        self.assertIn("\"｛１｝\"", found[0]["message"])
        self.assertIn("U+FF5B", found[0]["message"])
        self.assertNotIn("throw", found[0]["message"])

    def test_one_brace_still_ascii(self):
        # VidCoder ja, EncodeCompleteWarning_SleepMessage (source written for the test).
        found = g.check_pair("Going to sleep in {0} seconds", "｛0}秒後にスリープになります")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", None)])
        self.assertIn("\"｛0}\"", found[0]["message"])
        self.assertIn("string.Format", found[0]["message"])

    def test_double_braces_in_json(self):
        # OWASP Juice Shop zh_TW, NFT_SBT_BOX_TEXT.
        found = g.check_catalog({"NFT_SBT_BOX_TEXT": "Find the Juice Shop SBT on {{link}}."},
                                {"NFT_SBT_BOX_TEXT": "好哇！ 在｛｛link｝｝上找到果汁店SBT。"})
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", "NFT_SBT_BOX_TEXT")])
        self.assertIn("{{link}}", found[0]["message"])

    def test_case_of_the_name(self):
        # jfa-go zh-hant, languageSet: the name is capitalized too.
        found = g.check_pair("Language set to {language}.", "語言設置為｛Language｝。")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", None)])

    def test_icu_argument(self):
        found = g.check_arb({"files": "{count, plural, one {# file} other {# files}}"},
                            {"files": "｛count， plural， other {# 个文件}｝"})
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", "files")])

    def test_properties(self):
        found = g.check_properties("pages={0} pages\n", "pages=\\uFF5B0\\uFF5D\\u9875\n")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-brace", "pages")])

    def test_copy_next_to_the_real_one_is_a_warning(self):
        found = g.check_pair("{0} files", "{0} 個のファイル ｛0｝")
        self.assertEqual(codes(found), [(g.WARNING, "lookalike-brace", None)])

    def test_fullwidth_braces_in_the_source_are_text(self):
        self.assertEqual(g.check_pair("Type ｛name｝ to insert {name}",
                                      "｛name｝ と入力すると {name} を挿入"), [])
        found = g.check_pair("｛0｝ means {0}", "｛0｝ の意味")
        self.assertEqual(codes(found), [(g.ERROR, "placeholder-missing", None)])

    def test_not_placeholders(self):
        # pentaho-kettle ja furigana; Scilab's set notation around an ASCII %s.
        self.assertEqual(g.check_pair("Standard deviation", "標準偏差｛ひょうじゅん へんさ｝"), [])
        self.assertEqual(g.check_pair("{%s}", "｛%s｝"), [])
        self.assertEqual(codes(g.check_pair("Hello {0}", "こんにちは ｛1｝")),
                         [(g.ERROR, "placeholder-missing", None)])

    def test_percent_verdicts_are_unchanged(self):
        found = g.check_pair("%s files", "٪s ملفات")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-percent", None)])
        self.assertIn("Arabic percent sign", found[0]["message"])


class Resx080Test(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(g.parse_resx(RAYMAN_SRC),
                         {"ModLoader_GameBanana_UploadInfo": "Uploaded by {0} on {1}", "Other": "Other"})

    def test_check(self):
        self.assertEqual(codes(g.check_resx(RAYMAN_SRC, RAYMAN_ZH)),
                         [(g.ERROR, "lookalike-brace", "ModLoader_GameBanana_UploadInfo"),
                          (g.ERROR, "lookalike-brace", "ModLoader_GameBanana_UploadInfo"),
                          (g.WARNING, "missing-key", "Other")])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, text in (("Resources.resx", RAYMAN_SRC), ("Resources.zh-Hans.resx", RAYMAN_ZH)):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write(text)
                paths.append(path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = g.run(["resx"] + paths)
            self.assertEqual(code, 1)
            self.assertIn("ERROR lookalike-brace [ModLoader_GameBanana_UploadInfo]", out.getvalue())
            self.assertIn("2 error(s), 1 warning(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
