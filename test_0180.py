# Tests for l10n-guard 0.18.0: folder-script and locale-code warnings for Android folders.
# Made with AI agents by MV2 of Munim, Inc. Apache-2.0.
import contextlib
import io
import os
import tempfile
import unittest

import l10n_guard as g

ENGLISH = ["Open settings", "Close window", "Delete message", "Archive message",
           "Choose folder", "Create folder", "Skip for now", "Account not found",
           "Folder name is empty", "Sync with server", "Cancel", "Done"]
WELSH = ["Agor gosodiadau", "Cau ffenestr", "Dileu neges", "Archifo neges", "Dewis ffolder",
         "Creu ffolder", "Hepgor am nawr", "Heb ganfod cyfrif", "Mae enw ffolder yn wag",
         "Cysoni gyda gweinydd", "Diddymu", "Gorffen"]
JAPANESE = ["設定を開く", "ウィンドウを閉じる", "メッセージを削除", "メッセージをアーカイブ",
            "フォルダーを選択", "フォルダーを作成", "今はスキップ", "アカウントが見つかりません",
            "フォルダー名が空です", "サーバーと同期", "キャンセル", "完了"]
LEFTOVER_RU = ["Open the settings", "Close this window", "Delete the message",
               "Archive the message", "Choose a folder", "Create a folder", "Skip it for now",
               "Account was not found", "The folder name is empty", "Sync with the server",
               "Отмена", "Готово"]
KAZAKH_LATIN = ["Parametrlerdi ashu", "Terezeni jabu", "Habarlamany joiu",
                "Habarlamany muraghattau", "Qaltany tandau", "Qalta jasau",
                "Azirshe otkizip jiberu", "Esepjazba tabylmady", "Qalta aty bos",
                "Servermen undestiru", "Bas tartu", "Dayin"]


def xml(values):
    rows = "".join('    <string name="s%d">%s</string>\n' % (i + 1, v)
                   for i, v in enumerate(values))
    return '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n' + rows + "</resources>\n"


SRC = xml(ENGLISH)


def check(values, locale, source=SRC):
    return g.check_folder_script(source, xml(values), locale)


def codes(problems):
    return [p["code"] for p in problems]


class FolderScript(unittest.TestCase):
    def test_welsh_in_arabic_folder(self):
        p = check(WELSH, "app/src/main/res/values-ar/strings.xml")
        self.assertEqual(codes(p), ["folder-script"])
        self.assertEqual(p[0]["level"], g.WARNING)
        self.assertNotIn("key", p[0])
        self.assertIn("12 of 12", p[0]["message"])
        self.assertIn("0 use Arabic script", p[0]["message"])
        self.assertIn("only 0 of them", p[0]["message"])

    def test_japanese_in_belarusian_folder(self):
        p = check(JAPANESE, "res/values-be/strings.xml")
        self.assertEqual(codes(p), ["folder-script"])
        self.assertIn("11 of 12", p[0]["message"])
        self.assertIn("Kana script and 0 in Cyrillic", p[0]["message"])

    def test_english_left_in_russian_folder(self):
        p = check(LEFTOVER_RU, "res/values-ru/strings.xml")
        self.assertEqual(codes(p), ["folder-script"])
        self.assertIn("10 of 12", p[0]["message"])
        self.assertIn("2 use Cyrillic script", p[0]["message"])
        self.assertIn("10 of them reuse", p[0]["message"])
        self.assertIn("untranslated", p[0]["message"])

    def test_below_threshold(self):
        self.assertEqual(check(WELSH[:9] + ENGLISH[9:], "res/values-ar/strings.xml"), [])

    def test_own_script_majority(self):
        source = xml(["Some text"] * 21)
        target = ["Lorem ipsum"] * 10 + ["Пример текста"] * 11
        self.assertEqual(check(target, "res/values-ru/strings.xml", source), [])

    def test_strings_equal_to_source_are_skipped(self):
        self.assertEqual(check(ENGLISH, "res/values-ru/strings.xml"), [])

    def test_latin_kazakh(self):
        p = check(KAZAKH_LATIN, "res/values-kk/strings.xml")
        self.assertEqual(codes(p), ["folder-script"])
        self.assertIn("values-b+kk+Latn", p[0]["message"])
        self.assertEqual(check(KAZAKH_LATIN, "res/values-b+kk+Latn/strings.xml"), [])

    def test_languages_outside_the_table(self):
        for folder in ("values-fr", "values-sr", "values-b+sr+Latn", "values-az", "values-in"):
            self.assertEqual(check(WELSH, "res/%s/strings.xml" % folder), [], folder)

    def test_locale_tag(self):
        self.assertEqual(codes(check(WELSH, "ar")), ["folder-script"])
        self.assertEqual(codes(check(JAPANESE, "be-BY")), ["folder-script"])

    def test_no_locale(self):
        self.assertEqual(check(WELSH, "translations/strings.xml"), [])
        self.assertEqual(check(WELSH, None), [])
        self.assertEqual(check(WELSH, "strings.xml"), [])

    def test_units(self):
        text = ('<resources>\n'
                '  <string name="a">A\\nB</string>\n'
                '  <string name="hidden" translatable="false">x</string>\n'
                '  <string-array name="arr"><item>One</item><item>Two</item></string-array>\n'
                '  <plurals name="files"><item quantity="one">%d file</item>'
                '<item quantity="other">%d files</item></plurals>\n'
                '</resources>\n')
        self.assertEqual(g._fs_units(text), {
            "a": "A\\nB", "arr[0]": "One", "arr[1]": "Two",
            "files:one": "%d file", "files:other": "%d files"})

    def test_placeholders_and_escapes_are_not_letters(self):
        self.assertEqual(g._fs_scripts(g._fs_plain("Привет\\n%1$s {name}")), {"Cyrillic"})


