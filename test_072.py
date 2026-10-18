#!/usr/bin/env python3
"""l10n-guard 0.7.2: markup that is text in strings.xml (&lt;/a&gt;, CDATA)
is kept whole in the runtime text; only real elements are dropped. Text
only: placeholder verdicts are the same as before. Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import copy
import unittest

import l10n_guard as g

# Wikimedia Commons Android, about_improve at commit 66ad8cbd (values/ and
# values-hsb/). The Upper Sorbian text has two escaped links and no %1$s; its
# "%20A" is what String.format trips on.
SOURCE = ('<resources><string name="about_improve">Create a new &lt;a href=\\"%1$s\\"&gt;GitHub '
          'issue&lt;/a&gt; for bug reports and suggestions.</string></resources>')
HSB = ('<resources><string name="about_improve" fuzzy="true">Žórłowy kod na &lt;a '
       'href=\\"https://github.com/commons-app/apps-android-commons\\"&gt;GitHub&lt;/a&gt;. '
       'Zdźělenja wo programowych zmylkach na &lt;a '
       'href=\\"https://bugzilla.wikimedia.org/enter_bug.cgi?product=Commons%20App\\"&gt;'
       'Bugzilla&lt;/a&gt;.</string></resources>')
HSB_RUNTIME = ('Žórłowy kod na <a href="https://github.com/commons-app/apps-android-commons">GitHub</a>. '
               'Zdźělenja wo programowych zmylkach na '
               '<a href="https://bugzilla.wikimedia.org/enter_bug.cgi?product=Commons%20App">Bugzilla</a>.')
HSB_RUNTIME_071 = ('Žórłowy kod na <a href="https://github.com/commons-app/apps-android-commons">GitHub. '
                   'Zdźělenja wo programowych zmylkach na '
                   '<a href="https://bugzilla.wikimedia.org/enter_bug.cgi?product=Commons%20App">Bugzilla.')


def text_of(xml, key):
    return g._android_text(g.parse_android(xml)[key])


class AndroidText072Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 7, 2))

    def test_escaped_links_keep_their_closing_tags(self):
        self.assertEqual(text_of(HSB, "about_improve"), HSB_RUNTIME)
        self.assertEqual(text_of(SOURCE, "about_improve"),
                         'Create a new <a href="%1$s">GitHub issue</a> for bug reports and suggestions.')

    def test_plain_strings_keep_the_old_rule(self):
        # A plain string can't tell an element's <a> from text, as before.
        parsed = g.parse_android(HSB)["about_improve"]
        self.assertEqual(g._android_text(str(parsed)), HSB_RUNTIME_071)
        self.assertEqual(g._android_text("Hello <b>%1$s</b>"), "Hello %1$s")

    def test_parsed_text_is_unchanged(self):
        parsed = g.parse_android(HSB)["about_improve"]
        self.assertIsInstance(parsed, str)
        self.assertEqual(parsed.count("</a>"), 2)
        self.assertEqual(parsed.count('href=\\"'), 2)
        self.assertEqual(copy.copy(parsed).runtime, parsed.runtime)

    def test_verdicts_are_unchanged(self):
        new = g.check_android(SOURCE, HSB)
        parse = g.parse_android
        try:
            g.parse_android = lambda text: {k: str(v) for k, v in parse(text).items()}
            old = g.check_android(SOURCE, HSB)
        finally:
            g.parse_android = parse
        # Messages may quote the text around a placeholder, which now keeps </a>.
        verdicts = lambda problems: [(p["level"], p["code"], p.get("key")) for p in problems]
        self.assertEqual(verdicts(new), verdicts(old))
        # "%20A" reads as a %A (decimal) where the source passes %1$s, so
        # String.format throws unless the app passes a number: a warning.
        self.assertTrue(any(p["code"] == "java-format-type" and p["level"] == g.WARNING
                            for p in new))

    def test_cdata_and_elements_together(self):
        xml = ('<resources><string name="s"><![CDATA[<b>Bold</b> %1$s]]> and <b>%2$d</b>'
               '</string></resources>')
        self.assertEqual(text_of(xml, "s"), "<b>Bold</b> %1$s and %2$d")

    def test_plurals_and_arrays(self):
        xml = ('<resources><plurals name="p"><item quantity="other">%d &lt;i&gt;files&lt;/i&gt;'
               '</item></plurals><string-array name="a"><item>&lt;b&gt;x&lt;/b&gt; <b>y</b>'
               '</item></string-array></resources>')
        self.assertEqual(text_of(xml, "p[other]"), "%d <i>files</i>")
        self.assertEqual(text_of(xml, "a[0]"), "<b>x</b> y")


if __name__ == "__main__":
    unittest.main(verbosity=2)
