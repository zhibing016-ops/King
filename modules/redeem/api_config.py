import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.fernet import Fernet, InvalidToken

SECRET_FILE = Path(__file__).resolve().parents[1] / 'storage' / 'redeem_secrets.json'


def normalize_url(value):
    value = value.strip().rstrip('/')
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Use URL HTTPS válida, sem credenciais, query ou fragmento.')
    host = parts.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Host local/interno não permitido.')
    try:
        ip = ipaddress.ip_address(host)
        if not ip.is_global: raise ValueError('IP privado ou reservado não permitido.')
    except ValueError as exc:
        if 'não permitido' in str(exc): raise
    if not all(part and part.replace('-', '').isalnum() for part in host.split('.')) or '.' not in host:
        raise ValueError('Domínio inválido.')
    if len(value) > 250: raise ValueError('URL muito longa.')
    return value


def validate_endpoint(value, required):
    value = value.strip()
    if not value and not required: return ''
    if not value.startswith('/') or value.startswith('//') or '://' in value or '?' in value or '#' in value or '..' in value or '\\' in value:
        raise ValueError('Endpoint deve ser caminho relativo, como /v1/claim.')
    return value


def _fernet():
    key = os.getenv('REDEEM_SECRET_KEY', '').strip()
    if not key: raise RuntimeError('Configure REDEEM_SECRET_KEY no .env antes de salvar credenciais.')
    try: return Fernet(key.encode())
    except (ValueError, TypeError): raise RuntimeError('REDEEM_SECRET_KEY inválida; gere uma chave Fernet.')


def _read():
    if not SECRET_FILE.exists(): return {}
    return json.loads(SECRET_FILE.read_text(encoding='utf-8'))


def secret_set(game_key, value):
    if not value.strip(): raise ValueError('Credencial vazia.')
    encrypted = _fernet().encrypt(value.strip().encode()).decode()
    data = _read(); data[game_key] = encrypted
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600); tmp.replace(SECRET_FILE)


def secret_exists(game_key): return game_key in _read()


def secret_delete(game_key):
    data = _read(); data.pop(game_key, None)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600); tmp.replace(SECRET_FILE)


def secret_move(old_key, new_key):
    data = _read()
    if old_key not in data: return
    data[new_key] = data.pop(old_key)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SECRET_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600); tmp.replace(SECRET_FILE)


def secret_get(game_key):
    encrypted = _read().get(game_key)
    if not encrypted: return None
    try: return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken: raise RuntimeError('Credencial não pôde ser descriptografada; confira REDEEM_SECRET_KEY.')
