#!/usr/bin/env python3
"""Tests for l10n-guard 0.21.1: linguas-unlisted names the gettext spelling for a file named
with a hyphen, autotools messages use "compile or install", and the GitHub Action passes only
`target` to the project-folder kinds locale-config and linguas.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import l10n_guard as g

HERE = os.path.dirname(os.path.abspath(__file__))
MESON = "i18n.gettext(meson.project_name(), preset: 'glib')\n"
HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def po_text(done=1):
    return HEADER + "".join('msgid "a%d"\nmsgstr "b%d"\n\n' % (i, i) for i in range(done))


def check(files):
    data = dict((k, v.encode("utf-8")) for k, v in files.items())
    return g.check_linguas(sorted(data), data.get)


def action_script():
    """The bash script of the Action's single run step, dedented."""
    with open(os.path.join(HERE, "action.yml"), encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    at = [i for i, x in enumerate(lines) if x.strip() == "run: |"]
    if len(at) != 1:
        raise AssertionError("action.yml has %d run blocks" % len(at))
    indent = len(lines[at[0]]) - len(lines[at[0]].lstrip())
    body = []
    for line in lines[at[0] + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    pad = min(len(x) - len(x.lstrip()) for x in body if x.strip())
    return "\n".join(x[pad:] for x in body) + "\n"


class MessageTest(unittest.TestCase):
    def test_version(self):
        self.assertGreaterEqual(tuple(int(x) for x in g.__version__.split(".")), (0, 21, 1))

    def test_hyphen_name_gets_the_gettext_spelling(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/nb-NO.po": po_text(3)})
        self.assertEqual([(p["code"], p["key"]) for p in problems],
                         [("linguas-unlisted", "nb-NO")])
        msg = problems[0]["message"]
        self.assertIn("po/nb-NO.po has 3 of 3 messages translated", msg)
        self.assertIn("rename po/nb-NO.po to po/nb_NO.po and add 'nb_NO' to po/LINGUAS", msg)
        self.assertNotIn("add 'nb-NO'", msg)

    def test_listed_spelling_still_wins(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "pt_BR\n", "po/pt-BR.po": po_text()})
        unlisted = [p for p in problems if p["code"] == "linguas-unlisted"]
        self.assertEqual(len(unlisted), 1)
        self.assertIn("po/LINGUAS lists 'pt_BR'", unlisted[0]["message"])
        self.assertNotIn("rename", unlisted[0]["message"])

    def test_autotools_wording(self):
        problems, _ = check({
            "configure.ac": "AC_INIT([x], [1])\nAM_GNU_GETTEXT([external])\n",
            "po/LINGUAS": "de\n", "po/de.po": po_text(), "po/cs.po": po_text()})
        self.assertEqual([(p["code"], p["key"]) for p in problems], [("linguas-unlisted", "cs")])
        self.assertIn("so gettext's build rules never compile or install it; add 'cs' to "
                      "po/LINGUAS", problems[0]["message"])

    def test_meson_message_is_unchanged(self):
        problems, _ = check({
            "po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
            "po/cs.po": po_text(2)})
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["message"],
                         "po/cs.po has 2 of 2 messages translated, but po/LINGUAS does not "
                         "list 'cs', so Meson never compiles or installs it; add 'cs' to "
                         "po/LINGUAS if the translation is ready")


@unittest.skipUnless(shutil.which("bash") and shutil.which("python3"),
                     "needs bash and python3, as the Action does")
class ActionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        files = {"po/meson.build": MESON, "po/LINGUAS": "de\n", "po/de.po": po_text(),
                 "po/cs.po": po_text(2)}
        for rel, text in files.items():
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_action(self, kind, strict):
        env = dict(os.environ, L10N_KIND=kind, L10N_SOURCE="", L10N_TARGET=self.root,
                   L10N_STRICT=strict, L10N_SCRIPT=os.path.join(HERE, "l10n_guard.py"))
        return subprocess.run(["bash", "-e", "-c", action_script()], env=env,
                              capture_output=True, text=True, timeout=120)

    def test_linguas_takes_only_target(self):
        p = self.run_action("linguas", "false")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("linguas-unlisted [cs]", p.stdout)
        p = self.run_action("linguas", "true")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)

    def test_locale_config_takes_only_target(self):
        p = self.run_action("locale-config", "false")
        self.assertNotEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertNotIn("unrecognized arguments", p.stderr)


if __name__ == "__main__":
    unittest.main()
