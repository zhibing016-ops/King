"""Read-only guild-scoped Redeem statistics; no player identifiers in reports."""
from collections import Counter
from datetime import datetime, timezone, timedelta

STATES = ('pending', 'processing', 'review', 'delivered', 'failed', 'cancelled')

def _date(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

def report(data, guild_id, days=30):
    if days not in (7, 30, 90, 0):
        raise ValueError('Período inválido')
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days) if days else None
    games = {k:v for k,v in data.get('games', {}).items() if str(v.get('guild_id')) == str(guild_id)}
    codes = {k:v for k,v in data.get('codes', {}).items() if str(v.get('guild_id')) == str(guild_id)}
    claims = [c for c in data.get('claims', []) if str(c.get('guild_id')) == str(guild_id) and (since is None or (_date(c.get('created_at')) is not None and _date(c['created_at']) >= since))]
    counts = Counter(c.get('status', 'unknown') for c in claims)
    by_game = Counter(c.get('game_key') for c in claims if c.get('game_key') in games)
    by_code = Counter(c.get('code_id') for c in claims if c.get('code_id') in codes)
    return {'period': days, 'games': len(games), 'codes': len(codes), 'total': len(claims),
            'counts': counts, 'by_game': [(games[k].get('name', k), n) for k,n in by_game.most_common(10)],
            'by_code': [(codes[k].get('code', k), n) for k,n in by_code.most_common(10)]}

def format_report(r):
    label = f"Últimos {r['period']} dias" if r['period'] else 'Todo o histórico'
    counts = r['counts']
    lines = [f'**Período:** {label}', f"**Jogos:** {r['games']} | **Códigos:** {r['codes']}",
             f"**Solicitações:** {r['total']}", f"**Entregues:** {counts['delivered']} | **Pendentes:** {counts['pending']}",
             f"**Processando:** {counts['processing']} | **Em revisão:** {counts['review']}",
             f"**Falhas:** {counts['failed']} | **Canceladas:** {counts['cancelled']}",
             '', '**Jogos com mais solicitações:**']
    lines += [f'• {name[:55]}: {n}' for name,n in r['by_game'][:5]] or ['• Nenhum']
    lines += ['', '**Códigos com mais solicitações:**']
    lines += [f'• {name[:55]}: {n}' for name,n in r['by_code'][:5]] or ['• Nenhum']
    lines += ['', '*Ranking por solicitações, não por entregas. Sem dados pessoais.*']
    return '\n'.join(lines)[:3900]
