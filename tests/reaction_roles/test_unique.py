import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.unique import set_unique, conflicting_role_ids

class UniqueTests(unittest.TestCase):
    def test_conflicts(self):
        panel = {'unique': True, 'roles': {'🎮': '10', '🎨': '20', '🎵': '30'}}
        self.assertEqual(conflicting_role_ids(panel, 20), {10, 30})
        panel['unique'] = False
        self.assertEqual(conflicting_role_ids(panel, 20), set())

    def test_json_persistence(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                await store.initialize(123)
                await store.mutate(123, lambda d: d['panels'].update({'a': {'id': 'a', 'title': 'Teste', 'roles': {}}}))
                await set_unique(store, 123, 'a', True)
                fresh = GuildJsonStore(Path(tmp))
                self.assertTrue((await fresh.get(123))['panels']['a']['unique'])
                await set_unique(store, 123, 'a', False)
                self.assertFalse((await fresh.get(123))['panels']['a']['unique'])
        asyncio.run(run())

    def test_missing_panel(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                with self.assertRaises(ValueError):
                    await set_unique(store, 123, 'missing', True)
        asyncio.run(run())

if __name__ == '__main__':
    unittest.main()
