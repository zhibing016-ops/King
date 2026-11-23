"""Relatórios agregados sobre a auditoria JSON existente (últimos 500 eventos)."""
from collections import Counter
from datetime import datetime, timedelta, timezone

EVENT_LABELS = {'grant': 'Atribuições', 'revoke': 'Remoções', 'expire': 'Expirações',
                'denied': 'Bloqueios', 'error': 'Erros', 'config': 'Configurações'}

def _parse_date(raw):
    try:
        value = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None

def calculate_statistics(history, days=None, now=None):
    """Agrupa eventos conhecidos; métricas NÃO são totais históricos globais.

    days=None inclui todo o histórico retido. days=7/30 aplica filtro UTC.
    A contagem de participantes inclui usuários identificados em eventos de
    concessão/remoção/expiração, e não o número atual de membros com cargos.
    """
    if days not in (None, 7, 30):
        raise ValueError('Período deve ser 7, 30 dias ou todo o histórico.')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('now precisa conter fuso horário.')
    since = now.astimezone(timezone.utc) - timedelta(days=days) if days else None
    events = []
    for item in history:
        if not isinstance(item, dict) or item.get('event') not in EVENT_LABELS:
            continue
        when = _parse_date(item.get('at'))
        if when is None or (since and when < since) or when > now.astimezone(timezone.utc):
            continue
        events.append(item)
    counts = Counter(e['event'] for e in events)
    sources = Counter(e.get('source') or 'desconhecido' for e in events)
    grants = Counter(str(e.get('role_id')) for e in events
                     if e['event'] == 'grant' and str(e.get('role_id') or '').isdigit())
    users = {str(e['member_id']) for e in events
             if e['event'] in ('grant', 'revoke', 'expire') and str(e.get('member_id') or '').isdigit()}
    days_count = Counter(str(e['at'])[:10] for e in events)
    return {'period_days': days, 'events': len(events), 'counts': dict(counts),
            'unique_users': len(users), 'top_roles': grants.most_common(10),
            'sources': sources.most_common(10), 'daily': sorted(days_count.items()),
            'first_event': min((e['at'] for e in events), default=None),
            'last_event': max((e['at'] for e in events), default=None)}

def report_from_guild(data, days=None, now=None):
    audit = data.get('audit', {})
    history = audit.get('history', [])
    if not isinstance(history, list):
        history = []
    result = calculate_statistics(history, days=days, now=now)
    result['retained_records'] = len(history)
    result['history_limit'] = 500
    result['audit_enabled'] = bool(audit.get('enabled', True))
    return result
