# tasks/monitor.py
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import tasks

import database
import albion_api

# Configurar logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BattleReportView(discord.ui.View):
    """
    Vista con botones para generar reportes detallados de una batalla.
    Se adjunta al mensaje de notificación de una nueva batalla con bajas.
    """

    def __init__(self, battle_id: int, guild_config: Dict[str, Any]):
        super().__init__(timeout=None)  # Sin timeout para que los botones funcionen siempre
        self.battle_id = battle_id
        self.guild_config = guild_config

    @discord.ui.button(label="📋 Reporte por jugador", style=discord.ButtonStyle.primary)
    async def individual_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Genera un reporte detallado por cada jugador que murió en la batalla,
        listando los items perdidos por cada uno.
        """
        await interaction.response.defer(ephemeral=True)  # Indicar que estamos procesando
        try:
            # Obtener datos de la base de datos para esta batalla
            # Nota: Necesitarás implementar consultas en database.py para obtener muertes e items por battle_id
            # Aquí asumimos que existen funciones: obtener_muertes_por_batalla(battle_id) y obtener_items_por_muerte(muerte_id)
            muertes = database.obtener_muertes_por_batalla(self.battle_id)
            if not muertes:
                await interaction.followup.send("No se encontraron muertes para esta batalla.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"📜 Reporte de bajas - Batalla {self.battle_id}",
                color=discord.Color.blue()
            )
            for muerte in muertes:
                items = database.obtener_items_por_muerte(muerte['id'])
                # Construir lista de items con nombres localizados
                lista_items = []
                for item in items:
                    # Obtener nombre localizado (función a implementar en albion_api o database)
                    nombre_item = await self._get_item_name(item['item_type'], item['calidad'])
                    cantidad = item['cantidad']
                    lista_items.append(f"{nombre_item} x{cantidad}")

                embed.add_field(
                    name=f"⚔️ {muerte['player_name']}",
                    value="\n".join(lista_items) if lista_items else "Sin items registrados",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en individual_report: {e}")
            await interaction.followup.send("Ocurrió un error al generar el reporte.", ephemeral=True)

    @discord.ui.button(label="🛒 Resumen de compras", style=discord.ButtonStyle.secondary)
    async def summary_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Genera un resumen agrupado de todos los items perdidos en la batalla,
        útil como lista de compras para reequipos.
        """
        await interaction.response.defer(ephemeral=True)
        try:
            # Obtener todos los items perdidos en la batalla (quizás con una consulta agrupada)
            items_agrupados = database.obtener_items_agrupados_por_batalla(self.battle_id)
            if not items_agrupados:
                await interaction.followup.send("No hay items registrados para esta batalla.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"🛒 Lista de compras - Batalla {self.battle_id}",
                description="Items necesarios para reequipar todas las bajas",
                color=discord.Color.green()
            )
            for item in items_agrupados:
                nombre_item = await self._get_item_name(item['item_type'], item['calidad'])
                embed.add_field(
                    name=nombre_item,
                    value=f"Cantidad: {item['total_cantidad']}",
                    inline=True
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en summary_report: {e}")
            await interaction.followup.send("Ocurrió un error al generar el resumen.", ephemeral=True)

    async def _get_item_name(self, item_type: str, calidad: int) -> str:
        """
        Obtiene el nombre localizado de un item según el idioma del gremio.
        """
        idioma = self.guild_config.get('idioma', 'es')
        item_data = await albion_api.get_item_data(item_type, idioma)
        if item_data:
            nombre = albion_api.get_localized_name(item_data, idioma)
            if calidad > 0:
                # Añadir calidad si es mayor que 0 (normal)
                nombre += f" (Calidad {calidad})"
            return nombre
        else:
            return item_type  # fallback al código


class Monitor:
    """
    Clase encargada de monitorear nuevas batallas de los gremios registrados.
    Ejecuta una tarea en segundo plano que consulta la API de Albion periódicamente.
    """

    def __init__(self, bot: discord.Client):
        self.bot = bot

    @tasks.loop(minutes=2)  # Ejecutar cada 2 minutos (ajustable)
    async def check_new_battles(self):
        """
        Tarea programada que recorre todos los gremios activos y verifica nuevas batallas.
        """
        logger.info("Iniciando verificación de nuevas batallas...")
        try:
            gremios = database.obtener_gremios_activos()
            for guild_config in gremios:
                await self.process_guild(guild_config)
        except Exception as e:
            logger.error(f"Error en check_new_battles: {e}")

    async def process_guild(self, guild_config: Dict[str, Any]):
        """
        Procesa un gremio: obtiene sus batallas recientes y las procesa una por una.
        """
        albion_guild_id = guild_config['albion_guild_id']
        logger.info(f"Procesando gremio {guild_config['nombre_gremio']} (ID: {albion_guild_id})")

        try:
            # Obtener batallas del último día (máx 10 para no saturar)
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
            logger.error(f"Error procesando gremio {guild_config['nombre_gremio']}: {e}")

    async def process_battle(self, battle_data: Dict[str, Any], guild_config: Dict[str, Any]):
        """
        Procesa una batalla individual: registra la batalla, obtiene sus eventos,
        detecta víctimas del gremio, registra muertes e items, y envía notificación a Discord.
        """
        battle_id = battle_data['id']
        logger.info(f"Procesando batalla {battle_id} para gremio {guild_config['nombre_gremio']}")

        try:
            # Extraer datos básicos
            start_time = battle_data.get('startTime')
            total_fame = battle_data.get('totalFame')
            total_kills = battle_data.get('totalKills')

            # Registrar la batalla en la base de datos (la fecha se convierte automáticamente en database.py)
            database.registrar_batalla(battle_id, start_time, total_fame, total_kills)

            # Obtener eventos (muertes) de la batalla
            events = await albion_api.get_battle_events(battle_id, limit=51)
            if not events:
                logger.warning(f"No se pudieron obtener eventos para batalla {battle_id}")
                return

            muertes_gremio = 0
            for idx, event in enumerate(events):
                victim = event.get('Victim')
                if not victim:
                    continue

                # Verificar si la víctima pertenece al gremio que nos interesa
                if victim.get('GuildId') == guild_config['albion_guild_id']:
                    muertes_gremio += 1
                    # Registrar muerte
                    player_id = victim['Id']
                    player_name = victim['Name']
                    timestamp = event.get('TimeStamp')

                    muerte_id = database.registrar_muerte(
                        battle_id, idx, player_id, player_name,
                        guild_config['albion_guild_id'], timestamp
                    )

                    # Registrar items perdidos
                    equipment = victim.get('Equipment', {})
                    for slot, item_data in equipment.items():
                        if item_data and isinstance(item_data, dict):
                            item_type = item_data.get('Type')
                            if item_type:
                                calidad = item_data.get('Quality', 0)
                                cantidad = item_data.get('Count', 1)
                                database.registrar_item(muerte_id, slot, item_type, calidad, cantidad)

                    logger.info(f"Muerte registrada: {player_name} en batalla {battle_id}")

            # Si hubo bajas del gremio, enviar notificación al canal correspondiente
            if muertes_gremio > 0:
                await self.send_battle_notification(battle_id, muertes_gremio, guild_config, start_time, total_fame, total_kills)
            else:
                logger.debug(f"Batalla {battle_id} sin bajas del gremio.")

        except Exception as e:
            logger.error(f"Error procesando batalla {battle_id}: {e}")

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
            # Obtener el canal usando fetch_channel (más fiable que get_channel)
            channel = await self.bot.fetch_channel(int(canal_id))
        except (ValueError, discord.NotFound, discord.Forbidden) as e:
            logger.error(f"No se pudo obtener el canal {canal_id}: {e}")
            return

        # Crear embed con información básica
        embed = discord.Embed(
            title=f"⚔️ Batalla Detectada: {battle_id}",
            description=f"Se han registrado **{num_muertes}** bajas de **{guild_config['nombre_gremio']}**.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        if start_time:
            embed.add_field(name="📅 Inicio", value=start_time.replace('T', ' ').split('.')[0], inline=True)
        if total_fame:
            embed.add_field(name="💰 Fama total", value=f"{total_fame:,}", inline=True)
        if total_kills:
            embed.add_field(name="💀 Asesinatos", value=total_kills, inline=True)

        # Crear vista con botones
        view = BattleReportView(battle_id, guild_config)

        try:
            await channel.send(embed=embed, view=view)
            logger.info(f"Notificación enviada para batalla {battle_id} al canal {channel.name}")
        except discord.Forbidden:
            logger.error(f"Permisos insuficientes para enviar mensaje en {channel.name}")
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Discord: {e}")