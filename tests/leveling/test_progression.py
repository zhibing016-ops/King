import unittest
from systems.leveling.progression import progress_from_xp, progress_bar
from systems.leveling.level_calculator import xp_for_level

class ProgressionTests(unittest.TestCase):
    def test_boundaries(self):
        for level in range(0, 101):
            data = progress_from_xp(xp_for_level(level))
            self.assertEqual(data["level"], level)
            self.assertEqual(data["current_level_xp"], 0)
            self.assertEqual(data["remaining_xp"], 100 * (2 * level + 1))
    def test_midlevel(self):
        data = progress_from_xp(250)
        self.assertEqual((data["level"], data["remaining_xp"]), (1, 150))
        self.assertEqual(data["percent"], 50)
    def test_invalid(self):
        with self.assertRaises(ValueError): progress_from_xp(-1)
    def test_bar(self):
        self.assertEqual(progress_bar(5, 10, 10), "▰"*5 + "▱"*5)

if __name__ == "__main__": unittest.main()
