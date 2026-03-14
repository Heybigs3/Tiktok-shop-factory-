"""
image_generator.py — Gemini API scene image generator.

Takes product images and script visual hints, generates styled lifestyle/context
scene variations using Google's Gemini image model via the google-genai SDK.
50 free images/day via AI Studio.

Caveat: Gemini may hallucinate product details (~6% error rate).
Fine for lifestyle backgrounds; risky for close-up product label shots.
We generate scene images, not product detail shots.

Usage:
    python -m src.renderers.image_generator
"""

from io import BytesIO
from pathlib import Path

from rich import print as rprint

from src.utils.config import (
    DATA_RAW_DIR,
    DATA_SCRIPTS_DIR,
    GOOGLE_AI_API_KEY,
    OUTPUT_IMAGES_DIR,
    load_pipeline_config,
)
from src.utils.data_io import load_latest

# ── Gemini model for image generation ──
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

# ── Prompt templates per video style ──
SCENE_PROMPTS = {
    "product_showcase": (
        "Professional product photography of {product_title} on a {background} background. "
        "Soft studio lighting, clean composition, vertical 9:16 aspect ratio. "
        "Lifestyle context: {context}. No text overlays."
    ),
    "ugc_showcase": (
        "Casual authentic photo of {product_title} in an everyday setting. "
        "Natural lighting, UGC style as if taken with a phone. "
        "Vertical 9:16, {background} tones. {context}."
    ),
    "comparison": (
        "Clean comparison layout with {product_title} highlighted. "
        "Minimal {background} background, professional product photography. "
        "Vertical 9:16 aspect ratio. {context}."
    ),
}

# ── Background style → context mapping ──
BACKGROUND_CONTEXTS = {
    "warm": "warm golden tones, cozy bathroom shelf setting",
    "cool": "cool blue tones, modern minimalist bathroom",
    "energetic": "vibrant colorful background, dynamic composition",
    "calm": "soft pastel tones, serene spa-like setting",
    "default": "neutral clean background, professional studio",
}


def _build_scene_prompt(
    product_title: str,
    video_style: str,
    mood: str = "default",
    scene_index: int = 0,
) -> str:
    """Build a prompt for Gemini image generation."""
    template = SCENE_PROMPTS.get(video_style, SCENE_PROMPTS["product_showcase"])
    background = BACKGROUND_CONTEXTS.get(mood, BACKGROUND_CONTEXTS["default"])

    contexts = [
        "product displayed prominently",
        "product in use, hands visible",
        "product on a shelf with complementary items",
        "close-up of product texture or packaging",
        "product in a lifestyle flat-lay arrangement",
    ]
    context = contexts[scene_index % len(contexts)]

    return template.format(
        product_title=product_title,
        background=background,
        context=context,
    )


def _get_client():
    """Initialize and return the Gemini client. Returns None if unavailable."""
    if not GOOGLE_AI_API_KEY:
        return None

    try:
        from google import genai
        return genai.Client(api_key=GOOGLE_AI_API_KEY)
    except ImportError:
        rprint("[red]google-genai not installed. Run: pip install google-genai[/red]")
        return None
    except Exception as e:
        rprint(f"[red]Gemini client init failed: {e}[/red]")
        return None


def generate_scene_image(
    prompt: str,
    output_path: Path,
    reference_image_path: Path | None = None,
    client=None,
) -> Path | None:
    """
    Generate a single scene image using the Gemini API.

    Args:
        prompt: Text prompt describing the scene
        output_path: Where to save the generated image
        reference_image_path: Optional product image for style reference
        client: Gemini client instance (created if not provided)

    Returns:
        Path to the generated image, or None on failure
    """
    if client is None:
        client = _get_client()
        if client is None:
            return None

    try:
        from google.genai import types
    except ImportError:
        rprint("[red]google-genai not installed[/red]")
        return None

    # Build contents — text prompt, optionally with a reference image
    contents = []

    if reference_image_path and reference_image_path.exists():
        image_bytes = reference_image_path.read_bytes()
        suffix = reference_image_path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    contents.append(prompt)

    try:
        response = client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                temperature=0.8,
            ),
        )
    except Exception as e:
        rprint(f"[red]Gemini API error: {e}[/red]")
        return None

    # Extract the generated image from the response
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.inline_data is not None:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(part.inline_data.data)
                    return output_path
    except Exception as e:
        rprint(f"[red]Failed to parse Gemini response: {e}[/red]")
        return None

    rprint("[yellow]Gemini returned no image data[/yellow]")
    return None


