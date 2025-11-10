"""
Example CLI for the pipeline:
  1) Convert all text files under paths.text_sources_dir to WAVs in paths.audio_sources_dir
  2) Build a final video by pairing PNGs in paths.image_sources_dir with WAVs in paths.audio_sources_dir
"""
import argparse
from pathlib import Path
import yaml
import logging


from tts_synthesizer import SpeechSynthesizer
from video_producer import VideoProducer

def load_paths(settings_path: str | Path = "settings.yaml") -> dict:
    with open(settings_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("paths", {})

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Chatterbox TTS + MoviePy pipeline")
    parser.add_argument("--settings", default="settings.yaml", help="Path to YAML settings file")
    parser.add_argument("--synthesize", action="store_true", help="Synthesize all text files to WAVs")
    parser.add_argument("--make-video", action="store_true", help="Assemble video from image/audio sources")
    args = parser.parse_args()

    paths = load_paths(args.settings)
    text_dir = paths.get("text_sources_dir", "data/text_sources")
    audio_dir = paths.get("audio_sources_dir", "data/audio_sources")
    root_dir = "data"

    if args.synthesize:
        synth = SpeechSynthesizer(args.settings)
        synth.synthesize_directory(text_dir=text_dir, output_dir=audio_dir)

    if args.make_video:
        producer = VideoProducer(args.settings)
        out = producer.create_video_from_directory(root_dir=root_dir)
        print(f"Final video written to: {out}")

if __name__ == "__main__":
    import os
    from pathlib import Path

    os.chdir(Path(__file__).parent.parent)
    main()