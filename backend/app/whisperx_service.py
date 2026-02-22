from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional, Tuple, Union

from .config import COMPUTE_TYPE, DEVICE, HF_TOKEN
from .debug_log import dlog
from .diarization_local import DiarizationConfig, diarize_segments_speechbrain
from .gigaam_vendor import prefer_vendored_gigaam
from .vad import VadSegment, segment_wav_energy_vad
from .whisperx_vendor import prefer_vendored_whisperx

logger = logging.getLogger(__name__)


class TranscriptionService:
    """
    Transcription pipeline.

    Default ASR engine: GigaAM Native (v3_e2e_rnnt) with VAD longform segmentation.
    Optional diarization uses local (ECAPA + sklearn) or fast (Silero VAD + ECAPA + Mean Shift).
    """

    def __init__(
        self,
        *,
        model_name: str = "large-v3",
        batch_size: int = 8,
        align_model: Optional[str] = None,
    ) -> None:
        self.model_name = model_name
        self.batch_size = int(batch_size)
        self.align_model = align_model

        self._init_lock = asyncio.Lock()

        self._whisperx: Any = None
        self._asr_engine = (os.getenv("ASR_ENGINE") or "gigaam").strip().lower()

        self._gigaam: Any = None
        self._gigaam_model: Any = None
        self._gigaam_model_name = os.getenv("GIGAAM_MODEL", "v3_e2e_rnnt")

        # WhisperX path kept for compatibility (if ASR_ENGINE=whisperx)
        self._asr_model: Any = None
        self._align: Optional[Tuple[Any, Any]] = None
        self._diarization_required = (os.getenv("DIARIZATION_REQUIRED") or "").strip().lower() in {"1", "true", "yes"}
        self._diarization_engine = (os.getenv("DIARIZATION_ENGINE") or "").strip().lower()
        self._diarization_default_speakers = int(os.getenv("DIARIZATION_DEFAULT_SPEAKERS", "2") or "2")
        self._diarization_min_segment_s = float(os.getenv("DIARIZATION_MIN_SEGMENT_S", "0.8") or "0.8")
        self._diarization_max_segment_s = float(os.getenv("DIARIZATION_MAX_SEGMENT_S", "8") or "8")
        self._diarization_subsegment_s = float(os.getenv("DIARIZATION_SUBSEGMENT_S", "2.5") or "2.5")
        self._diarization_min_rms = float(os.getenv("DIARIZATION_MIN_RMS", "0") or "0")
        self._diarization_embedding_model = (os.getenv("DIARIZATION_EMBEDDING_MODEL") or "").strip() or "speechbrain/spkrec-ecapa-voxceleb"
        self._diarization_local_batch = int(os.getenv("DIARIZATION_LOCAL_BATCH", "8") or "8")
        self._diarization_clustering = (os.getenv("DIARIZATION_CLUSTERING") or "").strip().lower() or "agglomerative"
        self._diarization_smooth_labels = (os.getenv("DIARIZATION_SMOOTH_LABELS") or "1").strip().lower() in {"1", "true", "yes"}
        self._diarization_rms_normalize = (os.getenv("DIARIZATION_RMS_NORMALIZE") or "1").strip().lower() in {"1", "true", "yes"}
        self._diarization_therapy_mode = (os.getenv("DIARIZATION_THERAPY_MODE") or "1").strip().lower() in {"1", "true", "yes"}
        self._diarization_client_label = (os.getenv("DIARIZATION_CLIENT_LABEL") or "Клиент").strip() or "Клиент"
        self._diarization_therapist_label = (os.getenv("DIARIZATION_THERAPIST_LABEL") or "Терапевт").strip() or "Терапевт"
        self._diarization_fast_vad_threshold = float(os.getenv("DIARIZATION_FAST_VAD_THRESHOLD", "0.5") or "0.5")
        self._diarization_fast_min_speech_ms = int(os.getenv("DIARIZATION_FAST_MIN_SPEECH_MS", "250") or "250")
        self._diarization_fast_min_silence_ms = int(os.getenv("DIARIZATION_FAST_MIN_SILENCE_MS", "100") or "100")
        self._diarization_fast_mean_shift_bandwidth = float(os.getenv("DIARIZATION_FAST_MEAN_SHIFT_BANDWIDTH", "0.4") or "0.4")
        self._diarization_first = (os.getenv("DIARIZATION_FIRST") or "").strip().lower() in {"1", "true", "yes"}

        if not self._diarization_engine:
            self._diarization_engine = "fast"

    async def _transcribe_from_diarization(
        self,
        audio_path: str,
        language: str,
        num_speakers: Optional[int],
        progress_cb: Optional[Callable[[str, Optional[float]], None]],
    ) -> Optional[dict]:
        """Diarization-first pipeline: diarize → transcribe each segment. Returns aligned dict or None on skip."""
        import tempfile

        import numpy as np  # type: ignore
        import soundfile as sf  # type: ignore

        from .services.diarization_fast import DiarizationFastConfig, diarize_audio_fast

        if progress_cb:
            progress_cb("diarize", 0.2)
        fast_cfg = DiarizationFastConfig(
            device="auto",
            embedding_model=str(self._diarization_embedding_model),
            vad_threshold=float(self._diarization_fast_vad_threshold),
            min_speech_duration_ms=int(self._diarization_fast_min_speech_ms),
            min_silence_duration_ms=int(self._diarization_fast_min_silence_ms),
            mean_shift_bandwidth=float(self._diarization_fast_mean_shift_bandwidth),
            min_segment_s=float(self._diarization_min_segment_s),
            batch_size=max(1, min(int(self._diarization_local_batch), 64)),
            therapy_mode=bool(self._diarization_therapy_mode),
            client_label=str(self._diarization_client_label),
            therapist_label=str(self._diarization_therapist_label),
        )
        eff_num = 2 if self._diarization_therapy_mode else (int(num_speakers) if num_speakers is not None else None)
        diar_segments = await asyncio.to_thread(diarize_audio_fast, audio_path, fast_cfg, num_speakers=eff_num)
        if not diar_segments:
            logger.warning("Diarization-first: diarize_audio_fast returned no segments")
            return None

        max_chunk_s = 30.0
        to_transcribe: list[dict] = []
        for s in diar_segments:
            start = float(s.get("start", 0.0))
            end = float(s.get("end", start))
            spk = s.get("speaker", "")
            if end - start <= max_chunk_s:
                to_transcribe.append({"start": start, "end": end, "speaker": spk})
            else:
                t = start
                while t < end:
                    e = min(t + max_chunk_s, end)
                    to_transcribe.append({"start": t, "end": e, "speaker": spk})
                    t = e

        if progress_cb:
            progress_cb("transcribe", 0.5)
        audio_i16, sr = sf.read(audio_path, dtype="int16", always_2d=True)
        mono = audio_i16.mean(axis=1).astype(np.int16)
        seg_conc = max(1, min(int(os.getenv("SEGMENT_CONCURRENCY", "2") or "2"), 16))
        sem = asyncio.Semaphore(seg_conc)

        async def transcribe_one(idx: int, seg: dict, tdir: Path) -> Optional[dict]:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            s0, s1 = int(start * sr), int(end * sr)
            chunk = mono[s0:s1]
            if chunk.size == 0:
                return None
            seg_path = str(tdir / f"seg_{idx:05d}.wav")
            async with sem:
                def _do():
                    sf.write(seg_path, chunk, sr, subtype="PCM_16")
                    return self._gigaam_model.transcribe(seg_path)

                try:
                    text = await asyncio.to_thread(_do)
                except Exception as exc:
                    logger.warning("Diarization-first segment %d failed: %s", idx, exc)
                    return None
            text = (str(text) or "").strip() or "[...]"
            return {"start": start, "end": end, "speaker": seg.get("speaker", ""), "text": text}

        with tempfile.TemporaryDirectory(prefix="gigaam_diar_") as td:
            tdir = Path(td)
            tasks = [transcribe_one(i, s, tdir) for i, s in enumerate(to_transcribe)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        segments = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Diarization-first segment error: %s", r)
                continue
            if r:
                segments.append(r)
        segments.sort(key=lambda s: float(s.get("start", 0.0)))
        if progress_cb:
            progress_cb("align", 0.9)
        return {
            "segments": segments,
            "language": language,
            "asr_engine": "gigaam",
            "asr_model": self._gigaam_model_name,
        }

    def _wx(self) -> Any:
        if self._whisperx is None:
            prefer_vendored_whisperx()
            import whisperx  # type: ignore

            # region agent log
            try:
                import importlib.util
                import sys

                dlog(
                    run_id="pre-fix",
                    hypothesis_id="H5",
                    location="backend/app/whisperx_service.py:_wx",
                    message="whisperx import ok",
                    data={
                        "py_executable": sys.executable,
                        "whisperx_file": getattr(whisperx, "__file__", "") or "",
                        "whisperx_diarize_spec": bool(importlib.util.find_spec("whisperx.diarize")),
                    },
                )
            except Exception:
                pass
            # endregion

            self._whisperx = whisperx
        return self._whisperx

    def _ga(self) -> Any:
        if self._gigaam is None:
            # region agent log
            try:
                import importlib.util
                import sys

                project_root = Path(__file__).resolve().parents[2]
                vendor_gigaam = project_root / "vendor" / "gigaam"
                dlog(
                    run_id="pre-fix",
                    hypothesis_id="H1",
                    location="backend/app/whisperx_service.py:_ga",
                    message="gigaam import precheck",
                    data={
                        "py_executable": sys.executable,
                        "cwd": os.getcwd(),
                        "vendor_gigaam_exists": vendor_gigaam.exists(),
                        "vendor_gigaam_is_dir": vendor_gigaam.is_dir(),
                        "sys_path_0": (sys.path[0] if sys.path else ""),
                        "hydra_spec": bool(importlib.util.find_spec("hydra")),
                        "hydra_core_spec": bool(importlib.util.find_spec("hydra.core")),
                    },
                )
            except Exception:
                pass
            # endregion
            prefer_vendored_gigaam()
            try:
                import gigaam  # type: ignore
            except Exception as e:
                # region agent log
                try:
                    import importlib.util
                    import sys

                    dlog(
                        run_id="pre-fix",
                        hypothesis_id="H2",
                        location="backend/app/whisperx_service.py:_ga",
                        message="gigaam import failed",
                        data={
                            "py_executable": sys.executable,
                            "err_type": type(e).__name__,
                            "err": str(e)[:500],
                            "hydra_spec": bool(importlib.util.find_spec("hydra")),
                        },
                    )
                except Exception:
                    pass
                # endregion
                raise

            # region agent log
            try:
                import sys

                dlog(
                    run_id="pre-fix",
                    hypothesis_id="H2",
                    location="backend/app/whisperx_service.py:_ga",
                    message="gigaam import ok",
                    data={
                        "py_executable": sys.executable,
                        "gigaam_file": getattr(gigaam, "__file__", "") or "",
                        "gigaam_version": getattr(gigaam, "__version__", "") or "",
                    },
                )
            except Exception:
                pass
            # endregion

            self._gigaam = gigaam
        return self._gigaam

    async def _ensure_models(self, *, language: str) -> None:
        async with self._init_lock:
            wx = None

            if self._asr_engine == "gigaam":
                if self._gigaam_model is None:
                    ga = self._ga()
                    # NOTE: Do not log HF_TOKEN; gigaam may use it internally for VAD models.
                    # region agent log
                    try:
                        import importlib.util

                        def _spec(name: str) -> bool:
                            return bool(importlib.util.find_spec(name))

                        dlog(
                            run_id="pre-fix",
                            hypothesis_id="H4",
                            location="backend/app/whisperx_service.py:_ensure_models",
                            message="loading gigaam model",
                            data={
                                "asr_engine": self._asr_engine,
                                "gigaam_model_name": str(self._gigaam_model_name),
                                "device": str(DEVICE),
                                # Check for common missing deps that break hydra instantiate targets.
                                "sentencepiece_spec": _spec("sentencepiece"),
                                "tqdm_spec": _spec("tqdm"),
                                "torch_spec": _spec("torch"),
                                "gigaam_decoding_spec": _spec("gigaam.decoding"),
                            },
                        )
                    except Exception:
                        pass
                    # endregion
                    self._gigaam_model = await asyncio.to_thread(
                        ga.load_model,
                        self._gigaam_model_name,
                        device=DEVICE,
                    )
            else:
                wx = self._wx()
                if self._asr_model is None:
                    self._asr_model = await asyncio.to_thread(
                        wx.load_model,
                        self.model_name,
                        device=DEVICE,
                        compute_type=COMPUTE_TYPE,
                        use_auth_token=HF_TOKEN,
                    )
                if self._align is None:
                    align_model, align_meta = await asyncio.to_thread(
                        wx.load_align_model,
                        language_code=language,
                        device=DEVICE,
                        align_model=self.align_model,
                    )
                    self._align = (align_model, align_meta)

    async def transcribe(
        self,
        audio_path: Union[str, Path],
        *,
        language: str = "ru",
        num_speakers: Optional[int] = None,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
        progress_cb: Optional[Callable[[str, Optional[float]], None]] = None,
    ) -> dict:
        audio_path = str(Path(audio_path).expanduser().resolve())
        language = (language or "ru").lower()

        await self._ensure_models(language=language)
        if self._asr_engine == "gigaam":
            segments = []
            # Diarization-first: run diarization to get segments with speaker, then transcribe each.
            if self._diarization_first and self._diarization_engine == "fast":
                diar_first_result = await self._transcribe_from_diarization(audio_path, language, num_speakers, progress_cb)
                if diar_first_result is not None:
                    return diar_first_result

            # VAD-based segmentation for long audio.
            try:
                import soundfile as sf  # type: ignore

                info = sf.info(str(audio_path))
                duration_s = (
                    float(info.frames) / float(info.samplerate)
                    if info.frames and info.samplerate
                    else 0.0
                )
            except Exception as e:
                duration_s = 0.0
                logger.warning("sf.info failed for %s: %s", audio_path, e)

            min_longform_s = float(os.getenv("LONGFORM_MIN_SECONDS", "10"))
            use_longform = duration_s >= min_longform_s
            try:
                from .debug_log import dlog
                dlog(run_id="vad_diag", hypothesis_id="V0", location="whisperx_service:gigaam_path", message="duration_check", data={"duration_s": duration_s, "min_longform_s": min_longform_s, "use_longform": use_longform})
            except Exception:
                pass

            if use_longform:
                vad_threshold_scale = float(os.getenv("VAD_THRESHOLD_SCALE", "0.9") or "0.9")
                vad_boundary_padding_s = float(os.getenv("VAD_BOUNDARY_PADDING_S", "0.3") or "0.3")
                vad_segments = await asyncio.to_thread(
                    segment_wav_energy_vad,
                    audio_path,
                    threshold_scale=vad_threshold_scale,
                    boundary_padding_s=vad_boundary_padding_s,
                )
                min_gap_s = float(os.getenv("VAD_GAP_FILL_MIN_S", "1.5") or "1.5")
                if min_gap_s > 0 and vad_segments and duration_s > 0:
                    gaps_list: list[VadSegment] = []
                    prev_end = 0.0
                    for s in vad_segments:
                        start = float(getattr(s, "start_s", 0.0))
                        end = float(getattr(s, "end_s", 0.0))
                        if start - prev_end >= min_gap_s:
                            gaps_list.append(VadSegment(start_s=prev_end, end_s=start))
                        prev_end = max(prev_end, end)
                    if duration_s - prev_end >= min_gap_s:
                        gaps_list.append(VadSegment(start_s=prev_end, end_s=duration_s))
                    vad_segments = list(vad_segments) + gaps_list
                    vad_segments.sort(key=lambda x: float(getattr(x, "start_s", 0.0)))
                if not vad_segments:
                    # fallback: split into fixed windows so GigaAM gets manageable chunks (avoids truncation)
                    chunk_s = min(30.0, max(15.0, duration_s / 4.0))
                    overlap_s = 1.0
                    fallback_segs: list[VadSegment] = []
                    t = 0.0
                    while t < duration_s:
                        end_t = min(t + chunk_s, duration_s)
                        fallback_segs.append(VadSegment(start_s=t, end_s=end_t))
                        t = end_t - overlap_s if end_t < duration_s else duration_s
                    vad_segments = fallback_segs if fallback_segs else [VadSegment(start_s=0.0, end_s=duration_s)]

                max_chunk_s = 30.0
                expanded: list[VadSegment] = []
                for s in vad_segments:
                    start = float(getattr(s, "start_s", 0.0))
                    end = float(getattr(s, "end_s", start))
                    if end - start <= max_chunk_s:
                        expanded.append(s if isinstance(s, VadSegment) else VadSegment(start_s=start, end_s=end))
                    else:
                        t = start
                        while t < end:
                            e = min(t + max_chunk_s, end)
                            expanded.append(VadSegment(start_s=t, end_s=e))
                            t = e
                vad_segments = expanded

                import tempfile

                import numpy as np  # type: ignore
                import soundfile as sf  # type: ignore

                audio_i16, sr = sf.read(audio_path, dtype="int16", always_2d=True)
                mono = audio_i16.mean(axis=1).astype(np.int16)

                with tempfile.TemporaryDirectory(prefix="gigaam_vad_") as td:
                    seg_conc = int(os.getenv("SEGMENT_CONCURRENCY", "2") or "2")
                    seg_conc = max(1, min(seg_conc, 16))
                    sem = asyncio.Semaphore(seg_conc)

                    async def transcribe_one(idx: int, seg: Any) -> Optional[dict]:
                        start = max(0.0, float(getattr(seg, "start_s", 0.0)))
                        end = max(start, float(getattr(seg, "end_s", start)))
                        s0 = int(start * sr)
                        s1 = int(end * sr)
                        chunk = mono[s0:s1]
                        if chunk.size == 0:
                            return None
                        seg_path = str(Path(td) / f"seg_{idx:04d}.wav")

                        async with sem:
                            def _write_and_transcribe() -> str:
                                sf.write(seg_path, chunk, sr, subtype="PCM_16")
                                return self._gigaam_model.transcribe(seg_path)

                            text = await asyncio.to_thread(_write_and_transcribe)

                        text = (str(text) or "").strip()
                        if not text:
                            text = "[...]"
                        return {"start": start, "end": end, "text": text}

                    tasks = [transcribe_one(i, s) for i, s in enumerate(vad_segments)]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    n_empty = 0
                    n_errors = 0
                    for r in results:
                        if isinstance(r, Exception):
                            n_errors += 1
                            logger.warning("Segment transcription failed: %s", r)
                            continue
                        if r:
                            segments.append(r)
                            if (r.get("text") or "").strip() == "[...]":
                                n_empty += 1
                    try:
                        from .debug_log import dlog

                        vad_covered = sum(
                            float(getattr(s, "end_s", 0)) - float(getattr(s, "start_s", 0))
                            for s in vad_segments
                        )
                        trans_covered = sum(
                            float(s.get("end", 0)) - float(s.get("start", 0)) for s in segments
                        )
                        dlog(
                            run_id="vad_diag",
                            hypothesis_id="V1",
                            location="whisperx_service:after_longform",
                            message="VAD coverage",
                            data={
                                "audio_duration_s": duration_s,
                                "vad_segments": len(vad_segments),
                                "vad_covered_s": round(vad_covered, 1),
                                "transcribed_segments": len(segments),
                                "trans_covered_s": round(trans_covered, 1),
                                "empty_placeholder_count": n_empty,
                                "segment_errors": n_errors,
                                "gap_s": round(max(0, duration_s - vad_covered), 1),
                            },
                        )
                    except Exception:
                        pass
            else:
                # Short audio: single segment (still timestamped).
                text = await asyncio.to_thread(self._gigaam_model.transcribe, audio_path)
                text = (str(text) or "").strip()
                if text:
                    segments.append({"start": 0.0, "end": float(duration_s or 0.0), "text": text})

            segments.sort(key=lambda s: float(s.get("start") or 0.0))

            aligned: dict = {
                "segments": segments,
                "language": language,
                "asr_engine": "gigaam",
                "asr_model": self._gigaam_model_name,
            }
        else:
            wx = self._wx()
            audio = await asyncio.to_thread(wx.load_audio, audio_path)
            result: dict = await asyncio.to_thread(
                self._asr_model.transcribe,
                audio,
                batch_size=self.batch_size,
                language=language,
            )
            align_model, align_meta = self._align  # type: ignore[misc]
            aligned = await asyncio.to_thread(
                wx.align,
                result.get("segments") or [],
                align_model,
                align_meta,
                audio,
                DEVICE,
                return_char_alignments=False,
            )

        # Diarization apply stage (local or fast engine only)
        do_local_or_fast = self._diarization_engine in ("local", "fast")
        if do_local_or_fast:
            try:
                segs = aligned.get("segments") or []
                eff_num_speakers = 2 if self._diarization_therapy_mode else (
                    int(num_speakers) if num_speakers is not None else (int(max_speakers) if max_speakers is not None else None)
                )
                if self._diarization_engine == "fast":
                    from .services.diarization_fast import DiarizationFastConfig
                    from .services.diarization_factory import get_diarization_function

                    # region agent log
                    dlog(
                        run_id="pre-fix",
                        hypothesis_id="H8",
                        location="backend/app/whisperx_service.py:transcribe",
                        message="fast diarization attempt",
                        data={
                            "device": str(DEVICE),
                            "num_speakers": eff_num_speakers,
                        },
                    )
                    # endregion
                    fast_cfg = DiarizationFastConfig(
                        device="auto",
                        embedding_model=str(self._diarization_embedding_model),
                        vad_threshold=float(self._diarization_fast_vad_threshold),
                        min_speech_duration_ms=int(self._diarization_fast_min_speech_ms),
                        min_silence_duration_ms=int(self._diarization_fast_min_silence_ms),
                        mean_shift_bandwidth=float(self._diarization_fast_mean_shift_bandwidth),
                        min_segment_s=float(self._diarization_min_segment_s),
                        batch_size=max(1, min(int(self._diarization_local_batch), 64)),
                        therapy_mode=bool(self._diarization_therapy_mode),
                        client_label=str(self._diarization_client_label),
                        therapist_label=str(self._diarization_therapist_label),
                    )
                    diarize_fn = get_diarization_function("fast")
                    segs = await asyncio.to_thread(
                        diarize_fn,
                        audio_path,
                        segs,
                        cfg=fast_cfg,
                        num_speakers=eff_num_speakers,
                    )
                else:
                    # region agent log
                    dlog(
                        run_id="pre-fix",
                        hypothesis_id="H8",
                        location="backend/app/whisperx_service.py:transcribe",
                        message="local diarization attempt",
                        data={
                            "default_speakers": int(self._diarization_default_speakers),
                            "min_segment_s": float(self._diarization_min_segment_s),
                            "num_speakers": eff_num_speakers,
                            "device": str(DEVICE),
                        },
                    )
                    # endregion
                    cfg = DiarizationConfig(
                        device=str(DEVICE),
                        default_speakers=int(self._diarization_default_speakers),
                        min_segment_s=float(self._diarization_min_segment_s),
                        max_segment_s=float(self._diarization_max_segment_s),
                        subsegment_duration_s=float(self._diarization_subsegment_s),
                        min_rms=float(self._diarization_min_rms),
                        embedding_model=str(self._diarization_embedding_model),
                        batch_size=max(1, min(int(self._diarization_local_batch), 64)),
                        clustering=str(self._diarization_clustering),
                        smooth_labels=bool(self._diarization_smooth_labels),
                        rms_normalize=bool(self._diarization_rms_normalize),
                        therapy_mode=bool(self._diarization_therapy_mode),
                        client_label=str(self._diarization_client_label),
                        therapist_label=str(self._diarization_therapist_label),
                    )
                    segs = await asyncio.to_thread(
                        diarize_segments_speechbrain,
                        audio_path,
                        segs,
                        cfg=cfg,
                        num_speakers=eff_num_speakers,
                    )
                aligned["segments"] = segs
                # region agent log
                dlog(
                    run_id="pre-fix",
                    hypothesis_id="H8",
                    location="backend/app/whisperx_service.py:transcribe",
                    message="local diarization done",
                    data={
                        "segments": len(segs),
                        "speakers_labeled": sum(1 for s in segs if bool((s or {}).get("speaker"))),
                    },
                )
                # endregion
            except Exception as e:
                # region agent log
                dlog(
                    run_id="pre-fix",
                    hypothesis_id="H8",
                    location="backend/app/whisperx_service.py:transcribe",
                    message="local diarization failed",
                    data={"err_type": type(e).__name__, "err": str(e)[:500]},
                )
                # endregion
                if self._diarization_required:
                    raise

        return aligned

