# bot.py

from dotenv import load_dotenv
import os
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.utils import get_random_id
import json
import psycopg2
from psycopg2.extras import RealDictCursor

# === Загрузка переменных окружения ===
load_dotenv()

# === Загрузка кэша городов ===
CITIES = {}
if os.path.exists('cities.json'):
    with open('cities.json', 'r', encoding='utf-8') as f:
        CITIES = json.load(f)
else:
    print("⚠️ Файл cities.json не найден. Используйте get_cities.py для его создания.")

# === Настройки VK ===
VK_TOKEN = os.getenv("VK_TOKEN")
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.131")

if not VK_TOKEN:
    raise ValueError("Требуется VK_TOKEN в файле .env")

# === Настройки PostgreSQL ===
DB_CONFIG = {
    'host': os.getenv("DB_HOST", "localhost"),
    'port': int(os.getenv("DB_PORT", 5432)),
    'dbname': os.getenv("DB_NAME", "vk_bot"),
    'user': os.getenv("DB_USER", "postgres"),
    'password': os.getenv("DB_PASSWORD"),
}

# === Инициализация VK ===
vk_session = vk_api.VkApi(token=VK_TOKEN, api_version=VK_API_VERSION)
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)


# === Работа с PostgreSQL ===
def get_db_connection():
    """Создаёт новое подключение к БД"""
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    """Инициализация таблиц при запуске"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bot_users (
            vk_id BIGINT PRIMARY KEY,
            age INT,
            sex INT,
            city_id INT,
            city_name TEXT,
            stage TEXT DEFAULT 'start',
            search_offset INT DEFAULT 0,
            last_shown_id BIGINT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            vk_id BIGINT,
            favorite_id BIGINT,
            name TEXT,
            link TEXT,
            PRIMARY KEY (vk_id, favorite_id)
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()


def get_user_stage(vk_id):
    """Получить данные пользователя"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM bot_users WHERE vk_id = %s", (vk_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def update_user(vk_id, **kwargs):
    """Обновить или создать запись пользователя"""
    conn = get_db_connection()
    cur = conn.cursor()
    fields = ", ".join([f"{k} = %s" for k in kwargs])
    values = list(kwargs.values())
    query = f"""
        INSERT INTO bot_users (vk_id, {', '.join(kwargs.keys())})
        VALUES ({vk_id}, {', '.join(['%s'] * len(values))})
        ON CONFLICT (vk_id) DO UPDATE SET {fields}
    """
    cur.execute(query, values + values)
    conn.commit()
    cur.close()
    conn.close()


def update_last_shown(vk_id, shown_id):
    """Обновить ID последнего показанного пользователя"""
    update_user(vk_id, last_shown_id=shown_id)


def increment_search_offset(vk_id):
    """Увеличить смещение поиска"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE bot_users SET search_offset = search_offset + 1 WHERE vk_id = %s", (vk_id,))
    conn.commit()
    cur.close()
    conn.close()


def add_to_favorites(vk_id, fav_id, name, link):
    """Добавить в избранное"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO favorites (vk_id, favorite_id, name, link)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    ''', (vk_id, fav_id, name, link))
    conn.commit()
    cur.close()
    conn.close()


def get_favorites(vk_id):
    """Получить список избранных"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT favorite_id, name, link FROM favorites WHERE vk_id = %s", (vk_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# === Работа с VK API ===
def get_popular_photos(user_id, count=3):
    """Получить 3 самых лайкаемых фото"""
    try:
        photos = vk.photos.getAll(owner_id=user_id, count=30, extended=1)
        sorted_photos = sorted(photos['items'], key=lambda x: x['likes']['count'], reverse=True)
        return [f"photo{x['owner_id']}_{x['id']}" for x in sorted_photos[:count]]
    except Exception as e:
        print(f"Ошибка загрузки фото: {e}")
        return []


def search_user(age, sex, city, offset=0):
    """Поиск пользователя по критериям"""
    try:
        response = vk.users.search(
            age_from=age, age_to=age,
            sex=sex,
            city=city,
            has_photo=1,
            count=1,
            offset=offset,
            fields='photo_id'
        )
        return response['items'][0] if response['items'] else None
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        return None


def show_profile(event, vk_id):
    """Показать следующего пользователя"""
    data = get_user_stage(vk_id)
    profile = search_user(data['age'], data['sex'], data['city_id'], data['search_offset'])

    if not profile:
        send_message(vk_id, "Анкеты закончились.")
        return

    # Сохраняем ID показанного пользователя
    update_last_shown(vk_id, profile['id'])
    increment_search_offset(vk_id)

    name = f"{profile['first_name']} {profile['last_name']}"
    link = f"https://vk.com/id{profile['id']}"
    message = f"{name}\n{link}"

    attachments = get_popular_photos(profile['id'])
    send_message(vk_id, message, attachment=",".join(attachments), keyboard=get_search_keyboard())


# === Клавиатуры ===
def get_search_keyboard():
    """Клавиатура 'Далее' и 'В избранное'"""
    keyboard = {
        "inline": True,
        "buttons": [
            [
                {
                    "action": {"type": "text", "label": "❤️ В избранное", "payload": json.dumps({"cmd": "fav"})},
                    "color": "secondary"
                },
                {
                    "action": {"type": "text", "label": "Далее ➡️", "payload": json.dumps({"cmd": "next"})},
                    "color": "primary"
                }
            ]
        ]
    }
    return json.dumps(keyboard)


def get_start_keyboard():
    """Начальная клавиатура"""
    keyboard = {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "Начать поиск"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "Показать избранное"}, "color": "secondary"}]
        ]
    }
    return json.dumps(keyboard)


# === Отправка сообщений ===
def send_message(user_id, message, attachment=None, keyboard=None):
    """Отправка сообщения через VK API"""
    vk.messages.send(
        user_id=user_id,
        message=message,
        attachment=attachment,
        keyboard=keyboard,
        random_id=get_random_id()
    )


# === Основной цикл ===
def main():
    init_db()
    print("✅ Бот запущен. Ожидание сообщений...")

    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            msg = event.text.lower().strip()
            vk_id = event.user_id

            data = get_user_stage(vk_id)

            if not data:
                update_user(vk_id, stage='start')
                data = {'stage': 'start'}
                send_message(vk_id, "Привет! Я бот для знакомств. Готов начать?", keyboard=get_start_keyboard())
                continue

            # === Логика диалога ===

            if msg == "начать поиск":
                update_user(vk_id, stage='age')
                send_message(vk_id, "Введите ваш возраст (14–100):")

            elif data['stage'] == 'age':
                if msg.isdigit() and 14 <= int(msg) <= 100:
                    update_user(vk_id, age=int(msg), stage='sex')
                    send_message(vk_id, "Укажите пол (мужской/женский):")
                else:
                    send_message(vk_id, "Введите корректный возраст (например: 25):")

            elif data['stage'] == 'sex':
                sex_map = {'м': 2, 'мужской': 2, 'ж': 1, 'женский': 1}
                if msg in sex_map:
                    update_user(vk_id, sex=sex_map[msg], stage='city')
                    send_message(vk_id, "Введите город:")
                else:
                    send_message(vk_id, "Выберите: мужской или женский.")

            elif data['stage'] == 'city':
                query = msg.lower().strip()
                found = None
                for name, cid in CITIES.items():
                    if query in name or name in query:
                        found = (name.title(), cid)
                        break

                if found:
                    city_name, city_id = found
                    update_user(vk_id, city_id=city_id, city_name=city_name, stage='searching', search_offset=0)
                    send_message(vk_id, f"Город: {city_name}. Ищем…")
                    show_profile(event, vk_id)
                else:
                    send_message(vk_id, "Город не найден. Попробуйте уточнить название (например: Москва, Мытищи).")

            elif data['stage'] == 'searching':
                if msg in ("далее", "next", "следующий"):
                    show_profile(event, vk_id)
                elif msg in ("в избранное", "❤️ в избранное"):
                    if data.get('last_shown_id'):
                        try:
                            user = vk.users.get(user_ids=data['last_shown_id'])[0]
                            name = f"{user['first_name']} {user['last_name']}"
                            link = f"https://vk.com/id{user['id']}"
                            add_to_favorites(vk_id, user['id'], name, link)
                            send_message(vk_id, f"✅ {name} добавлен(а) в избранное!")
                        except Exception as e:
                            send_message(vk_id, "Не удалось получить данные пользователя.")
                    else:
                        send_message(vk_id, "Сначала посмотрите анкету.")

            elif msg == "показать избранное":
                favs = get_favorites(vk_id)
                if not favs:
                    send_message(vk_id, "❤️ Ваш список избранных пуст.")
                else:
                    for fav_id, name, link in favs:
                        attachments = get_popular_photos(fav_id)
                        send_message(vk_id, f"{name}\n{link}", attachment=",".join(attachments))
                send_message(vk_id, "Это всё избранное.", keyboard=get_start_keyboard())

            else:
                send_message(vk_id, "Неизвестная команда.", keyboard=get_start_keyboard())


if __name__ == '__main__':
    main()