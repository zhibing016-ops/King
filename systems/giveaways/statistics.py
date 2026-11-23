"""Relatórios derivados dos registros JSON existentes; sem alterar os dados."""
from collections import Counter
from datetime import datetime, timezone

def summarize(config):
    records = list(config.get('giveaways', {}).values())
    ended = [r for r in records if r.get('status') == 'ended']
    active = [r for r in records if r.get('status') == 'active']
    participants = [set(map(str, r.get('participants', []))) for r in records]
    winner_ids = [str(uid) for r in ended for uid in r.get('winners', [])]
    rerolls = sum(len(r.get('reroll_history', [])) for r in ended)
    return {
        'total': len(records), 'active': len(active), 'ended': len(ended),
        'entries': sum(len(p) for p in participants),
        'unique_participants': len(set().union(*participants)) if participants else 0,
        'winners': len(winner_ids), 'unique_winners': len(set(winner_ids)),
        'rerolls': rerolls,
        'top': sorted(records, key=lambda r: len(set(map(str, r.get('participants', [])))), reverse=True)[:10],
        'winner_ranking': Counter(winner_ids).most_common(10),
        'scheduled': len(config.get('schedules', {})),
        'recurring': len(config.get('recurrings', {})),
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
