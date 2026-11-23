from collections import Counter
from datetime import datetime, timezone, timedelta

STATUS = ('Pendente', 'Em análise', 'Aprovada', 'Rejeitada')

def collect(data):
    records = [(str(k), v) for k, v in data.get('suggestions', {}).items() if isinstance(v, dict) and v.get('status') != 'Falha no envio']
    statuses = Counter(v.get('status', 'Pendente') for _, v in records)
    totals = {'total': len(records), 'positivos': 0, 'negativos': 0, 'comentarios': 0, 'anonimas': 0}
    ranking = []
    for key, record in records:
        votes = record.get('votes') or {}
        if not isinstance(votes, dict): votes = {}
        up = sum(x == 'up' for x in votes.values())
        down = sum(x == 'down' for x in votes.values())
        comments = record.get('comment_count', record.get('comments_count', 0))
        if not isinstance(comments, int): comments = 0
        totals['positivos'] += up
        totals['negativos'] += down
        totals['comentarios'] += max(0, comments)
        totals['anonimas'] += bool(record.get('anonymous', False))
        ranking.append({'id': key, 'titulo': str(record.get('text', '')).splitlines()[0][:80], 'up': up, 'down': down, 'saldo': up-down, 'status': record.get('status', 'Pendente')})
    ranking.sort(key=lambda r: (-r['saldo'], -r['up'], int(r['id']) if r['id'].isdigit() else 10**20))
    return {'totals': totals, 'statuses': dict(statuses), 'ranking': ranking}

def format_summary(metrics):
    t = metrics['totals']; s = metrics['statuses']
    lines = [f"Sugestões: **{t['total']}**", f"Votos: 👍 **{t['positivos']}** | 👎 **{t['negativos']}**", f"Comentários via bot: **{t['comentarios']}** | Anônimas: **{t['anonimas']}**", '', '**Status**']
    lines += [f"• {k}: **{s.get(k, 0)}**" for k in STATUS]
    other = [(k,v) for k,v in s.items() if k not in STATUS]
    lines += [f"• {k[:35]}: **{v}**" for k,v in other]
    return '\n'.join(lines)
