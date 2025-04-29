import os
import zipfile
import urllib.request
import shutil
import subprocess
import winreg

def download_ffmpeg(download_url, output_path):
    print("⬇️ Завантажую ffmpeg...")
    urllib.request.urlretrieve(download_url, output_path)
    print("✅ Завантажено!")

def unzip_ffmpeg(zip_path, extract_path):
    print("📦 Розпаковую ffmpeg...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)
    print("✅ Розпаковано!")

def find_ffmpeg_bin(extracted_folder):
    for root, dirs, files in os.walk(extracted_folder):
        if 'ffmpeg.exe' in files:
            return root
    return None

def add_to_path(ffmpeg_bin_path):
    print("➕ Додаю ffmpeg у PATH...")
    with winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE) as reg:
        with winreg.OpenKey(reg, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                path_value, regtype = winreg.QueryValueEx(key, "Path")
                if ffmpeg_bin_path not in path_value:
                    new_path = path_value + ";" + ffmpeg_bin_path
                    winreg.SetValueEx(key, "Path", 0, regtype, new_path)
                    print("✅ PATH успішно оновлено!")
                else:
                    print("ℹ️ ffmpeg вже є в PATH.")
            except FileNotFoundError:
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ffmpeg_bin_path)
                print("✅ PATH створено з ffmpeg.")
    # Сповіщення системи, що PATH оновлений
    subprocess.run(["setx", "Path", ffmpeg_bin_path])

def main():
    download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = "ffmpeg.zip"
    extract_folder = "C:\\ffmpeg_temp"

    # Крок 1: Завантажити
    download_ffmpeg(download_url, zip_path)

    # Крок 2: Розпакувати
    unzip_ffmpeg(zip_path, extract_folder)

    # Крок 3: Знайти bin
    ffmpeg_bin_path = find_ffmpeg_bin(extract_folder)
    if not ffmpeg_bin_path:
        print("🚫 Помилка: ffmpeg.exe не знайдено після розпаковки!")
        return

    # Крок 4: Перемістити bin у зручне місце
    target_folder = "C:\\ffmpeg"
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    shutil.move(ffmpeg_bin_path, target_folder)
    final_bin_path = os.path.join(target_folder, "bin")

    # Крок 5: Додати в PATH
    add_to_path(final_bin_path)

    # Крок 6: Очистити тимчасові файли
    os.remove(zip_path)
    shutil.rmtree(extract_folder, ignore_errors=True)

    print("\n🎉 УСПІШНО! Тепер перезапусти комп'ютер або перезайди в сесію, щоб оновити PATH.")

if __name__ == "__main__":
    main()
