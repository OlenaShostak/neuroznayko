@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
:menu
echo.
echo  НейроЗнайко - Готовність до школи: озвучка
echo  1 - перевірка наголосів (українська й російська)
echo  2 - озвучити все, чого ще немає
echo  3 - переозвучити фрази з одним словом (після правки pronunciation.json)
echo  4 - варіанти вимови проблемних слів (variants_uk.json, variants_ru.json)
echo  0 - вихід
set /p CH=Ваш вибір: 
if "%CH%"=="1" (
  %PY% azure_tts_gotovnist.py check uk
  %PY% azure_tts_gotovnist.py check ru
  start "" "audio\_check"
)
if "%CH%"=="4" (
  if exist variants_uk.json %PY% azure_tts_gotovnist.py variants uk
  if exist variants_ru.json %PY% azure_tts_gotovnist.py variants ru
  start "" "audio\_check"
)
if "%CH%"=="2" %PY% azure_tts_gotovnist.py
if "%CH%"=="3" (
  set /p W=Слово: 
  call %PY% azure_tts_gotovnist.py refresh "%%W%%"
)
if "%CH%"=="0" exit /b
goto menu
