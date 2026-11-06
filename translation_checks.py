"""translation-checks: catch machine (or human) translations that would break your app.

    python3 translation_checks.py locales/en.json locales/de.json --lang de [--keep "Habit Garden,Pro"]
    python3 translation_checks.py locale/ru/LC_MESSAGES/app.po [--lang ru]      a gettext file: its own msgids are the
                                                                               source, and its plural rule is checked

or, in your own pipeline:

    from translation_checks import check
    problems = check("Hello, {name}!", "Hallo!", "de")      # ["lost {name}"]

The checks, per string:

- placeholders: every printf (%s, %d, %1$s, %.2f, %(name)s), brace ({name}, {0}, {{name}}), ${name} and :name
  placeholder, every HTML or XML tag, every \\n, every URL, inline `code`, Markdown link target and | of the source
  appears in the translation as often as in the source; nothing new appears;
- ICU messages ({count, plural, one {...} other {...}}): the same variables and the same plural/select keywords, and
  a branch for a category that covers several numbers shows the number (# or the variable) when the English "other"
  branch does: Russian "one" is also 21 and 31, French "one" is also 0, so "one {One day left}" needs # there;
- every term you keep (names, brands) is still there exactly as written, where the source has it as a word in its
  own case ("Pressing" does not contain the name "Press"); a translation may join it into a compound
  ("Store-Dock-Kits");
- numbers: every number written in digits comes back, in any digits (٣, ３) and with any separators (1,000 = 1.000 =
  1 000; 06 = 6); what the source spells out may come back in digits ("ten" -> 10, "July 2026" -> 2026年7月,
  "3 million" -> 300万, "3 pm" -> 15:00, "the twelfth month" -> 12ヶ月目, "Feb." -> 2月), and a lone 1 may become a
  word. ICU messages skip this check;
- no stray letters: letters of another script that the source does not have, such as a word slipping into Chinese
  in a Romanian sentence ("valori植入"), Thai inside Khmer or a Cyrillic "о" inside a Finnish word. Latin letters are
  always allowed; Chinese, Japanese and Korean are not checked, Serbian and Punjabi only for Chinese, Japanese and
  Korean letters;
- not empty, and not longer than 4 times the source (plus 20 characters);
- written in the target language's script: at least 60% of the letters, for languages that do not use Latin letters
  (names, code and paths copied from the source do not count; a single word or unit kept as it is passes);
- gettext files: the header's Plural-Forms sends every number from 0 to 1000 to a slot that holds one CLDR form only
  (a Russian file with "nplurals=2; plural=(n != 1)" puts 2 and 5 in one slot, where Russian needs "привычки" and
  "привычек"); every plural entry has a msgstr for each slot, each form keeps the placeholders, and a slot used for
  several numbers shows the number (Russian msgstr[0] is also 21 and 31);
- not identical to the source, unless the source is a single word (a loanword is often right), a term you keep,
  or has no letters to translate.

No dependencies beyond Python 3.9. MIT licence. Part of Polyglot
(https://lightsoutfactory.ai/kits/polyglot/), which also does the translating: JSON, Flutter ARB, Android,
Apple .strings, gettext and Markdown into 42 languages with your own model, with plural forms and a
translation memory.
"""
import argparse
import collections
import gettext
import json
import re
import sys
import unicodedata

__version__ = "1.3.2"


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
# the scripts a model may slip into in the middle of a sentence, for the stray-letter check (Latin is never stray)
STRAY_SCRIPTS = {**{k: v for k, v in SCRIPTS.items() if k != "latin"}, "cyrillic": [(0x400, 0x52F)],
                 "devanagari": [(0x900, 0x97F)], "bengali": [(0x980, 0x9FF)], "gujarati": [(0xA80, 0xAFF)],
                 "oriya": [(0xB00, 0xB7F)], "tamil": [(0xB80, 0xBFF)], "telugu": [(0xC00, 0xC7F)],
                 "malayalam": [(0xD00, 0xD7F)], "sinhala": [(0xD80, 0xDFF)], "lao": [(0xE80, 0xEFF)],
                 "tibetan": [(0xF00, 0xFFF)], "myanmar": [(0x1000, 0x109F)], "georgian": [(0x10A0, 0x10FF)],
                 "thaana": [(0x780, 0x7BF)]}
