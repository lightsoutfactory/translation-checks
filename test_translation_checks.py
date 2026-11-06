"""translation-checks tests.  python3 -m unittest test_translation_checks"""
import gettext
import io
import json
import os
import re
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



class TestRealFiles(unittest.TestCase):
    """What Django's own .po files (human translations, 39 of these languages) showed us to accept"""
    def test_names_units_and_code_copied_from_the_source(self):
        for src, out, lang in (("URL", "URL", "ja"), ("%s KB", "%s KB", "th"), ("IPv4", "IPv4", "ko"), ("salt", "salt", "ar"),
                               ("Boolean (Either True or False)", "ブール値 (True または False)", "ja"),
                               ("PostgreSQL extensions", "PostgreSQL разширения", "bg"), ("A JSON object", "JSON对象", "zh-cn"),
                               ("IPv4 or IPv6", "IPv4またはIPv6", "ja"), ("email address", "Email адреса", "mk"),
                               ("Example: “/about/contact/”. Make sure to have leading and trailing slashes.",
                                "例如：“/about/contact/”。确保有开头和结尾的斜杠。", "zh-cn"),
                               ("%(value).1f million", "%(value).1f милион", "mk")):
            self.assertEqual(t.check(src, out, lang), [], (src, lang))
        # still caught: English left in place, around a few translated words or all of it
        self.assertIn("only 59% of the letters are in cyrillic script",
                      t.check("Your changes are saved and will sync later", "Your changes are saved и будут синхронизированы", "ru"))
        self.assertIn("not translated", t.check("Save changes", "Save changes", "ru"))
        self.assertEqual(t.check("%(value).1f million", "%(value)s милион", "mk"), ["lost %(value).1f", "added %(value)s"])

    def test_times_dates_and_words_for_numbers(self):
        for src, out, lang in (("6 a.m.", "06.00", "fi"), ("6 p.m.", "18.00", "fi"), ("Opens at 3 pm", "Öffnet um 15:00", "de"),
                               ("Opens at 3:30 pm", "Öffnet um 15:30", "de"), ("Feb.", "2月", "ja"), ("dec", "12월", "ko"),
                               ("Thursday", "Thứ 5", "vi"), ("The table shows the twelfth month.", "表は12ヶ月目を示します。", "ja"),
                               ("It wins in about one-fifth of cases.", "약 20%의 경우에서 승리합니다.", "ko"),
                               ("spouses more than a decade younger", "10歳以上年下の配偶者", "ja"),
                               ("See https://example.com/path for more", "Siehe „https://example.com/path“ für mehr", "de")):
            self.assertEqual(t.check(src, out, lang), [], (src, lang))
        self.assertTrue(t.check("Scratches mar the finish", "Кратки драскотини 3", "bg"), "mar is a month only on its own")
        self.assertTrue(t.check("Price 0.5", "Цена 5", "ru"))

RU_PO = """msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"
"Language: ru\\n"
"Plural-Forms: {rule}\\n"

msgid "Save changes"
msgstr "Сохранить изменения"

msgid "One habit missed"
msgid_plural "%(n)s habits missed"
{forms}
"""
RU_RULE = t.gettext_plural("ru")[0]
RU_FORMS = 'msgstr[0] "Пропущена %(n)s привычка"\nmsgstr[1] "Пропущено %(n)s привычки"\nmsgstr[2] "Пропущено %(n)s привычек"'


