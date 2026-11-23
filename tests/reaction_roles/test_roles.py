import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.panels import create_panel
from systems.reaction_roles.services.roles import add_mapping, remove_mapping, validate_emoji

class RoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_remove_preserve_panel(self):
        with TemporaryDirectory() as temp:
            store = GuildJsonStore(Path(temp))
            panel = await create_panel(store, 123, 'Cargos', 'Escolha', 0x5865F2)
            await add_mapping(store, 123, panel['id'], '🎮', 456)
            data = await store.get(123)
            self.assertEqual(data['panels'][panel['id']]['roles']['🎮'], '456')
            await remove_mapping(store, 123, panel['id'], '🎮')
            self.assertEqual((await store.get(123))['panels'][panel['id']]['roles'], {})
    async def test_invalid_emoji(self):
        with self.assertRaises(ValueError):
            validate_emoji('abc')
    async def test_mapping_limit(self):
        with TemporaryDirectory() as temp:
            store = GuildJsonStore(Path(temp))
            panel = await create_panel(store, 123, 'Cargos', 'Escolha', 0x5865F2)
            for i in range(20):
                await add_mapping(store, 123, panel['id'], f'<:role:{100000000000000+i}>', 456+i)
            with self.assertRaises(ValueError):
                await add_mapping(store, 123, panel['id'], '🎮', 999)
