"""translation-checks tests.  python3 -m unittest test_translation_checks"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import translation_checks as t


class TestChecks(unittest.TestCase):
    def test_placeholders_tags_breaks(self):
        self.assertEqual(t.check("Hello, {name}!", "Hallo, {name}!", "de"), [])
        self.assertEqual(t.check("%1$s of %2$d", "%2$d von %1$s", "de"), [])
        self.assertIn("added", t.check("Save", "Speichern %s", "de")[0])
        self.assertTrue(t.check('Read <a href="/t">terms</a>', "Lesen Sie AGB", "de"))
        self.assertEqual(t.check("Line one\\nLine two", "Zeile eins\\nZeile zwei", "de"), [])
        self.assertEqual(t.check("Is 100% sure", "Ist zu 100 % sicher", "de"), [])

    def test_script_kept_names_identity(self):
        self.assertIn("cyrillic", t.check("Save changes", "Save changes", "ru")[0])
        self.assertEqual(t.check("Open Habit Garden", "Открыть Habit Garden", "ru", keep=["Habit Garden"]), [])
        self.assertIn("changed Habit Garden", t.check("Open Habit Garden", "Открыть Сад", "ru", keep=["Habit Garden"])[0])
        self.assertEqual(t.check("Backups", "Backups", "de"), [], "a loanword may stay")
        self.assertIn("not translated", t.check("Save changes", "Save changes", "de"))

    def test_email_and_icu(self):
        line = "Questions? Write to support" + "@" + "example.com."
        self.assertEqual(t.check(line, "Вопросы? Пишите на support" + "@" + "example.com.", "ru"), [])
        src = "{count, plural, =0{None} one{{count} day} other{{count} days}}"
        self.assertEqual(t.check(src, "{count, plural, =0{連続記録なし} other{{count}日連続}}", "ja", icu=True), [])
        ru = "{count, plural, =0{Нет} one{{count} день} few{{count} дня} many{{count} дней} other{{count} дня}}"
        self.assertEqual(t.check(src, ru, "ru", icu=True), [])
        self.assertIn("ICU variables changed", t.check(src, "{n, plural, other{{n} дней}}", "ru", icu=True))

    def test_stray_letters(self):
        # the kinds a model produced on our sites: Chinese inside Romanian and Greek, Thai on a Khmer page,
        # Devanagari inside Kannada, a Cyrillic "о" inside a Finnish word
        self.assertIn("letters of another script than Romanian: 入植",
                      t.check("Planted values show up.", "Apar valori植入.", "ro"))
        self.assertIn("letters of another script than Greek: 向面",
                      t.check("A campaign aimed at players", "Μια εκστρατεία面向 στους παίκτες", "el"))
        self.assertTrue(t.stray_letters("Draw results", "លទ្ធផលការចាប់ឆ្នោតจับ", "km"))
        self.assertTrue(t.stray_letters("Restart the service", "ಸೇವೆಯನ್ನು पुनः ಪ್ರಾರಂಭಿಸಿ", "kn"))
        self.assertEqual(t.stray_letters("card case", "korttikotel\u043e", "fi"), "\u043e")
        # fine: Latin names anywhere, kanji in Japanese, letters the source already has, Serbian in its own letters
        self.assertEqual(t.check("Open Habit Garden", "Открыть Habit Garden", "ru", keep=["Habit Garden"]), [])
        self.assertEqual(t.check("Save settings", "設定を保存", "ja"), [])
        self.assertEqual(t.check("Say 你好 to your users", "Sag 你好 zu deinen Nutzern", "de"), [])
        self.assertEqual(t.check("Save", "Сачувај", "sr"), [])
        self.assertEqual(t.check("Größe", "Größe", "de", keep=["Größe"]), [])

    def test_numbers(self):
        self.assertEqual(t.check("Free for 14 days", "14 Tage kostenlos", "de"), [])
        self.assertEqual(t.check("Free for 14 days", "41 Tage kostenlos", "de"), ["numbers changed: lost 14; added 41"])
        self.assertEqual(t.check("Free for 14 days", "Kostenlos testen", "de"), ["numbers changed: lost 14"])
        for lang, out in (("de", "1.000 Credits"), ("fr", "1\u00a0000 crédits"), ("fa", "۱٬۰۰۰ اعتبار"),
                          ("ja", "１，０００クレジット")):
            self.assertEqual(t.check("1,000 credits", out, lang), [], lang)
        self.assertEqual(t.check("4.5 stars", "4,5 Sterne", "de"), [])
        self.assertEqual(t.check("ten rounds", "10 Runden", "de"), [])
        self.assertEqual(t.check("Opens at 3 pm", "Öffnet um 15 Uhr", "de"), [])
        self.assertEqual(t.check("97 of every 100 bets", "97 % der Wetten", "de"), [])
        self.assertEqual(t.check("1 round in 26", "jede 26. Runde", "de"), [])
        self.assertEqual(t.check("Since June 15", "15.6. alkaen", "fi"), [])
        self.assertEqual(t.check("On 30.09.2026", "2026年9月30日に", "ja"), [])
        self.assertEqual(t.check("In July 2026", "2026年7月に", "ja"), [])
        self.assertEqual(t.check("8 gave 109", "thug 8 109", "gd"), [], "two numbers, not 8109")
        self.assertEqual(t.check("$80,000 of other income, 2026", "其他收入$80,000，2026年", "zh-cn"), [])
        # "3 million" is 300万 in Japanese, 300만 in Korean; the value must still be right
        self.assertEqual(t.check("more than 3 million tokens", "300万トークン以上", "ja"), [])
        self.assertEqual(t.check("0.76 and 1.08 million tokens", "76万および108万トークン", "ja"), [])
        self.assertEqual(t.check("more than three million tokens", "300만 개 이상의 토큰", "ko"), [])
        self.assertTrue(t.check("more than 3 million tokens", "30万トークン以上", "ja"))
        # placeholders and ICU branches are not numbers
        self.assertEqual(t.check("%1$s of %2$d", "%2$d von %1$s", "de"), [])
        src = "{count, plural, one{# day} other{# days}} left of 30"
        self.assertEqual(t.check(src, "{count, plural, one{# Tag} other{# Tage}} übrig", "de"), [])
        self.assertEqual(t.check("Free for 14 days", "41 Tage kostenlos", "de", numbers=False), [])

    def test_plural_forms_that_cover_several_numbers(self):
        src = "{count, plural, one{One day left} other{# days left}}"
        # Russian "one" is also 21 and 31: "один день" would be shown to someone with 21 days left
        ru_bad = "{count, plural, one{Остался один день} few{Осталось # дня} many{Осталось # дней} other{Осталось # дня}}"
        self.assertIn("the one form is used for 1, 21, 31, 41..., so it must not say one: write it like the other form, "
                      "with # where the number goes", t.check(src, ru_bad, "ru"))
        ru = "{count, plural, one{Остался # день} few{Осталось # дня} many{Осталось # дней} other{Осталось # дня}}"
        self.assertEqual(t.check(src, ru, "ru"), [])
        # German "one" is only 1; French "one" is 0 and 1, unless 0 has a branch of its own
        self.assertEqual(t.check(src, "{count, plural, one{Noch ein Tag} other{Noch # Tage}}", "de"), [])
        self.assertIn("the one form is used for 0, 1, so it must not say one: write it like the other form, with # where "
                      "the number goes",
                      t.check(src, "{count, plural, one{Un jour restant} other{# jours restants}}", "fr"))
        src0 = "{count, plural, =0{No days left} one{One day left} other{# days left}}"
        fr0 = "{count, plural, =0{Plus aucun jour} one{Un jour restant} other{# jours restants}}"
        self.assertEqual(t.check(src0, fr0, "fr"), [])
        # the variable counts as the number too; an English "other" without the number asks for nothing
        src_var = "{count, plural, one{One file} other{{count} files}}"
        self.assertEqual(t.check(src_var, "{count, plural, one{{count} файл} few{{count} файла} many{{count} файлов} "
                                          "other{{count} файла}}", "ru"), [])
        self.assertEqual(t.check("{count, plural, one{a file} other{files}}",
                                 "{count, plural, one{файл} few{файла} many{файлов} other{файла}}", "ru"), [])
        self.assertEqual(t.plural_numbers("sl", "two"), [2, 102, 202, 302, 402])
        self.assertEqual(t.plural_numbers("fr", "one", explicit={0}), [1])

    def test_kept_names(self):
        self.assertEqual(t.check("Pressing the button", "Drücken der Taste", "de", keep=["Press"]), [])
        self.assertEqual(t.check("Store Dock kits", "Store-Dock-Kits", "de", keep=["Store Dock"]), [])
        self.assertEqual(t.check("Factory Floor runs it", "Factory Floorin ajama", "fi", keep=["Factory Floor"]), [])
        self.assertIn("changed Factory Floor (to be kept as written)",
                      t.check("Factory Floor runs it", "팩토리 플로어가 실행합니다", "ko", keep=["Factory Floor"]))
        self.assertIn("changed LightsOut Factory (to be kept as written)",
                      t.check("About LightsOut Factory", "درباره لایتز‌اوت فکتوری", "fa",
                              keep=["LightsOut", "LightsOut Factory"]))

    def test_cli(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "en.json"), os.path.join(d, "de.json")
        for path, data in ((src, {"a": "Hello, {name}!", "nav": {"b": "Save changes"}}),
                           (dst, {"a": "Hallo!", "nav": {"b": "Änderungen speichern"}})):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        out = io.StringIO()
        with redirect_stdout(out):
            code = t.main([src, dst, "--lang", "de"])
        self.assertEqual(code, 1)
        self.assertIn("a: lost {name}", out.getvalue())
        self.assertIn("2 strings: 1 fine, 1 with problems", out.getvalue())
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump({"a": "Hallo, {name}!", "nav": {"b": "Änderungen speichern"}, "c": "41"}, fh)
        with open(src, "w", encoding="utf-8") as fh:
            json.dump({"a": "Hello, {name}!", "nav": {"b": "Save changes"}, "c": "14"}, fh)
        for flags, code in (([], 1), (["--no-numbers"], 0)):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(t.main([src, dst, "--lang", "de"] + flags), code, flags)


if __name__ == "__main__":
    unittest.main()
