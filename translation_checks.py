"""translation-checks: catch machine (or human) translations that would break your app.

    python3 translation_checks.py locales/en.json locales/de.json --lang de [--keep "Habit Garden,Pro"]

or, in your own pipeline:

    from translation_checks import check
    problems = check("Hello, {name}!", "Hallo!", "de")      # ["lost {name}"]

The checks, per string:

- placeholders: every printf (%s, %d, %1$s, %.2f, %(name)s), brace ({name}, {0}, {{name}}), ${name} and :name
  placeholder, every HTML or XML tag, every \\n, every URL, inline `code`, Markdown link target and | of the source
  appears in the translation as often as in the source; nothing new appears;
- ICU messages ({count, plural, one {...} other {...}}): the same variables and the same plural/select keywords;
- every term you keep (names, brands) is still there exactly as written;
- not empty, and not longer than 4 times the source (plus 20 characters);
- written in the target language's script: at least 60% of the letters, for languages that do not use Latin letters;
- not identical to the source, unless the source is a single word (a loanword is often right), a term you keep,
  or has no letters to translate.

No dependencies beyond Python 3.9. MIT licence. Part of Polyglot
(https://lightsoutfactory.ai/kits/polyglot/), which also does the translating: JSON, Flutter ARB, Android,
Apple .strings, gettext and Markdown into 42 languages with your own model, with plural forms and a
translation memory.
"""
import argparse
import collections
import json
import re
import sys


# code: (English name, script, plural categories)
LANGS = {
    "ar": ("Arabic", "arabic", ("zero", "one", "two", "few", "many", "other")),
    "am": ("Amharic", "ethiopic", ("one", "other")),
    "bg": ("Bulgarian", "cyrillic", ("one", "other")),
    "cs": ("Czech", "latin", ("one", "few", "many", "other")),
    "de": ("German", "latin", ("one", "other")),
    "el": ("Greek", "greek", ("one", "other")),
    "en": ("English", "latin", ("one", "other")),
    "es": ("Spanish", "latin", ("one", "many", "other")),
    "fa": ("Persian", "arabic", ("one", "other")),
    "fi": ("Finnish", "latin", ("one", "other")),
    "fil": ("Filipino", "latin", ("one", "other")),
    "fr": ("French", "latin", ("one", "many", "other")),
    "gd": ("Scottish Gaelic", "latin", ("one", "two", "few", "other")),
    "he": ("Hebrew", "hebrew", ("one", "two", "other")),
    "ht": ("Haitian Creole", "latin", ("other",)),
    "hu": ("Hungarian", "latin", ("one", "other")),
    "hy": ("Armenian", "armenian", ("one", "other")),
    "id": ("Indonesian", "latin", ("other",)),
    "it": ("Italian", "latin", ("one", "many", "other")),
    "ja": ("Japanese", "cjk", ("other",)),
    "km": ("Khmer", "khmer", ("other",)),
    "kn": ("Kannada", "kannada", ("one", "other")),
    "ko": ("Korean", "hangul", ("other",)),
    "mk": ("Macedonian", "cyrillic", ("one", "other")),
    "ms": ("Malay", "latin", ("other",)),
    "nl": ("Dutch", "latin", ("one", "other")),
    "no": ("Norwegian Bokmål", "latin", ("one", "other")),
    "om": ("Oromo", "latin", ("one", "other")),
    "pa": ("Punjabi", "gurmukhi", ("one", "other")),
    "pl": ("Polish", "latin", ("one", "few", "many", "other")),
    "pt": ("Portuguese (Brazil)", "latin", ("one", "many", "other")),
    "ro": ("Romanian", "latin", ("one", "few", "other")),
    "ru": ("Russian", "cyrillic", ("one", "few", "many", "other")),
    "sk": ("Slovak", "latin", ("one", "few", "many", "other")),
    "sl": ("Slovenian", "latin", ("one", "two", "few", "other")),
    "sr": ("Serbian (Cyrillic)", "cyrillic", ("one", "few", "other")),
    "sv": ("Swedish", "latin", ("one", "other")),
    "th": ("Thai", "thai", ("other",)),
    "tr": ("Turkish", "latin", ("one", "other")),
    "uk": ("Ukrainian", "cyrillic", ("one", "few", "many", "other")),
    "vi": ("Vietnamese", "latin", ("other",)),
    "zh-cn": ("Chinese (Simplified)", "cjk", ("other",)),
    "zh-tw": ("Chinese (Traditional)", "cjk", ("other",)),
}
ALL = [c for c in LANGS if c != "en"]

