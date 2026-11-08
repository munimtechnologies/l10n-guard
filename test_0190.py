# Tests for l10n-guard 0.19.0: the locale-config check (Android per-app language lists).
# Made with AI agents by MV2 of Munim, Inc. Apache-2.0.
import contextlib
import io
import os
import tempfile
import unittest

import l10n_guard as g

NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'
EN = ["Open settings", "Close window", "Delete message", "Archive message", "Choose folder",
      "Create folder", "Skip for now", "Account not found", "Folder name is empty",
      "Sync with server", "Cancel", "Done"]
DE = ["Einstellungen öffnen", "Fenster schließen", "Nachricht löschen", "Nachricht archivieren",
      "Ordner wählen", "Ordner erstellen", "Jetzt überspringen", "Konto nicht gefunden",
      "Ordnername ist leer", "Mit Server synchronisieren", "Abbrechen", "Fertig"]
FR = ["Ouvrir les paramètres", "Fermer la fenêtre", "Supprimer le message",
      "Archiver le message", "Choisir un dossier", "Créer un dossier", "Pas pour le moment",
      "Compte introuvable", "Le nom du dossier est vide", "Synchroniser avec le serveur",
      "Annuler", "Terminé"]
UK = ["Відкрити налаштування", "Закрити вікно", "Видалити повідомлення",
      "Архівувати повідомлення", "Вибрати теку", "Створити теку", "Пропустити зараз",
      "Обліковий запис не знайдено", "Назва теки порожня", "Синхронізувати з сервером",
      "Скасувати", "Готово"]
KO = ["설정 열기", "창 닫기", "메시지 삭제", "메시지 보관", "폴더 선택", "폴더 만들기",
      "지금은 건너뛰기", "계정을 찾을 수 없음", "폴더 이름이 비어 있음", "서버와 동기화", "취소", "완료"]
DA = ["Åbn indstillinger", "Luk vindue", "Slet besked", "Arkivér besked", "Vælg mappe",
      "Opret mappe", "Spring over for nu", "Konto ikke fundet", "Mappenavn er tomt",
      "Synkroniser med server", "Annuller", "Færdig"]
BG = ["Отвори настройките", "Затвори прозореца", "Изтрий съобщението", "Архивирай съобщението",
      "Избери папка", "Създай папка", "Пропусни засега", "Акаунтът не е намерен",
      "Името на папката е празно", "Синхронизирай със сървъра", "Отказ", "Готово"]
WELSH = ["Agor gosodiadau", "Cau ffenestr", "Dileu neges", "Archifo neges", "Dewis ffolder",
         "Creu ffolder", "Hepgor am nawr", "Heb ganfod cyfrif", "Mae enw ffolder yn wag",
         "Cysoni gyda gweinydd", "Diddymu", "Gorffen"]
EMPTY = b'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n</resources>\n'
APP = "app/src/main/"
RES = APP + "res/"


def manifest(name="locales_config"):
    return ('<manifest %s>\n<application android:localeConfig="@xml/%s"/>\n</manifest>\n'
            % (NS, name)).encode("utf-8")


def locales(*tags):
    body = "".join('<locale android:name="%s"/>' % t for t in tags)
    return ('<?xml version="1.0" encoding="utf-8"?>\n<locale-config %s>%s</locale-config>\n'
            % (NS, body)).encode("utf-8")


def strings(texts):
    rows = "".join('<string name="s%d">%s</string>' % (i + 1, t) for i, t in enumerate(texts))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<resources>%s</resources>\n'
            % rows).encode("utf-8")


def project(extra=None, listed=("en", "de", "fr")):
    files = {APP + "AndroidManifest.xml": manifest(),
             RES + "xml/locales_config.xml": locales(*listed),
             RES + "values/strings.xml": strings(EN),
             RES + "values-de/strings.xml": strings(DE),
             RES + "values-fr/strings.xml": strings(FR),
             "app/build.gradle": b"android { }\n"}
    files.update(extra or {})
    return {k: v for k, v in files.items() if v is not None}


def check(files):
    return g.check_locale_config(sorted(files), files.get)


def found(problems):
    return sorted((p["code"], p["key"]) for p in problems)


