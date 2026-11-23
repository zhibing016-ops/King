"""Backup e restauração JSON com validação e substituição atômica."""
import asyncio
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

class BackupManager:
    def __init__(self, storage):
        self.storage = storage
        self.backup_dir = storage.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _backup_path(self, guild_id, name):
        if not name.startswith(f"guild_{guild_id}_") or not name.endswith(".json") or Path(name).name != name:
            raise ValueError("Nome de backup inválido")
        return self.backup_dir / name

    async def create(self, guild_id):
        lock = self.storage._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            data = await asyncio.to_thread(self.storage._read, guild_id)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            name = f"guild_{guild_id}_{stamp}.json"
            target = self._backup_path(guild_id, name)
            await asyncio.to_thread(self._write_backup, target, data)
            return name

    @staticmethod
    def _write_backup(target, data):
        with target.open("x", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

    async def list(self, guild_id):
        return sorted((x.name for x in self.backup_dir.glob(f"guild_{guild_id}_*.json") if x.is_file()), reverse=True)

    async def restore(self, guild_id, name):
        target = self._backup_path(guild_id, name)
        lock = self.storage._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            def perform():
                with target.open(encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or data.get("guild_id") != guild_id or not isinstance(data.get("members"), dict) or not isinstance(data.get("config"), dict):
                    raise ValueError("Backup inválido ou pertence a outro servidor")
                for m in data["members"].values():
                    if not isinstance(m, dict) or type(m.get("xp")) is not int or m["xp"] < 0:
                        raise ValueError("Backup contém XP inválido")
                current = self.storage._read(guild_id)
                safety = self.backup_dir / f"guild_{guild_id}_before_restore_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
                self._write_backup(safety, current)
                self.storage._write(guild_id, data)
                return safety.name
            return await asyncio.to_thread(perform)
