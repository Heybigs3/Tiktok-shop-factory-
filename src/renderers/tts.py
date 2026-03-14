"""
tts.py — ElevenLabs text-to-speech via REST API.

Converts script sections (hook, body, CTA) into audio files. Uses the
ElevenLabs REST API directly (no SDK — avoids Windows path length issues).

Voice selection is driven by the script's visual_hints.mood, mapped through
pipeline_config.json's tts.voice_map. This means warm scripts get a warm
voice, energetic scripts get an upbeat voice, etc.

Usage:
    from src.renderers.tts import generate_speech, get_audio_duration
    audio_path = generate_speech("Hello world", voice_name="Rachel")
    duration = get_audio_duration(audio_path)
"""

import subprocess
import tempfile
from pathlib import Path

import requests
from rich import print as rprint

from src.utils.config import ELEVENLABS_API_KEY, load_pipeline_config

# ── ElevenLabs API ──
API_BASE = "https://api.elevenlabs.io/v1"

# Cache of voice_name → voice_id (fetched once per session)
_voice_cache: dict[str, str] | None = None


def _get_voice_id(voice_name: str) -> str | None:
    """Look up an ElevenLabs voice ID by name. Caches the full voice list."""
    global _voice_cache

    if _voice_cache is None:
        resp = requests.get(
            f"{API_BASE}/voices",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            rprint(f"[red]Failed to fetch ElevenLabs voices: {resp.status_code}[/red]")
            return None

        _voice_cache = {}
        for voice in resp.json().get("voices", []):
            full_name = voice.get("name", "")
            vid = voice.get("voice_id", "")
            if full_name and vid:
                # Store both the full name and the short name (before " - ")
                _voice_cache[full_name] = vid
                short_name = full_name.split(" - ")[0].strip()
                if short_name:
                    _voice_cache[short_name] = vid

    return _voice_cache.get(voice_name)


def get_voice_for_mood(mood: str) -> str:
    """Get the voice name for a given mood from pipeline config."""
    config = load_pipeline_config()
    tts_config = config.get("tts", {})
    voice_map = tts_config.get("voice_map", {})
    return voice_map.get(mood, voice_map.get("default", "Rachel"))


def generate_speech(
    text: str,
    voice_name: str = "Rachel",
    output_path: Path | None = None,
) -> Path | None:
    """
    Generate speech audio from text using ElevenLabs.

    Args:
        text: The text to speak
        voice_name: ElevenLabs voice name (e.g., "Rachel", "Adam")
        output_path: Where to save the MP3. Uses a temp file if None.

    Returns:
        Path to the generated MP3 file, or None on failure
    """
    if not ELEVENLABS_API_KEY:
        rprint("[red]ELEVENLABS_API_KEY not set in .env[/red]")
        return None

    if not text or not text.strip():
        return None

    voice_id = _get_voice_id(voice_name)
    if not voice_id:
        rprint(f"[yellow]Voice '{voice_name}' not found, trying default voices[/yellow]")
        # Try common fallbacks
        for fallback in ["Rachel", "Adam", "Elli"]:
            voice_id = _get_voice_id(fallback)
            if voice_id:
                break
        if not voice_id:
            rprint("[red]No valid ElevenLabs voice found[/red]")
            return None

    config = load_pipeline_config()
    tts_config = config.get("tts", {})

    payload = {
        "text": text,
        "model_id": tts_config.get("model", "eleven_multilingual_v2"),
        "voice_settings": {
            "stability": tts_config.get("stability", 0.5),
            "similarity_boost": tts_config.get("similarity_boost", 0.75),
        },
    }

    try:
        resp = requests.post(
            f"{API_BASE}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
            timeout=30,
        )
    except Exception as e:
        rprint(f"[red]ElevenLabs API request failed: {e}[/red]")
        return None

    if resp.status_code != 200:
        rprint(f"[red]ElevenLabs TTS failed: {resp.status_code}[/red]")
        error = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if error:
            rprint(f"[dim]{error.get('detail', {}).get('message', resp.text[:200])}[/dim]")
        return None

    # Save the audio
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = Path(tmp.name)
        tmp.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(resp.content)

    return output_path


def get_audio_duration(audio_path: Path) -> float:
    """
    Get the duration of an audio file in seconds using ffprobe.

    Works with MP3 and WAV files.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback: estimate from file size (MP3 at ~128kbps)
        size_bytes = audio_path.stat().st_size
        return size_bytes / 16000  # rough estimate


def generate_script_audio(
    script: dict,
    output_dir: Path | None = None,
) -> dict[str, Path] | None:
    """
    Generate TTS audio for all three sections of a script.

    Picks the voice based on the script's visual_hints.mood and the
    voice_map in pipeline_config.json.

    Args:
        script: Script dict with hook, body, cta keys
        output_dir: Directory to save audio files. Uses temp dir if None.

    Returns:
        Dict with keys "hook", "body", "cta" mapping to audio file paths,
        plus "durations" dict with the duration of each section in seconds.
        Returns None if TTS is disabled or fails.
    """
    config = load_pipeline_config()
    tts_config = config.get("tts", {})

    if not tts_config.get("enabled", False):
        return None

    if not ELEVENLABS_API_KEY:
        rprint("[yellow]TTS enabled but ELEVENLABS_API_KEY not set — skipping[/yellow]")
        return None

    # Pick voice based on mood
    hints = script.get("visual_hints", {})
    mood = hints.get("mood", "default") if isinstance(hints, dict) else "default"
    voice_name = get_voice_for_mood(mood)

    script_id = script.get("script_id", "unknown")[:8]
    rprint(f"    [dim]TTS: voice={voice_name}, mood={mood}[/dim]")

    sections = {}
    durations = {}

    for section in ("hook", "body", "cta"):
        text = script.get(section, "")
        if not text:
            continue

        if output_dir:
            path = output_dir / f"{script_id}_{section}.mp3"
        else:
            path = None

        audio_path = generate_speech(text, voice_name=voice_name, output_path=path)
        if audio_path is None:
            rprint(f"    [red]TTS failed for {section}[/red]")
            # Clean up any files we already generated
            for p in sections.values():
                p.unlink(missing_ok=True)
            return None

        sections[section] = audio_path
        durations[section] = get_audio_duration(audio_path)

    sections["durations"] = durations
    total = sum(durations.values())
    rprint(f"    [green]TTS done: {total:.1f}s total[/green]")

    return sections
