import asyncio
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.temporary import (configure_temporary, register_grant, expired_grants, remove_if_unchanged)

class TemporaryTests(unittest.TestCase):
    def test_config_and_expiry(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                store = GuildJsonStore(Path(directory))
                def create(data):
                    data['panels']['p1'] = {'id':'p1', 'roles': {'🎮':'100'}}
                await store.mutate(123, create)
                panel = await configure_temporary(store, 123, 'p1', 3600)
                self.assertEqual(panel['temporary_seconds'], 3600)
                now = datetime(2026, 1, 1, tzinfo=timezone.utc)
                await register_grant(store, 123, 45, 100, 'p1', 3600, now=now)
                data = await store.get(123)
                self.assertFalse(expired_grants(data, now+timedelta(minutes=59)))
                self.assertEqual(len(expired_grants(data, now+timedelta(hours=1))), 1)
                key='45:100'; expiry=data['temporary_grants'][key]['expires_at']
                self.assertFalse(await remove_if_unchanged(store,123,key,'wrong'))
                self.assertTrue(await remove_if_unchanged(store,123,key,expiry))
                self.assertFalse((await store.get(123))['temporary_grants'])
        asyncio.run(run())

    def test_invalid_duration(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                store=GuildJsonStore(Path(directory))
                with self.assertRaises(ValueError):
                    await configure_temporary(store, 123, 'x', 10)
        asyncio.run(run())
