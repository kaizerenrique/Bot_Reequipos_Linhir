# tasks/monitor.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import discord
from discord.ext import tasks

import database
import albion_api

logger = logging.getLogger(__name__)


def parse_item_type(item_type: str) -> Tuple[str, int]:
    """
    Separa un identificador de item en su parte base y el nivel de encantamiento.
    Ejemplo: 'T4_ARMOR_CLOTH_SET2@1' -> ('T4_ARMOR_CLOTH_SET2', 1)
    Si no tiene '@', el nivel de encantamiento es 0.
    """
    if '@' in item_type:
        base, enchant = item_type.split('@', 1)
        try:
            enchant_level = int(enchant)
        except ValueError:
            enchant_level = 0
        return base, enchant_level
    else:
        return item_type, 0


class PaginatedReportView(discord.ui.View):
    """
    Vista con botones para navegar entre páginas de un reporte.
    """

    def __init__(self, pages: List[discord.Embed], timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        """Actualiza el estado de los botones según la página actual."""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page == len(self.pages) - 1
        self.last_page.disabled = self.current_page == len(self.pages) - 1

    async def show_page(self, interaction: discord.Interaction):
        """Muestra la página actual."""
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


class BattleReportView(discord.ui.View):
    """
    Vista principal con botones para generar reportes de una batalla.
    """

    def __init__(self, battle_id: int, guild_config: Dict[str, Any]):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.guild_config = guild_config

    @discord.ui.button(label="📋 Reporte por jugador", style=discord.ButtonStyle.primary)
    async def individual_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Genera un reporte detallado por cada jugador que murió en la batalla,
        listando los items perdidos por cada uno.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            muertes = database.obtener_muertes_por_batalla(self.battle_id)
            if not muertes:
                await interaction.followup.send("No se encontraron muertes para esta batalla.", ephemeral=True)
                return

            pages = []
            current_embed = discord.Embed(
                title=f"📜 Reporte de bajas - Batalla {self.battle_id}",
                color=discord.Color.blue()
            )
            field_count = 0
            MAX_FIELDS_PER_PAGE = 10  # Discord permite hasta 25, pero usamos 10 para margen

            for muerte in muertes:
                items = database.obtener_items_por_muerte(muerte['id'])
                item_lines = []
                for item in items:
                    nombre = await self._get_item_name(item['item_type'], item['calidad'])
                    cantidad = item['cantidad']
                    item_lines.append(f"• {nombre} x{cantidad}")

                value = "\n".join(item_lines) if item_lines else "Sin items registrados"

                if field_count >= MAX_FIELDS_PER_PAGE:
                    pages.append(current_embed)
                    current_embed = discord.Embed(
                        title=f"📜 Reporte de bajas - Batalla {self.battle_id} (continuación)",
                        color=discord.Color.blue()
                    )
                    field_count = 0

                current_embed.add_field(
                    name=f"⚔️ {muerte['player_name']}",
                    value=value,
                    inline=False
                )
                field_count += 1

            if field_count > 0:
                pages.append(current_embed)

            if not pages:
                await interaction.followup.send("No hay datos para mostrar.", ephemeral=True)
                return

            if len(pages) == 1:
                await interaction.followup.send(embed=pages[0], ephemeral=True)
            else:
                view = PaginatedReportView(pages)
                await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en individual_report: {e}", exc_info=True)
            await interaction.followup.send("Ocurrió un error al generar el reporte.", ephemeral=True)

    @discord.ui.button(label="🛒 Resumen de compras", style=discord.ButtonStyle.secondary)
    async def summary_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Genera un resumen agrupado de todos los items perdidos en la batalla,
        útil como lista de compras para reequipos.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            items_agrupados = database.obtener_items_agrupados_por_batalla(self.battle_id)
            if not items_agrupados:
                await interaction.followup.send("No hay items registrados para esta batalla.", ephemeral=True)
                return

            pages = []
            current_lines = []
            MAX_LINES_PER_PAGE = 20  # Ajustable para evitar exceder límite de caracteres

            for item in items_agrupados:
                nombre = await self._get_item_name(item['item_type'], item['calidad'])
                line = f"• {nombre} x{item['total_cantidad']}"

                if len(current_lines) >= MAX_LINES_PER_PAGE:
                    embed = discord.Embed(
                        title=f"🛒 Lista de compras - Batalla {self.battle_id}",
                        description="\n".join(current_lines),
                        color=discord.Color.green()
                    )
                    pages.append(embed)
                    current_lines = []

                current_lines.append(line)

            if current_lines:
                embed = discord.Embed(
                    title=f"🛒 Lista de compras - Batalla {self.battle_id}",
                    description="\n".join(current_lines),
                    color=discord.Color.green()
                )
                pages.append(embed)

            if len(pages) == 1:
                await interaction.followup.send(embed=pages[0], ephemeral=True)
            else:
                view = PaginatedReportView(pages)
                await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en summary_report: {e}", exc_info=True)
            await interaction.followup.send("Ocurrió un error al generar el resumen.", ephemeral=True)

    async def _get_item_name(self, item_type: str, calidad: int) -> str:
        """
        Obtiene el nombre localizado del item, separando el tipo base del encantamiento.
        Primero intenta con el tipo base (sin @), y si falla, usa el completo.
        Añade el nivel de encantamiento y la calidad si corresponde.
        """
        idioma = self.guild_config.get('idioma', 'es')
        base_type, enchant_level = parse_item_type(item_type)

        # Intentar obtener datos del item base
        item_data = await albion_api.get_item_data(base_type, idioma)
        if item_data:
            nombre = albion_api.get_localized_name(item_data, idioma)
        else:
            # Fallback: intentar con el tipo completo (por si acaso)
            item_data = await albion_api.get_item_data(item_type, idioma)
            nombre = albion_api.get_localized_name(item_data, idioma) if item_data else item_type
            logger.warning(f"No se pudo obtener nombre para item base {base_type}, usando fallback {item_type}")

        # Añadir nivel de encantamiento si > 0
        if enchant_level > 0:
            nombre += f" .{enchant_level}"

        # Añadir calidad si es mayor que 0 (normal)
        if calidad > 0:
            calidad_texto = {1: "Bueno", 2: "Excelente", 3: "Sobresaliente", 4: "Maestro"}.get(calidad, f"Calidad {calidad}")
            nombre += f" ({calidad_texto})"

        return nombre


class Monitor:
    """
    Clase encargada de monitorear nuevas batallas de los gremios registrados.
    Ejecuta una tarea en segundo plano que consulta la API de Albion periódicamente.
    """

    def __init__(self, bot: discord.Client):
        self.bot = bot

    @tasks.loop(minutes=2)
    async def check_new_battles(self):
        """Tarea programada que recorre todos los gremios activos y verifica nuevas batallas."""
        logger.info("Iniciando verificación de nuevas batallas...")
        try:
            gremios = database.obtener_gremios_activos()
            for guild_config in gremios:
                await self.process_guild(guild_config)
        except Exception as e:
            logger.error(f"Error en check_new_battles: {e}", exc_info=True)

    async def process_guild(self, guild_config: Dict[str, Any]):
        """Procesa un gremio: obtiene sus batallas recientes y las procesa una por una."""
        albion_guild_id = guild_config['albion_guild_id']
        logger.info(f"Procesando gremio {guild_config['nombre_gremio']} (ID: {albion_guild_id})")

        try:
            battles = await albion_api.get_battles(albion_guild_id, limit=10, range='day')
            if not battles:
                logger.debug(f"No hay batallas recientes para {guild_config['nombre_gremio']}")
                return

            for battle in battles:
                battle_id = battle['id']
                if database.batalla_ya_procesada(battle_id):
                    logger.debug(f"Batalla {battle_id} ya procesada, saltando.")
                    continue

                logger.info(f"Nueva batalla detectada: {battle_id}")
                await self.process_battle(battle, guild_config)

        except Exception as e:
            logger.error(f"Error procesando gremio {guild_config['nombre_gremio']}: {e}", exc_info=True)

    async def process_battle(self, battle_data: Dict[str, Any], guild_config: Dict[str, Any]):
        """
        Procesa una batalla individual: registra la batalla, obtiene sus eventos,
        detecta víctimas del gremio, registra muertes e items, y envía notificación a Discord.
        """
        battle_id = battle_data['id']
        logger.info(f"Procesando batalla {battle_id} para gremio {guild_config['nombre_gremio']}")

        try:
            start_time = battle_data.get('startTime')
            total_fame = battle_data.get('totalFame')
            total_kills = battle_data.get('totalKills')

            database.registrar_batalla(battle_id, start_time, total_fame, total_kills)

            events = await albion_api.get_battle_events(battle_id, limit=51)
            if not events:
                logger.warning(f"No se pudieron obtener eventos para batalla {battle_id}")
                return

            muertes_gremio = 0
            for idx, event in enumerate(events):
                victim = event.get('Victim')
                if not victim:
                    continue

                if victim.get('GuildId') == guild_config['albion_guild_id']:
                    muertes_gremio += 1
                    player_id = victim['Id']
                    player_name = victim['Name']
                    timestamp = event.get('TimeStamp')

                    muerte_id = database.registrar_muerte(
                        battle_id, idx, player_id, player_name,
                        guild_config['albion_guild_id'], timestamp
                    )

                    equipment = victim.get('Equipment', {})
                    for slot, item_data in equipment.items():
                        if item_data and isinstance(item_data, dict):
                            item_type = item_data.get('Type')
                            if item_type:
                                calidad = item_data.get('Quality', 0)
                                cantidad = item_data.get('Count', 1)
                                database.registrar_item(muerte_id, slot, item_type, calidad, cantidad)

                    logger.info(f"Muerte registrada: {player_name} en batalla {battle_id}")

            if muertes_gremio > 0:
                await self.send_battle_notification(battle_id, muertes_gremio, guild_config, start_time, total_fame, total_kills)
            else:
                logger.debug(f"Batalla {battle_id} sin bajas del gremio.")

        except Exception as e:
            logger.error(f"Error procesando batalla {battle_id}: {e}", exc_info=True)

    async def send_battle_notification(self, battle_id: int, num_muertes: int, guild_config: Dict[str, Any],
                                       start_time: Optional[str], total_fame: Optional[int], total_kills: Optional[int]):
        """
        Envía un mensaje embed al canal configurado con la información de la batalla y los botones de reporte.
        """
        canal_id = guild_config.get('canal_reportes_batalla')
        if not canal_id:
            logger.warning(f"Gremio {guild_config['nombre_gremio']} no tiene canal de reportes configurado.")
            return

        try:
            channel = await self.bot.fetch_channel(int(canal_id))
        except (ValueError, discord.NotFound, discord.Forbidden) as e:
            logger.error(f"No se pudo obtener el canal {canal_id}: {e}")
            return

        embed = discord.Embed(
            title=f"⚔️ Batalla Detectada: {battle_id}",
            description=f"Se han registrado **{num_muertes}** bajas de **{guild_config['nombre_gremio']}**.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        if start_time:
            fecha_formateada = start_time.replace('T', ' ').split('.')[0]
            embed.add_field(name="📅 Inicio", value=fecha_formateada, inline=True)
        if total_fame:
            embed.add_field(name="💰 Fama total", value=f"{total_fame:,}", inline=True)
        if total_kills:
            embed.add_field(name="💀 Asesinatos", value=total_kills, inline=True)

        view = BattleReportView(battle_id, guild_config)

        try:
            await channel.send(embed=embed, view=view)
            logger.info(f"Notificación enviada para batalla {battle_id} al canal {channel.name}")
        except discord.Forbidden:
            logger.error(f"Permisos insuficientes para enviar mensaje en {channel.name}")
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Discord: {e}", exc_info=True)