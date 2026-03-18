# Note Therapy

Транскрибация и анализ психотерапевтических сессий.

## Возможности

- **Транскрибация аудио** — локальная обработка на CPU с использованием GigaAM и WhisperX
- **Диаризация** — определение спикеров (терапевт/клиент) с помощью Silero VAD + ECAPA + Mean Shift
- **Экспорт в Markdown** — хронологическая расшифровка диалога без временных меток
- **Анализ сессий** — AI-анализ через OpenRouter (deepseek/deepseek-chat) по требованию

## Требования

- Python 3.10+
- FFmpeg
- macOS / Windows / Linux

## Установка

### macOS / Linux

```bash
./install.sh
```

### Windows (PowerShell)

```powershell
.\install.ps1
```

### Windows (cmd)

```cmd
install.bat
```

Скрипт установки:
1. Проверяет Python
2. Запрашивает HuggingFace токен (для загрузки моделей)
3. Запрашивает OpenRouter ключ (для анализа)
4. Устанавливает зависимости
5. Создаёт файл `.env`
6. Скачивает модели

### Получить токены

**HuggingFace** (https://huggingface.co):
1. Зарегистрироваться
2. Settings → Access Tokens → создать токен с правами Read
3. Принять условия использования моделей:
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-3.1

**OpenRouter** (https://openrouter.ai):
1. Зарегистрироваться
2. Settings → API Keys → создать ключ
3. Бесплатные модели: deepseek/deepseek-chat

## Запуск

### Backend

```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm run dev
```

Открыть http://localhost:3000

## Использование

1. Загрузить аудиофайл (mp3, wav, m4a)
2. Нажать "Начать транскрибацию"
3. Дождаться завершения
4. Скачать Markdown с расшифровкой
5. (По желанию) Нажать "Скачать анализ" для AI-анализа сессии

## Структура проекта

```
whisperx-gigaam-mac/
├── backend/              # FastAPI сервер
│   ├── app/
│   │   ├── main.py      # API endpoints
│   │   ├── worker.py    # Транскрибация
│   │   ├── whisperx_service.py
│   │   ├── diarization_fast.py
│   │   ├── openrouter_service.py
│   │   └── config.py    # Конфигурация
│   └── requirements.txt
├── frontend/             # Vue.js приложение
│   ├── src/
│   │   ├── App.vue
│   │   └── services/api.js
│   └── package.json
├── output/              # Скачанные файлы
├── install.sh           # Установщик macOS/Linux
├── install.ps1          # Установщик Windows (PowerShell)
├── install.bat          # Установщик Windows (cmd)
├── requirements.txt     # Основные зависимости
└── .env                 # Конфигурация (создаётся при установке)
```

## Конфигурация

Параметры в `.env`:

| Параметр | Описание | По умолчанию | Оптимизировано |
|----------|----------|--------------|----------------|
| HF_TOKEN | HuggingFace токен | - | - |
| OPENROUTER_API_KEY | OpenRouter ключ | - | - |
| DIARIZATION_ENGINE | diarizer: fast | fast | fast |
| DIARIZATION_EMBEDDING_MODEL | Модель эмбеддингов | ecapa-voxceleb | **ecapa-voxceleb-m** |
| DIARIZATION_THERAPY_MODE | Режим терапии (2 спикера) | 1 | 1 |
| SEGMENT_CONCURRENCY | Параллельных сегментов | 4 | 16 |
| DIARIZATION_FAST_MIN_SPEECH_MS | Min речь (мс) | 250 | 400 |
| DIARIZATION_FAST_MIN_SILENCE_MS | Min тишина (мс) | 100 | 200 |

## Оптимизация производительности

После оптимизации (autoresearch):
- **Время транскрибации**: ~9с vs 13.1с (baseline) — **на 30% быстрее**
- **RTF**: 0.15 vs 0.22
- **Тест**: 60-секундное аудио на M2 Mac

### Ключевые параметры

```env
DIARIZATION_EMBEDDING_MODEL=speechbrain/spkrec-ecapa-voxceleb-m
SEGMENT_CONCURRENCY=16
DIARIZATION_FAST_MIN_SPEECH_MS=400
DIARIZATION_FAST_MIN_SILENCE_MS=200
```

## Технические notes

- **CPU-only**: Для стабильности на macOS используется CPU + int8 (MPS отключён из-за проблем с памятью)
- **Диаризация**: Fast mode использует Silero VAD + ECAPA embedding + Mean Shift кластеризация
- **Анализ**: Запускается только по кнопке "Скачать анализ", не автоматически

## Лицензия

MIT
