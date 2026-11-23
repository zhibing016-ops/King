import unittest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
try:
    from systems.reaction_roles.services.reactions import mapped_role, handle_raw_reaction
    import discord
except ImportError:
    discord = None

@unittest.skipIf(discord is None, 'discord.py não instalado')
class ReactionTests(unittest.IsolatedAsyncioTestCase):
    def test_emoji_mapping(self):
        panel = {'roles': {'🎮': '123', '<:gaming:123456789012345678>': '456'}}
        self.assertEqual(mapped_role(panel, '🎮'), 123)
        self.assertEqual(mapped_role(panel, discord.PartialEmoji(name='other', id=123456789012345678)), 456)
        self.assertIsNone(mapped_role(panel, '🎨'))

    async def test_add_and_remove(self):
        role = MagicMock(); role.id = 123; role.is_default.return_value = False; role.managed = False
        role.__ge__.return_value = False
        member = MagicMock(); member.id = 9; member.bot = False; member.roles = []
        member.add_roles = AsyncMock(); member.remove_roles = AsyncMock()
        guild = MagicMock(); guild.id = 1; guild.get_role.return_value = role
        guild.me.guild_permissions.manage_roles = True
        guild.get_member.return_value = member
        bot = MagicMock(); bot.user.id = 99; bot.get_guild.return_value = guild
        store = MagicMock(); store.get = AsyncMock(return_value={'enabled': True, 'panels': {'abc': {'message_id':'2','channel_id':'3','roles':{'🎮':'123'}}}})
        payload = SimpleNamespace(guild_id=1,user_id=9,message_id=2,channel_id=3,emoji='🎮',member=member)
        await handle_raw_reaction(bot, store, payload, True)
        member.add_roles.assert_awaited_once()
        member.roles = [role]
        await handle_raw_reaction(bot, store, payload, False)
        member.remove_roles.assert_awaited_once()
