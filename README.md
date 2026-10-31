# translation-checks

Catch the translations that would break your app, before your users do. One Python file, no dependencies. Use it on
machine translations, on what a translation service sent back, or in CI.

```sh
python3 translation_checks.py locales/en.json locales/de.json --lang de --keep "Habit Garden,Pro"
```

```python
from translation_checks import check
check("Hello, {name}!", "Hallo!", "de")          # ['lost {name}']
check("Save changes", "Save changes", "ru")      # ['only 0% of the letters are in cyrillic script', 'not translated']
```

## What it checks, per string

- **Placeholders come back exactly:** printf (`%s`, `%1$s`, `%.2f`, `%(name)s`), braces (`{name}`, `{0}`,
  `{{count}}`, `${name}`), `:name`, HTML and XML tags with their attributes, line breaks, URLs, e-mail addresses,
  inline code and Markdown link targets. Nothing lost, nothing invented.
- **ICU messages** (`{count, plural, one{...} other{...}}`) keep their variables. The number of branches may differ,
  since Russian needs one, few, many and other, and Arabic six forms.
- **Names you keep** (your product, brands) are still there as written.
- **The right script:** at least 60% of the letters in Cyrillic, Arabic, Hebrew, Greek, Armenian, Ethiopic, CJK,
  Hangul, Thai, Khmer, Kannada or Gurmukhi for the languages written in them. That catches English left in place.
- **Not left in English:** two or more words identical to the source fail. A single identical word is allowed, since
  loanwords are often right ("Backups" in German).
- **Not empty and not runaway:** at most 4 times the source's length plus 20 characters.

43 languages, with their scripts and CLDR plural categories, are in `LANGS`.

## What it cannot check

Meaning. In our own test run a model translated "You are offline" into well-formed Khmer that says "you are online",
and every check above passed it. Have someone who reads the language look at the strings that matter most.

## Where these checks come from

They guard every string in **[Polyglot](https://lightsoutfactory.ai/kits/polyglot/)**, which does the translating:
JSON, Flutter ARB, Android `strings.xml`, Apple `.strings`, gettext and Markdown into 42 languages with your own
model, a failed string asked for again with its problem named, real plural forms and a translation memory. Three of
these rules were fixed after a live run; that story is in the
[field notes](https://lightsoutfactory.ai/field-notes/translation-checks-were-wrong/).

MIT licence. `python3 -m unittest test_translation_checks` runs the tests.
