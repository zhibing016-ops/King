import asyncio
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.audit import record_audit, audit_settings, set_audit_channel, MAX_HISTORY

class AuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = GuildJsonStore(Path(self.temp.name))
        await self.store.initialize(123)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_history_persistence(self):
        await record_audit(None, self.store, 123, 'grant', member_id=99, role_id=100, source='test')
        self.assertEqual(audit_settings(await self.store.get(123))['history'][0]['event'], 'grant')

    async def test_channel_setting(self):
        await set_audit_channel(self.store, 123, 999)
        self.assertEqual(audit_settings(await self.store.get(123))['channel_id'], '999')
        await set_audit_channel(self.store, 123, None)
        self.assertEqual(audit_settings(await self.store.get(123))['channel_id'], '')

    async def test_bounded_history(self):
        for i in range(MAX_HISTORY + 3):
            await record_audit(None, self.store, 123, 'grant', member_id=i)
        self.assertEqual(len(audit_settings(await self.store.get(123))['history']), MAX_HISTORY)

    async def test_invalid_event(self):
        with self.assertRaises(ValueError):
            await record_audit(None, self.store, 123, 'invalid')
