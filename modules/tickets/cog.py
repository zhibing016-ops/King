import discord
from discord import app_commands
from discord.ext import commands, tasks
from modules.tickets.config.storage import get_config, update_config
from modules.tickets.config.category_store import list_categories, add_category, update_category
from modules.tickets.config.form_store import get_questions, modify_questions
from modules.tickets.config.ticket_store import get_open, save_open, remove_open, find_ticket, set_assignee, set_ticket_status
from modules.tickets.services.transcripts import build_transcript, send_to_logs
from modules.tickets.config.limit_store import get_limits, configure_limits, remaining_cooldown, record_open
from modules.tickets.config.stats_store import record_event, record_assignee, submit_rating, get_report
import asyncio
from modules.tickets.config.automation_store import (
    get_settings as get_automation_settings, update_settings as update_automation_settings,
    mark_activity, due_reminders, mark_reminded
)
from modules.tickets.config.ticket_store import list_open_tickets
from modules.tickets.config.attention_store import set_priority, add_note, get_attention

def panel_embed(cfg):
    enabled = cfg.get("enabled", True)
    embed = discord.Embed(
        title="👑 KING PLUS • Central de Tickets",
        description="**Fase 16/16 — Sistema completo de tickets**\\nConfigure o atendimento usando os controles abaixo.",
        color=discord.Color.green() if enabled else discord.Color.orange()
    )
    embed.add_field(name="Sistema", value="🟢 Ativado" if enabled else "🔴 Em manutenção", inline=False)
    embed.add_field(name="Canal do painel", value=f"<#{cfg['panel_channel_id']}>" if cfg.get("panel_channel_id") else "Não definido")
    embed.add_field(name="Categoria dos tickets", value=f"<#{cfg['ticket_category_id']}>" if cfg.get("ticket_category_id") else "Não definida")
    embed.add_field(name="Canal de logs", value=f"<#{cfg['log_channel_id']}>" if cfg.get("log_channel_id") else "Não definido")
    embed.add_field(name="Cargo de suporte", value=f"<@&{cfg['support_role_id']}>" if cfg.get("support_role_id") else "Não definido")
    embed.set_footer(text="KING PLUS • Tickets • Configuração dentro do Discord.")
    return embed

class PanelTextModal(discord.ui.Modal, title="Personalizar painel"):
    panel_title = discord.ui.TextInput(label="Título do painel", max_length=100, required=True)
    panel_description = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    def __init__(self, cfg):
        super().__init__()
        self.panel_title.default = cfg.get("panel_title", "🎫 Abra seu ticket")
        self.panel_description.default = cfg.get("panel_description", "Clique no botão para falar com a equipe.")
    async def on_submit(self, interaction):
        await update_config(interaction.guild_id, panel_title=str(self.panel_title), panel_description=str(self.panel_description))
        await interaction.response.send_message("✅ Textos salvos no JSON.", ephemeral=True)

class AdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você precisa da permissão Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ativar", style=discord.ButtonStyle.success, row=0)
    async def activate(self, interaction, button):
        cfg = await update_config(interaction.guild_id, enabled=True)
        await interaction.response.edit_message(embed=panel_embed(cfg), view=self)

    @discord.ui.button(label="Desativar", style=discord.ButtonStyle.danger, row=0)
    async def deactivate(self, interaction, button):
        cfg = await update_config(interaction.guild_id, enabled=False)
        await interaction.response.edit_message(embed=panel_embed(cfg), view=self)

    @discord.ui.button(label="Atualizar status", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(embed=panel_embed(await get_config(interaction.guild_id)), view=self)

    @discord.ui.button(label="Personalizar textos", style=discord.ButtonStyle.primary, row=1)
    async def customize(self, interaction, button):
        await interaction.response.send_modal(PanelTextModal(await get_config(interaction.guild_id)))

    @discord.ui.button(label="Pré-visualizar", style=discord.ButtonStyle.secondary, row=1)
    async def preview(self, interaction, button):
        cfg = await get_config(interaction.guild_id)
        await interaction.response.send_message(embed=public_embed(cfg), view=public_view(cfg), ephemeral=True)

class AppearanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão para configurar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Cores, imagens e rodapé", style=discord.ButtonStyle.primary)
    async def visual(self, interaction, button):
        await interaction.response.send_modal(VisualModal(await get_config(interaction.guild_id)))

    @discord.ui.button(label="Texto, emoji e cor do botão", style=discord.ButtonStyle.secondary)
    async def button_look(self, interaction, button):
        await interaction.response.send_modal(ButtonModal(await get_config(interaction.guild_id)))


class ConfigChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, key, label, channel_types):
        super().__init__(placeholder=label, min_values=1, max_values=1, channel_types=channel_types)
        self.key = key
    async def callback(self, interaction):
        channel = self.values[0]
        await update_config(interaction.guild_id, **{self.key: channel.id})
        await interaction.response.send_message(f"✅ {channel.mention} configurado.", ephemeral=True)

class ConfigRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="Selecionar cargo da equipe de suporte", min_values=1, max_values=1)
    async def callback(self, interaction):
        role = self.values[0]
        await update_config(interaction.guild_id, support_role_id=role.id)
        await interaction.response.send_message(f"✅ Cargo {role.mention} configurado.", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ConfigChannelSelect("panel_channel_id", "Canal do painel público", [discord.ChannelType.text]))
        self.add_item(ConfigChannelSelect("ticket_category_id", "Categoria para tickets", [discord.ChannelType.category]))
        self.add_item(ConfigChannelSelect("log_channel_id", "Canal de logs", [discord.ChannelType.text]))
        self.add_item(ConfigRoleSelect())
    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão para configurar.", ephemeral=True)
            return False
        return True

# Locks prevent two concurrent button presses from creating duplicate channels.
_open_locks = {}

