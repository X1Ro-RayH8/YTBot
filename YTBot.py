import os
import asyncio
import re
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from ytmusicapi import YTMusic
import yt_dlp
import logging
from dotenv import load_dotenv

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Налаштування Telegram API
API_ID = '23740623'  # Замініть на ваш API_ID (як рядок)
API_HASH = '79d70c1924d4cbbafcea5b8bcbbd8dc1'  # Замініть на ваш API_HASH
BOT_TOKEN = '8173348706:AAFvKfdvUxH-9_UhTo2Wo0QMI03pjLVuyAw'  # Замініть на ваш BOT_TOKEN

# Ініціалізація YTMusic API
ytmusic = YTMusic()

# Налаштування yt-dlp - Основні налаштування без метаданих
ydl_opts_base = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'writethumbnail': True,
    'embedthumbnail': True,
    'cookiefile': 'cookies.txt'
}

# Ініціалізація клієнта Telegram
client = TelegramClient('music_bot', API_ID, API_HASH)

# Перевірка наявності директорії для завантажень
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Словник для зберігання результатів пошуку для кожного користувача
user_search_results = {}
# Словник для зберігання поточної сторінки результатів для кожного користувача
user_current_page = {}

# Регулярні вирази для розпізнавання URL
YOUTUBE_REGEX = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie|music\.youtube)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
YOUTUBE_SHORT_REGEX = r'(https?://)?(www\.)?youtu\.be/([^&=%\?]{11})'

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await event.respond('Привіт! Я бот для пошуку та завантаження музики з YouTube Music. Просто напишіть назву пісні або частину тексту, або надішліть посилання на YouTube, і я допоможу вам завантажити аудіо.')

@client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    help_text = """
🎵 Як користуватися ботом:
1. Надішліть мені назву пісні, частину тексту або посилання на YouTube
2. Я знайду відповідні пісні на YouTube Music
3. Виберіть пісню з кнопок у повідомленні, і я надішлю вам аудіофайл

Команди:
/start - Почати роботу з ботом
/help - Показати цю довідку
"""
    await event.respond(help_text)

@client.on(events.CallbackQuery(pattern=r'select_|page_'))
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')
    
    # Перевіряємо, чи це кнопка для вибору пісні чи для навігації по сторінках
    if data.startswith('select_'):
        # Отримуємо ID пісні з даних кнопки
        index = int(data.split('_')[1])
        
        if user_id not in user_search_results:
            await event.answer('Сесія пошуку закінчилася. Будь ласка, виконайте новий пошук.')
            return
        
        search_results = user_search_results[user_id]
        
        if 0 <= index < len(search_results):
            await event.answer('Починаю завантаження...')
            await download_and_send_song(event, search_results[index], event.chat_id)
        else:
            await event.answer('Невірний вибір. Спробуйте ще раз.')
    
    # Обробка кнопок навігації по сторінках
    elif data == 'page_prev' or data == 'page_next':
        if user_id not in user_search_results or user_id not in user_current_page:
            await event.answer('Сесія пошуку закінчилася. Будь ласка, виконайте новий пошук.')
            return
        
        current_page = user_current_page[user_id]
        
        if data == 'page_prev' and current_page > 0:
            user_current_page[user_id] = current_page - 1
        elif data == 'page_next':
            total_results = len(user_search_results[user_id])
            total_pages = (total_results + 4) // 5  # Округлення вгору
            
            if current_page < total_pages - 1:
                user_current_page[user_id] = current_page + 1
        
        # Оновлюємо повідомлення з новою сторінкою результатів
        # Отримуємо оригінальне повідомлення через event.query.msg
        original_message = await event.get_message()
        await display_search_page(user_id, original_message)

@client.on(events.NewMessage())
async def message_handler(event):
    if event.text.startswith('/'):
        return  # Пропускаємо команди, вони обробляються в інших обробниках
    
    # Перевіряємо, чи це URL YouTube
    youtube_url = extract_youtube_url(event.text)
    
    if youtube_url:
        await handle_youtube_url(event, youtube_url)
    else:
        await search_music(event)

def extract_youtube_url(text):
    # Перевіряємо, чи текст містить YouTube URL
    youtube_match = re.search(YOUTUBE_REGEX, text)
    if youtube_match:
        return f"https://www.youtube.com/watch?v={youtube_match.group(6)}"
    
    # Перевіряємо короткий формат youtu.be
    youtube_short_match = re.search(YOUTUBE_SHORT_REGEX, text)
    if youtube_short_match:
        return f"https://www.youtube.com/watch?v={youtube_short_match.group(3)}"
    
    return None

async def handle_youtube_url(event, url):
    status_msg = await event.respond('🔄 Обробляю посилання...')
    
    try:
        # Отримуємо інформацію про відео
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
        title = info.get('title', 'Невідома пісня')
        artist = info.get('artist', info.get('uploader', 'Невідомий виконавець'))
        
        await status_msg.edit(f'⏱️ Завантажую **{title}** - {artist}...')
        
        # Створюємо копію базових опцій і додаємо до них метадані
        ydl_opts = ydl_opts_base.copy()
        
        # Додаємо метадані для конкретного відео
        ydl_opts['postprocessor_args'] = [
            '-id3v2_version', '3',
            '-metadata', f'title={title}',
            '-metadata', f'artist={artist}',
        ]
        
        # Завантажуємо відео
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        
        await status_msg.edit(f'✅ Завантаження завершено! Надсилаю файл...')
        
        # Відправляємо аудіофайл
        await client.send_file(
            event.chat_id,
            filename,
            caption=f'🎵 **{title}** - {artist}',
            voice_note=False,
            supports_streaming=True
        )
        
        # Видаляємо файл після відправки
        os.remove(filename)
        
        # Видаляємо можливі залишкові файли
        for ext in ['.jpg', '.png', '.webp']:
            thumbnail = filename.rsplit('.', 1)[0] + ext
            if os.path.exists(thumbnail):
                os.remove(thumbnail)
        
    except Exception as e:
        logger.error(f"Помилка при обробці URL: {str(e)}")
        await status_msg.edit(f'❌ Сталася помилка при завантаженні відео. Спробуйте інше посилання.')

