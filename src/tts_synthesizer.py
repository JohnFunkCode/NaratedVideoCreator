import os
import logging
from pathlib import Path
from typing import Optional
import yaml

import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

import re

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class SpeechSynthesizer:
    """
    Synthesizes speech from text using Resemble AI's ChatterBox.

    Reads configuration (e.g., voice sample path) from settings.yaml.
    """

    def __init__(self, settings_path: str | Path = "settings.yaml") -> None:
        settings_path = Path(settings_path)
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = yaml.safe_load(f) or {}

        self.tts_cfg = self.settings.get("tts", {}) or {}
        self.paths_cfg = self.settings.get("paths", {}) or {}

        device = self.tts_cfg.get("device", "auto")
        if device == "auto":
            if torch.cuda.is_available():
                device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        logging.info(f"Initializing ChatterBox on device: {device}")
        self.model = ChatterboxTTS.from_pretrained(device=device)
        self.sample_rate = getattr(self.model, "sr", 48000)

        # Optional generation controls
        self.cfg_weight = float(self.tts_cfg.get("cfg_weight", 0.5))
        self.exaggeration = float(self.tts_cfg.get("exaggeration", 0.5))

        # Voice prompt (reference voice)
        self.voice_prompt_path = self.tts_cfg.get("voice_prompt_path") or None
        if self.voice_prompt_path:
            self.voice_prompt_path = str(Path(self.voice_prompt_path))
            if not Path(self.voice_prompt_path).exists():
                logging.warning("Configured voice_prompt_path does not exist: %s", self.voice_prompt_path)

    def _split_text(self, text: str, max_words: int = 100) -> list[str]:
        """
        Split `text` into chunks of up to `max_words` words.

        Heuristics:
        - Prefer to keep whole sentences together.
        - Prefer to respect paragraph breaks (blank lines).
        - If a single sentence exceeds `max_words`, split that sentence
          into smaller word-based chunks.
        """
        # Normalize line endings
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        # Split by blank lines (paragraph boundaries)
        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]

        chunks: list[str] = []
        current_sentences: list[str] = []
        word_count = 0

        for paragraph in paragraphs:
            # Naive sentence split: split on punctuation + whitespace.
            # This keeps the punctuation at the end of each sentence.
            sentences = [
                s.strip()
                for s in re.split(r"(?<=[.!?])\s+", paragraph)
                if s.strip()
            ]

            for sentence in sentences:
                words = sentence.split()
                n = len(words)
                if n == 0:
                    continue

                # If this sentence alone is longer than max_words:
                # flush any current chunk, then split this sentence itself.
                if n > max_words:
                    if current_sentences:
                        chunks.append(" ".join(current_sentences))
                        current_sentences = []
                        word_count = 0

                    for i in range(0, n, max_words):
                        sub_words = words[i : i + max_words]
                        sub_text = " ".join(sub_words)
                        chunks.append(sub_text)
                    continue

                # Normal case: sentence fits within max_words
                if word_count + n > max_words and current_sentences:
                    # Close current chunk, start a new one with this sentence
                    chunks.append(" ".join(current_sentences))
                    current_sentences = [sentence]
                    word_count = n
                else:
                    # Add sentence to current chunk
                    current_sentences.append(sentence)
                    word_count += n

        # Append any remaining sentences as a final chunk
        if current_sentences:
            chunks.append(" ".join(current_sentences))

        logging.info(f"\nOriginal text:\n{text}\n===")
        logging.info(f"Split into {len(chunks)} chunks")

        return chunks

    # 1A) Convert text to speech with ChatterBox, using voice sample from settings.yaml
    def synthesize_to_file(self, text: str, output_path: str | Path) -> Path:
        """
        Generate speech from `text` and save as WAV to `output_path`.
        Respects voice sample from settings.yaml if provided.
        """
        words = text.split()
        para_word_count = len(words)

        logging.info(f'Synthesizing the following text which is {para_word_count} words long:\n"{text}"\n storing the audio in: {output_path}')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # logging.info("Synthesizing to %s", output_path)
        wav = self.model.generate(
            text,
            audio_prompt_path=self.voice_prompt_path,  # may be None for default voice
            cfg_weight=self.cfg_weight,
            exaggeration=self.exaggeration,
        )

        # wav is a torch.Tensor; save via torchaudio
        ta.save(str(output_path), wav, self.sample_rate)
        return output_path

    # 1B) Read all .txt files in `text_dir` and convert them to speech
    def synthesize_directory(
        self,
        text_dir: str | Path,
        output_dir: Optional[str | Path] = None,
        suffix: str = ".wav",
    ) -> list[Path]:
        """
        Convert all *.txt files under `text_dir` into WAV files in `output_dir` (defaults to settings.paths.audio_sources_dir).
        Filenames are preserved for short files (e.g. chapter1.txt -> chapter1.wav).
        For files longer than 200 words, the text is split into chunks of up to 200 words, and
        multiple files are generated with a numeric suffix, e.g. chapter1-01.wav, chapter1-02.wav, etc.
        """
        text_dir = Path(text_dir)
        if not text_dir.exists():
            raise FileNotFoundError(f"Text directory not found: {text_dir}")

        if output_dir is None:
            audio_dir_cfg = self.paths_cfg.get("audio_sources_dir", "data/audio_sources")
            output_dir = Path(audio_dir_cfg)
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        generated: list[Path] = []
        for txt_path in sorted(text_dir.glob("*.txt")):
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            if not text:
                logging.warning("Skipping empty file: %s", txt_path.name)
                continue

            # Split text into chunks of up to 100 words
            chunks = self._split_text(text, max_words=100)
            base_name = txt_path.stem

            if len(chunks) == 1:
                out_path = output_dir / (base_name + suffix)
                if out_path.exists():
                    txt_mtime = txt_path.stat().st_mtime
                    audio_mtime = out_path.stat().st_mtime
                    if txt_mtime <= audio_mtime:
                        logging.info("Skipping up-to-date file: %s", out_path)
                        continue
                    else:
                        logging.info(
                            "Regenerating audio because text is newer: %s (txt: %s > wav: %s)",
                            out_path,
                            txt_mtime,
                            audio_mtime,
                        )

                # Either file does not exist, or text is newer – (re)generate
                self.synthesize_to_file(chunks[0], out_path)
                generated.append(out_path)
                logging.info("Generated: %s", out_path)
            else:
                for idx, chunk_text in enumerate(chunks, start=1):
                    out_path = output_dir / f"{base_name}-{idx:02d}{suffix}"
                    if out_path.exists():
                        txt_mtime = txt_path.stat().st_mtime
                        audio_mtime = out_path.stat().st_mtime
                        if txt_mtime <= audio_mtime:
                            logging.info("Skipping up-to-date file: %s", out_path)
                            continue
                        else:
                            logging.info(
                                "Regenerating audio chunk because text is newer: %s (txt: %s > wav: %s)",
                                out_path,
                                txt_mtime,
                                audio_mtime,
                            )

                    # Either file does not exist, or text is newer – (re)generate
                    self.synthesize_to_file(chunk_text, out_path)
                    generated.append(out_path)
                    logging.info(
                        "Generated chunk %02d for %s: %s",
                        idx,
                        txt_path.name,
                        out_path,
                    )

        if not generated:
            logging.warning("No .txt files found in %s", text_dir)

        return generated