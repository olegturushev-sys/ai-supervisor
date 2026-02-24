# Note Therapy - Installation Script for Windows
# Run with: .\install.ps1

$ErrorActionPreference = "Continue"

function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Note Therapy - Установка (Windows)" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

# Check Python
Write-Info "Проверка Python..."
$pythonCmd = $null
try {
    $null = & python --version 2>$null
    if ($LASTEXITCODE -eq 0) { $pythonCmd = "python" }
} catch {}
try {
    $null = & python3 --version 2>$null
    if ($LASTEXITCODE -eq 0) { $pythonCmd = "python3" }
} catch {}

if (-not $pythonCmd) {
    Write-Err "Python не найден. Установите Python 3.10+"
    Write-Host "  winget install Python.Python.3.10"
    Write-Host "  или: https://python.org"
    exit 1
}

$pythonVersion = & $pythonCmd --version 2>&1
Write-Success "Python: $pythonVersion"

# Create output directory
if (-not (Test-Path "output")) { New-Item -ItemType Directory -Path "output" | Out-Null }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Настройка Hugging Face" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Для загрузки моделей GigaAM и pyannote требуется токен HuggingFace." -ForegroundColor Yellow
Write-Host ""
Write-Host "Инструкция:"
Write-Host "1. Зарегистрируйтесь на https://huggingface.co"
Write-Host "2. Перейдите в Settings -> Access Tokens"
Write-Host "3. Создайте новый токен (Read permissions)"
Write-Host "4. Примите условия использования моделей:"
Write-Host "   - https://huggingface.co/pyannote/segmentation-3.0"
Write-Host "   - https://huggingface.co/pyannote/speaker-diarization-3.1"
Write-Host ""

$HF_TOKEN = Read-Host "Введите HuggingFace токен (или Enter чтобы пропустить)"
if ($HF_TOKEN) {
    Write-Success "Токен сохранён"
} else {
    Write-Warn "Токен не введён - некоторые модели могут не загрузиться"
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Настройка OpenRouter" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Для анализа сессий требуется OpenRouter API ключ." -ForegroundColor Yellow
Write-Host ""
Write-Host "Инструкция:"
Write-Host "1. Зарегистрируйтесь на https://openrouter.ai"
Write-Host "2. Перейдите в Settings -> API Keys"
Write-Host "3. Созайте новый ключ"
Write-Host "4. Бесплатные модели: deepseek/deepseek-chat"
Write-Host ""

$OPENROUTER_KEY = Read-Host "Введите OpenRouter API ключ (или Enter чтобы пропустить)"
if ($OPENROUTER_KEY) {
    Write-Success "Ключ сохранён"
} else {
    Write-Warn "Ключ не введён - анализ сессий будет недоступен"
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Установка зависимостей" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

# Upgrade pip
Write-Info "Обновление pip..."
& $pythonCmd -m pip install --upgrade pip --quiet 2>$null

# Install main requirements
if (Test-Path "requirements.txt") {
    Write-Info "Установка основных зависимостей..."
    & $pythonCmd -m pip install -r requirements.txt --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Основные зависимости установлены"
    } else {
        Write-Warn "Ошибка установки. Попробуйте вручную: pip install -r requirements.txt"
    }
}

# Install backend requirements
if (Test-Path "backend\requirements.txt") {
    Write-Info "Установка backend зависимостей..."
    & $pythonCmd -m pip install -r backend\requirements.txt --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Backend зависимости установлены"
    } else {
        Write-Warn "Ошибка установки backend"
    }
}

# Install frontend dependencies
if (Test-Path "frontend\package.json") {
    Write-Info "Установка frontend зависимостей..."
    Set-Location frontend
    npm install --silent 2>$null
    Set-Location ..
    if ($LASTEXITCODE -eq 0) {
        Write-Success "Frontend зависимости установлены"
    } else {
        Write-Warn "Ошибка установки npm пакетов"
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Создание .env файла" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

$envContent = @"
# Local environment (DO NOT commit secrets).

# Hugging Face token
$(if ($HF_TOKEN) { "HF_TOKEN=$HF_TOKEN" } else { "# HF_TOKEN=" })

# OpenRouter API key for therapy session analysis
$(if ($OPENROUTER_KEY) { "OPENROUTER_API_KEY=$OPENROUTER_KEY" } else { "# OPENROUTER_API_KEY=" })

# Diarization settings
DIARIZATION_ENGINE=fast
DIARIZATION_FIRST=1
DIARIZATION_FAST_VAD_THRESHOLD=0.5
DIARIZATION_FAST_MIN_SPEECH_MS=250
DIARIZATION_FAST_MIN_SILENCE_MS=100
DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH=0.4
"@

$envContent | Out-File -FilePath ".env" -Encoding UTF8
Write-Success ".env файл создан"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Загрузка моделей" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

Write-Info "Загрузка моделей (может занять несколько минут)..."
Write-Host ""

$env:HF_TOKEN = $HF_TOKEN

& $pythonCmd -c @"
import os
import sys

hf_token = os.getenv('HF_TOKEN', '').strip()
if not hf_token:
    hf_token = None

try:
    from huggingface_hub import snapshot_download
    
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
except Exception as e:
    print(f'Error: {e}')
"@

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Проверка установки" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""

Write-Info "Проверка импортов..."
$importErrors = @()

try { Import-Module whisperx -ErrorAction Stop } catch { $importErrors += "whisperx" }
try { Import-Module pyannote -ErrorAction Stop } catch { $importErrors += "pyannote" }
try { Import-Module faster_whisper -ErrorAction Stop } catch { $importErrors += "faster_whisper" }
try { Import-Module speechbrain -ErrorAction Stop } catch { $importErrors += "speechbrain" }

& $pythonCmd -c @"
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
    sys.exit(1)
else:
    print('All imports OK')
"@

if ($LASTEXITCODE -eq 0) {
    Write-Success "Установка завершена!"
} else {
    Write-Warn "Некоторые импорты не работают"
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host "  Запуск" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Backend:" -ForegroundColor Cyan
Write-Host "  cd backend"
Write-Host "  uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Frontend:" -ForegroundColor Cyan
Write-Host "  cd frontend"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "==========================================" -ForegroundColor Magenta
