<div align="center">

<img src="branding/logo-mark.svg" width="150" alt="InsaneVoice mark">

# InsaneVoice

**A free, local, ElevenLabs-class voice studio for faceless creators.**

Clone your voice from 10 seconds of audio, speak 30+ languages (Bangla included), inject emotions
and non-verbals, swap performances between voices, isolate, transcribe, dub,
direct long-form projects — and let an agent turn one prompt into a finished video.

No cloud. No account. No API keys required. No cost.

`Python 3.10+` · `CPU-friendly` · `Windows / macOS / Linux` · `MIT License`

</div>

---

## The full toolkit

| Menu | What it does |
|---|---|
| 🎙 **Studio** | Text → cloned speech. 6 languages, speed & clone-strength sliders, **emotion tags** (`[happy]`, `[whisper]`, `[sigh]`, `[gasp]`, `[pause]`…). |
| 🎬 **Director's Studio** | Long-form projects: scripts auto-cut into chunks, **3 takes per chunk**, pick the winner, regenerate any chunk alone, noise-isolated export to WAV/MP3. |
| ◉ **Voice DNA** | The analyser: pitch, warmth, brightness, grit → radar chart + a named archetype. |
| ● **Recorder** | Realtime mic capture with live waveform. |
| ☰ **Voice Library** | Every voice keeps its fingerprint + speaker embedding. **Ownership verification** by voice-metric challenge. |
| ✦ **Voice Design** | *"warm elderly British narrator, a bit breathy"* → a DSP feedback loop sculpts a voice to match, then saves it as a normal cloneable voice. |
| ⇄ **Voice Changer** | Audio-to-audio **performance transfer** in ANY language: your dramatic read, laugh or sigh comes out in the target voice. |
| ≡ **Batch Studio** | One line per clip — render a whole video queue in order. |
| ◌ **Voice Isolator** | Strip room noise and hiss from recordings. |
| ✐ **Transcribe** | Offline STT (Vosk, 15+ languages) with word timings → TXT / **SRT subtitles**. |
| ▷ **Dubbing Studio** | Video in → transcribed with timings → edit lines → re-voice with clones → **muxed back onto the video**, timing preserved. |
| ★ **Agent Studio** | One prompt → script → scenes → cloned narration → **rendered MP4**, with live SSE feedback and approval gates at every stage. |
| ⊕ **Connections** | Bring your own OpenAI-compatible text / audio / image endpoints (multi-model **failover** with context preserved). Keys stay on disk. |
| ↺ **History** | Everything stays on this machine until you delete it. |

## Quick start (Windows)

```bat
git clone https://github.com/<you>/InsaneVoice.git
cd InsaneVoice
scripts\setup_windows.bat     :: venv + deps + engines + models (~10 min, once)
scripts\start_windows.bat     :: http://127.0.0.1:8177 opens itself
```

<details>
<summary>macOS / Linux</summary>

```bash
git clone https://github.com/<you>/InsaneVoice.git && cd InsaneVoice
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git third_party/OpenVoice
git clone --depth 1 https://github.com/myshell-ai/MeloTTS.git third_party/MeloTTS
python scripts/patch_melotts.py
python scripts/download_models.py
cd backend && uvicorn main:app --host 127.0.0.1 --port 8177
```

</details>

