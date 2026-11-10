# l10n-guard

Catch the translation mistakes that break software and docs, before they ship.

A translation can read perfectly and still break the app: a renamed `{{name}}`, a lost `%s`,
an unclosed `<b>`, a "translated" shell command, a payment link that no longer matches, an
apostrophe in `l'application` that fails the Android build or makes Java print a literal `{0}`,
or a French `100 % sûr` that crashes an Android app the moment the string is shown.
These are the mistakes machine and AI translation make most often, and the ones human reviewers
miss because they read for meaning. `l10n-guard` checks a translation against its source for
exactly these.

- **One file, standard library only** (Python 3.8+). It reads files and sends nothing anywhere.
- **JSON catalogs** (i18next, vue-i18n, next-intl, flat or nested): placeholders, markup, missing
  and extra keys, value types, and plural keys (`_one`, `_few`, `_many`, `_other`), checked per
  language, so Japanese with only `_other` or Polish with `_few`/`_many` doesn't raise false alarms.
  Since 0.14.0 the source may be a FormatJS `extract` file (`{"id": {"defaultMessage": ...,
  "description": ...}}`, as Mattermost's `en.json`): each `defaultMessage` is the source text,
  descriptions are not compared, and flat translations of such a file are checked key by key.
- **gettext `.po`**: placeholders per entry, plural form count against the `Plural-Forms` header,
  and counts of fuzzy and untranslated entries.
- **Java `.properties`**: ResourceBundle and Spring message bundles, with `#`/`!`
  comments, `key=value`, `key: value` and `key value` lines, backslash continuations and
  `\uXXXX` escapes. Files that aren't UTF-8 are read as ISO-8859-1. In a MessageFormat string
  (one with `{0}` or `{name}`), a single `'` in the translation is an error: MessageFormat
  treats it as the start of quoted text, so `L'utilisateur {0}` prints `Lutilisateur {0}`.
  Write `''` instead.
- **Flutter `.arb`**: messages are compared with the template and `@key`
  metadata is skipped. ICU plural and select branches may differ between languages (Japanese
  needs only `other`), but every argument and tag must survive. `@@locale` left as the
  template's locale is a warning.
- **.NET `.resx`** (0.8.0): the text `<data>` entries of a translated `Resources.ja.resx`
  are compared with the neutral `Resources.resx` as a catalog. Typed entries (images, files:
  `type=`, `mimetype=`) and WinForms designer entries (`>>button1.Name`) are skipped.
- **Laravel lang files** (0.9.0): `lang/ja/validation.php` is compared with `lang/en/validation.php`
  key by key (nested keys as `size.string`), by Laravel's `:name` placeholders. Plural ranges
  (`{0}`, `[2,*]`) may differ between languages. Values that aren't plain strings (function
  calls, constants) are skipped.
- **Rails locale files** (0.10.0): `config/locales/ja.yml` is compared with `config/locales/en.yml`
  key by key, below the locale's root key (`en:`, `ja:`), by Ruby I18n's `%{name}` and `%<name>s`
  placeholders. Plural keys (`one`, `few`, `other`) are checked per language, as in JSON catalogs,
  and any form may add `%{count}`.
- **Symfony translations** (0.10.0): `messages.ja.yaml` or `.xlf`/`.xliff` is compared with the
  source language's file **by key**, the way Symfony's translator pairs them, so XLIFF files whose
  `<source>` is the key (as in SonataAdminBundle) are checked too. Parameters are `%name%`, plus
  `{{ name }}` and `%s`. In a plural message (`one|many`, with `{0}` or `]1,Inf]` intervals) each
  form is checked against the source's last form.
- **YAML** is read by a small built-in reader, so PyYAML isn't needed: nested mappings and lists,
  plain, quoted and block (`|`, `>`) values. Anchors, aliases and tags are refused with an error.
