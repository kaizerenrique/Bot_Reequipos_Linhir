# albion_api.py
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

BASE_URL = "https://gameinfo.albiononline.com/api/gameinfo"

logger = logging.getLogger(__name__)

# Cache de items: {item_type: {"data": item_data, "timestamp": datetime, "not_found": bool}}
item_cache = {}
CACHE_DURATION = timedelta(hours=24)


async def fetch_json(session: aiohttp.ClientSession, url: str) -> Optional[Any]:
    """
    Realiza una petición GET y retorna el JSON si la respuesta es 200.
    Maneja errores HTTP y de conexión.
    """
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            elif response.status == 404:
                logger.warning(f"Recurso no encontrado (404): {url}")
                return None
            else:
                logger.error(f"Error {response.status} en {url}")
                return None
    except aiohttp.ClientError as e:
        logger.error(f"Error de conexión en {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado en {url}: {e}")
        return None


async def get_battles(guild_id: str, limit: int = 50, offset: int = 0,
                      range: str = 'day', sort: str = 'recent') -> Optional[List[Dict]]:
    """
    Obtiene lista de batallas para un gremio específico.
    """
    url = f"{BASE_URL}/battles?range={range}&offset={offset}&limit={limit}&sort={sort}&guildId={guild_id}"
    async with aiohttp.ClientSession() as session:
        return await fetch_json(session, url)


async def get_battle_events(battle_id: int, limit: int = 51, offset: int = 0) -> Optional[List[Dict]]:
    """
    Obtiene los eventos (muertes) de una batalla específica.
    """
    url = f"{BASE_URL}/events/battle/{battle_id}?offset={offset}&limit={limit}"
    async with aiohttp.ClientSession() as session:
        return await fetch_json(session, url)


async def get_item_data(item_type: str, idioma: str = 'es') -> Optional[Dict]:
    """
    Obtiene la información detallada de un item desde la API.
    Implementa caché para evitar consultas repetidas.
    Si el item no existe (404), lo marca en caché para no volver a consultarlo.
    """
    now = datetime.now()

    # Verificar caché
    if item_type in item_cache:
        entry = item_cache[item_type]
        if now - entry['timestamp'] < CACHE_DURATION:
            if entry.get('not_found'):
                return None
            else:
                return entry['data']
        else:
            del item_cache[item_type]

    # Consultar API
    url = f"{BASE_URL}/items/{item_type}/data"
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)

    if data is None:
        item_cache[item_type] = {
            'data': None,
            'timestamp': now,
            'not_found': True
        }
        return None
    else:
        item_cache[item_type] = {
            'data': data,
            'timestamp': now,
            'not_found': False
        }
        return data


def get_localized_name(item_data: Optional[Dict], idioma: str = 'es') -> str:
    """
    Extrae el nombre localizado del item data.
    Si no hay datos o no existe localización, retorna el uniqueName como fallback.
    """
    if not item_data:
        return "Item desconocido"
    lang_key = 'ES-ES' if idioma == 'es' else 'EN-US'
    localized = item_data.get('localizedNames', {})
    return localized.get(lang_key, item_data.get('uniqueName', 'Item sin nombre'))