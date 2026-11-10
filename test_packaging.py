#!/usr/bin/env python3
"""l10n-guard packaging: pyproject.toml installs l10n_guard.py, and only it,
as an `l10n-guard` command; .pre-commit-hooks.yaml runs that command with the
user's own arguments; the install section of README.md names the version in
l10n_guard.py. The end-to-end check (pip install, wheel contents, a real
pre-commit run) was run before release; this file needs only the standard
library.

Licensed under the Apache License, Version 2.0 (Apache-2.0).
Made by MV2 of Munim, Inc. with AI agents.
"""

import os
import re
import unittest

import l10n_guard as g

HERE = os.path.dirname(os.path.abspath(__file__))

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


@unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
class PyprojectTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(HERE, "pyproject.toml"), "rb") as f:
            self.data = tomllib.load(f)

    def test_license(self):
        self.assertEqual(self.data["project"]["license"], "Apache-2.0")
        self.assertEqual(self.data["project"]["license-files"], ["LICENSE"])

    def test_only_the_module_is_packaged(self):
        self.assertEqual(self.data["tool"]["setuptools"]["py-modules"], ["l10n_guard"])

    def test_command_points_at_run(self):
        target = self.data["project"]["scripts"]["l10n-guard"]
        self.assertEqual(target, "l10n_guard:run")
        self.assertTrue(callable(getattr(g, target.split(":")[1])))

    def test_version_comes_from_the_module(self):
        self.assertEqual(self.data["project"]["dynamic"], ["version"])
        self.assertEqual(self.data["tool"]["setuptools"]["dynamic"]["version"],
                         {"attr": "l10n_guard.__version__"})
        self.assertRegex(g.__version__, r"^\d+\.\d+\.\d+$")


class PreCommitHookTest(unittest.TestCase):
    def setUp(self):
        self.lines = [line.strip() for line in read(".pre-commit-hooks.yaml").splitlines()]

    def test_one_hook(self):
        self.assertEqual([x for x in self.lines if x.startswith("- id:")], ["- id: l10n-guard"])

    def test_runs_the_command_with_user_args(self):
        for line in ("entry: l10n-guard", "language: python", "pass_filenames: false"):
            self.assertIn(line, self.lines)


class ReadmeInstallTest(unittest.TestCase):
    def setUp(self):
        path = os.path.join(HERE, "README.md")
        text = read("README.md") if os.path.exists(path) else ""
        if "## Install with pip or pre-commit" not in text:
            self.skipTest("README.md has no install section here")
        self.text = text

    def test_pip_line_names_this_version(self):
        found = re.findall(r"l10n-guard@v([\d.]+)\"", self.text)
        self.assertTrue(found)
        self.assertEqual(set(found), {g.__version__})

    def test_hook_rev_names_this_version(self):
        self.assertEqual(re.findall(r"rev: v([\d.]+)", self.text), [g.__version__])

    def test_hook_id_matches(self):
        self.assertIn("- id: l10n-guard\n", self.text)

    def test_action_examples_name_this_version(self):
        tags = re.findall(r"uses: munimtechnologies/l10n-guard@v([\d.]+)", self.text)
        self.assertTrue(tags)
        self.assertEqual(set(tags), {g.__version__})


if __name__ == "__main__":
    unittest.main()
