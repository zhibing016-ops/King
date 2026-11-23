import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.panels import create_panel, delete_panel, parse_color, save_publication

class TestPanels(unittest.TestCase):
    def test_crud_and_persistence(self):
        async def run():
            with tempfile.TemporaryDirectory() as d:
                store = GuildJsonStore(Path(d))
                p = await create_panel(store, 123, 'Teste', 'Descrição', parse_color('#5865F2'))
                await save_publication(store, 123, p['id'], 456, 789)
                data = await GuildJsonStore(Path(d)).get(123)
                self.assertEqual(data['panels'][p['id']]['message_id'], '789')
                await delete_panel(store, 123, p['id'])
                self.assertFalse((await store.get(123))['panels'])
        asyncio.run(run())

    def test_bad_color(self):
        with self.assertRaises(ValueError):
            parse_color('not a color')
