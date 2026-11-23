from modules.redeem.maintenance import create_backup, backups_for, restore_backup, diagnostics
from modules.redeem.audit import history as audit_history, set_channel as audit_set_channel, notify as audit_notify, append as audit_append
from modules.redeem.appearance import get_theme, update_theme, make_public_embed, make_dashboard_embed
from modules.redeem.campaigns import create_campaign, active as campaign_active, parse_rewards
from modules.redeem.delivery import deliver_one, _LOCK
from modules.redeem.api_probe import check_api
from modules.redeem.claims import submit_claim
from modules.redeem.limits import configure_limits, policy_for
from modules.redeem.availability import configure as configure_availability, policy as availability_policy
from modules.redeem.validation import configure, PRESETS
from modules.redeem.codes import create_code, guild_codes, code_status
import re
import discord
from discord import app_commands
from discord.ext import commands
from modules.redeem.store import load, save, guild_games
from modules.redeem.api_config import normalize_url, validate_endpoint, secret_set, secret_exists, secret_delete, secret_move


from modules.redeem.security import authorized, can_manage_roles, get_roles, set_roles


def game_key(guild_id, name):
    slug = re.sub(r'[^a-z0-9_-]+', '-', name.casefold().strip()).strip('-')
    return f'{guild_id}:{slug}' if slug else ''


def dashboard(guild_id):
    games = guild_games(load(), guild_id)
    return make_dashboard_embed(guild_id, len(games), sum(bool(g.get('api', {}).get('base_url')) for g in games.values()))


class AddGameModal(discord.ui.Modal, title='Cadastrar jogo'):
    name = discord.ui.TextInput(label='Nome do jogo', max_length=80)
    identifier = discord.ui.TextInput(label='Identificador do jogador', placeholder='UID, nickname, personagem...', max_length=80)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        key = game_key(interaction.guild_id, self.name.value)
        if not key:
            return await interaction.response.send_message('Nome inválido.', ephemeral=True)
        data = load()
        if key in data['games']:
            return await interaction.response.send_message('Jogo já cadastrado.', ephemeral=True)
        data['games'][key] = {'guild_id': interaction.guild_id, 'name': self.name.value.strip(),
                              'identifier': self.identifier.value.strip(), 'api': {'enabled': False}}
        save(data)
        await interaction.response.send_message('✅ Jogo cadastrado. Use **Gerenciar jogos** para editar.', ephemeral=True)


