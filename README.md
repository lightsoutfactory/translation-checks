# translation-checks

Catch the translations that would break your app, before your users do. One Python file, no dependencies. Use it on
machine translations, on what a translation service sent back, or in CI.

```sh
python3 translation_checks.py locales/en.json locales/de.json --lang de --keep "Habit Garden,Pro"
python3 translation_checks.py locale/ru/LC_MESSAGES/app.po          # a gettext file, with its plural rule
```

```python
from translation_checks import check
check("Hello, {name}!", "Hallo!", "de")              # ['lost {name}']
check("Free for 14 days", "41 Tage kostenlos", "de")  # ['numbers changed: lost 14; added 41']
check("Planted values show up.", "Apar valori植入.", "ro")
# ['letters of another script than Romanian: 入植']
```

## Install

```sh
pip install git+https://github.com/lightsoutfactory/translation-checks
translation-checks locales/en.json locales/de.json --lang de
```

Or copy `translation_checks.py` into your project: it is one file with no dependencies.

## What it checks, per string

- **Placeholders come back exactly:** printf (`%s`, `%1$s`, `%.2f`, `%(name)s`), braces (`{name}`, `{0}`,
  `{{count}}`, `${name}`), `:name`, HTML and XML tags with their attributes, line breaks, URLs, e-mail addresses,
  inline code and Markdown link targets. Nothing lost, nothing invented.
- **ICU messages** (`{count, plural, one{...} other{...}}`) keep their variables. The number of branches may differ,
  since Russian needs one, few, many and other, and Arabic six forms.
- **Plural forms that cover several numbers show the number.** Russian "one" is also 21 and 31, French "one" is also
  0 (CLDR). So `one{One day left}` must become `one{Остался # день}`, not "один день", which a user with 21 days left
  would see; German "one" is only 1 and may say "ein Tag". Checked when the English "other" branch shows the number,
  with `=N` branches taken into account.
- **Numbers come back:** every number written in digits, in any digits (`٣` and `３` are 3) and with the target's
  separators (1,000 = 1.000 = 1 000; 06 is 6). What the source says in words may come back in digits: "ten rounds" as
  10, "July 2026" as 2026年7月, "3 million" as 300万 or 300만, "3 pm" as 15:00, "half the time" as 50%, "the twelfth
  month" as 12ヶ月目, "a decade" as 10, "Feb." as 2月. A lone 1 may become a word. `--no-numbers` (or
  `numbers=False`) turns this off; ICU messages skip it.
- **No letters of another script:** a model that slips into Chinese for one word ("valori植入" in Romanian), writes
  Thai on a Khmer page, or types a Cyrillic "о" inside a Finnish word. Letters the source has, and Latin letters, are
  always allowed. Chinese, Japanese and Korean are not checked; Serbian and Punjabi only for Chinese, Japanese and
  Korean letters.
- **Names you keep** (your product, brands) are still there as written, where the source has them as words
  ("Pressing" does not contain the name "Press"). A translation may join a name into a compound: "Store-Dock-Kits".
- **The right script:** at least 60% of the letters in Cyrillic, Arabic, Hebrew, Greek, Armenian, Ethiopic, CJK,
  Hangul, Thai, Khmer, Kannada or Gurmukhi for the languages written in them. That catches English left in place.
  Names, code and paths copied from the source (PostgreSQL, True, `flatpages/default.html`) do not count, and a
  single word or unit kept as it is (URL, IPv4, `%s KB`) passes.
- **Not left in English:** two or more words identical to the source fail. A single identical word is allowed, since
  loanwords are often right ("Backups" in German).
- **Not empty and not runaway:** at most 4 times the source's length plus 20 characters.

43 languages, with their scripts and CLDR plural categories, are in `LANGS`.

## gettext files

A translated `.po` file is checked on its own, its msgids being the source:

```sh
translation-checks locale/ru/LC_MESSAGES/app.po      # the language comes from its Language: header, or give --lang
```