class LocaleCode(unittest.TestCase):
    def test_country_codes(self):
        p = check(ENGLISH, "app/src/main/res/values-ua/strings.xml")
        self.assertEqual(codes(p), ["locale-code"])
        self.assertIn("'ua' is not a language code", p[0]["message"])
        self.assertIn("is uk", p[0]["message"])
        self.assertIn("values-zh-rCN", check(ENGLISH, "res/values-cn/strings.xml")[0]["message"])
        self.assertEqual(codes(check(ENGLISH, "res/values-cz-rCZ/strings.xml")), ["locale-code"])

    def test_real_and_deliberate_codes(self):
        for folder in ("values-qq", "values-zz", "values-in", "values-iw", "values-uk",
                       "values-se", "values-kr"):
            got = codes(check(["Скасувати"] * 12, "res/%s/strings.xml" % folder))
            self.assertNotIn("locale-code", got, folder)
        self.assertEqual(check(["Скасувати"] * 12, "res/values-uk/strings.xml"), [])


class AndroidLocale(unittest.TestCase):
    def test_parse(self):
        cases = {
            "res/values-zh-rTW/strings.xml": ("zh", None),
            "res/values-b+sr+Latn/strings.xml": ("sr", "Latn"),
            "C:\\app\\res\\values-be\\strings.xml": ("be", None),
            "values-ru": ("ru", None),
            "zh-Hant-TW": ("zh", "Hant"),
            "ru": ("ru", None),
            "values/strings.xml": (None, None),
            "res/values-ja-land/strings.xml": (None, None),
            "res/values-night/strings.xml": (None, None),
            "ru.xml": (None, None),
        }
        for text, want in cases.items():
            self.assertEqual(g.android_locale(text), want, text)


class Cli(unittest.TestCase):
    def run_cli(self, folder, values):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "values", "strings.xml")
            tgt = os.path.join(tmp, folder, "strings.xml")
            for path, text in ((src, SRC), (tgt, xml(values))):
                os.makedirs(os.path.dirname(path))
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = g.run(["android", src, tgt])
            return code, out.getvalue()

    def test_folder_script_is_a_warning(self):
        code, out = self.run_cli("values-ar", WELSH)
        self.assertEqual(code, 0)
        self.assertIn("WARNING folder-script", out)

    def test_locale_code_is_a_warning(self):
        code, out = self.run_cli("values-ua", ["Скасувати"] * 12)
        self.assertEqual(code, 0)
        self.assertIn("WARNING locale-code", out)

    def test_clean_folder(self):
        code, out = self.run_cli("values-ru", LEFTOVER_RU[10:] * 6)
        self.assertNotIn("folder-script", out)


class Version(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 18, 0))


if __name__ == "__main__":
    unittest.main()
