@echo off
chcp 65001 >nul
cd /d "%~dp0"
set AZURE_SPEECH_REGION=swedencentral
echo.
echo Папка: %cd%
echo Вставте KEY 1 з Azure ОДИН раз (правий клік) і натисніть Enter:
set /p AZURE_SPEECH_KEY=
echo.
echo Готово. Тепер можна вводити команди, напр.: python azure_tts.py refresh "слово"
echo.
cmd /k
