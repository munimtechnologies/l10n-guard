#!/usr/bin/env python3
"""l10n-guard: catch the mistakes that break translated software and docs.

Checks a translation against its source and reports what changed that should
not have: placeholders, HTML tags, code blocks, inline code, links, numbers,
plural forms, hreflang alternates, and Android strings that would crash
Java's String.format. Standard library only; reads files, never sends
anything.

  python3 l10n_guard.py html       source.html  translated.html
  python3 l10n_guard.py json       en.json      de.json
  python3 l10n_guard.py po         de.po
  python3 l10n_guard.py md         README.md    README.de.md
  python3 l10n_guard.py dir        site         site/de
  python3 l10n_guard.py android    values/strings.xml  values-fr/strings.xml
  python3 l10n_guard.py strings    en.lproj/Localizable.strings  de.lproj/Localizable.strings
  python3 l10n_guard.py xcstrings  Localizable.xcstrings
  python3 l10n_guard.py xliff      messages.de.xlf
  python3 l10n_guard.py qt         app_ar.ts
  python3 l10n_guard.py properties messages.properties  messages_fr.properties
  python3 l10n_guard.py arb        app_en.arb   app_de.arb
  python3 l10n_guard.py resx       Resources.resx  Resources.ja.resx
  python3 l10n_guard.py laravel    lang/en/validation.php  lang/ja/validation.php
  python3 l10n_guard.py rails      config/locales/en.yml  config/locales/ja.yml
  python3 l10n_guard.py symfony    translations/messages.en.yaml  translations/messages.ja.xlf

Exit code 0 = no errors, 1 = errors found, 2 = bad input.
Made by MV2 of Munim, Inc. with AI agents. Licensed under the Apache License,
Version 2.0 (Apache-2.0); see LICENSE.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser

__version__ = "0.12.0"

ERROR = "error"
WARNING = "warning"


def issue(level, code, message, key=None):
    item = {"level": level, "code": code, "message": message}
    if key is not None:
        item["key"] = key
    return item


# ---------------------------------------------------------------- placeholders

_PLACEHOLDER_RES = [
    re.compile(r"\{\{\s*[-\w.]+\s*\}\}"),          # i18next / Handlebars {{name}}
    re.compile(r"%\([\w.]+\)[-+#0]*\d*(?:\.\d+)?[sdifr]"),   # Python %(name)s
    re.compile(r"%\d+\$[-+#0]*\d*(?:\.\d+)?[sdif@]"),        # positional %1$s
    # printf %s %d %.2f. No space flag and no digit before: "50 % de remise"
    # and "50%ige" are prose, not "% d" and "%i".
    re.compile(r"(?<!\d)%[-+#0]*\d*(?:\.\d+)?(?:ll|l|h|z)?[sdifuxXc@]"),
    re.compile(r"\$\{[\w.]+\}"),                    # JS template ${name}
]
_BRACE_ARG_RE = re.compile(r"(?<!\{)\{\s*([A-Za-z_][\w.]*|\d+)\s*(?:,[^{}]*)?(?=[},])")


def placeholders(text):
    """Return a Counter of the placeholders in a string.

    {{name}}, %(name)s, %1$s, %s, ${name} are taken literally. Single-brace
    arguments ({name}, {0}, ICU {count, plural, ...}) count by argument name,
    so translated plural branches inside an ICU message do not matter.
    """
    found = Counter()
    rest = text.replace("%%", "")
    for pattern in _PLACEHOLDER_RES:
        for match in pattern.findall(rest):
            found[re.sub(r"\s+", "", match)] += 1
        rest = pattern.sub(" ", rest)
    for name in _BRACE_ARG_RE.findall(rest):
        found["{%s}" % name] += 1
    return found


# Letters for HTML; digits for react-i18next <Trans> slots like <0>...</0>.
_TAG_RE = re.compile(r"</?([A-Za-z][\w:-]*|\d+)[^<>]*?/?>")


def tags(text):
    """Counter of HTML/XML-ish tag names in a string, keeping open vs close."""
    found = Counter()
    for match in _TAG_RE.finditer(text):
        whole = match.group(0)
        name = match.group(1).lower()
        if whole.startswith("</"):
            found["</%s>" % name] += 1
        elif whole.endswith("/>"):
            found["<%s/>" % name] += 1
        else:
            found["<%s>" % name] += 1
    return found


# Percent signs that look like % but that no formatter reads: printf,
# String.format and Python print "٪s" or "％1$d" as written, and the value
# meant for it is never shown.
_LOOKALIKE_PERCENTS = {"٪": "the Arabic percent sign ٪ (U+066A)",
                       "％": "the fullwidth percent sign ％ (U+FF05)",
                       "﹪": "the small percent sign ﹪ (U+FE6A)"}


def _lookalike(name, target):
    """How target writes the %-placeholder name with a look-alike percent
    sign ("٪s", "％1$d", "٪ 1$S"), or None."""
    if not name.startswith("%"):
        return None
    m = re.search("[%s] ?%s" % ("".join(_LOOKALIKE_PERCENTS), re.escape(name[1:])), target, re.I)
    return m.group(0) if m else None


# Braces that look like { and } but that no formatter reads (0.8.0): .NET
# string.Format, Java MessageFormat, ICU and Python's str.format show "｛0｝"
# as written. Chinese and Japanese input methods type them, often with
# fullwidth digits inside ("｛０｝").
_LOOKALIKE_BRACES = {"｛": "the fullwidth left brace ｛ (U+FF5B)",
                     "｝": "the fullwidth right brace ｝ (U+FF5D)"}
_BRACE_NAME_RE = re.compile(r"(\{+)\s*([^{}\s]+)\s*\}+$")


def _fullwidth_class(c):
    """A regex for c or its fullwidth form (０ for 0, ｎ for n)."""
    if "!" <= c <= "~":
        return "[%s%s]" % (re.escape(c), chr(ord(c) + 0xFEE0))
    return re.escape(c)


def _lookalike_brace(name, target):
    """How target writes the brace placeholder name ({0}, {name}, {{name}})
    with a fullwidth brace ("｛0｝", "｛０｝", "｛0}", "｛｛link｝｝", ICU
    "｛count，"), or None."""
    m = _BRACE_NAME_RE.match(name)
    if not m:
        return None
    depth = len(m.group(1))
    inner = "".join(_fullwidth_class(c) for c in m.group(2))
    pattern = r"[{｛]{%d}\s*%s\s*(?:[}｝]{%d}|[,，])" % (depth, inner, depth)
    for found in re.finditer(pattern, target, re.I):
        if any(brace in found.group(0) for brace in _LOOKALIKE_BRACES):
            return found.group(0)
    return None


def _seen_lookalike(name, source, target):
    """(how target writes name with a look-alike, what the look-alike is,
    code), or None. Fullwidth braces the source has too are text."""
    seen = _lookalike(name, target)
    if seen:
        return seen, _LOOKALIKE_PERCENTS[seen[0]], "lookalike-percent"
    seen = _lookalike_brace(name, target)
    if seen and seen not in source:
        brace = next(c for c in seen if c in _LOOKALIKE_BRACES)
        return seen, _LOOKALIKE_BRACES[brace], "lookalike-brace"
    return None


def _lookalike_issues(source, target, missing, key):
    """Placeholders written with a look-alike percent sign or fullwidth
    braces. The missing ones explained this way are taken out of missing (a
    list, changed in place)."""
    problems = []
    lost = [(name, _seen_lookalike(name, source, target)) for name in missing]
    lost = [(name, found) for name, found in lost if found]
    for name, (seen, what, code) in lost:
        missing.remove(name)
        message = ("%s is written \"%s\" with %s, which no formatter reads: the text is shown as "
                   "written and the value is lost" % (name, seen, what))
        if code == "lookalike-brace" and ("{" in seen or "}" in seen):
            message += ("; with one brace still ASCII, .NET string.Format and Python str.format "
                        "throw on it instead")
        problems.append(issue(ERROR, code, message, key))
    for name in sorted(set(placeholders(source)) - {name for name, _ in lost}):
        found = _seen_lookalike(name, source, target)
        if found:
            seen, what, code = found
            problems.append(issue(WARNING, code,
                                  "\"%s\" is written with %s, which no formatter reads, so it is "
                                  "shown as written; the value itself appears at the ASCII %s"
                                  % (seen, what, name), key))
    return problems


# A Japanese translation sometimes keeps a word's katakana reading between
# fullwidth number signs (削除＃サクジョ＃ for "Delete"), as some machine
# translation and dictionary tools write it: users see the reading as text
# (0.11.0). A warning, since nothing breaks. The sign must follow a character
# other than a space or ＃, so a hashtag (＃タグ) or ICU's ＃ isn't one.
_READING_LEAK_RE = re.compile(r"(?<=[^\s＃])＃[ァ-ヺー]+＃")


def _reading_leak(source, target, key=None):
    """A reading-leak warning when target shows a katakana reading between
    fullwidth number signs and source has no # or ＃; else []."""
    if not isinstance(source, str) or not isinstance(target, str):
        return []
    if "#" in source or "＃" in source:
        return []
    found = _READING_LEAK_RE.findall(target)
    if not found:
        return []
    return [issue(WARNING, "reading-leak",
                  "%s: a katakana reading between fullwidth number signs, which users see as "
                  "text; the source has no number sign" % ", ".join(found), key)]


def _diff(source, target):
    missing = source - target
    extra = target - source
    return sorted(missing.elements()), sorted(extra.elements())


def check_pair(source, target, key=None):
    """Checks one translated string against its source string."""
    problems = []
    if not isinstance(target, str) or not target.strip():
        if isinstance(source, str) and source.strip():
            problems.append(issue(WARNING, "empty", "translation is empty", key))
        return problems
    missing, extra = _diff(placeholders(source), placeholders(target))
    problems.extend(_lookalike_issues(source, target, missing, key))
    if missing:
        problems.append(issue(ERROR, "placeholder-missing",
                              "placeholder(s) missing: %s" % ", ".join(missing), key))
    if extra:
        problems.append(issue(ERROR, "placeholder-extra",
                              "placeholder(s) not in source: %s" % ", ".join(extra), key))
    missing, extra = _diff(tags(source), tags(target))
    if missing or extra:
        parts = []
        if missing:
            parts.append("missing " + " ".join(missing))
        if extra:
            parts.append("extra " + " ".join(extra))
        problems.append(issue(ERROR, "tags", "markup differs: %s" % "; ".join(parts), key))
    problems.extend(_reading_leak(source, target, key))
    if source.strip() and target.strip() == source.strip() and re.search(r"[A-Za-z]{4,}", source):
        problems.append(issue(WARNING, "untranslated", "translation is identical to source", key))
    return problems


def _check_form(source, target, key, quantity):
    """check_pair for one plural form. zero/one/two forms often spell the
    number out ("one file", "un fichier"), so a missing placeholder there is
    only a warning."""
    found = check_pair(source, target, key)
    if quantity in ("zero", "one", "two"):
        for p in found:
            if p["code"] == "placeholder-missing":
                p["level"] = WARNING
    return found


# ------------------------------------------------------------- Java Formatter

# java.util.Formatter's specifier syntax. Android passes every string the app
# gives arguments to (getString(id, args), getQuantityString, Compose
# stringResource) through String.format, which parses the whole string first
# and throws on any % it can't read.
_JAVA_SPEC_RE = re.compile(r"%(\d+\$)?([-#+ 0,(<]*)?(\d+)?(\.\d+)?([tT])?([a-zA-Z%])")
_JAVA_KINDS = {"b": "any", "h": "any", "s": "any", "c": "char",
               "d": "int", "o": "int", "x": "int",
               "e": "float", "f": "float", "g": "float", "a": "float"}
_JAVA_UPPER = set("BHSCXEGA")
_JAVA_DATE = set("HIklMSLNpzZsQBbhAaCYyjmdeRTrDFc")
# Flags each conversion refuses (FormatFlagsConversionMismatchException).
# '#' on %s needs a Formattable argument, which app strings never get.
_JAVA_BAD_FLAGS = {"b": "#+ 0,(", "h": "#+ 0,(", "s": "#+ 0,(", "c": "#+ 0,(",
                   "d": "#", "o": ",", "x": ",", "e": ",", "f": "", "g": "#", "a": "(,"}
_JAVA_KIND_NAMES = {"any": "general (%s)", "char": "a character (%c)",
                    "int": "an integer (%d)", "float": "a decimal (%f)", "date": "a date (%t)"}


class JavaFormatError(ValueError):
    """What java.util.Formatter would throw; .exception is its class name and
    .pos the index of the % it stops at."""

    def __init__(self, exception, detail, pos=None):
        super().__init__("%s (%s)" % (exception, detail))
        self.exception = exception
        self.pos = pos


