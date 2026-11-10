# Tests for l10n-guard 0.20.0: the locale-config check counts only real translations (not
# untranslated copies of the default text) and does not report phantom languages for apps
# whose interface text lives outside Android's res/ folders.
# Made with AI agents by MV2 of Munim, Inc. Apache-2.0.
import unittest

import l10n_guard as g
from test_0190 import EN, RES, UK, check, found, project, strings


def moved(files, pre):
    """The same Android project inside a folder (android/ of a Flutter or JavaScript app)."""
    return {pre + k: v for k, v in files.items()}


def report(files):
    return g.locale_config_lists(sorted(files), files.get)[0]


class Version(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 20, 0))


class WhatCountsAsTranslated(unittest.TestCase):
    def test_count_function(self):
        self.assertEqual(g._lc_count({"a": "Hallo Welt", "b": "Open settings", "c": "OK",
                                      "d": "Extra"},
                                     {"a": "Hello world", "b": "Open settings", "c": "OK"}),
                         (2, 1))
        self.assertEqual(g._lc_count({"x": "%1$s – %2$s"}, {"x": "%1$s – %2$s"}), (1, 0))
        self.assertEqual(g._lc_count({}, {"a": "Hello world"}), (0, 0))

    def test_english_copy_is_not_an_orphan(self):
        problems, _ = check(project({RES + "values-fa/strings.xml": strings(EN)}))
        self.assertEqual(problems, [])

    def test_english_copy_listed_is_a_phantom(self):
        problems, _ = check(project({RES + "values-fa/strings.xml": strings(EN)},
                                    listed=("en", "de", "fr", "fa")))
        self.assertEqual(found(problems), [("locale-config-phantom", "fa")])
        self.assertIn("its values-fa strings files have no translated strings "
                      "(empty, or copies of the default text)", problems[0]["message"])

    def test_partly_translated_counts_only_translated_strings(self):
        # 5 Ukrainian strings, 5 English sentences left as they were, and the one-word
        # "Cancel" and "Done" left equal: 7 of 12 count.
        problems, _ = check(project({RES + "values-uk/strings.xml": strings(UK[:5] + EN[5:])}))
        self.assertEqual(found(problems), [("locale-config-orphan", "uk")])
        self.assertIn("values-uk has 7 of this module's 12 strings translated",
                      problems[0]["message"])
        self.assertIn("(untranslated copies of default sentences not counted)",
                      problems[0]["message"])
        less, _ = check(project({RES + "values-uk/strings.xml": strings(UK[:3] + EN[3:])}))
        self.assertEqual(less, [])


class TextOutsideRes(unittest.TestCase):
    def test_flutter_app_skips_phantoms(self):
        files = moved(project(listed=("en", "de", "fr", "az")), "android/")
        self.assertEqual(found(check(files)[0]), [("locale-config-phantom", "az")])
        files["pubspec.yaml"] = b"name: demo\n"
        problems, stats = check(files)
        self.assertEqual(problems, [])
        self.assertEqual(stats["phantom checks skipped"], 1)
        self.assertTrue(report(files)["phantoms"].startswith(
            "skipped: Flutter app (pubspec.yaml)"))

    def test_javascript_app_skips_phantoms_but_not_orphans(self):
        files = moved(project({RES + "values-uk/strings.xml": strings(UK)},
                              listed=("en", "de", "fr", "ja")), "apps/mobile/android/")
        files["apps/mobile/package.json"] = b"{}\n"
        problems, stats = check(files)
        self.assertEqual(found(problems), [("locale-config-orphan", "uk")])
        self.assertEqual(stats["phantom checks skipped"], 1)
        self.assertTrue(report(files)["phantoms"].startswith(
            "skipped: JavaScript app (apps/mobile/package.json"))

    def test_arb_catalogs_skip_phantoms(self):
        files = project(listed=("en", "de", "fr", "az"))
        files["lib/l10n/app_az.arb"] = b"{}\n"
        problems, stats = check(files)
        self.assertEqual(problems, [])
        self.assertEqual(stats["phantom checks skipped"], 1)

    def test_catalog_for_the_language_elsewhere(self):
        files = project(listed=("en", "de", "fr", "ja", "ko", "it"))
        files["app/src/main/assets/locales/ja/translation.json"] = b"{}\n"
        files["i18n/ko.json"] = b"{}\n"
        files["shared/src/commonMain/composeResources/values-it/strings.xml"] = strings(["Apri"])
        problems, stats = check(files)
        self.assertEqual(problems, [])
        self.assertEqual(stats["phantom checks skipped"], 0)
        rep = report(files)
        self.assertEqual(rep["phantoms"], "checked")
        self.assertEqual(rep["phantoms_elsewhere"],
                         ["it (shared/src/commonMain/composeResources/values-it/strings.xml)",
                          "ja (app/src/main/assets/locales/ja/translation.json)",
                          "ko (i18n/ko.json)"])

    def test_store_listings_and_docs_are_not_catalogs(self):
        files = project(listed=("en", "de", "fr", "ja"))
        files["fastlane/metadata/android/ja-JP/full_description.txt"] = b"x\n"
        files["fastlane/metadata/android/ja/strings.json"] = b"{}\n"
        files["docs/ja/index.md"] = b"x\n"
        self.assertEqual(found(check(files)[0]), [("locale-config-phantom", "ja")])

    def test_catalog_langs(self):
        got = g._lc_catalog_langs([
            "po/fr.po", "locale/de/LC_MESSAGES/app.po", "lib/l10n/intl_pt_BR.arb",
            "web/i18n/zh-Hans.json", "src/main/java/de/x/Y.java", "README.md", "assets/index.js",
            "MR/es/strings.xml", "app/src/main/res/values-sv/strings.xml"])
        self.assertEqual({k: v for k, v in got.items() if k in g._LC_ISO639_1},
                         {"fr": "po/fr.po", "de": "locale/de/LC_MESSAGES/app.po",
                          "pt": "lib/l10n/intl_pt_BR.arb", "zh": "web/i18n/zh-Hans.json",
                          "es": "MR/es/strings.xml"})


if __name__ == "__main__":
    unittest.main()
