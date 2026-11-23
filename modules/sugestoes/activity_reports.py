"""Métricas por período baseadas em eventos auditados, sem inferir datas ausentes."""
from datetime import datetime,timezone,timedelta
from collections import Counter
from .metrics import collect

PERIODS = {'7d': 7, '30d': 30, '90d': 90, 'total': None}

def parse_time(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None

def build_report(data, period='30d', now=None):
    if period not in PERIODS: raise ValueError('Período inválido')
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=PERIODS[period]) if PERIODS[period] else None
    events = data.get('audit_events', [])
    events = events if isinstance(events,list) else []
    selected=[]
    for e in events:
        if not isinstance(e,dict): continue
        t=parse_time(e.get('timestamp'))
        if t and t<=now and (since is None or t>=since): selected.append(e)
    counts=Counter(str(e.get('action','desconhecida')) for e in selected)
    daily=Counter(str(e['timestamp'])[:10] for e in selected)
    created_ids={str(e['suggestion_id']) for e in selected if e.get('action')=='suggestion_created' and e.get('suggestion_id') is not None}
    records=data.get('suggestions',{})
    records=records if isinstance(records,dict) else {}
    # Ranking por votos ATUAIS das sugestões criadas no período. Não é histórico de votos.
    all_rank=collect(data)['ranking']
    ranking=[x for x in all_rank if period=='total' or x['id'] in created_ids]
    return {'period':period,'events':len(selected),'counts':counts,'daily':dict(sorted(daily.items())),
            'created':counts['suggestion_created'],'status_changes':counts['status_changed'],
            'ranking':ranking,'totals':collect(data)['totals'],
            'known_created':len(created_ids),'has_legacy':any(str(k) not in {str(e.get('suggestion_id')) for e in events if isinstance(e,dict) and e.get('action')=='suggestion_created'} for k in records)}