def _java_specs(text):
    """java_format, keeping each specifier's match: [(argument number, kind,
    match)]."""
    specs = []
    ordinary = last = 0
    pos = 0
    while True:
        m = _JAVA_SPEC_RE.search(text, pos)
        end = m.start() if m else len(text)
        bad = text.find("%", pos, end)
        if bad >= 0:
            after = text[bad + 1] if bad + 1 < end else "%"
            raise JavaFormatError("UnknownFormatConversionException", "Conversion = '%s'" % after,
                                  bad)
        if not m:
            return specs
        pos = m.end()
        at = m.start()
        index, flags, width, precision, dt, conv = m.groups()
        flags = flags or ""
        spec = m.group(0)
        if len(set(flags)) != len(flags):
            raise JavaFormatError("DuplicateFormatFlagsException", spec, at)
        if dt:
            kind, rule = "date", "c"
            if conv not in _JAVA_DATE:
                raise JavaFormatError("UnknownFormatConversionException",
                                      "Conversion = 't%s'" % conv, at)
        elif conv in "%n":
            kind, rule = None, conv
        elif conv.lower() in _JAVA_KINDS and (conv.islower() or conv in _JAVA_UPPER):
            kind, rule = _JAVA_KINDS[conv.lower()], conv.lower()
        else:
            raise JavaFormatError("UnknownFormatConversionException", "Conversion = '%s'" % conv, at)
        if kind is None:
            if precision:
                raise JavaFormatError("IllegalFormatPrecisionException", spec, at)
            if flags not in ("", "-") or (conv == "n" and (flags or width)):
                raise JavaFormatError("IllegalFormatFlagsException", spec, at)
            if "-" in flags and not width:
                raise JavaFormatError("MissingFormatWidthException", spec, at)
            continue
        if kind in ("int", "float"):
            if not width and ("-" in flags or "0" in flags):
                raise JavaFormatError("MissingFormatWidthException", spec, at)
            if ("+" in flags and " " in flags) or ("-" in flags and "0" in flags):
                raise JavaFormatError("IllegalFormatFlagsException", spec, at)
        if precision and kind in ("char", "int", "date"):
            raise JavaFormatError("IllegalFormatPrecisionException", spec, at)
        for flag in flags:
            if flag in _JAVA_BAD_FLAGS[rule]:
                raise JavaFormatError("FormatFlagsConversionMismatchException", spec, at)
        if "-" in flags and not width:
            raise JavaFormatError("MissingFormatWidthException", spec, at)
        if "<" in flags:
            if not last:
                raise JavaFormatError("MissingFormatArgumentException", spec, at)
            number = last
        elif index:
            number = int(index[:-1])
            if number == 0:
                raise JavaFormatError("IllegalFormatArgumentIndexException", spec, at)
            last = number
        else:
            ordinary += 1
            number = last = ordinary
        specs.append((number, kind, m))


def java_format(text):
    """Parses text as String.format does. Returns [(argument number, kind)]
    for each specifier that takes an argument (kind: any, char, int, float or
    date); raises JavaFormatError where Java would throw."""
    return [(number, kind) for number, kind, _ in _java_specs(text)]


def java_formatted(text):
    """The (argument, kind) list if text is a string an app would pass to
    String.format: Java can parse it and at least one specifier is meant as
    one, not prose like "50% off" (a space flag or a digit before the %).
    Otherwise None."""
    try:
        specs = java_format(text)
    except JavaFormatError:
        return None
    for m in _JAVA_SPEC_RE.finditer(text):
        if m.group(6) in "%n" and not m.group(5):
            continue
        if " " in (m.group(2) or "") or (m.start() and text[m.start() - 1].isdigit()):
            continue
        return specs
    return None


def _java_clash(src_kind, tgt_kind):
    """None if Java accepts the source's argument for the translation's
    specifier, "crash" if it never does, "maybe" if it depends on the value
    the app passes (a %s argument may be text or a number)."""
    if tgt_kind == "any" or src_kind == tgt_kind:
        return None
    if src_kind == "any" or (src_kind, tgt_kind) in (("int", "char"), ("int", "date"),
                                                     ("date", "int")):
        return "maybe"
    return "crash"


def _lone_percent(text, pos):
    """True if the % at pos reads as a percent sign in prose ("50 % de",
    "50%ige", "25% adicional", "100%.") rather than as a placeholder."""
    after = text[pos + 1:pos + 2]
    if after == "%":
        return False
    if not after or after.isspace() or (pos and text[pos - 1].isdigit()):
        return True
    if after.isalpha():
        return not after.isascii()
    return not after.isdigit() and after not in "$<-#+0,("


def _space_flagged(source, target, m, tgt):
    """True if a "% d" in the translation is the source's "%d" written with a
    space flag (a translator's typo that Java prints as " 5"), not a percent
    sign in prose: no digit before it ("50 % de"), no Latin letter right
    after it ("% de"), and no placeholder more than the source has."""
    spec = m.group(0)
    if spec.replace(" ", "") not in _arg_specs(source) or len(tgt) != len(_arg_specs(source)):
        return False
    before = target[:m.start()].rstrip(" ")
    if before and before[-1].isdigit():
        return False
    after = target[m.end():m.end() + 1]
    return not (after.isalpha() and after.isascii())


def _context(text, pos):
    """A few characters either side of pos, for messages."""
    start, end = max(0, pos - 10), min(len(text), pos + 10)
    return "%s%s%s" % ("..." if start else "", text[start:end], "..." if end < len(text) else "")


_PERCENT_HINT = "; if the %% in \"%s\" is a percent sign, write it as %%%%"


def _numbered(n, spec):
    return "%%%d$%s" % (n, spec[1:])


def _arg_specs(text):
    """The specifiers in text that take an argument, as written."""
    return [m.group(0) for m in _JAVA_SPEC_RE.finditer(text)
            if m.group(5) or m.group(6) not in "%n"]


def _java_order(source, kinds, passed, tgt, key):
    """The translation's placeholders hold the source's types in another
    order: unnumbered ones moved (Java fills them left to right), or numbered
    ones whose types are swapped. Either way each value lands in the wrong
    place, and String.format throws where text reaches a %d."""
    if passed < 2 or sorted(kinds) != list(range(1, passed + 1)):
        return []
    want = [kinds[n] for n in range(1, passed + 1)]
    unnumbered = not any(m.group(1) or "<" in (m.group(2) or "") for _, _, m in tgt)
    if unnumbered and len(tgt) == passed:
        got = [kind for _, kind, _ in tgt]
        if got == want or sorted(got) != sorted(want):
            return []
        used, fixed = set(), []
        for _, kind, m in tgt:
            n = next(k for k in range(1, passed + 1) if kinds[k] == kind and k not in used)
            used.add(n)
            fixed.append(_numbered(n, m.group(0)))
        return [issue(ERROR, "java-format", "unnumbered placeholders in a new order (%s in the "
                      "source, %s here): String.format fills them left to right, so the values "
                      "land in the wrong places, and it throws IllegalFormatConversionException "
                      "where a value doesn't fit its new placeholder; number them to reorder: %s"
                      % (" ... ".join(_arg_specs(source)), " ... ".join(m.group(0) for _, _, m in tgt),
                         " ... ".join(fixed)), key)]
    if all(m.group(1) for _, _, m in tgt):
        got = {}
        for n, kind, _ in tgt:
            if got.get(n, "any") == "any":
                got[n] = kind
        if sorted(got) != sorted(kinds) or got == kinds:
            return []
        if sorted(got.values()) != sorted(kinds.values()):
            return []
        swapped = [n for n in sorted(kinds) if kinds[n] != got[n]]
        return [issue(ERROR, "java-format", "argument numbers look swapped: %s in the source, %s "
                      "here. Each value lands in the wrong place, and String.format throws "
                      "IllegalFormatConversionException where a value doesn't fit; check which "
                      "number is which"
                      % (", ".join("%d is %s" % (n, _JAVA_KIND_NAMES[kinds[n]]) for n in swapped),
                         ", ".join("%d is %s" % (n, _JAVA_KIND_NAMES[got[n]]) for n in swapped)),
                      key)]
    return []


def check_java_format(source, target, key=None):
    """Checks a translation of a string the app formats with String.format.
    Java reads the whole translation before printing, so one stray % (as in
    "50 % de", "100 % sûr" or "50%ige"), an argument the source doesn't pass,
    or a %d for the source's %f crashes the app in that language. Placeholders
    moved without numbers, swapped numbers and a %1$d broken up as 1%d are
    errors too: they put the wrong value in each place even where nothing
    throws. The source's %d written "% d" is only a warning: Java prints the
    number with a leading space."""
    src = java_formatted(source)
    if not src:
        return []
    passed = max(n for n, _ in src)
    kinds = {}
    for n, kind in src:
        if kinds.get(n, "any") == "any":
            kinds[n] = kind
    try:
        tgt = _java_specs(target)
    except JavaFormatError as exc:
        message = "String.format would throw %s" % exc
        if exc.pos is not None and _lone_percent(target, exc.pos):
            message += _PERCENT_HINT % _context(target, exc.pos)
        return [issue(ERROR, "java-format", message, key)]
    problems = []
    in_source = set(_arg_specs(source))
    stray = set()
    for i, (n, kind, m) in enumerate(tgt):
        spec = m.group(0)
        if spec in in_source or m.group(1):
            continue
        before = target[m.start() - 1] if m.start() else ""
        if before.isdigit() and "%" + before + "$" in source and "%" + before + "$" not in target:
            problems.append(issue(ERROR, "java-format", "\"%s%s\" looks like %s with the %% moved "
                                  "after the %s: String.format prints the digit %s and fills %s "
                                  "with argument %d"
                                  % (before, spec, _numbered(int(before), spec), before, before,
                                     spec, n), key))
        elif " " in (m.group(2) or "") and _space_flagged(source, target, m, tgt):
            problems.append(issue(WARNING, "java-format-flag", "\"%s\" in \"%s\" is the source's %s "
                                  "with a space flag: String.format prints argument %d with a "
                                  "leading space; write %s unless the space is wanted"
                                  % (spec, _context(target, m.start()), spec.replace(" ", ""), n,
                                     spec.replace(" ", "")), key))
        elif " " in (m.group(2) or "") or before.isdigit():
            stray.add(i)
            clash = _java_clash(kinds.get(n, "any"), kind) if n <= passed else None
            if n > passed:
                effect = "throw MissingFormatArgumentException (the source passes %d)" % passed
            elif clash == "crash":
                effect = "throw IllegalFormatConversionException"
            elif clash == "maybe":
                effect = ("throw IllegalFormatConversionException unless the app passes a "
                          "matching value")
            else:
                effect = "print argument %d there" % n
            problems.append(issue(ERROR, "java-format", "String.format reads \"%s\" in \"%s\" as a "
                                  "placeholder for argument %d and would %s; write %%%% for a "
                                  "percent sign" % (spec, _context(target, m.start()), n, effect),
                                  key))
    if not stray:
        order = _java_order(source, kinds, passed, tgt, key)
        if order:
            return problems + order
    for i, (n, kind, _) in enumerate(tgt):
        if i in stray:
            continue
        if n > passed:
            problems.append(issue(ERROR, "java-format", "uses argument %d but the source passes %d, "
                                  "so String.format would throw MissingFormatArgumentException"
                                  % (n, passed), key))
            continue
        if n not in kinds:
            continue
        clash = _java_clash(kinds[n], kind)
        if clash == "crash":
            problems.append(issue(ERROR, "java-format", "argument %d is %s in the source but %s "
                                  "here, so String.format would throw "
                                  "IllegalFormatConversionException"
                                  % (n, _JAVA_KIND_NAMES[kinds[n]], _JAVA_KIND_NAMES[kind]), key))
        elif clash == "maybe":
            problems.append(issue(WARNING, "java-format-type", "argument %d is %s in the source but "
                                  "%s here; String.format throws IllegalFormatConversionException "
                                  "unless the app passes a matching value"
                                  % (n, _JAVA_KIND_NAMES[kinds[n]], _JAVA_KIND_NAMES[kind]), key))
    return problems


# --------------------------------------------------------------- JSON catalogs

def flatten(data, prefix=""):
    """Flattens nested JSON catalogs (i18next, vue-i18n, next-intl) to dotted keys."""
    flat = {}
    if isinstance(data, dict):
        for k, v in data.items():
            path = "%s.%s" % (prefix, k) if prefix else str(k)
            flat.update(flatten(v, path))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            flat.update(flatten(v, "%s[%d]" % (prefix, i)))
    else:
        flat[prefix] = data
    return flat


_PLURAL_SUFFIX_RE = re.compile(r"_(zero|one|two|few|many|other)$")


