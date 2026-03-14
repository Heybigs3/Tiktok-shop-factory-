"""
kalodata_scraper.py — Playwright-based Kalodata product scraper.

Uses browser automation to scrape top-performing product data from Kalodata's
web UI. Different from the Apify-based scrapers — uses Playwright to drive
a headless Chromium browser instead of calling an API.

Collects: product name, price, revenue estimate, sales volume, trend direction,
top video links, and product images.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python -m src.scrapers.kalodata_scraper
"""

import asyncio
import re
import time
from pathlib import Path

import requests
from rich import print as rprint
from rich.table import Table

from src.utils.config import (
    DATA_RAW_DIR,
    KALODATA_EMAIL,
    KALODATA_PASSWORD,
    PRODUCT_IMAGES_DIR,
    load_pipeline_config,
)
from src.utils.data_io import save_json

# ── Kalodata URLs ──
KALODATA_LOGIN_URL = "https://kalodata.com/login"
KALODATA_PRODUCTS_URL = "https://kalodata.com/products"


def _random_delay(min_sec: float = 1.0, max_sec: float = 3.0) -> float:
    """Generate a human-like random delay between actions."""
    import random
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def _download_image(url: str, save_path: Path) -> bool:
    """Download a product image to local storage. Returns True on success."""
    try:
        resp = requests.get(url, timeout=15, stream=True)
        if resp.status_code == 200:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(resp.content)
            rprint(f"[dim]  Downloaded: {save_path.name}[/dim]")
            return True
        else:
            rprint(f"[yellow]  Download failed (HTTP {resp.status_code}): {url[:80]}[/yellow]")
    except Exception as e:
        rprint(f"[yellow]  Download error: {e} — {url[:80]}[/yellow]")
    return False


async def _save_debug_screenshot(page, label: str = "debug") -> None:
    """Save a debug screenshot to help diagnose scraping failures."""
    try:
        screenshot_path = DATA_RAW_DIR / f"debug_screenshot_{label}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        rprint(f"[dim]Debug screenshot saved: {screenshot_path}[/dim]")
    except Exception as e:
        rprint(f"[yellow]Could not save debug screenshot: {e}[/yellow]")


async def _login(page, max_retries: int = 3) -> bool:
    """Log into Kalodata with credentials from .env. Returns True on success.

    Retries up to max_retries times with 5s delays between attempts.
    Uses multiple fallback selectors for the password field.
    """
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                rprint(f"[yellow]Login retry {attempt}/{max_retries} (waiting 5s)...[/yellow]")
                time.sleep(5)

            await page.goto(KALODATA_LOGIN_URL, wait_until="networkidle", timeout=30000)
            _random_delay(1.0, 2.0)

            # Fill email
            email_input = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]')
            await email_input.fill(KALODATA_EMAIL)
            _random_delay(0.5, 1.0)

            # Fill password — try multiple selectors for resilience
            password_input = None
            for selector in [
                'input[type="password"]',
                'input[name="password"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="Password"]',
            ]:
                candidate = page.locator(selector)
                if await candidate.count() > 0:
                    password_input = candidate.first
                    break

            if password_input is None:
                rprint(f"[red]Attempt {attempt}: Could not find password field[/red]")
                continue

            await password_input.fill(KALODATA_PASSWORD)
            _random_delay(0.5, 1.0)

            # Click login button
            login_btn = page.locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")')
            await login_btn.first.click()

            # Wait for navigation after login
            await page.wait_for_load_state("networkidle", timeout=15000)
            _random_delay(2.0, 3.0)

            # Verify login succeeded by checking we're not still on login page
            if "login" in page.url.lower():
                rprint(f"[red]Attempt {attempt}: Login failed — still on login page[/red]")
                continue

            rprint("[green]Logged into Kalodata[/green]")
            return True

        except Exception as e:
            rprint(f"[red]Attempt {attempt}: Kalodata login error: {e}[/red]")

    rprint(f"[red]All {max_retries} login attempts failed[/red]")
    return False


