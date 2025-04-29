@echo off
:: Автор: Топовий скрипт для відновлення Python PATH
:: Дата: 2025

setlocal

echo ---------------------------------------
echo 🔧 Відновлення змінної PATH для Python
echo ---------------------------------------

:: Введи повний шлях до твоєї теки Python
set PYTHON_PATH=D:\Python

:: Шляхи, які будемо додавати
set PYTHON_SCRIPTS=%PYTHON_PATH%\Scripts
set PYTHON_EXE=%PYTHON_PATH%

:: Додаємо до системного PATH (обережно, не стираючи)
setx PATH "%PYTHON_SCRIPTS%;%PYTHON_EXE%;%PATH%"

echo ---------------------------------------
echo ✅ PATH успішно оновлений!
echo 📢 Перезапусти термінал після виконання!
echo ---------------------------------------

pause
exit
