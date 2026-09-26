import unittest

from saylo.config import LANGUAGES, VOICES, voices_for
from saylo.decide import (
    InputError,
    action_for,
    clean_input,
    clean_translation,
    jev_criteria,
    jev_prompt,
    translate_prompt,
)


class DecideTests(unittest.TestCase):
    def test_jev_prompt_is_the_one_line_check(self) -> None:
        self.assertEqual(
            jev_prompt("english"),
            "is this text is fully english or other language is in there?",
        )
        self.assertEqual(set(jev_criteria("spanish")), {"spanish", "other"})

    def test_english_text_is_spoken_without_translation(self) -> None:
        self.assertEqual(action_for("english", "english"), "speak")

    def test_other_language_is_translated(self) -> None:
        self.assertEqual(action_for("other", "spanish"), "translate")

    def test_unexpected_jev_choice_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            action_for("french", "english")

    def test_input_limit(self) -> None:
        self.assertEqual(clean_input("  hello  "), "hello")
        with self.assertRaises(InputError):
            clean_input("   ")
        with self.assertRaises(InputError):
            clean_input("x" * 501)

    def test_translation_strips_wrapping_quotes(self) -> None:
        self.assertEqual(clean_translation('"hola"'), "hola")

    def test_english_accents_share_one_language_check(self) -> None:
        self.assertEqual(voices_for("en"), ["en-us", "en-gb"])
        self.assertEqual(voices_for("es"), ["es"])
        self.assertEqual(LANGUAGES["en"]["jev_name"], "english")
        self.assertEqual(LANGUAGES["es"]["jev_name"], "spanish")
        self.assertEqual(VOICES["en-gb"]["lang_code"], "b")
        self.assertEqual(VOICES["es"]["voice"], "ef_dora")

    def test_translate_prompt_names_the_target(self) -> None:
        self.assertEqual(
            translate_prompt("Spanish"),
            "Translate the text into Spanish. Return only the translation.",
        )


if __name__ == "__main__":
    unittest.main()
