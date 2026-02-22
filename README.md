# whisperx-gigaam-mac

Локальный проект для macOS (Apple Silicon) на базе WhisperX с дальнейшей интеграцией GigaAM.

## Цель

- Полностью локальная транскрипция русской речи.
- Определение собеседников (диаризация) в пайплайне.
- Экспорт результата в Markdown.

## Требования

- macOS на Apple Silicon (M1/M2/M3/M4)
- Homebrew
- Python 3.10
- FFmpeg

## Текущее состояние bootstrap

- Инициализирован Git-репозиторий.
- Создано виртуальное окружение `.venv` на Python 3.10.
- Установлены базовые зависимости:
  - `torch`, `torchaudio`, `torchvision` (с поддержкой MPS backend)
  - `whisperx` из официального репозитория
- Зафиксированы версии в `requirements.txt`.

## Структура проекта

```text
whisperx-gigaam-mac/
  src/
  scripts/
  data/
  output/
  .venv/
  requirements.txt
  README.md
```

## Быстрый старт

1. Активировать окружение:

```bash
source "/Users/olegturushev/Note Therapy/whisperx-gigaam-mac/.venv/bin/activate"
```

2. Проверить FFmpeg:

```bash
ffmpeg -version
```

3. Проверить PyTorch/MPS и WhisperX:

```bash
python -c "import torch, whisperx; print('mps_built=', torch.backends.mps.is_built()); print('mps_available=', torch.backends.mps.is_available())"
```

## Примечания

- `whisperx` установлен из официального репозитория и сейчас включает полный набор зависимостей.
- На следующем этапе можно скорректировать зависимости под интеграцию GigaAM и зафиксировать целевую конфигурацию пайплайна.
