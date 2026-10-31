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


if __name__ == "__main__":
    unittest.main()
