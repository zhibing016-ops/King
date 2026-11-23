import json
from pathlib import Path
from threading import RLock

DATA_DIR = Path(__file__).resolve().parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
LOCK = RLock()
DEFAULT = {'enabled': True, 'log_channel': None, 'staff_role': None, 'settings': {}, 'warnings': {}, 'cases': [], 'counters': {}}

def load(guild_id):
    path = DATA_DIR / f'{int(guild_id)}.json'
    with LOCK:
        if not path.exists():
            return json.loads(json.dumps(DEFAULT))
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict): raise ValueError('JSON inválido')
            return {**json.loads(json.dumps(DEFAULT)), **data}
        except (OSError, ValueError) as exc:
            raise RuntimeError(f'Falha ao ler {path}: {exc}') from exc

def save(guild_id, data):
    path = DATA_DIR / f'{int(guild_id)}.json'
    temp = path.with_suffix('.tmp')
    with LOCK:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