- **Android `strings.xml`**: `<string>`, `<plurals>` and `<string-array>`, with inline markup
  and `<xliff:g>` kept. Strings marked `translatable="false"` are skipped. An apostrophe that is
  neither written `\'` nor inside double quotes is an error, because aapt rejects it (`&apos;`
  doesn't help). Plural quantities the source lacks (`few`, `many`) are checked against its
  `other` form. Emoji written as two escapes (`😀`) are read as the one character
  they encode.
- **Android crashes from `String.format`** (code `java-format`): when the app
  passes arguments (`getString(id, args)`, `getQuantityString`, Compose `stringResource`),
  Android formats the string with Java's `java.util.Formatter`, which reads the *whole*
  translation first and throws on anything it can't parse. So a translation crashes the app in
  that language even though the English works. l10n-guard parses each translation of a
  formatted string the way `Formatter` does and names the exception it would throw:
  - `UnknownFormatConversionException`: a stray `%`, as in `Téléchargé à 50%`, `50%ige`,
    `%ф` or `%d %restants`;
  - `FormatFlagsConversionMismatchException`: prose that happens to read as a flag, as in
    `100 % sûr` (`% s`) or `%1$d % terminé` (`% te`);
  - `MissingFormatArgumentException`: `%3$s` when the source passes two arguments;
  - `IllegalFormatConversionException`: `%d` for the source's `%.1f`, or the reverse;
  - `MissingFormatWidthException`, `IllegalFormatPrecisionException` and the other flag errors.

  A `%d` for the source's `%s` is a warning (`java-format-type`): it crashes only if the app
  passes text. Strings marked `formatted="false"`, string arrays, and sources whose only `%` is
  prose (`50% off`) are not checked, because the app doesn't format them.

  **Plurals** (0.5.1): `getQuantityString` passes the same arguments to every quantity, so each
  translated form is checked against the source form that reads the most of them. A Russian
  `one` form may use `%2$d из %3$d` when the English `one` is just `File from %1$s` but `other`
  is `%2$d of %3$d files from %1$s`; and a stray `%` in a `one` form is caught even when the
  English `one` has no placeholder at all.
- **Look-alike percent signs** (0.7.1, code `lookalike-percent`): a placeholder written with the
  Arabic percent sign `٪` (U+066A), the fullwidth `％` (U+FF05) or the small `﹪` (U+FE6A), as in
  `٪s`, `％1$d` or `٪D`, looks right, but no formatter reads it: Android's `String.format`, printf
  and Python show it as written, and the value is lost. That is an error in every format, plural
  `one` forms included (where a missing placeholder is otherwise only a warning), and the message
  names the character. A look-alike next to the real placeholder (`％s ... %s`) is a warning. On
  2026-10-17 seven Android apps had such strings, and Android Lint, read in source, misses them in
  `<plurals>` and in mixed strings
  ([findings](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/lookalike-percent/FINDINGS.md)).
- **Look-alike braces** (0.8.0, code `lookalike-brace`): a `{0}`, `{name}` or `{{name}}` written
  with the fullwidth braces `｛` and `｝` (U+FF5B, U+FF5D), which Chinese and Japanese input
  methods type, often with fullwidth digits (`｛０｝`). .NET `string.Format`, Java `MessageFormat`,
  ICU, ngx-translate and Python's `str.format` read only ASCII braces, so the text is shown as
  written and the value is lost: an error, in every format. With one brace still ASCII (`｛0}`),
  .NET and Python throw instead. A fullwidth copy next to the real placeholder is a warning, and
  fullwidth braces the source has too are left alone. On 2026-10-18 nine open-source projects
  had such strings, among them about 200 messages in ONLYOFFICE's Japanese audit trail
  ([findings](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/lookalike-brace/BRACES.md)).
- **Look-alike colons** (0.9.0, code `lookalike-colon`): a Laravel `:attribute` written with the
  fullwidth colon `：` (U+FF1A), as in `The：attributeフィールドは必須です。`. Laravel searches for
  the ASCII colon only, so the text is shown as written and the field name, user or time is
  lost: an error. A copy next to the real placeholder is a warning. On 2026-10-18 Akaunting,
  UNIT3D and Snipe-IT had such strings in Japanese or Chinese
  ([findings](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/lookalike-colon/LARAVEL.md)).
- **Look-alike percent signs in Rails and Symfony files** (0.10.0, code `lookalike-percent`):
  `％{count}` and `٪ {name}` in Rails, `％name％` and `٪ name٪` in Symfony. Ruby's I18n reads only
  `%{` and `%<`, and Symfony replaces each parameter by its exact key, so the text is shown as
  written and the value is lost: an error. On 2026-10-18 GOV.UK Publishing Components,
  OpenStreetMap, SonataAdminBundle, Akeneo PIM and OpenDXP had such strings, all in Chinese,
  Japanese or Arabic ([Rails](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/lookalike-percent/RAILS.md),
  [Symfony](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/lookalike-percent/SYMFONY.md)).
- **Leaked katakana readings** (0.11.0, code `reading-leak`): a Japanese translation that keeps a
  word's reading between fullwidth number signs, as in `削除＃サクジョ＃` for "Delete", shows the
  reading to users as text. It is reported when a `＃` follows a character other than a space,
  then katakana, then a second `＃`, and the source has no `#` or `＃`, in every kind. Nothing
  breaks, so it is a warning. A reading written in hiragana with no signs (`検索けんさく`) is not
  reported, because kanji followed by hiragana is ordinary written Japanese. The rule and its
  predictions were published before the code ([pre-registration](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/mt-artifacts/READING-LEAK-PREREG.md));
  on 2026-10-18 the Japanese file of the Nostr client nostrmo had 18 such strings
  ([note](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/mt-artifacts/KATAKANA-READING.md)).
- **Antonym collisions** (0.12.0, code `antonym-collision`, JSON and `.arb`): two keys whose source
  texts differ only by antonyms ("Default expanded" / "Default collapse", "Mute" / "Unmute") but
  share one translation, so one of the two labels says the opposite of what it does. A source fix
  that keeps the old translations leaves this shape: in NocoBase, a switch relabelled "Default
  expanded" still read "collapse" in 13 of 16 locales. A shared value equal to either source text
  is left to the untranslated check. The 40 word classes were fixed before any scan, and antonyms
  outside them ("Visible" / "Hidden") are missed, so it is a warning
  ([scan](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/antonym-collision/RESULTS.md),
  [pre-registration of this check](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/antonym-collision/GUARD-PREREG.md),
  [test results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/antonym-collision/GUARD-RESULTS.md)). Since 0.13.0 the upload/download
  class is left out, as fixed in advance by a
  [second held-out test](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/antonym-collision/HOLDOUT2-RESULTS.md): in French, Arabic,
  Russian, Ukrainian and Finnish one word covers both directions, so 11 of the 12 warnings graded in
  that class were not defects, while all 49 graded in the other classes were real (graded by AI
  agents, not native speakers). 39 word classes remain.
- **Invisible characters** (0.15.0, code `invisible-char`, every format): a translation that
  carries a zero-width space, soft hyphen, word joiner, byte-order mark or other invisible format
  character its source doesn't have is a warning, since it breaks search, wrapping and string
  comparison without showing on screen. Zero-width spaces in Thai, Lao, Tibetan, Myanmar and
  Khmer, directional marks and bidi controls in right-to-left text, zero-width (non-)joiners, and
  soft hyphens between two letters (hyphenation points in compound words) are normal there and
  not reported, except (0.16.0) a space followed by two zero-width spaces, which is no word break
  (the space already is one) and is reported in every language. The exemptions were checked against the census of 2,392 F-Droid apps in
  [android-translation-crash-census/hidden-chars](https://github.com/munimtechnologies/android-translation-crash-census/tree/main/hidden-chars), the 0.16.0 rule in
  [zwsp-langs](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/hidden-chars/zwsp-langs/RESULTS.md).
- **Simplified characters in Traditional Chinese** (0.17.0, code `wrong-script`): when the
  translation is Traditional Chinese (`zh-TW`, `zh-HK`, `zh-MO`, `zh-Hant`, Android's
  `values-zh-rTW` or `values-b+zh+Hant`), a Simplified-only character its source doesn't have
  (这 for 這, 设 for 設) is a warning: text that was never converted, or only partly. The
  locale is read from the target's path, or given with `--locale zh-TW`. The `android`, `json`,
  `arb`, `strings`, `properties` and `resx` kinds are checked, and the new `text` kind compares
  two plain-text files, such as app-store listings, for this and for invisible characters. The
  3,771 characters come from OpenCC; the Cantonese particle 晒 is not reported in Hong Kong and
  Macau. In the census, 188 of 692 F-Droid apps with a Traditional Chinese translation shipped
  such characters, and hand checks by AI agents found 39 of 40 flagged strings
  ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/hanzi-leak/RESULTS.md)) and 32 of 35 flagged store-listing lines
  ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/hanzi-meta/RESULTS.md)) to be real defects. Mainland
  vocabulary written in Traditional characters is not checked.
