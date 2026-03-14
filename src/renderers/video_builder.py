"""
video_builder.py — FFmpeg-powered video rendering pipeline. (Phase 3)

Takes generated scripts and produces TikTok-ready 9:16 vertical videos.

Content mode (solid-color background):
  - 5 color themes (warm, cool, energetic, calm, default) selected via visual_hints
  - Text shadow/outline for readability
  - Crossfade transitions between sections (0.5s)
  - Different font sizes per section (hook largest, body medium, CTA emphasis)
  - Optional key_overlay_text from visual_hints displayed as smaller subtitle
  - Optional TTS narration via ElevenLabs (audio drives video timing)

Product mode (image/clip backgrounds):
  - Ken Burns zoom/pan animation on static images (FREE — no Muapi needed)
  - Variable-pace image timing (first images longer, last images rapid cuts)
  - TikTok safe zone text positioning (avoids UI overlay dead zones)
  - Timed text overlays: hook at top, body center, price badge upper-right, CTA lower
  - Muapi video clips used as backgrounds when available (premium upgrade)

Requires FFmpeg installed and on PATH:
    winget install --id Gyan.FFmpeg -e

Usage:
    python -m src.renderers.video_builder
"""

import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import ffmpeg
from rich import print as rprint
from rich.table import Table

from src.utils.config import (
    DATA_SCRIPTS_DIR,
    FONT_PATH,
    MUSIC_DIR,
    OUTPUT_CLIPS_DIR,
    OUTPUT_DIR,
    OUTPUT_IMAGES_DIR,
    load_pipeline_config,
)
from src.utils.data_io import load_latest

# ── Product video styles (route to render_product_video) ──
PRODUCT_STYLES = {"product_showcase", "ugc_showcase", "comparison"}

# ── All recognized rendering formats ──
ALL_RENDER_FORMATS = {
    "product_showcase", "ugc_showcase", "comparison",
    "screen_recording", "ugc_avatar", "standard",
}

# ── Video constants ──
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# ── Typography ──
HOOK_FONT_SIZE = 72
BODY_FONT_SIZE = 48
CTA_FONT_SIZE = 64
OVERLAY_FONT_SIZE = 36

# ── Timing ──
HOOK_DURATION = 3
CTA_DURATION = 3
MIN_BODY_DURATION = 4
FADE_DURATION = 0.5

# ── Text wrapping (characters per line) ──
HOOK_WRAP_WIDTH = 20
BODY_WRAP_WIDTH = 30
CTA_WRAP_WIDTH = 25

# ── TikTok Safe Zones (pixels from edge) ──
SAFE_TOP = 150      # Below username / sound label
SAFE_BOTTOM = 480   # Above caption + TikTok Shop product card
SAFE_LEFT = 40      # Small left margin
SAFE_RIGHT = 80     # Away from like/comment/share icons

# ── Derived text positions for product videos ──
HOOK_TEXT_Y = SAFE_TOP + 40     # Hook near top of safe zone
BODY_TEXT_Y = 500               # Body text in upper-center
PRICE_BADGE_X = VIDEO_WIDTH - SAFE_RIGHT - 200  # Upper right
PRICE_BADGE_Y = SAFE_TOP + 20
CTA_TEXT_Y = VIDEO_HEIGHT - SAFE_BOTTOM - 100   # Just above bottom dead zone

# ── Product video crossfade (shorter = faster pacing) ──
PRODUCT_CROSSFADE = 0.3

# ── Color themes: (bg_color, text_color, accent_color) ──
# Each theme is a tuple of hex colors for background, main text, and CTA/accent text.
COLOR_THEMES = {
    "warm":      {"bg": "0x2d1b2e", "text": "0xfff0e6", "accent": "0xf5a623"},
    "cool":      {"bg": "0x0f1a2e", "text": "0xe0f0ff", "accent": "0x4fc3f7"},
    "energetic": {"bg": "0x1a0a2e", "text": "0xffffff", "accent": "0xff6b6b"},
    "calm":      {"bg": "0x0f2e1a", "text": "0xe6fff0", "accent": "0x81c784"},
    "default":   {"bg": "0x1a1a2e", "text": "0xffffff", "accent": "0xffd700"},
}

# ── Color grading per mood (FFmpeg eq filter values) ──
COLOR_GRADES = {
    "warm":      {"brightness": 0.02, "contrast": 1.05, "saturation": 1.15, "gamma_r": 1.05, "gamma_b": 0.95},
    "cool":      {"brightness": 0.0,  "contrast": 1.05, "saturation": 1.1,  "gamma_r": 0.95, "gamma_b": 1.08},
    "energetic": {"brightness": 0.03, "contrast": 1.12, "saturation": 1.25, "gamma_r": 1.0,  "gamma_b": 1.0},
    "calm":      {"brightness": -0.02,"contrast": 0.95, "saturation": 0.9,  "gamma_r": 1.0,  "gamma_b": 1.0},
    "default":   {"brightness": 0.0,  "contrast": 1.0,  "saturation": 1.0,  "gamma_r": 1.0,  "gamma_b": 1.0},
}

# ── Mood-based transition types for xfade ──
MOOD_TRANSITIONS = {
    "warm": "dissolve", "cool": "wiperight", "energetic": "slideright",
    "calm": "fade", "default": "fade",
}

# ── Text border/stroke for readability ──
TEXT_BORDER_WIDTH = 2
TEXT_BORDER_COLOR = "white@0.8"
PRODUCT_TEXT_BORDER_WIDTH = 3
PRODUCT_TEXT_BORDER_COLOR = "white@0.85"

# ── Vignette angles ──
VIGNETTE_ANGLE_CONTENT = "PI/5"
VIGNETTE_ANGLE_PRODUCT = "PI/4"


_analysis_overrides_cache: dict | None = None


def _get_analysis_overrides() -> dict:
    """Load render overrides from the feedback loop (comparison report + Style Bible).

    Returns cached overrides dict, or empty dict if no analysis data exists.
    This closes the feedback loop: analyze → compare → override renderer defaults.
    """
    global _analysis_overrides_cache
    if _analysis_overrides_cache is None:
        try:
            from src.analyzers.style_overrides import get_render_overrides
            overrides = get_render_overrides()
            if overrides.get("source") == "none":
                overrides = {}
        except ImportError:
            overrides = {}
        _analysis_overrides_cache = overrides
    return _analysis_overrides_cache


