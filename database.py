import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def convertir_fecha_albion(fecha_str: Optional[str]) -> Optional[str]:
    if not fecha_str:
        return None
    fecha_iso = fecha_str.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(fecha_iso)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return fecha_str.split('.')[0].replace('T', ' ')


# ==================== GREMIOS ====================

def registrar_gremio(discord_guild_id: str, albion_guild_id: str, nombre_gremio: str,
                     idioma: str, canal_reportes_batalla: str,
                     canal_reportes_individual: str, canal_resumen: str,
                     canal_solicitudes: str):
    conn = get_connection()
    cursor = conn.cursor()
    sql = """INSERT INTO gremios 
             (discord_guild_id, albion_guild_id, nombre_gremio, idioma, 
              canal_reportes_batalla, canal_reportes_individual, canal_resumen, canal_solicitudes)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    cursor.execute(sql, (discord_guild_id, albion_guild_id, nombre_gremio,
                         idioma, canal_reportes_batalla,
                         canal_reportes_individual, canal_resumen,
                         canal_solicitudes))
    conn.commit()
    cursor.close()
    conn.close()


def obtener_gremios_activos() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM gremios WHERE activo = TRUE")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_gremio_por_discord_id(discord_guild_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM gremios WHERE discord_guild_id = %s AND activo = TRUE", (discord_guild_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def obtener_todos_gremios() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM gremios")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def actualizar_estado_gremio(discord_guild_id: str, activo: bool):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE gremios SET activo = %s WHERE discord_guild_id = %s", (activo, discord_guild_id))
    conn.commit()
    cursor.close()
    conn.close()


def eliminar_gremio(discord_guild_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gremios WHERE discord_guild_id = %s", (discord_guild_id,))
    conn.commit()
    cursor.close()
    conn.close()


# ==================== BATALLAS ====================

def batalla_ya_procesada(battle_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM batallas WHERE battle_id = %s", (battle_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None


def registrar_batalla(battle_id: int, fecha: Optional[str], total_fame: int, total_kills: int):
    fecha_mysql = convertir_fecha_albion(fecha)
    conn = get_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO batallas (battle_id, fecha, total_fame, total_kills) VALUES (%s, %s, %s, %s)"
    cursor.execute(sql, (battle_id, fecha_mysql, total_fame, total_kills))
    conn.commit()
    cursor.close()
    conn.close()


# ==================== MUERTES E ITEMS ====================

def registrar_muerte(battle_id: int, event_index: int, player_albion_id: str,
                     player_name: str, guild_id_albion: str, timestamp: Optional[str]) -> int:
    timestamp_mysql = convertir_fecha_albion(timestamp)
    conn = get_connection()
    cursor = conn.cursor()
    sql = """INSERT INTO muertes 
             (battle_id, event_index, player_albion_id, player_name, guild_id_albion, timestamp_muerte)
             VALUES (%s, %s, %s, %s, %s, %s)"""
    cursor.execute(sql, (battle_id, event_index, player_albion_id, player_name,
                         guild_id_albion, timestamp_mysql))
    muerte_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return muerte_id


def registrar_item(muerte_id: int, slot: str, item_type: str, calidad: int, cantidad: int):
    conn = get_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO items_perdidos (muerte_id, slot, item_type, calidad, cantidad) VALUES (%s, %s, %s, %s, %s)"
    cursor.execute(sql, (muerte_id, slot, item_type, calidad, cantidad))
    conn.commit()
    cursor.close()
    conn.close()


def obtener_muertes_por_batalla(battle_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM muertes WHERE battle_id = %s", (battle_id,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_items_por_muerte(muerte_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items_perdidos WHERE muerte_id = %s", (muerte_id,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_items_agrupados_por_batalla(battle_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT ip.item_type, ip.calidad, SUM(ip.cantidad) as total_cantidad
        FROM items_perdidos ip
        JOIN muertes m ON ip.muerte_id = m.id
        WHERE m.battle_id = %s
        GROUP BY ip.item_type, ip.calidad
    """
    cursor.execute(sql, (battle_id,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


# ==================== SOLICITUDES DE REEQUIPO ====================

def obtener_jugadores_por_batalla(battle_id: int) -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT player_name FROM muertes WHERE battle_id = %s", (battle_id,))
    result = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return result


def marcar_solicitado(battle_id: int, player_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE muertes SET solicitado = TRUE WHERE battle_id = %s AND player_name = %s", (battle_id, player_name))
    conn.commit()
    cursor.close()
    conn.close()


def marcar_como_entregado(battle_id: int, player_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE muertes SET estado = 'entregado' WHERE battle_id = %s AND player_name = %s AND estado = 'pendiente'",
        (battle_id, player_name)
    )
    conn.commit()
    cursor.close()
    conn.close()


def obtener_solicitudes_pendientes(guild_id_albion: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = """
        SELECT m.*, b.fecha as battle_fecha
        FROM muertes m
        JOIN batallas b ON m.battle_id = b.battle_id
        WHERE m.guild_id_albion = %s AND m.solicitado = TRUE AND m.estado = 'pendiente'
        ORDER BY m.timestamp_muerte DESC
    """
    cursor.execute(sql, (guild_id_albion,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


# ==================== FUSIÓN DE BATALLAS ====================

def obtener_muertes_por_lista_batallas(battle_ids: List[int]) -> List[Dict[str, Any]]:
    if not battle_ids:
        return []
    placeholders = ','.join(['%s'] * len(battle_ids))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = f"SELECT * FROM muertes WHERE battle_id IN ({placeholders})"
    cursor.execute(sql, battle_ids)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_items_agrupados_por_lista_batallas(battle_ids: List[int]) -> List[Dict[str, Any]]:
    if not battle_ids:
        return []
    placeholders = ','.join(['%s'] * len(battle_ids))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    sql = f"""
        SELECT ip.item_type, ip.calidad, SUM(ip.cantidad) as total_cantidad
        FROM items_perdidos ip
        JOIN muertes m ON ip.muerte_id = m.id
        WHERE m.battle_id IN ({placeholders})
        GROUP BY ip.item_type, ip.calidad
    """
    cursor.execute(sql, battle_ids)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result