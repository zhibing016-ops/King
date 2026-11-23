import discord
from .manager import cast
from .embeds import render

class PollSelect(discord.ui.Select):
    def __init__(self,p):
        opts=[discord.SelectOption(label=o[:100], value=str(i)) for i,o in enumerate(p["options"])]
        super().__init__(placeholder="Selecione sua resposta", options=opts, min_values=1, max_values=min(p.get("max_choices",1),len(opts)), custom_id=f"kingpoll:{p['id']}")
        self.pid=p["id"]
    async def callback(self,interaction):
        from modules.enquetes.storage import read
        current=read("polls",{}).get(self.pid,{})
        role_id=current.get("required_role_id")
        if role_id and not any(role.id==role_id for role in getattr(interaction.user,"roles",[])):
            return await interaction.response.send_message("Você não possui o cargo necessário.",ephemeral=True)
        try:
            p=await cast(self.pid,interaction.user.id,[int(x) for x in self.values])
            await interaction.response.send_message("✅ Voto registrado!",ephemeral=True)
            try: await interaction.message.edit(embed=render(p))
            except discord.HTTPException: pass
        except ValueError as e: await interaction.response.send_message(str(e),ephemeral=True)
class PollView(discord.ui.View):
    def __init__(self,p):
        super().__init__(timeout=None)
        self.add_item(PollSelect(p))