async def create_ticket(interaction, category, answers):
    guild = interaction.guild
    if guild is None:
        await interaction.followup.send("Este botão funciona apenas em servidores.", ephemeral=True)
        return
    lock = _open_locks.setdefault((guild.id, interaction.user.id), asyncio.Lock())
    async with lock:
        cfg = await get_config(guild.id)
        if not cfg.get("enabled", True):
            await interaction.followup.send("🔧 Tickets em manutenção.", ephemeral=True)
            return
        existing = await get_open(guild.id, interaction.user.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                await interaction.followup.send(f"Você já possui um ticket aberto: {channel.mention}", ephemeral=True)
                return
            await remove_open(guild.id, interaction.user.id)
        wait = await remaining_cooldown(guild.id, interaction.user.id)
        if wait:
            await interaction.followup.send(
                f"⏳ Aguarde {wait} segundos antes de abrir outro ticket.", ephemeral=True)
            return
        category_channel = guild.get_channel(int(cfg["ticket_category_id"])) if cfg.get("ticket_category_id") else None
        if not isinstance(category_channel, discord.CategoryChannel):
            await interaction.followup.send("A categoria de canais ainda não foi configurada em `/ticket`.", ephemeral=True)
            return
        me = guild.me
        if me is None or not guild.me.guild_permissions.manage_channels:
            await interaction.followup.send("O bot precisa da permissão Gerenciar Canais.", ephemeral=True)
            return
        role_ids = set(cfg.get("support_role_ids", []))
        if cfg.get("support_role_id"):
            role_ids.add(int(cfg["support_role_id"]))
        roles = [r for rid in role_ids if (r := guild.get_role(int(rid))) is not None]
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        for role in roles:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        name = f"ticket-{interaction.user.id}"[:90]
        try:
            channel = await guild.create_text_channel(
                name, category=category_channel, overwrites=overwrites,
                topic=f"KING PLUS | Dono: {interaction.user.id} | Tipo: {category['key']}",
                reason=f"Ticket solicitado por {interaction.user} ({interaction.user.id})"
            )
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Não foi possível criar o canal. Verifique permissões e posição do cargo do bot.", ephemeral=True)
            return
        await save_open(guild.id, interaction.user.id, channel.id, category["key"])
        await record_event(guild.id, channel.id, interaction.user.id, "opened", interaction.user.id)
        await record_open(guild.id, interaction.user.id)
        await mark_activity(guild.id, channel.id)
        embed = discord.Embed(title=f"{category.get('emoji','🎫')} {category['name']}",
                              description=f"Ticket aberto por {interaction.user.mention}\\n{category['description']}",
                              color=discord.Color.blurple())
        for question, answer in answers:
            embed.add_field(name=question[:256], value=(answer or "Não informado")[:1024], inline=False)
        try:
            await channel.send(content=(" ".join(r.mention for r in roles) or None), embed=embed, view=TicketManageView(),
                               allowed_mentions=discord.AllowedMentions(roles=True, users=False))
        except discord.HTTPException:
            pass
        auto = await get_automation_settings(guild.id)
        if auto["enabled"] and auto["welcome_message"]:
            try:
                await channel.send(auto["welcome_message"],
                                   allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
        await interaction.followup.send(f"✅ Ticket criado: {channel.mention}", ephemeral=True)


class TicketFormModal(discord.ui.Modal):
    def __init__(self, category, questions):
        super().__init__(title=f"Ticket: {category['name']}"[:45])
        self.category = category
        self.fields = []
        for i, q in enumerate(questions[:5]):
            field = discord.ui.TextInput(
                label=q["label"][:45], placeholder=q.get("placeholder") or None,
                required=q.get("required", True),
                style=discord.TextStyle.paragraph if q.get("long") else discord.TextStyle.short,
                custom_id=f"ticket_answer_{i}"
            )
            self.add_item(field)
            self.fields.append((q["label"], field))

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await create_ticket(interaction, self.category,
                            [(label, str(field.value)) for label, field in self.fields])


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, categories):
        super().__init__(placeholder="Escolha o tipo de atendimento",
                         options=[discord.SelectOption(
                             label=c["name"][:100], value=c["key"],
                             description=c["description"][:100]) for c in categories[:20]])
        self.categories = {c["key"]: c for c in categories}

    async def callback(self, interaction):
        cfg = await get_config(interaction.guild_id)
        if not cfg.get("enabled", True):
            await interaction.response.send_message("🔧 Tickets em manutenção.", ephemeral=True)
            return
        category = self.categories[self.values[0]]
        current = await list_categories(interaction.guild_id)
        if not any(c["key"] == category["key"] and c.get("enabled", True) for c in current):
            await interaction.response.send_message("Categoria indisponível.", ephemeral=True)
            return
        questions = await get_questions(interaction.guild_id, category["key"])
        if questions:
            await interaction.response.send_modal(TicketFormModal(category, questions))
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await create_ticket(interaction, category, [])


class TicketCategoryView(discord.ui.View):
    def __init__(self, categories):
        super().__init__(timeout=180)
        self.add_item(TicketCategorySelect(categories))


class PublicTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir ticket", emoji="🎫", style=discord.ButtonStyle.primary,
                       custom_id="kingplus:tickets:public:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            await interaction.response.send_message("Disponível apenas no servidor.", ephemeral=True)
            return
        cfg = await get_config(interaction.guild_id)
        if not cfg.get("enabled", True):
            await interaction.response.send_message("🔧 Tickets em manutenção.", ephemeral=True)
            return
        categories = [c for c in await list_categories(interaction.guild_id) if c.get("enabled", True)]
        if not categories:
            await interaction.response.send_message("Nenhuma categoria de atendimento ativa. Avise a equipe.", ephemeral=True)
            return
        await interaction.response.send_message("Selecione a categoria do seu ticket:",
                                                view=TicketCategoryView(categories), ephemeral=True)


def public_embed(cfg):
    raw = cfg.get("panel_color", "5865F2").lstrip("#")
    try:
        color = int(raw, 16)
        if not 0 <= color <= 0xFFFFFF:
            raise ValueError
    except (ValueError, TypeError):
        color = 0x5865F2
    embed = discord.Embed(
        title=cfg.get("panel_title") or "🎫 Abra seu ticket",
        description=cfg.get("panel_description") or "Clique no botão abaixo para iniciar um atendimento.",
        color=color,
    )
    if cfg.get("panel_image"):
        embed.set_image(url=cfg["panel_image"])
    if cfg.get("panel_thumbnail"):
        embed.set_thumbnail(url=cfg["panel_thumbnail"])
    embed.set_footer(text=cfg.get("panel_footer") or "KING PLUS • Central de Atendimento")
    return embed


class VisualModal(discord.ui.Modal, title="Visual do painel"):
    color = discord.ui.TextInput(label="Cor HEX (ex.: 5865F2)", max_length=7)
    image = discord.ui.TextInput(label="URL da imagem (opcional)", required=False, max_length=400)
    thumbnail = discord.ui.TextInput(label="URL da miniatura (opcional)", required=False, max_length=400)
    footer = discord.ui.TextInput(label="Rodapé", required=False, max_length=200)

    def __init__(self, cfg):
        super().__init__()
        self.color.default = cfg.get("panel_color", "5865F2")
        self.image.default = cfg.get("panel_image", "")
        self.thumbnail.default = cfg.get("panel_thumbnail", "")
        self.footer.default = cfg.get("panel_footer", "KING PLUS • Central de Atendimento")

    async def on_submit(self, interaction):
        from urllib.parse import urlparse
        color = str(self.color).strip().lstrip("#")
        try:
            if len(color) != 6 or not 0 <= int(color, 16) <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Cor inválida. Use seis dígitos HEX, como 5865F2.", ephemeral=True)
            return
        image, thumbnail = str(self.image).strip(), str(self.thumbnail).strip()
        for url in (image, thumbnail):
            if url:
                parsed = urlparse(url)
                if parsed.scheme != "https" or not parsed.netloc or len(url) > 400:
                    await interaction.response.send_message("❌ Use URLs HTTPS válidas para as imagens.", ephemeral=True)
                    return
        await update_config(interaction.guild_id, panel_color=color.upper(), panel_image=image,
                            panel_thumbnail=thumbnail, panel_footer=str(self.footer))
        await interaction.response.send_message("✅ Aparência salva. Use Pré-visualizar ou /ticket-publicar para atualizar o painel.", ephemeral=True)


class ButtonModal(discord.ui.Modal, title="Botão do painel"):
    label = discord.ui.TextInput(label="Texto do botão", max_length=80)
    emoji = discord.ui.TextInput(label="Emoji Unicode (opcional)", required=False, max_length=16)
    style = discord.ui.TextInput(label="Estilo: azul, cinza, verde ou vermelho", max_length=12)

    def __init__(self, cfg):
        super().__init__()
        self.label.default = cfg.get("button_label", "Abrir ticket")
        self.emoji.default = cfg.get("button_emoji", "🎫")
        self.style.default = cfg.get("button_style", "azul")

    async def on_submit(self, interaction):
        style = str(self.style).strip().lower()
        if style not in {"azul", "cinza", "verde", "vermelho"}:
            await interaction.response.send_message("❌ Estilo inválido. Use azul, cinza, verde ou vermelho.", ephemeral=True)
            return
        label = str(self.label).strip()
        if not label:
            await interaction.response.send_message("❌ Informe um texto para o botão.", ephemeral=True)
            return
        emoji = str(self.emoji).strip()
        try:
            discord.PartialEmoji.from_str(emoji) if emoji else None
        except ValueError:
            await interaction.response.send_message("❌ Emoji inválido.", ephemeral=True)
            return
        await update_config(interaction.guild_id, button_label=label, button_emoji=emoji,
                            button_style=style)
        await interaction.response.send_message("✅ Botão salvo. Atualize o painel com /ticket-publicar.", ephemeral=True)


def public_view(cfg):
    view = PublicTicketView()
    button = view.children[0]
    button.label = cfg.get("button_label") or "Abrir ticket"
    emoji = cfg.get("button_emoji", "🎫")
    button.emoji = discord.PartialEmoji.from_str(emoji) if emoji else None
    button.style = {
        "azul": discord.ButtonStyle.primary,
        "cinza": discord.ButtonStyle.secondary,
        "verde": discord.ButtonStyle.success,
        "vermelho": discord.ButtonStyle.danger,
    }.get(cfg.get("button_style"), discord.ButtonStyle.primary)
    return view



class CategoryModal(discord.ui.Modal, title="Criar categoria de atendimento"):
    name = discord.ui.TextInput(label="Nome (ex.: Suporte)", min_length=2, max_length=60)
    description = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=300)
    emoji = discord.ui.TextInput(label="Emoji (opcional)", required=False, max_length=20)

    async def on_submit(self, interaction):
        try:
            item = await add_category(interaction.guild_id, str(self.name), str(self.description), str(self.emoji))
        except ValueError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Categoria **{item['name']}** criada.", ephemeral=True)