class Basics(unittest.TestCase):
    def test_matching_list_is_clean(self):
        problems, stats = check(project())
        self.assertEqual(problems, [])
        self.assertEqual(stats, {"lists checked": 1, "lists skipped": 0,
                                 "orphan checks skipped": 0, "phantom checks skipped": 0})

    def test_orphan(self):
        problems, _ = check(project({RES + "values-uk/strings.xml": strings(UK)}))
        self.assertEqual(found(problems), [("locale-config-orphan", "uk")])
        self.assertEqual(problems[0]["level"], g.WARNING)
        self.assertIn("values-uk has 12 of this module's 12 strings translated", problems[0]["message"])
        self.assertIn("does not list 'uk'", problems[0]["message"])

    def test_orphan_needs_half_the_strings(self):
        half, _ = check(project({RES + "values-ko/strings.xml": strings(KO[:6])}))
        self.assertEqual(found(half), [("locale-config-orphan", "ko")])
        less, _ = check(project({RES + "values-ko/strings.xml": strings(KO[:5])}))
        self.assertEqual(less, [])

    def test_phantom_without_folder(self):
        problems, _ = check(project(listed=("en", "de", "fr", "ja")))
        self.assertEqual(found(problems), [("locale-config-phantom", "ja")])
        self.assertIn("lists 'ja', but no values-ja folder in the project has translated strings",
                      problems[0]["message"])

    def test_phantom_from_empty_file(self):
        problems, _ = check(project({RES + "values-uk/strings.xml": EMPTY},
                                    listed=("en", "de", "fr", "uk")))
        self.assertEqual(found(problems), [("locale-config-phantom", "uk")])
        self.assertIn("its values-uk strings files have no translated strings",
                      problems[0]["message"])

    def test_country_code_in_list(self):
        problems, _ = check(project({RES + "values-da/strings.xml": strings(DA)},
                                    listed=("en", "de", "fr", "dk")))
        self.assertEqual(found(problems), [("locale-config-code", "dk"),
                                           ("locale-config-orphan", "da")])
        code = [p for p in problems if p["code"] == "locale-config-code"][0]
        self.assertIn("lists 'dk', which is not a language code (the language code is da)",
                      code["message"])

    def test_resource_folder_spelling(self):
        problems, _ = check(project(listed=("en", "de", "fr-rFR")))
        self.assertEqual(found(problems), [("locale-config-tag", "fr")])
        self.assertIn("such as 'fr-FR'", problems[0]["message"])

    def test_translation_in_a_library_module_is_not_a_phantom(self):
        problems, _ = check(project({"lib/src/main/res/values/strings.xml": strings(["Hello"]),
                                     "lib/src/main/res/values-ja/strings.xml": strings(["こんにちは"])},
                                    listed=("en", "de", "fr", "ja")))
        self.assertEqual(problems, [])

    def test_build_outputs_are_not_read(self):
        problems, _ = check(project({"app/build/generated/res/values/strings.xml": strings(EN),
                                     "app/build/generated/res/values-it/strings.xml":
                                         strings(["Apri le impostazioni"])},
                                    listed=("en", "de", "fr", "it")))
        self.assertEqual(found(problems), [("locale-config-phantom", "it")])

    def test_no_list(self):
        files = project()
        files[APP + "AndroidManifest.xml"] = b"<manifest><application/></manifest>"
        self.assertEqual(check(files), ([], {"lists checked": 0, "lists skipped": 0,
                                             "orphan checks skipped": 0,
                                             "phantom checks skipped": 0}))


class LanguageFilters(unittest.TestCase):
    def test_kotlin_locale_filters(self):
        kts = (b'android {\n  androidResources {\n'
               b'    localeFilters += listOf("en", "de", "fr", "ko")\n  }\n}\n')
        problems, _ = check(project({"app/build.gradle": None, "app/build.gradle.kts": kts,
                                     RES + "values-uk/strings.xml": strings(UK),
                                     RES + "values-ko/strings.xml": strings(KO)}))
        self.assertEqual(found(problems), [("locale-config-orphan", "ko")])

    def test_groovy_res_configs(self):
        gradle = (b'android {\n  defaultConfig {\n'
                  b'    resConfigs "en", "de", "fr" // keep in sync\n  }\n}\n')
        problems, _ = check(project({"app/build.gradle": gradle,
                                     RES + "values-uk/strings.xml": strings(UK)}))
        self.assertEqual(problems, [])

    def test_listed_language_dropped_by_filter(self):
        gradle = b'android {\n  defaultConfig {\n    resConfigs "en", "de"\n  }\n}\n'
        problems, _ = check(project({"app/build.gradle": gradle}))
        self.assertEqual(found(problems), [("locale-config-phantom", "fr")])
        self.assertIn("the build's language filter (app/build.gradle) leaves its translation out",
                      problems[0]["message"])

    def test_unreadable_filter_skips_orphans(self):
        gradle = b"android { defaultConfig { resourceConfigurations += supportedLocales } }\n"
        problems, stats = check(project({"app/build.gradle": gradle,
                                         RES + "values-uk/strings.xml": strings(UK)}))
        self.assertEqual(problems, [])
        self.assertEqual(stats["orphan checks skipped"], 1)

    def test_filter_in_root_build_file_skips_orphans(self):
        root = b'subprojects { android { defaultConfig { resConfigs "en" } } }\n'
        problems, stats = check(project({"build.gradle": root,
                                         RES + "values-uk/strings.xml": strings(UK)}))
        self.assertEqual(problems, [])
        self.assertEqual(stats["orphan checks skipped"], 1)

    def test_filter_statements(self):
        st = g._lc_filter_statements
        self.assertEqual(st('resConfigs "en", "xxhdpi"\n'), [("resConfigs", ["en"], True)])
        self.assertEqual(st('resConfigs "auto"\n'), [("resConfigs", [], False)])
        self.assertEqual(st('// resConfigs "en"\n'), [])
        self.assertEqual(st('localeFilters.addAll(\n    listOf(\n        "en",\n'
                            '        "pt-rBR",\n        "b+sr+Latn",\n    )\n)\n'),
                         [("localeFilters", ["en", "pt-rBR", "b+sr+Latn"], True)])
        self.assertEqual(st('resourceConfigurations += listOf("en") + extraLocales\n'),
                         [("resourceConfigurations", ["en"], False)])
        # Glob strings are not comments.
        self.assertEqual(st('packaging { excludes += "/META-INF/*.kotlin_module" }\n'
                            'resConfigs "en", "de"\nfoo("**/x")\n'),
                         [("resConfigs", ["en", "de"], True)])
        # Groovy list syntax and a keyword after a dot, as real projects write them.
        self.assertEqual(st('    // Replaces the removed defaultConfig.resConfigs\n'
                            '    localeFilters += ["en", "pt-rBR", "zh-rCN"]\n'),
                         [("localeFilters", ["en", "pt-rBR", "zh-rCN"], True)])
        self.assertEqual(st('androidResources.localeFilters += arrayOf(\n    "en",\n    "ar",\n)\n'),
                         [("localeFilters", ["en", "ar"], True)])

    def test_uncomment_keeps_strings(self):
        self.assertEqual(g._lc_uncomment('a = "x // y" // c\nb /* z\n */ c\n'),
                         'a = "x // y" \nb \n c\n')


