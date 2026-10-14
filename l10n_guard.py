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
  python3 l10n_guard.py properties messages.properties  messages_fr.properties
  python3 l10n_guard.py arb        app_en.arb   app_de.arb

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

__version__ = "0.5.1"

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
    """What java.util.Formatter would throw; .exception is its class name."""

    def __init__(self, exception, detail):
        super().__init__("%s (%s)" % (exception, detail))
        self.exception = exception


def java_format(text):
    """Parses text as String.format does. Returns [(argument number, kind)]
    for each specifier that takes an argument (kind: any, char, int, float or
    date); raises JavaFormatError where Java would throw."""
    specs = []
    ordinary = last = 0
    pos = 0
    while True:
        m = _JAVA_SPEC_RE.search(text, pos)
        end = m.start() if m else len(text)
        bad = text.find("%", pos, end)
        if bad >= 0:
            after = text[bad + 1] if bad + 1 < end else "%"
            raise JavaFormatError("UnknownFormatConversionException", "Conversion = '%s'" % after)
        if not m:
            return specs
        pos = m.end()
        index, flags, width, precision, dt, conv = m.groups()
        flags = flags or ""
        spec = m.group(0)
        if len(set(flags)) != len(flags):
            raise JavaFormatError("DuplicateFormatFlagsException", spec)
        if dt:
            kind, rule = "date", "c"
            if conv not in _JAVA_DATE:
                raise JavaFormatError("UnknownFormatConversionException", "Conversion = 't%s'" % conv)
        elif conv in "%n":
            kind, rule = None, conv
        elif conv.lower() in _JAVA_KINDS and (conv.islower() or conv in _JAVA_UPPER):
            kind, rule = _JAVA_KINDS[conv.lower()], conv.lower()
        else:
            raise JavaFormatError("UnknownFormatConversionException", "Conversion = '%s'" % conv)
        if kind is None:
            if precision:
                raise JavaFormatError("IllegalFormatPrecisionException", spec)
            if flags not in ("", "-") or (conv == "n" and (flags or width)):
                raise JavaFormatError("IllegalFormatFlagsException", spec)
            if "-" in flags and not width:
                raise JavaFormatError("MissingFormatWidthException", spec)
            continue
        if kind in ("int", "float"):
            if not width and ("-" in flags or "0" in flags):
                raise JavaFormatError("MissingFormatWidthException", spec)
            if ("+" in flags and " " in flags) or ("-" in flags and "0" in flags):
                raise JavaFormatError("IllegalFormatFlagsException", spec)
        if precision and kind in ("char", "int", "date"):
            raise JavaFormatError("IllegalFormatPrecisionException", spec)
        for flag in flags:
            if flag in _JAVA_BAD_FLAGS[rule]:
                raise JavaFormatError("FormatFlagsConversionMismatchException", spec)
        if "-" in flags and not width:
            raise JavaFormatError("MissingFormatWidthException", spec)
        if "<" in flags:
            if not last:
                raise JavaFormatError("MissingFormatArgumentException", spec)
            number = last
        elif index:
            number = int(index[:-1])
            if number == 0:
                raise JavaFormatError("IllegalFormatArgumentIndexException", spec)
            last = number
        else:
            ordinary += 1
            number = last = ordinary
        specs.append((number, kind))


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


def check_java_format(source, target, key=None):
    """Checks a translation of a string the app formats with String.format.
    Java reads the whole translation before printing, so one stray % (as in
    "50 % de", "100 % sûr" or "50%ige"), an argument the source doesn't pass,
    or a %d for the source's %f crashes the app in that language."""
    src = java_formatted(source)
    if not src:
        return []
    passed = max(n for n, _ in src)
    kinds = {}
    for n, kind in src:
        if kinds.get(n, "any") == "any":
            kinds[n] = kind
    try:
        tgt = java_format(target)
    except JavaFormatError as exc:
        return [issue(ERROR, "java-format", "String.format would throw %s" % exc, key)]
    problems = []
    for n, kind in tgt:
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
            out[name] = _inner_xml(el)
        elif kind == "plurals":
            for item in el:
                if _local(item.tag) == "item" and item.get("quantity"):
                    out["%s[%s]" % (name, item.get("quantity"))] = _inner_xml(item)
        elif kind == "string-array":
            items = [item for item in el if _local(item.tag) == "item"]
            for i, item in enumerate(items):
                out["%s[%d]" % (name, i)] = _inner_xml(item)
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


def _android_text(raw):
    """The string an app gets at runtime from parse_android's text: markup
    dropped, double quotes removed, backslash escapes resolved and, outside
    quotes, runs of whitespace collapsed to one space (as aapt2 does)."""
    text = _TAG_RE.sub("", raw)
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
    for kind in ("html", "md", "json", "dir", "android", "strings", "properties", "arb"):
        p = sub.add_parser(kind)
        p.add_argument("source")
        p.add_argument("target")
    for kind in ("po", "xliff", "xcstrings"):
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
        elif args.kind == "arb":
            problems = check_arb(json.loads(_read(args.source)), json.loads(_read(args.target)))
        elif args.kind == "xliff":
            problems, stats = check_xliff(_read(args.file))
        elif args.kind == "xcstrings":
            problems, stats = check_xcstrings(json.loads(_read(args.file)))
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