EAST_ASIAN = ("cjk", "hangul")
# written in more than one script (Serbian in Latin letters, Punjabi in Shahmukhi): only Chinese, Japanese and Korean
# letters are stray there
MULTI_SCRIPT = {"sr", "pa"}
# CLDR cardinal plural rules: the first whole numbers each category is used for (up to five; none where only fractions
# use it). A form for a category that covers several numbers has to show the number: Russian "one" is 1, 21, 31...,
# French "one" is 0 and 1, so "One day left" cannot be translated as "one day" there.
PLURAL_NUMBERS = {
    "ar": {"zero": (0,), "one": (1,), "two": (2,), "few": (3, 4, 5, 6, 7), "many": (11, 12, 13, 14, 15),
           "other": (100, 101, 102, 200, 201)},
    "am": {"one": (0, 1), "other": (2, 3, 4, 5, 6)},
    "bg": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "cs": {"one": (1,), "few": (2, 3, 4), "many": (), "other": (0, 5, 6, 7, 8)},
    "de": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "el": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "en": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "es": {"one": (1,), "many": (1000000, 2000000, 10000000), "other": (0, 2, 3, 4, 5)},
    "fa": {"one": (0, 1), "other": (2, 3, 4, 5, 6)},
    "fi": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "fil": {"one": (0, 1, 2, 3, 5), "other": (4, 6, 9, 14, 16)},
    "fr": {"one": (0, 1), "many": (1000000, 2000000, 10000000), "other": (2, 3, 4, 5, 6)},
    "gd": {"one": (1, 11), "two": (2, 12), "few": (3, 4, 5, 6, 7), "other": (0, 20, 21, 22, 23)},
    "he": {"one": (1,), "two": (2,), "other": (0, 3, 4, 5, 6)},
    "ht": {"other": (0, 1, 2, 3, 4)},
    "hu": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "hy": {"one": (0, 1), "other": (2, 3, 4, 5, 6)},
    "id": {"other": (0, 1, 2, 3, 4)},
    "it": {"one": (1,), "many": (1000000, 2000000, 10000000), "other": (0, 2, 3, 4, 5)},
    "ja": {"other": (0, 1, 2, 3, 4)},
    "km": {"other": (0, 1, 2, 3, 4)},
    "kn": {"one": (0, 1), "other": (2, 3, 4, 5, 6)},
    "ko": {"other": (0, 1, 2, 3, 4)},
    "mk": {"one": (1, 21, 31, 41, 51), "other": (0, 2, 3, 4, 5)},
    "ms": {"other": (0, 1, 2, 3, 4)},
    "nl": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "no": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "om": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "pa": {"one": (0, 1), "other": (2, 3, 4, 5, 6)},
    "pl": {"one": (1,), "few": (2, 3, 4, 22, 23), "many": (0, 5, 6, 7, 8), "other": ()},
    "pt": {"one": (0, 1), "many": (1000000, 2000000, 10000000), "other": (2, 3, 4, 5, 6)},
    "ro": {"one": (1,), "few": (0, 2, 3, 4, 5), "other": (20, 21, 22, 23, 24)},
    "ru": {"one": (1, 21, 31, 41, 51), "few": (2, 3, 4, 22, 23), "many": (0, 5, 6, 7, 8), "other": ()},
    "sk": {"one": (1,), "few": (2, 3, 4), "many": (), "other": (0, 5, 6, 7, 8)},
    "sl": {"one": (1, 101, 201, 301, 401), "two": (2, 102, 202, 302, 402), "few": (3, 4, 103, 104, 203),
           "other": (0, 5, 6, 7, 8)},
    "sr": {"one": (1, 21, 31, 41, 51), "few": (2, 3, 4, 22, 23), "other": (0, 5, 6, 7, 8)},
    "sv": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "th": {"other": (0, 1, 2, 3, 4)},
    "tr": {"one": (1,), "other": (0, 2, 3, 4, 5)},
    "uk": {"one": (1, 21, 31, 41, 51), "few": (2, 3, 4, 22, 23), "many": (0, 5, 6, 7, 8), "other": ()},
    "vi": {"other": (0, 1, 2, 3, 4)},
    "zh-cn": {"other": (0, 1, 2, 3, 4)},
    "zh-tw": {"other": (0, 1, 2, 3, 4)},
}

# gettext Plural-Forms for each target, and the CLDR category msgstr[0], msgstr[1]... carry. Every whole number from 0
# to 10000 lands on the form CLDR gives it (checked against Babel 2.18). Categories CLDR uses for fractions only
# (Russian "other", Czech "many") get no index, and the "many" of exact millions in Spanish, French, Italian and
# Portuguese shares "other". Haitian Creole nouns do not change for number: one form, as for its other formats.
_ONE_OTHER = ("nplurals=2; plural=(n != 1);", ("one", "other"))
_ZERO_ONE = ("nplurals=2; plural=(n > 1);", ("one", "other"))
_SINGLE = ("nplurals=1; plural=0;", ("other",))
_SLAVIC = "(n % 10 == 1 && n % 100 != 11) ? 0 : ((n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 1 : 2)"
GETTEXT_PLURALS = {
    **{c: _ONE_OTHER for c in ("bg", "de", "el", "es", "fi", "hu", "it", "nl", "no", "om", "sv", "tr")},
    **{c: _ZERO_ONE for c in ("am", "fa", "fr", "hy", "kn", "pa", "pt")},
    **{c: _SINGLE for c in ("ht", "id", "ja", "km", "ko", "ms", "th", "vi", "zh-cn", "zh-tw")},
    "ar": ("nplurals=6; plural=(n == 0) ? 0 : ((n == 1) ? 1 : ((n == 2) ? 2 : ((n % 100 >= 3 && n % 100 <= 10) ? 3 : "
           "((n % 100 >= 11) ? 4 : 5))));", ("zero", "one", "two", "few", "many", "other")),
    "cs": ("nplurals=3; plural=(n == 1) ? 0 : ((n >= 2 && n <= 4) ? 1 : 2);", ("one", "few", "other")),
    "sk": ("nplurals=3; plural=(n == 1) ? 0 : ((n >= 2 && n <= 4) ? 1 : 2);", ("one", "few", "other")),
    "fil": ("nplurals=2; plural=(n != 1 && n != 2 && n != 3 && (n % 10 == 4 || n % 10 == 6 || n % 10 == 9));",
            ("one", "other")),
    "gd": ("nplurals=4; plural=(n == 1 || n == 11) ? 0 : ((n == 2 || n == 12) ? 1 : ((n > 2 && n < 20) ? 2 : 3));",
           ("one", "two", "few", "other")),
    "he": ("nplurals=3; plural=(n == 1) ? 0 : ((n == 2) ? 1 : 2);", ("one", "two", "other")),
    "mk": ("nplurals=2; plural=(n % 10 == 1 && n % 100 != 11) ? 0 : 1;", ("one", "other")),
    "pl": ("nplurals=3; plural=(n == 1) ? 0 : ((n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 1 : 2);",
           ("one", "few", "many")),
    "ro": ("nplurals=3; plural=(n == 1) ? 0 : ((n == 0 || n % 100 >= 1 && n % 100 <= 19) ? 1 : 2);",
           ("one", "few", "other")),
    "ru": ("nplurals=3; plural=" + _SLAVIC + ";", ("one", "few", "many")),
    "uk": ("nplurals=3; plural=" + _SLAVIC + ";", ("one", "few", "many")),
    "sr": ("nplurals=3; plural=" + _SLAVIC + ";", ("one", "few", "other")),
    "sl": ("nplurals=4; plural=(n % 100 == 1) ? 0 : ((n % 100 == 2) ? 1 : ((n % 100 == 3 || n % 100 == 4) ? 2 : 3));",
           ("one", "two", "few", "other")),
}

