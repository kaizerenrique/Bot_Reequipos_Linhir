import aiohttp
import asyncio
from datetime import datetime, timedelta

BASE_URL = "https://gameinfo.albiononline.com/api/gameinfo"

# Cache simple para nombres de items: {item_type: {nombre_localizado, timestamp}}
item_name_cache = {}
CACHE_DURATION = timedelta(hours=24)

async def fetch_json(session, url):
    async with session.get(url) as response:
        if response.status == 200:
            return await response.json()
        else:
            print(f"Error {response.status} en {url}")
            return None

async def get_battles(guild_id, limit=50, offset=0, range='day', sort='recent'):
    url = f"{BASE_URL}/battles?range={range}&offset={offset}&limit={limit}&sort={sort}&guildId={guild_id}"
    async with aiohttp.ClientSession() as session:
        return await fetch_json(session, url)

async def get_battle_events(battle_id, limit=51, offset=0):
    url = f"{BASE_URL}/events/battle/{battle_id}?offset={offset}&limit={limit}"
    async with aiohttp.ClientSession() as session:
        return await fetch_json(session, url)

async def get_item_data(item_type, idioma='es'):
    # Verificar caché
    now = datetime.now()
    if item_type in item_name_cache:
        entry = item_name_cache[item_type]
        if now - entry['timestamp'] < CACHE_DURATION:
            return entry['data']
    # Si no está en caché, consultar API
    url = f"{BASE_URL}/items/{item_type}/data"
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, url)
        if data:
            item_name_cache[item_type] = {'data': data, 'timestamp': now}
        return data

def get_localized_name(item_data, idioma='es'):
    """Extrae el nombre localizado del item data."""
    if not item_data:
        return None
    # Las claves pueden ser 'ES-ES' o 'ES-ES'? El ejemplo muestra 'ES-ES' y 'EN-US'
    lang_key = 'ES-ES' if idioma == 'es' else 'EN-US'
    return item_data.get('localizedNames', {}).get(lang_key, item_data.get('uniqueName'))