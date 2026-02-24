@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo   Note Therapy - Установка (Windows)
echo ==========================================
echo.

:: Colors using ANSI escape sequences
set "BLUE=[94m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "NC=[0m"

:check_python
echo Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    python3 --version >nul 2>&1
    if errorlevel 1 (
        echo Python not found. Please install Python 3.10+ from https://python.org
        echo Or: winget install Python.Python.3.10
        pause
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

for /f "tokens=2" %%i in ('%PYTHON% --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python version: %PYTHON_VERSION%
echo.

:: Create output directory
if not exist "output" mkdir output

echo ==========================================
echo   Настройка Hugging Face
echo ==========================================
echo.
echo Для загрузки моделей GigaAM и pyannote требуется токен HuggingFace.
echo.
echo Инструкция:
echo 1. Зарегистрируйтесь на https://huggingface.co
echo 2. Перейдите в Settings -^> Access Tokens
echo 3. Создайте новый токен (Read permissions)
echo 4. При первом использовании pyannote нужно принять условия:
echo    - https://huggingface.co/pyannote/segmentation-3.0
echo    - https://huggingface.co/pyannote/speaker-diarization-3.1
echo.

set /p HF_TOKEN="Введите ваш HuggingFace токен (или нажмите Enter чтобы пропустить): "

if defined HF_TOKEN (
    echo Токен сохранён
) else (
    echo Внимание: Токен не введён - некоторые модели могут не загрузиться
)

echo.
echo ===========================================
echo   Настройка OpenRouter
echo ===========================================
echo.
echo Для анализа сессий требуется OpenRouter API ключ.
echo.
echo Инструкция:
echo 1. Зарегистрируйтесь на https://openrouter.ai
echo 2. Перейдите в Settings -^> API Keys
echo 3. Созайте новый ключ
echo 4. Бесплатные модели: deepseek/deepseek-chat
echo.

set /p OPENROUTER_KEY="Введите ваш OpenRouter API ключ (или нажмите Enter чтобы пропустить): "

if defined OPENROUTER_KEY (
    echo Ключ сохранён
) else (
    echo Внимание: Ключ не введён - анализ сессий будет недоступен
)

echo.
echo ===========================================
echo   Установка зависимостей
echo ===========================================
echo.

:: Upgrade pip
echo Обновление pip...
%PYTHON% -m pip install --upgrade pip >nul 2>&1

:: Install main requirements
if exist "requirements.txt" (
    echo Установка основных зависимостей...
    %PYTHON% -m pip install -r requirements.txt >> install_log.txt 2>&1
    if errorlevel 1 (
        echo Ошибка установки. Попробуйте вручную:
        echo pip install -r requirements.txt
    ) else (
        echo Основные зависимости установлены
    )
)

:: Install backend requirements
if exist "backend\requirements.txt" (
    echo Установка backend зависимостей...
    %PYTHON% -m pip install -r backend\requirements.txt >> install_log.txt 2>&1
    if errorlevel 1 (
        echo Ошибка установки backend
    ) else (
        echo Backend зависимости установлены
    )
)

:: Install frontend dependencies
if exist "frontend\package.json" (
    echo Установка frontend зависимостей...
    cd frontend
    call npm install >> ..\install_log.txt 2>&1
    cd ..
    if errorlevel 1 (
        echo Ошибка установки npm пакетов
    ) else (
        echo Frontend зависимости установлены
    )
)

echo.
echo ===========================================
echo   Создание .env файла
echo ===========================================
echo.

:: Create .env file
(
echo # Local environment
echo # Hugging Face token
if defined HF_TOKEN (
    echo HF_TOKEN=%HF_TOKEN%
) else (
    echo # HF_TOKEN=
)
echo.
echo # OpenRouter API key for therapy session analysis
if defined OPENROUTER_KEY (
    echo OPENROUTER_API_KEY=%OPENROUTER_KEY%
) else (
    echo # OPENROUTER_API_KEY=
)
echo.
echo DIARIZATION_ENGINE=fast
echo DIARIZATION_FIRST=1
echo DIARIZATION_FAST_VAD_THRESHOLD=0.5
echo DIARIZATION_FAST_MIN_SPEECH_MS=250
echo DIARIZATION_FAST_MIN_SILENCE_MS=100
echo DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH=0.4
) > .env

echo .env файл создан

echo.
echo ===========================================
echo   Загрузка моделей
echo ===========================================
echo.

echo Загрузка моделей (может занять несколько минут)...
echo.

%PYTHON% -c "
import os
hf_token = os.getenv('HF_TOKEN', '').strip()
if not hf_token:
    hf_token = None

try:
    from huggingface_hub import hf_hub_download, snapshot_download
    
    print('Downloading Whisper tiny...')
    try:
        from faster_whisper import WhisperModel
        WhisperModel('tiny', device='cpu', compute_type='int8')
        print('  Whisper tiny: OK')
    except Exception as e:
        print(f'  Whisper tiny: {e}')
    
    print('Downloading ECAPA model...')
    try:
        snapshot_download(
            repo_id='speechbrain/spkrec-ecapa-voxceleb',
            token=hf_token
        )
        print('  ECAPA: OK')
    except Exception as e:
        print(f'  ECAPA: {e}')
        
    print('Models download complete!')
    
except ImportError as e:
    print(f'huggingface_hub not available: {e}')
    print('Models will be downloaded on first run')
except Exception as e:
    print(f'Error: {e}')
"

echo.
echo ===========================================
echo   Проверка установки
echo ===========================================
echo.

%PYTHON% -c "
import sys
errors = []

try:
    import whisperx
except Exception as e:
    errors.append(f'whisperx: {e}')

try:
    import pyannote
except Exception as e:
    errors.append(f'pyannote: {e}')

try:
    import faster_whisper
except Exception as e:
    errors.append(f'faster_whisper: {e}')

try:
    import speechbrain
except Exception as e:
    errors.append(f'speechbrain: {e}')

if errors:
    print('Errors found:')
    for e in errors:
        print(f'  - {e}')
else:
    print('All imports OK')
"

if errorlevel 1 (
    echo.
    echo Внимание: Некоторые импорты не работают
) else (
    echo.
    echo Установка завершена!
)

echo.
echo ===========================================
echo   Запуск
echo ===========================================
echo.
echo Backend:
echo   cd backend ^&^& uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
echo.
echo Frontend:
echo   cd frontend ^&^& npm run dev
echo.
echo ===========================================

pause
