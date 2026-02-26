#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  Note Therapy - Установка"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Python
print_info "Проверка Python..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 не найден. Установите Python 3.10+ с сайта python.org или через brew:"
    echo "  brew install python@3.10"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_success "Python $PYTHON_VERSION"

# Check pip
if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null; then
    print_error "pip не найден"
    exit 1
fi
print_success "pip найден"

# Check HuggingFace CLI
print_info "Проверка huggingface-cli..."
if ! command -v huggingface-cli &> /dev/null; then
    print_warning "huggingface-cli не найден, будет установлен с dependencies"
fi

# Initialize git submodules
print_info "Инициализация git-субмодулей..."
if [ -d ".git" ]; then
    git submodule update --init --recursive 2>/dev/null || print_warning "Не удалось инициализировать субмодули"
else
    print_warning ".git не найден - субмодули не будут инициализированы"
fi

# Create output directory
mkdir -p output

echo ""
echo "=========================================="
echo "  Настройка Hugging Face"
echo "=========================================="
echo ""
echo -e "${YELLOW}Для загрузки моделей GigaAM и pyannote требуется токен Hugging Face.${NC}"
echo ""
echo "Инструкция:"
echo "1. Зарегистрируйтесь на https://huggingface.co"
echo "2. Перейдите в Settings -> Access Tokens"
echo "3. Создайте новый токен (Read permissions)"
echo "4. При первом использовании pyannote нужно принять условия:"
echo "   - https://huggingface.co/pyannote/segmentation-3.0"
echo "   - https://huggingface.co/pyannote/speaker-diarization-3.1"
echo ""
echo -n "Введите ваш Hugging Face токен (или нажмите Enter чтобы пропустить): "
read -r HF_TOKEN_INPUT

if [ -n "$HF_TOKEN_INPUT" ]; then
    print_info "Настройка Hugging Face токена..."
    if command -v huggingface-cli &> /dev/null; then
        echo "$HF_TOKEN_INPUT" | huggingface-cli login || print_warning "Не удалось войти через CLI"
    fi
    HF_TOKEN_LINE="HF_TOKEN=$HF_TOKEN_INPUT"
else
    print_warning "Токен HF не введён - некоторые модели могут не загрузиться"
    HF_TOKEN_LINE="# HF_TOKEN="
fi

# Accept pyannote conditions if token provided
if [ -n "$HF_TOKEN_INPUT" ]; then
    echo ""
    print_info "Принятие условий использования pyannote..."
    echo "Для принятия условий перейдите по ссылкам в браузере и нажмите 'Agree':"
    echo "  - https://huggingface.co/pyannote/segmentation-3.0"
    echo "  - https://huggingface.co/pyannote/speaker-diarization-3.1"
    echo ""
    read -p "Нажмите Enter после принятия условий..."
    
    # Try to download models to verify access
    print_info "Проверка доступа к моделям pyannote..."
    python3 -c "
import huggingface_hub
try:
    huggingface_hub.hf_hub_download('pyannote/segmentation-3.0', 'README.md', token='$HF_TOKEN_INPUT')
    print('segmentation-3.0: OK')
except Exception as e:
    print(f'segmentation-3.0: {e}')
try:
    huggingface_hub.hf_hub_download('pyannote/speaker-diarization-3.1', 'README.md', token='$HF_TOKEN_INPUT')
    print('speaker-diarization-3.1: OK')
except Exception as e:
    print(f'speaker-diarization-3.1: {e}')
" || print_warning "Не удалось проверить доступ к моделям"
fi

echo ""
echo "=========================================="
echo "  Настройка OpenRouter"
echo "=========================================="
echo ""
echo -e "${YELLOW}Для анализа сессий требуется OpenRouter API ключ (бесплатные модели доступны).${NC}"
echo ""
echo "Инструкция:"
echo "1. Зарегистрируйтесь на https://openrouter.ai"
echo "2. Перейдите в Settings -> API Keys"
echo "3. Создайте новый ключ"
echo "4. Бесплатные модели: deepseek/deepseek-chat, openrouter/default"
echo ""
echo -n "Введите ваш OpenRouter API ключ (или нажмите Enter чтобы пропустить): "
read -r OPENROUTER_KEY_INPUT

if [ -n "$OPENROUTER_KEY_INPUT" ]; then
    OPENROUTER_LINE="OPENROUTER_API_KEY=$OPENROUTER_KEY_INPUT"
    print_success "OpenRouter ключ сохранён"
else
    print_warning "Ключ не введён - анализ сессий будет недоступен"
    OPENROUTER_LINE="# OPENROUTER_API_KEY="
fi

echo ""
echo "=========================================="
echo "  Установка зависимостей"
echo "=========================================="
echo ""

# Check if in conda environment
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    print_info "Conda environment: $CONDA_DEFAULT_ENV"
fi

# Upgrade pip
print_info "Обновление pip..."
python3 -m pip install --upgrade pip --quiet 2>/dev/null || true

# Install GigaAM from vendor (editable mode)
print_info "Установка GigaAM из vendor..."
if [ -d "vendor/gigaam" ] && [ -f "vendor/gigaam/pyproject.toml" ]; then
    pip3 install -e ./vendor/gigaam --quiet 2>/dev/null || print_warning "Не удалось установить gigaam"
else
    print_warning "vendor/gigaam не найден"
fi

# Install backend requirements (includes all backend deps)
if [ -f "backend/requirements.txt" ]; then
    print_info "Установка backend зависимостей..."
    pip3 install -r backend/requirements.txt --quiet 2>/dev/null || print_warning "Некоторые пакеты не установились"
fi