class CategorySelect(discord.ui.Select):
    def __init__(self, categories, action):
        options = [
            discord.SelectOption(label=c["name"][:100], value=c["key"],
                                 description=("Ativa" if c.get("enabled", True) else "Desativada"))
            for c in categories[:20]
        ]
        super().__init__(placeholder="Selecione a categoria", options=options)
        self.action = action

    async def callback(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        try:
            await update_category(interaction.guild_id, self.values[0], self.action)
        except ValueError as error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return
        await interaction.response.send_message("✅ Categoria atualizada no JSON.", ephemeral=True)


class CategoryActionView(discord.ui.View):
    def __init__(self, categories, action):
        super().__init__(timeout=180)
        self.add_item(CategorySelect(categories, action))


class CategoriesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Criar categoria", style=discord.ButtonStyle.success)
    async def create(self, interaction, button):
        await interaction.response.send_modal(CategoryModal())

    @discord.ui.button(label="Listar categorias", style=discord.ButtonStyle.primary)
    async def show(self, interaction, button):
        items = await list_categories(interaction.guild_id)
        content = "\\n".join(
            f"{c['emoji']} **{c['name']}** — {'Ativa' if c.get('enabled', True) else 'Desativada'}\\n{c['description']}"
            for c in items
        ) if items else "Nenhuma categoria cadastrada."
        await interaction.response.send_message(content[:1900], ephemeral=True)

    @discord.ui.button(label="Ativar / Desativar", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction, button):
        items = await list_categories(interaction.guild_id)
        if not items:
            await interaction.response.send_message("Nenhuma categoria cadastrada.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha uma categoria:", view=CategoryActionView(items, "toggle"), ephemeral=True)

    @discord.ui.button(label="Excluir categoria", style=discord.ButtonStyle.danger)
    async def delete(self, interaction, button):
        items = await list_categories(interaction.guild_id)
        if not items:
            await interaction.response.send_message("Nenhuma categoria cadastrada.", ephemeral=True)
            return
        await interaction.response.send_message("⚠️ Selecione a categoria a excluir:", view=CategoryActionView(items, "delete"), ephemeral=True)



class QuestionModal(discord.ui.Modal, title="Adicionar pergunta ao formulário"):
    label = discord.ui.TextInput(label="Pergunta", max_length=45)
    placeholder = discord.ui.TextInput(label="Texto de exemplo", max_length=100, required=False)
    required_answer = discord.ui.TextInput(label="Obrigatória? (sim/não)", default="sim", max_length=3)
    long_answer = discord.ui.TextInput(label="Resposta longa? (sim/não)", default="não", max_length=3)

    def __init__(self, category_key):
        super().__init__()
        self.category_key = category_key

    async def on_submit(self, interaction):
        required = str(self.required_answer).strip().lower()
        long = str(self.long_answer).strip().lower()
        if required not in ("sim", "não", "nao") or long not in ("sim", "não", "nao"):
            await interaction.response.send_message("Use sim ou não nas opções.", ephemeral=True)
            return
        try:
            await modify_questions(interaction.guild_id, self.category_key, "add", question={
                "label": str(self.label), "placeholder": str(self.placeholder),
                "required": required == "sim", "long": long == "sim"
            })
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message("✅ Pergunta adicionada ao formulário JSON.", ephemeral=True)


class PreviewFormModal(discord.ui.Modal):
    def __init__(self, category_name, questions):
        super().__init__(title=f"Prévia: {category_name}"[:45])
        for index, q in enumerate(questions):
            self.add_item(discord.ui.TextInput(
                label=q["label"][:45],
                placeholder=q.get("placeholder") or None,
                required=q.get("required", True),
                style=discord.TextStyle.paragraph if q.get("long") else discord.TextStyle.short,
                custom_id=f"preview_question_{index}"
            ))

    async def on_submit(self, interaction):
        await interaction.response.send_message(
            "✅ Prévia recebida. As respostas **não foram registradas nem enviadas à equipe**. "
            "O envio real será conectado à abertura de tickets na Fase 7.", ephemeral=True
        )


class FormCategorySelect(discord.ui.Select):
    def __init__(self, categories, action):
        super().__init__(placeholder="Escolha a categoria", options=[
            discord.SelectOption(label=c["name"][:100], value=c["key"])
            for c in categories[:20]
        ])
        self.action = action
        self.categories = {c["key"]: c for c in categories}

    async def callback(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        key = self.values[0]
        questions = await get_questions(interaction.guild_id, key)
        if self.action == "add":
            await interaction.response.send_modal(QuestionModal(key))
        elif self.action == "preview":
            if not questions:
                await interaction.response.send_message("Adicione pelo menos uma pergunta antes da prévia.", ephemeral=True)
                return
            await interaction.response.send_modal(PreviewFormModal(self.categories[key]["name"], questions))
        elif self.action == "show":
            lines = [f"**{i+1}. {q['label']}** — {'Obrigatória' if q.get('required') else 'Opcional'}"
                     for i, q in enumerate(questions)]
            await interaction.response.send_message("\n".join(lines) if lines else "Formulário vazio.", ephemeral=True)
        elif self.action == "remove":
            if not questions:
                await interaction.response.send_message("Formulário vazio.", ephemeral=True)
                return
            await interaction.response.send_message("Escolha a pergunta para excluir:",
                view=RemoveQuestionView(key, questions), ephemeral=True)


class RemoveQuestionSelect(discord.ui.Select):
    def __init__(self, key, questions):
        super().__init__(placeholder="Excluir pergunta", options=[
            discord.SelectOption(label=q["label"][:100], value=str(i))
            for i, q in enumerate(questions)
        ])
        self.key = key

    async def callback(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        try:
            await modify_questions(interaction.guild_id, self.key, "remove", index=int(self.values[0]))
            await interaction.response.send_message("✅ Pergunta excluída.", ephemeral=True)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)


class RemoveQuestionView(discord.ui.View):
    def __init__(self, key, questions):
        super().__init__(timeout=180)
        self.add_item(RemoveQuestionSelect(key, questions))


class FormCategoryView(discord.ui.View):
    def __init__(self, categories, action):
        super().__init__(timeout=180)
        self.add_item(FormCategorySelect(categories, action))


class FormsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return False
        return True

    async def choose(self, interaction, action):
        categories = await list_categories(interaction.guild_id)
        if not categories:
            await interaction.response.send_message("Crie uma categoria em `/ticket-categorias` primeiro.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha a categoria:",
                                                view=FormCategoryView(categories, action), ephemeral=True)

    @discord.ui.button(label="Adicionar pergunta", style=discord.ButtonStyle.success)
    async def add(self, interaction, button):
        await self.choose(interaction, "add")

    @discord.ui.button(label="Listar perguntas", style=discord.ButtonStyle.primary)
    async def show(self, interaction, button):
        await self.choose(interaction, "show")

    @discord.ui.button(label="Remover pergunta", style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        await self.choose(interaction, "remove")

    @discord.ui.button(label="Pré-visualizar modal", style=discord.ButtonStyle.secondary)
    async def preview(self, interaction, button):
        await self.choose(interaction, "preview")



class SupportRoleSelect(discord.ui.RoleSelect):
    def __init__(self, action):
        super().__init__(placeholder="Selecione um cargo de suporte", min_values=1, max_values=1)
        self.action = action

    async def callback(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        role = self.values[0]
        if role.is_default() or role.managed:
            await interaction.response.send_message("Escolha um cargo normal, não @everyone ou cargo gerenciado.", ephemeral=True)
            return
        cfg = await get_config(interaction.guild_id)
        roles = set(int(x) for x in cfg.get("support_role_ids", []))
        if cfg.get("support_role_id"):
            roles.add(int(cfg["support_role_id"]))
        if self.action == "add":
            if len(roles) >= 10 and role.id not in roles:
                await interaction.response.send_message("Limite de 10 cargos de suporte.", ephemeral=True)
                return
            roles.add(role.id)
        else:
            roles.discard(role.id)
        await update_config(interaction.guild_id, support_role_ids=sorted(roles), support_role_id=None)
        await interaction.response.send_message(
            f"✅ Cargo {role.mention} {'adicionado' if self.action == 'add' else 'removido'}. "
            "A alteração vale automaticamente para novos tickets. Use Sincronizar para tickets existentes.",
            ephemeral=True)


class SupportRoleView(discord.ui.View):
    def __init__(self, action):
        super().__init__(timeout=180)
        self.add_item(SupportRoleSelect(action))


class SupportAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Requer Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Adicionar cargo", style=discord.ButtonStyle.success)
    async def add(self, interaction, button):
        await interaction.response.send_message("Escolha o cargo:", view=SupportRoleView("add"), ephemeral=True)

    @discord.ui.button(label="Remover cargo", style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        await interaction.response.send_message("Escolha o cargo:", view=SupportRoleView("remove"), ephemeral=True)

    @discord.ui.button(label="Listar equipe", style=discord.ButtonStyle.secondary)
    async def listing(self, interaction, button):
        cfg = await get_config(interaction.guild_id)
        ids = set(int(x) for x in cfg.get("support_role_ids", []))
        if cfg.get("support_role_id"):
            ids.add(int(cfg["support_role_id"]))
        await interaction.response.send_message(
            "**Cargos de suporte:**\n" + ("\n".join(f"• <@&{x}>" for x in sorted(ids)) or "Nenhum cadastrado."),
            ephemeral=True)

    @discord.ui.button(label="Sincronizar tickets", style=discord.ButtonStyle.primary, row=1)
    async def sync(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        from modules.tickets.config.ticket_store import list_open_tickets
        cfg = await get_config(interaction.guild_id)
        ids = set(int(x) for x in cfg.get("support_role_ids", []))
        if cfg.get("support_role_id"):
            ids.add(int(cfg["support_role_id"]))
        roles = [r for rid in ids if (r := interaction.guild.get_role(rid))]
        entries = await list_open_tickets(interaction.guild_id)
        ok = failed = 0
        for entry in entries:
            channel = interaction.guild.get_channel(entry["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                # Remove obsolete configured support overwrites only for roles
                # previously synchronized by this tool, preserving manual ACLs.
                from modules.tickets.config.support_store import get_synced, set_synced
                previous = await get_synced(interaction.guild_id, channel.id)
                for rid in previous - ids:
                    role = interaction.guild.get_role(rid)
                    if role:
                        await channel.set_permissions(role, overwrite=None, reason="KING PLUS: remover acesso de suporte")
                for role in roles:
                    await channel.set_permissions(role, view_channel=True, send_messages=True,
                                                  read_message_history=True,
                                                  reason="KING PLUS: sincronizar suporte")
                await set_synced(interaction.guild_id, channel.id, ids)
                ok += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
        await interaction.followup.send(f"Sincronização concluída: {ok} tickets; {failed} falhas.", ephemeral=True)


async def can_manage_ticket(interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.manage_channels:
        return True
    cfg = await get_config(interaction.guild_id)
    ids = {int(v) for v in cfg.get("support_role_ids", [])}
    if cfg.get("support_role_id"):
        ids.add(int(cfg["support_role_id"]))
    return any(role.id in ids for role in interaction.user.roles)


class MemberActionSelect(discord.ui.UserSelect):
    def __init__(self, action):
        super().__init__(placeholder="Selecione o membro", min_values=1, max_values=1)
        self.action = action

    async def callback(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Somente a equipe pode gerenciar tickets.", ephemeral=True)
            return
        owner_id, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record:
            await interaction.response.send_message("Este canal não é um ticket registrado.", ephemeral=True)
            return
        member = self.values[0]
        if self.action == "remove" and member.id == owner_id:
            await interaction.response.send_message("Não é permitido remover o dono do ticket.", ephemeral=True)
            return
        try:
            if self.action == "add":
                await interaction.channel.set_permissions(member, view_channel=True, send_messages=True,
                    read_message_history=True, reason=f"Ticket: adicionado por {interaction.user}")
            else:
                await interaction.channel.set_permissions(member, overwrite=None,
                    reason=f"Ticket: removido por {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("Não consegui alterar as permissões.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ {member.mention} {'adicionado ao' if self.action == 'add' else 'removido do'} ticket.",
            ephemeral=True)


class MemberActionView(discord.ui.View):
    def __init__(self, action):
        super().__init__(timeout=180)
        self.add_item(MemberActionSelect(action))


class TicketManageView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Apenas atendentes autorizados.", ephemeral=True)
            return False
        owner, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("Ticket não registrado.", ephemeral=True)
            return False
        if ticket.get("status", "open") == "closed":
            await interaction.response.send_message("Ticket fechado. Reabra antes de gerenciar.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Assumir", emoji="🙋", style=discord.ButtonStyle.success,
                       custom_id="kingplus:tickets:manage:claim")
    async def claim(self, interaction, button):
        _, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if ticket.get("assignee_id"):
            await interaction.response.send_message(
                f"Este ticket já foi assumido por <@{ticket['assignee_id']}>. Use Transferir.", ephemeral=True)
            return
        await set_assignee(interaction.guild_id, interaction.channel_id, interaction.user.id)
        await record_assignee(interaction.guild_id, interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"🙋 Atendimento assumido por {interaction.user.mention}.")

    @discord.ui.button(label="Transferir", emoji="🔁", style=discord.ButtonStyle.primary,
                       custom_id="kingplus:tickets:manage:transfer")
    async def transfer(self, interaction, button):
        await interaction.response.send_message("Selecione o novo atendente:",
            view=TransferView(), ephemeral=True)

    @discord.ui.button(label="Adicionar membro", style=discord.ButtonStyle.secondary,
                       custom_id="kingplus:tickets:manage:add")
    async def add(self, interaction, button):
        await interaction.response.send_message("Selecione o participante:",
            view=MemberActionView("add"), ephemeral=True)

    @discord.ui.button(label="Remover membro", style=discord.ButtonStyle.secondary,
                       custom_id="kingplus:tickets:manage:remove")
    async def remove(self, interaction, button):
        await interaction.response.send_message("Selecione o participante:",
            view=MemberActionView("remove"), ephemeral=True)


class TransferSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Novo atendente", min_values=1, max_values=1)

    async def callback(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        member = self.values[0]
        if not isinstance(member, discord.Member):
            member = interaction.guild.get_member(member.id)
        if not member or member.bot:
            await interaction.response.send_message("Selecione um membro humano do servidor.", ephemeral=True)
            return
        cfg = await get_config(interaction.guild_id)
        ids = {int(v) for v in cfg.get("support_role_ids", [])}
        if cfg.get("support_role_id"):
            ids.add(int(cfg["support_role_id"]))
        if not (member.guild_permissions.manage_channels or any(r.id in ids for r in member.roles)):
            await interaction.response.send_message("Esse membro não pertence à equipe de suporte.", ephemeral=True)
            return
        owner, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("Ticket não encontrado.", ephemeral=True)
            return
        await set_assignee(interaction.guild_id, interaction.channel_id, member.id)
        await record_assignee(interaction.guild_id, interaction.channel_id, member.id)
        await interaction.response.send_message(f"🔁 Ticket transferido para {member.mention}.")


class TransferView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(TransferSelect())



class CloseReasonModal(discord.ui.Modal, title="Fechar ticket"):
    reason = discord.ui.TextInput(label="Motivo do encerramento", style=discord.TextStyle.paragraph,
                                  max_length=500, required=True)
    async def on_submit(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        owner, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record or record.get("status", "open") == "closed":
            await interaction.response.send_message("Ticket inexistente ou já fechado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            member = interaction.guild.get_member(owner)
            if member:
                await interaction.channel.set_permissions(member, view_channel=True,
                    send_messages=False, read_message_history=True,
                    reason=f"Ticket fechado por {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Falha ao restringir o canal; ticket permanece aberto.", ephemeral=True)
            return
        await set_ticket_status(interaction.guild_id, interaction.channel_id,
                                "closed", interaction.user.id, str(self.reason))
        await record_event(interaction.guild_id, interaction.channel_id, owner,
                           "closed", interaction.user.id, record.get("assignee_id"))
        await interaction.channel.send(
            f"🔒 Ticket fechado por {interaction.user.mention}. Motivo: {self.reason}",
            allowed_mentions=discord.AllowedMentions.none())
        try:
            await send_to_logs(interaction.channel, interaction.user, str(self.reason))
        except (discord.Forbidden, discord.HTTPException, OSError) as exc:
            await interaction.followup.send(
                f"⚠️ Ticket fechado, mas não foi possível enviar a transcrição aos logs: {type(exc).__name__}.",
                ephemeral=True)
        await interaction.followup.send("Ticket fechado. Use `/ticket-fechamento` para reabrir ou excluir.", ephemeral=True)


class DeleteTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Confirmar exclusão", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        owner, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record or record.get("status") != "closed":
            await interaction.response.send_message("Apenas tickets fechados podem ser excluídos.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            delivered = await send_to_logs(interaction.channel, interaction.user, "Exclusão do canal")
        except (discord.Forbidden, discord.HTTPException, OSError):
            delivered = False
        if not delivered:
            await interaction.followup.send(
                "❌ Exclusão cancelada: configure o canal de logs e permita envio de arquivos "
                "para preservar a transcrição.", ephemeral=True)
            return
        try:
            await interaction.channel.delete(reason=f"Ticket excluído por {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Falha ao excluir o canal.", ephemeral=True)
            return
        await remove_open(interaction.guild_id, owner, interaction.channel_id)
        await record_event(interaction.guild_id, interaction.channel_id, owner,
                           "deleted", interaction.user.id, record.get("assignee_id"))


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    async def interaction_check(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Apenas a equipe de suporte.", ephemeral=True)
            return False
        owner, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record:
            await interaction.response.send_message("Este canal não é um ticket registrado.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger)
    async def close(self, interaction, button):
        _, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if record.get("status", "open") == "closed":
            await interaction.response.send_message("Ticket já fechado.", ephemeral=True)
            return
        await interaction.response.send_modal(CloseReasonModal())

    @discord.ui.button(label="Reabrir", emoji="🔓", style=discord.ButtonStyle.success)
    async def reopen(self, interaction, button):
        owner, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if record.get("status", "open") != "closed":
            await interaction.response.send_message("Este ticket já está aberto.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.guild.get_member(owner)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(owner)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.followup.send("O dono do ticket não está disponível.", ephemeral=True)
                return
        try:
            await interaction.channel.set_permissions(member, view_channel=True,
                send_messages=True, read_message_history=True,
                reason=f"Ticket reaberto por {interaction.user}")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Não foi possível restaurar as permissões.", ephemeral=True)
            return
        await set_ticket_status(interaction.guild_id, interaction.channel_id, "open", interaction.user.id)
        await record_event(interaction.guild_id, interaction.channel_id, owner,
                           "reopened", interaction.user.id, record.get("assignee_id"))
        await interaction.channel.send(f"🔓 Ticket reaberto por {interaction.user.mention}.",
                                       allowed_mentions=discord.AllowedMentions.none())
        await interaction.followup.send("Ticket reaberto.", ephemeral=True)

    @discord.ui.button(label="Excluir", emoji="🗑️", style=discord.ButtonStyle.secondary)
    async def delete(self, interaction, button):
        _, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if record.get("status", "open") != "closed":
            await interaction.response.send_message("Feche o ticket antes de excluir.", ephemeral=True)
            return
        await interaction.response.send_message(
            "⚠️ A exclusão do canal é permanente. Confirme abaixo.",
            view=DeleteTicketView(), ephemeral=True)


class LimitModal(discord.ui.Modal, title="Limites de abertura"):
    cooldown = discord.ui.TextInput(
        label="Cooldown em segundos (0 a 86400)",
        placeholder="300", min_length=1, max_length=5
    )
    async def on_submit(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        try:
            value = int(str(self.cooldown))
            await configure_limits(interaction.guild_id, value)
        except (ValueError, TypeError):
            await interaction.response.send_message("Informe um número inteiro entre 0 e 86400.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Cooldown configurado para {value} segundos. Limite de 1 ticket por membro.",
            ephemeral=True
        )


class LimitView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Configurar cooldown", style=discord.ButtonStyle.primary)
    async def edit(self, interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_modal(LimitModal())


class AutomationModal(discord.ui.Modal, title="Configurar automações"):
    inactivity = discord.ui.TextInput(label="Horas até aviso de inatividade", default="24", max_length=3)
    interval = discord.ui.TextInput(label="Intervalo entre lembretes (horas)", default="24", max_length=3)
    welcome = discord.ui.TextInput(label="Mensagem automática de boas-vindas",
                                    style=discord.TextStyle.paragraph, required=False, max_length=1000)

    async def on_submit(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        try:
            await update_automation_settings(
                interaction.guild_id,
                inactivity_hours=int(str(self.inactivity)),
                reminder_hours=int(str(self.interval)),
                welcome_message=str(self.welcome)
            )
        except (ValueError, TypeError) as exc:
            await interaction.response.send_message(f"Configuração inválida: {exc}", ephemeral=True)
            return
        await interaction.response.send_message("✅ Automações configuradas.", ephemeral=True)


class AutomationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Permissão Gerenciar Servidor necessária.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ativar", style=discord.ButtonStyle.success)
    async def enable(self, interaction, button):
        await update_automation_settings(interaction.guild_id, enabled=True)
        await interaction.response.send_message("🟢 Automações ativadas.", ephemeral=True)

    @discord.ui.button(label="Desativar", style=discord.ButtonStyle.danger)
    async def disable(self, interaction, button):
        await update_automation_settings(interaction.guild_id, enabled=False)
        await interaction.response.send_message("🔴 Automações desativadas.", ephemeral=True)

    @discord.ui.button(label="Configurar", style=discord.ButtonStyle.primary)
    async def configure(self, interaction, button):
        cfg = await get_automation_settings(interaction.guild_id)
        modal = AutomationModal()
        modal.inactivity.default = str(cfg["inactivity_hours"])
        modal.interval.default = str(cfg["reminder_hours"])
        modal.welcome.default = cfg["welcome_message"]
        await interaction.response.send_modal(modal)



class InternalNoteModal(discord.ui.Modal, title="Nota interna do ticket"):
    note = discord.ui.TextInput(label="Nota para a equipe", style=discord.TextStyle.paragraph,
                                max_length=1000, required=True)

    async def on_submit(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Somente a equipe autorizada.", ephemeral=True)
            return
        _, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("Ticket não encontrado.", ephemeral=True)
            return
        await add_note(interaction.guild_id, interaction.channel_id,
                       interaction.user.id, str(self.note))
        await interaction.response.send_message("📝 Nota interna registrada. Não foi publicada no canal.", ephemeral=True)


class PrioritySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(placeholder="Selecione a prioridade", min_values=1, max_values=1,
                         options=[discord.SelectOption(label=x.capitalize(), value=x)
                                  for x in ('baixa', 'normal', 'alta', 'urgente')])

    async def callback(self, interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        _, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("Ticket não encontrado.", ephemeral=True)
            return
        await set_priority(interaction.guild_id, interaction.channel_id,
                           self.values[0], interaction.user.id)
        await interaction.response.send_message(
            f"🚩 Prioridade alterada para **{self.values[0]}**.", ephemeral=True)


class PriorityView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PrioritySelect())


class AttentionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Definir prioridade", style=discord.ButtonStyle.primary)
    async def priority(self, interaction, button):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha a prioridade:",
                                                view=PriorityView(), ephemeral=True)

    @discord.ui.button(label="Adicionar nota interna", style=discord.ButtonStyle.secondary)
    async def note(self, interaction, button):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_modal(InternalNoteModal())



# One-command navigation. All subpanels are private to the administrator.
def central_ticket_embed(cfg):
    embed = discord.Embed(
        title="👑 KING PLUS — Tickets",
        description="**Gerenciamento completo do atendimento**\n\n"
                    "Escolha uma das opções abaixo para configurar o sistema.",
        color=discord.Color.from_rgb(218, 225, 239),
    )
    embed.set_footer(text="Armazenamento: JSON  •  Admin")
    return embed

class TicketBackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Apenas administradores com Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Voltar ao painel", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        await interaction.response.send_message(
            embed=central_ticket_embed(await get_config(interaction.guild_id)),
            view=TicketHomeView(), ephemeral=True
        )

class TicketCreateView(TicketBackView):
    @discord.ui.button(label="Publicar painel público", emoji="📨", style=discord.ButtonStyle.success)
    async def publish(self, interaction, button):
        cog = interaction.client.get_cog("Tickets")
        await cog.ticket_publicar(interaction)

    @discord.ui.button(label="Personalizar aparência", emoji="🎨", style=discord.ButtonStyle.primary)
    async def appearance(self, interaction, button):
        await interaction.response.send_message("🎨 Personalize o painel público:", view=AppearanceView(), ephemeral=True)

    @discord.ui.button(label="Formulários", emoji="📝", style=discord.ButtonStyle.secondary)
    async def forms(self, interaction, button):
        await interaction.response.send_message("📝 Configure as perguntas:", view=FormsView(), ephemeral=True)

class TicketSettingsView(TicketBackView):
    @discord.ui.button(label="Canais e cargos", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def channels(self, interaction, button):
        await interaction.response.send_message("⚙️ Configuração de canais e cargos:", view=ConfigView(), ephemeral=True)

    @discord.ui.button(label="Limites / Anti-spam", emoji="⏳", style=discord.ButtonStyle.secondary)
    async def limits(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_limites(interaction)

    @discord.ui.button(label="Automações", emoji="🤖", style=discord.ButtonStyle.secondary)
    async def automations(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_automacoes(interaction)

    @discord.ui.button(label="Ativar / Desativar", emoji="🔘", style=discord.ButtonStyle.secondary)
    async def enabled(self, interaction, button):
        await interaction.response.send_message("Controle de ativação:", view=AdminView(), ephemeral=True)

class TicketLogsView(TicketBackView):
    @discord.ui.button(label="Configurar canal de logs", emoji="📋", style=discord.ButtonStyle.primary)
    async def channel(self, interaction, button):
        await interaction.response.send_message("Selecione o canal de logs:", view=ConfigView(), ephemeral=True)

    @discord.ui.button(label="Exportar transcrição deste ticket", emoji="📄", style=discord.ButtonStyle.secondary)
    async def transcript(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_transcricao(interaction)

class TicketMaintenanceView(TicketBackView):
    @discord.ui.button(label="Diagnóstico", emoji="🩺", style=discord.ButtonStyle.primary)
    async def diagnose(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_diagnostico(interaction)

    @discord.ui.button(label="Gerenciar ticket atual", emoji="🎫", style=discord.ButtonStyle.secondary)
    async def manage(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_gerenciar(interaction)

    @discord.ui.button(label="Fechar / Reabrir / Excluir", emoji="🔒", style=discord.ButtonStyle.danger)
    async def lifecycle(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_fechamento(interaction)

class TicketHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    async def interaction_check(self, interaction):
        if not interaction.guild or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Apenas administradores com Gerenciar Servidor.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Criar Painel", style=discord.ButtonStyle.primary, row=0)
    async def create(self, interaction, button):
        await interaction.response.send_message("📨 Criação e publicação:", view=TicketCreateView(), ephemeral=True)

    @discord.ui.button(label="Categorias", style=discord.ButtonStyle.secondary, row=0)
    async def categories(self, interaction, button):
        await interaction.response.send_message("📂 Categorias de atendimento:", view=CategoriesView(), ephemeral=True)

    @discord.ui.button(label="Equipe", style=discord.ButtonStyle.secondary, row=1)
    async def team(self, interaction, button):
        await interaction.response.send_message("👥 Equipe de suporte:", view=SupportAdminView(), ephemeral=True)

    @discord.ui.button(label="Prioridades", style=discord.ButtonStyle.secondary, row=1)
    async def priorities(self, interaction, button):
        await interaction.response.send_message("🚩 Prioridade do ticket atual:", view=PriorityView(), ephemeral=True)

    @discord.ui.button(label="Logs", style=discord.ButtonStyle.secondary, row=2)
    async def logs(self, interaction, button):
        await interaction.response.send_message("📋 Logs e transcrições:", view=TicketLogsView(), ephemeral=True)

    @discord.ui.button(label="Configurações", style=discord.ButtonStyle.secondary, row=2)
    async def settings(self, interaction, button):
        await interaction.response.send_message("⚙️ Configurações do sistema:", view=TicketSettingsView(), ephemeral=True)

    @discord.ui.button(label="Estatísticas", style=discord.ButtonStyle.secondary, row=3)
    async def statistics(self, interaction, button):
        await interaction.client.get_cog("Tickets").ticket_estatisticas(interaction)

    @discord.ui.button(label="Manutenção", style=discord.ButtonStyle.secondary, row=3)
    async def maintenance(self, interaction, button):
        await interaction.response.send_message("🛠️ Ferramentas de manutenção:", view=TicketMaintenanceView(), ephemeral=True)

    @discord.ui.button(label="Voltar", emoji="⬅️", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction, button):
        await interaction.response.send_message("Você está no painel principal de Tickets. Para voltar ao KING PLUS, use `/kingplus`.", ephemeral=True)

    @discord.ui.button(label="Central", emoji="🏠", style=discord.ButtonStyle.secondary, row=4)
    async def central(self, interaction, button):
        await interaction.response.send_message("Abra a Central KING PLUS com `/kingplus` (quando instalada).", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(PublicTicketView())
        self.bot.add_view(TicketManageView())
        self.automation_reminders.start()

    def cog_unload(self):
        self.automation_reminders.cancel()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.author.bot:
            return
        _, record = await find_ticket(message.guild.id, message.channel.id)
        if record and record.get("status", "open") == "open":
            await mark_activity(message.guild.id, message.channel.id)

    @tasks.loop(minutes=15)
    async def automation_reminders(self):
        for guild in self.bot.guilds:
            cfg = await get_config(guild.id)
            if not cfg.get("enabled", True):
                continue
            records = await list_open_tickets(guild.id)
            open_ids = [
                int(r["channel_id"]) for r in records
                if r.get("status", "open") == "open"
            ]
            for channel_id in await due_reminders(guild.id, open_ids):
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.TextChannel):
                    continue
                try:
                    await channel.send(
                        "⏰ **Lembrete automático:** este ticket está sem atividade. "
                        "Equipe de suporte, verifique o atendimento.",
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                except (discord.Forbidden, discord.HTTPException):
                    continue
                await mark_reminded(guild.id, channel_id)

    @automation_reminders.before_loop
    async def before_automation_reminders(self):
        await self.bot.wait_until_ready()



    async def ticket_diagnostico(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Requer Gerenciar Servidor.", ephemeral=True)
            return
        guild = interaction.guild
        cfg = await get_config(guild.id)
        me = guild.me
        checks = [
            ("Sistema", "Ativado" if cfg.get("enabled", True) else "Em manutenção"),
            ("Permissão Gerenciar Canais", "OK" if me and me.guild_permissions.manage_channels else "FALTANDO"),
            ("Permissão Ler Histórico", "OK" if me and me.guild_permissions.read_message_history else "FALTANDO"),
            ("Categoria de tickets", "OK" if isinstance(
                guild.get_channel(int(cfg.get("ticket_category_id") or 0)), discord.CategoryChannel
            ) else "NÃO CONFIGURADA"),
            ("Canal do painel", "OK" if isinstance(
                guild.get_channel(int(cfg.get("panel_channel_id") or 0)), discord.TextChannel
            ) else "NÃO CONFIGURADO"),
            ("Canal de logs", "OK" if isinstance(
                guild.get_channel(int(cfg.get("log_channel_id") or 0)), discord.TextChannel
            ) else "NÃO CONFIGURADO"),
        ]
        records = await list_open_tickets(guild.id)
        stale = sum(1 for item in records if guild.get_channel(int(item["channel_id"])) is None)
        embed = discord.Embed(title="🩺 KING PLUS • Diagnóstico", color=discord.Color.blurple())
        embed.description = "\\n".join(f"**{name}:** {value}" for name, value in checks)
        embed.add_field(name="Tickets registrados", value=str(len(records)))
        embed.add_field(name="Canais ausentes", value=str(stale))
        embed.set_footer(text="A ausência de canal não remove automaticamente o registro.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def ticket_atendimento(self, interaction: discord.Interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Somente a equipe autorizada.", ephemeral=True)
            return
        owner, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("Use este comando dentro de um ticket.", ephemeral=True)
            return
        info = await get_attention(interaction.guild_id, interaction.channel_id)
        notes = info.get('notes', [])
        embed = discord.Embed(title="🛠️ Controle de Atendimento", color=discord.Color.blurple())
        embed.add_field(name="Solicitante", value=f"<@{owner}>", inline=True)
        embed.add_field(name="Estado", value=ticket.get('status', 'open'), inline=True)
        embed.add_field(name="Prioridade", value=info.get('priority', 'normal').capitalize(), inline=True)
        embed.add_field(name="Atendente", value=(f"<@{ticket['assignee_id']}>"
                        if ticket.get('assignee_id') else "Não atribuído"), inline=True)
        recent = notes[-5:]
        embed.add_field(name="Notas internas recentes",
                        value="\n".join(f"<@{n['author_id']}>: {discord.utils.escape_markdown(n['content'][:180])}"
                                        for n in recent)[:1024] or "Nenhuma nota", inline=False)
        embed.set_footer(text="Painel visível apenas para o atendente que executou o comando.")
        await interaction.response.send_message(embed=embed, view=AttentionView(), ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    async def ticket_automacoes(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        cfg = await get_automation_settings(interaction.guild_id)
        await interaction.response.send_message(
            f"🤖 **Automações KING PLUS**\\n"
            f"Estado: {'Ativadas' if cfg['enabled'] else 'Desativadas'}\\n"
            f"Inatividade: {cfg['inactivity_hours']} horas\\n"
            f"Intervalo entre avisos: {cfg['reminder_hours']} horas\\n"
            "As verificações ocorrem a cada 15 minutos.",
            view=AutomationView(), ephemeral=True
        )

    async def ticket_estatisticas(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        totals, by_staff, ratings = await get_report(interaction.guild_id)
        embed = discord.Embed(title="📊 KING PLUS • Estatísticas de Tickets",
                              color=discord.Color.blurple())
        for key, label in (("opened", "Abertos"), ("closed", "Fechamentos"),
                           ("reopened", "Reaberturas"), ("deleted", "Exclusões")):
            embed.add_field(name=label, value=str(totals[key]), inline=True)
        average = f"{sum(ratings)/len(ratings):.2f}/5 ({len(ratings)} avaliações)" if ratings else "Sem avaliações"
        embed.add_field(name="Satisfação", value=average, inline=False)
        ranking = sorted(by_staff.items(), key=lambda x: x[1], reverse=True)[:10]
        embed.add_field(name="Fechamentos por atendente",
                        value="\\n".join(f"<@{uid}>: {count}" for uid, count in ranking) or "Sem dados",
                        inline=False)
        embed.set_footer(text="Dados coletados a partir da Fase 13; eventos anteriores não são reconstruídos.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def ticket_avaliar(self, interaction: discord.Interaction,
                            nota: app_commands.Range[int, 1, 5]):
        owner, ticket = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not ticket or owner != interaction.user.id:
            await interaction.response.send_message("Somente o dono de um ticket pode avaliá-lo.", ephemeral=True)
            return
        if ticket.get("status", "open") != "closed":
            await interaction.response.send_message("Feche o ticket antes de avaliar.", ephemeral=True)
            return
        try:
            await submit_rating(interaction.guild_id, interaction.channel_id, owner, nota)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(f"⭐ Obrigado pela avaliação: {nota}/5!", ephemeral=True)

    async def ticket_limites(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        settings = await get_limits(interaction.guild_id)
        await interaction.response.send_message(
            f"🛡️ **Controle de abertura**\\n"
            f"Cooldown: **{settings['cooldown_seconds']} segundos**\\n"
            f"Máximo de tickets simultâneos por membro: **1**\\n"
            "Configure o cooldown pelo botão abaixo.",
            view=LimitView(), ephemeral=True
        )

    async def ticket_transcricao(self, interaction: discord.Interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Somente a equipe de suporte.", ephemeral=True)
            return
        _, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Use em um canal de ticket registrado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            transcript = await build_transcript(interaction.channel)
            await interaction.followup.send("📄 Transcrição HTML do ticket:", file=transcript, ephemeral=True)
        except (discord.Forbidden, discord.HTTPException, OSError):
            await interaction.followup.send("Não foi possível exportar. Verifique histórico e anexos.", ephemeral=True)

    async def ticket_fechamento(self, interaction: discord.Interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Apenas a equipe de suporte.", ephemeral=True)
            return
        _, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record:
            await interaction.response.send_message("Este canal não é um ticket registrado.", ephemeral=True)
            return
        await interaction.response.send_message("🔐 **Gerenciamento de encerramento**",
            view=TicketCloseView(), ephemeral=True)

    async def ticket_gerenciar(self, interaction: discord.Interaction):
        if not await can_manage_ticket(interaction):
            await interaction.response.send_message("Somente a equipe de suporte.", ephemeral=True)
            return
        owner, record = await find_ticket(interaction.guild_id, interaction.channel_id)
        if not record:
            await interaction.response.send_message("Este canal não é um ticket registrado.", ephemeral=True)
            return
        await interaction.response.send_message("🎫 **Gerenciamento do ticket**",
            view=TicketManageView(), ephemeral=True)

    async def ticket_equipe(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_message("👥 **Equipe de suporte — Fase 8**", view=SupportAdminView(), ephemeral=True)

    async def ticket_publicar(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        cfg = await get_config(interaction.guild_id)
        channel_id = cfg.get("panel_channel_id")
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Configure primeiro o canal de texto em `/ticket` → Configurações → Canais e cargos.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            old_id = cfg.get("panel_message_id")
            old_channel_id = cfg.get("published_channel_id")
            if old_id and old_channel_id == channel.id:
                try:
                    message = await channel.fetch_message(int(old_id))
                    await message.edit(embed=public_embed(cfg), view=public_view(cfg))
                    await interaction.followup.send(f"✅ Painel atualizado em {channel.mention}.", ephemeral=True)
                    return
                except discord.NotFound:
                    pass
            message = await channel.send(embed=public_embed(cfg), view=public_view(cfg))
            await update_config(interaction.guild_id, panel_message_id=message.id,
                                published_channel_id=channel.id)
            await interaction.followup.send(f"✅ Painel publicado em {channel.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Preciso das permissões Ver canal, Enviar mensagens e Incorporar links.", ephemeral=True)
        except discord.HTTPException:
            await interaction.followup.send("❌ O Discord não conseguiu publicar o painel. Tente novamente.", ephemeral=True)

    async def ticket_formularios(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_message(
            "📝 **Formulários de tickets** — até cinco perguntas por categoria.",
            view=FormsView(), ephemeral=True
        )

    async def ticket_categorias(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Sem permissão.", ephemeral=True)
            return
        await interaction.response.send_message(
            "🗂️ **Categorias de atendimento** — crie, consulte, ative, desative ou exclua.",
            view=CategoriesView(), ephemeral=True
        )

    @app_commands.command(name="ticket", description="Painel administrativo do sistema de tickets")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def ticket(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Você precisa de Gerenciar Servidor.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=central_ticket_embed(await get_config(interaction.guild_id)),
            view=TicketHomeView(), ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Tickets(bot))