class TestGettext(unittest.TestCase):
    def test_every_rule_matches_cldr(self):
        for code in t.ALL:
            rule, cats = t.gettext_plural(code)
            m = re.fullmatch(r"nplurals=(\d+); plural=(.+);", rule)
            self.assertEqual(int(m.group(1)), len(cats), code)
            pick = gettext.c2py(m.group(2))
            for cat in t.plural_categories(code):
                for n in t.plural_numbers(code, cat):
                    want = "other" if cat == "many" and code in ("es", "fr", "it", "pt") else cat
                    self.assertEqual(cats[pick(n)], want, (code, n))

    def test_a_good_file(self):
        problems, counts = t.check_po(RU_PO.format(rule=RU_RULE, forms=RU_FORMS), "ru")
        self.assertEqual((problems, counts), ([], (2, 0)))

    def test_a_rule_that_mixes_forms(self):
        problems, _ = t.check_po(RU_PO.format(rule="nplurals=2; plural=(n != 1);",
                                              forms='msgstr[0] "%(n)s привычка"\nmsgstr[1] "%(n)s привычек"'), "ru")
        header = dict(problems)["Plural-Forms"][0]
        self.assertIn("msgstr[1] serves numbers that Russian gives different forms (many: 0, 5, 6, 7...; few: 2, 3, "
                      "4, 22...; one: 21, 31, 41, 51...)", header)
        problems, _ = t.check_po(RU_PO.format(rule="nplurals=3; plural=(n != 1);", forms=RU_FORMS), "ru")
        self.assertIn("msgstr[1] serves", dict(problems)["Plural-Forms"][0])
        # an older Romanian rule: 101 goes with 20 ("de"), where current CLDR puts it with 2-19
        ro = RU_PO.replace("Language: ru", "Language: ro").format(
            rule="nplurals=3; plural=(n == 1) ? 0 : ((n == 0 || n % 100 >= 2 && n % 100 <= 19) ? 1 : 2);",
            forms='msgstr[0] "Un obicei ratat"\nmsgstr[1] "%(n)s obiceiuri ratate"\nmsgstr[2] "%(n)s de obiceiuri ratate"')
        self.assertIn("few: 101", dict(t.check_po(ro, "ro")[0])["Plural-Forms"][0])

    def test_plural_entries(self):
        po = RU_PO.format(rule=RU_RULE, forms='msgstr[0] "Пропущена одна привычка"\nmsgstr[1] "Пропущено %(n)s привычки"')
        problems = dict(t.check_po(po, "ru")[0])["One habit missed"]
        self.assertIn("2 msgstr forms, but Plural-Forms has 3", problems)
        self.assertIn("msgstr[2] is empty", problems)
        self.assertTrue(any("the one form is used for 1, 21, 31, 41..." in x for x in problems), problems)
        ar = RU_PO.replace("Language: ru", "Language: ar").format(rule=t.gettext_plural("ar")[0], forms="\n".join(
            f'msgstr[{i}] "{x}"' for i, x in enumerate(["لا عادات مفوّتة", "عادة واحدة مفوّتة", "عادتان مفوّتتان",
                                                         "%(n)s عادات مفوّتة", "%(n)s عادةً مفوّتة", "%(n)s عادة مفوّتة"])))
        self.assertEqual(dict(t.check_po(ar.replace('msgstr "Сохранить изменения"', 'msgstr "حفظ التغييرات"'), "ar")[0]),
                         {}, "zero and two are one number each and may leave it out")

    def test_cli_on_a_po_file(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "ru.po")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(RU_PO.format(rule="nplurals=2; plural=(n != 1);",
                                  forms='msgstr[0] "%(n)s привычка"\nmsgstr[1] "%(n)s привычек"'))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(t.main([path]), 1, "the language comes from the header")
        self.assertIn("2 translated entries (Russian): 2 fine, 0 with problems, 0 not translated; the Plural-Forms "
                      "header is wrong", out.getvalue())
        self.assertEqual(t.po_language('msgid ""\nmsgstr "Language: pt_BR\\n"\n'), "pt")
        self.assertEqual(t.po_language('msgid ""\nmsgstr "Language: nb\\n"\n'), "no")
        self.assertEqual(t.po_language('msgid ""\nmsgstr "Language: de_DE\\n"\n'), "de")

if __name__ == "__main__":
    unittest.main()
