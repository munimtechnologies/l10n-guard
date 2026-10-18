#!/usr/bin/env python3
"""l10n-guard 0.9.0: Laravel lang files (kind: laravel) and :name
placeholders written with the fullwidth colon (lookalike-colon). The
translations are real ones from open-source projects (2026-10-18); the
English sources marked "written for the test" are not. Standard library only.

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

# Written for the test, in the shape of Laravel's validation.php.
VALIDATION_EN = """<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Validation Language Lines
    |--------------------------------------------------------------------------
    */

    'required'             => 'The :attribute field is <strong>required</strong>.',
    'different'            => 'The :attribute and :other must be <strong>different</strong>.',
    'ends_with'            => 'The :attribute must end with one of the following: :values',
    'size'                 => [
        'string'  => 'The :attribute must be <strong>:size characters</strong>.',
    ],
    'attributes' => [],

];
"""
# Akaunting resources/lang/ja-JP/validation.php (06dfa473), these four lines.
AKAUNTING_JA = """<?php

return [
    'required'             => 'The：attributeフィールドは<strong>必須</ strong>です。',
    'different'            => '：attributeと：otherは<strong>異なる</ strong>でなければなりません。',
    'ends_with'            => '：attributeは、次のいずれかで終了する必要があります：：values',
    'size'                 => [
        'string'  => '：attributeは<strong>：size characters </ strong>でなければなりません。',
    ],
    'attributes' => [],
];
"""
# UNIT3D lang/en/email.php and lang/ja/email.php (8b88f4c8), fail-login-line2.
UNIT3D_EN = "<?php\n\nreturn [\n    'fail-login-line2'    => 'This request originated from :ip  ( :host ) at :time',\n];\n"
UNIT3D_JA = "<?php\n\nreturn [\n    'fail-login-line2' => 'この要求は、：ip（：host）at：timeから発生しました',\n];\n"

PARSE = r"""<?php
declare(strict_types=1);
// a comment with 'quotes' and return
# another
return array(
    'single' => 'It\'s a \\ path\n',
    "double" => "Tab\tand \"quotes\" and \$x",
    'joined' => 'one ' . 'two' . "three",
    'call' => trans('other.key'),
    'const' => SOME::CONSTANT,
    'nested' => [
        'deep' => ['x' => 'y'],
        'list' => ['a', 'b'],
        5 => 'five',
    ],
    'mixed' => 'a' . PHP_EOL,
    'empty' => [],
);
"""


def codes(problems):
    return [(p["level"], p["code"], p.get("key")) for p in problems]


class Laravel090Test(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 9, 0))

    def test_parse(self):
        self.assertEqual(g.parse_laravel(PARSE), {
            "single": "It's a \\ path\\n",
            "double": 'Tab\tand "quotes" and $x',
            "joined": "one twothree",
            "call": None,
            "const": None,
            "nested.deep.x": "y",
            "nested.list.0": "a",
            "nested.list.1": "b",
            "nested.5": "five",
            "mixed": None,
        })

    def test_parse_errors(self):
        for text in ("<?php return ['a' => 'b", "<?php echo 'x';", "<?php return 'x';",
                     "<?php return ['a' => 'b' 'c'];"):
            with self.assertRaises(ValueError, msg=text):
                g.parse_laravel(text)

    def test_akaunting(self):
        found = g.check_laravel(VALIDATION_EN, AKAUNTING_JA)
        colon = [(p["level"], p["key"]) for p in found if p["code"] == "lookalike-colon"]
        self.assertEqual(colon, [(g.ERROR, "different"), (g.ERROR, "different"),
                                 (g.ERROR, "ends_with"), (g.ERROR, "ends_with"),
                                 (g.ERROR, "required"),
                                 (g.ERROR, "size.string"), (g.ERROR, "size.string")])
        self.assertEqual([p["key"] for p in found if p["code"] == "tags"],
                         ["different", "required", "size.string"])
        self.assertEqual(len(found), 10)
        required = next(p for p in found if p["key"] == "required" and p["code"] == "lookalike-colon")
        self.assertIn(":attribute is written \"：attribute\"", required["message"])
        self.assertIn("U+FF1A", required["message"])
        values = [p for p in found if p["key"] == "ends_with"][1]
        self.assertIn(":values is written \"：values\"", values["message"])

    def test_unit3d(self):
        found = g.check_laravel(UNIT3D_EN, UNIT3D_JA)
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-colon", "fail-login-line2")] * 3)
        self.assertEqual([p["message"].split()[0] for p in found], [":host", ":ip", ":time"])

    def test_placeholder_dropped(self):
        # UNIT3D lang/ja/user.php, profile-desc; the English is lang/en/user.php.
        found = g._laravel_pair("User :user profile registered on :title",
                                "ユーザー：登録されているユーザープロフィール：title", "profile-desc")
        self.assertEqual(codes(found), [(g.ERROR, "lookalike-colon", "profile-desc"),
                                        (g.ERROR, "placeholder-missing", "profile-desc")])
        self.assertIn(":user", found[1]["message"])

    def test_snipe_it(self):
        # Snipe-IT resources/lang/zh-CN/validation.php, required_unless (source
        # written for the test, as Laravel's English).
        found = g._laravel_pair("The :attribute field is required unless :other is in :values.",
                                "需要：属性字段，除非：other is in：values。", "required_unless")
        self.assertEqual([p["code"] for p in found],
                         ["lookalike-colon", "lookalike-colon", "placeholder-missing"])
        self.assertIn("\"：other\"", found[0]["message"])
        self.assertIn("\"：values\"", found[1]["message"])
        self.assertIn(":attribute", found[2]["message"])

    def test_correct_translations_pass(self):
        self.assertEqual(g._laravel_pair("The :attribute field is required.",
                                         ":attributeは必須です。", "required"), [])
        self.assertEqual(g._laravel_pair(":Attribute must be accepted.",
                                         ":attributeを承認してください", "accepted"), [])

    def test_copy_next_to_the_real_one_is_a_warning(self):
        # Written for the test.
        found = g._laravel_pair("The :attribute field", ":attribute（：attribute）", "k")
        self.assertEqual(codes(found), [(g.WARNING, "lookalike-colon", "k")])

    def test_not_placeholders(self):
        # Written for the test: a time, a URL, mailto: and prose colons.
        found = g._laravel_pair("Time: 10:30, see https://example.com or mailto:info@example.com",
                                "時間：10:30、https://example.com または mailto:info@example.com を参照",
                                "k")
        self.assertEqual(found, [])

    def test_extra_placeholder_is_a_warning(self):
        found = g._laravel_pair("Saved.", ":count 件保存しました。", "k")
        self.assertEqual(codes(found), [(g.WARNING, "placeholder-extra", "k")])

    def test_plural_ranges_are_not_compared(self):
        found = g._laravel_pair("{0} No files|{1} :count file|[2,*] :count files",
                                "[0,*] :count 件のファイル", "files")
        self.assertEqual(found, [])

    def test_other_kinds_do_not_read_colons(self):
        self.assertEqual(g.check_pair("The :attribute field", "The：attribute欄"), [])

    def test_keys(self):
        found = g.check_laravel("<?php return ['a' => 'Hello :name', 'b' => 'Bye'];",
                                "<?php return ['a' => 'こんにちは :name', 'c' => 'x'];")
        self.assertEqual(codes(found), [(g.WARNING, "missing-key", "b"),
                                        (g.WARNING, "extra-key", "c")])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            en, ja = os.path.join(tmp, "en.php"), os.path.join(tmp, "ja.php")
            for path, text in ((en, UNIT3D_EN), (ja, UNIT3D_JA)):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["laravel", en, ja]), 1)
            self.assertIn("ERROR lookalike-colon [fail-login-line2]: :ip is written \"：ip\"",
                          out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(g.run(["--json", "laravel", en, en]), 0)
            self.assertEqual(json.loads(out.getvalue())["errors"], 0)


if __name__ == "__main__":
    unittest.main()
