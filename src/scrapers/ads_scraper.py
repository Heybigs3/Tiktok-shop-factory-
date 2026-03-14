"""
ads_scraper.py — Scrapes the TikTok Ads Library for top-performing ad creatives.

Uses the "data_xplorer/tiktok-ads-library-fast" Apify actor to find
ads that are spending big and performing well. This tells us what hooks
and formats are actually converting (not just getting views).

Why ads > organic?
  Organic virality ≠ conversion. An ad that's spending $10k+/day has been
  validated with real money. Those hooks are proven to drive purchases.

Inputs:
  - keyword or niche (e.g., "protein powder")
  - country/region filter
  - max results

Outputs:
  - List of ad creatives with: ad_id, advertiser, text, spend_estimate, cta
  - Saved to data/raw/ads_<timestamp>.json

Usage:
  python -m src.scrapers.ads_scraper
"""

from apify_client import ApifyClient
from rich import print as rprint
from rich.table import Table

from src.utils.config import APIFY_API_TOKEN, DATA_RAW_DIR, load_pipeline_config
from src.utils.data_io import save_json

# ── Apify actor ID for TikTok Ads Library ──
ADS_LIBRARY_ACTOR = "data_xplorer/tiktok-ads-library-fast"


def scrape_ads(
    keyword: str,
    country: str = "US",
    max_results: int = 30,
) -> list[dict]:
    """
    Scrape top-performing TikTok ads for a keyword.

    Args:
        keyword: Product/niche to search (e.g., "skincare")
        country: 2-letter country code for regional filtering
        max_results: Max ads to return

    Returns:
        List of ad data dicts
    """
    client = ApifyClient(APIFY_API_TOKEN)

    run_input = {
        "keyword": keyword,
        "country": country,
        "maxResults": max_results,
    }

    rprint(f"[blue]Scraping TikTok Ads Library for:[/blue] '{keyword}' (country={country}, max {max_results})")
    rprint("[dim]Running Apify actor… this may take a minute.[/dim]")

    try:
        run = client.actor(ADS_LIBRARY_ACTOR).call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    except Exception as e:
        rprint(f"[red]Apify ads scraper failed: {e}[/red]")
        return []

    rprint(f"[green]Got {len(items)} ads from TikTok Ads Library[/green]")
    return items


def analyze_ad_hooks(ads: list[dict]) -> list[dict]:
    """
    Extract hooks and CTAs from ad creatives.

    Args:
        ads: Raw ad data from scrape_ads()

    Returns:
        List of dicts with: ad_id, hook_text, cta_text, estimated_spend
    """
    hooks = []
    for ad in ads:
        ad_text = ad.get("text", "") or ad.get("adText", "") or ""

        # Extract hook: first sentence or first 100 chars
        hook_text = ""
        if ad_text:
            for end_char in [".", "!", "?"]:
                idx = ad_text.find(end_char)
                if idx != -1 and idx < 150:
                    hook_text = ad_text[: idx + 1].strip()
                    break
            if not hook_text:
                hook_text = ad_text[:100].strip()

        # Extract CTA (call-to-action) — often the last line or a button label
        cta_text = ad.get("callToAction", "") or ad.get("cta", "") or ""
        if not cta_text and ad_text:
            # Fallback: grab the last sentence as a rough CTA
            lines = [l.strip() for l in ad_text.strip().splitlines() if l.strip()]
            if len(lines) > 1:
                cta_text = lines[-1]

        hooks.append({
            "ad_id": ad.get("id", "") or ad.get("adId", ""),
            "advertiser": ad.get("advertiserName", "") or ad.get("advertiser", ""),
            "hook_text": hook_text,
            "cta_text": cta_text,
            "estimated_spend": ad.get("estimatedSpend") if "estimatedSpend" in ad else ad.get("spend", 0) or 0,
        })

    rprint(f"[green]Extracted hooks from {len(hooks)} ads[/green]")
    return hooks


# ── Run standalone ──
if __name__ == "__main__":
    rprint("[bold blue]TikTok Ads Library Scraper[/bold blue]")
    rprint("-" * 40)

    if not APIFY_API_TOKEN:
        rprint("[red]ERROR: APIFY_API_TOKEN not set in .env[/red]")
        rprint("Copy .env.example to .env and add your token.")
    else:
        config = load_pipeline_config()
        keywords = config.get("ad_keywords", ["skincare"])
        max_results = config.get("max_results_per_query", 10)

        rprint(f"[dim]Niche: {config.get('niche', 'unknown')} | Keywords: {keywords}[/dim]")

        all_ads = []
        for keyword in keywords:
            ads = scrape_ads(keyword, max_results=max_results)
            all_ads.extend(ads)

        if all_ads:
            hooks = analyze_ad_hooks(all_ads)
            save_json(all_ads, "ads", DATA_RAW_DIR)

            # Process and save enriched hooks to data/processed/
            from src.scrapers.hook_processor import process_and_save
            process_and_save([], all_ads)
            # Display a summary table
            table = Table(title="Top TikTok Ads", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Advertiser", style="cyan", max_width=20)
            table.add_column("Hook", style="white", max_width=45)
            table.add_column("CTA", style="yellow", max_width=20)
            for i, h in enumerate(hooks[:15], 1):
                table.add_row(str(i), h["advertiser"], h["hook_text"], h["cta_text"])
            rprint(table)
