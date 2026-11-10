---
name: l10n-guard
description: Check a translated file against its source for the mistakes that break software - lost or renamed placeholders ({name}, %s, %1$d, :attribute), broken markup, Android apostrophes that fail the build, translations that crash Java's String.format, look-alike percent signs and braces (٪ ％ ｛ ｝), Simplified characters in Traditional Chinese, invisible characters, misfiled Android translation folders, and Android per-app language lists (locales_config.xml) that drift from the shipped translations. Use after you write, machine-translate or edit a locale file, review a translation pull request, add a language to an Android app, or see raw placeholders or a crash in one language. Covers JSON (i18next, vue-i18n, next-intl, FormatJS), gettext .po, Android, Apple .strings/.xcstrings, XLIFF, Flutter .arb, Java .properties, .NET .resx, Qt .ts, Laravel, Rails, Symfony, HTML and Markdown. One Python file, standard library only; reads local files and sends nothing anywhere.
license: Apache-2.0
metadata:
  author: MV2 of Munim, Inc.
  version: "0.20.1"
  source: https://github.com/munimtechnologies/l10n-guard
---

# l10n-guard: check a translation before it ships

Human reviewers read translations for meaning; the mistakes that break an app are mechanical,
and machine and AI translation make them most often: a placeholder renamed or dropped, `%s ... %d`
reordered so Java throws, `100 % sûr` read by `String.format` as the flag `% s` (a crash in that
language only), an unescaped `'` that fails the Android build, `٪s` written with the Arabic percent
sign so the value silently disappears. `l10n-guard` compares a translation with its source and
reports exactly these. It does not judge wording or meaning.

Run it on every translation file you create or change, before you commit or open a pull request.

## Steps

1. **Get the tool** (pinned release; pick one):
   - `pip install "git+https://github.com/munimtechnologies/l10n-guard@v0.20.1"` gives an
     `l10n-guard` command (Python 3.9+).
   - Or use the single file `l10n_guard.py` from that release with `python3 l10n_guard.py ...`
     (Python 3.8+). If the project already vendors `l10n_guard.py` or runs the GitHub Action or
     pre-commit hook, use that copy.

2. **Pick the kind** from the file format. Options go *before* the kind.

   | Files | Command |
   |---|---|
   | JSON catalogs (i18next, vue-i18n, next-intl, FormatJS extract) | `l10n-guard json locales/en.json locales/de.json` |
   | gettext | `l10n-guard po locale/pl/LC_MESSAGES/messages.po` (one file) |
   | Android | `l10n-guard android app/src/main/res/values/strings.xml app/src/main/res/values-fr/strings.xml` |
   | Android per-app language list (`android:localeConfig`) | `l10n-guard locale-config .` (a project or module folder) |
   | Apple | `l10n-guard strings en.lproj/Localizable.strings de.lproj/Localizable.strings`; `l10n-guard xcstrings Localizable.xcstrings` |
   | XLIFF 1.2/2.0 (Weblate, Crowdin, Angular, Xcode exports) | `l10n-guard xliff src/locale/messages.de.xlf` |
   | Flutter | `l10n-guard arb lib/l10n/app_en.arb lib/l10n/app_ja.arb` |
   | Java ResourceBundle / Spring | `l10n-guard properties messages.properties messages_fr.properties` |
   | .NET | `l10n-guard resx Resources.resx Resources.ja.resx` |
   | Qt Linguist | `l10n-guard qt translations/app_ar.ts` |
   | Laravel / Rails / Symfony | `l10n-guard laravel lang/en/validation.php lang/ja/validation.php` (likewise `rails`, `symfony`) |
   | Docs | `l10n-guard md README.md README.ja.md`; `l10n-guard html page.html de/page.html` |
   | A whole docs folder | `l10n-guard dir site site/ja` |
   | Plain text such as store listings | `l10n-guard text fastlane/metadata/android/en-US/full_description.txt fastlane/metadata/android/zh-TW/full_description.txt` |

   The language is read from the target's path (`values-zh-rTW`, `de.lproj`, `zh-TW.json`). When
   the path doesn't name it, add `--locale zh-TW` (or `zh-Hant`, `uk`, ...) before the kind.

3. **Run it and read the result.** Exit code 0 = no errors, 1 = errors found, 2 = a file couldn't
   be read or parsed (fix the path or the syntax first). `--strict` makes warnings count as
   errors. `--json` prints `{"issues": [{"level", "code", "message", "key"}], "stats", "errors"}`.
   Each text line reads `LEVEL code [key]: message`.