class EditGameModal(discord.ui.Modal, title='Editar jogo'):
    def __init__(self, key, game):
        super().__init__()
        self.key = key
        self.name = discord.ui.TextInput(label='Nome do jogo', default=game['name'], max_length=80)
        self.identifier = discord.ui.TextInput(label='Identificador do jogador', default=game.get('identifier',''), max_length=80)
        self.add_item(self.name)
        self.add_item(self.identifier)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load()
        game = data['games'].get(self.key)
        if not game or str(game.get('guild_id')) != str(interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        new_key = game_key(interaction.guild_id, self.name.value)
        if not new_key or (new_key != self.key and new_key in data['games']):
            return await interaction.response.send_message('Nome inválido ou duplicado.', ephemeral=True)
        game.update(name=self.name.value.strip(), identifier=self.identifier.value.strip())
        if new_key != self.key:
            del data['games'][self.key]
            data['games'][new_key] = game
            secret_move(self.key, new_key)
        save(data)
        await interaction.response.send_message('✅ Jogo atualizado.', ephemeral=True)


class DeleteConfirm(discord.ui.View):
    def __init__(self, key):
        super().__init__(timeout=90)
        self.key = key

    @discord.ui.button(label='Confirmar exclusão', style=discord.ButtonStyle.danger, emoji='🗑️')
    async def confirm(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load()
        game = data['games'].get(self.key)
        if not game or str(game.get('guild_id')) != str(interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        del data['games'][self.key]
        secret_delete(self.key)
        save(data)
        await interaction.response.edit_message(content='✅ Jogo excluído.', view=None)

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content='Exclusão cancelada.', view=None)


class ValidationModal(discord.ui.Modal, title='Validação | Jogador e servidor'):
    def __init__(self, key, game):
        super().__init__(); self.key = key
        rules = game.get('validation') or {}
        self.kind = discord.ui.TextInput(label='Tipo: numeric/alphanumeric/username/uuid/custom', default=rules.get('type', 'username'), max_length=16)
        self.minimum = discord.ui.TextInput(label='Tamanho mínimo', default=str(rules.get('min_length', 2)), max_length=3)
        self.maximum = discord.ui.TextInput(label='Tamanho máximo', default=str(rules.get('max_length', 100)), max_length=3)
        self.regex = discord.ui.TextInput(label='Regex (somente tipo custom)', required=False, default=rules.get('pattern', ''), max_length=120)
        self.servers = discord.ui.TextInput(label='Servidores separados por vírgula (opcional)', required=False, default=', '.join(rules.get('servers', [])), max_length=500)
        for field in (self.kind, self.minimum, self.maximum, self.regex, self.servers): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load(); game = guild_games(data, interaction.guild_id).get(self.key)
        if not game:
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        try:
            configure(game, self.kind.value.strip().lower(), self.minimum.value,
                      self.maximum.value, self.regex.value.strip(),
                      bool(self.servers.value.strip()), self.servers.value)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        save(data)
        await interaction.response.send_message('✅ Validação salva. A lista de servidores, quando preenchida, passa a ser obrigatória. Nenhuma API foi chamada.', ephemeral=True)


class GameActions(discord.ui.View):
    def __init__(self, key):
        super().__init__(timeout=180)
        self.key = key

    @discord.ui.button(label='Editar', emoji='✏️', style=discord.ButtonStyle.primary)
    async def edit(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        game = load()['games'].get(self.key)
        if not game or str(game.get('guild_id')) != str(interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        await interaction.response.send_modal(EditGameModal(self.key, game))

    @discord.ui.button(label='Validar UID / Servidor', emoji='🛡️', style=discord.ButtonStyle.secondary)
    async def validation(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        game = guild_games(load(), interaction.guild_id).get(self.key)
        if not game:
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        await interaction.response.send_modal(ValidationModal(self.key, game))

    @discord.ui.button(label='Excluir', emoji='🗑️', style=discord.ButtonStyle.danger)
    async def delete(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_message('Confirma a exclusão deste jogo?', view=DeleteConfirm(self.key), ephemeral=True)


class GameSelect(discord.ui.Select):
    def __init__(self, games):
        options = [discord.SelectOption(label=g['name'][:100], value=k, description=g.get('identifier','')[:100]) for k,g in list(games.items())[:25]]
        super().__init__(placeholder='Selecione um jogo para gerenciar', options=options)

    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        key = self.values[0]
        game = guild_games(load(), interaction.guild_id).get(key)
        if not game:
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        embed = discord.Embed(title=f'🎮 {game["name"]}', description=f'**Identificador:** {game.get("identifier", "-")}\n**API:** {'Configurada' if game.get('api', {}).get('base_url') else 'Não configurada'}', color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=GameActions(key), ephemeral=True)


class GameList(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=180)
        self.add_item(GameSelect(games))



class ApiBaseModal(discord.ui.Modal, title='API | URL e endpoints'):
    def __init__(self, key, api):
        super().__init__(); self.key = key
        self.url = discord.ui.TextInput(label='URL base HTTPS', placeholder='https://api.exemplo.com', default=api.get('base_url', ''), max_length=250)
        self.claim = discord.ui.TextInput(label='Endpoint de resgate', placeholder='/v1/redeem/claim', default=api.get('claim_endpoint', '/v1/redeem/claim'), max_length=150)
        self.health = discord.ui.TextInput(label='Endpoint de status (opcional)', required=False, default=api.get('health_endpoint', ''), max_length=150)
        self.timeout = discord.ui.TextInput(label='Timeout (segundos: 3 a 30)', default=str(api.get('timeout', 15)), max_length=2)
        for field in (self.url, self.claim, self.health, self.timeout): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        try:
            url = normalize_url(self.url.value)
            claim = validate_endpoint(self.claim.value, required=True)
            health = validate_endpoint(self.health.value, required=False)
            timeout = int(self.timeout.value)
            if not 3 <= timeout <= 30: raise ValueError('Timeout deve ficar entre 3 e 30 segundos.')
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        data = load(); game = guild_games(data, interaction.guild_id).get(self.key)
        if not game: return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        game.setdefault('api', {}).update(base_url=url, claim_endpoint=claim, health_endpoint=health, timeout=timeout, enabled=False)
        save(data)
        await interaction.response.send_message('✅ Endpoints salvos. API permanece desativada; nenhum resgate foi executado.', ephemeral=True)


class ApiAuthModal(discord.ui.Modal, title='API | Autenticação'):
    def __init__(self, key):
        super().__init__(); self.key = key
        self.secret = discord.ui.TextInput(label='Token ou chave secreta', style=discord.TextStyle.short, max_length=1000)
        self.add_item(self.secret)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load(); game = guild_games(data, interaction.guild_id).get(self.key)
        if not game: return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        try: secret_set(self.key, self.secret.value)
        except (ValueError, RuntimeError) as exc: return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await interaction.response.send_message('🔐 Credencial criptografada e armazenada separadamente do JSON de jogos.', ephemeral=True)


class ApiAuthSelect(discord.ui.Select):
    def __init__(self, key):
        self.key = key
        super().__init__(placeholder='Método de autenticação', options=[discord.SelectOption(label=x, value=x) for x in ('none','bearer','api_key')])
    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load(); game = guild_games(data, interaction.guild_id).get(self.key)
        if not game: return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        game.setdefault('api', {})['auth_type'] = self.values[0]; game['api']['enabled'] = False; save(data)
        await interaction.response.send_message(f'✅ Autenticação: {self.values[0]}. API permanece desativada.', ephemeral=True)


class ApiAuthView(discord.ui.View):
    def __init__(self, key): super().__init__(timeout=180); self.add_item(ApiAuthSelect(key))


class ApiActions(discord.ui.View):
    def __init__(self, key): super().__init__(timeout=180); self.key = key
    async def get_game(self, interaction):
        if not authorized(interaction): await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True); return None
        game = guild_games(load(), interaction.guild_id).get(self.key)
        if not game: await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        return game

    @discord.ui.button(label='URL / Endpoints', emoji='🌐', style=discord.ButtonStyle.primary)
    async def endpoints(self, interaction, button):
        game = await self.get_game(interaction)
        if game: await interaction.response.send_modal(ApiBaseModal(self.key, game.get('api', {})))

    @discord.ui.button(label='Tipo de autenticação', emoji='🔑', style=discord.ButtonStyle.secondary)
    async def auth_type(self, interaction, button):
        if await self.get_game(interaction): await interaction.response.send_message('Selecione o método:', view=ApiAuthView(self.key), ephemeral=True)

    @discord.ui.button(label='Salvar credencial', emoji='🔐', style=discord.ButtonStyle.secondary)
    async def credential(self, interaction, button):
        if await self.get_game(interaction): await interaction.response.send_modal(ApiAuthModal(self.key))

    @discord.ui.button(label='Ver status', emoji='📋', style=discord.ButtonStyle.secondary, row=1)
    async def status(self, interaction, button):
        game = await self.get_game(interaction)
        if not game: return
        api = game.get('api', {})
        await interaction.response.send_message(f"**Jogo:** {discord.utils.escape_markdown(game['name'])}\n**URL:** `{api.get('base_url', 'Não configurada')}`\n**Claim:** `{api.get('claim_endpoint', '-')}`\n**Status:** Resgates desativados (Fase 04)\n**Autenticação:** `{api.get('auth_type', 'none')}`\n**Credencial:** {'Definida' if secret_exists(self.key) else 'Ausente'}", ephemeral=True)

    @discord.ui.button(label='Testar conexão', emoji='🩺', style=discord.ButtonStyle.primary, row=2)
    async def test_connection(self, interaction, button):
        game = await self.get_game(interaction)
        if not game: return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = await check_api(game.get('api', {}), self.key)
        except (ValueError, RuntimeError) as exc:
            result = f'⚠️ Configuração inválida: {type(exc).__name__}. Confira a URL, a chave de criptografia e os endpoints.'
        await audit_notify(interaction.guild, 'delivery_result', self.values[0], 'Entrega confirmada' if result.startswith('✅') else 'Verificar resultado no painel')
        await interaction.followup.send(result, ephemeral=True)

    @discord.ui.button(label='Apagar credencial', emoji='🗑️', style=discord.ButtonStyle.danger, row=1)
    async def clear(self, interaction, button):
        if await self.get_game(interaction):
            secret_delete(self.key)
            await interaction.response.send_message('Credencial apagada.', ephemeral=True)


class ApiGameSelect(discord.ui.Select):
    def __init__(self, games):
        super().__init__(placeholder='Escolha o jogo para configurar a API', options=[discord.SelectOption(label=g['name'][:100], value=k) for k,g in list(games.items())[:25]])
    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        key = self.values[0]
        if key not in guild_games(load(), interaction.guild_id): return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        await interaction.response.send_message('Configure URL, endpoints e autenticação:', view=ApiActions(key), ephemeral=True)


class ApiGameView(discord.ui.View):
    def __init__(self, games): super().__init__(timeout=180); self.add_item(ApiGameSelect(games))

class CreateCodeModal(discord.ui.Modal, title='Criar código de resgate'):
    def __init__(self, game_key):
        super().__init__(); self.game_key = game_key
        self.code = discord.ui.TextInput(label='Código', placeholder='KINGPLUS2026', max_length=64)
        self.reward = discord.ui.TextInput(label='Recompensa (descrição)', style=discord.TextStyle.paragraph, max_length=500)
        self.expiry = discord.ui.TextInput(label='Validade UTC (opcional)', placeholder='AAAA-MM-DD HH:MM', required=False, max_length=16)
        self.limit = discord.ui.TextInput(label='Máximo de resgates', default='100', max_length=7)
        for field in (self.code, self.reward, self.expiry, self.limit): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load()
        if self.game_key not in guild_games(data, interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        try:
            record = create_code(data, interaction.guild_id, self.game_key, self.code.value,
                                 self.reward.value, self.expiry.value, self.limit.value)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        save(data)
        await interaction.response.send_message(f'✅ Código `{record["code"]}` criado. **Nenhum item foi entregue.**', ephemeral=True)


class CodeActions(discord.ui.View):
    def __init__(self, code_id):
        super().__init__(timeout=180); self.code_id = code_id

    async def get_code(self, interaction):
        if not authorized(interaction):
            await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True); return None, None
        data = load(); record = guild_codes(data, interaction.guild_id).get(self.code_id)
        if not record:
            await interaction.response.send_message('Código não encontrado.', ephemeral=True)
        return data, record

    @discord.ui.button(label='Ativar / Desativar', style=discord.ButtonStyle.primary, emoji='🔁')
    async def toggle(self, interaction, button):
        data, record = await self.get_code(interaction)
        if not record: return
        record['enabled'] = not record.get('enabled', True)
        save(data)
        await interaction.response.edit_message(content=f'Código `{record["code"]}`: **{code_status(record)}**', view=None)

    @discord.ui.button(label='Excluir', style=discord.ButtonStyle.danger, emoji='🗑️')
    async def delete(self, interaction, button):
        data, record = await self.get_code(interaction)
        if not record: return
        await interaction.response.send_message('Confirme a exclusão permanente:', view=DeleteCodeConfirm(self.code_id), ephemeral=True)


class DeleteCodeConfirm(discord.ui.View):
    def __init__(self, code_id):
        super().__init__(timeout=90); self.code_id = code_id

    @discord.ui.button(label='Confirmar exclusão', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        data = load()
        if self.code_id not in guild_codes(data, interaction.guild_id):
            return await interaction.response.send_message('Código não encontrado.', ephemeral=True)
        del data['codes'][self.code_id]; save(data)
        await interaction.response.edit_message(content='✅ Código excluído.', view=None)

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content='Cancelado.', view=None)


class CodeSelect(discord.ui.Select):
    def __init__(self, records):
        options = [discord.SelectOption(label=r['code'][:100], value=k, description=code_status(r)[:100]) for k,r in list(records.items())[:25]]
        super().__init__(placeholder='Selecione um código', options=options)

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        record = guild_codes(load(), interaction.guild_id).get(self.values[0])
        if not record: return await interaction.response.send_message('Código não encontrado.', ephemeral=True)
        embed = discord.Embed(title=f'🎁 {record["code"]}', description=f'**Recompensa:** {discord.utils.escape_markdown(record["reward"])}\n**Status:** {code_status(record)}\n**Resgates:** {record["claims_count"]}/{record["max_claims"]}\n**Validade UTC:** {record["expires_at"] or "Sem validade"}', color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=CodeActions(self.values[0]), ephemeral=True)


class CodeList(discord.ui.View):
    def __init__(self, records):
        super().__init__(timeout=180); self.add_item(CodeSelect(records))


class CodeGameActions(discord.ui.View):
    def __init__(self, game_key):
        super().__init__(timeout=180); self.game_key = game_key

    @discord.ui.button(label='Criar código', style=discord.ButtonStyle.success, emoji='➕')
    async def create(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        if self.game_key not in guild_games(load(), interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        await interaction.response.send_modal(CreateCodeModal(self.game_key))

    @discord.ui.button(label='Gerenciar códigos', style=discord.ButtonStyle.secondary, emoji='📋')
    async def manage(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        if self.game_key not in guild_games(load(), interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        records = guild_codes(load(), interaction.guild_id, self.game_key)
        if not records: return await interaction.response.send_message('Nenhum código cadastrado.', ephemeral=True)
        await interaction.response.send_message(f'Códigos cadastrados: **{len(records)}**. Exibindo até 25 (limite do menu Discord).', view=CodeList(records), ephemeral=True)


class CodeGameSelect(discord.ui.Select):
    def __init__(self, games):
        super().__init__(placeholder='Selecione o jogo dos códigos', options=[discord.SelectOption(label=g['name'][:100], value=k) for k,g in list(games.items())[:25]])

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        if self.values[0] not in guild_games(load(), interaction.guild_id):
            return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        await interaction.response.send_message('Gerencie os códigos deste jogo:', view=CodeGameActions(self.values[0]), ephemeral=True)


class CodeGameView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=180); self.add_item(CodeGameSelect(games))


class ClaimModal(discord.ui.Modal, title='Solicitar resgate | Claim'):
    def __init__(self, game_key):
        super().__init__(timeout=300)
        self.game_key = game_key
        self.identifier = discord.ui.TextInput(label='UID / ID / Personagem', max_length=100)
        self.server = discord.ui.TextInput(label='Servidor / Região (opcional)', required=False, max_length=100)
        self.code = discord.ui.TextInput(label='Código de resgate', max_length=64)
        for field in (self.identifier, self.server, self.code): self.add_item(field)

    async def on_submit(self, interaction):
        if not interaction.guild_id:
            return await interaction.response.send_message('Use em um servidor.', ephemeral=True)
        async with _LOCK:
            data = load()
            try:
                claim = submit_claim(data, interaction.guild_id, self.game_key,
                                     interaction.user.id, self.identifier.value,
                                     self.server.value, self.code.value)
            except ValueError as exc:
                return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            save(data)
        await audit_notify(interaction.guild, 'claim_created', claim['id'], 'Solicitação pendente registrada')
        await interaction.response.send_message(
            f'📨 Solicitação registrada: `{claim["id"][:10]}`. Status: **pendente**. '
            'A entrega deve ser processada pelo administrador no painel, se a API estiver ativada.',
            ephemeral=True)


class ClaimGameSelect(discord.ui.Select):
    def __init__(self, games):
        super().__init__(placeholder='Escolha o jogo', options=[
            discord.SelectOption(label=g['name'][:100], value=k)
            for k, g in list(games.items())[:25]])

    async def callback(self, interaction):
        if not interaction.guild_id or self.values[0] not in guild_games(load(), interaction.guild_id):
            return await interaction.response.send_message('Jogo indisponível.', ephemeral=True)
        await interaction.response.send_modal(ClaimModal(self.values[0]))


class ClaimGameView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=180)
        self.add_item(ClaimGameSelect(games))


class PublicClaimView(discord.ui.View):
    def __init__(self, guild_id=None):
        super().__init__(timeout=None)
        if guild_id is not None:
            from modules.redeem.appearance import button_theme
            button_theme(self.children[0], guild_id)

    @discord.ui.button(label='Claim', emoji='🎟️', style=discord.ButtonStyle.success,
                       custom_id='kingplus:redeem:claim:v1')
    async def claim(self, interaction, button):
        if not interaction.guild_id:
            return await interaction.response.send_message('Use em um servidor.', ephemeral=True)
        games = guild_games(load(), interaction.guild_id)
        if not games:
            return await interaction.response.send_message('Nenhum jogo disponível.', ephemeral=True)
        await interaction.response.send_message('Selecione seu jogo:', view=ClaimGameView(games), ephemeral=True)


class DeliveryClaimSelect(discord.ui.Select):
    def __init__(self, claims):
        super().__init__(placeholder='Solicitação pendente para envio real', options=[
            discord.SelectOption(label=(c['id'][:12] + ' • ' + c['game_key'][-55:])[:100], value=c['id']) for c in claims])

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try: result = await deliver_one(self.values[0], interaction.guild_id)
        except (ValueError, RuntimeError) as exc: result = '❌ ' + str(exc)
        await audit_notify(interaction.guild, 'delivery_result', self.values[0], 'Entrega confirmada' if result.startswith('✅') else 'Verificar resultado no painel')
        await interaction.followup.send(result, ephemeral=True)

class DeliveryClaimView(discord.ui.View):
    def __init__(self, claims):
        super().__init__(timeout=180)
        self.add_item(DeliveryClaimSelect(claims))

class DeliveryGameSelect(discord.ui.Select):
    def __init__(self, games):
        super().__init__(placeholder='Jogo para configurar entrega', options=[
            discord.SelectOption(label=g['name'][:100], value=k) for k,g in list(games.items())[:25]])

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        key = self.values[0]
        data = load()
        game = guild_games(data, interaction.guild_id).get(key)
        if not game: return await interaction.response.send_message('Jogo não encontrado.', ephemeral=True)
        api = game.setdefault('api', {})
        api['enabled'] = not api.get('enabled', False)
        if api['enabled'] and not api.get('base_url'):
            api['enabled'] = False
            return await interaction.response.send_message('Configure URL e endpoint primeiro.', ephemeral=True)
        audit_append(data, interaction.guild_id, 'api_delivery_toggled', actor_id=interaction.user.id, details='Entrega ativada' if api['enabled'] else 'Entrega desativada')
        save(data)
        await audit_notify(interaction.guild, 'api_delivery_toggled', details='Configuração de entrega alterada')
        await interaction.response.send_message('Entrega ' + ('ativada' if api['enabled'] else 'desativada') + ' para este jogo. Ative somente APIs autorizadas que aceitem POST JSON e retornem delivered=true.', ephemeral=True)

class DeliveryGameView(discord.ui.View):
    def __init__(self, games):
        super().__init__(timeout=180)
        self.add_item(DeliveryGameSelect(games))

class LimitModal(discord.ui.Modal, title='Limites anti-duplicidade'):
    def __init__(self, code_id):
        super().__init__(timeout=300)
        self.code_id = code_id
        code = load().get('codes', {}).get(code_id, {})
        values = policy_for(code)
        self.discord_limit = discord.ui.TextInput(label='Máximo por conta Discord (1–100)', default=str(values['per_discord']), max_length=3)
        self.uid_limit = discord.ui.TextInput(label='Máximo por UID (1–100)', default=str(values['per_uid']), max_length=3)
        self.cooldown = discord.ui.TextInput(label='Cooldown em segundos (0–86400)', default=str(values['cooldown_seconds']), max_length=5)
        for field in (self.discord_limit, self.uid_limit, self.cooldown): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        async with _LOCK:
            data = load()
            code = data.get('codes', {}).get(self.code_id)
            if not code or str(code.get('guild_id')) != str(interaction.guild_id):
                return await interaction.response.send_message('Código não encontrado.', ephemeral=True)
            try:
                values = configure_limits(code, self.discord_limit.value, self.uid_limit.value, self.cooldown.value)
            except ValueError as exc:
                return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            save(data)
        await interaction.response.send_message(f'✅ Limites atualizados: Discord {values["per_discord"]}, UID {values["per_uid"]}, cooldown {values["cooldown_seconds"]}s.', ephemeral=True)

class LimitCodeSelect(discord.ui.Select):
    def __init__(self, codes):
        super().__init__(placeholder='Escolha o código para configurar limites', options=[
            discord.SelectOption(label=c['code'][:100], value=c['id']) for c in codes[:25]])

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(LimitModal(self.values[0]))

class LimitCodeView(discord.ui.View):
    def __init__(self, codes):
        super().__init__(timeout=180)
        self.add_item(LimitCodeSelect(codes))

class AvailabilityModal(discord.ui.Modal, title='Validade, estoque e período'):
    def __init__(self, code_id):
        super().__init__(timeout=300)
        self.code_id = code_id
        code = load().get('codes', {}).get(code_id, {})
        cfg = availability_policy(code)
        expiry = code.get('expires_at')
        self.expiry = discord.ui.TextInput(label='Validade UTC (vazio = sem validade)', required=False, default=expiry[:16].replace('T', ' ') if expiry else '', max_length=16)
        self.stock = discord.ui.TextInput(label='Estoque total (0 = ilimitado)', default=str(cfg['stock']), max_length=7)
        self.hours = discord.ui.TextInput(label='Janela em horas (0 = desativada)', default=str(cfg['window_hours']), max_length=4)
        self.period_limit = discord.ui.TextInput(label='Máximo por janela (0 = desativado)', default=str(cfg['window_limit']), max_length=7)
        for field in (self.expiry, self.stock, self.hours, self.period_limit): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        async with _LOCK:
            data = load()
            code = data.get('codes', {}).get(self.code_id)
            if not code or str(code.get('guild_id')) != str(interaction.guild_id):
                return await interaction.response.send_message('Código não encontrado.', ephemeral=True)
            try:
                values = configure_availability(code, self.stock.value, self.hours.value, self.period_limit.value, self.expiry.value)
            except ValueError as exc:
                return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            save(data)
        await interaction.response.send_message(f'✅ Estoque: {values["stock"] or "ilimitado"}; janela: {values["window_hours"]}h; máximo por janela: {values["window_limit"]}.', ephemeral=True)

class AvailabilityCodeSelect(discord.ui.Select):
    def __init__(self, codes):
        super().__init__(placeholder='Código para ajustar estoque e validade', options=[discord.SelectOption(label=c['code'][:100], value=c['id']) for c in codes[:25]])

    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(AvailabilityModal(self.values[0]))

class AvailabilityCodeView(discord.ui.View):
    def __init__(self, codes):
        super().__init__(timeout=180)
        self.add_item(AvailabilityCodeSelect(codes))

class CampaignCreateModal(discord.ui.Modal, title='Nova campanha promocional'):
    def __init__(self, game_key):
        super().__init__(timeout=300); self.game_key = game_key
        self.name = discord.ui.TextInput(label='Nome da campanha', max_length=80)
        self.start = discord.ui.TextInput(label='Início UTC (opcional)', placeholder='AAAA-MM-DD HH:MM', required=False)
        self.end = discord.ui.TextInput(label='Fim UTC (opcional)', placeholder='AAAA-MM-DD HH:MM', required=False)
        for field in (self.name, self.start, self.end): self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        async with _LOCK:
            data = load()
            if self.game_key not in guild_games(data, interaction.guild_id):
                return await interaction.response.send_message('Jogo indisponível.', ephemeral=True)
            try: key = create_campaign(data, interaction.guild_id, self.game_key, self.name.value, self.start.value, self.end.value)
            except ValueError as exc: return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            save(data)
        await interaction.response.send_message(f'✅ Campanha criada: **{self.name.value}** (`{key[:8]}`). Associe um código em **Recompensas / Campanhas**.', ephemeral=True)

class CampaignGameSelect(discord.ui.Select):
    def __init__(self, games):
        super().__init__(placeholder='Selecione o jogo', options=[discord.SelectOption(label=g['name'][:100], value=k) for k,g in list(games.items())[:25]])
    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(CampaignCreateModal(self.values[0]))

class CampaignGameView(discord.ui.View):
    def __init__(self, games): super().__init__(timeout=180); self.add_item(CampaignGameSelect(games))

class RewardCampaignModal(discord.ui.Modal, title='Recompensas e campanha do código'):
    def __init__(self, code_id):
        super().__init__(timeout=300); self.code_id = code_id
        self.rewards = discord.ui.TextInput(label='Recompensas (uma por linha)', style=discord.TextStyle.paragraph, max_length=1000)
        self.campaign = discord.ui.TextInput(label='ID da campanha (vazio = sem campanha)', required=False, max_length=32)
        self.add_item(self.rewards); self.add_item(self.campaign)

    async def on_submit(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        async with _LOCK:
            data = load(); code = data.get('codes', {}).get(self.code_id)
            if not code or str(code.get('guild_id')) != str(interaction.guild_id):
                return await interaction.response.send_message('Código indisponível.', ephemeral=True)
            try: items = parse_rewards(self.rewards.value)
            except ValueError as exc: return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
            cid = self.campaign.value.strip()
            if cid:
                camp = data.get('campaigns', {}).get(cid)
                if not camp or str(camp.get('guild_id')) != str(interaction.guild_id) or camp.get('game_key') != code.get('game_key'):
                    return await interaction.response.send_message('Campanha não pertence a este jogo/servidor.', ephemeral=True)
            code['reward_items'] = items
            code['reward'] = ' + '.join(items)[:500]
            code['campaign_id'] = cid or None
            save(data)
        await interaction.response.send_message('✅ Recompensas e vínculo da campanha atualizados. A API precisa suportar os itens para entregá-los.', ephemeral=True)

class RewardCodeSelect(discord.ui.Select):
    def __init__(self, codes):
        super().__init__(placeholder='Escolha um código', options=[discord.SelectOption(label=c['code'][:100], value=c['id']) for c in codes[:25]])
    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(RewardCampaignModal(self.values[0]))

class RewardCodeView(discord.ui.View):
    def __init__(self, codes): super().__init__(timeout=180); self.add_item(RewardCodeSelect(codes))

class CampaignToggleSelect(discord.ui.Select):
    def __init__(self, campaigns):
        super().__init__(placeholder='Ativar / desativar campanha', options=[discord.SelectOption(label=c['name'][:100], value=c['id'], description=('Ativa' if c['enabled'] else 'Pausada')) for c in campaigns[:25]])
    async def callback(self, interaction):
        if not authorized(interaction): return await interaction.response.send_message('Sem permissão.', ephemeral=True)
        async with _LOCK:
            data = load(); campaign = data.get('campaigns', {}).get(self.values[0])
            if not campaign or str(campaign.get('guild_id')) != str(interaction.guild_id):
                return await interaction.response.send_message('Campanha indisponível.', ephemeral=True)
            campaign['enabled'] = not campaign['enabled']; save(data)
        await interaction.response.send_message('Campanha ' + ('ativada.' if campaign['enabled'] else 'pausada.'), ephemeral=True)

class CampaignToggleView(discord.ui.View):
    def __init__(self, campaigns): super().__init__(timeout=180); self.add_item(CampaignToggleSelect(campaigns))


class AppearanceModal(discord.ui.Modal, title='Personalizar painel Redeem'):
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
        theme = get_theme(guild_id)
        self.heading = discord.ui.TextInput(label='Título do painel', default=theme['title'], max_length=180)
        self.description = discord.ui.TextInput(label='Descrição', default=theme['description'], style=discord.TextStyle.paragraph, max_length=1000)
        self.color = discord.ui.TextInput(label='Cor HEX (#RRGGBB)', default=theme['color'], max_length=7)
        self.footer = discord.ui.TextInput(label='Rodapé', default=theme['footer'], required=False, max_length=180)
        self.image = discord.ui.TextInput(label='URL da imagem (HTTPS, opcional)', default=theme['image'], required=False, max_length=500)
        for field in (self.heading, self.description, self.color, self.footer, self.image):
            self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        try:
            update_theme(interaction.guild_id, title=self.heading.value, description=self.description.value,
                         color=self.color.value, footer=self.footer.value, image=self.image.value)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await interaction.response.send_message('✅ Personalização salva. Use Pré-visualizar antes de publicar.', ephemeral=True)


class AppearanceExtrasModal(discord.ui.Modal, title='Imagem e botão Claim'):
    def __init__(self, guild_id):
        super().__init__()
        theme = get_theme(guild_id)
        self.thumbnail = discord.ui.TextInput(label='Thumbnail HTTPS (opcional)', default=theme['thumbnail'], required=False, max_length=500)
        self.claim_label = discord.ui.TextInput(label='Texto do botão Claim', default=theme['claim_label'], max_length=80)
        self.claim_emoji = discord.ui.TextInput(label='Emoji do botão (opcional)', default=theme['claim_emoji'], required=False, max_length=30)
        self.claim_style = discord.ui.TextInput(label='Estilo: green / blue / gray / red', default=theme['claim_style'], max_length=5)
        for field in (self.thumbnail, self.claim_label, self.claim_emoji, self.claim_style):
            self.add_item(field)

    async def on_submit(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        try:
            update_theme(interaction.guild_id, thumbnail=self.thumbnail.value, claim_label=self.claim_label.value,
                         claim_emoji=self.claim_emoji.value, claim_style=self.claim_style.value)
        except ValueError as exc:
            return await interaction.response.send_message(f'❌ {exc}', ephemeral=True)
        await interaction.response.send_message('✅ Configuração visual salva. Novas publicações usarão o botão atualizado.', ephemeral=True)


class AppearancePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Editar embed', emoji='🎨', style=discord.ButtonStyle.primary)
    async def edit(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(AppearanceModal(interaction.guild_id))

    @discord.ui.button(label='Imagem e botão', emoji='🖼️', style=discord.ButtonStyle.secondary)
    async def extras(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_modal(AppearanceExtrasModal(interaction.guild_id))

    @discord.ui.button(label='Pré-visualizar', emoji='👁️', style=discord.ButtonStyle.success)
    async def preview(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_message(embed=make_public_embed(interaction.guild_id),
                                                view=PublicClaimView(interaction.guild_id), ephemeral=True)

    @discord.ui.button(label='Restaurar padrão', emoji='↩️', style=discord.ButtonStyle.danger)
    async def reset(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        from modules.redeem.appearance import reset_theme
        reset_theme(interaction.guild_id)
        await interaction.response.send_message('✅ Visual padrão restaurado.', ephemeral=True)


class AuditChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder='Selecionar canal de logs', channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        channel = self.values[0]
        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return await interaction.response.send_message('O bot precisa de Enviar mensagens e Inserir links nesse canal.', ephemeral=True)
        audit_set_channel(interaction.guild_id, channel.id, interaction.user.id)
        await interaction.response.send_message(f'✅ Logs configurados em {channel.mention}.', ephemeral=True)

class AuditChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(AuditChannelSelect())

class AuditPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Configurar canal', emoji='📨', style=discord.ButtonStyle.primary)
    async def channel(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_message('Selecione o canal de logs:', view=AuditChannelView(), ephemeral=True)

    @discord.ui.button(label='Histórico recente', emoji='📜', style=discord.ButtonStyle.secondary)
    async def recent(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        events = audit_history(interaction.guild_id)
        lines = [f"`{e['at'][:16]}` • **{e['kind']}** • `{e['claim_id'][:10] or '—'}`" for e in events]
        await interaction.response.send_message('📋 **Histórico de auditoria**\n' + ('\n'.join(lines) if lines else 'Nenhum evento registrado.'), ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label='Desativar logs no canal', emoji='🔕', style=discord.ButtonStyle.danger)
    async def disable(self, interaction, button):
        if not authorized(interaction): return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        audit_set_channel(interaction.guild_id, None, interaction.user.id)
        await interaction.response.send_message('✅ Avisos no canal desativados; auditoria JSON preservada.', ephemeral=True)


class SecurityRolesSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder='Selecionar até 10 cargos administrativos', min_values=1, max_values=10)

    async def callback(self, interaction):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Apenas o dono ou quem possui Gerenciar Servidor pode alterar cargos.', ephemeral=True)
        selected = list(self.values)
        if any(r.is_default() or r.managed for r in selected):
            return await interaction.response.send_message('⛔ Não selecione @everyone nem cargos gerenciados por integrações.', ephemeral=True)
        set_roles(interaction.guild_id, [r.id for r in selected])
        await interaction.response.send_message('✅ Cargos administrativos atualizados: ' + ', '.join(r.mention for r in selected), ephemeral=True)


class SecurityPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(SecurityRolesSelect())

    @discord.ui.button(label='Consultar cargos', emoji='🔍', style=discord.ButtonStyle.secondary)
    async def show(self, interaction, button):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        ids = get_roles(interaction.guild_id)
        await interaction.response.send_message('Cargos autorizados: ' + (', '.join(f'<@&{r}>' for r in ids) if ids else 'Nenhum cargo delegado.') + '\nDono e membros com Gerenciar Servidor continuam autorizados.', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label='Remover cargos delegados', emoji='🗑️', style=discord.ButtonStyle.danger)
    async def clear(self, interaction, button):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        set_roles(interaction.guild_id, [])
        await interaction.response.send_message('✅ Cargos delegados removidos.', ephemeral=True)


class StatisticsPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    async def show(self, interaction, days):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        from modules.redeem.statistics import report, format_report
        r = report(load(), interaction.guild_id, days)
        embed = discord.Embed(title='📊 KING PLUS | Estatísticas Redeem',
                              description=format_report(r), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label='7 dias', style=discord.ButtonStyle.secondary)
    async def week(self, interaction, button):
        await self.show(interaction, 7)

    @discord.ui.button(label='30 dias', style=discord.ButtonStyle.primary)
    async def month(self, interaction, button):
        await self.show(interaction, 30)

    @discord.ui.button(label='90 dias', style=discord.ButtonStyle.secondary)
    async def quarter(self, interaction, button):
        await self.show(interaction, 90)

    @discord.ui.button(label='Tudo', style=discord.ButtonStyle.secondary)
    async def all_time(self, interaction, button):
        await self.show(interaction, 0)



class RestoreConfirm(discord.ui.View):
    def __init__(self, name, owner_id):
        super().__init__(timeout=90)
        self.name = name
        self.owner_id = owner_id

    @discord.ui.button(label='Confirmar restauração', style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if interaction.user.id != self.owner_id or not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Acesso restrito.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            # Safety snapshot before replacing any guild records.
            create_backup(interaction.guild_id)
            result = restore_backup(interaction.guild_id, self.name)
            await interaction.followup.send('✅ ' + result, ephemeral=True)
        except (ValueError, OSError) as exc:
            await interaction.followup.send(f'❌ Falha na restauração: {exc}', ephemeral=True)
        self.stop()

    @discord.ui.button(label='Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message('⛔ Acesso restrito.', ephemeral=True)
        await interaction.response.edit_message(content='Restauração cancelada.', view=None)
        self.stop()


class RestoreSelect(discord.ui.Select):
    def __init__(self, names):
        super().__init__(placeholder='Selecione um backup', min_values=1, max_values=1,
                         options=[discord.SelectOption(label=n[:100], value=n) for n in names[:15]])
    async def callback(self, interaction):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Apenas Gerenciar Servidor.', ephemeral=True)
        await interaction.response.send_message(
            '⚠️ A restauração substitui os registros deste servidor, desativa entregas e envia pendências para revisão. '
            'Credenciais não são restauradas. Confirmar?', view=RestoreConfirm(self.values[0], interaction.user.id), ephemeral=True)


class RestoreSelectView(discord.ui.View):
    def __init__(self, names):
        super().__init__(timeout=120)
        self.add_item(RestoreSelect(names))


class MaintenancePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Diagnóstico', emoji='🩺', style=discord.ButtonStyle.primary)
    async def check(self, interaction, button):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        info = diagnostics(interaction.guild_id)
        issues = info['issues']
        msg = (f"Jogos: {info['games']} | Códigos: {info['codes']} | Solicitações: {info['claims']}\n"
               + ('\n'.join('⚠️ '+i for i in issues) if issues else '✅ Nenhum problema estrutural detectado.'))
        await interaction.response.send_message(msg[:1900], ephemeral=True)

    @discord.ui.button(label='Criar backup', emoji='💾', style=discord.ButtonStyle.success)
    async def backup(self, interaction, button):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Apenas Gerenciar Servidor.', ephemeral=True)
        try:
            name = create_backup(interaction.guild_id)
            await interaction.response.send_message(f'✅ Backup local criado: `{name}`. Credenciais de API não incluídas.', ephemeral=True)
        except (ValueError, OSError) as exc:
            await interaction.response.send_message(f'❌ {exc}', ephemeral=True)

    @discord.ui.button(label='Restaurar backup', emoji='♻️', style=discord.ButtonStyle.danger)
    async def restore(self, interaction, button):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Apenas Gerenciar Servidor.', ephemeral=True)
        names = backups_for(interaction.guild_id)
        if not names:
            return await interaction.response.send_message('Nenhum backup local disponível.', ephemeral=True)
        await interaction.response.send_message('Selecione o backup local para restauração:', view=RestoreSelectView(names), ephemeral=True)


class LegacyActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def guard(self, interaction):
        if not authorized(interaction):
            await interaction.response.send_message('⛔ É necessária a permissão Gerenciar Servidor.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Adicionar jogo', emoji='🎮', style=discord.ButtonStyle.primary)
    async def add_game(self, interaction, button):
        if await self.guard(interaction):
            await interaction.response.send_modal(AddGameModal())

    @discord.ui.button(label='Gerenciar jogos', emoji='📋', style=discord.ButtonStyle.secondary)
    async def manage(self, interaction, button):
        if not await self.guard(interaction): return
        games = guild_games(load(), interaction.guild_id)
        if not games:
            return await interaction.response.send_message('Nenhum jogo cadastrado. Use **Adicionar jogo**.', ephemeral=True)
        await interaction.response.send_message('Selecione um jogo:', view=GameList(games), ephemeral=True)

    @discord.ui.button(label='Configurar API', emoji='🔌', style=discord.ButtonStyle.secondary)
    async def api(self, interaction, button):
        if await self.guard(interaction):
            games = guild_games(load(), interaction.guild_id)
            if not games: return await interaction.response.send_message('Cadastre um jogo primeiro.', ephemeral=True)
            await interaction.response.send_message('Selecione o jogo para configurar:', view=ApiGameView(games), ephemeral=True)

    @discord.ui.button(label='Códigos', emoji='🎁', style=discord.ButtonStyle.secondary)
    async def codes(self, interaction, button):
        if await self.guard(interaction):
            games = guild_games(load(), interaction.guild_id)
            if not games: return await interaction.response.send_message('Cadastre um jogo primeiro.', ephemeral=True)
            await interaction.response.send_message('Selecione o jogo:', view=CodeGameView(games), ephemeral=True)

    @discord.ui.button(label='Ativar entrega', emoji='📨', style=discord.ButtonStyle.secondary, row=2)
    async def toggle_delivery(self, interaction, button):
        if not await self.guard(interaction): return
        games = guild_games(load(), interaction.guild_id)
        if not games: return await interaction.response.send_message('Cadastre um jogo.', ephemeral=True)
        await interaction.response.send_message('Selecione o jogo para ativar/desativar a entrega:', view=DeliveryGameView(games), ephemeral=True)

    @discord.ui.button(label='Processar pendente', emoji='📦', style=discord.ButtonStyle.danger, row=2)
    async def process_delivery(self, interaction, button):
        if not await self.guard(interaction): return
        data = load()
        pending = [c for c in data.get('claims', []) if str(c.get('guild_id')) == str(interaction.guild_id) and c.get('status') == 'pending']
        if not pending: return await interaction.response.send_message('Nenhuma solicitação pendente. Solicitações em revisão não são reenviadas.', ephemeral=True)
        await interaction.response.send_message('Selecione uma solicitação para entregar (envio real à API):', view=DeliveryClaimView(pending[:25]), ephemeral=True)

    @discord.ui.button(label='Anti-duplicidade', emoji='🛡️', style=discord.ButtonStyle.secondary, row=3)
    async def limits(self, interaction, button):
        if not await self.guard(interaction): return
        data = load()
        codes = [c for c in data.get('codes', {}).values() if str(c.get('guild_id')) == str(interaction.guild_id)]
        if not codes: return await interaction.response.send_message('Crie um código antes de configurar os limites.', ephemeral=True)
        await interaction.response.send_message('Selecione um código para configurar limites:', view=LimitCodeView(codes), ephemeral=True)

    @discord.ui.button(label='Estoque e validade', emoji='📅', style=discord.ButtonStyle.secondary, row=3)
    async def availability(self, interaction, button):
        if not await self.guard(interaction): return
        data = load()
        codes = [c for c in data.get('codes', {}).values() if str(c.get('guild_id')) == str(interaction.guild_id)]
        if not codes: return await interaction.response.send_message('Cadastre um código primeiro.', ephemeral=True)
        await interaction.response.send_message('Escolha um código para configurar estoque, validade e limites por período:', view=AvailabilityCodeView(codes), ephemeral=True)

    @discord.ui.button(label='Criar campanha', emoji='🎉', style=discord.ButtonStyle.secondary, row=4)
    async def create_campaign(self, interaction, button):
        if not await self.guard(interaction): return
        games = guild_games(load(), interaction.guild_id)
        if not games: return await interaction.response.send_message('Cadastre um jogo primeiro.', ephemeral=True)
        await interaction.response.send_message('Selecione o jogo para a campanha:', view=CampaignGameView(games), ephemeral=True)

    @discord.ui.button(label='Recompensas', emoji='🎁', style=discord.ButtonStyle.secondary, row=4)
    async def rewards(self, interaction, button):
        if not await self.guard(interaction): return
        codes = list(guild_codes(load(), interaction.guild_id).values())
        if not codes: return await interaction.response.send_message('Cadastre um código primeiro.', ephemeral=True)
        data = load()
        campaigns = [c for c in data.get('campaigns', {}).values() if str(c.get('guild_id')) == str(interaction.guild_id)]
        lines = [f'`{c["id"]}` — {discord.utils.escape_markdown(c["name"])}' for c in campaigns[:12]]
        await interaction.response.send_message('Campanhas cadastradas (copie o ID completo para vincular):\n' + ('\n'.join(lines) if lines else 'Nenhuma campanha.') + '\nSelecione um código:', view=RewardCodeView(codes), ephemeral=True)

    @discord.ui.button(label='Pausar campanha', emoji='⏸️', style=discord.ButtonStyle.secondary, row=4)
    async def toggle_campaign(self, interaction, button):
        if not await self.guard(interaction): return
        campaigns = [c for c in load().get('campaigns', {}).values() if str(c.get('guild_id')) == str(interaction.guild_id)]
        if not campaigns: return await interaction.response.send_message('Nenhuma campanha cadastrada.', ephemeral=True)
        await interaction.response.send_message('Escolha a campanha:', view=CampaignToggleView(campaigns), ephemeral=True)

    @discord.ui.button(label='Personalizar', emoji='🎨', style=discord.ButtonStyle.secondary, row=3)
    async def appearance(self, interaction, button):
        if not await self.guard(interaction): return
        await interaction.response.send_message('Personalize o painel público:', view=AppearancePanel(), ephemeral=True)

    @discord.ui.button(label='Logs e histórico', emoji='📋', style=discord.ButtonStyle.secondary, row=4)
    async def audit_panel(self, interaction, button):
        if not await self.guard(interaction): return
        await interaction.response.send_message('Auditoria Redeem Codes:', view=AuditPanel(), ephemeral=True)

    @discord.ui.button(label='Segurança e cargos', emoji='🔐', style=discord.ButtonStyle.secondary, row=3)
    async def security(self, interaction, button):
        if not can_manage_roles(interaction):
            return await interaction.response.send_message('⛔ Apenas Gerenciar Servidor pode configurar cargos.', ephemeral=True)
        await interaction.response.send_message('Configure os cargos administrativos do Redeem Codes.\nOs cargos selecionados terão acesso a configurações e entregas reais da API.', view=SecurityPanel(), ephemeral=True)

    @discord.ui.button(label='Estatísticas', emoji='📊', style=discord.ButtonStyle.secondary, row=2)
    async def statistics(self, interaction, button):
        if not await self.guard(interaction): return
        await interaction.response.send_message('Escolha o período do relatório:', view=StatisticsPanel(), ephemeral=True)

    @discord.ui.button(label='Manutenção', emoji='🧰', style=discord.ButtonStyle.secondary, row=2)
    async def maintenance(self, interaction, button):
        if not await self.guard(interaction): return
        await interaction.response.send_message('Diagnóstico, backup e restauração JSON:', view=MaintenancePanel(), ephemeral=True)

    @discord.ui.button(label='Atualizar painel', emoji='🔄', style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        if await self.guard(interaction):
            await interaction.response.edit_message(embed=dashboard(interaction.guild_id), view=AdminPanel())

    @discord.ui.button(label='Publicar Claim', emoji='📢', style=discord.ButtonStyle.primary, row=1)
    async def publish(self, interaction, button):
        if not await self.guard(interaction): return
        if not interaction.channel or not interaction.channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message('Sem permissão para publicar neste canal.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.channel.send(embed=make_public_embed(interaction.guild_id), view=PublicClaimView(interaction.guild_id))
        except discord.HTTPException:
            return await interaction.followup.send('Não foi possível publicar o painel.', ephemeral=True)
        await interaction.followup.send('✅ Painel Claim publicado neste canal.', ephemeral=True)

    @discord.ui.button(label='Claim', emoji='🎟️', style=discord.ButtonStyle.success, row=1)
    async def claim(self, interaction, button):
        
        games = guild_games(load(), interaction.guild_id)
        if not games: return await interaction.response.send_message('Nenhum jogo disponível.', ephemeral=True)
        await interaction.response.send_message('Selecione seu jogo:', view=ClaimGameView(games), ephemeral=True)


# Painel único de navegação. As ações originais das 16 fases são preservadas.
PAGES = {
    'Jogos': [('Adicionar jogo', 'add_game'), ('Gerenciar jogos', 'manage')],
    'Configurar API': [('Configurar API', 'api'), ('Ativar entrega', 'toggle_delivery'), ('Processar pendente', 'process_delivery')],
    'Códigos': [('Códigos', 'codes'), ('Anti-duplicidade', 'limits'), ('Estoque e validade', 'availability')],
    'Claim': [('Publicar Claim', 'publish'), ('Testar Claim', 'claim'), ('Personalizar', 'appearance')],
    'Campanhas': [('Criar campanha', 'create_campaign'), ('Recompensas', 'rewards'), ('Pausar campanha', 'toggle_campaign')],
    'Logs': [('Logs e histórico', 'audit_panel')],
    'Estatísticas': [('Estatísticas', 'statistics')],
    'Configurações': [('Segurança e cargos', 'security'), ('Manutenção', 'maintenance'), ('Personalizar', 'appearance')],
}

class PageAction(discord.ui.Button):
    def __init__(self, label, method, row):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.method = method

    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        # Reutiliza o callback original em vez de reimplementar a lógica das fases.
        old_view = LegacyActions()
        old_button = next((b for b in old_view.children if getattr(getattr(b.callback, 'callback', None), '__name__', '') == self.method), None)
        if old_button is None:
            return await interaction.response.send_message('Ação indisponível.', ephemeral=True)
        await old_button.callback(interaction)

class PageBack(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Voltar', emoji='↩️', style=discord.ButtonStyle.secondary, row=4)
    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.edit_message(embed=dashboard(interaction.guild_id), view=AdminPanel())

class PageView(discord.ui.View):
    def __init__(self, page):
        super().__init__(timeout=300)
        for index, (label, method) in enumerate(PAGES[page]):
            self.add_item(PageAction(label, method, index // 5))
        self.add_item(PageBack())

class NavButton(discord.ui.Button):
    def __init__(self, page, row):
        super().__init__(label=page, style=discord.ButtonStyle.primary if page == 'Jogos' else discord.ButtonStyle.secondary, row=row)
        self.page = page
    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        embed = discord.Embed(title=f'🎁 KING PLUS — {self.page}',
                              description='Selecione uma funcionalidade abaixo.', color=discord.Color.blurple())
        await interaction.response.edit_message(embed=embed, view=PageView(self.page))

class CentralButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label='Central', emoji='🏠', style=discord.ButtonStyle.secondary, row=4)
    async def callback(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.edit_message(embed=dashboard(interaction.guild_id), view=AdminPanel())

class AdminPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        for index, page in enumerate(PAGES):
            self.add_item(NavButton(page, index // 2))
        self.add_item(CentralButton())


class RedeemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(PublicClaimView())

    @app_commands.command(name='redeem', description='Abre o painel Redeem Codes KING PLUS')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def redeem(self, interaction):
        if not authorized(interaction):
            return await interaction.response.send_message('⛔ Sem permissão.', ephemeral=True)
        await interaction.response.send_message(embed=dashboard(interaction.guild_id), view=AdminPanel(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(RedeemCog(bot))