class DefaultLanguage(unittest.TestCase):
    def test_french_default(self):
        files = project({RES + "values/strings.xml": strings(FR),
                         RES + "values-en/strings.xml": strings(EN),
                         RES + "values-fr/strings.xml": None}, listed=("fr", "en", "de"))
        self.assertEqual(check(files)[0], [])
        rep = g.locale_config_lists(sorted(files), files.get)[0]
        self.assertEqual((rep["default"], rep["default_how"]), ("fr", "values-en differs"))

    def test_bulgarian_default(self):
        files = project({RES + "values/strings.xml": strings(BG),
                         RES + "values-en/strings.xml": strings(EN),
                         RES + "values-de/strings.xml": None, RES + "values-fr/strings.xml": None},
                        listed=("bg", "en"))
        self.assertEqual(check(files)[0], [])
        rep = g.locale_config_lists(sorted(files), files.get)[0]
        self.assertEqual(rep["default_how"], "script")
        self.assertIn("bg", rep["default"].split())

    def test_unnamed_default_skips_phantoms(self):
        files = project({RES + "values/strings.xml": strings(WELSH),
                         RES + "values-en/strings.xml": strings(EN),
                         RES + "values-de/strings.xml": None, RES + "values-fr/strings.xml": None},
                        listed=("cy", "en", "ja"))
        problems, stats = check(files)
        self.assertEqual(problems, [])
        self.assertEqual(stats["phantom checks skipped"], 1)

    def test_resources_properties(self):
        files = project({RES + "resources.properties": b"unqualifiedResLocale=de-DE\n",
                         RES + "values/strings.xml": strings(DE),
                         RES + "values-de/strings.xml": None, RES + "values-en/strings.xml":
                             strings(EN)}, listed=("de", "en", "fr"))
        self.assertEqual(check(files)[0], [])


class SkippedLists(unittest.TestCase):
    def test_string_references(self):
        problems, stats = check(project(listed=("@string/english_tag", "@string/german_tag")))
        self.assertEqual(problems, [])
        self.assertEqual((stats["lists checked"], stats["lists skipped"]), (0, 1))

    def test_generated_list(self):
        gen = b"android {\n  androidResources {\n    generateLocaleConfig = true\n  }\n}\n"
        problems, stats = check(project({"app/build.gradle": gen},
                                        listed=("en", "de", "fr", "ja")))
        self.assertEqual((problems, stats["lists skipped"]), ([], 1))
        off = b"android {\n  androidResources {\n    // generateLocaleConfig = true\n  }\n}\n"
        problems, stats = check(project({"app/build.gradle": off},
                                        listed=("en", "de", "fr", "ja")))
        self.assertEqual(found(problems), [("locale-config-phantom", "ja")])

    def test_list_written_by_the_build(self):
        task = b'tasks.register("w") { outputs.file("src/main/res/xml/locales_config.xml") }\n'
        problems, stats = check(project({"app/build.gradle": task},
                                        listed=("en", "de", "fr", "ja")))
        self.assertEqual((problems, stats["lists skipped"]), ([], 1))


class CommandLine(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = g.run(args)
        return code, out.getvalue()

    def test_cli(self):
        files = project({RES + "values-uk/strings.xml": strings(UK)})
        with tempfile.TemporaryDirectory() as tmp:
            for rel, data in files.items():
                path = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(data)
            code, out = self.run_cli(["locale-config", tmp])
            self.assertEqual(code, 0)
            self.assertIn("WARNING locale-config-orphan [uk]: values-uk has 12", out)
            self.assertIn("1 lists checked", out)
            self.assertIn("0 error(s), 1 warning(s)", out)
            self.assertEqual(self.run_cli(["--strict", "locale-config", tmp])[0], 1)
            self.assertEqual(self.run_cli(["locale-config", os.path.join(tmp, "nope")])[0], 2)


if __name__ == "__main__":
    unittest.main()