4. **Fix errors in the translation, never in the source**, keeping the translator's wording:
   - `placeholder-missing` / extra placeholder: restore the source's placeholder exactly
     (`{{amount}}`, `{0}`, `%1$s`, `:attribute`, `%{count}`). Reordering is fine only with numbered
     forms (`%2$d ... %1$s`); `java-format` reorder errors suggest the numbered form.
   - `java-format`: the message names the exception Android would throw. A literal percent sign in
     a formatted Android string must be written `%%` (`50 %%`, `100 %% sûr`).
   - `tags`: restore the source's markup (`<b>...</b>`, `<0>...</0>` slots, `<xliff:g>`).
   - `android-apostrophe`: write `\'` (or wrap the whole string in double quotes); `&apos;` does
     not help.
   - `messageformat-apostrophe` (Java `.properties` with `{0}`): write `''` for a literal apostrophe.
   - `lookalike-percent`, `lookalike-brace`, `lookalike-colon`: replace `٪ ％ ﹪`, `｛ ｝`, `：` inside the
     placeholder with ASCII `%`, `{ }`, `:`.
   - `qt-arg-order`, `qt-arg-missing`, `qt-count`: keep each `%1`, `%2` as in the source, and write
     the count in plural (numerus) forms as ASCII `%n` or `%Ln`, not `٪n`, `％n` or `% n`.

5. **Treat warnings as questions for the user, not automatic fixes:**
   - `wrong-script` (Simplified characters such as 这 设 in a Traditional Chinese file) and
     `invisible-char` (zero-width space, soft hyphen, BOM): usually fix, but say what you changed.
   - `folder-script` (an Android `values-xx` folder whose text is mostly in another script, e.g.
     Welsh in `values-ar`) and `locale-code` (`values-ua`, `values-cz`, `values-cn`, `values-jp`,
     `values-dk`: country codes no phone language selects; the message names the right code):
     moving or renaming a translation folder can conflict with the project's Weblate or Crowdin
     setup, so report it and ask before renaming.
   - `locale-config-orphan` (a translation the per-app language list leaves out) and
     `locale-config-code` (`dk` instead of `da`): adding or fixing a `<locale android:name="..."/>`
     line is usually right, but first open the folder and check it really holds that language and
     isn't untranslated English copies. `locale-config-phantom` (a listed language with no
     translation in `res/`): **ignore it in Flutter, React Native and web-view apps**, whose text
     lives outside `res/` (for example `lib/l10n/app_az.arb`); otherwise ask whether to remove the
     line or add the translation. `locale-config-tag` (`pt-rBR`): write the tag as `pt-BR`.
   - `antonym-collision`, `reading-leak`, `java-format-type`, `qt-arg-renumbered`,
     `qt-count-missing`, `untranslated`, `missing-key`, `extra-key`: report.
   - In `dir` mode a `no-source` warning means a translated file has no source file next to it.

6. **In someone else's repository**, check its contributing rules first: many projects take
   translations only through Weblate, Crowdin or Transifex and close translation pull requests; some
   don't accept AI-assisted contributions or require disclosure. If the files are platform-managed,
   report the finding (issue, or a comment on the string in the platform) instead of editing them.

## CI options (when the user wants it enforced)

- GitHub Action: `uses: munimtechnologies/l10n-guard@v0.20.1` with `kind`, `source`, `target`
  (single-file kinds `po`, `xliff`, `xcstrings`, `qt` take only `target`). For `locale-config`,
  use a plain step instead: `pip install "git+https://github.com/munimtechnologies/l10n-guard@v0.20.1"`
  then `l10n-guard --strict locale-config .`.
- pre-commit: repo `https://github.com/munimtechnologies/l10n-guard`, `rev: v0.20.1`, hook id
  `l10n-guard`, `args: [json, locales/en.json, locales/de.json]`, one hook entry per pair (or the
  `dir` kind for a folder).

## Limits

- Mechanical checks only: a fluent but wrong translation passes. Mainland vocabulary written in
  Traditional characters, and a wrong language in the same script (Hungarian in `values-ast`), are
  not detected.
- `folder-script` covers only languages written in one script; Serbian, Uzbek, Azerbaijani,
  Punjabi, Kurdish, Mongolian and Sindhi folders are skipped.
- `locale-config` reads only Android `res/` folders. Since 0.20.1 it counts a string as
  translated only when it differs from the default (or keeps a one-word default such as `OK`),
  skips phantom checks in Flutter and JavaScript apps, and leaves `donottranslate*.xml` out, as
  Android Lint does. In the 0.19.0 test 31 of 36 sampled findings were real; the misses were
  phantoms in apps whose text isn't in `res/` and one folder of English copies
  ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/l10n-guard-0190/RESULTS.md)).
- `java-format` was measured against OpenJDK 21's `Formatter` on 1,262,958 translated Android
  strings from F-Droid apps: precision 1.0 and recall 0.98 for errors
  ([census](https://github.com/munimtechnologies/android-translation-crash-census)).
  The warning rules were checked by hand by AI agents, not by native speakers; see the linked
  results in the project README.

## About

`l10n-guard` and this skill are made by MV2 of Munim, Inc., with AI agents. Apache-2.0.
Issues and corrections: https://github.com/munimtechnologies/l10n-guard/issues