def get_theme(script: dict) -> dict:
    """Pick a color theme based on analysis overrides, visual_hints.mood, or source_type.

    Priority:
      1. Colors from comparison report / Style Bible (feedback loop)
      2. visual_hints.mood from the script
      3. source_type mapping
      4. 'default' theme
    """
    # Check if the feedback loop has color recommendations
    overrides = _get_analysis_overrides()
    override_colors = overrides.get("colors", {})

    hints = script.get("visual_hints", {})
    if isinstance(hints, dict):
        mood = hints.get("mood", "")
        if mood in COLOR_THEMES:
            theme = dict(COLOR_THEMES[mood])  # copy so we don't mutate
            # Apply analysis color overrides on top of mood theme
            if override_colors.get("bg"):
                theme["bg"] = override_colors["bg"]
            if override_colors.get("text"):
                theme["text"] = override_colors["text"]
            if override_colors.get("accent"):
                theme["accent"] = override_colors["accent"]
            return theme

    # Fallback: map source_type to a theme
    source_type = script.get("source_type", "")
    source_map = {
        "trending": "energetic",
        "ad": "warm",
        "mixed": "cool",
    }
    fallback_mood = source_map.get(source_type, "default")
    theme = dict(COLOR_THEMES[fallback_mood])

    # Apply analysis color overrides
    if override_colors.get("bg"):
        theme["bg"] = override_colors["bg"]
    if override_colors.get("text"):
        theme["text"] = override_colors["text"]
    if override_colors.get("accent"):
        theme["accent"] = override_colors["accent"]

    return theme


def get_music_track(script: dict) -> Path | None:
    """Pick a background music track based on the script's mood.

    Returns the path to an MP3 file in assets/music/, or None if
    music is disabled or the track doesn't exist.
    """
    config = load_pipeline_config()
    music_config = config.get("music", {})

    if not music_config.get("enabled", False):
        return None

    # Get mood from visual_hints
    hints = script.get("visual_hints", {})
    mood = hints.get("mood", "default") if isinstance(hints, dict) else "default"

    # Look up the track filename
    mood_map = music_config.get("mood_map", {})
    track_name = mood_map.get(mood, mood_map.get("default", "calm.mp3"))
    track_path = MUSIC_DIR / track_name

    if not track_path.exists():
        return None

    return track_path


def _get_mood(script: dict) -> str:
    """Extract mood string from a script's visual_hints."""
    hints = script.get("visual_hints", {})
    if isinstance(hints, dict):
        return hints.get("mood", "default")
    return "default"


def _apply_color_grade(stream: ffmpeg.Stream, mood: str) -> ffmpeg.Stream:
    """Apply color grading via FFmpeg eq filter based on mood."""
    grade = COLOR_GRADES.get(mood, COLOR_GRADES["default"])
    # Skip if all values are identity (no-op)
    if (grade["brightness"] == 0.0 and grade["contrast"] == 1.0
            and grade["saturation"] == 1.0 and grade["gamma_r"] == 1.0
            and grade["gamma_b"] == 1.0):
        return stream
    return stream.filter(
        "eq",
        brightness=grade["brightness"],
        contrast=grade["contrast"],
        saturation=grade["saturation"],
        gamma_r=grade["gamma_r"],
        gamma_b=grade["gamma_b"],
    )


def _apply_vignette(stream: ffmpeg.Stream, is_product: bool = False) -> ffmpeg.Stream:
    """Apply vignette overlay. Product videos get a slightly stronger effect."""
    angle = VIGNETTE_ANGLE_PRODUCT if is_product else VIGNETTE_ANGLE_CONTENT
    return stream.filter("vignette", angle=angle)


def _get_transition(script: dict) -> str:
    """Pick xfade transition type based on mood."""
    mood = _get_mood(script)
    return MOOD_TRANSITIONS.get(mood, "fade")


def _get_ken_burns_speeds(num_images: int, mood: str) -> list[float]:
    """Return per-image speed factors for Ken Burns animation.

    First images are slower (0.7x), last images faster (1.3x).
    Mood multiplier: calm=0.7, energetic=1.3, default=1.0.
    """
    if num_images <= 0:
        return []
    if num_images == 1:
        mood_mult = {"calm": 0.7, "energetic": 1.3, "warm": 1.0, "cool": 1.0}.get(mood, 1.0)
        return [1.0 * mood_mult]

    mood_mult = {"calm": 0.7, "energetic": 1.3, "warm": 1.0, "cool": 1.0}.get(mood, 1.0)
    speeds = []
    for i in range(num_images):
        # Linear interpolation: first image 0.7, last image 1.3
        position_factor = 0.7 + (0.6 * i / (num_images - 1))
        speeds.append(position_factor * mood_mult)
    return speeds


def check_ffmpeg() -> bool:
    """Check if FFmpeg is installed and on PATH."""
    if shutil.which("ffmpeg"):
        return True
    rprint("[red]FFmpeg not found on PATH.[/red]")
    rprint("[yellow]Install with:[/yellow]  winget install --id Gyan.FFmpeg -e")
    rprint("[yellow]Then restart your terminal.[/yellow]")
    return False


def escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg's drawtext filter."""
    # Order matters: backslash first, then others
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\u2019")  # Replace apostrophe with right single quote
    return text


def wrap_text(text: str, wrap_width: int) -> str:
    """Word-wrap text and join with newlines for drawtext."""
    if not text:
        return ""
    lines = textwrap.wrap(text, width=wrap_width)
    return "\n".join(lines)


