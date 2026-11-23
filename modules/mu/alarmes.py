import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import asyncio

from .config import load_config, save_config

# ======================================================
# ⏱️ TIMEZONE
# ======================================================
TZ = ZoneInfo("America/Sao_Paulo")

# ======================================================
# CONFIG
# ======================================================
def get_cfg():
    cfg = load_config()
    cfg.setdefault("alarmes", [])
    cfg.setdefault("painel_alarmes", {"canal_id": None, "mensagem_id": None})
    cfg.setdefault("canal_alertas", None)
    return cfg


# ======================================================
# 🧾 EMBED MODERNO DO PAINEL
# ======================================================
def build_alarmes_embed():
    cfg = get_cfg()
    alarmes = cfg["alarmes"]

    embed = discord.Embed(
        title="⏰ Painel de Notificações & Eventos",
        description="Alertas automáticos de bosses e eventos",
        color=discord.Color.orange()
    )

    if not alarmes:
        embed.add_field(
            name="— vazio —",
            value="Nenhuma notificação configurada",
            inline=False
        )
        return embed

    for a in alarmes:
        nome = a["nome"]
        tipo = a.get("tipo", "evento")
        hora_real = a["hora_real"]
        hora_game = a.get("hora_game")
        dias = "Todos os dias" if a["dias"] == ["todos"] else ", ".join(a["dias"])
        avisos = " / ".join(f"{m}m" for m in sorted(a["avisos"]))
        ativo = a.get("ativo", True)

        emoji = "👹" if tipo == "boss" else "🏰" if tipo == "guilda" else "🎉"
        status = "🟢 **Ativo**" if ativo else "🔴 **Inativo**"

        linha_hora = f"⏰ **{hora_real}** (Real)"
        if hora_game:
            linha_hora += f" • 🎮 **{hora_game}** (Game)"

        embed.add_field(
            name=f"{emoji} **{nome}**",
            value=(
                f"{linha_hora}\n"
                f"📅 {dias}\n"
                f"🔔 Alertas: **{avisos}**\n"
                f"{status}"
            ),
            inline=False
        )

    embed.set_footer(text="Use os botões abaixo para gerenciar notificações")
    return embed


# ======================================================
# 🔄 CRIAR / ATUALIZAR PAINEL
# ======================================================
async def atualizar_painel_alarmes(bot):
    cfg = get_cfg()
    painel = cfg["painel_alarmes"]

    canal = bot.get_channel(painel.get("canal_id"))
    if not canal:
        return

    if painel.get("mensagem_id"):
        try:
            msg = await canal.fetch_message(painel["mensagem_id"])
            await msg.edit(embed=build_alarmes_embed(), view=AlarmesView())
            return
        except discord.NotFound:
            painel["mensagem_id"] = None
            save_config(cfg)

    msg = await canal.send(embed=build_alarmes_embed(), view=AlarmesView())
    await msg.pin()

    painel["mensagem_id"] = msg.id
    save_config(cfg)


# ======================================================
# 🎛️ VIEW (BOTÕES)
# ======================================================
class AlarmesView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(BtnCriarAlarme())
        self.add_item(BtnExcluirAlarme())


class BtnCriarAlarme(Button):
    def __init__(self):
        super().__init__(
            label="Nova Notificação",
            emoji="➕",
            style=discord.ButtonStyle.success,
            custom_id="alarmes:criar"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ModalCriarAlarme())


class BtnExcluirAlarme(Button):
    def __init__(self):
        super().__init__(
            label="Remover",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id="alarmes:excluir"
        )

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg()
        if not cfg["alarmes"]:
            return await interaction.response.send_message(
                "⚠️ Não há alarmes para excluir.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "🗑️ Selecione o alarme para excluir:",
            view=ViewExcluirAlarme(),
            ephemeral=True
        )


# ======================================================
# 📝 MODAL — CRIAR ALARME
# ======================================================
class ModalCriarAlarme(Modal, title="Criar Notificação"):
    nome = TextInput(label="Nome do Boss / Evento")
    tipo_dias = TextInput(label="Tipo e dias", placeholder="boss todos | guilda dom")
    hora_real = TextInput(label="Horário REAL (HH:MM)", placeholder="22:30")
    hora_game = TextInput(label="Horário IN-GAME (opcional)", required=False)
    avisos = TextInput(label="Avisos em minutos", placeholder="15,10,5")

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_cfg()

        partes = self.tipo_dias.value.lower().split()
        tipo = partes[0] if partes else "evento"
        dias = partes[1:] if len(partes) > 1 else ["todos"]

        cfg["alarmes"].append({
            "nome": self.nome.value.strip(),
            "tipo": tipo,
            "hora_real": self.hora_real.value.strip(),
            "hora_game": self.hora_game.value.strip() or None,
            "avisos": [int(x.strip()) for x in self.avisos.value.split(",")],
            "dias": ["todos"] if dias == ["todos"] else dias,
            "ativo": True,
            "ultimo": {}
        })

        save_config(cfg)
        await atualizar_painel_alarmes(interaction.client)

        await interaction.response.send_message("✅ Alarme criado!", ephemeral=True)


