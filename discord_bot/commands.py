# discord_bot/commands.py
import discord
from discord import app_commands
from discord.ext import commands
import database
import logging

logger = logging.getLogger(__name__)

class ConfigCog(commands.Cog):
    """Comandos de configuración del bot."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="configurar_gremio", description="Registra un gremio de Albion en este servidor Discord")
    @app_commands.describe(
        albion_guild_id="ID del gremio en Albion (ej: iS2Q2Mw3S1asC9GVMC5P2w)",
        nombre_gremio="Nombre del gremio (para referencia)",
        idioma="Idioma para reportes (es/en)",
        canal_reportes_batalla="Canal para reportes de batalla",
        canal_reportes_individual="Canal para reportes por jugador",
        canal_resumen="Canal para resúmenes globales"
    )
    @app_commands.choices(idioma=[
        app_commands.Choice(name="Español", value="es"),
        app_commands.Choice(name="Inglés", value="en")
    ])
    async def configurar_gremio(
        self,
        interaction: discord.Interaction,
        albion_guild_id: str,
        nombre_gremio: str,
        idioma: str,
        canal_reportes_batalla: discord.TextChannel,
        canal_reportes_individual: discord.TextChannel,
        canal_resumen: discord.TextChannel
    ):
        """Registra un nuevo gremio en la base de datos."""
        # Verificar permisos de administrador
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Necesitas permisos de administrador.", ephemeral=True)
            return

        discord_guild_id = str(interaction.guild_id)

        try:
            database.registrar_gremio(
                discord_guild_id,
                albion_guild_id,
                nombre_gremio,
                idioma,
                str(canal_reportes_batalla.id),
                str(canal_reportes_individual.id),
                str(canal_resumen.id)
            )
            await interaction.response.send_message(
                f"✅ Gremio **{nombre_gremio}** registrado correctamente.\n"
                f"ID de Albion: `{albion_guild_id}`\n"
                f"Idioma: {idioma}\n"
                f"Canal de batallas: {canal_reportes_batalla.mention}\n"
                f"Canal individual: {canal_reportes_individual.mention}\n"
                f"Canal de resúmenes: {canal_resumen.mention}",
                ephemeral=True
            )
            logger.info(f"Gremio {nombre_gremio} registrado para el servidor {interaction.guild.name}")
        except Exception as e:
            logger.error(f"Error registrando gremio: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="pendientes", description="Muestra las muertes pendientes de reequipo")
    async def pendientes(self, interaction: discord.Interaction):
        """Lista las muertes pendientes del gremio asociado a este servidor."""
        # Obtener el gremio registrado para este servidor
        discord_guild_id = str(interaction.guild_id)
        # Aquí deberías consultar la base de datos para obtener las muertes pendientes
        # Por ahora, un mensaje de placeholder
        await interaction.response.send_message("🚧 Función en desarrollo.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ConfigCog(bot))