async def search_music(event):
    search_query = event.text
    chat_id = event.chat_id
    user_id = event.sender_id or event.chat_id
    
    # Повідомлення про початок пошуку
    status_msg = await event.respond('🔍 Шукаю пісні за вашим запитом...')
    
    try:
        # Пошук на YouTube Music (беремо більше результатів для пагінації)
        search_results = ytmusic.search(search_query, filter='songs', limit=20)
        
        if not search_results:
            await status_msg.edit('😕 На жаль, за вашим запитом нічого не знайдено.')
            return
        
        # Зберігаємо результати пошуку для цього користувача
        user_search_results[user_id] = search_results
        # Встановлюємо поточну сторінку як 0 (перша сторінка)
        user_current_page[user_id] = 0
        
        # Відображаємо першу сторінку результатів
        await display_search_page(user_id, status_msg)
        
    except Exception as e:
        logger.error(f"Помилка: {str(e)}")
        await status_msg.edit(f'❌ Сталася помилка при обробці запиту. Спробуйте ще раз пізніше.')

async def display_search_page(user_id, message):
    if user_id not in user_search_results or user_id not in user_current_page:
        await message.edit('❌ Сесія пошуку закінчилася. Будь ласка, виконайте новий пошук.')
        return
    
    search_results = user_search_results[user_id]
    current_page = user_current_page[user_id]
    
    # Визначаємо кількість сторінок
    total_pages = (len(search_results) + 4) // 5  # Округлення вгору
    
    # Вираховуємо індекси для поточної сторінки
    start_idx = current_page * 5
    end_idx = min(start_idx + 5, len(search_results))
    
    # Заголовок з мінімальною інформацією
    result_message = f'🎵 Результати пошуку (сторінка {current_page + 1}/{total_pages}):'
    
    # Створюємо кнопки для пісень з інформацією про виконавця
    buttons = []
    
    for i in range(start_idx, end_idx):
        result = search_results[i]
        title = result['title']
        artists = ', '.join([artist['name'] for artist in result['artists']])
        
        # Номер елемента в списку (з 1)
        item_num = i - start_idx + 1
        
        # Додаємо кнопку для пісні з назвою та виконавцем
        button_text = f"{item_num}. {title} - {artists}"
        # Обмежуємо довжину тексту кнопки
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
            
        buttons.append([Button.inline(button_text, data=f"select_{i}")])
    
    # Додаємо кнопки для навігації
    nav_buttons = []
    
    if current_page > 0:
        nav_buttons.append(Button.inline("⬅️ Назад", data="page_prev"))
    
    if current_page < total_pages - 1:
        nav_buttons.append(Button.inline("Далі ➡️", data="page_next"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Редагуємо повідомлення, додаючи кнопки
    await message.edit(result_message, buttons=buttons)

async def download_and_send_song(event, song_info, chat_id):
    try:
        video_id = song_info['videoId']
        title = song_info['title']
        artists = ', '.join([artist['name'] for artist in song_info['artists']])
        
        # Відправляємо повідомлення про початок завантаження
        if hasattr(event, 'edit'):
            download_msg = await event.edit(f'⏱️ Завантажую **{title}** - {artists}...')
        else:
            download_msg = await client.send_message(chat_id, f'⏱️ Завантажую **{title}** - {artists}...')
        
        # URL для завантаження
        url = f"https://music.youtube.com/watch?v={video_id}"
        
        # Створюємо копію базових опцій і додаємо до них метадані
        ydl_opts = ydl_opts_base.copy()
        
        # Додаємо метадані для конкретного відео
        ydl_opts['postprocessor_args'] = [
            '-id3v2_version', '3',
            '-metadata', f'title={title}',
            '-metadata', f'artist={artists}',
        ]
        
        # Завантаження аудіо з обкладинкою
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
        
        await download_msg.edit(f'✅ Завантаження завершено! Надсилаю файл...')
        
        # Відправка аудіофайлу
        await client.send_file(
            chat_id,
            filename,
            caption=f'🎵 **{title}** - {artists}',
            voice_note=False,
            supports_streaming=True  # Для потокового відтворення в Telegram
        )
        
        # Видаляємо файл після відправки
        os.remove(filename)
        
        # Видаляємо можливі залишкові файли
        for ext in ['.jpg', '.png', '.webp']:
            thumbnail = filename.rsplit('.', 1)[0] + ext
            if os.path.exists(thumbnail):
                os.remove(thumbnail)
                
        # Видаляємо результати пошуку для користувача після успішного відправлення
        if event.sender_id in user_search_results:
            del user_search_results[event.sender_id]
            
    except Exception as e:
        logger.error(f"Помилка при завантаженні: {str(e)}")
        if hasattr(event, 'edit'):
            await event.edit(f'❌ Сталася помилка при завантаженні пісні. Спробуйте ще раз пізніше.')
        else:
            await client.send_message(chat_id, f'❌ Сталася помилка при завантаженні пісні. Спробуйте ще раз пізніше.')

async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Бот запущено! Натисніть Ctrl+C для завершення.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
