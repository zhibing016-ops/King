import asyncio
import json
import io
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
from modules.enquetes.storage import read, write
from modules.enquetes.manager import create, update, now, counts
from modules.enquetes.embeds import render
from modules.enquetes.views import PollView

class FeatureCog(commands.GroupCog,group_name="enquetes",group_description="Administração avançada KING PLUS"):
    def __init__(self,bot):
        self.bot=bot
        self.tick.start()
    def cog_unload(self): self.tick.cancel()
    def get(self,interaction,pid):
        p=read("polls",{}).get(pid)
        if not p or p["guild_id"]!=interaction.guild_id: raise ValueError("Enquete não encontrada neste servidor.")
        return p
    async def refresh(self,p):
        if p.get("channel_id") and p.get("message_id"):
            try:
                ch=self.bot.get_channel(p["channel_id"]) or await self.bot.fetch_channel(p["channel_id"])
                msg=await ch.fetch_message(p["message_id"])
                await msg.edit(embed=render(p),view=PollView(p) if p["status"]=="open" else None)
            except (discord.HTTPException,discord.Forbidden): pass
    @tasks.loop(seconds=45)
    async def tick(self):
        polls=read("polls",{})
        for p in list(polls.values()):
            if p["status"]=="open" and p.get("ends_at") and datetime.fromisoformat(p["ends_at"])<=now():
                p["status"]="closed";await update(p);await self.refresh(p)
            if p["status"]=="scheduled" and datetime.fromisoformat(p["publish_at"])<=now():
                try:
                    ch=self.bot.get_channel(p["channel_id"]) or await self.bot.fetch_channel(p["channel_id"])
                    p["status"]="open"
                    msg=await ch.send(embed=render(p),view=PollView(p))
                    p["message_id"]=msg.id;await update(p)
                    self.bot.add_view(PollView(p),message_id=msg.id)
                except (discord.HTTPException,discord.Forbidden): pass
    @tick.before_loop
    async def before_tick(self): await self.bot.wait_until_ready()
    @app_commands.command(name="painel",description="Painel de ajuda das enquetes")
    @app_commands.default_permissions(manage_guild=True)
    async def painel(self,interaction:discord.Interaction):
        v=discord.ui.View(timeout=180)
        for label,cmd in [("Criar","/enquete criar"),("Publicar","/enquete publicar"),("Listar","/enquete listar"),("Encerrar","/enquete encerrar")]:
            b=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary)
            async def cb(i,cmd=cmd): await i.response.send_message(f"Use `{cmd}` para continuar.",ephemeral=True)
            b.callback=cb;v.add_item(b)
        await interaction.response.send_message("👑 Painel KING PLUS",view=v,ephemeral=True)
    @app_commands.command(name="formulario",description="Abra formulário para criar uma enquete")
    @app_commands.default_permissions(manage_guild=True)
    async def formulario(self,interaction:discord.Interaction):
        class Modal(discord.ui.Modal,title="Nova enquete"):
            question=discord.ui.TextInput(label="Pergunta",max_length=250)
            options=discord.ui.TextInput(label="Opções separadas por ;",style=discord.TextStyle.paragraph)
            duration=discord.ui.TextInput(label="Duração em minutos",default="60")
            async def on_submit(self,i):
                try:
                    minutes=int(self.duration.value)
                    if not 1<=minutes<=10080: raise ValueError()
                    p=await create(i.guild_id,i.user.id,self.question.value,self.options.value.split(";"),minutes)
                    await i.response.send_message(f"Rascunho `{p['id']}` criado.",ephemeral=True)
                except ValueError: await i.response.send_message("Verifique as opções e a duração (1–10080).",ephemeral=True)
        await interaction.response.send_modal(Modal())
    @app_commands.command(name="votos",description="Mostre número de votantes")
    @app_commands.default_permissions(manage_guild=True)
    async def votos(self,interaction:discord.Interaction,id:str):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        await interaction.response.send_message(f"Participantes: {len(p['votes'])}; votos: {sum(counts(p))}.",ephemeral=True)
    @app_commands.command(name="visual",description="Defina a cor hexadecimal da enquete")
    @app_commands.default_permissions(manage_guild=True)
    async def visual(self,interaction:discord.Interaction,id:str,cor:str):
        try: p=self.get(interaction,id);p["color"]=int(cor.lstrip("#"),16)
        except (ValueError,TypeError): return await interaction.response.send_message("ID ou cor inválidos.",ephemeral=True)
        await update(p);await self.refresh(p)
        await interaction.response.send_message("Visual atualizado.",ephemeral=True)
    @app_commands.command(name="resultado",description="Veja o resultado de uma enquete")
    async def resultado(self,interaction:discord.Interaction,id:str):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        if p.get("hide_results") and p["status"]!="closed" and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Resultados ocultos até o encerramento.",ephemeral=True)
        await interaction.response.send_message(embed=render(p),ephemeral=True)
    @app_commands.command(name="prazo",description="Altere o prazo em minutos a partir de agora")
    @app_commands.default_permissions(manage_guild=True)
    async def prazo(self,interaction:discord.Interaction,id:str,minutos:app_commands.Range[int,1,10080]):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        p["ends_at"]=(now()+timedelta(minutes=minutos)).isoformat();await update(p)
        await interaction.response.send_message("Prazo atualizado.",ephemeral=True)
    @app_commands.command(name="restringir",description="Restrinja votos a um cargo")
    @app_commands.default_permissions(manage_guild=True)
    async def restringir(self,interaction:discord.Interaction,id:str,cargo:discord.Role):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        p["required_role_id"]=cargo.id;await update(p)
        await interaction.response.send_message("Cargo exigido configurado.",ephemeral=True)
    @app_commands.command(name="anonima",description="Marque uma enquete como anônima e oculte resultados")
    @app_commands.default_permissions(manage_guild=True)
    async def anonima(self,interaction:discord.Interaction,id:str,ativar:bool=True):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        p["anonymous"]=ativar;p["hide_results"]=ativar;await update(p)
        await interaction.response.send_message("Modo configurado. IDs de votantes continuam armazenados para evitar votos duplicados.",ephemeral=True)
    @app_commands.command(name="multipla",description="Permita até N escolhas por membro")
    @app_commands.default_permissions(manage_guild=True)
    async def multipla(self,interaction:discord.Interaction,id:str,limite:app_commands.Range[int,1,20]):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        p["max_choices"]=min(limite,len(p["options"]));await update(p);await self.refresh(p)
        await interaction.response.send_message("Limite atualizado.",ephemeral=True)
    @app_commands.command(name="agendar",description="Agende publicação de rascunho após N minutos")
    @app_commands.default_permissions(manage_guild=True)
    async def agendar(self,interaction:discord.Interaction,id:str,minutos:app_commands.Range[int,1,10080]):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        if p["status"]!="draft": return await interaction.response.send_message("Apenas rascunhos.",ephemeral=True)
        p["status"]="scheduled";p["channel_id"]=interaction.channel_id;p["publish_at"]=(now()+timedelta(minutes=minutos)).isoformat()
        await update(p);await interaction.response.send_message("Publicação agendada.",ephemeral=True)
    @app_commands.command(name="historico",description="Mostre enquetes encerradas")
    @app_commands.default_permissions(manage_guild=True)
    async def historico(self,interaction:discord.Interaction):
        ps=[p for p in read("polls",{}).values() if p["guild_id"]==interaction.guild_id and p["status"]=="closed"]
        await interaction.response.send_message("\n".join(f"`{p['id']}` {p['question']}" for p in ps[-15:]) or "Sem histórico.",ephemeral=True)
    @app_commands.command(name="modelo",description="Salve uma enquete como modelo")
    @app_commands.default_permissions(manage_guild=True)
    async def modelo(self,interaction:discord.Interaction,id:str,nome:str):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        models=read("templates",{});models[f"{interaction.guild_id}:{nome}"]={"question":p["question"],"options":p["options"]};await write("templates",models)
        await interaction.response.send_message("Modelo salvo.",ephemeral=True)
    @app_commands.command(name="usar_modelo",description="Crie um rascunho a partir de um modelo")
    @app_commands.default_permissions(manage_guild=True)
    async def usar_modelo(self,interaction:discord.Interaction,nome:str):
        m=read("templates",{}).get(f"{interaction.guild_id}:{nome}")
        if not m: return await interaction.response.send_message("Modelo inexistente.",ephemeral=True)
        p=await create(interaction.guild_id,interaction.user.id,m["question"],m["options"])
        await interaction.response.send_message(f"Rascunho `{p['id']}` criado.",ephemeral=True)
    @app_commands.command(name="duplicar",description="Duplique uma enquete como rascunho")
    @app_commands.default_permissions(manage_guild=True)
    async def duplicar(self,interaction:discord.Interaction,id:str):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        new=await create(interaction.guild_id,interaction.user.id,p["question"],p["options"])
        await interaction.response.send_message(f"Nova enquete `{new['id']}`.",ephemeral=True)
    @app_commands.command(name="reabrir",description="Reabra uma enquete encerrada")
    @app_commands.default_permissions(manage_guild=True)
    async def reabrir(self,interaction:discord.Interaction,id:str):
        try: p=self.get(interaction,id)
        except ValueError as e: return await interaction.response.send_message(str(e),ephemeral=True)
        p["status"]="open";p["ends_at"]=(now()+timedelta(hours=1)).isoformat();await update(p);await self.refresh(p)
        await interaction.response.send_message("Enquete reaberta por 1 hora.",ephemeral=True)
    @app_commands.command(name="backup",description="Exporte enquetes do servidor em JSON")
    @app_commands.default_permissions(manage_guild=True)
    async def backup(self,interaction:discord.Interaction):
        polls=[p for p in read("polls",{}).values() if p["guild_id"]==interaction.guild_id]
        raw=json.dumps(polls,ensure_ascii=False,indent=2).encode("utf-8")
        await interaction.response.send_message(file=discord.File(io.BytesIO(raw),filename="kingplus-enquetes-backup.json"),ephemeral=True)
    @app_commands.command(name="diagnostico",description="Estado do sistema de enquetes")
    @app_commands.default_permissions(manage_guild=True)
    async def diagnostico(self,interaction:discord.Interaction):
        ps=[p for p in read("polls",{}).values() if p["guild_id"]==interaction.guild_id]
        await interaction.response.send_message(f"KING PLUS: {len(ps)} enquetes, {sum(p['status']=='open' for p in ps)} abertas, JSON local operacional.",ephemeral=True)

async def setup(bot): await bot.add_cog(FeatureCog(bot))
