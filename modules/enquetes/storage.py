import json
import asyncio
from pathlib import Path
DATA = Path(__file__).resolve().parents[2] / "data" / "enquetes"
DATA.mkdir(parents=True, exist_ok=True)
_lock = asyncio.Lock()
def read(name, default=None):
    p = DATA / f"{name}.json"
    if not p.exists(): return default if default is not None else {}
    try: return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError): return default if default is not None else {}
async def write(name, obj):
    async with _lock:
        p = DATA / f"{name}.json"
        temp = p.with_suffix(".tmp")
        temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(p)