# Install WhisperX from vendor (editable mode)
print_info "Установка WhisperX из vendor..."
if [ -d "vendor/whisperx" ] && [ -f "vendor/whisperx/setup.py" -o -f "vendor/whisperx/pyproject.toml" ]; then
    pip3 install -e ./vendor/whisperx --quiet 2>/dev/null || print_warning "Не удалось установить whisperx"
else
    print_info "vendor/whisperx не найден, будет использован из requirements.txt"
    # Install whisperx from requirements.txt if vendor not available
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt --quiet 2>/dev/null || print_warning "Некоторые пакеты не установились"
    fi
fi

# Install frontend dependencies
if [ -f "frontend/package.json" ]; then
    print_info "Установка frontend зависимостей..."
    cd frontend
    npm install --silent 2>/dev/null || print_warning "npm install failed"
    cd ..
fi

print_success "Зависимости установлены"

echo ""
echo "=========================================="
echo "  Создание .env файла"
echo "=========================================="
echo ""

# Create .env file
cat > .env << EOF
# Hugging Face access token (optional) for WhisperX models or GigaAM.
$HF_TOKEN_LINE

# Backend defaults
ASR_ENGINE=gigaam
GIGAAM_MODEL=v3_e2e_rnnt
LONGFORM_MIN_SECONDS=10
SEGMENT_CONCURRENCY=4
VAD_THRESHOLD_SCALE=0.9
VAD_BOUNDARY_PADDING_S=0.3
VAD_GAP_FILL_MIN_S=1.5
WHISPERX_MODEL=tiny
WHISPERX_LANGUAGE=ru
WHISPERX_BATCH_SIZE=8
JOBS_CONCURRENCY=1

# Diarization
DIARIZATION_ENGINE=fast
DIARIZATION_FIRST=1
DIARIZATION_REQUIRED=0
DIARIZATION_DEFAULT_SPEAKERS=2
DIARIZATION_THERAPY_MODE=1
DIARIZATION_MIN_SEGMENT_S=0.8
DIARIZATION_MAX_SEGMENT_S=8
DIARIZATION_SUBSEGMENT_S=2.5
DIARIZATION_MIN_RMS=0
DIARIZATION_EMBEDDING_MODEL=speechbrain/spkrec-ecapa-voxceleb
DIARIZATION_LOCAL_BATCH=8
DIARIZATION_CLUSTERING=agglomerative
DIARIZATION_SMOOTH_LABELS=1
DIARIZATION_RMS_NORMALIZE=1
DIARIZATION_FAST_VAD_THRESHOLD=0.5
DIARIZATION_FAST_MIN_SPEECH_MS=250
DIARIZATION_FAST_MIN_SILENCE_MS=100
DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH=0.4

WHISPERX_DISABLE=0

# OpenRouter API - for therapy session analysis
$OPENROUTER_LINE
EOF

print_success ".env файл создан"

echo ""
echo "=========================================="
echo "  Загрузка моделей"
echo "=========================================="
echo ""

# Download models using Python
print_info "Загрузка моделей (может занять несколько минут)..."
print_info "GigaAM устанавливается из vendor/, загружаем только модели для whisperx и diarization..."

python3 << 'PYTHON_SCRIPT'
import os
import sys

# Set token from env
hf_token = os.getenv("HF_TOKEN", "").strip()

# Remove # from token line if present
if hf_token.startswith("#"):
    hf_token = ""

try:
    from huggingface_hub import hf_hub_download, snapshot_download

    print("Downloading Whisper tiny...")
    try:
        from faster_whisper import WhisperModel
        WhisperModel("tiny", device="cpu", compute_type="int8")
        print("  Whisper tiny: OK")
    except Exception as e:
        print(f"  Whisper tiny: {e}")

    print("Downloading ECAPA model...")
    try:
        snapshot_download(
            repo_id="speechbrain/spkrec-ecapa-voxceleb",
            token=hf_token if hf_token else None
        )
        print("  ECAPA: OK")
    except Exception as e:
        print(f"  ECAPA: {e}")

    print("Downloading pyannote segmentation model (for VAD)...")
    try:
        hf_hub_download(
            repo_id="pyannote/segmentation-3.0",
            filename="pytorch_model.bin",
            token=hf_token if hf_token else None
        )
        print("  segmentation-3.0: OK")
    except Exception as e:
        print(f"  segmentation-3.0: {e}")

    print("Models download complete!")

except ImportError as e:
    print(f"huggingface_hub not available: {e}")
    print("Models will be downloaded on first run")
except Exception as e:
    print(f"Error downloading models: {e}")

PYTHON_SCRIPT

echo ""
echo "=========================================="
echo "  Проверка установки"
echo "=========================================="
echo ""

# Verify key imports
print_info "Проверка импортов..."
python3 -c "
import sys
errors = []

try:
    import gigaam
except Exception as e:
    errors.append(f'gigaam: {e}')

try:
    import whisperx
except Exception as e:
    errors.append(f'whisperx: {e}')

try:
    import speechbrain
except Exception as e:
    errors.append(f'speechbrain: {e}')

try:
    import faster_whisper
except Exception as e:
    errors.append(f'faster_whisper: {e}')

try:
    import fastapi
except Exception as e:
    errors.append(f'fastapi: {e}')

if errors:
    print('Errors found:')
    for e in errors:
        print(f'  - {e}')
    sys.exit(1)
else:
    print('All imports OK')
"

if [ $? -eq 0 ]; then
    print_success "Установка завершена!"
else
    print_warning "Некоторые импорты не работают - попробуйте перезапустить скрипт"
fi

echo ""
echo "=========================================="
echo "  Запуск"
echo "=========================================="
echo ""
echo "Backend:"
echo "  cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
echo ""
echo "Frontend:"
echo "  cd frontend && npm run dev"
echo ""
echo "=========================================="
