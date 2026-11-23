import asyncio
import json
import tempfile
import unittest
from systems.leveling.storage import LevelStorage
from systems.leveling.backups import BackupManager

class BackupTests(unittest.TestCase):
    def test_backup_restore_and_isolation(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                store = LevelStorage(tmp)
                manager = BackupManager(store)
                await store.set_member(101, 55, xp=300, level=1)
                name = await manager.create(101)
                await store.set_member(101, 55, xp=900, level=2)
                safety = await manager.restore(101, name)
                self.assertEqual((await store.get_member(101, 55))["xp"], 300)
                self.assertTrue(safety.startswith("guild_101_"))
                with self.assertRaises(ValueError):
                    await manager.restore(202, name)
                self.assertIn(name, await manager.list(101))
        asyncio.run(run())