def calculate_timing(script: dict) -> dict:
    """Calculate section durations from a script's estimated_duration_sec.

    Applies timing overrides from the feedback loop (comparison report)
    if available — e.g., if analysis says target 60-75s, we stretch
    the body to reach that range.

    Returns dict with hook_duration, body_duration, cta_duration, total_duration.
    """
    overrides = _get_analysis_overrides()
    timing_ov = overrides.get("timing", {})

    # Use override hook duration if available
    hook_dur = timing_ov.get("target_hook_duration", HOOK_DURATION)
    cta_dur = CTA_DURATION

    # Calculate base total from script estimate
    base_total = script.get("estimated_duration_sec", hook_dur + MIN_BODY_DURATION + cta_dur)

    # Apply target duration from comparison data (stretch video to match winners)
    target_min = timing_ov.get("target_min_duration", 0)
    if target_min > 0 and base_total < target_min:
        # Stretch body to reach the target minimum duration
        total = target_min
    else:
        total = base_total

    body_dur = max(total - hook_dur - cta_dur, MIN_BODY_DURATION)
    actual_total = hook_dur + body_dur + cta_dur

    return {
        "hook_duration": hook_dur,
        "body_duration": body_dur,
        "cta_duration": cta_dur,
        "total_duration": actual_total,
    }


def build_section(
    text: str,
    font_size: int,
    wrap_width: int,
    duration: float,
    font_path: str,
    bg_color: str = "0x1a1a2e",
    text_color: str = "white",
    overlay_text: str = "",
    overlay_color: str = "0xffd700",
    text_fade_in: float = 0.0,
) -> ffmpeg.Stream:
    """Generate a single video section: color background + centered drawtext with shadow.

    Args:
        text: Main text content for the section
        font_size: Font size for the main text
        wrap_width: Character wrap width for the main text
        duration: Section duration in seconds
        font_path: Path to the font file
        bg_color: Background color (hex)
        text_color: Main text color (hex or name)
        overlay_text: Optional smaller overlay text (e.g., a stat or key phrase)
        overlay_color: Color for the overlay text
        text_fade_in: Duration in seconds for text fade-in (0.0 = no fade)
    """
    wrapped = wrap_text(text, wrap_width)
    escaped = escape_drawtext(wrapped)

    stream = ffmpeg.input(
        f"color=c={bg_color}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={duration}:r={FPS}",
        f="lavfi",
    )

    # Build alpha expression for text fade-in
    alpha_expr = f"if(lt(t,{text_fade_in}),t/{text_fade_in},1)" if text_fade_in > 0 else "1"
    shadow_alpha = f"if(lt(t,{text_fade_in}),0.6*t/{text_fade_in},0.6)" if text_fade_in > 0 else "0.6"

    # Shadow layer (offset by 2px) for readability
    shadow_kwargs = dict(
        fontfile=font_path,
        text=escaped,
        fontsize=font_size,
        fontcolor="black@0.6",
        x="(w-text_w)/2+3",
        y="(h-text_h)/2+3",
    )
    if text_fade_in > 0:
        shadow_kwargs["alpha"] = shadow_alpha
    stream = stream.drawtext(**shadow_kwargs)

    # Main text layer with border for readability
    main_kwargs = dict(
        fontfile=font_path,
        text=escaped,
        fontsize=font_size,
        fontcolor=text_color,
        x="(w-text_w)/2",
        y="(h-text_h)/2",
        borderw=TEXT_BORDER_WIDTH,
        bordercolor=TEXT_BORDER_COLOR,
    )
    if text_fade_in > 0:
        main_kwargs["alpha"] = alpha_expr
    stream = stream.drawtext(**main_kwargs)

    # Optional overlay text (smaller, below main text)
    if overlay_text:
        overlay_escaped = escape_drawtext(overlay_text)
        overlay_kwargs = dict(
            fontfile=font_path,
            text=overlay_escaped,
            fontsize=OVERLAY_FONT_SIZE,
            fontcolor=overlay_color,
            x="(w-text_w)/2",
            y="(h*3/4)",
        )
        if text_fade_in > 0:
            overlay_kwargs["alpha"] = alpha_expr
        stream = stream.drawtext(**overlay_kwargs)

    return stream


def _merge_section_audio(audio_paths: dict[str, Path], output_path: Path) -> Path | None:
    """Concatenate hook + body + CTA audio files into one MP3.

    Uses FFmpeg's concat demuxer to join the three section audio files
    in order. Returns the merged audio path, or None on failure.
    """
    # Write a concat list file for FFmpeg
    list_path = output_path.with_suffix(".txt")
    with open(list_path, "w") as f:
        for section in ("hook", "body", "cta"):
            if section in audio_paths:
                # Use forward slashes for FFmpeg on Windows
                f.write(f"file '{audio_paths[section].as_posix()}'\n")

    merged = output_path.with_name(output_path.stem + "_audio.mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c", "copy", str(merged)],
            capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    finally:
        list_path.unlink(missing_ok=True)

    return merged if merged.exists() else None


def _mix_background_music(video_path: Path, music_path: Path, volume: float = 0.15) -> bool:
    """Mix background music into a video at low volume.

    If the video already has audio (TTS narration), the music is mixed
    underneath at the specified volume. If the video is silent, the music
    becomes the only audio track.

    Operates in-place: replaces the video file with the mixed version.
    Returns True on success.
    """
    mixed = video_path.with_name(video_path.stem + "_mixed.mp4")

    try:
        # Probe if video already has an audio stream
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        has_audio = "audio" in probe.stdout

        if has_audio:
            # Mix music under existing audio: video audio at full volume, music at low volume
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", str(video_path),
                 "-stream_loop", "-1", "-i", str(music_path),
                 "-filter_complex",
                 f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=shortest",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                 str(mixed)],
                capture_output=True, timeout=60,
            )
        else:
            # No existing audio — add music as the only audio track
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", str(video_path),
                 "-stream_loop", "-1", "-i", str(music_path),
                 "-filter_complex", f"[1:a]volume={volume}[music]",
                 "-map", "0:v", "-map", "[music]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                 "-shortest",
                 str(mixed)],
                capture_output=True, timeout=60,
            )

        if mixed.exists() and mixed.stat().st_size > 0:
            video_path.unlink()
            mixed.rename(video_path)
            return True
        return False

    except (subprocess.TimeoutExpired, FileNotFoundError):
        mixed.unlink(missing_ok=True)
        return False


