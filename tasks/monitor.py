import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import discord
from discord.ext import tasks

import database
import albion_api

logger = logging.getLogger(__name__)


def parse_item_type(item_type: str) -> Tuple[str, int]:
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
    """Vista con botones para navegar entre páginas de un reporte."""

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


class PlayerSelectView(discord.ui.View):
    """Vista con un Select paginado para elegir un jugador cuando hay más de 25."""

    def __init__(self, battle_id: int, jugadores: List[str], guild_config: Dict[str, Any], items_por_pagina: int = 25):
        super().__init__(timeout=60)
        self.battle_id = battle_id
        self.jugadores = jugadores
        self.guild_config = guild_config
        self.items_por_pagina = items_por_pagina
        self.current_page = 0
        self.max_page = (len(jugadores) - 1) // items_por_pagina
        self.update_select()

    def update_select(self):
        self.clear_items()
        start = self.current_page * self.items_por_pagina
        end = start + self.items_por_pagina
        page_jugadores = self.jugadores[start:end]

        select = discord.ui.Select(
            placeholder=f"Selecciona un jugador (página {self.current_page + 1}/{self.max_page + 1})",
            options=[discord.SelectOption(label=j, value=j) for j in page_jugadores]
        )

        async def select_callback(interaction: discord.Interaction):
            player = interaction.data['values'][0]
            database.marcar_solicitado(self.battle_id, player)

            muertes = database.obtener_muertes_por_batalla(self.battle_id)
            items_list = []
            for muerte in muertes:
                if muerte['player_name'] == player:
                    items = database.obtener_items_por_muerte(muerte['id'])
                    for item in items:
                        nombre = await self._get_item_name(item['item_type'], item['calidad'])
                        items_list.append(f"{nombre} x{item['cantidad']}")

            canal_id = self.guild_config.get('canal_solicitudes')
            if canal_id:
                canal = interaction.guild.get_channel(int(canal_id))
                if canal:
                    embed = discord.Embed(
                        title=f"🔄 Solicitud de reequipo",
                        description=f"**Jugador:** {player}\n**Batalla:** {self.battle_id}",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Items perdidos", value="\n".join(items_list) if items_list else "Sin items registrados", inline=False)
                    await canal.send(embed=embed)

            await interaction.response.send_message(f"✅ Solicitud registrada para **{player}**.", ephemeral=True)
            self.stop()

        select.callback = select_callback
        self.add_item(select)

        if self.max_page > 0:
            if self.current_page > 0:
                prev_button = discord.ui.Button(label="◀️ Anterior", style=discord.ButtonStyle.secondary)
                async def prev_callback(interaction):
                    self.current_page -= 1
                    self.update_select()
                    await interaction.response.edit_message(view=self)
                prev_button.callback = prev_callback
                self.add_item(prev_button)

            if self.current_page < self.max_page:
                next_button = discord.ui.Button(label="Siguiente ▶️", style=discord.ButtonStyle.secondary)
                async def next_callback(interaction):
                    self.current_page += 1
                    self.update_select()
                    await interaction.response.edit_message(view=self)
                next_button.callback = next_callback
                self.add_item(next_button)

    async def _get_item_name(self, item_type: str, calidad: int) -> str:
        idioma = self.guild_config.get('idioma', 'es')
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


class BattleReportView(discord.ui.View):
    """Vista principal con botones para reportes y solicitudes, organizados en dos filas."""

    def __init__(self, battle_id: int, guild_config: Dict[str, Any]):
        super().__init__(timeout=None)
        self.battle_id = battle_id
        self.guild_config = guild_config

        # Fila 0: botones de acción principales
        self.add_item(discord.ui.Button(
            label="📋 Reporte por jugador",
            style=discord.ButtonStyle.primary,
            custom_id=f"individual_{battle_id}",
            row=0
        ))
        self.add_item(discord.ui.Button(
            label="🛒 Resumen de compras",
            style=discord.ButtonStyle.secondary,
            custom_id=f"summary_{battle_id}",
            row=0
        ))
        self.add_item(discord.ui.Button(
            label="🔄 Solicitar reequipo",
            style=discord.ButtonStyle.success,
            custom_id=f"solicitar_{battle_id}",
            row=0
        ))

        # Fila 1: botón de enlace externo
        albionbb_url = f"https://albionbb.com/battles/{battle_id}"
        self.add_item(discord.ui.Button(
            label="🌐 Ver en AlbionBB",
            style=discord.ButtonStyle.link,
            url=albionbb_url,
            row=1
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get('custom_id', '')
        if custom_id.startswith('individual_'):
            await self.individual_report(interaction)
        elif custom_id.startswith('summary_'):
            await self.summary_report(interaction)
        elif custom_id.startswith('solicitar_'):
            await self.solicitar_reequipo(interaction)
        return True

    async def individual_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            muertes = database.obtener_muertes_por_batalla(self.battle_id)
            if not muertes:
                await interaction.followup.send("No se encontraron muertes.", ephemeral=True)
                return

            pages = []
            current_embed = discord.Embed(
                title=f"📜 Reporte de bajas - Batalla {self.battle_id}",
                color=discord.Color.blue()
            )
            field_count = 0
            MAX_FIELDS = 10

            for muerte in muertes:
                items = database.obtener_items_por_muerte(muerte['id'])
                item_lines = []
                for item in items:
                    nombre = await self._get_item_name(item['item_type'], item['calidad'])
                    item_lines.append(f"• {nombre} x{item['cantidad']}")

                value = "\n".join(item_lines) if item_lines else "Sin items registrados"

                if field_count >= MAX_FIELDS:
                    pages.append(current_embed)
                    current_embed = discord.Embed(
                        title=f"📜 Reporte de bajas (continuación)",
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
                await interaction.followup.send("No hay datos.", ephemeral=True)
                return

            await self._send_paginated_report(interaction, pages, 'canal_reportes_individual')

        except Exception as e:
            logger.error(f"Error en individual_report: {e}", exc_info=True)
            await interaction.followup.send("Error al generar el reporte.", ephemeral=True)

    async def summary_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            items = database.obtener_items_agrupados_por_batalla(self.battle_id)
            if not items:
                await interaction.followup.send("No hay items registrados.", ephemeral=True)
                return

            pages = []
            current_lines = []
            MAX_LINES = 20

            for item in items:
                nombre = await self._get_item_name(item['item_type'], item['calidad'])
                line = f"• {nombre} x{item['total_cantidad']}"

                if len(current_lines) >= MAX_LINES:
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

            await self._send_paginated_report(interaction, pages, 'canal_resumen')

        except Exception as e:
            logger.error(f"Error en summary_report: {e}", exc_info=True)
            await interaction.followup.send("Error al generar el resumen.", ephemeral=True)

    async def solicitar_reequipo(self, interaction: discord.Interaction):
        jugadores = database.obtener_jugadores_por_batalla(self.battle_id)
        if not jugadores:
            await interaction.response.send_message("No hay jugadores en esta batalla.", ephemeral=True)
            return

        view = PlayerSelectView(self.battle_id, jugadores, self.guild_config)
        await interaction.response.send_message("Selecciona el jugador que solicita reequipo:", view=view, ephemeral=True)

    async def _send_paginated_report(self, interaction: discord.Interaction, pages: List[discord.Embed], channel_key: str):
        channel_id = self.guild_config.get(channel_key)
        if not channel_id:
            await interaction.followup.send("Canal no configurado.", ephemeral=True)
            return

        try:
            channel = interaction.guild.get_channel(int(channel_id))
            if not channel:
                channel = await interaction.guild.fetch_channel(int(channel_id))

            if len(pages) == 1:
                await channel.send(embed=pages[0])
            else:
                view = PaginatedReportView(pages)
                await channel.send(embed=pages[0], view=view)

            await interaction.followup.send(f"✅ Reporte enviado a {channel.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error enviando a canal {channel_id}: {e}")
            await interaction.followup.send("Error al enviar el reporte.", ephemeral=True)

    async def _get_item_name(self, item_type: str, calidad: int) -> str:
        idioma = self.guild_config.get('idioma', 'es')
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


class Monitor:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @tasks.loop(minutes=2)
    async def check_new_battles(self):
        logger.info("Verificando nuevas batallas...")
        try:
            gremios = database.obtener_gremios_activos()
            for guild_config in gremios:
                await self.process_guild(guild_config)
        except Exception as e:
            logger.error(f"Error en check_new_battles: {e}", exc_info=True)

    async def process_guild(self, guild_config: Dict[str, Any]):
        albion_guild_id = guild_config['albion_guild_id']
        try:
            battles = await albion_api.get_battles(albion_guild_id, limit=10, range='day')
            if not battles:
                return

            for battle in battles:
                battle_id = battle['id']
                if database.batalla_ya_procesada(battle_id):
                    continue

                logger.info(f"Nueva batalla: {battle_id}")
                await self.process_battle(battle, guild_config)

        except Exception as e:
            logger.error(f"Error procesando gremio {guild_config['nombre_gremio']}: {e}", exc_info=True)

    async def process_battle(self, battle_data: Dict[str, Any], guild_config: Dict[str, Any]):
        battle_id = battle_data['id']
        try:
            start_time = battle_data.get('startTime')
            total_fame = battle_data.get('totalFame')
            total_kills = battle_data.get('totalKills')

            database.registrar_batalla(battle_id, start_time, total_fame, total_kills)

            events = await albion_api.get_battle_events(battle_id, limit=51)
            if not events:
                return

            muertes_gremio = 0
            for idx, event in enumerate(events):
                victim = event.get('Victim')
                if not victim or victim.get('GuildId') != guild_config['albion_guild_id']:
                    continue

                muertes_gremio += 1
                muerte_id = database.registrar_muerte(
                    battle_id, idx, victim['Id'], victim['Name'],
                    guild_config['albion_guild_id'], event.get('TimeStamp')
                )

                equipment = victim.get('Equipment', {})
                for slot, item_data in equipment.items():
                    if item_data and isinstance(item_data, dict):
                        item_type = item_data.get('Type')
                        if item_type:
                            database.registrar_item(
                                muerte_id, slot, item_type,
                                item_data.get('Quality', 0),
                                item_data.get('Count', 1)
                            )

                logger.info(f"Muerte registrada: {victim['Name']}")

            if muertes_gremio > 0:
                await self.send_battle_notification(battle_id, muertes_gremio, guild_config, start_time, total_fame, total_kills)

        except Exception as e:
            logger.error(f"Error procesando batalla {battle_id}: {e}", exc_info=True)

    async def send_battle_notification(self, battle_id: int, num_muertes: int, guild_config: Dict[str, Any],
                                       start_time: Optional[str], total_fame: Optional[int], total_kills: Optional[int]):
        canal_id = guild_config.get('canal_reportes_batalla')
        if not canal_id:
            return

        try:
            channel = await self.bot.fetch_channel(int(canal_id))
        except Exception as e:
            logger.error(f"No se pudo obtener el canal {canal_id}: {e}")
            return

        embed = discord.Embed(
            title=f"⚔️ Batalla Detectada: {battle_id}",
            description=f"**{num_muertes}** bajas de **{guild_config['nombre_gremio']}**.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        if start_time:
            embed.add_field(name="📅 Inicio", value=start_time.replace('T', ' ').split('.')[0])
        if total_fame:
            embed.add_field(name="💰 Fama total", value=f"{total_fame:,}")
        if total_kills:
            embed.add_field(name="💀 Asesinatos", value=total_kills)

        view = BattleReportView(battle_id, guild_config)

        try:
            await channel.send(embed=embed, view=view)
            logger.info(f"Notificación enviada para batalla {battle_id}")
        except Exception as e:
            logger.error(f"Error enviando notificación: {e}")