"""Validação local configurável por jogo (não verifica existência na API)."""
import re

PRESETS = {
    'numeric': r'[0-9]+',
    'alphanumeric': r'[A-Za-z0-9]+',
    'username': r'[A-Za-z0-9_.-]+',
    'uuid': r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
    'custom': None,
}


def configure(game, kind, minimum, maximum, custom_pattern='', require_server=False, servers=''):
    if kind not in PRESETS:
        raise ValueError('Tipo de identificador inválido.')
    try:
        minimum, maximum = int(minimum), int(maximum)
    except (TypeError, ValueError):
        raise ValueError('Tamanhos devem ser números inteiros.')
    if not 1 <= minimum <= maximum <= 100:
        raise ValueError('Tamanhos devem estar entre 1 e 100.')
    if kind == 'uuid' and (minimum > 36 or maximum < 36):
        raise ValueError('UUID precisa permitir exatamente 36 caracteres.')
    if kind == 'custom':
        if not 1 <= len(custom_pattern) <= 120:
            raise ValueError('Regex personalizada precisa ter 1 a 120 caracteres.')
        if any(x in custom_pattern for x in ('(?', '\\1', '\\2')):
            raise ValueError('Regex com grupos especiais ou referências não é permitida.')
        try:
            re.compile(custom_pattern)
        except re.error:
            raise ValueError('Regex personalizada inválida.')
    allowed = [s.strip() for s in servers.split(',') if s.strip()]
    if len(allowed) > 30 or any(len(s) > 60 for s in allowed):
        raise ValueError('Máximo 30 servidores, cada um com até 60 caracteres.')
    if len({s.casefold() for s in allowed}) != len(allowed):
        raise ValueError('Servidores duplicados.')
    game['validation'] = {'type': kind, 'min_length': minimum, 'max_length': maximum,
                          'pattern': custom_pattern if kind == 'custom' else '',
                          'require_server': bool(require_server), 'servers': allowed}
    return game['validation']


def validate_player(game, identifier, server):
    rules = game.get('validation') or {}
    identifier, server = identifier.strip(), server.strip()
    minimum, maximum = rules.get('min_length', 2), rules.get('max_length', 100)
    if not minimum <= len(identifier) <= maximum:
        raise ValueError(f'Identificador precisa ter entre {minimum} e {maximum} caracteres.')
    kind = rules.get('type', 'any')
    pattern = rules.get('pattern') if kind == 'custom' else PRESETS.get(kind)
    if kind == 'custom' and not pattern:
        raise ValueError('Regra personalizada não configurada.')
    if pattern and not re.fullmatch(pattern, identifier):
        raise ValueError('Identificador não corresponde ao formato configurado para este jogo.')
    if len(server) > 100:
        raise ValueError('Servidor/região excede 100 caracteres.')
    if rules.get('require_server') and not server:
        raise ValueError('Servidor/região é obrigatório para este jogo.')
    allowed = rules.get('servers', [])
    if allowed:
        match = next((s for s in allowed if s.casefold() == server.casefold()), None)
        if not match:
            raise ValueError('Servidor/região inválido. Escolha um servidor cadastrado.')
        server = match
    return identifier, server