async def _scrape_products(page, config: dict) -> list[dict]:
    """Navigate to products page and extract product data."""
    kalodata_config = config.get("product_sources", {}).get("kalodata", {})
    categories = kalodata_config.get("categories", ["skincare"])
    sort_by = kalodata_config.get("sort_by", "revenue")
    time_range = kalodata_config.get("time_range", "last7Day")
    max_results = kalodata_config.get("max_results", 10)

    # Build URL with query params
    category_param = ",".join(categories)
    url = f"{KALODATA_PRODUCTS_URL}?category={category_param}&sort={sort_by}&time={time_range}"

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        _random_delay(2.0, 4.0)

        # Scroll to load more products (lazy loading)
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            _random_delay(0.8, 1.5)

    except Exception as e:
        rprint(f"[red]Failed to load products page: {e}[/red]")
        return []

    products = []

    # Extract product cards from the page
    # Kalodata uses a table/card layout — selectors may need updating if site changes
    product_rows = await page.locator(
        'tr[class*="product"], div[class*="product-card"], '
        'div[class*="product-item"], table tbody tr'
    ).all()

    for i, row in enumerate(product_rows[:max_results]):
        try:
            product = await _extract_product_data(row, i)
            if product:
                img_count = len(product.get("image_urls", []))
                title = product.get("title", "")[:40]
                if img_count == 0:
                    rprint(f"[yellow]  Warning: 0 images found for '{title}'[/yellow]")
                else:
                    rprint(f"[dim]  Product {i+1}: '{title}' — {img_count} image(s)[/dim]")
                products.append(product)
        except Exception:
            continue

    return products


async def _extract_product_data(row, index: int) -> dict | None:
    """Extract structured data from a single product row/card element."""
    try:
        # Try multiple selector patterns for title
        title = ""
        for selector in ['[class*="title"]', '[class*="name"]', 'a', 'td:nth-child(2)']:
            el = row.locator(selector).first
            text = await el.text_content() if await el.count() > 0 else ""
            if text and len(text.strip()) > 3:
                title = text.strip()
                break

        if not title:
            return None

        # Extract price
        price_text = ""
        for selector in ['[class*="price"]', 'td:nth-child(3)']:
            el = row.locator(selector).first
            text = await el.text_content() if await el.count() > 0 else ""
            if text and "$" in text:
                price_text = text.strip()
                break

        price = 0.0
        if price_text:
            price_match = re.search(r'\$?([\d,.]+)', price_text)
            if price_match:
                price = float(price_match.group(1).replace(",", ""))

        # Extract revenue
        revenue_text = ""
        for selector in ['[class*="revenue"]', '[class*="sales"]', 'td:nth-child(4)']:
            el = row.locator(selector).first
            text = await el.text_content() if await el.count() > 0 else ""
            if text:
                revenue_text = text.strip()
                break

        revenue_estimate = _parse_number(revenue_text)

        # Extract sales volume
        volume_text = ""
        for selector in ['[class*="volume"]', '[class*="units"]', 'td:nth-child(5)']:
            el = row.locator(selector).first
            text = await el.text_content() if await el.count() > 0 else ""
            if text:
                volume_text = text.strip()
                break

        sales_volume = _parse_number(volume_text)

        # Extract trend direction
        trend = "flat"
        trend_el = row.locator('[class*="trend"], [class*="arrow"], [class*="change"]').first
        if await trend_el.count() > 0:
            trend_text = await trend_el.text_content() or ""
            trend_class = await trend_el.get_attribute("class") or ""
            if "up" in trend_class.lower() or "+" in trend_text:
                trend = "rising"
            elif "down" in trend_class.lower() or "-" in trend_text:
                trend = "falling"

        # Extract product image
        image_urls = []
        img_els = await row.locator("img").all()
        for img in img_els[:3]:
            src = await img.get_attribute("src") or ""
            if src and not src.startswith("data:"):
                image_urls.append(src)

        # Extract link for top videos
        top_video_links = []
        link_els = await row.locator('a[href*="tiktok"], a[href*="video"]').all()
        for link in link_els[:5]:
            href = await link.get_attribute("href") or ""
            if href:
                top_video_links.append(href)

        product_id = f"kd_{index:04d}_{re.sub(r'[^a-z0-9]', '', title.lower()[:20])}"

        return {
            "product_id": product_id,
            "title": title,
            "price": price,
            "category": "",  # filled from config downstream
            "revenue_estimate": revenue_estimate,
            "sales_volume": sales_volume,
            "trend_direction": trend,
            "top_video_links": top_video_links,
            "image_urls": image_urls,
            "local_images": [],
            "source": "kalodata",
        }

    except Exception:
        return None


def _parse_number(text: str) -> int:
    """Parse a number string like '$1.2M', '45.3K', '12,000' into an integer."""
    if not text:
        return 0

    text = text.strip().replace("$", "").replace(",", "")

    match = re.search(r'([\d.]+)\s*([KkMmBb])?', text)
    if not match:
        return 0

    num = float(match.group(1))
    suffix = (match.group(2) or "").upper()

    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    return int(num * multipliers.get(suffix, 1))


