#!/usr/bin/env python3
"""l10n-guard 0.5.2: placeholders inside markup that is text in strings.xml
(CDATA, &lt;a href="%2$s"&gt;) count; element markup is still dropped.
Standard library only.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import unittest

import l10n_guard as g

# Wikipedia's temp_account_edit_status (values/strings.xml) and shapes its
# translations take (values-de, values-pt, values-ru).
SOURCE = ('<resources><string name="s"><![CDATA[<b>You are using a temporary account.</b> '
          'Your edit will be attributed to %1$s. <a href="%2$s">Learn more</a>.]]></string>'
          '</resources>')
GOOD = ('<resources><string name="s">&lt;b&gt;Du benutzt ein temporäres Konto.&lt;/b&gt; %1$s. '
        '&lt;a href=\\"%2$s\\"&gt;Mehr&lt;/a&gt;.</string></resources>')
BROKEN_PT = ('<resources><string name="s">%1$s. &lt;a href=\\"%2$s2Saiba mais.</string>'
             '</resources>')
SPAN_RU = ('<resources><string name="s">%1$s. &lt;a href=\\"&lt;span class=\\"notranslate\\" '
           'translate=\\"no\\"&gt;%2$s \\"&gt;Узнать больше&lt;/a&gt;.</string></resources>')
WRONG_INDEX = ('<resources><string name="s">%1$s. &lt;a href=\\"%3$s\\"&gt;Mehr&lt;/a&gt;.'
               '</string></resources>')


def errors(problems):
    return [p for p in problems if p["level"] == g.ERROR]


class AndroidText052Test(unittest.TestCase):
    def test_version(self):
        self.assertEqual(g.__version__, "0.5.2")

    def test_cdata_href_placeholder_is_kept(self):
        text = g._android_text(g.parse_android(SOURCE)["s"])
        self.assertIn("%2$s", text)
        self.assertEqual(max(n for n, _ in g.java_formatted(text)), 2)

    def test_wikipedia_translations_do_not_crash(self):
        for xml in (GOOD, BROKEN_PT, SPAN_RU):
            java = [p for p in g.check_android(SOURCE, xml) if p["code"] == "java-format"]
            self.assertEqual(java, [], xml)

    def test_argument_hidden_in_a_link_is_caught(self):
        java = [p for p in g.check_android(SOURCE, WRONG_INDEX) if p["code"] == "java-format"]
        self.assertEqual(len(java), 1)
        self.assertIn("uses argument 3 but the source passes 2", java[0]["message"])

    def test_real_elements_lose_markup_and_attributes(self):
        xml = ('<resources><string name="s">Hi <b>%1$s</b>, <a href="%2$s">more</a> '
               '<xliff:g xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2" id="n">%3$d</xliff:g>'
               '</string></resources>')
        self.assertEqual(g._android_text(g.parse_android(xml)["s"]), "Hi %1$s, more %3$d")

    def test_text_markup_is_kept_literally(self):
        self.assertEqual(g._android_text('<a href=\\"%1$s\\">'), '<a href="%1$s">')
        self.assertEqual(g._android_text("<0>%1$s</0>"), "<0>%1$s</0>")
        self.assertEqual(g._android_text("50 < 60 %1$s"), "50 < 60 %1$s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
