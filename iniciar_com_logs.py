#!/usr/bin/env python3
"""Inicia main.py e registra a saída em TXT em tempo real."""
from datetime import datetime
from pathlib import Path
import os
import re
import signal
import subprocess
import sys

BASE_DIR = Path(__file__).resolve().parent
MAIN_FILE = BASE_DIR / 'main.py'
LOG_DIR = BASE_DIR / 'logs'
ERRO = re.compile(r'Traceback \(most recent call last\)|\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b|\b(?:CRITICAL|ERROR)\b', re.I)
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def ocultar_segredos(texto):
    """Oculta valores das variáveis sensíveis presentes no ambiente/.env."""
    chaves = ('TOKEN', 'SECRET', 'API_KEY', 'PASSWORD', 'WEBHOOK')
    segredos = set()
    for k, v in os.environ.items():
        if any(p in k.upper() for p in chaves) and len(v) >= 6:
            segredos.add(v)
    env_file = BASE_DIR / '.env'
    if env_file.is_file():
        for linha in env_file.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            if '=' not in linha or linha.lstrip().startswith('#'):
                continue
            chave, valor = linha.split('=', 1)
            valor = valor.strip().strip('"\'')
            if any(p in chave.upper() for p in chaves) and len(valor) >= 6:
                segredos.add(valor)
    for segredo in sorted(segredos, key=len, reverse=True):
        texto = texto.replace(segredo, '[REDACTED]')
    return texto


def main():
    if not MAIN_FILE.is_file():
        print('ERRO: main.py não encontrado na mesma pasta do script.', file=sys.stderr)
        return 2
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    agora = datetime.now().astimezone()
    sufixo = agora.strftime('%Y-%m-%d_%H-%M-%S_%f')
    caminho = LOG_DIR / f'terminal_{sufixo}.txt'
    ultimo = LOG_DIR / 'ultimo_terminal.txt'
    erros = LOG_DIR / 'ultimo_erros.txt'
    status = 'NÃO CONCLUÍDO'
    codigo = 1
    achou_erro = False
    processo = None
    cabecalho = (f'KING PLUS - REGISTRO DO TERMINAL\nInício: {agora.isoformat(timespec="seconds")}\n'
                 f'Python: {sys.executable}\nProjeto: {BASE_DIR}\n' + '=' * 72 + '\n')
    try:
        with caminho.open('w', encoding='utf-8') as log, ultimo.open('w', encoding='utf-8') as atual, erros.open('w', encoding='utf-8') as somente_erros:
            def gravar(s):
                log.write(s); log.flush()
                atual.write(s); atual.flush()
            gravar(cabecalho)
            print(f'KING PLUS | Relatório: {caminho}', flush=True)
            try:
                ambiente = os.environ.copy()
                ambiente['PYTHONUNBUFFERED'] = '1'
                processo = subprocess.Popen([sys.executable, '-u', str(MAIN_FILE)], cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    text=True, encoding='utf-8', errors='replace', bufsize=1, env=ambiente)
                assert processo.stdout is not None
                for linha in processo.stdout:
                    limpa = ocultar_segredos(ANSI.sub('', linha))
                    print(limpa, end='', flush=True)
                    gravar(limpa)
                    if ERRO.search(limpa):
                        achou_erro = True
                        somente_erros.write(limpa); somente_erros.flush()
                codigo = processo.wait()
                status = 'FINALIZADO SEM ERRO DE EXECUÇÃO' if codigo == 0 else f'FINALIZADO COM CÓDIGO {codigo}'
            except KeyboardInterrupt:
                status = 'INTERROMPIDO PELO USUÁRIO (Ctrl+C)'
                codigo = 130
                if processo and processo.poll() is None:
                    processo.send_signal(signal.SIGINT)
                    try:
                        processo.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        processo.terminate()
                        try:
                            processo.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            processo.kill(); processo.wait()
            except Exception as exc:
                status = f'FALHA DO REGISTRADOR: {type(exc).__name__}: {exc}'
                achou_erro = True
                codigo = 1
                gravar(ocultar_segredos(status) + '\n')
            finally:
                if processo and processo.stdout:
                    processo.stdout.close()
                resumo = (f'\n{"=" * 72}\nStatus: {status}\n'
                          f'Mensagens típicas de erro: {"SIM" if achou_erro else "NÃO"}\n'
                          f'Fim: {datetime.now().astimezone().isoformat(timespec="seconds")}\n')
                gravar(ocultar_segredos(resumo))
                if not achou_erro:
                    somente_erros.write('Nenhuma linha típica de erro foi detectada.\n')
    except OSError as exc:
        print(f'Não foi possível gravar os logs: {exc}', file=sys.stderr)
        return 2
    print(f'\n{status}\nÚltimo relatório: {ultimo}\nErros detectados: {erros}', flush=True)
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
