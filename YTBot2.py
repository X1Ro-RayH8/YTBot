import os
import asyncio
import re
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from ytmusicapi import YTMusic
import yt_dlp
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка Telegram API (предпочтительно из переменных окружения)
API_ID = os.getenv('API_ID', '23740623')
API_HASH = os.getenv('API_HASH', '79d70c1924d4cbbafcea5b8bcbbd8dc1')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8173348706:AAFvKfdvUxH-9_UhTo2Wo0QMI03pjLVuyAw')

# Инициализация YTMusic API с аутентификацией
# Создаем объект YTMusic без аутентификации (для поиска достаточно)
ytmusic = YTMusic()

# Настройка yt-dlp - Основные настройки без метаданных
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
    # Решение проблемы с cookies
    'cookiesfrombrowser': ('chrome',),  # Пробуем использовать cookies из Chrome по умолчанию
    'skip_download_archive': True,  # Не сохраняем историю загрузок
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],  # Подделываем клиент
            'player_skip': ['configs', 'webpage'],  # Пропускаем некоторые проверки
        }
    },
    # Добавляем обход ограничений YouTube
    'nocheckcertificate': True,
    'geo_bypass': True,
    'ignoreerrors': True
}

# Инициализация клиента Telegram
client = TelegramClient('music_bot', API_ID, API_HASH)

# Проверка наличия директории для загрузок
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Словарь для хранения результатов поиска для каждого пользователя
user_search_results = {}
# Словарь для хранения текущей страницы результатов для каждого пользователя
user_current_page = {}

# Регулярные выражения для распознавания URL
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
    
    # Проверяем, кнопка для выбора песни или для навигации по страницам
    if data.startswith('select_'):
        # Получаем ID песни из данных кнопки
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
    
    # Обработка кнопок навигации по страницам
    elif data == 'page_prev' or data == 'page_next':
        if user_id not in user_search_results or user_id not in user_current_page:
            await event.answer('Сесія пошуку закінчилася. Будь ласка, виконайте новий пошук.')
            return
        
        current_page = user_current_page[user_id]
        
        if data == 'page_prev' and current_page > 0:
            user_current_page[user_id] = current_page - 1
        elif data == 'page_next':
            total_results = len(user_search_results[user_id])
            total_pages = (total_results + 4) // 5  # Округление вверх
            
            if current_page < total_pages - 1:
                user_current_page[user_id] = current_page + 1
        
        # Обновляем сообщение с новой страницей результатов
        original_message = await event.get_message()
        await display_search_page(user_id, original_message)

@client.on(events.NewMessage())
async def message_handler(event):
    if event.text.startswith('/'):
        return  # Пропускаем команды, они обрабатываются в других обработчиках
    
    # Проверяем, URL YouTube или нет
    youtube_url = extract_youtube_url(event.text)
    
    if youtube_url:
        await handle_youtube_url(event, youtube_url)
    else:
        await search_music(event)

def extract_youtube_url(text):
    # Проверяем, содержит ли текст YouTube URL
    youtube_match = re.search(YOUTUBE_REGEX, text)
    if youtube_match:
        return f"https://www.youtube.com/watch?v={youtube_match.group(6)}"
    
    # Проверяем короткий формат youtu.be
    youtube_short_match = re.search(YOUTUBE_SHORT_REGEX, text)
    if youtube_short_match:
        return f"https://www.youtube.com/watch?v={youtube_short_match.group(3)}"
    
    return None

async def handle_youtube_url(event, url):
    status_msg = await event.respond('🔄 Обробляю посилання...')
    
    try:
        # Получаем информацию о видео с обновленными опциями
        with yt_dlp.YoutubeDL({
            'quiet': True,
            'no_warnings': True,
            'extractor_args': ydl_opts_base['extractor_args'],
            'nocheckcertificate': True,
            'geo_bypass': True
        }) as ydl:
            info = ydl.extract_info(url, download=False)
            
        title = info.get('title', 'Невідома пісня')
        artist = info.get('artist', info.get('uploader', 'Невідомий виконавець'))
        
        await status_msg.edit(f'⏱️ Завантажую **{title}** - {artist}...')
        
        # Создаем копию базовых опций и добавляем к ним метаданные
        ydl_opts = ydl_opts_base.copy()
        
        # Добавляем метаданные для конкретного видео
        ydl_opts['postprocessor_args'] = [
            '-id3v2_version', '3',
            '-metadata', f'title={title}',
            '-metadata', f'artist={artist}',
        ]
        
        # Альтернативный подход к загрузке, использующий параметры для обхода ограничений
        try:
            # Загружаем видео
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            await status_msg.edit(f'✅ Завантаження завершено! Надсилаю файл...')
            
            # Отправляем аудиофайл
            await client.send_file(
                event.chat_id,
                filename,
                caption=f'🎵 **{title}** - {artist}',
                voice_note=False,
                supports_streaming=True
            )
            
            # Удаляем файл после отправки
            if os.path.exists(filename):
                os.remove(filename)
            
            # Удаляем возможные остаточные файлы
            for ext in ['.jpg', '.png', '.webp']:
                thumbnail = filename.rsplit('.', 1)[0] + ext
                if os.path.exists(thumbnail):
                    os.remove(thumbnail)
                    
        except Exception as download_error:
            logger.error(f"Помилка при завантаженні: {str(download_error)}")
            await status_msg.edit(f'❌ Сталася помилка при завантаженні відео. Спробуйте інше посилання або використовуйте пошук за назвою пісні.')
        
    except Exception as e:
        logger.error(f"Помилка при обробці URL: {str(e)}")
        await status_msg.edit(f'❌ Сталася помилка при обробці URL. YouTube може вимагати аутентифікацію. Спробуйте скористатись пошуком за назвою пісні замість посилання.')

