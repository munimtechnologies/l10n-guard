# l10n-guard

Catch the translation mistakes that break software and docs, before they ship.

A translation can read perfectly and still break the app: a renamed `{{name}}`, a lost `%s`,
an unclosed `<b>`, a "translated" shell command, a payment link that no longer matches, an
apostrophe in `l'application` that fails the Android build. These are the mistakes machine and AI
translation make most often, and the ones human reviewers miss because they read for meaning.
`l10n-guard` checks a translation against its source for exactly these.

- **One file, standard library only** (Python 3.8+). It reads files and sends nothing anywhere.
- **JSON catalogs** (i18next, vue-i18n, next-intl, flat or nested): placeholders, markup, missing
  and extra keys, value types, and plural keys (`_one`, `_few`, `_many`, `_other`), checked per
  language, so Japanese with only `_other` or Polish with `_few`/`_many` doesn't raise false alarms.
- **gettext `.po`**: placeholders per entry, plural form count against the `Plural-Forms` header,
  and counts of fuzzy and untranslated entries.
- **Android `strings.xml`** (new in 0.3.0): `<string>`, `<plurals>` and `<string-array>`, with
  inline markup and `<xliff:g>` kept. Strings marked `translatable="false"` are skipped. An
  apostrophe that is neither written `\'` nor inside double quotes is an error, because aapt
  rejects it (`&apos;` doesn't help). Plural quantities the source lacks (`few`, `many`) are
  checked against its `other` form.
- **Apple `.strings` and String Catalogs** (new in 0.3.0): `.strings` files in UTF-8 or UTF-16,
  with `/* */` and `//` comments, and Xcode `.xcstrings` catalogs, where every language's
  values, plural and device variations and substitutions are checked against the source
  language. `%@`, `%lld` and `%1$@` count as placeholders.
- **XLIFF 1.2 and 2.0** (new in 0.3.0), as exported by Weblate, Crowdin, Angular and Xcode: each
  translated `<trans-unit>` or `<segment>` keeps its placeholders, and its inline elements
  (`<x>`, `<g>`, `<ph>`, `<pc>`, `<bpt>`...) by name and id. Units marked `translate="no"`
  are skipped; empty targets are counted as untranslated.
- **HTML and Markdown docs**: every code block must be byte-identical, inline code must match,
  external links (including `mailto:` and checkout links) must survive, and `<html lang>` must
  change. Numbers that vanish from the prose are reported as warnings. If the pages carry
  `<link rel="alternate" hreflang>` tags, the translation must list the same alternates as the
  source, because search engines ignore a language cluster whose pages disagree.
- **Whole locale folders**: `dir site site/de` checks every HTML, Markdown, JSON and `.strings`
  file under `site/de` against the file with the same path under `site` (`dir en.lproj de.lproj`
  works too). When the folder is named like a language (`de`, `ja`, `pt-br`, `zh_Hans`), each
  page's `<html lang>` must match it.

Placeholder styles recognised: `{{name}}`, `{name}`, `{0}`, ICU `{count, plural, ...}` (by argument
name, so translated plural branches are fine), `%s`, `%d`, `%.2f`, `%@`, `%lld`, `%(name)s`,
`%1$s`, `${name}`. Markup: HTML/XML tags and react-i18next `<0>...</0>` slots. Prose like
`50 % de remise` is not mistaken for `% d`. In plural forms for zero, one and two, a missing
placeholder is only a warning, since "one file" often spells the number out.

## Use

```sh
python3 l10n_guard.py json      locales/en.json locales/de.json
python3 l10n_guard.py po        locale/pl/LC_MESSAGES/messages.po
python3 l10n_guard.py android   app/src/main/res/values/strings.xml app/src/main/res/values-fr/strings.xml
python3 l10n_guard.py strings   en.lproj/Localizable.strings de.lproj/Localizable.strings
python3 l10n_guard.py xcstrings Localizable.xcstrings
python3 l10n_guard.py xliff     src/locale/messages.de.xlf
python3 l10n_guard.py html      secure-ollama.html de/secure-ollama.html
python3 l10n_guard.py md        README.md README.ja.md
python3 l10n_guard.py dir       site site/ja
python3 l10n_guard.py --json --strict json en.json fr.json   # options go before the kind
```

Example output:

```
ERROR placeholder-missing [cart.total]: placeholder(s) missing: {{amount}}
ERROR tags [welcome]: markup differs: missing </b>
ERROR android-apostrophe [saved]: apostrophe must be written \' (or the text put in double quotes), or the build fails
WARNING missing-key [settings.title]: key missing from translation
3 error(s), 1 warning(s)
```

In `dir` mode each issue starts with the file's path, for example
`ERROR inline-code-missing [guide.html]: ...` or `WARNING no-source [extra.html]: ...` for a
translated file with no source file next to it. `xliff` and `xcstrings` also print counts, for
example `4 units, 3 translated, 1 untranslated`.

Exit code 0 means no errors, 1 means errors were found, 2 means the input couldn't be read.
`--strict` counts warnings as errors. `--json` prints machine-readable output.

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: munimv2/l10n-guard@v0.3.0
  with:
    kind: json
    source: locales/en.json
    target: locales/de.json
```

An Android translation, or a single-file format (`po`, `xliff`, `xcstrings` take only `target`):

```yaml
- uses: munimv2/l10n-guard@v0.3.0
  with:
    kind: android
    source: app/src/main/res/values/strings.xml
    target: app/src/main/res/values-fr/strings.xml
- uses: munimv2/l10n-guard@v0.3.0
  with:
    kind: xcstrings
    target: App/Localizable.xcstrings
```

A whole translated folder:

```yaml
- uses: munimv2/l10n-guard@v0.3.0
  with:
    kind: dir
    source: docs
    target: docs/de
```

## Tested on real translations

`examples/` holds five English pages from [munimv2.github.io](https://munimv2.github.io/), each
with five translations (German, Spanish, French, Japanese, Brazilian Portuguese):
[secure-ollama](https://munimv2.github.io/secure-ollama.html),
[ollama-remote-access](https://munimv2.github.io/ollama-remote-access.html),
[ollama-api-key](https://munimv2.github.io/ollama-api-key.html),
[docker-ollama](https://munimv2.github.io/docker-ollama.html) and
[sample-report](https://munimv2.github.io/sample-report.html). The test suite checks that every
command, code block and external link, including both payment links, survived translation. Those
translations were made with AI and are labelled as such on each page.

## About

Made by MV2 of Munim, Inc., with AI agents. MIT licence. Issues and corrections are welcome at
[github.com/munimv2/l10n-guard/issues](https://github.com/munimv2/l10n-guard/issues).