def generate_script_images(
    script: dict,
    product: dict | None = None,
    num_scenes: int = 3,
) -> list[Path]:
    """
    Generate scene images for a single script.

    Args:
        script: Script dict with visual_hints
        product: Optional product data (title, local_images)
        num_scenes: Number of scene images to generate (3-5)

    Returns:
        List of paths to generated images
    """
    script_id = script.get("script_id", "unknown")[:8]
    output_dir = OUTPUT_IMAGES_DIR / script_id
    output_dir.mkdir(parents=True, exist_ok=True)

    hints = script.get("visual_hints", {})
    if not isinstance(hints, dict):
        hints = {}

    mood = hints.get("mood", "default")
    video_style = hints.get("video_style", "product_showcase")

    # Determine product title
    product_title = "the product"
    reference_image = None
    if product:
        product_title = product.get("title", "the product")
        local_images = product.get("local_images", [])
        if local_images:
            ref_path = Path(local_images[0])
            if ref_path.exists():
                reference_image = ref_path

    # Reuse one client for all scenes
    client = _get_client()

    generated = []
    for i in range(num_scenes):
        prompt = _build_scene_prompt(product_title, video_style, mood, i)
        output_path = output_dir / f"scene_{i:02d}.png"

        rprint(f"    [dim]Generating scene {i + 1}/{num_scenes}...[/dim]")
        result = generate_scene_image(prompt, output_path, reference_image, client=client)

        if result:
            generated.append(result)
        else:
            # Fallback: use original product image if available
            if reference_image and reference_image.exists():
                import shutil
                fallback_path = output_dir / f"scene_{i:02d}_fallback.jpg"
                shutil.copy2(reference_image, fallback_path)
                generated.append(fallback_path)
                rprint(f"    [yellow]Using original product image as fallback[/yellow]")

    return generated


def generate_all(
    scripts: list[dict],
    products: list[dict] | None = None,
) -> dict[str, list[Path]]:
    """
    Generate scene images for all scripts.

    Args:
        scripts: List of script dicts
        products: Optional list of product dicts (matched by index)

    Returns:
        Dict mapping script_id (first 8 chars) → list of image paths
    """
    results = {}

    # Build product lookup by product_id for explicit matching
    product_map = {}
    if products:
        for p in products:
            pid = p.get("product_id", "")
            if pid:
                product_map[pid] = p

    for i, script in enumerate(scripts):
        script_id = script.get("script_id", f"unknown_{i}")[:8]

        # Match product by product_id (explicit), fall back to index
        product_id = script.get("product_id", "")
        product = product_map.get(product_id)
        if product is None and products and i < len(products):
            product = products[i]

        rprint(f"  [{i + 1}/{len(scripts)}] Generating images for [cyan]{script_id}[/cyan]...")
        images = generate_script_images(script, product)
        results[script_id] = images

        if images:
            rprint(f"    [green]{len(images)} images generated[/green]")
        else:
            rprint(f"    [yellow]No images generated[/yellow]")

    return results


def run() -> dict[str, list[Path]]:
    """Entry point: load scripts + products → generate scene images."""
    rprint("[bold blue]Scene Image Generator (Gemini)[/bold blue]")
    rprint("-" * 40)

    if not GOOGLE_AI_API_KEY:
        rprint("[red]GOOGLE_AI_API_KEY not set in .env[/red]")
        rprint("Get a free key at https://aistudio.google.com/apikey")
        return {}

    # Load latest scripts
    scripts = load_latest(DATA_SCRIPTS_DIR, "scripts")
    if not scripts:
        rprint("[yellow]No scripts found. Run the generator first.[/yellow]")
        return {}

    # Load latest products (optional)
    products = load_latest(DATA_RAW_DIR, "products")
    if products:
        rprint(f"[green]Found {len(products)} products for image reference[/green]")
    else:
        rprint("[dim]No product data — generating generic scenes[/dim]")

    rprint(f"\n[bold]Generating scene images for {len(scripts)} scripts...[/bold]")
    results = generate_all(scripts, products)

    total = sum(len(imgs) for imgs in results.values())
    rprint(f"\n[bold green]Generated {total} scene images[/bold green]")
    rprint(f"[dim]Output: {OUTPUT_IMAGES_DIR}[/dim]")

    return results


if __name__ == "__main__":
    run()