async def search_music(event):
    search_query = event.text
    chat_id = event.chat_id
    user_id = event.sender_id or event.chat_id
    
    # Сообщение о начале поиска
    status_msg = await event.respond('🔍 Шукаю пісні за вашим запитом...')
    
    try:
        # Поиск на YouTube Music (берем больше результатов для пагинации)
        search_results = ytmusic.search(search_query, filter='songs', limit=20)
        
        if not search_results:
            await status_msg.edit('😕 На жаль, за вашим запитом нічого не знайдено.')
            return
        
        # Сохраняем результаты поиска для этого пользователя
        user_search_results[user_id] = search_results
        # Устанавливаем текущую страницу как 0 (первая страница)
        user_current_page[user_id] = 0
        
        # Отображаем первую страницу результатов
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
    
    # Определяем количество страниц
    total_pages = (len(search_results) + 4) // 5  # Округление вверх
    
    # Вычисляем индексы для текущей страницы
    start_idx = current_page * 5
    end_idx = min(start_idx + 5, len(search_results))
    
    # Заголовок с минимальной информацией
    result_message = f'🎵 Результати пошуку (сторінка {current_page + 1}/{total_pages}):'
    
    # Создаем кнопки для песен с информацией об исполнителе
    buttons = []
    
    for i in range(start_idx, end_idx):
        result = search_results[i]
        title = result['title']
        artists = ', '.join([artist['name'] for artist in result['artists']])
        
        # Номер элемента в списке (с 1)
        item_num = i - start_idx + 1
        
        # Добавляем кнопку для песни с названием и исполнителем
        button_text = f"{item_num}. {title} - {artists}"
        # Ограничиваем длину текста кнопки
        if len(button_text) > 60:
            button_text = button_text[:57] + "..."
            
        buttons.append([Button.inline(button_text, data=f"select_{i}")])
    
    # Добавляем кнопки для навигации
    nav_buttons = []
    
    if current_page > 0:
        nav_buttons.append(Button.inline("⬅️ Назад", data="page_prev"))
    
    if current_page < total_pages - 1:
        nav_buttons.append(Button.inline("Далі ➡️", data="page_next"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Редактируем сообщение, добавляя кнопки
    await message.edit(result_message, buttons=buttons)

async def download_and_send_song(event, song_info, chat_id):
    try:
        video_id = song_info['videoId']
        title = song_info['title']
        artists = ', '.join([artist['name'] for artist in song_info['artists']])
        
        # Отправляем сообщение о начале загрузки
        if hasattr(event, 'edit'):
            download_msg = await event.edit(f'⏱️ Завантажую **{title}** - {artists}...')
        else:
            download_msg = await client.send_message(chat_id, f'⏱️ Завантажую **{title}** - {artists}...')
        
        # URL для загрузки
        url = f"https://music.youtube.com/watch?v={video_id}"
        
        # Создаем копию базовых опций и добавляем к ним метаданные
        ydl_opts = ydl_opts_base.copy()
        
        # Добавляем метаданные для конкретного видео
        ydl_opts['postprocessor_args'] = [
            '-id3v2_version', '3',
            '-metadata', f'title={title}',
            '-metadata', f'artist={artists}',
        ]
        
        try:
            # Загрузка аудио с обложкой
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            await download_msg.edit(f'✅ Завантаження завершено! Надсилаю файл...')
            
            # Отправка аудиофайла
            await client.send_file(
                chat_id,
                filename,
                caption=f'🎵 **{title}** - {artists}',
                voice_note=False,
                supports_streaming=True  # Для потокового воспроизведения в Telegram
            )
            
            # Удаляем файл после отправки
            if os.path.exists(filename):
                os.remove(filename)
            
            # Удаляем возможные остаточные файлы
            for ext in ['.jpg', '.png', '.webp']:
                thumbnail = filename.rsplit('.', 1)[0] + ext
                if os.path.exists(thumbnail):
                    os.remove(thumbnail)
            
        except Exception as download_error:
            logger.error(f"Помилка при завантаженні пісні: {str(download_error)}")
            await download_msg.edit(f'❌ Помилка при завантаженні. YouTube вимагає аутентифікацію. Спробуйте іншу пісню.')
                    
        # Удаляем результаты поиска для пользователя после успешной отправки
        if hasattr(event, 'sender_id') and event.sender_id in user_search_results:
            del user_search_results[event.sender_id]
            
    except Exception as e:
        logger.error(f"Загальна помилка при завантаженні: {str(e)}")
        if hasattr(event, 'edit'):
            await event.edit(f'❌ Сталася помилка при завантаженні пісні. Спробуйте ще раз пізніше або виберіть іншу пісню.')
        else:
            await client.send_message(chat_id, f'❌ Сталася помилка при завантаженні пісні. Спробуйте ще раз пізніше або виберіть іншу пісню.')

async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Бот запущено! Натисніть Ctrl+C для завершення.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