# Two keys whose source texts differ only by antonyms ("Default expanded" /
# "Default collapse", "Mute" / "Unmute") but share one translation: one of the
# two labels says the opposite of what it does, or users can't tell them
# apart. A source fix that keeps the old translations leaves this shape
# (0.12.0). A warning. The word classes were fixed in the census's
# antonym-collision/PREREG.md before any scan; antonyms outside them
# ("Visible" / "Hidden") are missed.
_ANTONYM_CLASSES = {
    "EXPAND": ("expand expands expanded expanding unfold unfolded",
               "collapse collapses collapsed collapsing fold folded"),
    "SHOW": ("show shows showing shown", "hide hides hiding hidden"),
    "ENABLE": ("enable enables enabled enabling", "disable disables disabled disabling"),
    "OPEN": ("open opens opened opening", "close closes closed closing"),
    "LOCK": ("lock locks locked locking", "unlock unlocks unlocked unlocking"),
    "ALLOW": ("allow allows allowed allowing",
              "deny denies denied denying disallow disallowed forbid forbidden"),
    "VISIBLE": ("visible", "invisible"),
    "SORT": ("ascending asc", "descending desc"),
    "INCREASE": ("increase increases increased", "decrease decreases decreased"),
    "MAX": ("max maximum", "min minimum"),
    "INCLUDE": ("include includes included including", "exclude excludes excluded excluding"),
    "SELECT": ("select selected", "deselect deselected unselect unselected"),
    "PIN": ("pin pinned", "unpin unpinned"),
    "MUTE": ("mute muted", "unmute unmuted"),
    "FOLLOW": ("follow followed", "unfollow unfollowed"),
    "BLOCK": ("block blocked", "unblock unblocked"),
    "FAVOURITE": ("favourite favorite favourited favorited",
                  "unfavourite unfavorite unfavourited unfavorited"),
    "BOOKMARK": ("bookmark bookmarked", "unbookmark unbookmarked"),
    "SUBSCRIBE": ("subscribe subscribed", "unsubscribe unsubscribed"),
    "ARCHIVE": ("archive archived", "unarchive unarchived"),
    "ADD": ("add added", "remove removed"),
    "IMPORT": ("import imported", "export exported"),
    "UPLOAD": ("upload uploaded", "download downloaded"),
    "START": ("start starts started", "end ends ended"),
    "BEFORE": ("before", "after"),
    "ABOVE": ("above", "below"),
    "LEFT": ("left", "right"),
    "FIRST": ("first", "last"),
    "NEXT": ("next", "previous prev"),
    "MORE": ("more", "less"),
    "IN": ("in", "out"),
    "ON": ("on", "off"),
    "YES": ("yes", "no"),
    "TRUE": ("true", "false"),
    "READ": ("read", "unread"),
    "PUBLIC": ("public", "private"),
    "ONLINE": ("online", "offline"),
    "CONNECT": ("connect connected", "disconnect disconnected"),
    "LOGIN": ("login", "logout"),
    "REQUIRED": ("required", "optional"),
}
_ANTONYMS = {}
for _cls, (_plus, _minus) in _ANTONYM_CLASSES.items():
    for _word in _plus.split():
        _ANTONYMS[_word] = (_cls, 1)
    for _word in _minus.split():
        _ANTONYMS[_word] = (_cls, -1)
_WORD_RE = re.compile(r"[a-z]+")


def _antonym_signature(text):
    """(words with antonyms replaced by their class, polarity of each word)."""
    sig, pol = [], []
    for word in _WORD_RE.findall(text.lower()):
        cls, p = _ANTONYMS.get(word, (word, 0))
        sig.append(cls)
        pol.append(p)
    return tuple(sig), tuple(pol)


def antonym_pairs(source):
    """Sorted (key1, key2) of keys whose source texts differ only by an odd
    number of antonym flips (inflections of one side don't count)."""
    groups = {}
    for key, text in source.items():
        if not isinstance(text, str):
            continue
        sig, pol = _antonym_signature(text)
        if any(pol):
            groups.setdefault(sig, []).append((key, pol))
    pairs = []
    for members in groups.values():
        members.sort()
        for i, (k1, p1) in enumerate(members):
            for k2, p2 in members[i + 1:]:
                if sum(1 for a, b in zip(p1, p2) if a and a != b) % 2:
                    pairs.append((k1, k2))
    return sorted(pairs)


def _antonym_collisions(source, target):
    """antonym-collision warnings for two flattened catalogs. A shared value
    equal to either source text is an untranslated copy, not a collision."""
    problems = []
    for k1, k2 in antonym_pairs(source):
        v1, v2 = target.get(k1), target.get(k2)
        if not isinstance(v1, str) or not isinstance(v2, str):
            continue
        v1, v2 = v1.strip(), v2.strip()
        if not v1 or v1 != v2:
            continue
        if v1.casefold() in (source[k1].strip().casefold(), source[k2].strip().casefold()):
            continue
        p = issue(WARNING, "antonym-collision",
                  "same translation as %s (%r), though the sources say opposite things: %r / %r"
                  % (k2, v1, source[k1], source[k2]), k1)
        p["other_key"] = k2
        problems.append(p)
    return problems


def check_catalog(source, target):
    """Compares two loaded JSON catalogs (dicts). Returns a list of issues."""
    src, tgt = flatten(source), flatten(target)
    problems = []
    src_bases = {_PLURAL_SUFFIX_RE.sub("", k) for k in src}
    tgt_plural_bases = {_PLURAL_SUFFIX_RE.sub("", k) for k in tgt if _PLURAL_SUFFIX_RE.search(k)}
    for key in sorted(src):
        if key in tgt:
            if isinstance(src[key], str):
                problems.extend(check_pair(src[key], tgt[key], key))
            elif type(src[key]) is not type(tgt[key]):
                problems.append(issue(ERROR, "type", "value type changed from %s to %s"
                                      % (type(src[key]).__name__, type(tgt[key]).__name__), key))
        elif not (_PLURAL_SUFFIX_RE.search(key) and
                  _PLURAL_SUFFIX_RE.sub("", key) in tgt_plural_bases):
            # A missing _one is fine when the language has other plural forms (ja: _other only).
            problems.append(issue(WARNING, "missing-key", "key missing from translation", key))
    for key in sorted(tgt):
        if key in src:
            continue
        base = _PLURAL_SUFFIX_RE.sub("", key)
        if _PLURAL_SUFFIX_RE.search(key) and base in src_bases:
            # Languages have different plural categories (pl: few/many). Check
            # against the source's _other form.
            other = src.get(base + "_other")
            if isinstance(other, str):
                problems.extend(check_pair(other, tgt[key], key))
            continue
        problems.append(issue(WARNING, "extra-key", "key not in source", key))
    problems.extend(_antonym_collisions(src, tgt))
    return problems


# --------------------------------------------------------------------- gettext

