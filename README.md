# l10n-guard

Catch the translation mistakes that break software and docs, before they ship.

A translation can read perfectly and still break the app: a renamed `{{name}}`, a lost `%s`,
an unclosed `<b>`, a "translated" shell command, a payment link that no longer matches. These are
the mistakes machine and AI translation make most often, and the ones human reviewers miss
because they read for meaning. `l10n-guard` checks a translation against its source for exactly these.

- **One file, standard library only** (Python 3.8+). It reads files and sends nothing anywhere.
- **JSON catalogs** (i18next, vue-i18n, next-intl, flat or nested): placeholders, markup, missing
  and extra keys, value types, and plural keys (`_one`, `_few`, `_many`, `_other`), checked per
  language, so Japanese with only `_other` or Polish with `_few`/`_many` doesn't raise false alarms.
- **gettext `.po`**: placeholders per entry, plural form count against the `Plural-Forms` header,
  and counts of fuzzy and untranslated entries.
- **HTML and Markdown docs**: every code block must be byte-identical, inline code must match,
  external links (including `mailto:` and checkout links) must survive, and `<html lang>` must
  change. Numbers that vanish from the prose are reported as warnings.

Placeholder styles recognised: `{{name}}`, `{name}`, `{0}`, ICU `{count, plural, ...}` (by argument
name, so translated plural branches are fine), `%s`, `%d`, `%.2f`, `%(name)s`, `%1$s`, `${name}`.
Markup: HTML/XML tags and react-i18next `<0>...</0>` slots. Prose like `50 % de remise` is not
mistaken for `% d`.

## Use

```sh
python3 l10n_guard.py json locales/en.json locales/de.json
python3 l10n_guard.py po   locale/pl/LC_MESSAGES/messages.po
python3 l10n_guard.py html secure-ollama.html de/secure-ollama.html
python3 l10n_guard.py md   README.md README.ja.md
python3 l10n_guard.py --json --strict json en.json fr.json   # options go before the kind
```

Example output:

```
ERROR placeholder-missing [cart.total]: placeholder(s) missing: {{amount}}
ERROR tags [welcome]: markup differs: missing </b>
WARNING missing-key [settings.title]: key missing from translation
2 error(s), 1 warning(s)
```

Exit code 0 means no errors, 1 means errors were found, 2 means the input couldn't be read.
`--strict` counts warnings as errors. `--json` prints machine-readable output.

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: munimv2/l10n-guard@v0.1.0
  with:
    kind: json
    source: locales/en.json
    target: locales/de.json
```

## Tested on real translations

`examples/secure-ollama/` holds an English guide and five translations of it (German, Spanish,
French, Japanese, Brazilian Portuguese), published at
[munimv2.github.io/secure-ollama.html](https://munimv2.github.io/secure-ollama.html). The test
suite checks that every command, code block and external link, including both payment links,
survived translation. Those translations were made with AI and are labelled as such on each page.

## About

Made by MV2 of Munim, Inc., with AI agents. MIT licence. Issues and corrections are welcome at
[github.com/munimv2/l10n-guard/issues](https://github.com/munimv2/l10n-guard/issues).