def name(code):
    return LANGS[code][0]


def plural_categories(code):
    return LANGS[code][2]


def plural_numbers(code, category, explicit=()):
    """The whole numbers a plural category is used for (the first five), without those an ICU message gives an =N
    branch of their own."""
    return [n for n in PLURAL_NUMBERS.get(code, {}).get(category, ()) if n not in explicit]


def gettext_plural(code):
    """(the Plural-Forms header value, the CLDR category of msgstr[0], msgstr[1], ...) for a target code"""
    return GETTEXT_PLURALS[code]


def _numbers_text(nums):
    return ", ".join(map(str, nums[:4])) + ("..." if len(nums) > 4 else "")


def several_numbers_problem(category, nums, mark):
    """Worded so that a model acts on it: told only to "put # in it", ours wrote Persian "one" as "one habit" three
    times out of three; told not to say "one" and to write the form like the "other" one, it did it right."""
    word = category if category in ("zero", "one", "two") else "the number in words"
    return (f"the {category} form is used for {_numbers_text(nums)}, so it must not say {word}: write it like the "
            f"other form, with {mark} where the number goes")


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
    r"|%\([A-Za-z_][\w]*\)[-+#0 ]*\d*(?:\.\d+)?[sdifrxXeEgGc]"  # %(name)s, %(value).1f
    r"|\{\{\s*[A-Za-z0-9_.\-]+\s*\}\}"                      # {{name}} (names are ASCII: {連続} is text)
    r"|\{[A-Za-z0-9_.\-]+\}"                                # {name} {0}
    r"|\$\{[A-Za-z0-9_.\-]+\}"                              # ${name}
    r"|(?<![\w:]):[a-z_][a-z0-9_]*(?![\w])"                 # :name (Laravel style)
    r"|</?[A-Za-z][\w:-]*(?:\s+[\w:-]+(?:=\"[^\"]*\"|='[^']*')?)*\s*/?>"  # tags with their attributes
    r"|\\n|\n"                                              # line breaks, escaped or real
    r"|https?://[^\s\"'<>)\u201c\u201d\u201e\u00ab\u00bb\u2018\u2019\u200e\u200f\u202a-\u202e\u2066-\u2069]*"
    r"[^\s\"'<>)\u201c\u201d\u201e\u00ab\u00bb\u2018\u2019\u200e\u200f\u202a-\u202e\u2066-\u2069.,;:!?]"  # URLs, without the quote,
                                                            # bidi mark or full stop that follows them
    r"|[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"  # e-mail addresses
    r"|`[^`\n]+`"                                           # inline code (Markdown)
    r"|\]\([^)\s]+\)"                                      # a link target (Markdown)
    r"|\|")                                                # table cells (Markdown)
ICU_HEAD = re.compile(r"\{\s*(\w+)\s*,\s*(plural|select|selectordinal)\s*,")
ICU_KEY = re.compile(r"(=\d+|zero|one|two|few|many|other|\w+)\s*\{")
ICU_BRANCH = re.compile(r"\s*(=\d+|[A-Za-z_]\w*)\s*\{")


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


def icu_branches(s):
    """{variable: [(selector, text), ...]} for every plural argument of an ICU message (select and selectordinal are
    left out: their branches are not the cardinal categories)."""
    out = {}
    for head in ICU_HEAD.finditer(s):
        if head.group(2) != "plural":
            continue
        i, items = head.end(), out.setdefault(head.group(1), [])
        while i < len(s):
            m = ICU_BRANCH.match(s, i)
            if not m:
                break
            depth, j = 0, m.end() - 1
            while j < len(s):
                depth += {"{": 1, "}": -1}.get(s[j], 0)
                if depth == 0:
                    break
                j += 1
            if j >= len(s):
                break
            items.append((m.group(1), s[m.end():j]))
            i = j + 1
    return out