def _po_unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    out, i = [], 0
    escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(escapes.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def parse_po(text):
    """Parses a .po file into a list of entry dicts.

    Each entry: msgctxt, msgid, msgid_plural, msgstr (str) or msgstr_plural
    (dict index -> str), flags (set), obsolete (bool), line (int).
    """
    entries = []
    entry = None
    field = None
    pending_flags = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        obsolete = False
        if line.startswith("#~"):
            obsolete = True
            line = line[2:].strip()
        elif line.startswith("#,"):
            pending_flags |= {f.strip() for f in line[2:].split(",") if f.strip()}
            continue
        elif line.startswith("#") or not line:
            continue
        if line.startswith('"'):
            if entry is None or field is None:
                continue
            value = _po_unquote(line)
            if isinstance(field, int):
                entry["msgstr_plural"][field] += value
            else:
                entry[field] = (entry[field] or "") + value
            continue
        keyword, _, rest = line.partition(" ")
        # msgctxt or msgid after a msgid means the next entry has begun.
        if entry is None or (keyword in ("msgctxt", "msgid") and entry["msgid"] is not None):
            if entry is not None:
                entries.append(entry)
            entry = {"msgctxt": None, "msgid": None, "msgid_plural": None, "msgstr": None,
                     "msgstr_plural": {}, "flags": pending_flags, "obsolete": False,
                     "line": lineno}
            pending_flags = set()
        entry["obsolete"] = entry["obsolete"] or obsolete
        plural = re.match(r"msgstr\[(\d+)\]$", keyword)
        if plural:
            field = int(plural.group(1))
            entry["msgstr_plural"][field] = _po_unquote(rest)
        elif keyword in ("msgctxt", "msgid", "msgid_plural", "msgstr"):
            field = keyword
            entry[field] = _po_unquote(rest)
        else:
            field = None
    if entry is not None and entry["msgid"] is not None:
        entries.append(entry)
    return entries


def _nplurals(entries):
    for e in entries:
        if e["msgid"] == "" and e["msgctxt"] is None:
            m = re.search(r"nplurals\s*=\s*(\d+)", e["msgstr"] or "")
            if m:
                return int(m.group(1))
    return None


def check_po(text):
    """Checks a translated .po file. Returns (issues, stats)."""
    entries = [e for e in parse_po(text) if not e["obsolete"]]
    nplurals = _nplurals(entries)
    problems = []
    stats = {"entries": 0, "translated": 0, "fuzzy": 0, "untranslated": 0}
    for e in entries:
        if e["msgid"] == "":
            continue
        stats["entries"] += 1
        label = "line %d" % e["line"]
        if "fuzzy" in e["flags"]:
            stats["fuzzy"] += 1
        if e["msgid_plural"] is not None:
            forms = e["msgstr_plural"]
            if not any(v.strip() for v in forms.values()):
                stats["untranslated"] += 1
                continue
            if nplurals is not None and len(forms) != nplurals:
                problems.append(issue(ERROR, "plural-count", "%d plural forms, header says %d"
                                      % (len(forms), nplurals), label))
            for idx, value in sorted(forms.items()):
                # Form 0 may drop the number (e.g. "one file"), so a missing
                # placeholder there is only a warning. With one plural form
                # (ja, zh, ko), msgstr[0] covers every count.
                if nplurals == 1:
                    source = e["msgid_plural"]
                else:
                    source = e["msgid"] if idx == 0 else e["msgid_plural"]
                for p in check_pair(source, value, "%s msgstr[%d]" % (label, idx)):
                    if idx == 0 and p["code"] == "placeholder-missing" and nplurals != 1:
                        p["level"] = WARNING
                    problems.append(p)
        else:
            if not (e["msgstr"] or "").strip():
                stats["untranslated"] += 1
                continue
            problems.extend(check_pair(e["msgid"], e["msgstr"], label))
        if "fuzzy" not in e["flags"]:
            stats["translated"] += 1
    return problems, stats


# --------------------------------------------------------------------- Android

def _local(tag):
    """Element name without its {namespace}."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _inner_xml(el):
    """An element's content as text with its child elements written as plain
    <name>...</name> (namespaces and attributes dropped), so markup can be
    compared between source and translation."""
    parts = [el.text or ""]
    for child in el:
        name = _local(child.tag)
        parts.append("<%s>%s</%s>" % (name, _inner_xml(child), name))
        parts.append(child.tail or "")
    return "".join(parts)


def _runtime_xml(el):
    """An element's content as the app gets it: text kept, child elements'
    tags dropped (their content and tails kept)."""
    parts = [el.text or ""]
    for child in el:
        parts.append(_runtime_xml(child))
        parts.append(child.tail or "")
    return "".join(parts)


class _AndroidString(str):
    """parse_android's text for one string, plus .runtime from the XML tree.
    In the text, <b> from an element and <b> written &lt;b&gt; look alike;
    in .runtime only the second is there."""

    def __new__(cls, text, runtime=None):
        self = super().__new__(cls, text)
        self.runtime = text if runtime is None else runtime
        return self


def _android_string(el):
    return _AndroidString(_inner_xml(el), _runtime_xml(el))


_QUANTITY_KEY_RE = re.compile(r"^(.*)\[(zero|one|two|few|many|other)\]$")
_ARRAY_KEY_RE = re.compile(r"\[\d+\]$")
_QUANTITIES = ("other", "many", "few", "two", "one", "zero")


def parse_android(text):
    """Reads an Android strings.xml into {key: text}. Plurals become
    name[one], name[other], ...; string arrays name[0], name[1], ...
    Strings marked translatable="false" are skipped.
    """
    root = ET.fromstring(text)
    out = {}
    for el in root:
        kind = _local(el.tag)
        name = el.get("name")
        if not name or el.get("translatable") == "false":
            continue
        if kind == "string":
            out[name] = _android_string(el)
        elif kind == "plurals":
            for item in el:
                if _local(item.tag) == "item" and item.get("quantity"):
                    out["%s[%s]" % (name, item.get("quantity"))] = _android_string(item)
        elif kind == "string-array":
            items = [item for item in el if _local(item.tag) == "item"]
            for i, item in enumerate(items):
                out["%s[%d]" % (name, i)] = _android_string(item)
    return out


def android_unformatted(text):
    """Names of the <string>s and <plurals> marked formatted="false"."""
    return {el.get("name") for el in ET.fromstring(text)
            if el.get("name") and el.get("formatted") == "false"}


_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def _join_surrogates(text):
    """Emoji written as two escapes (\\uD83D\\uDE00) unescape to a UTF-16
    surrogate pair; joins each pair into the character it encodes. A lone
    surrogate becomes U+FFFD, so the text can always be printed and encoded."""
    if not _SURROGATE_RE.search(text):
        return text
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


# parse_android writes a child element as a bare <name>...</name>, which looks
# just like markup that is text in the XML (CDATA, &lt;a href="%2$s"&gt;,
# &lt;/a&gt;) and reaches the app as written. Its strings carry .runtime, read
# from the tree (0.7.2); _ELEMENT_RE is only for plain strings passed in.
_ELEMENT_RE = re.compile(r"</?[A-Za-z][\w:.-]*/?>")


def _android_text(raw):
    """The string an app gets at runtime from parse_android's text: element
    markup dropped (markup that is text, from CDATA or &lt;, is kept whole,
    closing tags too), double quotes removed, backslash escapes resolved
    and, outside quotes, runs of whitespace collapsed to one space (as aapt2
    does)."""
    text = getattr(raw, "runtime", None)
    if text is None:
        text = _ELEMENT_RE.sub("", raw)
    out, quoted, pending = [], False, False
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace() and not quoted:
            pending = True
            i += 1
            continue
        if pending and out:
            out.append(" ")
        pending = False
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "u" and re.match(r"[0-9A-Fa-f]{4}$", text[i + 2:i + 6]):
                out.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
            i += 2
        elif c == '"':
            quoted = not quoted
            i += 1
        else:
            out.append(c)
            i += 1
    return _join_surrogates("".join(out))


_QUOTED_RE = re.compile(r'(?<!\\)"(?:[^"\\]|\\.)*"', re.S)
_BARE_APOSTROPHE_RE = re.compile(r"(?<!\\)'")


def _android_apostrophe(text):
    """True if aapt would reject the text: an apostrophe that is neither
    escaped (\\') nor inside double quotes. &apos; does not escape it."""
    return bool(_BARE_APOSTROPHE_RE.search(_QUOTED_RE.sub("", text)))


def _plural_forms(src, base):
    """The source's quantity forms of one <plurals>, other first."""
    return [src[k] for k in ("%s[%s]" % (base, q) for q in _QUANTITIES) if k in src]


def _plural_format_source(src, base):
    """getQuantityString formats every quantity with the same arguments, so a
    translated form may use any argument some source form uses ("File from
    %1$s" for one, "%2$d of %3$d files from %1$s" for other). Returns the
    source form that reads the most arguments, other on a tie."""
    best, most = None, -1
    for form in _plural_forms(src, base):
        specs = java_formatted(_android_text(form)) or []
        count = max((n for n, _ in specs), default=0)
        if count > most:
            best, most = form, count
    return best


def check_android(source_text, target_text):
    """Compares a translated strings.xml (values-fr/) with the source (values/)."""
    src, tgt = parse_android(source_text), parse_android(target_text)
    unformatted = android_unformatted(source_text)
    problems = []
    tgt_plural_bases = set()
    for key in tgt:
        m = _QUANTITY_KEY_RE.match(key)
        if m:
            tgt_plural_bases.add(m.group(1))
    for key in sorted(src):
        if key in tgt:
            continue
        m = _QUANTITY_KEY_RE.match(key)
        if m and m.group(1) in tgt_plural_bases:
            continue  # this language uses other plural categories (ja: other only)
        problems.append(issue(WARNING, "missing-key", "key missing from translation", key))
    for key in sorted(tgt):
        m = _QUANTITY_KEY_RE.match(key)
        if key in src:
            source = src[key]
        elif m and m.group(1) + "[other]" in src:
            source = src[m.group(1) + "[other]"]
        else:
            problems.append(issue(WARNING, "extra-key", "key not in source", key))
            continue
        found = _check_form(source, tgt[key], key, m.group(2) if m else None)
        if m:
            # Every quantity gets the same arguments, so a form may use one
            # that only another source form shows.
            shared = set()
            for form in _plural_forms(src, m.group(1)):
                shared |= set(placeholders(form))
            if not set(placeholders(tgt[key])) - shared:
                found = [p for p in found if p["code"] != "placeholder-extra"]
        problems.extend(found)
        if _android_apostrophe(tgt[key]):
            problems.append(issue(ERROR, "android-apostrophe",
                                  "apostrophe must be written \\' (or the text put in double "
                                  "quotes), or the build fails", key))
        # getStringArray never formats; a formatted="false" string isn't formatted.
        if not _ARRAY_KEY_RE.search(key) and (m.group(1) if m else key) not in unformatted:
            if m:
                source = _plural_format_source(src, m.group(1))
            problems.extend(check_java_format(_android_text(source), _android_text(tgt[key]), key))
    return problems


# ----------------------------------------------------------------------- XLIFF

_XLIFF_ANNOTATIONS = {"mrk", "sm", "em"}


def _inline_codes(el):
    """Counter of the inline elements inside a <source> or <target>, by name
    and id (<x id="1"/>, <g id="2">, <ph>, <pc>, <bpt>, ...)."""
    found = Counter()
    for child in el.iter():
        if child is el:
            continue
        name = _local(child.tag)
        if name in _XLIFF_ANNOTATIONS:
            continue
        ident = child.get("id")
        found["<%s%s>" % (name, "" if ident is None else " id=%s" % ident)] += 1
    return found


def parse_xliff(text):
    """Reads XLIFF 1.2 (<trans-unit>) or 2.0 (<unit><segment>) into a list of
    dicts: id, source and target elements (target may be None)."""
    root = ET.fromstring(text)
    units = []
    for el in root.iter():
        name = _local(el.tag)
        if el.get("translate") == "no":
            continue
        ident = el.get("id") or "?"
        if name == "trans-unit":
            holders = [(ident, el)]
        elif name == "unit":
            segments = [s for s in el if _local(s.tag) == "segment"]
            if len(segments) == 1:
                holders = [(ident, segments[0])]
            else:
                holders = [("%s#%d" % (ident, i), s) for i, s in enumerate(segments, 1)]
        else:
            continue
        for uid, holder in holders:
            source = target = None
            for child in holder:
                part = _local(child.tag)
                if part == "source" and source is None:
                    source = child
                elif part == "target" and target is None:
                    target = child
            if source is not None:
                units.append({"id": uid, "source": source, "target": target})
    return units


def check_xliff(text):
    """Checks every translated unit of an XLIFF file. Returns (issues, stats)."""
    problems = []
    stats = {"units": 0, "translated": 0, "untranslated": 0}
    for unit in parse_xliff(text):
        stats["units"] += 1
        source, target = unit["source"], unit["target"]
        if target is None or (not "".join(target.itertext()).strip() and len(target) == 0):
            stats["untranslated"] += 1
            continue
        stats["translated"] += 1
        key = "unit %s" % unit["id"]
        problems.extend(check_pair("".join(source.itertext()), "".join(target.itertext()), key))
        missing, extra = _diff(_inline_codes(source), _inline_codes(target))
        if missing or extra:
            parts = []
            if missing:
                parts.append("missing " + " ".join(missing))
            if extra:
                parts.append("extra " + " ".join(extra))
            problems.append(issue(ERROR, "inline-codes",
                                  "inline elements differ: %s" % "; ".join(parts), key))
    return problems, stats


# ------------------------------------------------------------------ Apple

_BARE_WORD_RE = re.compile(r"[\w.$:/-]+")


def parse_strings(text):
    """Reads an Apple .strings file ("key" = "value"; with /* */ and //
    comments) into a dict. Escapes inside quotes are kept as written."""
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("unclosed /* comment")
            i = end + 2
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end + 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            if j >= n:
                raise ValueError("unclosed string at offset %d" % i)
            tokens.append(("s", text[i + 1:j]))
            i = j + 1
        elif c in "=;":
            tokens.append((c, c))
            i += 1
        else:
            m = _BARE_WORD_RE.match(text, i)
            if not m:
                raise ValueError("unexpected %r at offset %d" % (c, i))
            tokens.append(("s", m.group(0)))
            i = m.end()
    entries = {}
    k = 0
    while k < len(tokens):
        if [t[0] for t in tokens[k:k + 4]] != ["s", "=", "s", ";"]:
            raise ValueError('expected "key" = "value"; at entry %d' % (len(entries) + 1))
        entries[tokens[k][1]] = tokens[k + 2][1]
        k += 4
    return entries


def _xc_units(node, path=""):
    """Flattens one String Catalog localization to {variation path: stringUnit}.
    "" is a plain string; "plural.one", "device.iphone.plural.other" and
    "substitutions.n.plural.few" are variations."""
    out = {}
    if not isinstance(node, dict):
        return out
    unit = node.get("stringUnit")
    if isinstance(unit, dict) and isinstance(unit.get("value"), str):
        out[path] = unit
    variations = node.get("variations")
    if isinstance(variations, dict):
        for kind, branches in sorted(variations.items()):
            if isinstance(branches, dict):
                for name, sub in sorted(branches.items()):
                    out.update(_xc_units(sub, ".".join(p for p in (path, kind, name) if p)))
    substitutions = node.get("substitutions")
    if isinstance(substitutions, dict):
        for name, sub in sorted(substitutions.items()):
            out.update(_xc_units(sub, ".".join(p for p in (path, "substitutions", name) if p)))
    return out


def check_xcstrings(data):
    """Checks an Xcode String Catalog (.xcstrings, loaded from JSON): every
    language's values against the source language's. Returns (issues, stats)."""
    if not isinstance(data, dict) or not isinstance(data.get("strings"), dict):
        raise ValueError('not a String Catalog: no "strings" object')
    source_lang = data.get("sourceLanguage") or "en"
    strings = data["strings"]
    languages = set()
    for entry in strings.values():
        if isinstance(entry, dict) and isinstance(entry.get("localizations"), dict):
            languages.update(entry["localizations"])
    languages.discard(source_lang)
    problems = []
    stats = {"strings": 0, "checked": 0, "untranslated": 0}
    for key in sorted(strings):
        entry = strings[key] if isinstance(strings[key], dict) else {}
        if entry.get("shouldTranslate") is False:
            continue
        stats["strings"] += 1
        localizations = entry.get("localizations") or {}
        src = {path: unit["value"] for path, unit in
               _xc_units(localizations.get(source_lang)).items()}
        for lang in sorted(languages):
            units = _xc_units(localizations.get(lang))
            if not any(unit["value"].strip() for unit in units.values()):
                stats["untranslated"] += 1
                continue
            for path, unit in sorted(units.items()):
                if not unit["value"].strip():
                    continue
                other = re.sub(r"(zero|one|two|few|many)$", "other", path)
                source = src.get(path, src.get(other, src.get("", key)))
                label = "%s [%s%s]" % (key, lang, " " + path if path else "")
                problems.extend(_check_form(source, unit["value"], label, path.rsplit(".", 1)[-1]))
                stats["checked"] += 1
    return problems, stats


# ---------------------------------------------------------- Java and Flutter

_PROPS_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
_PROPS_SPACE = " \t\f"


def _props_unescape(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == "u" and re.match(r"[0-9A-Fa-f]{4}$", s[i + 2:i + 6]):
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_PROPS_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return _join_surrogates("".join(out))


def _continues(line):
    """A .properties line continues on the next one if it ends in an odd
    number of backslashes."""
    return (len(line) - len(line.rstrip("\\"))) % 2 == 1


def parse_properties(text):
    """Reads a Java .properties file (ResourceBundle, Spring messages) into
    {key: value}: # and ! comments, key=value, key: value or key value,
    backslash line continuations, \\uXXXX and the other escapes."""
    entries = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].lstrip(_PROPS_SPACE)
        i += 1
        if not line or line[0] in "#!":
            continue
        while _continues(line) and i < len(lines):
            line = line[:-1] + lines[i].lstrip(_PROPS_SPACE)
            i += 1
        if _continues(line):
            line = line[:-1]
        j = 0
        while j < len(line) and line[j] not in "=:" + _PROPS_SPACE:
            j += 2 if line[j] == "\\" else 1
        key = line[:j]
        rest = line[j:].lstrip(_PROPS_SPACE)
        if rest[:1] in ("=", ":"):
            rest = rest[1:].lstrip(_PROPS_SPACE)
        entries[_props_unescape(key)] = _props_unescape(rest)
    return entries


def _messageformat_quote(source, target):
    """True if the translation of a MessageFormat string ({0}, {name}) has a
    single apostrophe the source doesn't. MessageFormat reads ' as the start of
    quoted text, so "L'utilisateur {0}" prints "Lutilisateur {0}"; '' is the
    literal apostrophe."""
    if not _BRACE_ARG_RE.search(source) or "'" in source.replace("''", ""):
        return False
    return "'" in target.replace("''", "")


def check_properties(source_text, target_text):
    """Compares a translated bundle (messages_fr.properties) with its source
    (messages.properties)."""
    src, tgt = parse_properties(source_text), parse_properties(target_text)
    problems = check_catalog(src, tgt)
    for key in sorted(set(src) & set(tgt)):
        if _messageformat_quote(src[key], tgt[key]):
            problems.append(issue(ERROR, "messageformat-apostrophe",
                                  "a single ' starts quoted text in MessageFormat, so the "
                                  "arguments after it print literally; write ''", key))
    return problems


def arb_messages(data):
    """The messages of a Flutter .arb file: every key except @@locale-style
    globals and @key metadata."""
    if not isinstance(data, dict):
        raise ValueError("not an ARB file: the top level is not an object")
    return {k: v for k, v in data.items() if not k.startswith("@")}


def check_arb(source, target):
    """Compares a translated .arb (app_de.arb) with the template (app_en.arb),
    both loaded from JSON. ICU plural and select branches may differ between
    languages; arguments and markup may not."""
    problems = check_catalog(arb_messages(source), arb_messages(target))
    locale = target.get("@@locale")
    if locale and locale == source.get("@@locale"):
        problems.append(issue(WARNING, "locale", "@@locale is still %r" % locale))
    return problems


# --------------------------------------------------------------------- .NET resx

def parse_resx(text):
    """Reads a .NET .resx file (Resources.ja.resx) into {name: value}: the
    <data> entries that hold text. Typed entries (images, files: type= or
    mimetype=) and WinForms designer entries (>>button1.Name) are skipped."""
    out = {}
    for el in ET.fromstring(text):
        name = el.get("name")
        if (_local(el.tag) != "data" or not name or name.startswith(">>")
                or el.get("type") or el.get("mimetype")):
            continue
        value = next((child for child in el if _local(child.tag) == "value"), None)
        out[name] = "" if value is None else value.text or ""
    return out


def check_resx(source_text, target_text):
    """Compares a translated .resx (Resources.ja.resx) with the neutral one
    (Resources.resx). string.Format reads {0} only with ASCII braces, so a
    fullwidth ｛0｝ loses the value (lookalike-brace)."""
    return check_catalog(parse_resx(source_text), parse_resx(target_text))


# ------------------------------------------------------------- Laravel lang

# Laravel fills :name placeholders (and :Name, :NAME) by searching for the
# ASCII colon, in Translator::makeReplacements and the validator's
# replaceAttributePlaceholder. A ：name typed with the fullwidth colon, as
# Chinese and Japanese input methods do, is shown as written (0.9.0).
_LARAVEL_RE = re.compile(r"(?<![A-Za-z0-9_:]):([A-Za-z][A-Za-z0-9_]*)")
_LOOKALIKE_COLONS = {"：": "the fullwidth colon ： (U+FF1A)",
                     "﹕": "the small colon ﹕ (U+FE55)",
                     "︓": "the vertical colon ︓ (U+FE13)"}
_PHP_SKIP_RE = re.compile(r"(?:\s+|//[^\n]*|#(?!\[)[^\n]*|/\*.*?\*/)*", re.S)
_PHP_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "v": "\v", "f": "\f", "e": "\x1b",
                "\\": "\\", "$": "$", '"': '"'}
_PHP_NUMBER_RE = re.compile(r"-?\d+")
_PHP_ARRAY_RE = re.compile(r"array\s*\(", re.I)
_PHP_RETURN_RE = re.compile(r"return\b")


def _php_skip(text, i):
    return _PHP_SKIP_RE.match(text, i).end()


def _php_string(text, i):
    """The PHP string literal at text[i] (' or "), and the index after it.
    Variables in double quotes are kept as written."""
    quote, out, i = text[i], [], i + 1
    while i < len(text):
        c = text[i]
        if c == quote:
            return "".join(out), i + 1
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in (quote, "\\") or (quote == '"' and nxt in _PHP_ESCAPES):
                out.append(_PHP_ESCAPES[nxt] if quote == '"' else nxt)
                i += 2
                continue
        out.append(c)
        i += 1
    raise ValueError("unterminated PHP string")


def _php_skip_expr(text, i):
    """Skips an expression the reader doesn't evaluate (a function call, a
    constant) up to the , ] or ) that ends it."""
    depth = 0
    while i < len(text):
        c = text[i]
        if c in "'\"":
            i = _php_string(text, i)[1]
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            if depth == 0:
                return i
            depth -= 1
        elif c in ",;" and depth == 0:
            return i
        i += 1
    raise ValueError("unexpected end of the PHP file")


def _php_value(text, i):
    """The PHP value at text[i] and the index after it: a string (joined
    across . concatenation), a whole number (as a string), or an array (a
    dict). Anything else is None."""
    i = _php_skip(text, i)
    if text[i:i + 1] in ("'", '"'):
        parts = []
        while True:
            part, i = _php_string(text, i)
            parts.append(part)
            j = _php_skip(text, i)
            if text[j:j + 1] != ".":
                return "".join(parts), i
            j = _php_skip(text, j + 1)
            if text[j:j + 1] not in ("'", '"'):
                return None, _php_skip_expr(text, j)
            i = j
    if text.startswith("[", i):
        return _php_array(text, i + 1, "]")
    m = _PHP_ARRAY_RE.match(text, i)
    if m:
        return _php_array(text, m.end(), ")")
    m = _PHP_NUMBER_RE.match(text, i)
    if m and not re.match(r"[\w.]", text[m.end():m.end() + 1]):
        return m.group(0), m.end()
    return None, _php_skip_expr(text, i)


def _php_array(text, i, close):
    """The entries of a PHP array whose opening bracket ends at i, as
    {key: value}, and the index after the closing bracket."""
    out, auto = {}, 0
    while True:
        i = _php_skip(text, i)
        if i >= len(text):
            raise ValueError("unclosed PHP array")
        if text.startswith(close, i):
            return out, i + 1
        first, i = _php_value(text, i)
        i = _php_skip(text, i)
        if text.startswith("=>", i):
            key = first
            value, i = _php_value(text, i + 2)
            if isinstance(key, str) and _PHP_NUMBER_RE.fullmatch(key):
                auto = max(auto, int(key) + 1)
        else:
            key, value, auto = str(auto), first, auto + 1
        if isinstance(key, str):
            out[key] = value
        i = _php_skip(text, i)
        if text.startswith(",", i):
            i += 1
        elif not text.startswith(close, i):
            raise ValueError("unexpected %r in a PHP array" % text[i:i + 20])


def parse_laravel(text):
    """Reads a Laravel lang file (lang/ja/validation.php, `<?php return
    [...];`) into {dotted.key: value}. Values the reader doesn't evaluate
    (function calls, constants) are None."""
    i = _php_skip(text, 0)
    if text.startswith("<?php", i):
        i += 5
    while True:
        i = _php_skip(text, i)
        if _PHP_RETURN_RE.match(text, i):
            value = _php_value(text, i + 6)[0]
            if not isinstance(value, dict):
                raise ValueError("the PHP file does not return an array")
            return flatten(value)
        end = text.find(";", i)
        if end < 0:
            raise ValueError("no return statement in the PHP file"
                             + (" (it is only \"<?php\")" if text.strip() == "<?php" else ""))
        i = end + 1


def _laravel_names(text):
    """The names of the :name placeholders in a Laravel string, lower-cased."""
    return {name.lower() for name in _LARAVEL_RE.findall(text)}


def _lookalike_colon(name, target):
    """How target writes :name with a look-alike colon ("：attribute"), or None."""
    m = re.search("[%s] ?%s(?![A-Za-z0-9_])" % ("".join(_LOOKALIKE_COLONS), re.escape(name)),
                  target, re.I)
    return m.group(0) if m else None


def _laravel_pair(source, target, key):
    """check_pair for one Laravel string, by its :name placeholders. Brace and
    printf placeholders are not compared: Laravel doesn't fill them, and its
    plural ranges ({0}, [2,*]) may differ between languages."""
    problems = [p for p in check_pair(source, target, key)
                if p["code"] in ("empty", "tags", "untranslated", "reading-leak")]
    if not target.strip():
        return problems
    names, missing = _laravel_names(source), []
    spelled = {}
    for written in _LARAVEL_RE.findall(source):
        spelled.setdefault(written.lower(), written)
    for name in sorted(names):
        seen = _lookalike_colon(name, target)
        if re.search(":%s(?![A-Za-z0-9_])" % re.escape(name), target, re.I):
            if seen:
                problems.append(issue(WARNING, "lookalike-colon",
                                      "\"%s\" is written with %s, which Laravel doesn't replace, "
                                      "so it is shown as written; the value itself appears at the "
                                      "ASCII :%s" % (seen, _LOOKALIKE_COLONS[seen[0]], spelled[name]), key))
        elif seen:
            problems.append(issue(ERROR, "lookalike-colon",
                                  ":%s is written \"%s\" with %s, which Laravel doesn't replace: "
                                  "the text is shown as written and the value is lost"
                                  % (spelled[name], seen, _LOOKALIKE_COLONS[seen[0]]), key))
        else:
            missing.append(":" + spelled[name])
    if missing:
        problems.append(issue(ERROR, "placeholder-missing",
                              "placeholder(s) missing: %s" % ", ".join(missing), key))
    extra = sorted(_laravel_names(target) - names)
    if extra:
        problems.append(issue(WARNING, "placeholder-extra",
                              "placeholder(s) not in source, shown as written unless the app "
                              "passes them: %s" % ", ".join(":" + name for name in extra), key))
    return problems


def check_laravel(source_text, target_text):
    """Compares a translated Laravel lang file (lang/ja/validation.php) with
    the source one (lang/en/validation.php)."""
    src, tgt = parse_laravel(source_text), parse_laravel(target_text)
    problems = []
    for key in sorted(src):
        if key not in tgt:
            if isinstance(src[key], str) and src[key].strip():
                problems.append(issue(WARNING, "missing-key", "key missing from translation", key))
        elif isinstance(src[key], str) and isinstance(tgt[key], str):
            problems.extend(_laravel_pair(src[key], tgt[key], key))
    for key in sorted(set(tgt) - set(src)):
        problems.append(issue(WARNING, "extra-key", "key not in source", key))
    return problems



# ------------------------------------------------------------------------ YAML

# A reader for YAML as translation files write it (Rails config/locales,
# Symfony translations), so that no PyYAML is needed (0.10.0): nested
# mappings and lists, plain, quoted and block (| >) scalars, comments, and
# {} or one-line [a, b] flow values. Anchors, aliases and tags are refused.
_YAML_KEY_RE = re.compile(r"([^\s#'\"\[\]{}&*!|>%@`?-].*?|-\S.*?)[ \t]*:(?:[ \t]+|$)")
_YAML_COLON_RE = re.compile(r"[ \t]*:(?:[ \t]+|$)")
_YAML_BLOCK_RE = re.compile(r"([|>])([1-9]?)([+-]?)([1-9]?)[ \t]*(?:#.*)?$")
_YAML_DOC_RE = re.compile(r"---(?:[ \t]+#.*)?[ \t]*$")
_YAML_ESCAPES = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
                 "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
                 "N": "\x85", "_": "\xa0", "L": " ", "P": " "}
