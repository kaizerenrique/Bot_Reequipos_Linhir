import discord
import database

class BattleReportView(discord.ui.View):
    def __init__(self, battle_id, guild_config):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.guild_config = guild_config

    @discord.ui.button(label="Reporte por jugador", style=discord.ButtonStyle.primary)
    async def individual_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Obtener datos de la BD para esta batalla
        # Construir embed con lista de jugadores y sus items
        # Usar albion_api.get_localized_name para traducir items según idioma del gremio
        await interaction.response.send_message("Generando reporte...", ephemeral=True)
        # ... lógica

    @discord.ui.button(label="Resumen de compras", style=discord.ButtonStyle.secondary)
    async def summary_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Obtener todos los items perdidos en la batalla, agrupar por tipo y calidad
        # Mostrar tabla
        await interaction.response.send_message("Generando resumen...", ephemeral=True)