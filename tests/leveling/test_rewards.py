import unittest
from systems.leveling.rewards import reward_changes, desired_roles

class RewardTests(unittest.TestCase):
    def test_stack(self):
        config = {"rewards": {"1": 11, "3": 33}, "reward_mode": "stack"}
        self.assertEqual(desired_roles(config, 3), {11, 33})
        self.assertEqual(reward_changes(config, 900, [11]), ({33}, set()))
    def test_replace(self):
        config = {"rewards": {"1": 11, "3": 33}, "reward_mode": "replace"}
        self.assertEqual(reward_changes(config, 900, [11]), ({33}, {11}))
    def test_unrelated_role_untouched(self):
        config = {"rewards": {"1": 11}, "reward_mode": "replace"}
        self.assertEqual(reward_changes(config, 0, [11, 99]), (set(), {11}))
if __name__ == "__main__": unittest.main()
