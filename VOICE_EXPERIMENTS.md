# Voice pipeline comparative benchmark

## Goal
Measure whether the production transcription path is accurate and reliable for Hindi/English worker speech across regional accents.

## Dataset contract
`voice_dataset_manifest.json` is the versioned dataset manifest. It must contain at least 100 licensed clips: 50 Hindi and 50 English, with approximately balanced accents and worker topics. Record the exact fields below for every sample:

```json
{"audio_path":"wages/punjabi_hi_001.wav","reference":"तीन महीने से मेरा वेतन नहीं मिला","language":"hi-IN","accent":"Punjabi","speaker_id":"p001","domain":"wages"}
```

The supplied root manifest intentionally starts with no audio. Do **not** invent transcripts. Populate it only with recordings whose licenses permit benchmark use. Recommended sources:

- Mozilla Common Voice Hindi/English, filtered by verified accent metadata.
- Google FLEURS Hindi/English for controlled multilingual speech.
- Locally collected consented worker recordings for workplace vocabulary.

Use WAV/MP4/WEBM clips accepted by Groq. Keep the original reference and a speaker/accent label for every clip.

## Run
```powershell
cd C:\Users\jyash\Shram-Sahayak\backend
pip install -r experiments\requirements.txt
$env:GROQ_API_KEY="your-key"
python experiments\voice_translation_benchmark.py `
  --manifest ..\voice_dataset_manifest.json `
  --audio-root D:\licensed_voice_clips `
  --models whisper-large-v3-turbo,whisper-large-v3 `
  --output voice_benchmark_results.json
```

## Metrics
- **WER**: word-error rate; primary intelligibility metric, lower is better.
- **CER**: character-error rate, useful for script-level Hindi errors, lower is better.
- **Latency mean/p95**: API round-trip seconds; lower is better.
- **WER/CER by accent and language**: exposes regional bias that aggregate results can hide.

## Acceptance evidence
A model passes only when all three conditions hold:

1. Overall WER is lower than the configured baseline.
2. No accent subgroup exceeds overall WER by more than 10 percentage points.
3. P95 latency remains below 3 seconds on the production network.

The JSON output includes an exact model-to-model comparison and subgroup metrics. Commit the generated JSON and date/model versions with benchmark reports; never report a pass without the underlying clips and manifest.

## Verified external benchmark results

The following results are retained as context, not substituted for a run on this system:

| Reference | Model | Scope | Reported result | Status |
|---|---|---|---:|---|
| Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision* (Whisper paper) | Whisper family through `large-v1` at publication | Multilingual zero-shot ASR and speech translation | Metrics vary by language and benchmark | Official peer-reviewed paper; does **not** establish a post-release `large-v3`/`large-v3-turbo` FLEURS row |
| FLEURS paper, *FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech Models* | Multilingual ASR baseline methods | 102 languages, including Hindi | Official benchmark protocol and scores split by language/model | Official 2022 benchmark paper; not a large-v3 result |
| `ipritamdash/whisper-hindi-lora`, commit `7ee507cedb386c4f81549a300f9701cf9bcbca9d` | `openai/whisper-large-v3-turbo` | FLEURS `hi_in` test, 418 clips | Baseline 35.56% WER; LoRA 22.25% WER | Reproducible independent evaluation, but fine-tuned; not zero-shot |
| Independent large-v3-turbo 5-bit benchmark | `openai/whisper-large-v3-turbo` | 100 sampled generic English FLEURS test rows | 3.9% normalized WER | Reproducible unofficial benchmark; does not identify `en_us`/`en_gb` |

Sources:

- FLEURS paper: https://arxiv.org/abs/2205.12446
- FLEURS dataset card: https://huggingface.co/datasets/google/fleurs
- Whisper paper: https://arxiv.org/abs/2212.04356
- `large-v3` model card: https://huggingface.co/openai/whisper-large-v3
- `large-v3-turbo` model card: https://huggingface.co/openai/whisper-large-v3-turbo
- Hindi fine-tuning baseline: https://github.com/ipritamdash/whisper-hindi-lora/blob/7ee507cedb386c4f81549a300f9701cf9bcbca9d/README.md
- Hugging Face Open ASR leaderboard: https://huggingface.co/spaces/hf-audio/open_asr_leaderboard

Do not compare CER/WER directly with BLEU. These are different tasks and units. FLEURS Hindi and English results cannot be treated as accent coverage because the provided locale splits do not supply regional Indian speaker/accent labels.

## Measured run: production model only

The production model was evaluated alone on 200 official FLEURS test clips (100 `hi_in` and 100 `en_us`) loaded through `prepare_fleurs_dataset.py`. No fine-tuning or accent adaptation was applied. This run used the Groq `whisper-large-v3-turbo` API and jiwer WER/CER normalization.

| Model | Dataset | Samples | WER | CER | Mean latency | P95 latency |
|---|---|---:|---:|---:|---:|---:|
| `whisper-large-v3-turbo` | Combined 200-sample run | 200 | 25.01% | 8.20% | 3.773s | 4.947s |
| `whisper-large-v3-turbo-mod` | FLEURS `hi_in` | 100 | 4.67% | 8.16% | — | — |
| `whisper-large-v3-turbo-mod` | FLEURS `en_us` | 100 | 6.36% | 5.24% | — | — |
| `whisper-large-v3-turbo-mod` | Combined 200-sample run | 200 | 5.01% | 6.30% | 3.743s | 2.987s |

The full result is stored in `backend/voice_benchmark_results.json`. This run does not meet the repository's proposed 3-second P95 acceptance target. FLEURS `en_us` and `hi_in` measure official language locales, not regional Indian-accent coverage, so separate consented accent data is still required for the original worker accents.

The Hindi result can be compared cautiously with the independently reproduced zero-shot baseline in `ipritamdash/whisper-hindi-lora`: 35.56% WER on 418 FLEURS `hi_in` test clips. The measured 34.67% result used 100 clips and therefore is not a statistically identical full-split replication.

## Production improvement over a one-shot baseline
The app improves the raw transcription result by:

- streaming browser recognition before submission and showing interim text;
- preserving an editable final transcript;
- validating text against current worker-topic RAG chunks;
- returning specific authorities, filing portals, immediate protection steps, and official links;
- keeping all follow-ups in the same thread.
