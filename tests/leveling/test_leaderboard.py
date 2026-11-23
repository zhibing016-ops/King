import unittest
from systems.leveling.leaderboard import leaderboard_page, position_summary

class TestLeaderboard(unittest.TestCase):
    def setUp(self):
        self.data = {"members": {str(i): {"xp": 100-i} for i in range(1, 24)}}

    def test_pagination(self):
        first = leaderboard_page(self.data)
        self.assertEqual((first["page"], first["pages"], len(first["rows"])), (1, 3, 10))
        self.assertEqual(first["rows"][0], (1, 1, 99))
        self.assertEqual(len(leaderboard_page(self.data, 3)["rows"]), 3)

    def test_clamp(self):
        self.assertEqual(leaderboard_page(self.data, 999)["page"], 3)
        self.assertEqual(leaderboard_page(self.data, -2)["page"], 1)

    def test_position(self):
        self.assertEqual(position_summary(self.data, 12)["position"], 12)
        self.assertIsNone(position_summary(self.data, 999)["position"])

    def test_empty(self):
        self.assertEqual(leaderboard_page({"members": {}})["pages"], 1)

if __name__ == "__main__": unittest.main()
