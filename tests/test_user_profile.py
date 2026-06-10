import unittest

from core.user_profile import normalize_user_profile, profile_initials


class UserProfileTests(unittest.TestCase):
    def test_normalize_user_profile_keeps_known_string_fields(self) -> None:
        profile = normalize_user_profile(
            {
                "display_name": "  Justin Forge  ",
                "email": " justin@example.com ",
                "role": " Technical Artist ",
                "studio": 42,
                "unknown": "ignored",
            }
        )

        self.assertEqual(profile["display_name"], "Justin Forge")
        self.assertEqual(profile["email"], "justin@example.com")
        self.assertEqual(profile["role"], "Technical Artist")
        self.assertEqual(profile["studio"], "")
        self.assertNotIn("unknown", profile)

    def test_profile_initials_uses_first_and_last_words(self) -> None:
        self.assertEqual(profile_initials({"display_name": "Justin Forge"}), "JF")
        self.assertEqual(profile_initials({"display_name": "Skyforge"}), "SK")
        self.assertEqual(profile_initials({}), "SF")


if __name__ == "__main__":
    unittest.main()
