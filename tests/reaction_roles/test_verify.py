import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.verify import set_verify, is_verify, validate_verify_panel

class VerifyTests(unittest.TestCase):
    def test_flag(self):
        self.assertFalse(is_verify({}))
        self.assertTrue(is_verify({'verify': True}))

    def test_requires_single_mapping(self):
        for roles in ({}, {'a': '1', 'b': '2'}):
            with self.assertRaises(ValueError):
                validate_verify_panel({'roles': roles})
        validate_verify_panel({'roles': {'✅': '123'}})

    def test_persist_and_incompatible_unique(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                await store.initialize(123)
                await store.mutate(123, lambda d: d['panels'].update({'p': {'title': 'Verificação', 'roles': {'✅': '555'}, 'unique': False}}))
                await set_verify(store, 123, 'p', True)
                self.assertTrue((await GuildJsonStore(Path(tmp)).get(123))['panels']['p']['verify'])
                await set_verify(store, 123, 'p', False)
                self.assertFalse((await store.get(123))['panels']['p']['verify'])
                await store.mutate(123, lambda d: d['panels']['p'].update(unique=True))
                with self.assertRaises(ValueError):
                    await set_verify(store, 123, 'p', True)
        asyncio.run(run())

    def test_missing_panel(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = GuildJsonStore(Path(tmp))
                with self.assertRaises(ValueError):
                    await set_verify(store, 123, 'missing', True)
        asyncio.run(run())
