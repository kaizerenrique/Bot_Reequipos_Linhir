import discord
from discord import app_commands
from discord.ext import commands
import database
from config import MASTER_GUILD_ID
import logging

logger = logging.getLogger(__name__)


class MasterCog(commands.Cog):
    """Comandos de administración global solo accesibles desde el servidor maestro."""

    def __init__(self, bot):
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.guild_id) != MASTER_GUILD_ID:
            await interaction.response.send_message(
                "❌ Este comando solo puede ejecutarse desde el servidor maestro.",
                ephemeral=True
            )
            return False
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Necesitas permisos de administrador en el servidor maestro.",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(
        name="master_listar_gremios",
        description="Lista todos los gremios registrados (activos e inactivos)"
    )
    async def listar_gremios(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gremios = database.obtener_todos_gremios()
        if not gremios:
            await interaction.followup.send("No hay gremios registrados.")
            return

        lines = []
        for g in gremios:
            estado = "✅ Activo" if g['activo'] else "❌ Inactivo"
            lines.append(
                f"**{g['nombre_gremio']}** (Discord: `{g['discord_guild_id']}`, Albion: `{g['albion_guild_id']}`) - {estado}"
            )
        await interaction.followup.send("\n".join(lines))

    @app_commands.command(
        name="master_expulsar",
        description="Expulsa al bot de un servidor Discord y elimina su registro"
    )
    @app_commands.describe(discord_guild_id="ID del servidor a expulsar")
    async def expulsar(self, interaction: discord.Interaction, discord_guild_id: str):
        await interaction.response.defer(ephemeral=True)
        gremio = database.obtener_gremio_por_discord_id(discord_guild_id)
        if not gremio:
            await interaction.followup.send(f"No hay ningún gremio registrado con ID {discord_guild_id}.")
            return

        guild = self.bot.get_guild(int(discord_guild_id))
        if guild:
            try:
                await guild.leave()
                logger.info(f"Bot expulsado manualmente del servidor {guild.name} ({discord_guild_id})")
            except Exception as e:
                await interaction.followup.send(f"Error al intentar salir del servidor: {e}")
                return
        else:
            await interaction.followup.send(
                "El bot no está en ese servidor o no se pudo obtener. Se procederá a eliminar de la BD igualmente."
            )

        database.eliminar_gremio(discord_guild_id)
        await interaction.followup.send(f"✅ Bot expulsado y gremio {gremio['nombre_gremio']} eliminado.")

    @app_commands.command(
        name="master_desactivar",
        description="Desactiva un gremio (deja de monitorear, pero no expulsa)"
    )
    @app_commands.describe(discord_guild_id="ID del servidor a desactivar")
    async def desactivar(self, interaction: discord.Interaction, discord_guild_id: str):
        await interaction.response.defer(ephemeral=True)
        gremio = database.obtener_gremio_por_discord_id(discord_guild_id)
        if not gremio:
            await interaction.followup.send(f"No hay ningún gremio registrado con ID {discord_guild_id}.")
            return
        database.actualizar_estado_gremio(discord_guild_id, False)
        await interaction.followup.send(f"✅ Gremio {gremio['nombre_gremio']} desactivado.")

    @app_commands.command(
        name="master_activar",
        description="Activa un gremio previamente desactivado"
    )
    @app_commands.describe(discord_guild_id="ID del servidor a activar")
    async def activar(self, interaction: discord.Interaction, discord_guild_id: str):
        await interaction.response.defer(ephemeral=True)
        gremio = database.obtener_gremio_por_discord_id(discord_guild_id)
        if not gremio:
            await interaction.followup.send(f"No hay ningún gremio registrado con ID {discord_guild_id}.")
            return
        database.actualizar_estado_gremio(discord_guild_id, True)
        await interaction.followup.send(f"✅ Gremio {gremio['nombre_gremio']} activado.")


async def setup(bot):
    await bot.add_cog(MasterCog(bot))