_YAML_HEX = {"x": 2, "u": 4, "U": 8}
_YAML_NULLS = ("", "~", "null", "Null", "NULL")


def _yaml_indent(line):
    return len(line) - len(line.lstrip(" "))


def _yaml_blank(line):
    text = line.strip()
    return not text or text.startswith("#")


def _yaml_dash(text):
    return text == "-" or text.startswith(("- ", "-\t"))


def _yaml_uncomment(text):
    """A plain scalar without its trailing comment ("value # note")."""
    return re.split(r"[ \t]+#", text, maxsplit=1)[0].strip()


def _yaml_scalar(text):
    """A plain scalar's value: null and ~ are None, everything else is text."""
    return None if text in _YAML_NULLS else text


def _yaml_quoted(lines, li, start):
    """The quoted scalar at lines[li][start] (' or "), folded over as many
    lines as it takes, and the line index and column just after it."""
    line, quote = lines[li], lines[li][start]
    out, i = [], start + 1
    while True:
        while i < len(line):
            c = line[i]
            if c == quote and quote == "'" and line.startswith("''", i):
                out.append("'")
                i += 2
            elif c == quote:
                return "".join(out), li, i + 1
            elif quote == '"' and c == "\\" and i + 1 < len(line):
                nxt = line[i + 1]
                if nxt in _YAML_HEX:
                    digits = line[i + 2:i + 2 + _YAML_HEX[nxt]]
                    if not re.fullmatch(r"[0-9A-Fa-f]{%d}" % _YAML_HEX[nxt], digits):
                        raise ValueError("line %d: bad \\%s escape" % (li + 1, nxt))
                    out.append(chr(int(digits, 16)))
                    i += 2 + len(digits)
                elif nxt in _YAML_ESCAPES:
                    out.append(_YAML_ESCAPES[nxt])
                    i += 2
                else:
                    raise ValueError("line %d: unknown escape \\%s" % (li + 1, nxt))
            elif quote == '"' and c == "\\":
                break
            else:
                out.append(c)
                i += 1
        joined = i < len(line)   # the line ended with an escaped line break
        if not joined:
            while out and out[-1] in " \t":
                out.pop()
        li, breaks = li + 1, 0
        while li < len(lines) and not lines[li].strip():
            li, breaks = li + 1, breaks + 1
        if li >= len(lines):
            raise ValueError("unterminated quoted value")
        out.append("\n" * breaks if breaks or joined else " ")
        line = lines[li]
        i = len(line) - len(line.lstrip(" \t"))


