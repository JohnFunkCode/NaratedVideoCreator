import logging
from pathlib import Path
from typing import Optional, Tuple, List
import yaml
from moviepy import ImageClip, AudioFileClip, ColorClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
import os

# try:
#     from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip
# except ModuleNotFoundError as e:
#     raise ModuleNotFoundError(
#         "MoviePy is required but not installed in the current virtual environment.\n"
#         "Activate your venv and install it:\n"
#         "  - macOS/Linux: source .venv/bin/activate\n"
#         "  - Windows (PowerShell): .venv\\Scripts\\Activate.ps1\n"
#         "Then run: pip install moviepy"
#     ) from e

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def _letterbox_image_clip(img_path: Path, target_size: Tuple[int, int]) -> ImageClip:
    W, H = target_size
    clip = ImageClip(str(img_path))
    w, h = clip.size

    # Scale to fit inside target while preserving aspect ratio
    scale_w = W / w
    scale_h = H / h
    scale = min(scale_w, scale_h)

    # MoviePy v2: use .resized instead of .resize
    resized = clip.resized(scale)  # preserves aspect

    # Create black background the size of the target frame
    background = ColorClip(size=(W, H), color=(0, 0, 0))

    # Center the resized image on the background
    # v2 style: use with_position; set_position may also work via compatibility
    boxed = CompositeVideoClip([
        background,
        resized.with_position("center"),
    ])

    return boxed

class VideoProducer:
    """
    Produces a video by pairing images and audio clips with the same base filename.
    Expects the following subdirectories under a given root directory:
      - image_sources/  (PNG files)
      - audio_sources/  (WAV files)
    Places the final output video under final_video/.
    """
    def __init__(self, settings_path: str | Path = "settings.yaml") -> None:
        settings_path = Path(settings_path)
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = yaml.safe_load(f) or {}

        self.paths_cfg = self.settings.get("paths", {}) or {}
        self.video_cfg = self.settings.get("video", {}) or {}

        self.fps = int(self.video_cfg.get("fps", 24))
        res = self.video_cfg.get("resolution", [1280, 720])
        self.target_size = (int(res[0]), int(res[1]))
        self.codec = self.video_cfg.get("codec", "libx264")
        self.audio_codec = self.video_cfg.get("audio_codec", "aac")
        self.bitrate = self.video_cfg.get("bitrate", None)
        self.filename_pattern = self.video_cfg.get("filename_pattern", "final_{timestamp}.mp4")

    # 2A) Assemble a video by matching PNGs in image_sources with WAVs in audio_sources
    def create_video_from_directory(self, root_dir: str | Path, output_path: Optional[str | Path] = None) -> Path:
        """
        Looks under:
          root_dir/image_sources/*.png
          root_dir/audio_sources/*.wav
        Pairs files with the same stem and concatenates into one video.
        """
        root_dir = Path(root_dir)
        images_dir = root_dir / "image_sources"
        audios_dir = root_dir / "audio_sources"
        finals_dir = root_dir / "final_video"
        finals_dir.mkdir(parents=True, exist_ok=True)

        # Build image map, sorted A–Z by filename
        image_files = sorted(images_dir.glob("*.png"), key=lambda p: p.name.lower())
        image_map = {p.stem: p for p in image_files}

        # Build audio groups keyed by base stem, so that
        #   chapter1.wav, chapter1-01.wav, chapter1-02.wav
        # all map under the base key "chapter1".
        audio_groups = {}
        for p in sorted(audios_dir.glob("*.wav"), key=lambda p: p.name.lower()):
            stem = p.stem
            base = stem
            idx = 0
            if "-" in stem:
                base_candidate, suffix = stem.rsplit("-", 1)
                if suffix.isdigit():
                    base = base_candidate
                    idx = int(suffix)

            audio_groups.setdefault(base, []).append((idx, p))

        # Only keep stems that have both an image and at least one audio file
        common_stems = sorted(
            set(image_map.keys()) & set(audio_groups.keys()),
            key=lambda s: s.lower(),
        )

        if not common_stems:
            raise FileNotFoundError(
                f"No matching (png,wav) pairs found in {images_dir} and {audios_dir}."
            )

        logging.info("Found %d matching image/audio base names", len(common_stems))

        clips = []
        for stem in common_stems:
            img_path = image_map[stem]
            # Sort audio chunks by their numeric index so playback order is deterministic
            chunks = sorted(audio_groups[stem], key=lambda t: t[0])
            logging.info("Processing base '%s': image=%s, audio_count=%d", stem, img_path.name, len(chunks))

            for idx, wav_path in chunks:
                logging.info("   Assembling clip: image=%s, audio=%s", img_path.name, wav_path.name)

                audio_clip = AudioFileClip(str(wav_path))
                lead_in = 1.0  # seconds of silent lead before audio starts

                # Total video duration = silent lead + audio length
                total_duration = audio_clip.duration + lead_in

                # Still image lasts for the entire (lead + audio) duration
                img_clip = _letterbox_image_clip(img_path, self.target_size).with_duration(total_duration)

                # Shift audio so it starts at t = lead_in
                shifted_audio = audio_clip.with_start(lead_in)

                # CompositeAudioClip returns silence before `lead_in`, then the audio
                composite_audio = CompositeAudioClip([shifted_audio])

                # Attach audio to the image clip
                clip = img_clip.with_audio(composite_audio)

                clips.append(clip)

        logging.info("Assembling final video...")
        final = concatenate_videoclips(clips, method="compose")

        # Resolve output path
        if output_path is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.filename_pattern.format(timestamp=timestamp)
            output_path = finals_dir / filename
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        logging.info("Writing final video to %s", output_path)
        write_kwargs = {"codec": self.codec, "audio_codec": self.audio_codec, "fps": self.fps}
        if self.bitrate:
            write_kwargs["bitrate"] = self.bitrate

        logging.info("Video write parameters: %s", write_kwargs)
        final.write_videofile(str(output_path), **write_kwargs)

        # Clean up
        for c in clips:
            c.close()
        final.close()
        return output_path