- **The Plural-Forms rule.** The header's formula picks the msgstr slot for a number, and every number from 0 to 1000
  must land in a slot that CLDR gives a single form. A Russian file with `nplurals=2; plural=(n != 1);` puts 2, 5 and
  21 in one slot, where Russian says "2 привычки", "5 привычек" and "21 привычка"; the check names the numbers that
  clash and the rule to use. The rules for all 42 languages, checked against CLDR for every number from 0 to 10,000,
  are in `GETTEXT_PLURALS`, and a [field note](https://lightsoutfactory.ai/field-notes/gettext-plural-forms/) shows
  them in a table.
- **Every plural entry** has a msgstr for each slot, none of them empty. Each form passes the checks above against
  msgid or msgid_plural; a slot used for several numbers shows the number (`%d`, `%(n)s`, `{count}`), and a slot for a
  single number may leave it out (Arabic says "two" with the dual).
- Every other translated entry is checked like a JSON string. Untranslated entries are counted, not flagged.

## Measured

On the sites we run, every translation goes through checks like these before it is published. Against that record:

- **False alarms:** 0 among the 576,162 page translations those checks accepted, in 42 languages, and 0 among the
  897 ICU plural translations in Android's own framework strings (android-36, 39 of these languages).
- **On someone else's files:** Django 5.2's own `.po` files in 39 of these languages, translated by people: 31,879
  translated entries, 475 flagged (1.5%). By kind: 234 plural entries whose number of forms does not match their
  file's Plural-Forms (the Spanish, French, Italian and Portuguese headers say two forms where the entries carry
  three, the Hebrew header four where they carry three); 125 with English left in place (Thai "log entry", Greek "work
  factor"); 78 with a placeholder, tag or line break changed; 28 with numbers that differ, among them numbers the
  translator wrote in words (Arabic "the past seven days"), which this check does not accept; 6 forms for several
  numbers without the number; 4 with letters of another script (a Thai letter in the Khmer word for "Russian"). The
  Armenian, Punjabi and Turkish files' Plural-Forms give 0 a different form than CLDR does. Those files also taught it
  what to accept: names and code copied into a translation (PostgreSQL, True, JSON), units and abbreviations left as
  they are (URL, IPv4, `%s KB`), whole hours as 18:00, calendar abbreviations as numbers (Feb. as 2月) and ordinals as
  digits (the twelfth month as 12ヶ月目).
- **Letters of another script:** caught in all 5,121 translations our checks refused for them.
- **Numbers:** caught in 69,924 of the 83,350 translations our checks refused over numbers. Version 1.3.0 lets 6,782
  of them through that 1.2.0 caught; we read them by kind, and they are the same numbers written in a way our sites'
  own checks do not know: ordinals and fractions in digits ("the twelfth month" as 12ヶ月目, "one-fifth" as 1/5 or 20%),
  a decade as 10, a time as 17:00, a date with its leading zero.

## What it cannot check

Meaning. In our own test run a model translated "You are offline" into well-formed Khmer that says "you are online",
and every check above passed it. Polyglot 1.3.0 has the model read each translation again for exactly this; on our
store's own pages that second reading found a Czech refund answer that said the opposite of the English
([field note](https://lightsoutfactory.ai/field-notes/read-for-meaning/)). It misses things too, so have someone who
reads the language look at the strings that matter most.

## Where these checks come from

They guard every string in **[Polyglot](https://lightsoutfactory.ai/kits/polyglot/)**, which does the translating:
JSON, Flutter ARB, Android `strings.xml`, Apple `.strings`, gettext and Markdown into 42 languages with your own
model, a failed string asked for again with its problem named, real plural forms and a translation memory. Three of
these rules were fixed after a live run; that story is in the
[field notes](https://lightsoutfactory.ai/field-notes/translation-checks-were-wrong/).

Also free from us: [bot-gate](https://github.com/lightsoutfactory/bot-gate) (keep pages up for people during a scraper
flood), [cloudflare-free-shield](https://github.com/lightsoutfactory/cloudflare-free-shield) (three Cloudflare
Free-plan rules against scraper floods) and [vllm-health](https://github.com/lightsoutfactory/vllm-health) (a vLLM
health check that never waits in the queue).

MIT licence. `python3 -m unittest test_translation_checks` runs the tests.