def _yaml_fold(lines):
    """Folds the lines of a > block: a line break between two lines of text
    becomes a space; blank lines and more-indented lines keep their breaks."""
    out, breaks, started, before = [], 0, False, False
    for line in lines:
        if not line:
            breaks += 1
            continue
        more = line[0] in " \t"
        if not started:
            out.append("\n" * breaks)
        elif more or before:
            out.append("\n" * (breaks + 1))
        else:
            out.append("\n" * breaks if breaks else " ")
        out.append(line)
        started, breaks, before = True, 0, more
    return "".join(out)


def _yaml_flow(text, li):
    """An empty {} or [], or a one-line list of scalars ([a, 'b c'])."""
    if re.fullmatch(r"\{\s*\}", text):
        return {}
    m = re.fullmatch(r"\[(.*)\]", text)
    if not m:
        raise ValueError("line %d: YAML flow mappings are not read" % (li + 1))
    body, items, k = m.group(1), [], 0
    while True:
        while k < len(body) and body[k] in " \t":
            k += 1
        if k >= len(body):
            return items
        if body[k] in "'\"":
            item, _, k = _yaml_quoted([body], 0, k)
        else:
            end = body.find(",", k)
            end = len(body) if end < 0 else end
            item = _yaml_scalar(body[k:end].strip())
            if item is not None and re.search(r"[\[\]{}]|:\s", item):
                raise ValueError("line %d: nested YAML flow collections are not read" % (li + 1))
            k = end
        items.append(item)
        while k < len(body) and body[k] in " \t":
            k += 1
        if k < len(body):
            if body[k] != ",":
                raise ValueError("line %d: unreadable YAML flow list" % (li + 1))
            k += 1


class _YamlReader:
    """Reads block YAML line by line; pos is the next line not yet read."""

    def __init__(self, text):
        self.lines = []
        for line in text.split("\n"):
            if line.rstrip() == "...":
                break
            if line.startswith("%") or _YAML_DOC_RE.match(line):
                line = ""
            self.lines.append(line)
        self.pos = 0

    def significant(self):
        """The index of the next line that isn't blank or a comment."""
        i = self.pos
        while i < len(self.lines) and _yaml_blank(self.lines[i]):
            i += 1
        if i < len(self.lines) and self.lines[i][_yaml_indent(self.lines[i])] == "\t":
            raise ValueError("line %d: a tab in the indentation" % (i + 1))
        return i

    def key(self, text):
        """(key, length of "key: ") when text starts a mapping entry, else None."""
        if text[:1] in ("'", '"'):
            try:
                key, _, end = _yaml_quoted([text], 0, 0)
            except ValueError:
                return None
            m = _YAML_COLON_RE.match(text, end)
            return (key, m.end()) if m else None
        m = _YAML_KEY_RE.match(text)
        return (m.group(1), m.end()) if m else None

    def node(self, indent):
        """The node on the next line, if it is indented at least indent."""
        i = self.pos = self.significant()
        if i >= len(self.lines):
            return None
        col = _yaml_indent(self.lines[i])
        if col < indent:
            return None
        text = self.lines[i][col:]
        if _yaml_dash(text):
            return self.sequence(col)
        if self.key(text) is not None:
            return self.mapping(col)
        return self.value(i, col, indent - 1, False)

    def mapping(self, col):
        out = {}
        while True:
            i = self.pos = self.significant()
            if i >= len(self.lines) or _yaml_indent(self.lines[i]) < col:
                return out
            line = self.lines[i]
            if _yaml_indent(line) > col:
                raise ValueError("line %d: unexpected indentation" % (i + 1))
            found = self.key(line[col:])
            if found is None:
                raise ValueError("line %d: expected a key: %s" % (i + 1, line.strip()[:40]))
            out[found[0]] = self.value(i, col + found[1], col, True)

    def sequence(self, col):
        out = []
        while True:
            i = self.pos = self.significant()
            if i >= len(self.lines) or _yaml_indent(self.lines[i]) < col:
                return out
            line = self.lines[i]
            if _yaml_indent(line) > col:
                raise ValueError("line %d: unexpected indentation" % (i + 1))
            text = line[col:]
            if not _yaml_dash(text):
                return out
            start = col + len(text) - len(text[1:].lstrip(" \t"))
            rest = line[start:]
            if rest and (_yaml_dash(rest) or self.key(rest) is not None):
                # "- key: value" or "- - item": a node that starts at this column
                self.lines[i] = " " * start + rest
                out.append(self.node(start))
            else:
                out.append(self.value(i, start, col, False))

    def value(self, i, start, parent, in_map):
        """The value at column start of line i, after "key: " or "- ";
        parent is the column of its key or dash. A value on the lines below
        is indented more, except a list under a key."""
        text = self.lines[i][start:].rstrip()
        if not text or text.startswith("#"):
            self.pos = i + 1
            j = self.significant()
            if j < len(self.lines):
                col = _yaml_indent(self.lines[j])
                if col > parent or (in_map and col == parent and _yaml_dash(self.lines[j][col:])):
                    return self.node(col)
            return None
        if text[0] in "&*!":
            raise ValueError("line %d: YAML anchors, aliases and tags are not read" % (i + 1))
        if text[0] in "|>":
            return self.block(i, text, parent)
        if text[0] in "'\"":
            value, j, end = _yaml_quoted(self.lines, i, start)
            rest = self.lines[j][end:].strip()
            if rest and not rest.startswith("#"):
                raise ValueError("line %d: text after a quoted value: %s" % (j + 1, rest[:40]))
            self.pos = j + 1
            return value
        if text[0] in "[{":
            self.pos = i + 1
            return _yaml_flow(_yaml_uncomment(text), i)
        return self.plain(i, start, parent)

    def plain(self, i, start, parent):
        """A plain scalar, folded over the more-indented lines after it."""
        parts, j, breaks = [_yaml_uncomment(self.lines[i][start:])], i + 1, 0
        while j < len(self.lines):
            line = self.lines[j]
            if not line.strip():
                j, breaks = j + 1, breaks + 1
                continue
            if _yaml_indent(line) <= parent or line.strip().startswith("#"):
                break
            parts.append("\n" * breaks if breaks else " ")
            parts.append(_yaml_uncomment(line))
            j, breaks = j + 1, 0
        self.pos = j
        return _yaml_scalar("".join(parts))

    def block(self, i, header, parent):
        """A literal (|) or folded (>) block scalar."""
        m = _YAML_BLOCK_RE.match(header)
        if not m:
            raise ValueError("line %d: unreadable block scalar header %s" % (i + 1, header[:20]))
        j, body = i + 1, []
        while j < len(self.lines) and (not self.lines[j].strip()
                                       or _yaml_indent(self.lines[j]) > parent):
            body.append(self.lines[j])
            j += 1
        self.pos = j
        width = m.group(2) or m.group(4)
        filled = [line for line in body if line.strip()]
        width = parent + int(width) if width else (_yaml_indent(filled[0]) if filled else 0)
        lines = [line[width:] if line.strip() else "" for line in body]
        trailing = 0
        while lines and not lines[-1]:
            lines.pop()
            trailing += 1
        if not lines:
            return ""
        text = "\n".join(lines) if m.group(1) == "|" else _yaml_fold(lines)
        if m.group(3) == "-":
            return text
        return text + "\n" * (1 + trailing if m.group(3) == "+" else 1)


def parse_yaml(text):
    """Reads YAML as translation files write it into dicts, lists and
    strings (null and ~ are None; numbers and booleans stay text)."""
    reader = _YamlReader(text)
    value = reader.node(0)
    i = reader.significant()
    if i < len(reader.lines):
        raise ValueError("line %d: unexpected text: %s" % (i + 1, reader.lines[i].strip()[:40]))
    return {} if value is None else value


# ------------------------------------------------------------------ Rails YAML

# Ruby's I18n fills %{name} and %<name>s and nothing else
# (DEFAULT_INTERPOLATION_PATTERNS; %% is a literal %). A ％{name} or
# ٪ {name} typed with a look-alike percent sign, or %｛name｝ with fullwidth
# braces, is shown as written and the value is lost (0.10.0).
_RAILS_RE = re.compile(r"%\{([\w|]+)\}|%<(\w+)>[^\d<>]*?\d*\.?\d*[bBdiouxXeEfgGcps]")
_RAILS_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")
_RAILS_PLURAL_RE = re.compile(r"\.(zero|one|two|few|many|other)$")


def _rails_names(text):
    """The names of the %{name} and %<name>s placeholders in a Rails string."""
    return {a or b for a, b in _RAILS_RE.findall(text.replace("%%", ""))}


def _lookalike_rails(name, target):
    """(how target writes %{name} with a look-alike, what it is, code) for
    "％{count}", "٪ {name}", "%｛name｝" or "％<count>d", or None."""
    marks = "%" + "".join(_LOOKALIKE_PERCENTS)
    word = re.escape(name)
    for m in re.finditer("[%s] ?(?:[{｛] ?%s ?[}｝]|<%s>)" % (marks, word, word), target):
        seen = m.group(0)
        if seen[0] in _LOOKALIKE_PERCENTS:
            return seen, _LOOKALIKE_PERCENTS[seen[0]], "lookalike-percent"
        brace = next((c for c in seen if c in _LOOKALIKE_BRACES), None)
        if brace:
            return seen, _LOOKALIKE_BRACES[brace], "lookalike-brace"
    return None


def _rails_pair(source, target, key, quantity=None):
    """check_pair for one Rails string, by its %{name} placeholders. In a
    plural form for zero, one or two a missing placeholder is a warning, and
    any form may add %{count}, which I18n always passes."""
    problems = [p for p in check_pair(source, target, key)
                if p["code"] in ("empty", "tags", "untranslated", "reading-leak")]
    if not target.strip():
        return problems
    names, found, missing = _rails_names(source), _rails_names(target), []
    for name in sorted(names):
        seen = _lookalike_rails(name, target)
        if name in found:
            if seen:
                problems.append(issue(WARNING, seen[2],
                                      "\"%s\" is written with %s, which Ruby's I18n doesn't read, "
                                      "so it is shown as written; the value itself appears at the "
                                      "ASCII %%{%s}" % (seen[0], seen[1], name), key))
        elif seen:
            problems.append(issue(ERROR, seen[2],
                                  "%%{%s} is written \"%s\" with %s, which Ruby's I18n doesn't "
                                  "read: the text is shown as written and the value is lost"
                                  % (name, seen[0], seen[1]), key))
        else:
            missing.append("%%{%s}" % name)
    if missing:
        problems.append(issue(WARNING if quantity in ("zero", "one", "two") else ERROR,
                              "placeholder-missing",
                              "placeholder(s) missing: %s" % ", ".join(missing), key))
    extra = sorted(found - names - ({"count"} if quantity else set()))
    if extra:
        problems.append(issue(WARNING, "placeholder-extra",
                              "placeholder(s) not in source; Ruby's I18n raises "
                              "MissingInterpolationArgument unless the app passes them: %s"
                              % ", ".join("%%{%s}" % name for name in extra), key))
    return problems


def _rails_root(data):
    """A Rails locale file's messages, under its locale key (en:, ja:)."""
    if not isinstance(data, dict):
        raise ValueError("the YAML file is not a mapping")
    if len(data) == 1:
        root, inner = next(iter(data.items()))
        if isinstance(inner, dict) and _RAILS_LOCALE_RE.match(str(root)):
            return inner
    return data


def check_rails(source_text, target_text):
    """Compares a translated Rails locale file (config/locales/ja.yml) with
    the source one (config/locales/en.yml). Plural keys (one, few, other)
    are checked per language: a missing one is fine when the translation
    has other forms, and a few or many the source lacks is checked against
    its other."""
    src = flatten(_rails_root(parse_yaml(source_text)))
    tgt = flatten(_rails_root(parse_yaml(target_text)))
    plural_bases = {_RAILS_PLURAL_RE.sub("", k) for k in tgt if _RAILS_PLURAL_RE.search(k)}
    problems = []
    for key in sorted(src):
        form = _RAILS_PLURAL_RE.search(key)
        if key in tgt:
            if isinstance(src[key], str) and isinstance(tgt[key], str):
                problems.extend(_rails_pair(src[key], tgt[key], key, form and form.group(1)))
        elif isinstance(src[key], str) and src[key].strip() and not (
                form and _RAILS_PLURAL_RE.sub("", key) in plural_bases):
            problems.append(issue(WARNING, "missing-key", "key missing from translation", key))
    for key in sorted(set(tgt) - set(src)):
        form = _RAILS_PLURAL_RE.search(key)
        other = src.get(_RAILS_PLURAL_RE.sub("", key) + ".other") if form else None
        if isinstance(other, str):
            if isinstance(tgt[key], str):
                problems.extend(_rails_pair(other, tgt[key], key, form.group(1)))
        else:
            problems.append(issue(WARNING, "extra-key", "key not in source", key))
    return problems


