import json
import tempfile
import unittest
from pathlib import Path
from systems.reaction_roles.storage.json_store import GuildJsonStore
from systems.reaction_roles.services.maintenance import validate_backup, diagnose, export_backup, restore_backup

GID = 12345

def sample():
    return {"schema_version": 1, "guild_id": str(GID), "enabled": True,
            "panels": {"abc": {"id": "abc", "title": "Teste", "description": "Escolha",
                                "color": 1234, "roles": {"🎮": "123456"}}},
            "settings": {"logs_channel_id": None}}

class ValidationTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_backup(json.dumps(sample()).encode(), GID), sample())
    def test_other_guild(self):
        with self.assertRaises(ValueError):
            validate_backup(json.dumps(sample()).encode(), 999)
    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            validate_backup(b'{invalid', GID)
    def test_large(self):
        with self.assertRaises(ValueError):
            validate_backup(b' '*2_000_001, GID)
    def test_invalid_panel(self):
        data = sample()
        data['panels']['abc']['roles'] = {'🎮': 'wrong'}
        with self.assertRaises(ValueError):
            validate_backup(json.dumps(data).encode(), GID)
    def test_diagnosis(self):
        self.assertTrue(any(level == 'info' for level, _ in diagnose(sample())))

class RestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            store = GuildJsonStore(Path(folder))
            await store.initialize(GID)
            payload = json.dumps(sample()).encode()
            self.assertEqual(await restore_backup(store, GID, payload), 1)
            self.assertEqual(validate_backup(await export_backup(store, GID), GID), sample())
    async def test_reject_without_change(self):
        with tempfile.TemporaryDirectory() as folder:
            store = GuildJsonStore(Path(folder))
            await store.initialize(GID)
            before = await store.get(GID)
            with self.assertRaises(ValueError):
                await restore_backup(store, GID, b'{}')
            self.assertEqual(before, await store.get(GID))