- **A translation in the wrong folder, and folder names that aren't languages** (0.18.0, `android`
  kind, codes `folder-script` and `locale-code`): Android picks a `values-<code>` folder by the
  phone's language. When at least 10 translated strings of a folder (strings that differ from the
  source) are written in another script and outnumber those in the folder language's own script,
  as with Welsh text in `values-ar` or Japanese in `values-be`, that is a `folder-script`
  warning: another language's translation is probably filed under the wrong code. Latin text that
  mostly reuses the source's words is reported as source text left untranslated instead. The rule
  covers only languages written in one script (Cyrillic, Greek, Armenian, Hebrew, Arabic, the
  Indic scripts, Thai, Lao, Georgian, Korean, Ethiopic, Khmer, Japanese and Chinese, among others),
  only folders without a script tag (`values-b+kk+Latn` is fine), and leaves out languages with
  several scripts in everyday use (Serbian, Uzbek, Azerbaijani, Punjabi, Kurdish, Mongolian,
  Sindhi). A wrong language in the same script, such as Hungarian in `values-ast`, is invisible
  to it. A folder named with a code that is not a language, mostly a country code (`values-ua`,
  `values-cz`, `values-cn`, `values-jp`, `values-dk`), is a `locale-code` warning that names the
  right code, because no phone language setting selects it (only an in-app language picker that
  asks for that code itself would). The locale is read from the target's path, or given with
  `--locale`. The rule comes from a pre-registered census of F-Droid apps, where hand checks by AI
  agents found 26 of 32 flagged folders to be real defects
  ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/locale-mismatch/RESULTS.md)).
  Before release it flagged exactly the 5 known folders among the 73 of Thunderbird for Android's
  message-list module, and no other
  ([check](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/l10n-guard-0180/RESULTS.md)).
