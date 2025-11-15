@echo off
REM Скрипт для установки зависимостей на Windows

echo ============================================================
echo Установка зависимостей для парсера trast
echo ============================================================

REM Определяем путь к скрипту
set SCRIPT_DIR=%~dp0
set REQUIREMENTS_FILE=%SCRIPT_DIR%requirements.txt

if not exist "%REQUIREMENTS_FILE%" (
    echo Ошибка: файл %REQUIREMENTS_FILE% не найден!
    exit /b 1
)

REM Обновляем pip
echo.
echo 1. Обновление pip...
python -m pip install --upgrade pip

REM Устанавливаем/обновляем основные зависимости
echo.
echo 2. Установка основных зависимостей...
python -m pip install --upgrade -r "%REQUIREMENTS_FILE%"

REM Специально обновляем undetected-chromedriver
echo.
echo 3. Обновление undetected-chromedriver...
python -m pip install --upgrade --force-reinstall undetected-chromedriver

REM Проверяем установку
echo.
echo 4. Проверка установленных пакетов...
python -m pip list | findstr /i "undetected selenium cloudscraper beautifulsoup"

echo.
echo ============================================================
echo Установка завершена!
echo ============================================================
echo.
echo Если возникли проблемы с версией ChromeDriver:
echo 1. Убедитесь, что Chrome установлен и обновлен
echo 2. Запустите этот скрипт снова для обновления undetected-chromedriver
echo 3. Парсер автоматически попробует использовать Firefox при ошибках Chrome

pause