def placeholders(s, icu=False):
    return collections.Counter(m.group(0) for m in PLACEHOLDER.finditer(mask_icu(s) if icu else s))


def has_letters(s):
    stripped = PLACEHOLDER.sub(" ", s)
    return any(ch.isalpha() for ch in stripped)


def stray_letters(source, target, lang):
    """Letters of the translation that are in another script than the language's and not in the source: a model that
    slips into Chinese for one word ("valori植入"), into Thai on a Khmer page or types a Cyrillic "о" in Finnish."""
    own = LANGS[lang][1]
    if own in EAST_ASIAN:  # Japanese mixes kana and kanji, Korean may use hanja: no script there is foreign enough
        return ""
    found = set()
    for ch in set(target) - set(source):
        if not ch.isalpha() or ch.isascii():
            continue
        o = ord(ch)
        for script, ranges in STRAY_SCRIPTS.items():
            if any(a <= o <= b for a, b in ranges):
                if script != own and (lang not in MULTI_SCRIPT or script in EAST_ASIAN):
                    found.add(ch)
                break
    return "".join(sorted(found))


def _lost_terms(source, target, keep):
    """Kept names the source has as a word, in its own case, that the translation does not copy. The translation may
    join a name into a compound or give it an ending ("Store-Dock-Kits", "Factory Floorin"). Of two lost names, only
    the longer is reported."""
    flat = re.sub(r"[\s-]+", " ", target)
    lost = [n for n in keep if n and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), source)
            and re.sub(r"[\s-]+", " ", n) not in flat]
    return [n for n in lost if not any(n != m and n in m for m in lost)]


# ---------------------------------------------------------------------------------------------------------- numbers
ENTITY = re.compile(r"&(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#x[0-9a-fA-F]+);")   # "&#39;" is an apostrophe, not 39
SEP = ".,\u00a0\u202f'\u066b\u066c\uff0e"    # Arabic and full-width ones too
# a space or a full-width comma groups thousands only before three digits ("1 000", "１，０００"): "2007, 104 in all"
# and "$80,000，2026年" (Chinese for "$80,000, 2026") stay two numbers
NUM = re.compile(r"\d(?:[\d%s]|(?<=\d)[\s\uff0c](?=\d{3}(?!\d)))*\d|\d" % SEP)
# read again without spaces inside numbers when the first reading differs: Gaelic "thug 8 109" is 8 and 109
NUM_TIGHT = re.compile(r"\d(?:[\d%s])*\d|\d" % SEP)
MONTHS = {m: i for i, m in enumerate("january february march april may june july august september october november "
                                       "december".split(), 1)}
# a calendar label ("Feb.", "Thu") is a number in many languages: 2月, Tháng 2, 2월; Thứ 5 (Vietnamese Thursday).
# Only for short sources, where "mar" or "sun" cannot be an ordinary word
MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
              "nov": 11, "dec": 12}
WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
WEEKDAY_ABBR = {"mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun"}
WORDNUM = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                   "sixteen seventeen eighteen nineteen twenty".split(), range(21)))
WORDNUM.update(thirty=30, forty=40, fifty=50, sixty=60, seventy=70, eighty=80, ninety=90, hundred=100, thousand=1000,
               million=1000000, dozen=12, first=1, second=2, third=3, fourth=4, fifth=5, sixth=6, seventh=7,
               eighth=8, ninth=9, tenth=10, once=1, twice=2, thrice=3)    # "the second try" -> 2回目
# words a good translation may write in digits: "half the time" -> 50%, "half a second" -> 0.5秒, "half an hour" -> 30分,
# "midnight" -> 0時, "a dozen" -> 12, "minors" -> "under 18", "from none" -> 0から, "around the clock" -> 24時間365日,
# and in blackjack "the dealer busts" -> "le croupier dépasse 21" (231 good translations on our sites said so)
IMPLIED = {"half": ("2", "50", "05", "30"), "halves": ("2",), "quarter": ("4", "25"), "quarters": ("4", "75"),
           "thirds": ("3",), "midnight": ("0", "12", "24", "00"), "noon": ("12",), "dozen": ("12",),
           "dozens": ("12",), "clock": ("365",), "minor": ("18",), "minors": ("18",), "none": ("0",),
           "bust": ("21",), "busts": ("21",), "busted": ("21",), "busting": ("21",),
           "decade": ("10",), "decades": ("10",), "century": ("100",)}