- **Android per-app language lists** (0.19.0, new `locale-config` kind, codes
  `locale-config-orphan`, `locale-config-phantom`, `locale-config-code`, `locale-config-tag`):
  since Android 13 a user can pick a language for one app in the system settings, but Android
  offers only the languages in the app's locale config, the `res/xml` file that
  `android:localeConfig` names in the manifest. A hand-written list drifts from the translations
  the app ships. `l10n-guard locale-config <project folder>` finds every manifest that names such a
  list and compares the list with the module's `values-*` folders:
  - `locale-config-orphan`: a translated folder with at least half of the module's strings that
    the list leaves out, so the setting never offers that language;
  - `locale-config-phantom`: a listed language with no translated strings, or one the build's
    `localeFilters` / `resConfigs` / `resourceConfigurations` drops, so the setting offers it and
    the app shows its default language;
  - `locale-config-code`: a listed code that is not a language (`dk`, with the right code named);
  - `locale-config-tag`: a resource-folder spelling such as `pt-rBR` instead of `pt-BR`.

  Languages are compared, not regions or scripts; `iw`/`he`, `in`/`id` and `ji`/`yi` count as the
  same language. A list the build generates (`generateLocaleConfig`) or that a build file names is
  skipped, an unreadable language filter skips the orphan check, and a default language that is
  not English and can't be identified skips the phantom check; the stats line says which. All four
  are warnings, so use `--strict` to fail a CI step or a commit on them.

  Android Lint already warns about part of this: its `UnusedTranslation` check (Android Gradle
  plugin 7.4 and later) reports translated folders the locale config leaves out, as a warning
  during a lint run. What `locale-config` adds is phantom languages, non-language codes, awareness
  of the build's language filters, and a check that needs no Gradle build, so it runs in a
  pre-commit hook or a plain Python step.

  The rule and its predictions were published before the release, and all six held: on 96
  held-out open-source apps with drifting lists, hand checks by AI agents found a real finding in
  14 of 16 sampled apps and 31 of 36 sampled findings to be real
  ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/l10n-guard-0190/RESULTS.md),
  [census](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/locale-config/RESULTS.md)).
  Since 0.20.1 the check closes the two gaps that test found. A string counts as translated
  only when it differs from the default text or keeps a one-word or wordless default (`OK`,
  `%1$s`), so a folder of untranslated English copies is no longer an orphan; and phantom
  checks are skipped in Flutter and JavaScript apps (React Native, Expo, Capacitor, Cordova)
  and for languages with a catalog outside `res/`. Files named `donottranslate*.xml` are left
  out of the counts, as Android Lint treats them
  ([0.20.1 check](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/l10n-guard-0201/RESULTS.md)).
