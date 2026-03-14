"""
video_generator.py — Muapi REST API video clip generator.

Takes scene images from the image generator and animates them into short video
clips (3-5 seconds each) with cinematic motion (camera pans, zooms, rotations).

Muapi (muapi.ai) is a unified API gateway to 275+ AI models including Kling,
Veo, Sora, Runway, etc. No SDK needed — pure REST via requests.

Two-step async pattern:
  1. POST to submit image-to-video job → get request_id
  2. GET to poll status → download completed video

Usage:
    python -m src.renderers.video_generator
"""

import time
from pathlib import Path

import requests
from rich import print as rprint

from src.utils.config import (
    DATA_SCRIPTS_DIR,
    MUAPI_API_KEY,
    OUTPUT_CLIPS_DIR,
    OUTPUT_IMAGES_DIR,
    load_pipeline_config,
)
from src.utils.data_io import load_latest

# ── Muapi API ──
MUAPI_BASE = "https://api.muapi.ai/api/v1"

# ── Default model for image-to-video ──
# Kling v2.1 is a good balance of quality/speed/cost for product videos
DEFAULT_MODEL = "kling-v2.1-standard-i2v"

# ── Available image-to-video models (endpoint suffixes) ──
AVAILABLE_MODELS = {
    "kling-v2.1": "kling-v2.1-standard-i2v",
    "kling-v3.0": "kling-v3.0-pro-image-to-video",
    "kling-o1": "kling-o1-image-to-video",
    "veo3.1": "veo3.1-image-to-video",
    "sora-2": "openai-sora-2-image-to-video",
    "sora-2-pro": "openai-sora-2-pro-image-to-video",
    "midjourney-v7": "midjourney-v7-image-to-video",
    "seedance-2.0": "seedance-2.0-i2v",
    "wan2.6": "wan2.6-image-to-video",
    "runway": "runway-image-to-video",
    "auto": DEFAULT_MODEL,
}

# ── Motion presets per mood ──
MOTION_PRESETS = {
    "energetic": {
        "prompt_suffix": "dynamic camera movement, fast zoom in, vibrant energy",
        "duration": 5,
    },
    "calm": {
        "prompt_suffix": "slow dolly shot, shallow depth of field, serene",
        "duration": 5,
    },
    "warm": {
        "prompt_suffix": "gentle rotation, soft golden lighting, cozy atmosphere",
        "duration": 5,
    },
    "cool": {
        "prompt_suffix": "smooth pan, cool blue tones, modern aesthetic",
        "duration": 5,
    },
    "default": {
        "prompt_suffix": "subtle camera movement, professional product showcase",
        "duration": 5,
    },
}

# ── Poll settings ──
POLL_INTERVAL_SEC = 3
MAX_POLL_ATTEMPTS = 100  # ~5 minutes max wait


def _get_headers() -> dict:
    """Build Muapi API request headers."""
    return {
        "Content-Type": "application/json",
        "x-api-key": MUAPI_API_KEY,
    }


def _get_model_endpoint(model_name: str) -> str:
    """Resolve a model name to the Muapi endpoint."""
    return AVAILABLE_MODELS.get(model_name, DEFAULT_MODEL)


def _get_motion_preset(mood: str) -> dict:
    """Get the motion preset for a given mood."""
    return MOTION_PRESETS.get(mood, MOTION_PRESETS["default"])



def generate_clip(
    image_path: Path,
    output_path: Path,
    prompt: str = "",
    mood: str = "default",
    image_url: str | None = None,
) -> Path | None:
    """
    Generate a single video clip from an image using Muapi.

    Args:
        image_path: Source image (used as fallback reference)
        output_path: Where to save the generated clip
        prompt: Optional text prompt for motion guidance
        mood: Mood for motion preset selection
        image_url: Direct URL to the image (required by Muapi API)

    Returns:
        Path to the generated clip, or None on failure
    """
    if not MUAPI_API_KEY:
        rprint("[red]MUAPI_API_KEY not set in .env[/red]")
        return None

    if not image_path.exists() and not image_url:
        rprint(f"[red]Image not found: {image_path}[/red]")
        return None

    preset = _get_motion_preset(mood)
    config = load_pipeline_config()
    muapi_config = config.get("muapi", {})

    # Resolve model
    model_name = muapi_config.get("model", "auto")
    endpoint = _get_model_endpoint(model_name)

    # Build the generation prompt
    full_prompt = prompt or "Animate this product image with cinematic motion"
    full_prompt += f". {preset['prompt_suffix']}"

    # Prepare the image URL
    # If no URL provided, try to use a publicly accessible URL or skip
    if not image_url:
        rprint("      [yellow]No image URL — Muapi requires a URL, not local files[/yellow]")
        rprint("      [dim]Provide image_url from product data or host images[/dim]")
        return None

    # Step 1: Submit the job
    payload = {
        "prompt": full_prompt,
        "image_url": image_url,
        "aspect_ratio": "9:16",
        "duration": preset["duration"],
    }

    submit_url = f"{MUAPI_BASE}/{endpoint}"

    try:
        resp = requests.post(submit_url, headers=_get_headers(), json=payload, timeout=30)
    except Exception as e:
        rprint(f"      [red]Muapi submit failed: {e}[/red]")
        return None

    if resp.status_code != 200:
        rprint(f"      [red]Muapi submit error: {resp.status_code}[/red]")
        try:
            rprint(f"      [dim]{resp.json()}[/dim]")
        except Exception:
            pass
        return None

    result = resp.json()
    request_id = result.get("request_id")
    if not request_id:
        rprint("      [red]No request_id in Muapi response[/red]")
        return None

    rprint(f"      [dim]Job submitted: {request_id[:12]}... (model: {endpoint})[/dim]")

    # Step 2: Poll for completion
    poll_url = f"{MUAPI_BASE}/predictions/{request_id}/result"

    for attempt in range(MAX_POLL_ATTEMPTS):
        try:
            poll_resp = requests.get(poll_url, headers={"x-api-key": MUAPI_API_KEY}, timeout=15)
            poll_data = poll_resp.json()
        except Exception:
            time.sleep(POLL_INTERVAL_SEC)
            continue

        status = poll_data.get("status", "unknown")

        if status == "completed":
            outputs = poll_data.get("outputs", [])
            if outputs:
                video_url = outputs[0]
                try:
                    dl_resp = requests.get(video_url, timeout=60)
                    if dl_resp.status_code == 200:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(dl_resp.content)
                        return output_path
                except Exception as e:
                    rprint(f"      [red]Video download failed: {e}[/red]")

            rprint("      [yellow]Job completed but no video in outputs[/yellow]")
            return None

        if status == "failed":
            error = poll_data.get("error", "unknown error")
            rprint(f"      [red]Job failed: {error}[/red]")
            return None

        # Still processing
        time.sleep(POLL_INTERVAL_SEC)

    rprint(f"      [yellow]Job timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC}s[/yellow]")
    return None