def render_video(
    script: dict,
    output_path: Path,
    font_path: Path,
    audio_data: dict | None = None,
) -> Path:
    """Render a single script to an MP4 video file.

    Builds 3 sections (hook, body, CTA) with themed colors and text shadows,
    applies crossfade transitions, and encodes to H.264.

    If audio_data is provided (from TTS), section durations are driven by
    the audio length so the narration and text stay perfectly in sync.
    The audio is then merged into the final video.
    """
    # Use TTS durations if available, otherwise fall back to word-count estimate
    if audio_data and "durations" in audio_data:
        durations = audio_data["durations"]
        timing = {
            "hook_duration": durations.get("hook", HOOK_DURATION),
            "body_duration": durations.get("body", MIN_BODY_DURATION),
            "cta_duration": durations.get("cta", CTA_DURATION),
        }
        # Add a small buffer so text doesn't vanish before audio finishes
        for key in timing:
            timing[key] = timing[key] + 0.3
        timing["total_duration"] = sum(v for k, v in timing.items() if k != "total_duration")
    else:
        timing = calculate_timing(script)

    font_str = font_path.as_posix()  # Forward slashes for FFmpeg on Windows
    theme = get_theme(script)
    mood = _get_mood(script)
    xfade_type = _get_transition(script)

    # Extract overlay text from visual_hints
    hints = script.get("visual_hints", {})
    overlay_text = ""
    if isinstance(hints, dict):
        overlay_text = hints.get("key_overlay_text", "")

    # Add fade duration padding to each section so crossfade doesn't cut content
    fade = FADE_DURATION

    hook_stream = build_section(
        script.get("hook", ""),
        HOOK_FONT_SIZE, HOOK_WRAP_WIDTH,
        timing["hook_duration"] + fade,
        font_str,
        bg_color=theme["bg"],
        text_color=theme["text"],
        text_fade_in=0.5,
    )
    body_stream = build_section(
        script.get("body", ""),
        BODY_FONT_SIZE, BODY_WRAP_WIDTH,
        timing["body_duration"] + fade,
        font_str,
        bg_color=theme["bg"],
        text_color=theme["text"],
        overlay_text=overlay_text,
        overlay_color=theme["accent"],
        text_fade_in=0.3,
    )
    cta_stream = build_section(
        script.get("cta", ""),
        CTA_FONT_SIZE, CTA_WRAP_WIDTH,
        timing["cta_duration"],
        font_str,
        bg_color=theme["bg"],
        text_color=theme["accent"],  # CTA uses accent color for emphasis
        text_fade_in=0.4,
    )

    # Concatenate with crossfade transitions using xfade filter
    # xfade between hook→body, then between that result→cta
    combined = (
        ffmpeg
        .filter([hook_stream, body_stream], "xfade",
                transition=xfade_type, duration=fade,
                offset=timing["hook_duration"])
        .filter("xfade",
                **{"0": cta_stream},
                transition=xfade_type, duration=fade,
                offset=timing["hook_duration"] + timing["body_duration"])
    )

    # Apply color grading and vignette
    combined = _apply_color_grade(combined, mood)
    combined = _apply_vignette(combined, is_product=False)

    # If we have TTS audio, merge the section audio files and mux with video
    if audio_data and any(k in audio_data for k in ("hook", "body", "cta")):
        merged_audio = _merge_section_audio(audio_data, output_path)
        if merged_audio:
            # Render video without audio first to a temp file
            video_only = output_path.with_name(output_path.stem + "_videoonly.mp4")
            out = ffmpeg.output(combined, str(video_only), vcodec="libx264", pix_fmt="yuv420p")
            out = out.overwrite_output()
            try:
                out.run(quiet=True)
            except ffmpeg.Error:
                # Fallback to simple concat
                rprint("    [dim]xfade unavailable, using simple concat[/dim]")
                _render_simple_concat(script, video_only, font_str, theme, timing, overlay_text)

            # Mux video + audio together
            try:
                subprocess.run(
                    ["ffmpeg", "-y",
                     "-i", str(video_only), "-i", str(merged_audio),
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                     "-shortest", str(output_path)],
                    capture_output=True, timeout=60,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                rprint("    [yellow]Audio mux failed, keeping video-only[/yellow]")
                video_only.rename(output_path)
            finally:
                video_only.unlink(missing_ok=True)
                merged_audio.unlink(missing_ok=True)

            return output_path

    # No audio — render video only (original behavior)
    out = ffmpeg.output(combined, str(output_path), vcodec="libx264", pix_fmt="yuv420p")
    out = out.overwrite_output()

    try:
        out.run(quiet=True)
    except ffmpeg.Error:
        # Fallback: if xfade fails (older FFmpeg), use simple concat without transitions
        rprint("    [dim]xfade unavailable, using simple concat[/dim]")
        _render_simple_concat(script, output_path, font_str, theme, timing, overlay_text)

    return output_path


def _render_simple_concat(
    script: dict,
    output_path: Path,
    font_str: str,
    theme: dict,
    timing: dict,
    overlay_text: str,
) -> None:
    """Fallback renderer using simple concat instead of xfade transitions."""
    mood = _get_mood(script)

    hook_simple = build_section(
        script.get("hook", ""),
        HOOK_FONT_SIZE, HOOK_WRAP_WIDTH,
        timing["hook_duration"], font_str,
        bg_color=theme["bg"], text_color=theme["text"],
        text_fade_in=0.5,
    )
    body_simple = build_section(
        script.get("body", ""),
        BODY_FONT_SIZE, BODY_WRAP_WIDTH,
        timing["body_duration"], font_str,
        bg_color=theme["bg"], text_color=theme["text"],
        overlay_text=overlay_text, overlay_color=theme["accent"],
        text_fade_in=0.3,
    )
    cta_simple = build_section(
        script.get("cta", ""),
        CTA_FONT_SIZE, CTA_WRAP_WIDTH,
        timing["cta_duration"], font_str,
        bg_color=theme["bg"], text_color=theme["accent"],
        text_fade_in=0.4,
    )
    joined = ffmpeg.concat(hook_simple, body_simple, cta_simple, v=1, a=0)
    # Apply color grading and vignette
    joined = _apply_color_grade(joined, mood)
    joined = _apply_vignette(joined, is_product=False)
    out = ffmpeg.output(joined, str(output_path), vcodec="libx264", pix_fmt="yuv420p")
    out = out.overwrite_output()
    out.run(quiet=True)


def _get_script_media(script_id: str, product_id: str = "") -> tuple[list[Path], list[Path]]:
    """Find video clips and/or scene images for a script.

    Returns (clips, images) — clips take priority, images are fallback.
    Falls back to Kalodata product images if no generated media exists.
    """
    short_id = script_id[:8]
    clips = []
    images = []

    clips_dir = OUTPUT_CLIPS_DIR / short_id
    if clips_dir.exists():
        clips = sorted(clips_dir.glob("*.mp4"))

    images_dir = OUTPUT_IMAGES_DIR / short_id
    if images_dir.exists():
        images = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))

    # Fallback: use Kalodata product images if no generated media found
    if not images and product_id:
        from src.utils.config import PRODUCT_IMAGES_DIR
        product_images = sorted(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.jpg"))
        product_images += sorted(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.png"))
        images = product_images[:5]

    # Log what we found (helps debug the "solid rectangle" problem)
    rprint(f"    [dim]Media lookup for {short_id}:[/dim]")
    rprint(f"      [dim]Clips dir:  {clips_dir} ({'exists' if clips_dir.exists() else 'missing'})[/dim]")
    rprint(f"      [dim]Images dir: {images_dir} ({'exists' if images_dir.exists() else 'missing'})[/dim]")
    if product_id:
        rprint(f"      [dim]Product ID: {product_id}[/dim]")
    if clips:
        rprint(f"      [green]Found {len(clips)} clip(s)[/green]")
    if images:
        rprint(f"      [green]Found {len(images)} image(s)[/green]")
    if not clips and not images:
        rprint("      [yellow]No media found — will fall back to solid color[/yellow]")

    return clips, images


def _apply_ken_burns(
    image_path: Path, duration: float, effect: str = "zoom_in",
    speed_factor: float = 1.0,
) -> ffmpeg.Stream:
    """Apply Ken Burns zoom/pan to a static image, producing an animated video stream.

    Scales the image up for headroom, then uses FFmpeg's zoompan filter
    to create smooth camera motion over the still frame.

    Args:
        image_path: Path to the source image file.
        duration: Output duration in seconds.
        effect: One of zoom_in, zoom_out, pan_left, pan_right, pan_up.
        speed_factor: Multiplier for animation speed (1.0 = default).

    Returns:
        An ffmpeg.Stream ready for concatenation or overlay.
    """
    num_frames = int(duration * FPS)
    increment = (0.3 * speed_factor) / max(num_frames, 1)

    # Scale image large enough for pan/zoom headroom (1.5x output dimensions)
    stream = ffmpeg.input(str(image_path)).filter(
        "scale", 1620, 2880, force_original_aspect_ratio="increase",
    )

    effects_map = {
        "zoom_in": {
            "z": f"min(zoom+{increment:.6f},1.3)",
            "x": "iw/2-(iw/zoom/2)",
            "y": "ih/2-(ih/zoom/2)",
        },
        "zoom_out": {
            "z": f"if(eq(on,1),1.3,max(zoom-{increment:.6f},1.0))",
            "x": "iw/2-(iw/zoom/2)",
            "y": "ih/2-(ih/zoom/2)",
        },
        "pan_left": {
            "z": "1.3",
            "x": f"(iw-iw/zoom)*(1-on/{num_frames})",
            "y": "(ih-ih/zoom)/2",
        },
        "pan_right": {
            "z": "1.3",
            "x": f"(iw-iw/zoom)*on/{num_frames}",
            "y": "(ih-ih/zoom)/2",
        },
        "pan_up": {
            "z": "1.3",
            "x": "(iw-iw/zoom)/2",
            "y": f"(ih-ih/zoom)*(1-on/{num_frames})",
        },
    }

    params = effects_map.get(effect, effects_map["zoom_in"])

    stream = stream.filter(
        "zoompan",
        z=params["z"], x=params["x"], y=params["y"],
        d=num_frames, s=f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}", fps=FPS,
    )
    return stream.filter("setsar", "1")


def _get_ken_burns_sequence(num_images: int) -> list[str]:
    """Return alternating Ken Burns effects so consecutive images use different motion."""
    effects = ["zoom_in", "pan_left", "zoom_out", "pan_right", "pan_up"]
    return [effects[i % len(effects)] for i in range(num_images)]


def _calculate_image_timing(num_images: int, total_duration: float) -> list[dict]:
    """Distribute images across video with variable pacing.

    First images get more time (3-5s for hooks), last images get
    rapid cuts (1-2s for urgency). Matches TikTok pacing research.

    Returns:
        List of dicts with start, end, duration for each image.
    """
    if num_images <= 0:
        return []
    if num_images == 1:
        return [{"start": 0.0, "end": total_duration, "duration": total_duration}]

    # Weight distribution: earlier images get more screen time
    weights = []
    for i in range(num_images):
        w = 1.5 - (1.0 * i / (num_images - 1))
        weights.append(max(w, 0.5))

    total_weight = sum(weights)
    durations = [(w / total_weight) * total_duration for w in weights]

    # Clamp minimum 1.0s per image, then re-normalize to fit total
    durations = [max(d, 1.0) for d in durations]
    scale = total_duration / sum(durations)
    durations = [d * scale for d in durations]

    # Build timing list
    timings = []
    start = 0.0
    for d in durations:
        timings.append({"start": start, "end": start + d, "duration": d})
        start += d

    # Snap last image end to exact total
    timings[-1]["end"] = total_duration
    timings[-1]["duration"] = total_duration - timings[-1]["start"]

    return timings


def _mux_product_audio(audio_data: dict | None, output_path: Path) -> None:
    """Mux TTS audio into a rendered product video, if audio data is available."""
    if not audio_data or not any(k in audio_data for k in ("hook", "body", "cta")):
        return

    merged_audio = _merge_section_audio(audio_data, output_path)
    if not merged_audio:
        return

    video_only = output_path.with_name(output_path.stem + "_vo.mp4")
    output_path.rename(video_only)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_only), "-i", str(merged_audio),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
             "-shortest", str(output_path)],
            capture_output=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        video_only.rename(output_path)
    finally:
        video_only.unlink(missing_ok=True)
        merged_audio.unlink(missing_ok=True)