# ordinals come back as digits in many languages ("the twelfth month" is 12ヶ月目); a fifth is also 20%, a third 33%
IMPLIED.update({w: (str(i),) for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth "
    "fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split(), 1)})
IMPLIED.update(thirtieth=("30",), fortieth=("40",), fiftieth=("50",), hundredth=("100",), fifth=("5", "20"),
               fifths=("5",), third=("3", "33"))
PER_100 = re.compile(r"\b(?:of|in|out of) (?:every |each )?100\b", re.I)   # "97 of every 100" is rightly "97%"
TIME_12 = re.compile(r"\b(\d{1,2})(?::\d\d)?\s*([ap])\.?m\b", re.I)          # "3 pm" may become 15:00
DATE_DMY = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")             # dates are three numbers, not one
DATE_YMD = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_YEAR0 = re.compile(r"\b0([1-9])/(\d{4})\b")
DATE_DM = re.compile(r"(?<![\d.,])(\d{1,2})\.\s?(\d{1,2})\.(?!\d)")
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(%s)\b|\b(%s)\s+(\d{1,2})(?:st|nd|rd|th)?\b"
                       % (_MON, _MON))
# "3 million tokens" is 300万 in Japanese and Chinese, 300만 in Korean, 3,000,000 in some translations
SCALE_WORDS = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}
SCALE_UNITS = {"千": 10 ** 3, "천": 10 ** 3, "万": 10 ** 4, "萬": 10 ** 4, "만": 10 ** 4, "百万": 10 ** 6, "百萬": 10 ** 6,
               "백만": 10 ** 6, "千万": 10 ** 7, "千萬": 10 ** 7, "천만": 10 ** 7, "亿": 10 ** 8, "億": 10 ** 8, "억": 10 ** 8}
SCALE_SPELLED = {"a": 1, **{w: WORDNUM[w] for w in "one two three four five six seven eight nine ten eleven twelve "
                                                     "fifteen twenty thirty forty fifty hundred".split()}}
_SNUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|%s" % "|".join(SCALE_SPELLED)
SNUM = re.compile(r"(?<![\w.,])(?:%s)(?!\w)" % _SNUM)
SCALED_EN = re.compile(r"(?<![\w.,])(?:%s)(?:\s*(?:,|and|or|to|-|–)\s*(?:%s))*[\s-]+(%s)\b"    # "0.76 and 1.08 million"
                       % (_SNUM, _SNUM, "|".join(SCALE_WORDS)))
SCALED_UNIT = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%s)" % "|".join(sorted(SCALE_UNITS, key=len, reverse=True)))


def _text(s):
    return ENTITY.sub(" ", PLACEHOLDER.sub(" ", s))


def _plain(s):
    return re.sub(r"\s+", " ", _text(s)).strip()


