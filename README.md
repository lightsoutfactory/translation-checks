# translation-checks

Catch the translations that would break your app, before your users do. One Python file, no dependencies. Use it on
machine translations, on what a translation service sent back, or in CI.

```sh
python3 translation_checks.py locales/en.json locales/de.json --lang de --keep "Habit Garden,Pro"
```

```python
from translation_checks import check
check("Hello, {name}!", "Hallo!", "de")              # ['lost {name}']
check("Free for 14 days", "41 Tage kostenlos", "de")  # ['numbers changed: lost 14; added 41']
check("Planted values show up.", "Apar valori植入.", "ro")
# ['letters of another script than Romanian: 入植']
```

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
  separators (1,000 = 1.000 = 1 000). What the source says in words may come back in digits: "ten rounds" as 10,
  "July 2026" as 2026年7月, "3 million" as 300万 or 300만, "3 pm" as 15:00, "half the time" as 50%. A lone 1 may
  become a word. `--no-numbers` (or `numbers=False`) turns this off; ICU messages skip it.
- **No letters of another script:** a model that slips into Chinese for one word ("valori植入" in Romanian), writes
  Thai on a Khmer page, or types a Cyrillic "о" inside a Finnish word. Letters the source has, and Latin letters, are
  always allowed. Chinese, Japanese and Korean are not checked; Serbian and Punjabi only for Chinese, Japanese and
  Korean letters.
- **Names you keep** (your product, brands) are still there as written, where the source has them as words
  ("Pressing" does not contain the name "Press"). A translation may join a name into a compound: "Store-Dock-Kits".
- **The right script:** at least 60% of the letters in Cyrillic, Arabic, Hebrew, Greek, Armenian, Ethiopic, CJK,
  Hangul, Thai, Khmer, Kannada or Gurmukhi for the languages written in them. That catches English left in place.
- **Not left in English:** two or more words identical to the source fail. A single identical word is allowed, since
  loanwords are often right ("Backups" in German).
- **Not empty and not runaway:** at most 4 times the source's length plus 20 characters.

43 languages, with their scripts and CLDR plural categories, are in `LANGS`.

## Measured

On the sites we run, every translation goes through checks like these before it is published. Against that record:

- **False alarms:** 0 among the 568,574 page translations those checks accepted, in 42 languages, and 0 among the
  897 ICU plural translations in Android's own framework strings (android-36, 39 of these languages).
- **Letters of another script:** caught in all 1,652 translations our checks refused for them.
- **Numbers:** caught in 66,768 of the 73,404 translations refused over numbers. Of the rest, 6,503 were refusals our
  own checks have since stopped making (Japanese 300万 for "3 million", 0時 for "midnight"), and 133 are ones this
  tool reads as the same number, such as "4pm" as 16h and Persian thousands separators.

## What it cannot check

Meaning. In our own test run a model translated "You are offline" into well-formed Khmer that says "you are online",
and every check above passed it. Have someone who reads the language look at the strings that matter most.

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
