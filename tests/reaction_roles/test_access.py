import unittest
from types import SimpleNamespace
from systems.reaction_roles.services.access import can_change, access_policy

class AccessTests(unittest.TestCase):
    def member(self, *roles, user=99):
        return SimpleNamespace(id=user, roles=[SimpleNamespace(id=x) for x in roles])
    def test_default(self):
        self.assertTrue(can_change({}, self.member())[0])
    def test_required_any(self):
        panel={"access":{"required_roles":["1","2"]}}
        self.assertTrue(can_change(panel,self.member(2))[0])
        self.assertFalse(can_change(panel,self.member(3))[0])
    def test_required_all(self):
        panel={"access":{"required_roles":["1","2"],"require_all":True}}
        self.assertFalse(can_change(panel,self.member(1))[0])
        self.assertTrue(can_change(panel,self.member(1,2))[0])
    def test_blocked(self):
        self.assertFalse(can_change({"access":{"blocked_roles":["3"]}},self.member(3))[0])
    def test_allowed_user(self):
        self.assertFalse(can_change({"access":{"allowed_users":["88"]}},self.member())[0])
    def test_blocked_user(self):
        self.assertFalse(can_change({"access":{"blocked_users":["99"]}},self.member())[0])
    def test_revoke(self):
        self.assertFalse(can_change({"access":{"allow_remove":False}},self.member(),"revoke")[0])
    def test_invalid(self):
        with self.assertRaises(ValueError):
            access_policy({"access":{"required_roles":["abc"]}})