# how folder- and file-based formats name a language when it differs from the code above
ANDROID = {"he": "iw", "id": "in", "fil": "tl", "no": "nb", "zh-cn": "zh-rCN", "zh-tw": "zh-rTW"}
APPLE = {"no": "nb", "pt": "pt-BR", "zh-cn": "zh-Hans", "zh-tw": "zh-Hant"}
UNDERSCORE = {"no": "nb", "pt": "pt_BR", "zh-cn": "zh_CN", "zh-tw": "zh_TW"}   # gettext, Flutter ARB

# Unicode ranges that count as each script (letters outside every range, e.g. digits and punctuation, are ignored)
SCRIPTS = {
    "latin": [(0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF)],
    "cyrillic": [(0x400, 0x4FF)],
    "greek": [(0x370, 0x3FF), (0x1F00, 0x1FFF)],
    "arabic": [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "hebrew": [(0x590, 0x5FF)],
    "armenian": [(0x530, 0x58F)],
    "ethiopic": [(0x1200, 0x139F)],
    "cjk": [(0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)],
    "hangul": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)],
    "thai": [(0xE00, 0xE7F)],
    "khmer": [(0x1780, 0x17FF)],
    "kannada": [(0xC80, 0xCFF)],
    "gurmukhi": [(0xA00, 0xA7F)],
}


def name(code):
    return LANGS[code][0]


def plural_categories(code):
    return LANGS[code][2]


def parse(spec):
    """"de,fr" or "all" -> ["de", "fr"]; unknown codes raise ValueError."""
    if spec.strip().lower() == "all":
        return list(ALL)
    out = []
    for c in (x.strip().lower() for x in spec.replace(" ", ",").split(",") if x.strip()):
        if c not in LANGS or c == "en":
            raise ValueError(f"unknown target language {c!r}: polyglot langs lists the codes")
        if c not in out:
            out.append(c)
    return out


def script_share(text, code):
    """The share of letters in `text` that are written in the language's script (1.0 when there are no letters)."""
    ranges = SCRIPTS[LANGS[code][1]]
    letters = [ord(ch) for ch in text if ch.isalpha()]
    if not letters:
        return 1.0
    inside = sum(1 for o in letters if any(a <= o <= b for a, b in ranges))
    return inside / len(letters)

PLACEHOLDER = re.compile(
    r"%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifuxXeEgGcpo@]"    # printf, %1$s, %.2f, %@ (no space flag: "100% sure")
    r"|%\([A-Za-z_][\w]*\)[sdifr]"                          # %(name)s
    r"|\{\{\s*[A-Za-z0-9_.\-]+\s*\}\}"                      # {{name}} (names are ASCII: {連続} is text)
    r"|\{[A-Za-z0-9_.\-]+\}"                                # {name} {0}
    r"|\$\{[A-Za-z0-9_.\-]+\}"                              # ${name}
    r"|(?<![\w:]):[a-z_][a-z0-9_]*(?![\w])"                 # :name (Laravel style)
    r"|</?[A-Za-z][\w:-]*(?:\s+[\w:-]+(?:=\"[^\"]*\"|='[^']*')?)*\s*/?>"  # tags with their attributes
    r"|\\n|\n"                                              # line breaks, escaped or real
    r"|https?://[^\s\"'<>)]+"                              # URLs
    r"|[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"  # e-mail addresses
    r"|`[^`\n]+`"                                           # inline code (Markdown)
    r"|\]\([^)\s]+\)"                                      # a link target (Markdown)
    r"|\|")                                                # table cells (Markdown)
ICU_HEAD = re.compile(r"\{\s*(\w+)\s*,\s*(plural|select|selectordinal)\s*,")
ICU_KEY = re.compile(r"(=\d+|zero|one|two|few|many|other|\w+)\s*\{")