def generate_script_clips(
    script: dict,
    image_paths: list[Path],
    image_urls: list[str] | None = None,
) -> list[Path]:
    """
    Generate video clips for a script from its scene images.

    Args:
        script: Script dict with visual_hints
        image_paths: List of scene image paths
        image_urls: Optional list of image URLs (Muapi requires URLs)

    Returns:
        List of generated clip paths
    """
    if not image_paths:
        return []

    if not MUAPI_API_KEY:
        rprint("    [yellow]Muapi API key not set — using static images as fallback[/yellow]")
        return []

    script_id = script.get("script_id", "unknown")[:8]
    clips_dir = OUTPUT_CLIPS_DIR / script_id
    clips_dir.mkdir(parents=True, exist_ok=True)

    hints = script.get("visual_hints", {})
    mood = hints.get("mood", "default") if isinstance(hints, dict) else "default"

    clips = []
    for i, img_path in enumerate(image_paths):
        output_path = clips_dir / f"clip_{i:02d}.mp4"
        rprint(f"    [dim]Generating clip {i + 1}/{len(image_paths)}...[/dim]")

        # Use provided URL or None
        url = image_urls[i] if image_urls and i < len(image_urls) else None

        result = generate_clip(
            image_path=img_path,
            output_path=output_path,
            mood=mood,
            image_url=url,
        )

        if result:
            clips.append(result)
        else:
            rprint(f"    [yellow]Clip {i + 1} failed — will use static image[/yellow]")

    return clips


def generate_all(
    scripts: list[dict],
    images: dict[str, list[Path]],
) -> dict[str, list[Path]]:
    """
    Generate video clips for all scripts.

    Args:
        scripts: List of script dicts
        images: Dict mapping script_id → list of image paths

    Returns:
        Dict mapping script_id → list of clip paths
    """
    results = {}

    for i, script in enumerate(scripts):
        script_id = script.get("script_id", f"unknown_{i}")[:8]
        script_images = images.get(script_id, [])

        if not script_images:
            rprint(f"  [{i + 1}/{len(scripts)}] No images for {script_id} — skipping")
            results[script_id] = []
            continue

        rprint(f"  [{i + 1}/{len(scripts)}] Generating clips for [cyan]{script_id}[/cyan]...")
        clips = generate_script_clips(script, script_images)
        results[script_id] = clips

        if clips:
            rprint(f"    [green]{len(clips)} clips generated[/green]")

    return results


def run() -> dict[str, list[Path]]:
    """Entry point: load scripts + images → generate video clips."""
    rprint("[bold blue]Video Clip Generator (Muapi)[/bold blue]")
    rprint("-" * 40)

    if not MUAPI_API_KEY:
        rprint("[red]MUAPI_API_KEY not set in .env[/red]")
        rprint("Sign up at https://muapi.ai")
        return {}

    config = load_pipeline_config()
    model = config.get("muapi", {}).get("model", "auto")
    rprint(f"  [dim]Model: {_get_model_endpoint(model)}[/dim]")

    # Load latest scripts
    scripts = load_latest(DATA_SCRIPTS_DIR, "scripts")
    if not scripts:
        rprint("[yellow]No scripts found. Run the generator first.[/yellow]")
        return {}

    # Discover existing scene images
    images: dict[str, list[Path]] = {}
    for script in scripts:
        script_id = script.get("script_id", "")[:8]
        img_dir = OUTPUT_IMAGES_DIR / script_id
        if img_dir.exists():
            imgs = sorted(img_dir.glob("*.png")) + sorted(img_dir.glob("*.jpg"))
            if imgs:
                images[script_id] = imgs

    if not images:
        rprint("[yellow]No scene images found. Run the image generator first.[/yellow]")
        return {}

    rprint(f"\n[bold]Generating video clips for {len(images)} scripts...[/bold]")
    results = generate_all(scripts, images)

    total = sum(len(clips) for clips in results.values())
    rprint(f"\n[bold green]Generated {total} video clips[/bold green]")
    rprint(f"[dim]Output: {OUTPUT_CLIPS_DIR}[/dim]")

    return results


if __name__ == "__main__":
    run()
