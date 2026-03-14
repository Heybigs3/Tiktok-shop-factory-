"""
screen_recorder.py — Screen recording style video renderer.

Simulates the "scrolling through a product page" TikTok format using
Playwright screenshots + FFmpeg scroll animation. This is the most common
TikTok Shop affiliate format — high authenticity, zero cost.

Pipeline:
  1. Capture tall screenshot of product page (Playwright) or use existing images
  2. Animate scrolling with FFmpeg crop filter (variable speed, pauses)
  3. Add recording indicator (red dot + "Screen Recording" text)
  4. Overlay TTS narration and background music

Usage:
    from src.renderers.screen_recorder import render_screen_recording_video
"""

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import ffmpeg
from rich import print as rprint

from src.utils.config import (
    OUTPUT_SCREENSHOTS_DIR,
    PRODUCT_IMAGES_DIR,
    load_pipeline_config,
)

# ── Video constants (match video_builder.py) ──
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

# ── Screen recording overlay constants ──
RECORDING_DOT_X = 40
RECORDING_DOT_Y = 60
RECORDING_DOT_SIZE = 48
RECORDING_LABEL_X = 70
RECORDING_LABEL_Y = 50
RECORDING_LABEL_SIZE = 28

# ── Scroll animation defaults ──
DEFAULT_SCROLL_SPEED = 300   # pixels per second
DEFAULT_PAUSE_DURATION = 1.5  # seconds to pause at key points
PHONE_FRAME_PADDING = 40     # pixels of black border to simulate phone edge


def get_screenshot_cache_dir(product_id: str) -> Path:
    """Get the cache directory for a product's screenshots."""
    cache_dir = OUTPUT_SCREENSHOTS_DIR / product_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _hash_product(product: dict) -> str:
    """Create a short hash for cache invalidation."""
    key = product.get("product_id", "") + product.get("title", "")
    return hashlib.md5(key.encode()).hexdigest()[:8]


async def capture_product_screenshots(
    product: dict,
    output_dir: Path | None = None,
) -> list[dict]:
    """Capture screenshots of product-related pages using Playwright.

    Takes full-page tall screenshots (1080px wide, ~3000-5000px tall).
    Returns list of {path, type, scroll_duration, pause_points}.

    Falls back to product images from assets/product_images/ if Playwright
    is not available or page capture fails.
    """
    product_id = product.get("product_id", "unknown")
    if output_dir is None:
        output_dir = get_screenshot_cache_dir(product_id)

    # Check cache first
    cached = _load_cached_screenshots(output_dir, product_id)
    if cached:
        rprint(f"    [dim]Using {len(cached)} cached screenshot(s) for {product_id}[/dim]")
        return cached

    screenshots = []

    # Try Playwright capture
    try:
        screenshots = await _capture_with_playwright(product, output_dir)
    except Exception as e:
        rprint(f"    [yellow]Playwright capture failed: {e}[/yellow]")

    # Fallback: compose product images into a tall scrollable strip
    if not screenshots:
        screenshots = _create_from_product_images(product_id, output_dir)

    if screenshots:
        rprint(f"    [green]Prepared {len(screenshots)} screenshot(s) for scroll animation[/green]")
    else:
        rprint(f"    [yellow]No screenshots available for {product_id}[/yellow]")

    return screenshots


