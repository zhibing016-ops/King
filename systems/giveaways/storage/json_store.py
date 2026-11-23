import asyncio
import json
import os
import tempfile
import secrets
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[3] / 'data' / 'giveaways' / 'giveaways.json'

class GiveawayStore:
    def __init__(self, path=DATA_FILE):
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _read(self):
        if not self.path.exists():
            return {'schema_version': 1, 'guilds': {}}
        with self.path.open('r', encoding='utf-8') as file:
            return json.load(file)

    def _write(self, data):
        # Auditoria transacional: a alteração e seu registro são salvos no mesmo JSON.
        previous = self._read()
        for gid, guild in data.get('guilds', {}).items():
            old = previous.get('guilds', {}).get(gid, {})
            events = []
            for key, kind in [('enabled', 'sistema_alterado'), ('appearance', 'aparencia_alterada'),
                              ('requirements', 'requisitos_alterados')]:
                if guild.get(key) != old.get(key):
                    events.append((kind, None, {'valor': guild.get(key)}))
            old_g = old.get('giveaways', {})
            for mid, record in guild.get('giveaways', {}).items():
                before = old_g.get(mid)
                if before is None:
                    events.append(('sorteio_criado', mid, {'premio': str(record.get('prize', ''))[:120]}))
                    continue
                prior = set(map(str, before.get('participants', [])))
                current = set(map(str, record.get('participants', [])))
                for uid in sorted(current - prior): events.append(('participacao_entrada', mid, {'usuario': uid}))
                for uid in sorted(prior - current): events.append(('participacao_saida', mid, {'usuario': uid}))
                if before.get('status') != record.get('status'):
                    events.append(('sorteio_encerrado', mid, {'estado': record.get('status'), 'vencedores': record.get('winners', [])}))
                if len(record.get('reroll_history', [])) > len(before.get('reroll_history', [])):
                    events.append(('reroll', mid, {'vencedores': record.get('winners', [])}))
            old_s = {str(x.get('id')): x for x in old.get('schedules', [])} if isinstance(old.get('schedules'), list) else {}
            if isinstance(guild.get('schedules'), list):
                for sched in guild['schedules']:
                    sid = str(sched.get('id'))
                    if sid not in old_s: events.append(('agendamento_criado', sid, {}))
                    elif sched.get('status') != old_s[sid].get('status'):
                        events.append(('agendamento_atualizado', sid, {'estado': sched.get('status')}))
            if events:
                audit = guild.setdefault('audit_log', [])
                for kind, ref, detail in events:
                    audit.append({'id': secrets.token_hex(8), 'at': datetime.now(timezone.utc).isoformat(),
                                  'event': kind, 'reference': str(ref) if ref is not None else None,
                                  'details': detail, 'delivered': False})
                guild['audit_log'] = audit[-2000:]

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='giveaways_', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def get_guild(self, guild_id):
        async with self._lock:
            data = self._read()
            return data.get('guilds', {}).get(str(guild_id), {'enabled': True, 'giveaways': {}})

    async def set_enabled(self, guild_id, enabled):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            guild['enabled'] = bool(enabled)
            self._write(data)

    async def add_giveaway(self, guild_id, giveaway):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            if not guild.get('enabled', True):
                raise ValueError('O sistema está desativado.')
            guild.setdefault('giveaways', {})[str(giveaway['message_id'])] = giveaway
            self._write(data)

    async def set_appearance(self, guild_id, appearance):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            guild['appearance'] = appearance
            self._write(data)

    async def set_requirements(self, guild_id, role_id, min_days):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            guild['requirements'] = {**guild.get('requirements', {}), 'role_id': int(role_id) if role_id else None, 'min_days': int(min_days)}
            self._write(data)

    async def set_account_age_requirement(self, guild_id, days):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            requirements = guild.setdefault('requirements', {})
            requirements['min_account_days'] = int(days)
            self._write(data)

    async def get_giveaway(self, guild_id, message_id):
        async with self._lock:
            data = self._read()
            return data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))

    async def toggle_participant(self, guild_id, message_id, user_id):
        async with self._lock:
            data = self._read()
            guild = data.get('guilds', {}).get(str(guild_id), {})
            if not guild.get('enabled', True):
                raise ValueError('Sistema em manutenção.')
            giveaway = guild.get('giveaways', {}).get(str(message_id))
            if not giveaway or giveaway.get('status') != 'active':
                raise ValueError('Sorteio indisponível.')
            from datetime import datetime, timezone
            if datetime.fromisoformat(giveaway['ends_at']) <= datetime.now(timezone.utc):
                raise ValueError('O prazo de participação terminou.')
            users = giveaway.setdefault('participants', [])
            uid = int(user_id)
            if uid in users:
                users.remove(uid)
                joined = False
            else:
                users.append(uid)
                joined = True
            self._write(data)
            return joined, len(users)

    async def all_active(self):
        async with self._lock:
            data = self._read()
            return [(int(gid), int(mid)) for gid, guild in data.get('guilds', {}).items()
                    for mid, giveaway in guild.get('giveaways', {}).items()
                    if giveaway.get('status') == 'active']

    async def participant_count(self, guild_id, message_id):
        async with self._lock:
            giveaway = self._read().get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id), {})
            return len(giveaway.get('participants', []))

    async def expired_active(self, now_iso):
        """Lista sorteios vencidos, sem alterar o JSON."""
        async with self._lock:
            data = self._read()
            return [(int(gid), int(mid), dict(giveaway))
                    for gid, guild in data.get('guilds', {}).items()
                    for mid, giveaway in guild.get('giveaways', {}).items()
                    if giveaway.get('status') == 'active' and giveaway.get('ends_at', '') <= now_iso]

    async def set_eligible_participants(self, guild_id, message_id, eligible):
        async with self._lock:
            data = self._read()
            record = data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))
            if record and record.get('status') == 'active':
                record['participants'] = list(dict.fromkeys(int(uid) for uid in eligible))
                self._write(data)

    async def close_expired(self, guild_id, message_id, now_iso):
        """Transição idempotente, protegida por lock; não seleciona vencedores."""
        async with self._lock:
            data = self._read()
            giveaway = data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))
            if not giveaway or giveaway.get('status') != 'active' or giveaway.get('ends_at', '') > now_iso:
                return None
            giveaway['status'] = 'ended'
            giveaway['ended_at'] = now_iso
            # Sorteio criptograficamente aleatório, sem repetição e persistido uma única vez.
            participants = list(dict.fromkeys(int(uid) for uid in giveaway.get('participants', [])))
            count = max(0, min(int(giveaway.get('winner_count', 1)), len(participants)))
            giveaway['winners'] = secrets.SystemRandom().sample(participants, count)
            giveaway['announcement_status'] = 'pending'
            self._write(data)
            return dict(giveaway)

    async def mark_announced(self, guild_id, message_id):
        async with self._lock:
            data = self._read()
            giveaway = data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))
            if not giveaway or giveaway.get('status') != 'ended':
                return
            giveaway['announcement_status'] = 'done'
            self._write(data)

    async def pending_announcements(self):
        async with self._lock:
            data = self._read()
            return [(int(gid), int(mid), dict(giveaway))
                    for gid, guild in data.get('guilds', {}).items()
                    for mid, giveaway in guild.get('giveaways', {}).items()
                    if giveaway.get('status') == 'ended' and giveaway.get('announcement_status') == 'pending']

    async def close_manually(self, guild_id, message_id, now_iso):
        """Encerra uma única vez e registra vencedores para anúncio posterior."""
        async with self._lock:
            data = self._read()
            giveaway = data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))
            if not giveaway or giveaway.get('status') != 'active':
                return None
            giveaway['status'] = 'ended'
            giveaway['ended_at'] = now_iso
            participants = list(dict.fromkeys(int(uid) for uid in giveaway.get('participants', [])))
            count = min(max(0, int(giveaway.get('winner_count', 1))), len(participants))
            giveaway['winners'] = secrets.SystemRandom().sample(participants, count)
            giveaway['announcement_status'] = 'pending'
            self._write(data)
            return dict(giveaway)

    async def reroll(self, guild_id, message_id, quantity, now_iso, eligible_ids=None):
        """Escolhe novos vencedores sem reutilizar qualquer vencedor histórico."""
        async with self._lock:
            data = self._read()
            record = data.get('guilds', {}).get(str(guild_id), {}).get('giveaways', {}).get(str(message_id))
            if not record or record.get('status') != 'ended':
                raise ValueError('Somente sorteios encerrados permitem reroll.')
            if record.get('announcement_status') != 'done':
                raise ValueError('Aguarde a publicação do resultado anterior.')
            previous = set(map(int, record.get('original_winners', record.get('winners', []))))
            for entry in record.get('reroll_history', []):
                previous.update(map(int, entry.get('winners', [])))
            eligible = list(dict.fromkeys(int(uid) for uid in record.get('participants', [])))
            available = [uid for uid in eligible if uid not in previous and (eligible_ids is None or uid in eligible_ids)]
            if not available:
                raise ValueError('Não existem participantes restantes para um novo sorteio.')
            if not 1 <= int(quantity) <= min(20, len(available)):
                raise ValueError(f'Escolha de 1 a {min(20, len(available))} novo(s) vencedor(es).')
            selected = secrets.SystemRandom().sample(available, int(quantity))
            record.setdefault('original_winners', list(record.get('winners', [])))
            record.setdefault('reroll_history', []).append({'at': now_iso, 'winners': selected})
            record['winners'] = selected
            record['announcement_status'] = 'pending'
            self._write(data)
            return dict(record)

    async def add_schedule(self, guild_id, record):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            if not guild.get('enabled', True):
                raise ValueError('Sistema em manutenção.')
            guild.setdefault('schedules', {})[record['id']] = record
            self._write(data)

    async def pending_schedules(self, now_iso):
        async with self._lock:
            data = self._read()
            return [(int(gid), dict(record)) for gid, guild in data.get('guilds', {}).items()
                    if guild.get('enabled', True)
                    for record in guild.get('schedules', {}).values()
                    if record.get('status') == 'pending' and record['starts_at'] <= now_iso]

    async def scheduled_for_guild(self, guild_id):
        async with self._lock:
            data = self._read()
            guild = data.get('guilds', {}).get(str(guild_id), {})
            return [dict(x) for x in guild.get('schedules', {}).values() if x.get('status') == 'pending']

    async def cancel_schedule(self, guild_id, schedule_id):
        async with self._lock:
            data = self._read()
            record = data.get('guilds', {}).get(str(guild_id), {}).get('schedules', {}).get(str(schedule_id))
            if not record or record.get('status') != 'pending':
                return False
            record['status'] = 'cancelled'
            self._write(data)
            return True

    async def recurring_for_guild(self, guild_id):
        async with self._lock:
            data = self._read()
            guild = data.get('guilds', {}).get(str(guild_id), {})
            return [dict(x) for x in guild.get('schedules', {}).values()
                    if x.get('recurrence') and x.get('status') == 'pending']

    async def cancel_recurring(self, guild_id, schedule_id):
        async with self._lock:
            data = self._read()
            record = data.get('guilds', {}).get(str(guild_id), {}).get('schedules', {}).get(str(schedule_id))
            if not record or not record.get('recurrence') or record.get('status') != 'pending':
                return False
            record['status'] = 'cancelled'
            self._write(data)
            return True

    async def mark_schedule_published(self, guild_id, schedule_id, giveaway):
        async with self._lock:
            data = self._read()
            guild = data['guilds'][str(guild_id)]
            record = guild.get('schedules', {}).get(str(schedule_id))
            if not record or record.get('status') != 'pending':
                return False
            guild.setdefault('giveaways', {})[str(giveaway['message_id'])] = giveaway
            if record.get('recurrence'):
                from datetime import datetime, timedelta, timezone
                import calendar
                from zoneinfo import ZoneInfo
                local = datetime.fromisoformat(record['starts_at']).astimezone(ZoneInfo('America/Sao_Paulo'))
                period = record['recurrence']
                if period == 'daily':
                    next_local = local + timedelta(days=1)
                elif period == 'weekly':
                    next_local = local + timedelta(days=7)
                elif period == 'monthly':
                    year = local.year + (local.month // 12)
                    month = local.month % 12 + 1
                    desired = int(record.get('anchor_day', local.day))
                    next_local = local.replace(year=year, month=month, day=min(desired, calendar.monthrange(year, month)[1]))
                else:
                    raise ValueError('Recorrência inválida')
                record['starts_at'] = next_local.astimezone(timezone.utc).isoformat()
                record['last_message_id'] = giveaway['message_id']
                record['occurrences'] = int(record.get('occurrences', 0)) + 1
            else:
                record['status'] = 'published'
                record['message_id'] = giveaway['message_id']
            self._write(data)
            return True

    async def configure_audit_channel(self, guild_id, channel_id):
        async with self._lock:
            data = self._read()
            guild = data.setdefault('guilds', {}).setdefault(str(guild_id), {'enabled': True, 'giveaways': {}})
            guild['audit_channel_id'] = int(channel_id) if channel_id else None
            self._write(data)

    async def audit_history(self, guild_id, limit=15):
        async with self._lock:
            guild = self._read().get('guilds', {}).get(str(guild_id), {})
            return list(reversed(guild.get('audit_log', [])[-max(1, min(int(limit), 50)) :]))

    async def pending_audit(self):
        async with self._lock:
            result = []
            for gid, guild in self._read().get('guilds', {}).items():
                channel = guild.get('audit_channel_id')
                if channel:
                    for event in guild.get('audit_log', []):
                        if not event.get('delivered', False):
                            result.append((int(gid), int(channel), dict(event)))
            return result[:50]

    async def mark_audit_delivered(self, guild_id, event_id):
        async with self._lock:
            data = self._read()
            for event in data.get('guilds', {}).get(str(guild_id), {}).get('audit_log', []):
                if event.get('id') == event_id:
                    event['delivered'] = True
                    self._write(data)
                    return
