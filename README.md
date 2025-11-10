# Chatterbox TTS → MoviePy Video Pipeline

This project turns `.txt` files into narrated `.wav` audio using **Resemble AI's Chatterbox TTS**, then pairs `.png` images with the generated audio to render a stitched video using **MoviePy**.

## What it does

1. **Text → Speech** (Chatterbox TTS)
   - Uses the reference voice sample specified in `settings.yaml` (`tts.voice_prompt_path`) to synthesize lifelike voices.
   - Converts each `*.txt` file under `data/text_sources/` into a `*.wav` with the same filename under `data/audio_sources/`.

2. **Images + Audio → Final Video** (MoviePy)
   - Looks for matching basenames between `data/image_sources/*.png` and `data/audio_sources/*.wav` (e.g. `intro.png` + `intro.wav`).
   - Builds a clip for each pair, letterboxes images to a target resolution, and concatenates all clips into one video.
   - Writes the final video into `data/final_video/` (filename pattern configurable).

## Project layout

```text
chatterbox_moviepy_project/
├─ src/
│  ├─ tts_synthesizer.py      # Class: SpeechSynthesizer – text→speech
│  └─ video_producer.py       # Class: VideoProducer – build final video
├─ data/
│  ├─ text_sources/           # Your .txt inputs
│  ├─ audio_sources/          # Generated .wav (and/or your own WAVs)
│  ├─ image_sources/          # Your .png stills, named to match WAVs
│  └─ final_video/            # Output .mp4
├─ voice_samples/             # Put your reference voice .wav here
├─ src/main.py                # Optional CLI: synthesize + assemble
├─ settings.yaml              # All configuration lives here
├─ requirements.txt
└─ README.md
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
```

**Dependencies** (see `requirements.txt`):
- `chatterbox-tts` (Resemble AI) – open-source TTS engine
- `moviepy` – video assembly
- `torchaudio` – saving WAVs
- `pyyaml` – config parsing

> **FFmpeg is required** by MoviePy. Install it with your OS package manager and ensure `ffmpeg` is on your PATH.

## Configure

Edit `settings.yaml`:

- `tts.voice_prompt_path`: Path to a reference voice sample `.wav` to guide Chatterbox's voice. Leave empty to use the default voice.
- `tts.device`: `"cuda"`, `"mps"`, `"cpu"`, or `"auto"` (auto-detect).
- `video.resolution`: Final video `(width, height)`; images are letterboxed to fit.
- `paths.*`: You can relocate any of the data folders here.

## Usage

1. Drop your `.txt` files into `data/text_sources/` and `.png` images into `data/image_sources/`.
2. (Optional) Place a reference voice sample in `voice_samples/` and set `tts.voice_prompt_path` in `settings.yaml`.
3. Run the pipeline via the CLI:

```bash
cd chatterbox_moviepy_project
python -m src.main --settings settings.yaml --synthesize --make-video
```

- The synth step creates WAVs in `data/audio_sources/`.
- The video step pairs `*.png` with `*.wav` (by basename) and writes an `.mp4` to `data/final_video/`.

## API (Classes)

### `SpeechSynthesizer`
- `synthesize_to_file(text: str, output_path: Path) -> Path`  
  Generate speech for a single string and save as WAV (uses the voice sample from `settings.yaml`).
- `synthesize_directory(text_dir: Path, output_dir: Optional[Path] = None, suffix: str = ".wav") -> list[Path]`  
  Batch-convert all `*.txt` in a directory to WAVs, preserving filenames.

### `VideoProducer`
- `create_video_from_directory(root_dir: Path, output_path: Optional[Path] = None) -> Path`  
  Pair `image_sources/*.png` with `audio_sources/*.wav` under `root_dir`, build clips, concatenate, and save a single `.mp4` into `final_video/`.

## Notes & Tips

- Chatterbox usage follows the official pattern: load a model and call `model.generate(text, audio_prompt_path=...)`.  
  See the upstream README for details.
- If your images have different aspect ratios, this project letterboxes them to a consistent resolution to avoid MoviePy concatenation errors.
- Set `video.fps` in `settings.yaml` if you need a specific framerate.

---
**Credits:**  
- Chatterbox TTS by Resemble AI (MIT).  
- MoviePy (MIT).