async def _capture_with_playwright(product: dict, output_dir: Path) -> list[dict]:
    """Capture product page screenshots using Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        rprint("    [dim]Playwright not installed — using product image fallback[/dim]")
        return []

    product_id = product.get("product_id", "unknown")
    title = product.get("title", "Product")
    screenshots = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1080, "height": 1920})

        # Try Google Shopping search for the product
        search_url = f"https://www.google.com/search?tbm=shop&q={title.replace(' ', '+')}"
        try:
            await page.goto(search_url, timeout=15000)
            await page.wait_for_load_state("networkidle", timeout=10000)

            screenshot_path = output_dir / f"{product_id}_search.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)

            screenshots.append({
                "path": screenshot_path,
                "type": "search_results",
                "scroll_duration": 6.0,
                "pause_points": [0.3, 0.6],  # Pause at 30% and 60% of scroll
            })
        except Exception as e:
            rprint(f"    [dim]Search screenshot failed: {e}[/dim]")

        await browser.close()

    return screenshots


def _load_cached_screenshots(output_dir: Path, product_id: str) -> list[dict]:
    """Load previously captured screenshots from cache."""
    if not output_dir.exists():
        return []

    pngs = sorted(output_dir.glob(f"{product_id}_*.png"))
    if not pngs:
        return []

    return [
        {
            "path": p,
            "type": "cached",
            "scroll_duration": 6.0,
            "pause_points": [0.3, 0.6],
        }
        for p in pngs
    ]


def _create_from_product_images(product_id: str, output_dir: Path) -> list[dict]:
    """Create a tall scrollable strip from product images in assets/product_images/.

    Stacks product images vertically into one tall image that can be scroll-animated.
    This is the free fallback when Playwright can't capture a real product page.
    """
    product_images = sorted(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.jpg"))
    product_images += sorted(PRODUCT_IMAGES_DIR.glob(f"{product_id}_*.png"))

    if not product_images:
        return []

    # Use FFmpeg to stack images vertically into a tall strip
    strip_path = output_dir / f"{product_id}_strip.png"

    try:
        if len(product_images) == 1:
            # Single image — scale to width and pad to make it taller
            (
                ffmpeg.input(str(product_images[0]))
                .filter("scale", VIDEO_WIDTH, -1, force_original_aspect_ratio="decrease")
                .filter("pad", VIDEO_WIDTH, VIDEO_HEIGHT * 2, "(ow-iw)/2", 0, color="white")
                .output(str(strip_path), vframes=1)
                .overwrite_output()
                .run(quiet=True)
            )
        else:
            # Multiple images — scale each to same width and stack
            inputs = []
            for img in product_images[:5]:
                stream = (
                    ffmpeg.input(str(img))
                    .filter("scale", VIDEO_WIDTH, -1, force_original_aspect_ratio="decrease")
                    .filter("pad", VIDEO_WIDTH, "ih", "(ow-iw)/2", 0, color="white")
                )
                inputs.append(stream)

            stacked = ffmpeg.filter(inputs, "vstack", inputs=len(inputs))
            stacked.output(str(strip_path), vframes=1).overwrite_output().run(quiet=True)

        if strip_path.exists():
            # Calculate scroll duration based on image height
            duration = max(4.0, len(product_images) * 3.0)
            return [{
                "path": strip_path,
                "type": "product_strip",
                "scroll_duration": duration,
                "pause_points": [i / len(product_images) for i in range(1, len(product_images))],
            }]
    except ffmpeg.Error as e:
        rprint(f"    [yellow]Failed to create image strip: {e}[/yellow]")

    return []


def build_scroll_expression(
    image_height: int,
    duration: float,
    pause_points: list[float] | None = None,
    scroll_speed: int = DEFAULT_SCROLL_SPEED,
) -> str:
    """Build an FFmpeg expression for variable-speed scrolling.

    The expression controls the crop y-position over time, creating the
    illusion of scrolling through a tall page. Pauses at specified points.

    Args:
        image_height: Height of the source image in pixels.
        duration: Total animation duration in seconds.
        pause_points: List of fractions (0.0-1.0) where scrolling pauses.
        scroll_speed: Base scroll speed in pixels per second.

    Returns:
        FFmpeg expression string for the crop y parameter.
    """
    max_scroll = max(0, image_height - VIDEO_HEIGHT)
    if max_scroll == 0:
        return "0"

    if not pause_points:
        # Simple linear scroll
        return f"min({max_scroll},{scroll_speed}*t)"

    # Build piecewise expression with pauses
    # Strategy: divide time into segments, fast-scroll between pauses,
    # hold position during pauses
    pause_duration = load_pipeline_config().get("screen_recording", {}).get(
        "pause_duration", DEFAULT_PAUSE_DURATION
    )

    num_pauses = len(pause_points)
    total_pause_time = num_pauses * pause_duration
    scroll_time = max(0.1, duration - total_pause_time)

    # Calculate y positions for each pause point
    pause_positions = [int(p * max_scroll) for p in sorted(pause_points)]

    # Build nested if/else expression for FFmpeg
    # Each segment: scroll to pause_position, then hold
    parts = []
    t_offset = 0.0

    for i, (pos, pp) in enumerate(zip(pause_positions, sorted(pause_points))):
        segment_scroll_time = scroll_time * (
            (sorted(pause_points)[i] - (sorted(pause_points)[i - 1] if i > 0 else 0))
        )
        segment_scroll_time = max(segment_scroll_time, 0.1)
        prev_pos = pause_positions[i - 1] if i > 0 else 0

        # Scrolling phase
        scroll_end = t_offset + segment_scroll_time
        speed_for_segment = (pos - prev_pos) / segment_scroll_time if segment_scroll_time > 0 else 0
        parts.append(
            f"if(lt(t,{scroll_end:.2f}),{prev_pos}+{speed_for_segment:.1f}*(t-{t_offset:.2f})"
        )
        t_offset = scroll_end

        # Pause phase
        pause_end = t_offset + pause_duration
        parts.append(f"if(lt(t,{pause_end:.2f}),{pos}")
        t_offset = pause_end

    # Final scroll to bottom
    remaining_scroll = max_scroll - (pause_positions[-1] if pause_positions else 0)
    final_speed = remaining_scroll / max(duration - t_offset, 0.1)
    last_pos = pause_positions[-1] if pause_positions else 0
    final_expr = f"{last_pos}+{final_speed:.1f}*(t-{t_offset:.2f})"

    # Assemble nested expression
    expr = final_expr
    for part in reversed(parts):
        expr = f"{part},{expr})"

    # Clamp to valid range
    return f"min({max_scroll},max(0,{expr}))"


def _get_image_height(image_path: Path) -> int:
    """Get the height of an image using FFprobe."""
    try:
        probe = ffmpeg.probe(str(image_path))
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                return int(stream.get("height", VIDEO_HEIGHT * 2))
    except ffmpeg.Error:
        pass
    return VIDEO_HEIGHT * 2  # default fallback


def render_scroll_segment(
    screenshot_path: Path,
    duration: float,
    pause_points: list[float] | None = None,
) -> ffmpeg.Stream:
    """Animate scrolling over a tall screenshot using FFmpeg crop filter.

    Variable speed: fast through headers, slow/pause on product image, price, reviews.
    """
    config = load_pipeline_config()
    sr_config = config.get("screen_recording", {})
    scroll_speed = sr_config.get("scroll_speed", DEFAULT_SCROLL_SPEED)

    # Get actual image dimensions
    image_height = _get_image_height(screenshot_path)

    # Scale image to video width first
    stream = ffmpeg.input(str(screenshot_path), loop=1, t=duration, framerate=FPS)
    stream = stream.filter("scale", VIDEO_WIDTH, -1, force_original_aspect_ratio="decrease")
    # Pad to ensure minimum height
    stream = stream.filter("pad", VIDEO_WIDTH, f"max(ih,{VIDEO_HEIGHT})", 0, 0, color="white")

    # Build scroll expression
    scroll_expr = build_scroll_expression(
        image_height, duration, pause_points, scroll_speed,
    )

    # Crop to viewport with animated y position
    stream = stream.filter(
        "crop", VIDEO_WIDTH, VIDEO_HEIGHT, 0, scroll_expr,
    )

    return stream


def _add_recording_indicator(stream: ffmpeg.Stream, font_path: str) -> ffmpeg.Stream:
    """Add red recording dot + 'Screen Recording' label to top-left."""
    config = load_pipeline_config()
    show_indicator = config.get("screen_recording", {}).get("show_recording_indicator", True)
    if not show_indicator:
        return stream

    # Red dot — pulsing with 1.5s period
    from src.renderers.video_builder import escape_drawtext
    stream = stream.drawtext(
        text=escape_drawtext("●"),
        fontsize=RECORDING_DOT_SIZE,
        fontcolor="red@0.9",
        x=str(RECORDING_DOT_X),
        y=str(RECORDING_DOT_Y),
        alpha="0.5+0.5*sin(2*PI*t/1.5)",
    )

    # "Screen Recording" label
    stream = stream.drawtext(
        fontfile=font_path,
        text=escape_drawtext("Screen Recording"),
        fontsize=RECORDING_LABEL_SIZE,
        fontcolor="white@0.7",
        x=str(RECORDING_LABEL_X),
        y=str(RECORDING_LABEL_Y),
    )

    return stream


def render_screen_recording_video(
    script: dict,
    product: dict | None,
    output_path: Path,
    font_path: Path,
    audio_data: dict | None = None,
) -> Path:
    """Render a screen-recording style video.

    1. Load/capture screenshots for the product
    2. Render scroll segments with variable speed
    3. Add recording indicator (red dot + label)
    4. Overlay TTS narration
    5. Mix background music

    Args:
        script: Script dict with hook/body/cta and visual_hints.
        product: Product dict with product_id, title, etc. Can be None.
        output_path: Where to save the final MP4.
        font_path: Path to the font file for text overlays.
        audio_data: Optional TTS audio data from tts.py.

    Returns:
        Path to the rendered video.
    """
    from src.renderers.video_builder import (
        calculate_timing,
        escape_drawtext,
        wrap_text,
        HOOK_FONT_SIZE,
        HOOK_WRAP_WIDTH,
        BODY_FONT_SIZE,
        BODY_WRAP_WIDTH,
        CTA_FONT_SIZE,
        CTA_WRAP_WIDTH,
        HOOK_TEXT_Y,
        BODY_TEXT_Y,
        CTA_TEXT_Y,
        PRODUCT_TEXT_BORDER_WIDTH,
        PRODUCT_TEXT_BORDER_COLOR,
        get_theme,
        _apply_color_grade,
        _apply_vignette,
        _get_mood,
        _mux_product_audio,
        HOOK_DURATION,
        MIN_BODY_DURATION,
        CTA_DURATION,
    )

    font_str = font_path.as_posix()
    theme = get_theme(script)
    mood = _get_mood(script)
    product_id = ""
    if product:
        product_id = product.get("product_id", "")
    elif script:
        product_id = script.get("product_id", "")

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

    total_duration = timing["total_duration"]

    # Try to get screenshots
    screenshots = []
    if product_id:
        cache_dir = get_screenshot_cache_dir(product_id)
        screenshots = _load_cached_screenshots(cache_dir, product_id)
        if not screenshots:
            screenshots = _create_from_product_images(product_id, cache_dir)

    if screenshots:
        # Use the first screenshot as the scroll background
        ss = screenshots[0]
        stream = render_scroll_segment(
            ss["path"], total_duration, ss.get("pause_points"),
        )
    else:
        # Fallback: solid color background with "product page" feel
        rprint("    [yellow]No screenshots — rendering with solid background[/yellow]")
        stream = ffmpeg.input(
            f"color=c=0xfafafa:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={total_duration}:r={FPS}",
            f="lavfi",
        )

    # Add recording indicator
    stream = _add_recording_indicator(stream, font_str)

    # ── Text overlays ──
    hook_end = timing["hook_duration"]
    body_start = hook_end
    body_end = body_start + timing["body_duration"]
    cta_start = body_end

    # Hook text
    hook_text = escape_drawtext(wrap_text(script.get("hook", ""), HOOK_WRAP_WIDTH))
    if hook_text:
        # Shadow
        stream = stream.drawtext(
            fontfile=font_str, text=hook_text, fontsize=HOOK_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+3", y=f"{HOOK_TEXT_Y}+3",
            enable=f"lt(t,{hook_end})",
        )
        # Text
        stream = stream.drawtext(
            fontfile=font_str, text=hook_text, fontsize=HOOK_FONT_SIZE,
            fontcolor=theme["text"], x="(w-text_w)/2", y=str(HOOK_TEXT_Y),
            enable=f"lt(t,{hook_end})",
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # Body text
    body_text = escape_drawtext(wrap_text(script.get("body", ""), BODY_WRAP_WIDTH))
    if body_text:
        stream = stream.drawtext(
            fontfile=font_str, text=body_text, fontsize=BODY_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+2", y=f"{BODY_TEXT_Y}+2",
            enable=f"between(t,{body_start},{body_end})",
        )
        stream = stream.drawtext(
            fontfile=font_str, text=body_text, fontsize=BODY_FONT_SIZE,
            fontcolor=theme["text"], x="(w-text_w)/2", y=str(BODY_TEXT_Y),
            enable=f"between(t,{body_start},{body_end})",
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # CTA text
    cta_text = escape_drawtext(wrap_text(script.get("cta", ""), CTA_WRAP_WIDTH))
    if cta_text:
        stream = stream.drawtext(
            fontfile=font_str, text=cta_text, fontsize=CTA_FONT_SIZE,
            fontcolor="black@0.7", x="(w-text_w)/2+3", y=f"{CTA_TEXT_Y}+3",
            enable=f"gte(t,{cta_start})",
        )
        stream = stream.drawtext(
            fontfile=font_str, text=cta_text, fontsize=CTA_FONT_SIZE,
            fontcolor=theme["accent"], x="(w-text_w)/2", y=str(CTA_TEXT_Y),
            enable=f"gte(t,{cta_start})",
            borderw=PRODUCT_TEXT_BORDER_WIDTH,
            bordercolor=PRODUCT_TEXT_BORDER_COLOR,
        )

    # Apply color grading
    stream = _apply_color_grade(stream, mood)

    # Encode
    out = ffmpeg.output(
        stream, str(output_path),
        vcodec="libx264", pix_fmt="yuv420p", t=total_duration,
    )
    out.overwrite_output().run(quiet=True)

    # Mux TTS audio
    _mux_product_audio(audio_data, output_path)

    return output_path