def _download_product_images(products: list[dict]) -> list[dict]:
    """Download product images to assets/product_images/. Returns updated products."""
    for product in products:
        local_paths = []
        urls = product.get("image_urls", [])
        title = product.get("title", "")[:30]
        if not urls:
            rprint(f"[yellow]  No image URLs for '{title}' — skipping download[/yellow]")
        for i, url in enumerate(urls):
            ext = Path(url).suffix or ".jpg"
            if len(ext) > 5:
                ext = ".jpg"
            filename = f"{product['product_id']}_img{i}{ext}"
            save_path = PRODUCT_IMAGES_DIR / filename

            if _download_image(url, save_path):
                local_paths.append(str(save_path))

        product["local_images"] = local_paths

    return products


async def scrape_kalodata() -> list[dict]:
    """
    Full Kalodata scrape: login → navigate → extract → download images → save.

    Returns list of product dicts, or empty list on failure.
    """
    if not KALODATA_EMAIL or not KALODATA_PASSWORD:
        rprint("[yellow]Kalodata credentials not set in .env — skipping product scrape[/yellow]")
        rprint("[dim]Set KALODATA_EMAIL and KALODATA_PASSWORD to enable[/dim]")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        rprint("[red]Playwright not installed. Run:[/red]")
        rprint("  pip install playwright && playwright install chromium")
        return []

    config = load_pipeline_config()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # Step 1: Login
            logged_in = await _login(page)
            if not logged_in:
                rprint("[yellow]Kalodata login failed — skipping product scrape[/yellow]")
                await _save_debug_screenshot(page, "login_failed")
                return []

            # Step 2: Scrape products
            products = await _scrape_products(page, config)
            rprint(f"[green]Scraped {len(products)} products from Kalodata[/green]")

            if not products:
                rprint("[yellow]No products found — check category filters in pipeline_config.json[/yellow]")
                await _save_debug_screenshot(page, "no_products")
                return []

            # Step 3: Download images
            rprint("[blue]Downloading product images...[/blue]")
            products = _download_product_images(products)
            img_count = sum(len(p.get("local_images", [])) for p in products)
            rprint(f"[green]Downloaded {img_count} product images[/green]")

            if img_count == 0:
                rprint("[yellow]Warning: 0 images downloaded — saving debug screenshot[/yellow]")
                await _save_debug_screenshot(page, "no_images")

            # Step 4: Tag categories from config
            categories = config.get("product_sources", {}).get("kalodata", {}).get("categories", [])
            category_str = ", ".join(categories)
            for product in products:
                product["category"] = category_str

            # Step 5: Validate data before saving
            for product in products:
                title = product.get("title", "")[:30]
                if not product.get("product_id"):
                    rprint(f"[yellow]Warning: Missing product_id for '{title}'[/yellow]")
                if not product.get("image_urls"):
                    rprint(f"[yellow]Warning: Missing image_urls for '{title}'[/yellow]")

            # Step 6: Save
            save_json(products, "products", DATA_RAW_DIR)

            return products

        finally:
            await browser.close()


def display_products(products: list[dict]) -> None:
    """Pretty-print scraped products as a rich table."""
    if not products:
        rprint("[yellow]No products to display.[/yellow]")
        return

    table = Table(title="Kalodata Products", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Product", style="bold cyan", max_width=35)
    table.add_column("Price", style="green", justify="right", width=10)
    table.add_column("Revenue", style="yellow", justify="right", width=12)
    table.add_column("Sales", style="white", justify="right", width=10)
    table.add_column("Trend", style="white", width=8)
    table.add_column("Images", style="dim", justify="right", width=6)

    for i, p in enumerate(products, 1):
        trend_style = {
            "rising": "[green]rising[/green]",
            "falling": "[red]falling[/red]",
            "flat": "[dim]flat[/dim]",
        }
        table.add_row(
            str(i),
            p.get("title", "")[:35],
            f"${p.get('price', 0):.2f}" if p.get("price") else "-",
            f"${_parse_number(str(p.get('revenue_estimate', 0))):,}" if p.get("revenue_estimate") else "-",
            str(p.get("sales_volume", "-")),
            trend_style.get(p.get("trend_direction", "flat"), "[dim]flat[/dim]"),
            str(len(p.get("local_images", []))),
        )

    rprint(table)


def run() -> list[dict]:
    """Entry point: scrape Kalodata products and display results."""
    rprint("[bold blue]Kalodata Product Scraper[/bold blue]")
    rprint("-" * 40)

    products = asyncio.run(scrape_kalodata())

    if products:
        display_products(products)

    return products


if __name__ == "__main__":
    run()