def render_product_video(
    script: dict,
    output_path: Path,
    font_path: Path,
    audio_data: dict | None = None,
) -> Path:
    """Render a product video by compositing video clips (or static images) with text overlays.

    Takes Higgsfield video clips or Nano Banana Pro images as background,
    overlays precise text (hook at top, price badge in corner, CTA at bottom),
    and mixes TTS audio.
    """
    script_id = script.get("script_id", "unknown")
    product_id = script.get("product_id", "")
    clips, images = _get_script_media(script_id, product_id)

    font_str = font_path.as_posix()
    theme = get_theme(script)
    hints = script.get("visual_hints", {}) if isinstance(script.get("visual_hints"), dict) else {}

    # Determine timing
    if audio_data and "durations" in audio_data:
        durations = audio_data["durations"]
        timing = {
            "hook_duration": durations.get("hook", HOOK_DURATION) + 0.3,
            "body_duration": durations.get("body", MIN_BODY_DURATION) + 0.3,
            "cta_duration": durations.get("cta", CTA_DURATION) + 0.3,
        }
        timing["total_duration"] = sum(timing.values())
    else:
        timing = calculate_timing(script)

    # If we have video clips, use them as backgrounds
    if clips:
        return _render_with_clip_backgrounds(
            script, clips, output_path, font_str, theme, timing, hints, audio_data,
        )

    # If we have images, use them as static backgrounds
    if images:
        return _render_with_image_backgrounds(
            script, images, output_path, font_str, theme, timing, hints, audio_data,
        )

    # Fallback: render as standard content video
    rprint("    [yellow]No product media found — falling back to standard render[/yellow]")
    return render_video(script, output_path, font_path, audio_data)


