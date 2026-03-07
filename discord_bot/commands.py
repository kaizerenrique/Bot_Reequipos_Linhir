import discord
from discord import app_commands
from discord.ext import commands
import database
import albion_api
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


async def _get_item_name(item_type: str, calidad: int, idioma: str) -> str:
    from tasks.monitor import parse_item_type
    base_type, enchant_level = parse_item_type(item_type)
    item_data = await albion_api.get_item_data(base_type, idioma)
    if item_data:
        nombre = albion_api.get_localized_name(item_data, idioma)
    else:
        item_data = await albion_api.get_item_data(item_type, idioma)
        nombre = albion_api.get_localized_name(item_data, idioma) if item_data else item_type
    if enchant_level > 0:
        nombre += f" .{enchant_level}"
    if calidad > 0:
        calidad_texto = {1: "Bueno", 2: "Excelente", 3: "Sobresaliente", 4: "Maestro"}.get(calidad, f"Calidad {calidad}")
        nombre += f" ({calidad_texto})"
    return nombre


class PaginatedReportView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.pages) - 1
        self.last_page.disabled = self.current_page == len(self.pages) - 1

    async def show_page(self, interaction: discord.Interaction):
        embed = self.pages[self.current_page]
        embed.set_footer(text=f"Página {self.current_page + 1} de {len(self.pages)}")
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏪", style=discord.ButtonStyle.primary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self.show_page(interaction)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.show_page(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
        await self.show_page(interaction)

    @discord.ui.button(label="⏩", style=discord.ButtonStyle.primary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        await self.show_page(interaction)


class PendingView(PaginatedReportView):
    """
    Vista paginada para solicitudes pendientes, con botón para marcar como pagado.
    Al marcar como pagado, envía una notificación al canal de solicitudes.
    """

    def __init__(self, pages: List[discord.Embed], battle_ids_players: List[Tuple[int, str]], guild_config: Dict[str, Any], timeout: float = 180.0):
        super().__init__(pages, timeout)
        self.battle_ids_players = battle_ids_players
        self.guild_config = guild_config

    @discord.ui.button(label="✅ Marcar como pagado", style=discord.ButtonStyle.success, row=2)
    async def mark_paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        idx = self.current_page
        battle_id, player = self.battle_ids_players[idx]

        # Marcar como entregado en la base de datos
        database.marcar_como_entregado(battle_id, player)

        # Enviar notificación al canal de solicitudes
        canal_id = self.guild_config.get('canal_solicitudes')
        if canal_id:
            canal = interaction.guild.get_channel(int(canal_id))
            if canal:
                embed = discord.Embed(
                    title="✅ Reequipo pagado",
                    description=f"El reequipo solicitado por **{player}** en la batalla **{battle_id}** ha sido marcado como pagado por {interaction.user.mention}.",
                    color=discord.Color.green()
                )
                await canal.send(embed=embed)

        # Eliminar la página actual
        del self.pages[idx]
        del self.battle_ids_players[idx]

        if not self.pages:
            await interaction.response.edit_message(content="✅ No hay más solicitudes pendientes.", embed=None, view=None)
            return

        if self.current_page >= len(self.pages):
            self.current_page = len(self.pages) - 1

        embed = self.pages[self.current_page]
        embed.set_footer(text=f"Página {self.current_page + 1} de {len(self.pages)}")
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="configurar_gremio", description="Registra un gremio de Albion en este servidor")
    @app_commands.describe(
        albion_guild_id="ID del gremio en Albion",
        nombre_gremio="Nombre del gremio",
        idioma="Idioma para reportes (es/en/pt)",
        canal_reportes_batalla="Canal para notificaciones de batalla",
        canal_reportes_individual="Canal para reportes por jugador",
        canal_resumen="Canal para resúmenes de compras",
        canal_solicitudes="Canal para notificaciones de solicitudes de reequipo"
    )
    @app_commands.choices(idioma=[
        app_commands.Choice(name="Español", value="es"),
        app_commands.Choice(name="Inglés", value="en"),
        app_commands.Choice(name="Português", value="pt")
    ])
    async def configurar_gremio(
        self,
        interaction: discord.Interaction,
        albion_guild_id: str,
        nombre_gremio: str,
        idioma: str,
        canal_reportes_batalla: discord.TextChannel,
        canal_reportes_individual: discord.TextChannel,
        canal_resumen: discord.TextChannel,
        canal_solicitudes: discord.TextChannel
    ):
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
                str(canal_resumen.id),
                str(canal_solicitudes.id)
            )
            await interaction.response.send_message(
                f"✅ Gremio **{nombre_gremio}** registrado.\n"
                f"Idioma: {idioma}\n"
                f"Canal batallas: {canal_reportes_batalla.mention}\n"
                f"Canal individual: {canal_reportes_individual.mention}\n"
                f"Canal resúmenes: {canal_resumen.mention}\n"
                f"Canal solicitudes: {canal_solicitudes.mention}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error registrando gremio: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="fusionar", description="Fusiona varias batallas en un solo reporte")
    @app_commands.describe(ids="Lista de IDs separados por comas (ej: 12345,67890)")
    async def fusionar_batallas(self, interaction: discord.Interaction, ids: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild_config = database.obtener_gremio_por_discord_id(str(interaction.guild_id))
        if not guild_config:
            await interaction.followup.send("❌ Este servidor no tiene un gremio configurado.", ephemeral=True)
            return

        try:
            battle_ids = [int(id.strip()) for id in ids.split(',') if id.strip().isdigit()]
            if not battle_ids:
                await interaction.followup.send("❌ IDs inválidos.", ephemeral=True)
                return

            items = database.obtener_items_agrupados_por_lista_batallas(battle_ids)
            if not items:
                await interaction.followup.send("No se encontraron items para esos IDs.", ephemeral=True)
                return

            pages = []
            current_lines = []
            MAX_LINES = 20
            idioma = guild_config['idioma']

            for item in items:
                nombre = await _get_item_name(item['item_type'], item['calidad'], idioma)
                line = f"• {nombre} x{item['total_cantidad']}"
                if len(current_lines) >= MAX_LINES:
                    embed = discord.Embed(
                        title=f"🛒 Lista fusionada - Batallas: {', '.join(map(str, battle_ids))}",
                        description="\n".join(current_lines),
                        color=discord.Color.green()
                    )
                    pages.append(embed)
                    current_lines = []
                current_lines.append(line)

            if current_lines:
                embed = discord.Embed(
                    title=f"🛒 Lista fusionada - Batallas: {', '.join(map(str, battle_ids))}",
                    description="\n".join(current_lines),
                    color=discord.Color.green()
                )
                pages.append(embed)

            if len(pages) == 1:
                await interaction.followup.send(embed=pages[0], ephemeral=False)
            else:
                view = PaginatedReportView(pages)
                await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)

        except Exception as e:
            logger.error(f"Error en fusionar: {e}", exc_info=True)
            await interaction.followup.send("❌ Error al procesar.", ephemeral=True)

    @app_commands.command(name="pendientes", description="Muestra las solicitudes de reequipo pendientes")
    async def pendientes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild_config = database.obtener_gremio_por_discord_id(str(interaction.guild_id))
        if not guild_config:
            await interaction.followup.send("❌ Gremio no configurado.", ephemeral=True)
            return

        solicitudes = database.obtener_solicitudes_pendientes(guild_config['albion_guild_id'])
        if not solicitudes:
            await interaction.followup.send("No hay solicitudes pendientes.", ephemeral=True)
            return

        from collections import defaultdict
        por_batalla = defaultdict(lambda: defaultdict(list))
        for s in solicitudes:
            por_batalla[s['battle_id']][s['player_name']].append(s)

        pages = []
        battle_ids_players = []

        for battle_id, jugadores in por_batalla.items():
            for player, muertes in jugadores.items():
                items_list = []
                for muerte in muertes:
                    items = database.obtener_items_por_muerte(muerte['id'])
                    for item in items:
                        nombre = await _get_item_name(item['item_type'], item['calidad'], guild_config['idioma'])
                        items_list.append(f"• {nombre} x{item['cantidad']}")
                value = "\n".join(items_list) if items_list else "Sin items"
                embed = discord.Embed(
                    title=f"⚔️ Batalla {battle_id} - {player}",
                    description=value,
                    color=discord.Color.orange()
                )
                pages.append(embed)
                battle_ids_players.append((battle_id, player))

        if not pages:
            await interaction.followup.send("No hay solicitudes pendientes.", ephemeral=True)
            return

        view = PendingView(pages, battle_ids_players, guild_config)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=False)


async def setup(bot):
    await bot.add_cog(ConfigCog(bot))