# --------------------------------------------------------------------- Symfony

# Symfony's translator fills parameters with strtr($message, $parameters),
# so a '%name%' the caller passes must appear exactly: ％name％ or ٪ name٪ is
# shown as written and the value is lost (0.10.0). Messages are paired by
# key, as the translator pairs them; Sonata's XLIFF files have the key, not
# the English, as <source>, so source and target in one file can't show it.
_SYMFONY_PARAM_RE = re.compile(r"(?<!%)%([A-Za-z_][\w.-]*)%(?!%)")
_SYMFONY_INTERVAL_RE = re.compile(
    r"^\s*(?:\{\s*-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*\s*\}"
    r"|[\[\]]\s*(?:-Inf|-?\d+(?:\.\d+)?)\s*,\s*(?:\+?Inf|-?\d+(?:\.\d+)?)\s*[\[\]])\s*")


def parse_symfony(text, name):
    """Reads a Symfony translation file (messages.ja.yaml, .xlf, .xliff) into
    {key: message}, the way the translator loads it: YAML keys are joined
    with dots; an XLIFF unit's key is its resname (1.2) or name (2.0), else
    its <source>, and its message is the <target>, else the <source>."""
    lower = name.lower()
    if lower.endswith((".yml", ".yaml")):
        data = parse_yaml(text)
        if not isinstance(data, dict):
            raise ValueError("the YAML file is not a mapping")
        return flatten(data)
    if not lower.endswith((".xlf", ".xliff", ".xml")):
        raise ValueError("a Symfony translation file is .yaml, .yml, .xlf or .xliff: %s" % name)
    messages = {}
    for el in ET.fromstring(text).iter():
        part = _local(el.tag)
        if part == "trans-unit":
            holders = [(el.get("resname"), el)]
        elif part == "unit":
            holders = [(el.get("name"), s) for s in el if _local(s.tag) == "segment"]
        else:
            continue
        for key, holder in holders:
            source = next((c for c in holder if _local(c.tag) == "source"), None)
            target = next((c for c in holder if _local(c.tag) == "target"), None)
            if source is None:
                continue
            words = "".join(source.itertext())
            messages[key or words] = words if target is None else "".join(target.itertext())
    return messages


def _symfony_forms(text):
    """A message's plural forms (one|many), without their intervals ({0},
    [2,Inf[), which may differ between languages."""
    if "|" not in text:
        return [text]
    return [_SYMFONY_INTERVAL_RE.sub("", form) for form in text.split("|")]


def _lookalike_symfony(name, target):
    """How target writes %name% with a look-alike percent sign ("％name％",
    "٪ name٪", "%name％"), and what that sign is, or None."""
    marks = "%" + "".join(_LOOKALIKE_PERCENTS)
    for m in re.finditer("([%s]) ?%s ?([%s])" % (marks, re.escape(name), marks), target):
        odd = [c for c in m.groups() if c in _LOOKALIKE_PERCENTS]
        if odd:
            return m.group(0), _LOOKALIKE_PERCENTS[odd[0]]
    return None


def _symfony_form(source, target, key, last):
    """check_pair for one form of a Symfony message, with its %name%
    parameters. Outside the last form a missing parameter is a warning,
    since "one file" often spells the number out."""
    names = set(_SYMFONY_PARAM_RE.findall(source))
    found = set(_SYMFONY_PARAM_RE.findall(target))
    problems = check_pair(_SYMFONY_PARAM_RE.sub(r"\1", source),
                          _SYMFONY_PARAM_RE.sub(r"\1", target), key)
    missing = []
    for name in sorted(names):
        seen = _lookalike_symfony(name, target)
        if name in found:
            if seen:
                problems.append(issue(WARNING, "lookalike-percent",
                                      "\"%s\" is written with %s, which Symfony doesn't replace, "
                                      "so it is shown as written; the value itself appears at the "
                                      "ASCII %%%s%%" % (seen[0], seen[1], name), key))
        elif seen:
            problems.append(issue(ERROR, "lookalike-percent",
                                  "%%%s%% is written \"%s\" with %s, which Symfony doesn't "
                                  "replace: the text is shown as written and the value is lost"
                                  % (name, seen[0], seen[1]), key))
        else:
            missing.append("%" + name + "%")
    if missing:
        problems.append(issue(ERROR, "placeholder-missing",
                              "placeholder(s) missing: %s" % ", ".join(missing), key))
    extra = sorted(found - names)
    if extra:
        problems.append(issue(WARNING, "placeholder-extra",
                              "placeholder(s) not in source, shown as written unless the app "
                              "passes them: %s" % ", ".join("%" + name + "%" for name in extra),
                              key))
    if not last:
        for p in problems:
            if p["code"] == "placeholder-missing":
                p["level"] = WARNING
    return problems


def _symfony_pair(source, target, key):
    """check_pair for one Symfony message. In a plural message (one|many)
    each form of the translation is checked against the source's last form."""
    if not target.strip():
        return check_pair(source, target, key)
    other, forms = _symfony_forms(source)[-1], _symfony_forms(target)
    problems = []
    for n, form in enumerate(forms):
        problems.extend(_symfony_form(other, form, key, n == len(forms) - 1))
    return problems


def check_symfony(source_text, target_text, source_name=".yaml", target_name=".yaml"):
    """Compares a translated Symfony file (translations/messages.ja.yaml or
    .xlf) with the source language's file, message by message, by key. The
    names (paths) give each file's format."""
    src = parse_symfony(source_text, source_name)
    tgt = parse_symfony(target_text, target_name)
    problems = []
    for key in sorted(src):
        if key not in tgt:
            if isinstance(src[key], str) and src[key].strip():
                problems.append(issue(WARNING, "missing-key", "key missing from translation", key))
        elif isinstance(src[key], str) and isinstance(tgt[key], str):
            problems.extend(_symfony_pair(src[key], tgt[key], key))
    for key in sorted(set(tgt) - set(src)):
        problems.append(issue(WARNING, "extra-key", "key not in source", key))
    return problems


# ----------------------------------------------------------------- HTML / docs