# ======================================================
# ⏱️ COG — LOOP + AUTO-RECOVERY
# ======================================================
class AlarmesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not self.loop.is_running():
            self.loop.start()

    def cog_unload(self):
        if self.loop.is_running():
            self.loop.cancel()

    # ---------------- AUTO-RECOVERY ----------------
    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(2)

        cfg = get_cfg()
        painel = cfg["painel_alarmes"]

        if not painel.get("canal_id"):
            return

        canal = self.bot.get_channel(painel["canal_id"])
        if not canal:
            return

        if painel.get("mensagem_id"):
            try:
                await canal.fetch_message(painel["mensagem_id"])
                await atualizar_painel_alarmes(self.bot)
                return
            except discord.NotFound:
                painel["mensagem_id"] = None
                save_config(cfg)

        msg = await canal.send(embed=build_alarmes_embed(), view=AlarmesView())
        await msg.pin()

        painel["mensagem_id"] = msg.id
        save_config(cfg)

        await atualizar_painel_alarmes(self.bot)

    # ---------------- LOOP ----------------
    @tasks.loop(seconds=30)
    async def loop(self):
        cfg = get_cfg()
        agora = datetime.now(TZ)
        dia_atual = agora.weekday()

        mapa_dias = {
            "seg": 0, "ter": 1, "qua": 2,
            "qui": 3, "sex": 4, "sab": 5, "dom": 6
        }

        for a in cfg["alarmes"]:
            if not a.get("ativo"):
                continue

            if a["dias"] != ["todos"]:
                dias_validos = [mapa_dias[d] for d in a["dias"] if d in mapa_dias]
                if dia_atual not in dias_validos:
                    continue

            hora_evento = datetime.strptime(a["hora_real"], "%H:%M").time()
            evento = datetime.combine(agora.date(), hora_evento, tzinfo=TZ)
            if evento < agora:
                evento += timedelta(days=1)

            data_evento = evento.date().isoformat()
            a["ultimo"] = {
                k: v for k, v in a.get("ultimo", {}).items()
                if k.startswith(data_evento)
            }

            for m in a["avisos"]:
                aviso = evento - timedelta(minutes=m)
                chave = f"{data_evento}-{m}"

                if 0 <= (aviso - agora).total_seconds() <= 60:
                    if a["ultimo"].get(chave):
                        continue

                    canal = self.bot.get_channel(cfg.get("canal_alertas"))
                    if canal:
                        await canal.send(
                            f"@everyone ⏰ **{a['nome']}**\n"
                            f"Começa em **{m} minuto(s)**\n"
                            f"🕒 Horário real: **{a['hora_real']}**",
                            allowed_mentions=discord.AllowedMentions(everyone=True)
                        )

                    a["ultimo"][chave] = True
                    save_config(cfg)

    @loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


# ======================================================
# 🗑️ VIEW — EXCLUIR
# ======================================================
class ViewExcluirAlarme(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(SelectExcluirAlarme())


class SelectExcluirAlarme(discord.ui.Select):
    def __init__(self):
        cfg = get_cfg()
        options = [
            discord.SelectOption(
                label=a["nome"],
                description=f"{a['hora_real']} • {', '.join(a['dias'])}",
                value=str(i)
            )
            for i, a in enumerate(cfg["alarmes"])
        ]

        super().__init__(
            placeholder="Selecione o alarme",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg()
        idx = int(self.values[0])
        nome = cfg["alarmes"][idx]["nome"]

        cfg["alarmes"].pop(idx)
        save_config(cfg)

        cfg["painel_alarmes"]["mensagem_id"] = None
        save_config(cfg)

        await atualizar_painel_alarmes(interaction.client)

        await interaction.response.send_message(
            f"🗑️ Alarme **{nome}** removido!",
            ephemeral=True
        )


# ======================================================
# SETUP
# ======================================================
async def setup(bot):
    await bot.add_cog(AlarmesCog(bot))
    bot.add_view(AlarmesView())