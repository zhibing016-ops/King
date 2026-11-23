import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.modes import panel_mode, role_action, set_mode

class ModeTests(unittest.TestCase):
    def test_actions(self):
        self.assertEqual(role_action({}, True), "grant")
        self.assertEqual(role_action({}, False), "revoke")
        self.assertEqual(role_action({"reversed": True}, True), "revoke")
        self.assertEqual(role_action({"reversed": True}, False), "grant")
        self.assertEqual(role_action({"binding": True}, False), None)
        self.assertEqual(role_action({"verify": True}, False), None)

    def test_persistence_and_exclusivity(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                await store.initialize(123)
                await store.mutate(123, lambda d: d['panels'].update({'abc': {'title':'Teste','roles':{'🎮':'456'}}}))
                p = await set_mode(store, 123, 'abc', 'reversed')
                self.assertEqual(panel_mode(p), 'reversed')
                p = await set_mode(store, 123, 'abc', 'binding')
                self.assertEqual(panel_mode(p), 'binding')
                self.assertFalse(p['reversed'])
                self.assertTrue((await store.get(123))['panels']['abc']['binding'])
                await store.mutate(123, lambda d: d['panels']['abc'].update(unique=True))
                with self.assertRaises(ValueError):
                    await set_mode(store, 123, 'abc', 'reversed')
        asyncio.run(run())

    def test_requires_mapping(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                await store.mutate(456, lambda d: d['panels'].update({'abc': {'title':'Vazio','roles':{}}}))
                with self.assertRaises(ValueError):
                    await set_mode(store, 456, 'abc', 'binding')
        asyncio.run(run())
