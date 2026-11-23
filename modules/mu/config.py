"""Persistência JSON do painel MU (ausente no ZIP fornecido)."""
import json
from pathlib import Path
from threading import RLock

FILE = Path(__file__).resolve().parent / "data" / "config.json"
LOCK = RLock()

def load_config():
    with LOCK:
        if not FILE.exists():
            return {}
        return json.loads(FILE.read_text(encoding="utf-8"))

def save_config(data):
    with LOCK:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(FILE)
