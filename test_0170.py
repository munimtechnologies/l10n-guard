#!/usr/bin/env python3
"""l10n-guard 0.17.0: the `wrong-script` warning for Simplified-only Chinese
characters in Traditional Chinese translations, the locale read from a path
or --locale, and the `text` kind. Lines marked "census" are store-listing
lines from the hanzi-meta study's hand-check sample (fdroidclient, NewPipe,
LibreTorrent); the rest are written for the test. Standard library only.

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

SAI = chr(0x6652)


def codes(problems):
    return [p["code"] for p in problems]


def run_json(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = g.run(["--json"] + argv)
    return code, json.loads(out.getvalue())


def write(d, rel, text):
    path = os.path.join(d, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class Version0170Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 17, 0))

    def test_character_set(self):
        s = g._SIMPLIFIED_ONLY
        self.assertEqual(len(s), 3771)
        for c in "这设发说个们给踪内并":
            self.assertIn(c, s)
        for c in "這設發說個們給蹤內並設定已儲存保置":
            self.assertNotIn(c, s)


class LocaleTest(unittest.TestCase):
    def test_traditional(self):
        cases = {
            "zh-TW": "tw", "zh_TW": "tw", "ZH-HK": "hk", "zh-MO": "mo", "zh-Hant": "hant",
            "zh-Hant-HK": "hk", "zh_Hant_HK": "hk", "zh-Hant-TW": "tw",
            "app/src/main/res/values-zh-rTW/strings.xml": "tw",
            "res/values-zh-rHK/strings.xml": "hk",
            "res/values-b+zh+Hant/strings.xml": "hant",
            "res/values-b+zh+Hant+MO/strings.xml": "mo",
            "fastlane/metadata/android/zh-TW/full_description.txt": "tw",
            "metadata/zh-Hant-HK/changelogs/1000010.txt": "hk",
            "src/main/resources/messages_zh_TW.properties": "tw",
            "Properties/Resources.zh-Hant.resx": "hant",
            "lib/l10n/app_zh_Hant.arb": "hant",
            "zh-Hant.lproj/Localizable.strings": "hant",
            "locales/zh-TW/zh.json": "tw",
            "C:\\app\\res\\values-zh-rTW\\strings.xml": "tw",
        }
        for locale, region in cases.items():
            with self.subTest(locale=locale):
                self.assertEqual(g.traditional_chinese(locale), region)

    def test_not_traditional(self):
        for locale in ("zh", "zh-CN", "zh_Hans", "zh-Hans-HK", "zh-SG", "ja", "en", "", None,
                       "res/values-zh-rCN/strings.xml", "res/values-b+zh+Hans/strings.xml",
                       "res/values-zh/strings.xml", "res/values-fr/strings.xml",
                       "zhuyin/strings.xml", "locales/zh-TW/zh-CN.json"):
            with self.subTest(locale=locale):
                self.assertIsNone(g.traditional_chinese(locale))


class CheckScriptTest(unittest.TestCase):
    def test_flags_simplified(self):
        problems = g.check_script({"a": "Settings saved"}, {"a": "设置已儲存"}, "zh-TW")
        self.assertEqual(problems, [{
            "level": g.WARNING, "code": "wrong-script", "key": "a",
            "message": "Simplified Chinese character(s) in a Traditional Chinese (Taiwan) translation: 设"}])

    def test_characters_sorted_and_named_once(self):
        problems = g.check_script({"a": "This setting"}, {"a": "这个设定这个"}, "zh-Hant")
        self.assertEqual([p["message"] for p in problems],
                         ["Simplified Chinese character(s) in a Traditional Chinese translation: 个 设 这"])

    def test_clean_and_other_locales(self):
        self.assertEqual(g.check_script({"a": "Settings saved"}, {"a": "設定已儲存"}, "zh-TW"), [])
        for locale in ("zh-CN", "zh-Hans", "ja", None):
            with self.subTest(locale=locale):
                self.assertEqual(g.check_script({"a": "x"}, {"a": "设置"}, locale), [])

    def test_source_has_it_too(self):
        self.assertEqual(g.check_script({"a": "Write 这 for 'this'"}, {"a": "寫這或这"}, "zh-TW"), [])

    def test_cantonese_particle(self):
        target = {"a": "刪除" + SAI + "所有檔案"}
        self.assertEqual(g.check_script({"a": "Delete all files"}, target, "zh-HK"), [])
        self.assertEqual(g.check_script({"a": "Delete all files"}, target, "zh-MO"), [])
        self.assertEqual(codes(g.check_script({"a": "Delete all files"}, target, "zh-TW")),
                         ["wrong-script"])
        self.assertEqual(codes(g.check_script({"a": "Delete all files"}, target, "zh-Hant")),
                         ["wrong-script"])

    def test_keys_without_source(self):
        source = {"n[one]": "%d file", "n[other]": "%d files"}
        self.assertEqual(codes(g.check_script(source, {"n[few]": "%d 个"}, "zh-TW")), ["wrong-script"])
        self.assertEqual(g.check_script(source, {"x": "这"}, "zh-TW"), [])
        self.assertEqual(g.check_script({"m[one]": "a"}, {"n[few]": "这"}, "zh-TW"), [])

    def test_non_text_values(self):
        self.assertEqual(g.check_script({"a": 1, "b": None}, {"a": 2, "b": None}, "zh-TW"), [])

    def test_android_api_unchanged(self):
        src = '<resources><string name="s">Save settings</string></resources>'
        tgt = '<resources><string name="s">儲存设置</string></resources>'
        result = g.check_android(src, tgt)
        problems = result[0] if isinstance(result, tuple) else result
        self.assertNotIn("wrong-script", codes(problems))


class CheckTextTest(unittest.TestCase):
    def test_census_lines(self):
        # census: fdroidclient metadata/zh-Hant-HK/changelogs/1000010.txt, line 15
        line = "* 改進了針對跟踪的保護（HTTP ETag、TLS 等）"
        problems = g.check_text("* Improved protection against tracking (HTTP ETag, TLS, etc.)", line,
                                "metadata/zh-Hant-HK/changelogs/1000010.txt")
        self.assertEqual(problems, [{
            "level": g.WARNING, "code": "wrong-script",
            "message": "Simplified Chinese character(s) in a Traditional Chinese (Hong Kong) translation: 踪"}])
        # census: LibreTorrent fastlane/metadata/android/zh-TW/full_description.txt, line 1
        line = "* 使用 GPLv3+ 授權條款。你可以使用、查看、修改並再次分發给所有人。"
        self.assertEqual(codes(g.check_text("* Licensed under GPLv3+.", line, "zh-TW")),
                         ["wrong-script"])
        # census: NewPipe zh_Hant_HK/changelogs/987.txt, line 11 (a correct Cantonese 晒)
        line = "• 修正喺播放清單度剷走由頭到尾睇過" + SAI + "嘅影片"
        self.assertEqual(g.check_text("• Fixed removing fully watched videos from playlists", line,
                                      "fastlane/metadata/android/zh_Hant_HK/changelogs/987.txt"), [])

    def test_invisible_and_no_locale(self):
        self.assertEqual(codes(g.check_text("Save", "Spei" + chr(0x200B) + "chern", None)),
                         ["invisible-char"])
        self.assertEqual(g.check_text("Save", "设置", None), [])
        self.assertEqual(g.check_text("Save", "设置", "zh-CN"), [])


class CliTest(unittest.TestCase):
    def test_android_from_path(self):
        with tempfile.TemporaryDirectory() as d:
            src = write(d, "res/values/strings.xml",
                        '<resources><string name="save">Save settings</string></resources>')
            tgt = write(d, "res/values-zh-rTW/strings.xml",
                        '<resources><string name="save">儲存设置</string></resources>')
            code, data = run_json(["android", src, tgt])
            self.assertEqual(code, 0)
            self.assertEqual(codes(data["issues"]).count("wrong-script"), 1)
            self.assertEqual([p["key"] for p in data["issues"] if p["code"] == "wrong-script"], ["save"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.run(["--strict", "android", src, tgt]), 1)
            # --locale overrides the path.
            code, data = run_json(["--locale", "zh-CN", "android", src, tgt])
            self.assertNotIn("wrong-script", codes(data["issues"]))
            other = write(d, "res/values-xx/strings.xml",
                          '<resources><string name="save">儲存设置</string></resources>')
            code, data = run_json(["android", src, other])
            self.assertNotIn("wrong-script", codes(data["issues"]))
            code, data = run_json(["--locale", "zh-Hant", "android", src, other])
            self.assertEqual(codes(data["issues"]).count("wrong-script"), 1)

    def test_catalog_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            en = write(d, "en.json", json.dumps({"menu": {"save": "Save"}}))
            zh = write(d, "zh_TW.json", json.dumps({"menu": {"save": "保存设置"}}, ensure_ascii=False))
            code, data = run_json(["json", en, zh])
            self.assertEqual([p.get("key") for p in data["issues"] if p["code"] == "wrong-script"],
                             ["menu.save"])
            arb_en = write(d, "app_en.arb", json.dumps({"@@locale": "en", "save": "Save"}))
            arb_zh = write(d, "app_zh_Hant.arb",
                           json.dumps({"@@locale": "zh_Hant", "save": "保存设置"}, ensure_ascii=False))
            code, data = run_json(["arb", arb_en, arb_zh])
            self.assertEqual(codes(data["issues"]).count("wrong-script"), 1)
            props_en = write(d, "messages.properties", "save=Save settings\n")
            props_zh = write(d, "messages_zh_TW.properties", "save=" + "\\" + "u8bbe\n")
            code, data = run_json(["properties", props_en, props_zh])
            self.assertEqual([p["message"][-1] for p in data["issues"] if p["code"] == "wrong-script"],
                             [chr(0x8BBE)])

    def test_text_kind(self):
        with tempfile.TemporaryDirectory() as d:
            en = write(d, "fastlane/metadata/android/en-US/short_description.txt",
                       "Hide your private files and apps with one tap.\n")
            tw = write(d, "fastlane/metadata/android/zh-TW/short_description.txt",
                       "一键隐藏你的隐私文件与应用。\n")
            ok = write(d, "fastlane/metadata/android/zh-HK/short_description.txt",
                       "一鍵隱藏你的私人檔案與應用程式。\n")
            code, data = run_json(["text", en, tw])
            self.assertEqual(code, 0)
            self.assertEqual(codes(data["issues"]), ["wrong-script"])
            self.assertEqual(run_json(["text", en, ok])[1]["issues"], [])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.run(["--strict", "text", en, tw]), 1)


if __name__ == "__main__":
    unittest.main()
