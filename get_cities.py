# get_cities.py

from dotenv import load_dotenv
import os
import vk_api
import json

# Загружаем переменные окружения
load_dotenv()

# Получаем токен из .env
USER_TOKEN = os.getenv("USER_TOKEN")
if not USER_TOKEN:
    raise ValueError("Требуется USER_TOKEN в файле .env")

vk_session = vk_api.VkApi(token=USER_TOKEN)
vk = vk_session.get_api()


def fetch_cities(query):
    """Получить города по запросу"""
    try:
        response = vk.database.getCities(country_id=1, q=query, count=100)
        return {city['title'].lower(): city['id'] for city in response['items']}
    except Exception as e:
        print(f"Ошибка при запросе для '{query}': {e}")
        return {}


# Словарь для хранения всех городов
all_cities = {}

# Поисковые запросы для охвата крупных регионов
queries = [
    'москва', 'спб', 'санкт-петербург', 'новосибирск', 'екатеринбург',
    'казань', 'самара', 'омск', 'челябинск', 'волгоград',
    'пермь', 'воронеж', 'красноярск', 'саратов', 'тюмень',
    'тольятти', 'ижевск', 'бarnaul', 'уфа', 'ростов',
    'мытищи', 'химки', 'королёв', 'реутов', 'домодедово',
    'ярославль', 'владивосток', 'мурманск', 'архангельск', 'калининград'
]

print("🔍 Сбор городов из VK API...")
for q in queries:
    batch = fetch_cities(q)
    print(f"  → {q}: найдено {len(batch)} городов")
    all_cities.update(batch)

# Убираем дубликаты
print(f"✅ Всего уникальных городов: {len(all_cities)}")

# Сохраняем в файл
with open('cities.json', 'w', encoding='utf-8') as f:
    json.dump(all_cities, f, ensure_ascii=False, indent=2)

print("🎉 Файл cities.json успешно создан!")