import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore

class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_toggle_preserves_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GuildJsonStore(Path(tmp))
            original, created = await store.initialize(123)
            self.assertTrue(created)
            self.assertTrue(original['enabled'])
            await store.update(123, {'panels': {'abc': {'title': 'Painel'}}})
            await store.toggle_enabled(123)
            saved = await store.get(123)
            self.assertFalse(saved['enabled'])
            self.assertEqual(saved['panels']['abc']['title'], 'Painel')
            _, created_again = await store.initialize(123)
            self.assertFalse(created_again)
            self.assertFalse((await store.get(123))['enabled'])

    async def test_concurrent_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GuildJsonStore(Path(tmp))
            await store.initialize(123)
            await asyncio.gather(*(store.toggle_enabled(123) for _ in range(20)))
            self.assertTrue((await store.get(123))['enabled'])