class _DocScan(HTMLParser):
    """Collects the parts of a page a translation must not change."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.pre = []
        self.code = []
        self.links = []
        self.alternates = []
        self.text = []
        self._pre_depth = 0
        self._code_depth = 0
        self._skip_depth = 0
        self._buf_pre = []
        self._buf_code = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html" and attrs.get("lang"):
            self.lang = attrs["lang"]
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag == "pre":
            if self._pre_depth == 0:
                self._buf_pre = []
            self._pre_depth += 1
        elif tag == "code" and self._pre_depth == 0:
            if self._code_depth == 0:
                self._buf_code = []
            self._code_depth += 1
        elif tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"].strip())
        elif tag == "link" and attrs.get("hreflang") and \
                "alternate" in (attrs.get("rel") or "").lower().split():
            self.alternates.append((attrs["hreflang"].strip().lower(),
                                    (attrs.get("href") or "").strip()))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "pre" and self._pre_depth:
            self._pre_depth -= 1
            if self._pre_depth == 0:
                self.pre.append("".join(self._buf_pre))
        elif tag == "code" and self._code_depth and self._pre_depth == 0:
            self._code_depth -= 1
            if self._code_depth == 0:
                self.code.append("".join(self._buf_code))

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._pre_depth:
            self._buf_pre.append(data)
        elif self._code_depth:
            self._buf_code.append(data)
        else:
            self.text.append(data)


def _scan_html(text):
    scan = _DocScan()
    scan.feed(text)
    scan.close()
    return scan


_FENCE_RE = re.compile(r"^(```|~~~)[^\n]*\n(.*?)^\1[ \t]*$", re.M | re.S)
_INLINE_MD_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_MD_LINK_RE = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def _scan_md(text):
    class Scan:
        pass
    scan = Scan()
    scan.lang = None
    scan.alternates = []
    scan.pre = [m.group(2) for m in _FENCE_RE.finditer(text)]
    rest = _FENCE_RE.sub("\n", text)
    scan.code = _INLINE_MD_RE.findall(rest)
    scan.links = _MD_LINK_RE.findall(rest) + re.findall(r"<(https?://[^>\s]+)>", rest)
    scan.text = [_INLINE_MD_RE.sub(" ", rest)]
    return scan


_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")


def _is_absolute(href):
    return bool(re.match(r"(?i)^(https?:|mailto:|tel:)", href))


def _lang_key(tag):
    return tag.strip().replace("_", "-").lower()


def check_document(source_text, target_text, kind="html", lang=None):
    """Compares a translated HTML or Markdown document with its source.

    lang, if given, is the language the translation should declare in
    <html lang> (case and _/- ignored, so pt-br and pt_BR match pt-BR).
    """
    scan = _scan_html if kind == "html" else _scan_md
    src, tgt = scan(source_text), scan(target_text)
    problems = []
    if kind == "html":
        if not tgt.lang:
            problems.append(issue(WARNING, "lang", "translated page has no <html lang>"))
        elif src.lang and tgt.lang.lower() == src.lang.lower():
            problems.append(issue(WARNING, "lang", "<html lang> is still %r" % tgt.lang))
        elif lang and _lang_key(tgt.lang) != _lang_key(lang):
            problems.append(issue(WARNING, "lang", "<html lang> is %r, expected %r"
                                  % (tgt.lang, lang)))
    if len(src.pre) != len(tgt.pre):
        problems.append(issue(ERROR, "code-block-count", "%d code blocks in source, %d in translation"
                              % (len(src.pre), len(tgt.pre))))
    for i, (a, b) in enumerate(zip(src.pre, tgt.pre), 1):
        if a != b:
            problems.append(issue(ERROR, "code-block-changed",
                                  "code block %d differs from source (first difference near %r)"
                                  % (i, _first_diff(a, b)), "block %d" % i))
    missing, extra = _diff(Counter(src.code), Counter(tgt.code))
    if missing:
        problems.append(issue(ERROR, "inline-code-missing",
                              "inline code missing or changed: %s" % ", ".join(repr(x) for x in missing)))
    if extra:
        problems.append(issue(WARNING, "inline-code-extra",
                              "inline code not in source: %s" % ", ".join(repr(x) for x in extra)))
    src_abs = {h for h in src.links if _is_absolute(h)}
    tgt_abs = {h for h in tgt.links if _is_absolute(h)}
    for href in sorted(src_abs - tgt_abs):
        problems.append(issue(ERROR, "link-missing", "external link missing or changed: %s" % href))
    for href in sorted(tgt_abs - src_abs):
        problems.append(issue(WARNING, "link-extra", "external link not in source: %s" % href))
    # Every page in a language cluster should list the same hreflang alternates,
    # or search engines ignore the cluster.
    if src.alternates or tgt.alternates:
        missing = sorted(set(src.alternates) - set(tgt.alternates))
        extra = sorted(set(tgt.alternates) - set(src.alternates))
        if missing or extra:
            parts = ["missing %s %s" % a for a in missing] + ["extra %s %s" % a for a in extra]
            problems.append(issue(WARNING, "hreflang", "hreflang alternates differ from source: %s"
                                  % "; ".join(parts)))
    src_nums = set(_NUMBER_RE.findall(" ".join(src.text)))
    tgt_nums = set(_NUMBER_RE.findall(" ".join(tgt.text)))
    tgt_digits = {re.sub(r"[.,]", "", n) for n in tgt_nums}
    lost = sorted(n for n in src_nums - tgt_nums if re.sub(r"[.,]", "", n) not in tgt_digits)
    if lost:
        problems.append(issue(WARNING, "numbers", "numbers in source prose not found in translation: %s"
                              % ", ".join(lost)))
    problems.extend(_reading_leak(source_text, target_text))
    return problems


def _first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return b[max(0, i - 10):i + 20]
    return b[min(len(a), len(b)):][:30] or a[min(len(a), len(b)):][:30]


# ----------------------------------------------------------- locale folders

_DOC_KINDS = {".html": "html", ".htm": "html", ".md": "md", ".markdown": "md", ".json": "json",
              ".strings": "strings"}
# "de", "ja", "pt-br", "zh_Hans": folder names that are language tags.
_LANG_DIR_RE = re.compile(r"^[A-Za-z]{2}(?:[-_][A-Za-z0-9]{2,8})?$")


def check_dir(source_dir, target_dir):
    """Checks every HTML, Markdown, JSON and .strings file under target_dir
    against the file with the same relative path under source_dir (for a site:
    "site" and "site/de"; for Apple: "en.lproj" and "de.lproj"). Returns
    (issues, stats). Each issue's key starts with the file's relative path.
    """
    if not os.path.isdir(source_dir) or not os.path.isdir(target_dir):
        raise ValueError("not a directory: %s" % (target_dir if os.path.isdir(source_dir)
                                                  else source_dir))
    base = os.path.basename(os.path.normpath(target_dir))
    lang = base if _LANG_DIR_RE.match(base) else None
    problems = []
    stats = {"checked": 0, "unmatched": 0}
    for root, dirs, files in os.walk(target_dir):
        dirs.sort()
        for name in sorted(files):
            kind = _DOC_KINDS.get(os.path.splitext(name)[1].lower())
            if kind is None:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, target_dir).replace(os.sep, "/")
            source = os.path.join(source_dir, *rel.split("/"))
            if not os.path.isfile(source):
                stats["unmatched"] += 1
                problems.append(issue(WARNING, "no-source", "no source file at %s" % source, rel))
                continue
            if kind == "json":
                found = check_catalog(json.loads(_read(source)), json.loads(_read(path)))
            elif kind == "strings":
                found = check_catalog(parse_strings(_read(source)), parse_strings(_read(path)))
            else:
                found = check_document(_read(source), _read(path), kind, lang)
            for p in found:
                p["key"] = "%s %s" % (rel, p["key"]) if "key" in p else rel
                problems.append(p)
            stats["checked"] += 1
    return problems, stats


# ----------------------------------------------------------------- Qt Linguist

# A QString::arg() place marker: % then an optional L then one or two ASCII
# digits (qtbase qstring.cpp). Each arg() call fills the lowest-numbered
# marker left, so the i-th argument lands in the i-th smallest marker of the
# translation, whatever number the translator gave it. Digits such as ١ or ১
# stopped counting as markers in Qt 6.6.
_QT_ARG_RE = re.compile(r"%L?([0-9]{1,2})")
# The count of a plural (numerus) message. QCoreApplication::translate
# replaces only an ASCII % followed by n or Ln (replacePercentN).
_QT_COUNT_RE = re.compile(r"%L?n")
_QT_PERCENTS = "٪％﹪"   # Arabic ٪, fullwidth ％, small ﹪
_QT_FAKE_COUNT_RE = re.compile("(?:[%s]\\s*L?|%%\\s+L?)n(?![A-Za-z])" % _QT_PERCENTS)


def parse_qt_ts(text):
    """Reads a Qt Linguist .ts file into a list of dicts: context, source,
    numerus, forms (the translation's text, one per plural form) and state
    (finished, unfinished, untranslated or obsolete)."""
    root = ET.fromstring(text)
    if root.tag != "TS":
        raise ValueError("not a Qt .ts file (root element <%s>)" % root.tag)
    messages = []
    for ctx in root.iter("context"):
        name = ctx.findtext("name") or ""
        for msg in ctx.iter("message"):
            source, trans = msg.find("source"), msg.find("translation")
            if source is None:
                continue
            numerus = msg.get("numerus") == "yes"
            if trans is None:
                holders = []
            elif numerus:
                holders = trans.findall("numerusform")
            else:
                holders = [trans]
            forms = []
            for holder in holders:
                variants = holder.findall("lengthvariant")
                forms.extend("".join(v.itertext()) for v in variants or [holder])
            kind = trans.get("type", "") if trans is not None else ""
            if kind in ("obsolete", "vanished"):
                state = "obsolete"
            elif not any(f.strip() for f in forms):
                state = "untranslated"
            elif kind == "unfinished":
                state = "unfinished"
            else:
                state = "finished"
            messages.append({"context": name, "source": "".join(source.itertext()),
                             "numerus": numerus, "forms": forms, "state": state})
    return messages


def _qt_markers(text):
    """Sorted distinct place-marker numbers QString::arg() sees in text."""
    return sorted({int(n) for n in _QT_ARG_RE.findall(text)})


def _qt_hints(source, target):
    """What the translator may have written for each source marker the
    translation lacks."""
    tgt = _qt_markers(target)
    out = []
    for n in _qt_markers(source):
        if n in tgt:
            continue
        d = str(n)
        for pattern, what in ((r"[%s]\s*L?%s(?![0-9])" % (_QT_PERCENTS, d), "a percent sign Qt does not read"),
                              (r"%%\s+L?%s(?![0-9])" % d, "a space after the %"),
                              (r"(?<![0-9%%])%s%%" % d, "the % after the number")):
            m = re.search(pattern, target)
            if m:
                out.append("'%s' looks like %%%s written with %s" % (m.group(0), d, what))
                break
        else:
            for m in re.finditer(r"%L?(\d{1,2})", target):
                if not m.group(1).isascii() and int(m.group(1)) == n:
                    out.append("'%s' uses digits that Qt 6.6 and later do not read as a marker" % m.group(0))
                    break
    return out


def _qt_arg_issues(source, target, key, level):
    """QString::arg() markers of one translated text against its source."""
    src = _qt_markers(source)
    if not src:
        return []
    tgt = _qt_markers(target)
    meant = {n: i + 1 for i, n in enumerate(src)}
    shown = {n: (i + 1 if i < len(src) else None) for i, n in enumerate(tgt)}
    wrong, renumbered = [], True
    for n in tgt:
        if meant.get(n) == shown[n]:
            continue
        if shown[n] is None:
            wrong.append("%%%d is left as text" % n)
        else:
            wrong.append("%%%d shows the value of the source's %%%d" % (n, src[shown[n] - 1]))
        # A number the source lacks that still gets the value its place calls
        # for ("to %1" written "nach %2") only renumbers the marker.
        renumbered = renumbered and n not in meant and shown[n] is not None
    used = set(v for v in shown.values() if v)
    missing = ["%%%d" % src[i] for i in range(len(src)) if i + 1 not in used]
    hints = _qt_hints(source, target)
    tail = "; " + "; ".join(hints) if hints else ""
    problems = []
    if wrong and renumbered and not missing:
        problems.append(issue(WARNING, "qt-arg-renumbered",
                              "%s, so each value still lands where the translator put it; number "
                              "the marker as the source does (Qt Linguist's place-marker check "
                              "flags it)%s" % ("; ".join(wrong), tail), key))
    elif wrong:
        problems.append(issue(level, "qt-arg-order",
                              "QString::arg() fills the lowest-numbered marker first, so %s%s"
                              % ("; ".join(wrong), "" if missing else tail), key))
    if missing:
        problems.append(issue(level, "qt-arg-missing",
                              "the value of the source's %s is never shown%s" % (", ".join(missing), tail), key))
    return problems


def _qt_count_issues(source, forms, key, level):
    """The count (%n) of a plural message: a look-alike such as ٪n or ％n, or
    a %1 where the source has only %n, is shown as written, and a message with
    no %n in any form never shows the count."""
    if not _QT_COUNT_RE.search(source):
        return []
    has_markers = bool(_qt_markers(source))
    problems = []
    for i, form in enumerate(forms, 1):
        m = _QT_FAKE_COUNT_RE.search(form)
        if m:
            why = "Qt replaces only an ASCII %n or %Ln with the count"
        elif not has_markers and not _QT_COUNT_RE.search(form):
            m = re.search(r"%L?[1-9](?![0-9])", form)
            why = "the source has no place marker for arg() to fill"
        if m:
            problems.append(issue(level, "qt-count", "form %d: '%s' is not %%n; %s, so '%s' is shown as written"
                                  % (i, m.group(0), why, m.group(0)), key))
    if not problems and not any(_QT_COUNT_RE.search(f) for f in forms if f.strip()):
        problems.append(issue(WARNING, "qt-count-missing", "no plural form shows the count (%n)", key))
    return problems


def _qt_key(context, source, width=50):
    text = " ".join(source.split())
    if len(text) > width:
        text = text[:width - 3] + "..."
    return "%s: %s" % (context, text) if context else text


def check_qt(text):
    """Checks every translated message of a Qt Linguist .ts file: the
    QString::arg() place markers (%1, %L2) of each translation against its
    source, and the count (%n) of plural messages. Returns (issues, stats)."""
    problems = []
    stats = {"messages": 0, "finished": 0, "unfinished": 0, "untranslated": 0, "obsolete": 0}
    for msg in parse_qt_ts(text):
        stats["messages"] += 1
        stats[msg["state"]] += 1
        if msg["state"] not in ("finished", "unfinished"):
            continue
        # lrelease writes unfinished translations into the .qm file unless it
        # is given -nounfinished, so they may ship; their problems are warnings.
        level = ERROR if msg["state"] == "finished" else WARNING
        key = _qt_key(msg["context"], msg["source"])
        for i, form in enumerate(msg["forms"], 1):
            if form.strip():
                where = "%s (form %d)" % (key, i) if msg["numerus"] else key
                problems.extend(_qt_arg_issues(msg["source"], form, where, level))
                problems.extend(_reading_leak(msg["source"], form, where))
        if msg["numerus"]:
            problems.extend(_qt_count_issues(msg["source"], msg["forms"], key, level))
    return problems, stats


# ------------------------------------------------------------------------- CLI

def _read(path):
    """Reads UTF-8 (with or without BOM) or UTF-16 with a BOM, as Xcode often
    writes .strings files. Line endings become \\n."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_properties(path):
    """.properties files were ISO-8859-1 before Java 9. Most escape non-ASCII
    as \\uXXXX, but if the bytes aren't UTF-8, read them as Latin-1."""
    try:
        return _read(path)
    except UnicodeDecodeError:
        with open(path, "rb") as f:
            text = f.read().decode("latin-1")
        return text.replace("\r\n", "\n").replace("\r", "\n")


def run(argv=None):
    parser = argparse.ArgumentParser(prog="l10n-guard", description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--json", action="store_true", help="print issues as JSON")
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    sub = parser.add_subparsers(dest="kind", required=True)
    for kind in ("html", "md", "json", "dir", "android", "strings", "properties", "arb",
                 "resx", "laravel", "rails", "symfony"):
        p = sub.add_parser(kind)
        p.add_argument("source")
        p.add_argument("target")
    for kind in ("po", "xliff", "xcstrings", "qt"):
        p = sub.add_parser(kind)
        p.add_argument("file")
    args = parser.parse_args(argv)

    stats = None
    try:
        if args.kind in ("html", "md"):
            problems = check_document(_read(args.source), _read(args.target), args.kind)
        elif args.kind == "json":
            problems = check_catalog(json.loads(_read(args.source)), json.loads(_read(args.target)))
        elif args.kind == "dir":
            problems, stats = check_dir(args.source, args.target)
        elif args.kind == "android":
            problems = check_android(_read(args.source), _read(args.target))
        elif args.kind == "strings":
            problems = check_catalog(parse_strings(_read(args.source)),
                                     parse_strings(_read(args.target)))
        elif args.kind == "properties":
            problems = check_properties(_read_properties(args.source),
                                        _read_properties(args.target))
        elif args.kind == "resx":
            problems = check_resx(_read(args.source), _read(args.target))
        elif args.kind == "laravel":
            problems = check_laravel(_read(args.source), _read(args.target))
        elif args.kind == "rails":
            problems = check_rails(_read(args.source), _read(args.target))
        elif args.kind == "symfony":
            problems = check_symfony(_read(args.source), _read(args.target),
                                     args.source, args.target)
        elif args.kind == "arb":
            problems = check_arb(json.loads(_read(args.source)), json.loads(_read(args.target)))
        elif args.kind == "xliff":
            problems, stats = check_xliff(_read(args.file))
        elif args.kind == "xcstrings":
            problems, stats = check_xcstrings(json.loads(_read(args.file)))
        elif args.kind == "qt":
            problems, stats = check_qt(_read(args.file))
        else:
            problems, stats = check_po(_read(args.file))
    except (OSError, ValueError, ET.ParseError) as exc:
        print("l10n-guard: %s" % exc, file=sys.stderr)
        return 2

    errors = [p for p in problems if p["level"] == ERROR or args.strict]
    if args.json:
        print(json.dumps({"issues": problems, "stats": stats, "errors": len(errors)},
                         ensure_ascii=False, indent=2))
    else:
        for p in problems:
            where = " [%s]" % p["key"] if "key" in p else ""
            print("%s %s%s: %s" % (p["level"].upper(), p["code"], where, p["message"]))
        if stats and args.kind == "po":
            print("%(entries)d entries: %(translated)d translated, %(fuzzy)d fuzzy, "
                  "%(untranslated)d untranslated" % stats)
        elif stats and args.kind == "dir":
            print("%(checked)d file(s) checked, %(unmatched)d without a source file" % stats)
        elif stats:
            print(", ".join("%d %s" % (v, k) for k, v in stats.items()))
        print("%d error(s), %d warning(s)" % (len(errors), len(problems) - len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(run())
