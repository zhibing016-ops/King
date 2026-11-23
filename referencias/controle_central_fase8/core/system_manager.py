import asyncio
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYSTEMS_FILE = ROOT / "config" / "systems.json"

class SystemManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.systems = self._read()

    def _read(self):
        with SYSTEMS_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)

    def is_enabled(self, key: str) -> bool:
        return bool(self.systems.get(key, {}).get("enabled", False))

    async def set_enabled(self, key: str, enabled: bool):
        async with self._lock:
            await self._set_enabled_unlocked(key, enabled)

    async def _set_enabled_unlocked(self, key: str, enabled: bool):
            if key not in self.systems:
                raise KeyError(f"Sistema desconhecido: {key}")
            self.systems[key]["enabled"] = bool(enabled)
            tmp = SYSTEMS_FILE.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(self.systems, f, indent=2, ensure_ascii=False)
            os.replace(tmp, SYSTEMS_FILE)

    def status_text(self) -> str:
        return "\n".join(
            f"{item['emoji']} **{item['name']}** — {'🟢 Ativado' if item['enabled'] else '🔴 Em manutenção'}"
            for item in self.systems.values()
        )
