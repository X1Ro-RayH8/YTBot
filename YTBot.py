import os
import asyncio
from telethon import TelegramClient, events
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

# Налаштування yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': 'downloads/%(title)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
}

# Ініціалізація клієнта Telegram
client = TelegramClient('music_bot', API_ID, API_HASH)

# Перевірка наявності директорії для завантажень
if not os.path.exists('downloads'):
    os.makedirs('downloads')

# Словник для зберігання результатів пошуку для кожного користувача
user_search_results = {}

@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await event.respond('Привіт! Я бот для пошуку та завантаження музики з YouTube Music. Просто напишіть назву пісні або частину тексту, і я спробую знайти її для вас.')

@client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    help_text = """
🎵 Як користуватися ботом:
1. Просто надішліть мені назву пісні або частину тексту
2. Я знайду відповідні пісні на YouTube Music
3. Виберіть пісню зі списку, і я надішлю вам аудіофайл

Команди:
/start - Почати роботу з ботом
/help - Показати цю довідку
"""
    await event.respond(help_text)

@client.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/')))
async def message_handler(event):
    # Перевіряємо, чи це цифра (відповідь на пошук) або пошуковий запит
    if event.text.isdigit():
        await handle_selection(event)
    else:
        await search_music(event)

async def search_music(event):
    search_query = event.text
    chat_id = event.chat_id
    
    # Безпечно отримуємо ID користувача
    if event.sender_id:
        user_id = event.sender_id
    else:
        # Якщо ID відправника недоступний, використовуємо ID чату
        user_id = chat_id
    
    # Повідомлення про початок пошуку
    status_msg = await event.respond('🔍 Шукаю пісні за вашим запитом...')
    
    try:
        # Пошук на YouTube Music
        search_results = ytmusic.search(search_query, filter='songs', limit=5)
        
        if not search_results:
            await status_msg.edit('😕 На жаль, за вашим запитом нічого не знайдено.')
            return
        
        # Формуємо список результатів
        result_message = '🎵 Результати пошуку:\n\n'
        for i, result in enumerate(search_results, 1):
            title = result['title']
            artists = ', '.join([artist['name'] for artist in result['artists']])
            result_message += f"{i}. **{title}** - {artists}\n"
        
        result_message += '\nВідправте номер пісні, яку хочете завантажити.'
        
        await status_msg.edit(result_message)
        
        # Зберігаємо результати пошуку для цього користувача
        user_search_results[user_id] = search_results
        
    except Exception as e:
        logger.error(f"Помилка: {str(e)}")
        await status_msg.edit(f'❌ Сталася помилка при обробці запиту. Спробуйте ще раз пізніше.')

async def handle_selection(event):
    user_id = event.sender_id or event.chat_id
    chat_id = event.chat_id
    selected_index = int(event.text) - 1
    
    # Перевіряємо, чи є результати пошуку для цього користувача
    if user_id not in user_search_results:
        await event.respond('Спочатку виконайте пошук пісні.')
        return
    
    search_results = user_search_results[user_id]
    
    if 0 <= selected_index < len(search_results):
        try:
            selected_song = search_results[selected_index]
            video_id = selected_song['videoId']
            title = selected_song['title']
            artists = ', '.join([artist['name'] for artist in selected_song['artists']])
            
            download_msg = await event.respond(f'⏱️ Завантажую **{title}** - {artists}...')
            
            # URL для завантаження
            url = f"https://music.youtube.com/watch?v={video_id}"
            
            # Завантаження аудіо
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            await download_msg.edit(f'✅ Завантаження завершено! Надсилаю файл...')
            
            # Відправка аудіофайлу
            await client.send_file(
                chat_id,
                filename,
                caption=f'🎵 **{title}** - {artists}',
                voice_note=False
            )
            
            # Видалення файлу після відправки
            os.remove(filename)
            
            # Очищаємо результати пошуку для цього користувача
            del user_search_results[user_id]
            
        except Exception as e:
            logger.error(f"Помилка: {str(e)}")
            await event.respond(f'❌ Сталася помилка при завантаженні пісні. Спробуйте ще раз пізніше.')
    else:
        await event.respond('❌ Невірний номер. Будь ласка, виберіть номер зі списку.')

async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("Бот запущено! Натисніть Ctrl+C для завершення.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())