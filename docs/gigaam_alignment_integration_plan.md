# GigaAM Integration Plan for WhisperX Fork

## Scope

This plan targets replacing/augmenting WhisperX forced alignment model loading so Russian alignment can run through a GigaAM-based backend exposed via Hugging Face Transformers.

Fork target: `vendor/whisperx`  
Working branch: `feature/gigaam-integration`

## Key WhisperX Files Reviewed

- `vendor/whisperx/whisperx/alignment.py`
  - `load_align_model(...)` currently supports:
    - torchaudio bundles (`torchaudio.pipelines`)
    - Hugging Face Wav2Vec2 CTC (`Wav2Vec2Processor`, `Wav2Vec2ForCTC`)
  - `align(...)` expects:
    - logits/emissions over token vocabulary
    - `align_metadata` with `dictionary`, `language`, and `type`
  - Russian default align model currently points to wav2vec2 XLSR.
- `vendor/whisperx/whisperx/__init__.py`
  - lazy import wrappers (`load_align_model`, `align`) are stable extension points.
- `vendor/whisperx/whisperx/utils.py`
  - language maps include `ru`
  - writer stack already supports speaker-tagged text and subtitle formats.

Additional call-site reviewed:
- `vendor/whisperx/whisperx/transcribe.py`
  - alignment orchestration happens in Part 2 (`load_align_model` -> `align`)
  - CLI already supports `--align_model`, `--language`, cache control.

## External Architecture Notes (for GigaAM backend)

Observed reusable pattern from public GigaAM+Transformers integrations:

1. Load model via `AutoModel.from_pretrained(..., trust_remote_code=True, revision=...)`
2. Load processor via `AutoProcessor.from_pretrained(..., trust_remote_code=True)` when available
3. Convert waveform to 16 kHz mono features
4. Produce frame-level logits (CTC-style variants) and decode token IDs
5. Reuse standard CTC post-processing/alignment logic

Relevant references:
- `ai-sage/GigaAM-v3` (HF model card): recommends `AutoModel(..., trust_remote_code=True)` and revisions (`ctc`, `rnnt`, `e2e_ctc`, `e2e_rnnt`)
- `Den4ikAI/gigaam-ctc-whisperx` (HF model card): demonstrates AutoModel/AutoProcessor custom-code interface for GigaAM CTC

## Proposed Integration Design

### 1) Add pluggable align backend type in `alignment.py`

- Extend `load_align_model(...)` with backend detection:
  - `type="torchaudio"` (existing)
  - `type="huggingface_wav2vec2"` (existing)
  - `type="huggingface_gigaam"` (new)
- For GigaAM backend:
  - load with `AutoModel` (not `AutoModelForCTC`)
  - prefer CTC-compatible revision first (for alignment logits)
  - build a tokenizer dictionary from processor/tokenizer when present

### 2) Introduce GigaAM alignment adapter module

- New file: `vendor/whisperx/whisperx/gigaam_alignment.py`
- Responsibilities:
  - normalize model I/O to WhisperX alignment expectations
  - expose a callable returning frame-level logits
  - hide differences between GigaAM CTC and other variants
- Keep `alignment.py` logic mostly intact by adapting output shape to current trellis/backtrack code.

### 3) Update Russian default alignment routing

- In `alignment.py`, for `language_code == "ru"`:
  - allow selecting GigaAM via explicit model id or config flag
  - fallback to current wav2vec2 model if GigaAM loading fails

### 4) Add CLI controls in `transcribe.py`

- Add args:
  - `--align_backend` (`auto|wav2vec2|gigaam`)
  - `--align_revision` (default for GigaAM `ctc` or project-defined)
- Pass through to `load_align_model(...)`.

### 5) Validation and compatibility checks

- Add strict checks:
  - sample rate = 16 kHz
  - logits rank and vocab dimension
  - dictionary/token alignment with text normalization rules
- Keep existing fallback path to avoid regression for non-Russian languages.

## Rollout Phases

1. Wire backend selection + adapter scaffolding (no behavior change by default)
2. Enable GigaAM for RU in feature flag mode
3. Compare timestamp quality vs baseline wav2vec2 on RU samples
4. Promote GigaAM RU backend to default if stable

## Risks

- GigaAM revisions differ in output APIs (`ctc` vs `e2e_*` vs `rnnt`)
- Some revisions may expose `transcribe()` but not direct CTC logits
- `trust_remote_code=True` introduces dependency on remote modeling code versions

## Acceptance Criteria

- RU alignment can run through GigaAM backend without breaking existing CLI UX
- Non-RU paths remain unchanged
- Forced alignment output remains schema-compatible with WhisperX writers
- Feature branch keeps fallback to current wav2vec2 alignment
