import discord
from discord.ext import commands
from .commands import ConfigCog

class LinhirBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.add_cog(ConfigCog(self))
        # Sincronizar comandos con un servidor específico para pruebas (opcional)
        # self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
        await self.tree.sync()

    async def on_ready(self):
        print(f"Bot conectado como {self.user}")