def _render_with_image_backgrounds(
    script: dict,
    images: list[Path],
    output_path: Path,
    font_str: str,
    theme: dict,
    timing: dict,
    hints: dict,
    audio_data: dict | None,
) -> Path:
    """Render product video with Ken Burns animated images and timed text overlays.

    Instead of 3 separate sections, produces one continuous video: Ken Burns
    motion on each image, crossfaded together, with text that appears/disappears
    on a timed basis over the stream. Matches real TikTok product video pacing.
    """
    total_duration = timing["total_duration"]

    # Calculate per-image timing with variable pacing (first images longer)
    mood = _get_mood(script)
    image_timings = _calculate_image_timing(len(images), total_duration)
    effects = _get_ken_burns_sequence(len(images))
    kb_speeds = _get_ken_burns_speeds(len(images), mood)
    xfade_type = _get_transition(script)

    # Build Ken Burns streams with crossfade padding
    fade = PRODUCT_CROSSFADE
    streams = []
    for i, (img, img_t, effect, speed) in enumerate(
        zip(images, image_timings, effects, kb_speeds)
    ):
        pad = fade if i < len(images) - 1 else 0
        if img.exists():
            stream = _apply_ken_burns(img, img_t["duration"] + pad, effect,
                                       speed_factor=speed)
        else:
            # Fallback: solid color if image missing
            stream = ffmpeg.input(
                f"color=c={theme['bg']}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}"
                f":d={img_t['duration'] + pad}:r={FPS}",
                f="lavfi",
            )
        streams.append(stream)

    # Combine streams with crossfade transitions
    if len(streams) == 1:
        combined = streams[0]
    else:
        combined = streams[0]
        offset = image_timings[0]["duration"]
        for i in range(1, len(streams)):
            combined = ffmpeg.filter(
                [combined, streams[i]], "xfade",
                transition=xfade_type, duration=fade, offset=offset,
            )
            offset += image_timings[i]["duration"]

    # ── Timed text overlays in TikTok safe zones ──
    hook_end = timing["hook_duration"]
    body_start = hook_end
    body_end = body_start + timing["body_duration"]
    cta_start = body_end

    # Alpha expressions for text fade-in (relative to each section's start)
    hook_alpha = "if(lt(t,0.5),t/0.5,1)"
    body_alpha = f"if(lt(t-{body_start},0.3),(t-{body_start})/0.3,1)"
    cta_alpha = f"if(lt(t-{cta_start},0.4),(t-{cta_start})/0.4,1)"

    # Hook text — top of safe zone
    hook_text = escape_drawtext(wrap_text(script.get("hook", ""), HOOK_WRAP_WIDTH))
    if hook_text:
        combined = combined.drawtext(
            fontfile=font_str, text=hook_text, fontsize=HOOK_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+3", y=f"{HOOK_TEXT_Y}+3",
            enable=f"lt(t,{hook_end})",
            alpha=hook_alpha,
        )
        combined = combined.drawtext(
            fontfile=font_str, text=hook_text, fontsize=HOOK_FONT_SIZE,
            fontcolor=theme["text"], x="(w-text_w)/2", y=str(HOOK_TEXT_Y),
            enable=f"lt(t,{hook_end})",
            alpha=hook_alpha,
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # Body text — center of safe zone
    body_text = escape_drawtext(wrap_text(script.get("body", ""), BODY_WRAP_WIDTH))
    if body_text:
        combined = combined.drawtext(
            fontfile=font_str, text=body_text, fontsize=BODY_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+2", y=f"{BODY_TEXT_Y}+2",
            enable=f"between(t,{body_start},{body_end})",
            alpha=body_alpha,
        )
        combined = combined.drawtext(
            fontfile=font_str, text=body_text, fontsize=BODY_FONT_SIZE,
            fontcolor=theme["text"], x="(w-text_w)/2", y=str(BODY_TEXT_Y),
            enable=f"between(t,{body_start},{body_end})",
            alpha=body_alpha,
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # Price badge — upper right corner during body
    price_display = hints.get("price_display", "")
    if price_display:
        price_escaped = escape_drawtext(price_display)
        combined = combined.drawtext(
            fontfile=font_str, text=price_escaped, fontsize=OVERLAY_FONT_SIZE,
            fontcolor=theme["accent"],
            x=str(PRICE_BADGE_X), y=str(PRICE_BADGE_Y),
            box=1, boxcolor="black@0.6", boxborderw=10,
            enable=f"between(t,{body_start},{body_end})",
        )

    # Key overlay text — below body, appears 2s into body section
    overlay_text = hints.get("key_overlay_text", "")
    if overlay_text:
        overlay_escaped = escape_drawtext(overlay_text)
        combined = combined.drawtext(
            fontfile=font_str, text=overlay_escaped, fontsize=OVERLAY_FONT_SIZE,
            fontcolor=theme["accent"], x="(w-text_w)/2", y=str(BODY_TEXT_Y + 200),
            enable=f"between(t,{body_start + 2},{body_end})",
            shadowcolor="black@0.7", shadowx=2, shadowy=2,
        )

    # CTA text — lower safe zone
    cta_text = escape_drawtext(wrap_text(script.get("cta", ""), CTA_WRAP_WIDTH))
    if cta_text:
        combined = combined.drawtext(
            fontfile=font_str, text=cta_text, fontsize=CTA_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+3", y=f"{CTA_TEXT_Y}+3",
            enable=f"gte(t,{cta_start})",
            alpha=cta_alpha,
        )
        combined = combined.drawtext(
            fontfile=font_str, text=cta_text, fontsize=CTA_FONT_SIZE,
            fontcolor=theme["accent"], x="(w-text_w)/2", y=str(CTA_TEXT_Y),
            enable=f"gte(t,{cta_start})",
            alpha=cta_alpha,
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # Apply color grading and vignette
    combined = _apply_color_grade(combined, mood)
    combined = _apply_vignette(combined, is_product=True)

    # Encode final video
    out = ffmpeg.output(
        combined, str(output_path),
        vcodec="libx264", pix_fmt="yuv420p", t=total_duration,
    )
    out.overwrite_output().run(quiet=True)

    # Mux TTS audio
    _mux_product_audio(audio_data, output_path)

    return output_path


def _render_with_clip_backgrounds(
    script: dict,
    clips: list[Path],
    output_path: Path,
    font_str: str,
    theme: dict,
    timing: dict,
    hints: dict,
    audio_data: dict | None,
) -> Path:
    """Render video using Muapi video clips as backgrounds with text overlays."""
    clip_inputs = [ffmpeg.input(str(c)) for c in clips[:5]]

    if len(clip_inputs) == 1:
        stream = clip_inputs[0].filter("scale", VIDEO_WIDTH, VIDEO_HEIGHT,
                                        force_original_aspect_ratio="increase")
        stream = stream.filter("crop", VIDEO_WIDTH, VIDEO_HEIGHT)
    else:
        stream = ffmpeg.concat(*clip_inputs, v=1, a=0)
        stream = stream.filter("scale", VIDEO_WIDTH, VIDEO_HEIGHT,
                                force_original_aspect_ratio="increase")
        stream = stream.filter("crop", VIDEO_WIDTH, VIDEO_HEIGHT)

    mood = _get_mood(script)

    # Overlay hook text — top of safe zone
    hook_text = escape_drawtext(wrap_text(script.get("hook", ""), HOOK_WRAP_WIDTH))
    stream = stream.drawtext(
        fontfile=font_str, text=hook_text, fontsize=HOOK_FONT_SIZE,
        fontcolor=theme["text"], x="(w-text_w)/2", y=str(HOOK_TEXT_Y),
        enable=f"lt(t,{timing['hook_duration']})",
        shadowcolor="black@0.7", shadowx=3, shadowy=3,
        borderw=PRODUCT_TEXT_BORDER_WIDTH,
        bordercolor=PRODUCT_TEXT_BORDER_COLOR,
    )

    # Overlay body text — center of safe zone
    body_start = timing["hook_duration"]
    body_end = body_start + timing["body_duration"]
    body_text = escape_drawtext(wrap_text(script.get("body", ""), BODY_WRAP_WIDTH))
    stream = stream.drawtext(
        fontfile=font_str, text=body_text, fontsize=BODY_FONT_SIZE,
        fontcolor=theme["text"], x="(w-text_w)/2", y=str(BODY_TEXT_Y),
        enable=f"between(t,{body_start},{body_end})",
        shadowcolor="black@0.7", shadowx=2, shadowy=2,
        borderw=PRODUCT_TEXT_BORDER_WIDTH,
        bordercolor=PRODUCT_TEXT_BORDER_COLOR,
    )

    # Overlay CTA text — lower safe zone
    cta_start = body_end
    cta_text = escape_drawtext(wrap_text(script.get("cta", ""), CTA_WRAP_WIDTH))
    stream = stream.drawtext(
        fontfile=font_str, text=cta_text, fontsize=CTA_FONT_SIZE,
        fontcolor=theme["accent"], x="(w-text_w)/2", y=str(CTA_TEXT_Y),
        enable=f"gte(t,{cta_start})",
        shadowcolor="black@0.7", shadowx=3, shadowy=3,
        borderw=PRODUCT_TEXT_BORDER_WIDTH,
        bordercolor=PRODUCT_TEXT_BORDER_COLOR,
    )

    # Price badge — upper right of safe zone
    price_display = hints.get("price_display", "")
    if price_display:
        price_escaped = escape_drawtext(price_display)
        stream = stream.drawtext(
            fontfile=font_str, text=price_escaped, fontsize=OVERLAY_FONT_SIZE,
            fontcolor=theme["accent"],
            x=str(PRICE_BADGE_X), y=str(PRICE_BADGE_Y),
            box=1, boxcolor="black@0.6", boxborderw=10,
        )

    # Apply color grading and vignette
    stream = _apply_color_grade(stream, mood)
    stream = _apply_vignette(stream, is_product=True)

    out = ffmpeg.output(stream, str(output_path), vcodec="libx264", pix_fmt="yuv420p",
                        t=timing["total_duration"])
    out.overwrite_output().run(quiet=True)

    # Mux TTS audio
    _mux_product_audio(audio_data, output_path)

    return output_path


def select_render_format(script: dict, product: dict | None = None) -> str:
    """Pick rendering format based on script hints, available assets, and config.

    Decision tree:
      1. Explicit video_style in visual_hints → use that if enabled
      2. Product data with images available → "product_showcase"
      3. Config default_format
      4. "standard" (solid-color fallback)

    Config format_weights provide diversity (not every video same format).
    """
    hints = script.get("visual_hints", {}) if isinstance(script.get("visual_hints"), dict) else {}
    video_style = hints.get("video_style", "")
    config = load_pipeline_config()
    router_config = config.get("format_router", {})

    # 1. Explicit screen_recording requested
    if video_style == "screen_recording":
        if router_config.get("screen_recording_enabled", True):
            return "screen_recording"

    # 2. Explicit ugc_avatar requested
    if video_style == "ugc_avatar":
        if router_config.get("heygen_enabled", False):
            return "ugc_avatar"
        # Fall through if HeyGen not enabled

    # 3. Product styles
    if video_style in PRODUCT_STYLES:
        return video_style

    # 4. Check if product data suggests screen recording
    product_id = script.get("product_id", "") or (product or {}).get("product_id", "")
    if product_id and router_config.get("screen_recording_enabled", True):
        # Check if product images exist for screen recording
        from src.utils.config import PRODUCT_IMAGES_DIR
        has_product_images = bool(
            list(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.jpg"))
            or list(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.png"))
        )
        if has_product_images:
            # Use format weights to add variety
            import random
            weights = router_config.get("format_weights", {})
            showcase_weight = weights.get("product_showcase", 0.5)
            screen_weight = weights.get("screen_recording", 0.3)
            total = showcase_weight + screen_weight
            if total > 0 and random.random() < screen_weight / total:
                return "screen_recording"
            return "product_showcase"

    # 5. If product_id present, default to product_showcase
    if product_id:
        return "product_showcase"

    # 6. Config default
    default = router_config.get("default_format", "standard")
    if default in ALL_RENDER_FORMATS:
        return default

    return "standard"


def render_all(scripts: list[dict], font_path: Path | None = None) -> list[Path]:
    """Render all scripts to MP4 videos with optional TTS narration.

    If TTS is enabled in pipeline_config.json and ELEVENLABS_API_KEY is set,
    each script gets narrated and video timing syncs to the audio duration.
    Otherwise, renders silent videos with word-count-estimated timing.
    """
    if font_path is None:
        font_path = FONT_PATH

    # Import TTS lazily — only when actually rendering
    from src.renderers.tts import generate_script_audio

    paths = []
    for i, script in enumerate(scripts, 1):
        script_id = script.get("script_id", f"unknown_{i}")
        product_id = script.get("product_id", "")
        source_type = script.get("source_type", "mixed")
        if product_id:
            # Sanitize product_id for use in filename (remove colons, slashes, etc.)
            safe_id = re.sub(r'[<>:"/\\|?*]', '', product_id).strip()[:40]
            filename = f"{script_id[:8]}_{safe_id}.mp4"
        else:
            filename = f"{script_id[:8]}_{source_type}.mp4"
        output_path = OUTPUT_DIR / filename

        # Use format router to pick rendering format
        format_choice = select_render_format(script)
        hints = script.get("visual_hints", {}) if isinstance(script.get("visual_hints"), dict) else {}
        mood = hints.get("mood", "auto")
        rprint(f"  [{i}/{len(scripts)}] Rendering [cyan]{filename}[/cyan] [dim](format: {format_choice}, mood: {mood})[/dim]...")

        # Generate TTS audio (returns None if disabled or fails)
        audio_data = generate_script_audio(script, output_dir=OUTPUT_DIR)

        try:
            if format_choice == "screen_recording":
                from src.renderers.screen_recorder import render_screen_recording_video
                render_screen_recording_video(script, None, output_path, font_path, audio_data=audio_data)
            elif format_choice in PRODUCT_STYLES:
                render_product_video(script, output_path, font_path, audio_data=audio_data)
            else:
                render_video(script, output_path, font_path, audio_data=audio_data)

            # Mix background music if enabled
            music_track = get_music_track(script)
            if music_track:
                config = load_pipeline_config()
                volume = config.get("music", {}).get("volume", 0.15)
                if _mix_background_music(output_path, music_track, volume):
                    rprint(f"    [dim]Music: {music_track.name} (vol {volume})[/dim]")

            paths.append(output_path)
            rprint(f"    [green]Done[/green]")
        except ffmpeg.Error as e:
            rprint(f"    [red]FFmpeg error: {e}[/red]")
        finally:
            # Clean up individual section audio files
            if audio_data:
                for key in ("hook", "body", "cta"):
                    audio_path = audio_data.get(key)
                    if audio_path and isinstance(audio_path, Path):
                        audio_path.unlink(missing_ok=True)

    return paths


def display_results(paths: list[Path]) -> None:
    """Display a rich table of rendered video files."""
    if not paths:
        rprint("[yellow]No videos rendered.[/yellow]")
        return

    table = Table(title="Rendered Videos", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="yellow", justify="right")

    for i, path in enumerate(paths, 1):
        size_kb = path.stat().st_size / 1024
        if size_kb > 1024:
            size_str = f"{size_kb / 1024:.1f} MB"
        else:
            size_str = f"{size_kb:.0f} KB"
        table.add_row(str(i), path.name, size_str)

    rprint(table)


def run() -> list[Path]:
    """Full pipeline: check FFmpeg → check font → load scripts → render → display."""
    # Check FFmpeg
    if not check_ffmpeg():
        return []

    # Check font
    if not FONT_PATH.exists():
        rprint(f"[red]Font not found:[/red] {FONT_PATH}")
        rprint("[yellow]Download Inter-Bold.ttf from Google Fonts into assets/fonts/[/yellow]")
        return []

    # Load latest scripts
    rprint("[bold]Loading latest generated scripts...[/bold]")
    scripts = load_latest(DATA_SCRIPTS_DIR, "scripts")
    if not scripts:
        rprint("[yellow]No scripts found. Run the generator first:[/yellow]")
        rprint("  python -m src.generators.script_generator")
        return []

    rprint(f"[green]Found {len(scripts)} scripts[/green]")

    # Render
    rprint("\n[bold]Rendering videos...[/bold]")
    paths = render_all(scripts)

    # Display results
    rprint()
    display_results(paths)
    rprint(f"\n[bold green]Output directory:[/bold green] {OUTPUT_DIR}")

    return paths


if __name__ == "__main__":
    run()