def mask_icu(s):
    """The braces that open and close ICU branches (one {...}, =0 {...}) replaced by spaces: they are structure, and a
    branch like {None} or {なし} is text, not a placeholder."""
    chars = list(s)
    for head in ICU_HEAD.finditer(s):
        i = head.end()
        while i < len(s):
            m = re.compile(r"\s*(=\d+|[A-Za-z_]\w*)\s*\{").match(s, i)
            if not m:
                break
            open_at, depth, j = m.end() - 1, 0, m.end() - 1
            while j < len(s):
                depth += {"{": 1, "}": -1}.get(s[j], 0)
                if depth == 0:
                    break
                j += 1
            if j >= len(s):
                break
            chars[open_at] = chars[j] = " "
            i = j + 1
    return "".join(chars)


def placeholders(s, icu=False):
    return collections.Counter(m.group(0) for m in PLACEHOLDER.finditer(mask_icu(s) if icu else s))


def has_letters(s):
    stripped = PLACEHOLDER.sub(" ", s)
    return any(ch.isalpha() for ch in stripped)


def check(source, target, lang, keep=(), icu=False):
    """A list of problems (empty = good)."""
    problems = []
    if not target or not target.strip():
        return ["empty"]
    is_icu = icu or bool(ICU_HEAD.search(source))
    ps, pt = placeholders(source, is_icu), placeholders(target, is_icu)
    if is_icu:  # an ICU plural has as many branches as the language has categories: compare which, not how many
        ps, pt = collections.Counter(set(ps)), collections.Counter(set(pt))
    if ps != pt:
        missing = ps - pt
        extra = pt - ps
        if missing:
            problems.append("lost " + ", ".join(sorted(missing)))
        if extra:
            problems.append("added " + ", ".join(sorted(extra)))
    if is_icu:
        hs = sorted(ICU_HEAD.findall(source))
        ht = sorted(ICU_HEAD.findall(target))
        if hs != ht:
            problems.append("ICU variables changed")
    lost_terms = [t for t in keep if t in source and t not in target]
    if lost_terms:
        problems.append("changed " + ", ".join(lost_terms) + " (to be kept as written)")
    if len(target) > 4 * len(source) + 20:
        problems.append(f"{len(target)} characters for a source of {len(source)}")
    if LANGS[lang][1] != "latin" and has_letters(source):
        text = PLACEHOLDER.sub(" ", _strip_kept(target, keep))
        if is_icu:  # ICU variables and keywords stay in Latin letters
            text = ICU_KEY.sub(" ", ICU_HEAD.sub(" ", text))
        share = script_share(text, lang)
        if share < 0.6:
            problems.append(f"only {share:.0%} of the letters are in {LANGS[lang][1]} script")
    if target.strip() == source.strip() and _should_change(source, keep):
        problems.append("not translated")
    return problems


def _strip_kept(text, keep):
    for term in keep:
        text = text.replace(term, " ")
    return text


def _should_change(source, keep):
    rest = _strip_kept(PLACEHOLDER.sub(" ", source), keep)
    words = re.findall(r"[^\W\d_]{2,}", rest)
    # one identical word is often right (a loanword: "Backups" in German); two or more identical words are not
    return len(rest.strip()) > 3 and len(words) >= 2 and sum(len(w) for w in words) >= 4


def _flatten(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _flatten(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _flatten(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def main(argv=None):
    p = argparse.ArgumentParser(description="Check a translated JSON message file against its source.")
    p.add_argument("source")
    p.add_argument("translated")
    p.add_argument("--lang", required=True, help="the translation's language code (translation_checks.LANGS)")
    p.add_argument("--keep", default="", help="names that must stay as written, comma-separated")
    a = p.parse_args(argv)
    if a.lang not in LANGS:
        print(f"unknown language {a.lang!r}; known: {', '.join(LANGS)}", file=sys.stderr)
        return 2
    with open(a.source, encoding="utf-8-sig") as fh:
        src = dict(_flatten(json.load(fh)))
    with open(a.translated, encoding="utf-8-sig") as fh:
        dst = dict(_flatten(json.load(fh)))
    keep = [k.strip() for k in a.keep.split(",") if k.strip()]
    bad = 0
    for key, text in src.items():
        if key not in dst:
            continue
        problems = check(text, dst[key], a.lang, keep)
        if problems:
            bad += 1
            print(f"  {key}: {'; '.join(problems)}")
    missing = [k for k in src if k not in dst]
    print(f"{len(src)} strings: {len(src) - bad - len(missing)} fine, {bad} with problems, {len(missing)} missing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
