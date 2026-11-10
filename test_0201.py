# Tests for l10n-guard 0.20.1: the locale-config check leaves values files named
# donottranslate*.xml (which Android Lint treats as untranslatable) out of its string counts.
# Made with AI agents by MV2 of Munim, Inc. Apache-2.0.
import unittest

import l10n_guard as g
from test_0190 import EN, RES, UK, check, found, project, strings


def fixed(texts, prefix="fixed"):
    """A values file of strings named fixed1, fixed2, ... (no clash with strings())."""
    rows = "".join('<string name="%s%d">%s</string>' % (prefix, i + 1, t)
                   for i, t in enumerate(texts))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<resources>%s</resources>\n'
            % rows).encode("utf-8")


FIXED_EN = ["Fixed text number %d" % (i + 1) for i in range(12)]
FIXED_UK = ["Фіксований текст номер %d" % (i + 1) for i in range(12)]
PART_UK = UK[:5] + EN[5:]   # counts 7 of 12 (see test_0200)


class Version(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 20, 1))


class DoNotTranslateFiles(unittest.TestCase):
    def test_name_rule(self):
        self.assertTrue(g._lc_dnt("donottranslate.xml"))
        self.assertTrue(g._lc_dnt("donottranslate-cities.xml"))
        self.assertFalse(g._lc_dnt("strings.xml"))
        self.assertFalse(g._lc_dnt("constants.xml"))

    def test_left_out_of_the_module_count(self):
        problems, _ = check(project({RES + "values/donottranslate.xml": fixed(FIXED_EN),
                                     RES + "values-uk/strings.xml": strings(PART_UK)}))
        self.assertEqual(found(problems), [("locale-config-orphan", "uk")])
        self.assertIn("values-uk has 7 of this module's 12 strings translated",
                      problems[0]["message"])

    def test_other_files_still_counted(self):
        # The same fixed strings in a file with another name raise the module's count to 24,
        # and 7 translated strings are less than half of that.
        problems, _ = check(project({RES + "values/constants.xml": fixed(FIXED_EN),
                                     RES + "values-uk/strings.xml": strings(PART_UK)}))
        self.assertEqual(problems, [])

    def test_left_out_of_the_translation_count(self):
        problems, _ = check(project({RES + "values/donottranslate.xml": fixed(FIXED_EN),
                                     RES + "values-uk/donottranslate.xml": fixed(FIXED_UK),
                                     RES + "values-uk/strings.xml": strings(PART_UK)}))
        self.assertEqual(found(problems), [("locale-config-orphan", "uk")])
        self.assertIn("values-uk has 7 of this module's 12 strings translated",
                      problems[0]["message"])

    def test_only_donottranslate_shared_is_not_a_translation(self):
        # A folder that shares only donottranslate.xml with the default folder is not counted
        # as a translation, so its listed language is a phantom.
        problems, _ = check(project({RES + "values/donottranslate.xml": fixed(FIXED_EN),
                                     RES + "values-uk/donottranslate.xml": fixed(FIXED_UK)},
                                    listed=("en", "de", "fr", "uk")))
        self.assertEqual(found(problems), [("locale-config-phantom", "uk")])


if __name__ == "__main__":
    unittest.main()