def _ascii_digits(s):
    """Arabic-Indic, Persian, Devanagari, Thai, full-width... digits as 0-9."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdigit() and not "0" <= ch <= "9"
                   and unicodedata.decimal(ch, None) is not None else ch for ch in s)


def _numbers(s, num=NUM):
    s = _ascii_digits(_text(s))
    s = DATE_DMY.sub(lambda m: f"{int(m[1])} {int(m[2])} {m[3]}", s)      # 30.09.2026 = 2026年9月30日
    s = DATE_YMD.sub(lambda m: f"{m[1]} {int(m[2])} {int(m[3])}", s)
    s = MONTH_YEAR0.sub(r"\1 \2", s)
    def norm(n):                    # "06" is 6, but "0.5" keeps its zero (decimals lose only their separator)
        bare = re.sub(r"[\s\uff0c%s]" % SEP, "", n)
        return (bare.lstrip("0") or "0") if bare == n else bare
    return collections.Counter(norm(n) for n in num.findall(s))


def _day_month(source, target):
    """'15 June' becomes '15.6.' in Finnish, German or Czech: read that as a day and a month, only for a day and month
    the source names, so a decimal such as 15.6 is never split."""
    pairs = set()
    for m in DAY_MONTH.finditer(_plain(source).lower()):
        d, w = (m[1], m[2]) if m[1] else (m[4], m[3])
        if w != "may" and 1 <= int(d) <= 31:
            pairs.add((int(d), MONTHS[w]))
    if not pairs:
        return target
    return DATE_DM.sub(lambda m: f"{m[1]} {m[2]}" if (int(m[1]), int(m[2])) in pairs else m[0], target)


def _spelled(source):
    """Numbers a translation may write in digits because the source says them in words or names them: 'ten rounds',
    'a thousand sessions', 'July 2026' (2026年7月), 'a ten-day trial' (10日間)."""
    out = []
    low = _plain(source).lower()
    if re.search(r"\b(?:a)?round[- ]the[- ]clock\b", low):
        out += ["24", "7"]
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", low)
    short = len(words) <= 3
    for w in words:
        parts = w.split("-")
        for part in parts:
            out += IMPLIED.get(part, ())
            if part in MONTHS:
                out.append(str(MONTHS[part]))
            elif short and part in MONTH_ABBR:
                out.append(str(MONTH_ABBR[part]))
            if short and (part in WEEKDAYS or part in WEEKDAY_ABBR):   # a calendar label, not a weekday in a sentence
                out += [str(i) for i in range(1, 8)]        # the day's number, counted from Sunday or Monday
        if all(x in WORDNUM for x in parts):
            out.append(str(sum(WORDNUM[x] for x in parts)))
        elif len(parts) > 1:
            out += [str(WORDNUM[x]) for x in parts if x in WORDNUM]
    return out


def _scaled(source, target):
    """Digits of the source and of the translation that name the same value as a 'N million' of the source, to drop
    from both sides ('' when the source spells the number out)."""
    want = collections.defaultdict(list)
    for m in SCALED_EN.finditer(_plain(source).lower()):
        for n in SNUM.findall(m[0][:m.start(1) - m.start(0)]):
            x = float(n.replace(",", "")) if n[0].isdigit() else SCALE_SPELLED[n]
            want[round(x * SCALE_WORDS[m[1]])].append(re.sub(r"[.,]", "", n) if n[0].isdigit() else "")
    drop_src, drop_out = collections.Counter(), collections.Counter()
    if not want:
        return drop_src, drop_out
    o = _ascii_digits(_plain(target))
    found = [(round(float(m[1].replace(",", "")) * SCALE_UNITS[m[2]]), re.sub(r"[.,]", "", m[1]))
             for m in SCALED_UNIT.finditer(o)]
    for n in NUM.findall(SCALED_UNIT.sub(" ", o)):
        digits = re.sub(r"[\s\uff0c%s]" % SEP, "", n)
        if digits.isdigit():
            found.append((int(digits), digits))
    for value, digits in found:
        if want.get(value):
            raw = want[value].pop()
            if raw:
                drop_src[raw] += 1
            drop_out[digits] += 1
    return drop_src, drop_out


def number_changes(source, target, num=NUM):
    """(lost, added): Counters of the numbers of the source the translation lacks and of those it adds, after the
    renderings a good translation may use. Both empty when the numbers match."""
    times = list(TIME_12.finditer(_plain(source)))
    if times:   # "6 p.m." may be 18:00, 18.00 or 06.00: an hour and its minutes, ":00" dropped. With a dot only for an
        # hour the source names, so "$4.50" stays a price
        hours = {str(int(m[1]) % 12 + (12 if m[2].lower() == "p" else 0)) for m in times} | {str(int(m[1])) for m in times}

        def hm(m):
            if m[2] == ":" or str(int(m[1])) in hours:
                return m[1] if m[3] == "00" else f"{m[1]} {m[3]}"
            return m[0]
        clock = re.compile(r"(?<!\d)(?<!\d[.,:])(\d{1,2})([:.])([0-5]\d)(?!\d)(?![.,:]\d)")
        source = clock.sub(lambda m: hm(m) if m[2] == ":" and not re.match(r"\s*[ap]\.?m\b", m.string[m.end():], re.I)
                           else m[0], source)        # "3:30 pm" stays whole for the 12-hour reading below
        target = clock.sub(hm, target)
    sn, on = _numbers(source.replace("24/7", " ")), _numbers(_day_month(source, target), num)
    if "24/7" in source:            # "around the clock" is a fine translation of 24/7, so is "24 hours, 365 days"
        on -= collections.Counter(("24", "7", "365"))
    for d in _spelled(source):      # "ten rounds" may become "10 rounds", "July" a month number
        if on[d] > sn[d]:
            on[d] -= 1
    for m in TIME_12.finditer(_plain(source)):
        h = int(m[1])
        h24 = str(h % 12 + (12 if m[2].lower() == "p" else 0))
        if 1 <= h <= 12 and on[h24] > sn[h24] and sn[str(h)] > on[str(h)]:
            on[h24] -= 1
            on[str(h)] += 1
    if PER_100.search(_plain(source)) and re.search(r"[%％]", target) and sn["100"] > on["100"]:
        sn["100"] -= 1
    # "1 round in 26" -> "every 26th round": a lone 1 may become a word or vanish in good prose
    del sn["1"], on["1"]
    sn, on = +sn, +on
    if sn != on:                    # only a mismatch looks for "3 million" = 300万
        drop_src, drop_out = _scaled(source, target)
        del drop_src["1"], drop_out["1"]
        if not drop_src - sn and not drop_out - on:
            sn, on = sn - drop_src, on - drop_out
    return sn - on, on - sn


def check(source, target, lang, keep=(), icu=False, numbers=True):
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
        # a branch for a category that covers several numbers must show the number, as the English "other" does
        src_branches = icu_branches(source)
        for var, branches in icu_branches(target).items():
            other = dict(src_branches.get(var, [])).get("other", "")
            marks = [t for t in ("#", "{%s}" % var) if t in other]
            explicit = {int(sel[1:]) for sel, _ in branches if sel.startswith("=")}
            for sel, text in branches:
                nums = plural_numbers(lang, sel, explicit)
                if marks and not sel.startswith("=") and len(nums) >= 2 and not any(t in text for t in marks):
                    problems.append(several_numbers_problem(sel, nums, marks[0]))
    lost_terms = _lost_terms(source, target, keep)
    if lost_terms:
        problems.append("changed " + ", ".join(lost_terms) + " (to be kept as written)")
    if numbers and not is_icu:      # each plural branch may repeat or drop a number
        lost, added = number_changes(source, target)
        if (lost or added) and any(number_changes(source, target, NUM_TIGHT)):
            problems.append("numbers changed: " + "; ".join(
                f"{what} {', '.join(sorted(c.elements()))}" for what, c in (("lost", lost), ("added", added)) if c))
    if len(target) > 4 * len(source) + 20:
        problems.append(f"{len(target)} characters for a source of {len(source)}")
    stray = stray_letters(source, target, lang)
    if stray:
        problems.append(f"letters of another script than {LANGS[lang][0]}: {stray[:12]}")
    same = target.strip() == source.strip()
    if LANGS[lang][1] != "latin" and has_letters(source) and not (same and not _should_change(source, keep)):
        text = PLACEHOLDER.sub(" ", _strip_kept(target, keep))
        if is_icu:  # ICU variables and keywords stay in Latin letters
            text = ICU_KEY.sub(" ", ICU_HEAD.sub(" ", text))
        if script_share(text, lang) > 0:  # around translated words, names and code copied from the source stay
            # ASCII edges: in Python a Chinese or Japanese character counts as \w, so "JSON对象" has no \b in it
            names = {w for w in re.findall(r"[A-Za-z0-9_./-]*[/_.][A-Za-z0-9_./-]*[A-Za-z/]|[A-Za-z][A-Za-z0-9]*", text)
                     if (_name_like(w) or re.search(r"[/_.]", w))
                     and re.search(r"(?<![A-Za-z0-9_/.])%s(?![A-Za-z0-9_/])" % re.escape(w),
                                   PLACEHOLDER.sub(" ", source), re.I)}
            text = re.sub(r"(?<![A-Za-z0-9_/.])(%s)(?![A-Za-z0-9_/])" % "|".join(map(re.escape, sorted(
                names, key=len, reverse=True))), " ", text) if names else text
        share = script_share(text, lang)
        if share < 0.6:
            problems.append(f"only {share:.0%} of the letters are in {LANGS[lang][1]} script")
    if same and _should_change(source, keep):
        problems.append("not translated")
    return problems


def _name_like(word):
    """PostgreSQL, Django, True, IPv4, URL: a capital, two of them or a digit, as names and code have"""
    return word[0].isupper() or any(ch.isdigit() for ch in word) or sum(ch.isupper() for ch in word) >= 2


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



# ------------------------------------------------------------------------------------------------ gettext files --
_PO_LINE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+"(.*)"\s*$')
_PO_CONT = re.compile(r'^"(.*)"\s*$')
_GETTEXT_CODES = {**{v: k for k, v in UNDERSCORE.items()}, "zh_Hans": "zh-cn", "zh_Hant": "zh-tw"}
_COUNT = re.compile(r"%(\d+\$)?[di]|\{(count|n|num|number|quantity)\}|%\((count|n|num|number|quantity)\)[sd]")


def _po_unquote(s):
    return re.sub(r'\\(["\\nt])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def po_entries(text):
    """The entries of a .po file: dicts with msgctxt, msgid, msgid_plural, msgstr or msgstr[0], msgstr[1]...
    Comments and obsolete (#~) entries are skipped."""
    entries, cur, field = [], None, None
    for line in text.splitlines() + [""]:
        if not line.strip():
            if cur and "msgid" in cur:
                entries.append(cur)
            cur, field = None, None
            continue
        cur = cur if cur is not None else {}
        if line.startswith("#"):
            continue
        m = _PO_LINE.match(line)
        if m:
            field = m.group(1)
            cur[field] = _po_unquote(m.group(2))
        elif field and _PO_CONT.match(line):
            cur[field] += _po_unquote(_PO_CONT.match(line).group(1))
    return entries


def po_language(text):
    """The language code of a .po file from its Language: header (pt_BR -> pt, nb -> no), or None."""
    header = next((e.get("msgstr", "") for e in po_entries(text) if e.get("msgid") == ""), "")
    m = re.search(r"Language:\s*([\w@-]+)", header)
    code = (m.group(1) if m else "").split("@")[0]
    for c in (_GETTEXT_CODES.get(code), code.lower().replace("_", "-"), code.split("_")[0].lower()):
        if c in LANGS:
            return c
    return None


def plural_rule_problems(rule, lang, upto=1000):
    """([problems], {slot: numbers 0..upto it serves}) for a Plural-Forms header value: every slot must serve numbers
    that CLDR gives one form only."""
    want = gettext_plural(lang)[0]
    m = re.fullmatch(r"\s*nplurals\s*=\s*(\d+)\s*;\s*plural\s*=\s*(.+?)\s*;?\s*", rule or "")
    if not m:
        return [f"no usable Plural-Forms in the header; for {name(lang)} use: {want}"], {}
    n_slots = int(m.group(1))
    try:
        pick = gettext.c2py(m.group(2))
    except ValueError as e:
        return [f"the Plural-Forms formula cannot be read ({e}); for {name(lang)} use: {want}"], {}
    ours, cats = gettext.c2py(want.split("plural=", 1)[1].rstrip(";")), gettext_plural(lang)[1]
    slots, forms = {i: [] for i in range(n_slots)}, {}
    for n in range(upto + 1):
        i = pick(n)
        if i not in slots:
            return [f"Plural-Forms sends {n} to msgstr[{i}], but nplurals is {n_slots}"], {}
        slots[i].append(n)
        forms.setdefault(i, {}).setdefault(cats[ours(n)], []).append(n)
    problems = [f"msgstr[{i}] serves numbers that {name(lang)} gives different forms ("
                + "; ".join(f"{c}: {_numbers_text(ns)}" for c, ns in by_cat.items()) + f"); use: {want}"
                for i, by_cat in sorted(forms.items()) if len(by_cat) > 1]
    return problems, slots


def check_po(text, lang, keep=(), numbers=True):
    """The problems of a translated .po file as [(where, [problems])], and (translated entries, untranslated)."""
    entries = po_entries(text)
    header = next((e.get("msgstr", "") for e in entries if e.get("msgid") == ""), "")
    out, slots = [], {}
    if any("msgid_plural" in e for e in entries):
        m = re.search(r"Plural-Forms:\s*([^\n]*)", header)
        rule_problems, slots = plural_rule_problems(m.group(1) if m else "", lang)
        if rule_problems:
            out.append(("Plural-Forms", rule_problems))
    ours, cats = gettext.c2py(gettext_plural(lang)[0].split("plural=", 1)[1].rstrip(";")), gettext_plural(lang)[1]
    done = missing = 0
    for e in entries:
        if e.get("msgid", "") == "":
            continue
        where = (e["msgctxt"] + " | " if "msgctxt" in e else "") + e["msgid"][:60].replace("\n", " ")
        if "msgid_plural" not in e:
            if not e.get("msgstr"):
                missing += 1
                continue
            done += 1
            problems = check(e["msgid"], e["msgstr"], lang, keep, numbers=numbers)
        else:
            given = [k for k in e if k.startswith("msgstr[")]
            if not any(e[k] for k in given):
                missing += 1
                continue
            done += 1
            problems = [f"{len(given)} msgstr forms, but Plural-Forms has {len(slots)}"] if slots and len(given) != len(slots) else []
            other_ph = set(placeholders(e["msgid_plural"]))
            marks = [x for x in other_ph if _COUNT.fullmatch(x)] or (
                [x for x in other_ph if re.fullmatch(r"%(\d+\$)?s|%\(\w+\)[sd]", x)] if len(other_ph) == 1 else [])
            for i, nums in sorted(slots.items()):
                form = e.get(f"msgstr[{i}]")
                if not form:
                    problems.append(f"msgstr[{i}] is empty")
                    continue
                p = check(e["msgid"] if 1 in nums else e["msgid_plural"], form, lang, keep, numbers=False)
                # a form may show the count where English spells it out ("One habit" -> "%d привычка"), and a form
                # for a single number may leave it out (Arabic "two" says it with the dual)
                p = [x for x in p if not (x.startswith("added ") and all(ph in other_ph for ph in x[6:].split(", ")))]
                p = [x for x in p if not (x.startswith("lost ") and len(nums) == 1 and x[5:] in marks)]
                if marks and len(nums) >= 2 and not any(mk in form for mk in marks) and not any(x.startswith("lost ") for x in p):
                    p.append(several_numbers_problem(cats[ours(nums[0])], nums, marks[0]))
                problems += [f"msgstr[{i}]: {x}" for x in p]
        if problems:
            out.append((where, problems))
    return out, (done, missing)


def main(argv=None):
    p = argparse.ArgumentParser(description="Check a translated JSON message file against its source, or a translated "
                                            "gettext .po file on its own.")
    p.add_argument("source", help="the source JSON file, or a translated .po file")
    p.add_argument("translated", nargs="?", help="the translated JSON file")
    p.add_argument("--lang", help="the translation's language code (translation_checks.LANGS); a .po file's "
                                  "Language: header is used when it is not given")
    p.add_argument("--keep", default="", help="names that must stay as written, comma-separated")
    p.add_argument("--no-numbers", action="store_true", help="do not compare the numbers of each string")
    p.add_argument("--version", action="version", version=f"translation-checks {__version__}")
    a = p.parse_args(argv)
    keep = [k.strip() for k in a.keep.split(",") if k.strip()]
    if a.translated is None and a.source.endswith(".po"):
        with open(a.source, encoding="utf-8-sig") as fh:
            text = fh.read()
        lang = a.lang or po_language(text)
        if lang not in LANGS or lang == "en":
            print(f"no target language for {a.source}: give --lang (known: {', '.join(ALL)})", file=sys.stderr)
            return 2
        problems, (done, missing) = check_po(text, lang, keep, numbers=not a.no_numbers)
        for where, ps in problems:
            print(f"  {where}: {'; '.join(ps)}")
        bad = sum(1 for where, _ in problems if where != "Plural-Forms")
        print(f"{done} translated {'entry' if done == 1 else 'entries'} ({name(lang)}): {done - bad} fine, {bad} with problems, {missing} not "
              f"translated" + ("; the Plural-Forms header is wrong" if any(w == "Plural-Forms" for w, _ in problems) else ""))
        return 1 if problems else 0
    if a.translated is None or not a.lang:
        p.error("a JSON check needs the source, the translated file and --lang")
    if a.lang not in LANGS:
        print(f"unknown language {a.lang!r}; known: {', '.join(LANGS)}", file=sys.stderr)
        return 2
    with open(a.source, encoding="utf-8-sig") as fh:
        src = dict(_flatten(json.load(fh)))
    with open(a.translated, encoding="utf-8-sig") as fh:
        dst = dict(_flatten(json.load(fh)))
    bad = 0
    for key, text in src.items():
        if key not in dst:
            continue
        problems = check(text, dst[key], a.lang, keep, numbers=not a.no_numbers)
        if problems:
            bad += 1
            print(f"  {key}: {'; '.join(problems)}")
    missing = [k for k in src if k not in dst]
    print(f"{len(src)} strings: {len(src) - bad - len(missing)} fine, {bad} with problems, {len(missing)} missing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
