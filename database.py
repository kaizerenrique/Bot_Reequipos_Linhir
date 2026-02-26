# database.py
import mysql.connector
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_connection():
    """Retorna una conexión a la base de datos."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )


def convertir_fecha_albion(fecha_str: Optional[str]) -> Optional[str]:
    """
    Convierte una fecha en formato ISO 8601 con 'Z' (ej: '2026-02-26T05:38:15.108776600Z')
    a formato 'YYYY-MM-DD HH:MM:SS' para MySQL.
    Si la fecha es None o vacía, retorna None.
    """
    if not fecha_str:
        return None
    fecha_iso = fecha_str.replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(fecha_iso)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return fecha_str.split('.')[0].replace('T', ' ')


def registrar_gremio(discord_guild_id: str, albion_guild_id: str, nombre_gremio: str,
                     idioma: str, canal_reportes_batalla: str,
                     canal_reportes_individual: str, canal_resumen: str):
    """Registra un nuevo gremio en la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()
    sql = """INSERT INTO gremios 
             (discord_guild_id, albion_guild_id, nombre_gremio, idioma, 
              canal_reportes_batalla, canal_reportes_individual, canal_resumen)
             VALUES (%s, %s, %s, %s, %s, %s, %s)"""
    cursor.execute(sql, (discord_guild_id, albion_guild_id, nombre_gremio,
                         idioma, canal_reportes_batalla,
                         canal_reportes_individual, canal_resumen))
    conn.commit()
    cursor.close()
    conn.close()


def obtener_gremios_activos() -> List[Dict[str, Any]]:
    """Retorna todos los gremios activos."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM gremios WHERE activo = TRUE")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def batalla_ya_procesada(battle_id: int) -> bool:
    """Verifica si una batalla ya fue procesada."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM batallas WHERE battle_id = %s", (battle_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None


def registrar_batalla(battle_id: int, fecha: Optional[str], total_fame: int, total_kills: int):
    """Registra una batalla en la base de datos."""
    fecha_mysql = convertir_fecha_albion(fecha)
    conn = get_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO batallas (battle_id, fecha, total_fame, total_kills) VALUES (%s, %s, %s, %s)"
    cursor.execute(sql, (battle_id, fecha_mysql, total_fame, total_kills))
    conn.commit()
    cursor.close()
    conn.close()


def registrar_muerte(battle_id: int, event_index: int, player_albion_id: str,
                     player_name: str, guild_id_albion: str, timestamp: Optional[str]) -> int:
    """Registra una muerte y retorna su ID."""
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
    """Registra un item perdido en una muerte."""
    conn = get_connection()
    cursor = conn.cursor()
    sql = "INSERT INTO items_perdidos (muerte_id, slot, item_type, calidad, cantidad) VALUES (%s, %s, %s, %s, %s)"
    cursor.execute(sql, (muerte_id, slot, item_type, calidad, cantidad))
    conn.commit()
    cursor.close()
    conn.close()


def obtener_muertes_por_batalla(battle_id: int) -> List[Dict[str, Any]]:
    """Obtiene todas las muertes de una batalla específica."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM muertes WHERE battle_id = %s", (battle_id,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_items_por_muerte(muerte_id: int) -> List[Dict[str, Any]]:
    """Obtiene todos los items perdidos en una muerte específica."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items_perdidos WHERE muerte_id = %s", (muerte_id,))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def obtener_items_agrupados_por_batalla(battle_id: int) -> List[Dict[str, Any]]:
    """
    Obtiene todos los items perdidos en una batalla, agrupados por tipo y calidad,
    sumando las cantidades.
    """
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