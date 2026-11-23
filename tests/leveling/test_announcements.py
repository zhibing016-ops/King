import unittest
from systems.leveling.announcements import validate_template, render_announcement

class AnnouncementTests(unittest.TestCase):
    def test_template(self):
        self.assertEqual(validate_template("Olá {mention}, nível {level}"), "Olá {mention}, nível {level}")
    def test_invalid(self):
        for template in ("", "{everyone}", "{mention", "{level.__class__}"):
            with self.assertRaises(ValueError): validate_template(template)
    def test_render(self):
        self.assertEqual(render_announcement("{member} {level} {previous_level} {guild}", member_name="Ana", member_id=123, level=4, previous_level=3, guild_name="Teste"), "Ana 4 3 Teste")
