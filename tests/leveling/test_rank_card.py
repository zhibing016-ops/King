import unittest
from io import BytesIO
from systems.leveling.ranking import member_position, ranked_members
from systems.leveling.cards.rank_card import make_rank_card

class RankTests(unittest.TestCase):
    def test_ranking_and_tie(self):
        data = {"members": {"9": {"xp": 100}, "3": {"xp": 100}, "2": {"xp": 50}}}
        self.assertEqual(ranked_members(data), [(3, 100), (9, 100), (2, 50)])
        self.assertEqual(member_position(data, 9), 2)
        self.assertIsNone(member_position(data, 4))

    def test_png(self):
        card = make_rank_card("Membro", 1200, 3)
        self.assertIsInstance(card, BytesIO)
        self.assertEqual(card.read(8), b"\x89PNG\r\n\x1a\n")

if __name__ == "__main__":
    unittest.main()