**You need:** Python 3.10+ and [ffmpeg](https://ffmpeg.org) on PATH.
First run downloads ~330 MB of model checkpoints. STT models (~50 MB per
language) download on first use of Transcribe/Dubbing.

## How the clone works

```
 your 10–30s sample ──► Voice DNA (numpy/scipy DSP: F0, formants, spectra)
        │
        └──► OpenVoice SE extractor ──► speaker embedding (.pth)

 any text ──► MeloTTS (base speaker, CPU) ──► neutral speech
                      │
                      ▼
        OpenVoice V2 ToneColorConverter  (tau = clone-strength slider)
                      │
                      ▼
        your voice, your script ──► watermarked wav
```

**Emotions** are honest DSP per span: pitch, tempo, spectral tilt, dynamics.
**Non-verbals** (`[sigh]`, `[gasp]`, `[breath]`) are synthesised from shaped
filtered noise. `[laughter]` deliberately has no synthetic equivalent — record
a real chuckle and run it through the **Voice Changer**. That is what it is for.

**Language support:** base speech via MeloTTS (EN US/BR, ES, FR, ZH, JA, KO) and
Meta MMS-TTS (Bangla, Hindi, Arabic, German, Portuguese, Russian, Italian, Turkish,
Vietnamese, Indonesian, Dutch, Polish, …) — extra
languages load on first use with an LRU pool (8 GB laptops can't hold them all).
The Voice Changer is language-agnostic: performance in, tone out.

## Agent Studio pipeline

```
 prompt ─► script (your LLM, failover across model ids)
        ─► [you approve / edit the script]
        ─► plan (scene timings fitted to target duration)
        ─► attachments (optional, needs a vision-capable model)
        ─► audio (local cloned voice, or your connected audio model)
        ─► [you approve the audio]
        ─► visuals (built-in motion engine — animated titles, points,
           quotes, Ken-Burns images, audio-synced waveform bars)
        ─► render ─► MP4
```

Every stage streams feedback over SSE. Without any provider connected the
motion engine still renders a complete, on-brand video — the commercial in
`docs/` was produced exactly that way, narrated by InsaneVoice itself.

## Consent & ethics

1. Cloning requires an explicit **consent confirmation** stored with the voice.
2. **Ownership verification**: read 5 random words; InsaneVoice matches voice
   metrics (pitch / brightness / formants) against the reference sample.
3. Every generated clip carries an inaudible **watermark** (OpenVoice wavmark).
4. Everything is local. Keys, voices and audio never leave the machine.

Clone only voices you own or have written permission to use.

## Project layout

```
InsaneVoice/
├── backend/          FastAPI + engines
│   ├── main.py       API surface (v2)
│   ├── engine.py     multi-language MeloTTS pool + OpenVoice converter
│   ├── dna.py        Voice DNA analyser (pure numpy/scipy)
│   ├── emotions.py   tag parser + emotion DSP + non-verbal synthesis
│   ├── voice_design.py  description → sculpted voice (feedback loop)
│   ├── stt.py        Vosk offline transcription (+SRT)
│   ├── verify.py     ownership challenge (voice-metric match)
│   ├── pacing.py     multi-speaker contextual pauses
│   ├── projects.py   Director's Studio storage/takes/export
│   ├── dubbing.py    ingest → segments → revoice → mux
│   ├── motion.py     motion-graphics renderer (PIL + ffmpeg)
│   └── agents.py     connections, failover LLM calls, SSE pipeline
├── frontend/         Vanilla-JS studio (17 pages, no build step)
├── scripts/          setup · download · patch · e2e · commercial renderer
├── branding/         logo source (SVG, regenerable)
└── docs/             rendered commercial + working files
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Models are not downloaded" | `python scripts/download_models.py` |
| Import fails on m4a / webm | Install ffmpeg, restart the server |
| Extra language slow the first time | Its base model downloads once (~170 MB) |
| Agent: "No text provider connected" | Connections → add an OpenAI-compatible endpoint |
| Transcribe: model download fails | Check internet; models come from alphacephei.com |
| Clone sounds distant / rough | Raise / lower clone strength; longer cleaner sample |

## Credits

Built on [OpenVoice](https://github.com/myshell-ai/OpenVoice) and
[MeloTTS](https://github.com/myshell-ai/MeloTTS) by MyShell.ai (both MIT),
[Vosk](https://alphacephei.com/vosk) for offline STT. InsaneVoice adds the
studio, Voice DNA, emotion engine, director, dubbing, motion renderer and
agent pipeline.

## License

MIT — see [LICENSE](LICENSE).

<div align="center">
<sub>Made for creators who'd rather own their tools.</sub>
</div>
