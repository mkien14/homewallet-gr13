import copy
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr

from handler import SUBJECTS, handler


class MessageTests(unittest.TestCase):
    def event(self, source="CustomMessage_SignUp", locale="vi"):
        return {
            "triggerSource": source,
            "request": {
                "codeParameter": "{TEST_CODE}",
                "usernameParameter": "{TEST_USERNAME}",
                "userAttributes": {"custom:preferred_locale": locale},
            },
            "response": {"smsMessage": "unchanged"},
        }

    def test_supported_triggers_and_locales_preserve_placeholders(self):
        for source, subjects in SUBJECTS.items():
            for locale in ("vi", "en"):
                with self.subTest(source=source, locale=locale):
                    event = self.event(source, locale)
                    request = copy.deepcopy(event["request"])
                    result = handler(event, None)
                    self.assertIs(result, event)
                    self.assertEqual(result["request"], request)
                    self.assertIn(subjects[int(locale == "en")], result["response"]["emailSubject"])
                    self.assertIn("{TEST_CODE}", result["response"]["emailMessage"])
                    self.assertEqual(result["response"]["smsMessage"], "unchanged")
                    if source == "CustomMessage_AdminCreateUser":
                        self.assertIn("{TEST_USERNAME}", result["response"]["emailMessage"])

    def test_invalid_or_missing_locale_falls_back_to_vietnamese(self):
        for locale in (None, "", "xx", "EN"):
            event = self.event(locale=locale)
            if locale is None:
                event["request"]["userAttributes"].clear()
            self.assertIn("Xác minh", handler(event, None)["response"]["emailSubject"])

    def test_unsupported_trigger_or_missing_placeholder_is_unchanged(self):
        cases = [self.event("Unknown"), self.event(), self.event("CustomMessage_AdminCreateUser")]
        cases[1]["request"].pop("codeParameter")
        cases[2]["request"].pop("usernameParameter")
        for event in cases:
            expected = copy.deepcopy(event)
            self.assertEqual(handler(event, None), expected)

    def test_no_stdout_or_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            handler(self.event(), None)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