- **Apple `.strings` and String Catalogs**: `.strings` files in UTF-8 or UTF-16, with `/* */`
  and `//` comments, and Xcode `.xcstrings` catalogs, where every language's values, plural and
  device variations and substitutions are checked against the source language. `%@`, `%lld`
  and `%1$@` count as placeholders.
- **XLIFF 1.2 and 2.0**, as exported by Weblate, Crowdin, Angular and Xcode: each translated
  `<trans-unit>` or `<segment>` keeps its placeholders, and its inline elements (`<x>`, `<g>`,
  `<ph>`, `<pc>`, `<bpt>`...) by name and id. Units marked `translate="no"` are skipped; empty
  targets are counted as untranslated.
- **Qt Linguist `.ts`** (0.7.0): `QString::arg()` fills the lowest-numbered place marker first,
  whatever number the translator gave it, so a translation that renumbers the markers (`%1 of %2`
  to `%2 の %3`) or drops one shows the wrong value or none. Each translation's markers (`%1`,
  `%L2`) are checked by what `arg()` would show, with a hint when a missing marker was written
  `٪1`, `% 1`, `1%`, or with digits such as `%১` that Qt 6.6 and later don't read as a marker.
  In plural (numerus) messages Qt replaces only an ASCII `%n` or `%Ln` with the count, so a form
  that writes it `٪n` (Arabic percent sign), `％n` (fullwidth) or `% n`, or writes `%1` where the
  source has only `%n`, shows that text instead of the number: an error. A message where no form
  shows the count is a warning. On 2026-10-17 Bitcoin Core's Arabic and Chinese translations had
  such forms ([details](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/qt-numerus/FINDINGS.md));
  the translation workbench [corpus](https://github.com/miguelaguiar01/corpus/pull/1102) found the
  same kind of form in KeePassXC's Arabic and Finnish files first.
  Unfinished translations get warnings, since lrelease ships them unless given `-nounfinished`;
  obsolete ones are skipped.
  A translation that only renumbers a marker to a number the source lacks (`to %1` written
  `nach %2`, `('%2')` written `('%22')`), so that every value still lands where the translator put
  it, is a warning (`qt-arg-renumbered`, 0.7.1), not an error. In a census of 39 open-source Qt
  projects, 11 of the 130 translations first counted as "value in the wrong place" were such
  renumberings ([results](https://github.com/munimtechnologies/android-translation-crash-census/blob/main/qt-args/RESULTS.md)).
- **HTML and Markdown docs**: every code block must be byte-identical, inline code must match,
  external links (including `mailto:` and checkout links) must survive, and `<html lang>` must
  change. Numbers that vanish from the prose are reported as warnings. If the pages carry
  `<link rel="alternate" hreflang>` tags, the translation must list the same alternates as the
  source, because search engines ignore a language cluster whose pages disagree.
- **Whole locale folders**: `dir site site/de` checks every HTML, Markdown, JSON and `.strings`
  file under `site/de` against the file with the same path under `site` (`dir en.lproj de.lproj`
  works too). When the folder is named like a language (`de`, `ja`, `pt-br`, `zh_Hans`), each
  page's `<html lang>` must match it.

**Placeholders in a new order, swapped numbers, a broken `%1$d`, and percent signs read as placeholders** (0.6.0):
Java fills unnumbered placeholders left to right, so a translation that moves them (`%s ... %d` to `%d ... %s`) puts each value in the wrong place, and String.format throws where text reaches `%d`. l10n-guard reports it as an error and suggests the numbered form (`%2$d ... %1$s`).
Numbered placeholders whose types are swapped against the source (`%1$s ... %2$d` to `%1$d ... %2$s`) are reported the same way, and `1%d` where the source has `%1$d` as a moved `%`.
A percent sign that Java reads as a placeholder without throwing (`50 % de` read as `% d`, `25% adicional` as `% a`) is now an error that says which argument it takes, and every stray-`%` error shows where it is and says to write `%%`. The source's own `%d` written `% d` (a space flag, with no number before it and no extra placeholder) is only a warning: Java prints the number with a leading space.

Placeholder styles recognised: `{{name}}`, `{name}`, `{0}`, ICU `{count, plural, ...}` (by argument
name, so translated plural branches are fine), `%s`, `%d`, `%.2f`, `%@`, `%lld`, `%(name)s`,
`%1$s`, `${name}`, Laravel `:name` in `laravel` files, Rails `%{name}` and `%<name>s`
in `rails` files, and Symfony `%name%` in `symfony` files. Markup: HTML/XML tags and react-i18next `<0>...</0>` slots. Prose like
`50 % de remise` is not mistaken for `% d`, except in an Android string the app formats, where
Java does read it that way. In plural forms for zero, one and two, a missing placeholder is only
a warning, since "one file" often spells the number out.

## Use

```sh
python3 l10n_guard.py json       locales/en.json locales/de.json
python3 l10n_guard.py po         locale/pl/LC_MESSAGES/messages.po
python3 l10n_guard.py properties src/main/resources/messages.properties src/main/resources/messages_fr.properties
python3 l10n_guard.py arb        lib/l10n/app_en.arb lib/l10n/app_ja.arb
python3 l10n_guard.py resx       Properties/Resources.resx Properties/Resources.ja.resx
python3 l10n_guard.py laravel    lang/en/validation.php lang/ja/validation.php
python3 l10n_guard.py rails      config/locales/en.yml config/locales/ja.yml
python3 l10n_guard.py symfony    translations/messages.en.yaml translations/messages.ja.yaml
python3 l10n_guard.py android    app/src/main/res/values/strings.xml app/src/main/res/values-fr/strings.xml
python3 l10n_guard.py strings    en.lproj/Localizable.strings de.lproj/Localizable.strings
python3 l10n_guard.py xcstrings  Localizable.xcstrings
python3 l10n_guard.py xliff      src/locale/messages.de.xlf
python3 l10n_guard.py qt         translations/app_ar.ts
python3 l10n_guard.py html       secure-ollama.html de/secure-ollama.html
python3 l10n_guard.py md         README.md README.ja.md
python3 l10n_guard.py dir        site site/ja
python3 l10n_guard.py text       fastlane/metadata/android/en-US/full_description.txt fastlane/metadata/android/zh-TW/full_description.txt
python3 l10n_guard.py locale-config  .   # an Android project folder: per-app language lists
python3 l10n_guard.py --locale zh-Hant json en.json zh.json   # when the path doesn't name the language
python3 l10n_guard.py --json --strict json en.json fr.json   # options go before the kind
```

Example output:

```
ERROR placeholder-missing [cart.total]: placeholder(s) missing: {{amount}}
ERROR tags [welcome]: markup differs: missing </b>
ERROR messageformat-apostrophe [deleted]: a single ' starts quoted text in MessageFormat, so the arguments after it print literally; write ''
ERROR java-format [done]: String.format would throw FormatFlagsConversionMismatchException (% te)
WARNING missing-key [settings.title]: key missing from translation
4 error(s), 1 warning(s)
```

In `dir` mode each issue starts with the file's path, for example
`ERROR inline-code-missing [guide.html]: ...` or `WARNING no-source [extra.html]: ...` for a
translated file with no source file next to it. `xliff` and `xcstrings` also print counts, for
example `4 units, 3 translated, 1 untranslated`.

Exit code 0 means no errors, 1 means errors were found, 2 means the input couldn't be read.
`--strict` counts warnings as errors. `--json` prints machine-readable output.
`--locale zh-TW` names the translation's language when its path doesn't.

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: munimtechnologies/l10n-guard@v0.20.1
  with:
    kind: json
    source: locales/en.json
    target: locales/de.json
```

A Java bundle, an Android translation, or a single-file format (`po`, `xliff`, `xcstrings`, `qt` take
only `target`):

```yaml
- uses: munimtechnologies/l10n-guard@v0.20.1
  with:
    kind: properties
    source: src/main/resources/messages.properties
    target: src/main/resources/messages_fr.properties
- uses: munimtechnologies/l10n-guard@v0.20.1
  with:
    kind: android
    source: app/src/main/res/values/strings.xml
    target: app/src/main/res/values-fr/strings.xml
- uses: munimtechnologies/l10n-guard@v0.20.1
  with:
    kind: xcstrings
    target: App/Localizable.xcstrings
```

A whole translated folder:

```yaml
- uses: munimtechnologies/l10n-guard@v0.20.1
  with:
    kind: dir
    source: docs
    target: docs/de
```

The Action takes a source and a target, so the `locale-config` kind runs as a plain step for now:

```yaml
- uses: actions/checkout@v4
- run: |
    pip install "git+https://github.com/munimtechnologies/l10n-guard@v0.20.1"
    l10n-guard --strict locale-config .
```

## Install with pip or pre-commit

`l10n_guard.py` is one file and needs nothing else, but it can also be installed as an
`l10n-guard` command (pip needs Python 3.9 or newer for this; the file itself still runs on 3.8):

```sh
pip install "git+https://github.com/munimtechnologies/l10n-guard@v0.20.1"
l10n-guard android values/strings.xml values-fr/strings.xml
```

To check translations on every commit with [pre-commit](https://pre-commit.com), add the hook to
`.pre-commit-config.yaml`. `args` are the same as on the command line (`--strict` and `--json`
first, then the kind, source and target); `files` makes the hook run only when a translation file
is part of the commit. Add one hook entry per source/target pair, or use the `dir` kind for a
whole locale folder.

```yaml
repos:
  - repo: https://github.com/munimtechnologies/l10n-guard
    rev: v0.20.1
    hooks:
      - id: l10n-guard
        name: l10n-guard (de)
        args: [json, locales/en.json, locales/de.json]
        files: ^locales/
```

The commit is stopped when l10n-guard finds an error (exit code 1), and with `--strict` also
when it finds a warning.

## Tested on real translations

`examples/` holds five English pages from [munimv2.github.io](https://munimv2.github.io/), each
with six translations (German, Spanish, French, Japanese, Korean, Brazilian Portuguese):
[secure-ollama](https://munimv2.github.io/secure-ollama.html),
[ollama-remote-access](https://munimv2.github.io/ollama-remote-access.html),
[ollama-api-key](https://munimv2.github.io/ollama-api-key.html),
[docker-ollama](https://munimv2.github.io/docker-ollama.html) and
[sample-report](https://munimv2.github.io/sample-report.html). The test suite checks that every
command, code block and external link, including both payment links, survived translation. Those
translations were made with AI and are labelled as such on each page.

### Results against a real JVM

The `java-format` check follows the specifier grammar and checks of OpenJDK's
`java.util.Formatter`. It was measured against the real thing (OpenJDK 21) on every open-source
Android app listed on F-Droid, in the
[Android translation-crash census](https://github.com/munimtechnologies/android-translation-crash-census)
(full pass, 2026-10-14: 4,476 repositories, 1,262,958 translations of formatted strings).

- The JVM rejected 382 translations whatever the app passes. l10n-guard 0.5.1 called 375 of them
  errors and the other 7 warnings (recall 0.98 for errors). It never called a translation an error
  that the JVM accepted (precision 1.0).
- 4 of those 7 warnings are a `%t` (date) conversion where the English has `%d`. The JVM check
  passes an `Integer`, which `%t` rejects; but the one app involved passes a `Long`, which `%t`
  accepts and prints as a date. So a warning, not an error, was the right call there.
- 190 more translations crash only if the app passes text for a `%s`; l10n-guard warns on these.

The census data, with a link to every crashing line, is in that repository under `data/`.

## About

Made by MV2 of Munim, Inc., with AI agents. Licensed under the Apache License, Version 2.0
(Apache-2.0); see [LICENSE](LICENSE). Issues and corrections are welcome at
[github.com/munimtechnologies/l10n-guard/issues](https://github.com/munimtechnologies/l10n-guard/issues).
