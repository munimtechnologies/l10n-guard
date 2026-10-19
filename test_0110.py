#!/usr/bin/env python3
"""l10n-guard 0.11.0: reading-leak, a Japanese translation that keeps a
word's katakana reading between fullwidth number signs. The unit cases are
P4 of the census's mt-artifacts/READING-LEAK-PREREG.md, written before the
code; the translations are real ones from nostrmo's lib/l10n/intl_ja.arb
(94b8c64) unless marked "written for the test". Standard library only.

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

LEAK = [(g.WARNING, "reading-leak", "k")]


def codes(problems):
    return [(p["level"], p["code"], p.get("key")) for p in problems]


class ReadingLeak0110Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 11, 0))

    def test_flagged(self):
        # P4: flagged.
        found = g.check_pair("load", "ロード＃ロード＃", "k")
        self.assertEqual(codes(found), LEAK)
        self.assertIn("＃ロード＃", found[0]["message"])
        found = g.check_pair("Delete", "削除＃サクジョ＃", "k")
        self.assertEqual(codes(found), LEAK)
        self.assertTrue(found[0]["message"].startswith("＃サクジョ＃: a katakana reading"))

    def test_not_flagged(self):
        # P4: not flagged.
        self.assertEqual(g._reading_leak("Rule 1", "ルール＃1", "k"), [])
        self.assertEqual(g._reading_leak("Tag", "＃タグ", "k"), [])
        self.assertEqual(g._reading_leak("{count, plural, other {{count} items}}",
                                         "{count, plural, other {＃件}}", "k"), [])
        self.assertEqual(g._reading_leak("Delete", "＃サクジョ＃", "k"), [])
        self.assertEqual(g._reading_leak("Delete #tag", "削除＃サクジョ＃", "k"), [])
        self.assertEqual(g._reading_leak("Delete ＃tag", "削除＃サクジョ＃", "k"), [])

    def test_known_miss(self):
        # P2: a reading in hiragana with no signs is ordinary-looking Japanese.
        self.assertEqual(g.check_pair("Search", "検索けんさく", "k"), [])

    def test_more_than_one(self):
        # Written for the test.
        found = g._reading_leak("Delete note", "削除＃サクジョ＃ 動的＃ドウテキ＃", "k")
        self.assertEqual(codes(found), LEAK)
        self.assertIn("＃サクジョ＃, ＃ドウテキ＃", found[0]["message"])

    def test_space_before_sign(self):
        # Written for the test: a space before the sign isn't a word's reading.
        self.assertEqual(g._reading_leak("Delete", "削除 ＃サクジョ＃", "k"), [])

    def test_arb(self):
        en = {"@@locale": "en", "Delete": "Delete", "Search": "Search"}
        ja = {"@@locale": "ja", "Delete": "削除＃サクジョ＃", "Search": "検索けんさく"}
        self.assertEqual(codes(g.check_arb(en, ja)), [(g.WARNING, "reading-leak", "Delete")])

    def test_rails_and_laravel_keep_it(self):
        # Their pairs keep only some check_pair codes; reading-leak is one.
        self.assertEqual(codes(g._rails_pair("Delete", "削除＃サクジョ＃", "k")), LEAK)
        self.assertEqual(codes(g._laravel_pair("Delete", "削除＃サクジョ＃", "k")), LEAK)
        self.assertEqual(codes(g._rails_pair("Delete %{name}", "%{name} を削除＃サクジョ＃", "k")),
                         LEAK)

    def test_symfony(self):
        self.assertEqual(codes(g._symfony_pair("Delete %name%", "%name% を削除＃サクジョ＃", "k")),
                         LEAK)

    def test_qt(self):
        # Written for the test.
        ts = ('<TS version="2.1" language="ja"><context><name>Main</name>'
              '<message><source>Delete</source><translation>削除＃サクジョ＃</translation></message>'
              '<message><source>Search</source><translation>検索けんさく</translation></message>'
              '</context></TS>')
        problems, stats = g.check_qt(ts)
        self.assertEqual(codes(problems), [(g.WARNING, "reading-leak", "Main: Delete")])
        self.assertEqual(stats["finished"], 2)

    def test_android(self):
        # Written for the test.
        en = '<resources><string name="delete">Delete</string></resources>'
        ja = '<resources><string name="delete">削除＃サクジョ＃</string></resources>'
        self.assertIn((g.WARNING, "reading-leak", "delete"), codes(g.check_android(en, ja)))

    def test_documents(self):
        # Written for the test.
        en = '<html lang="en"><body><p>Delete</p></body></html>'
        ja = '<html lang="ja"><body><p>削除＃サクジョ＃</p></body></html>'
        self.assertIn((g.WARNING, "reading-leak", None), codes(g.check_document(en, ja, "html")))
        # A Markdown heading is a # in the source, so nothing is said.
        found = g.check_document("# Delete\n", "# 削除＃サクジョ＃\n", "md")
        self.assertNotIn("reading-leak", [p["code"] for p in found])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, data in (("en.json", {"Delete": "Delete"}), ("ja.json", {"Delete": "削除＃サクジョ＃"})):
                paths[name] = os.path.join(tmp, name)
                with open(paths[name], "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = g.run(["json", paths["en.json"], paths["ja.json"]])
            self.assertEqual(code, 0)
            self.assertIn("WARNING reading-leak [Delete]: ＃サクジョ＃", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = g.run(["--strict", "json", paths["en.json"], paths["ja.json"]])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
