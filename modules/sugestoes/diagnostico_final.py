"""Diagnóstico offline: python diagnostico_final.py"""
import json
import sys
from modules.sugestoes.config import DATA_DIR
from modules.sugestoes.maintenance import validate_data

def main():
    failures = 0
    files = sorted(DATA_DIR.glob('guild_*.json'))
    print(f'Arquivos de servidores: {len(files)}')
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            issues = validate_data(data)
            if issues:
                failures += 1
                print(f'[FALHA] {path.name}: ' + '; '.join(issues))
            else:
                print(f'[OK] {path.name}: {len(data["suggestions"])} sugestões')
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            failures += 1
            print(f'[FALHA] {path.name}: {exc}')
    print('Problemas encontrados:', failures)
    return 1 if failures else 0

if __name__ == '__main__':
    sys.exit(main())
