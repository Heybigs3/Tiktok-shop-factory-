"""
niche_radar.py — Dynamic niche scanner for TikTok Shop affiliate marketing.

Scans multiple niches, scores them on virality potential, and recommends
which niches to launch new accounts for. This is the intelligence layer
that replaces hardcoded niche selection in pipeline_config.json.

Scoring model is tuned for GROWTH MODE (new accounts need followers before
TikTok Shop eligibility at 5k). Weights favor engagement and velocity over
revenue signals.

Inputs:
  - NICHE_CATALOG: 10 pre-selected niches with queries, hashtags, categories
  - Apify trending videos + hashtag stats (live data)
  - Kalodata product data (optional, Playwright-based)

Outputs:
  - Scored niches sorted by virality potential
  - Top 3 recommendations with diversity enforcement
  - Per-account pipeline_config.json generation
  - Dashboard account creation

Usage:
  python -m src.scrapers.niche_radar
"""

import time
from datetime import datetime, timezone

from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.utils.config import APIFY_API_TOKEN, KALODATA_EMAIL, DATA_RAW_DIR, load_pipeline_config
from src.utils.data_io import save_json, load_latest

console = Console()

# ── Niche catalog ─────────────────────────────────────────────────────────────
# 10 starter niches chosen for TikTok Shop affiliate viability:
# high commission, visual products, proven demand.

NICHE_CATALOG = {
    "skincare": {
        "queries": ["skincare routine viral"],
        "hashtags": ["skincareroutine", "glowup"],
        "kalodata_cat": "Beauty",
    },
    "haircare": {
        "queries": ["hair transformation product"],
        "hashtags": ["hairtok", "haircare"],
        "kalodata_cat": "Beauty",
    },
    "supplements": {
        "queries": ["supplement results tiktok"],
        "hashtags": ["supplementtok", "wellness"],
        "kalodata_cat": "Health",
    },
    "kitchen_gadgets": {
        "queries": ["kitchen gadget tiktok"],
        "hashtags": ["kitchentok", "kitchengadgets"],
        "kalodata_cat": "Home",
    },
    "fitness_gear": {
        "queries": ["fitness product review"],
        "hashtags": ["fitnesstok", "workoutgear"],
        "kalodata_cat": "Sports",
    },
    "pet_products": {
        "queries": ["pet product tiktok viral"],
        "hashtags": ["pettok", "dogproducts"],
        "kalodata_cat": "Pet",
    },
    "phone_accessories": {
        "queries": ["phone accessory tiktok"],
        "hashtags": ["techtok", "phonecase"],
        "kalodata_cat": "Electronics",
    },
    "cleaning": {
        "queries": ["cleaning product satisfying"],
        "hashtags": ["cleantok", "cleaningmotivation"],
        "kalodata_cat": "Home",
    },
    "baby_products": {
        "queries": ["baby product must have"],
        "hashtags": ["momtok", "babymusthaves"],
        "kalodata_cat": "Baby",
    },
    "fashion_accessories": {
        "queries": ["fashion accessory haul"],
        "hashtags": ["fashiontok", "accessoryhaul"],
        "kalodata_cat": "Fashion",
    },
}

# ── Scoring weights (must sum to 1.0) ─────────────────────────────────────────
SCORING_WEIGHTS = {
    "engagement": 0.35,
    "velocity": 0.25,
    "gap": 0.20,
    "momentum": 0.20,
}

# Quick scan uses these 5 niches (diverse categories, high TikTok Shop potential)
QUICK_SCAN_NICHES = ["skincare", "kitchen_gadgets", "pet_products", "fitness_gear", "fashion_accessories"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value to [0, 100] range."""
    return max(0.0, min(100.0, value))


def _get_video_stats(video: dict) -> dict:
    """Extract normalized stats from an Apify video dict (handles both field conventions)."""
    return {
        "plays": video.get("playCount") if "playCount" in video else video.get("plays", 0) or 0,
        "likes": video.get("diggCount") if "diggCount" in video else video.get("likes", 0) or 0,
        "shares": video.get("shareCount") if "shareCount" in video else video.get("shares", 0) or 0,
        "comments": video.get("commentCount") if "commentCount" in video else video.get("comments", 0) or 0,
    }


def _get_create_time(video: dict) -> float | None:
    """Get video creation timestamp. Returns epoch seconds or None."""
    ct = video.get("createTime") or video.get("createTimeISO")
    if ct is None:
        return None
    if isinstance(ct, (int, float)):
        return float(ct)
    # Try ISO format
    try:
        dt = datetime.fromisoformat(str(ct).replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _engagement_rate(stats: dict) -> float:
    """Calculate engagement rate from stats dict. Returns 0-100 percentage."""
    plays = stats.get("plays", 0)
    if plays <= 0:
        return 0.0
    interactions = stats.get("likes", 0) + stats.get("comments", 0) + stats.get("shares", 0)
    return (interactions / plays) * 100


# ── Sub-score calculators ─────────────────────────────────────────────────────

def calc_engagement_score(videos: list[dict]) -> float:
    """Score 0-100 based on median engagement rate of top 5 videos.

    Baseline: 3% = 50, 8%+ = 100, <1% = 10.
    """
    if not videos:
        return 0.0

    # Take top 5 by play count
    sorted_vids = sorted(videos, key=lambda v: _get_video_stats(v).get("plays", 0), reverse=True)[:5]
    rates = [_engagement_rate(_get_video_stats(v)) for v in sorted_vids]

    if not rates:
        return 0.0

    # Median
    rates.sort()
    mid = len(rates) // 2
    median_rate = rates[mid] if len(rates) % 2 == 1 else (rates[mid - 1] + rates[mid]) / 2

    # Scale: <1% → 10, 3% → 50, 8%+ → 100
    if median_rate <= 0:
        return 0.0
    elif median_rate < 1.0:
        score = 10.0 * median_rate
    elif median_rate < 3.0:
        score = 10.0 + (median_rate - 1.0) * 20.0  # 1% → 10, 3% → 50
    elif median_rate < 8.0:
        score = 50.0 + (median_rate - 3.0) * 10.0  # 3% → 50, 8% → 100
    else:
        score = 100.0

    return normalize_score(score)


def calc_velocity_score(videos: list[dict]) -> float:
    """Score 0-100 based on recency-weighted engagement.

    Videos from last 48h get full weight, older videos decay.
    """
    if not videos:
        return 0.0

    now = datetime.now(timezone.utc).timestamp()
    weighted_sum = 0.0
    count = 0

    for video in videos[:10]:  # Cap at 10
        stats = _get_video_stats(video)
        rate = _engagement_rate(stats)
        create_time = _get_create_time(video)

        if create_time is None:
            # No timestamp — use neutral weight
            recency_weight = 0.5
        else:
            age_hours = (now - create_time) / 3600
            if age_hours < 48:
                recency_weight = 1.0
            elif age_hours < 96:
                recency_weight = 0.7
            elif age_hours < 168:
                recency_weight = 0.4
            else:
                recency_weight = 0.1

        weighted_sum += rate * recency_weight
        count += 1

    if count == 0:
        return 0.0

    avg_weighted = weighted_sum / count

    # Scale similar to engagement: 2% weighted avg → 50, 6%+ → 100
    if avg_weighted <= 0:
        return 0.0
    elif avg_weighted < 2.0:
        score = avg_weighted * 25.0  # 0 → 0, 2% → 50
    elif avg_weighted < 6.0:
        score = 50.0 + (avg_weighted - 2.0) * 12.5  # 2% → 50, 6% → 100
    else:
        score = 100.0

    return normalize_score(score)


def calc_gap_score(videos: list[dict], products: list[dict] | None = None) -> float:
    """Score 0-100 based on demand/supply gap.

    High product demand (Kalodata) + low creator saturation = opportunity.
    Falls back to 50 (neutral) if no product data.
    """
    if products is None or len(products) == 0:
        return 50.0  # Neutral — no Kalodata data

    # Demand: count of products with significant revenue
    demand = len(products)

    # Supply: count of videos with >100k views (saturation indicator)
    supply = 0
    for v in videos:
        stats = _get_video_stats(v)
        if stats.get("plays", 0) > 100_000:
            supply += 1

    gap_ratio = demand / max(supply, 1)

    # Scale: ratio 1 → 30, ratio 3+ → 80, ratio 5+ → 100
    if gap_ratio < 1:
        score = gap_ratio * 30.0
    elif gap_ratio < 3:
        score = 30.0 + (gap_ratio - 1.0) * 25.0  # 1 → 30, 3 → 80
    elif gap_ratio < 5:
        score = 80.0 + (gap_ratio - 3.0) * 10.0  # 3 → 80, 5 → 100
    else:
        score = 100.0

    return normalize_score(score)


def calc_momentum_score(hashtags: list[dict], previous_hashtags: list[dict] | None = None) -> float:
    """Score 0-100 based on week-over-week hashtag view growth.

    No previous data → 50 (neutral).
    """
    if not hashtags:
        return 0.0

    if previous_hashtags is None or len(previous_hashtags) == 0:
        return 50.0  # Neutral — first scan, no history

    # Build lookup of previous views by hashtag name
    prev_lookup = {}
    for h in previous_hashtags:
        name = h.get("name", "") or h.get("hashtag", "")
        views = h.get("viewCount", 0) or h.get("views", 0)
        if name:
            prev_lookup[name.lower().lstrip("#")] = views

    growths = []
    for h in hashtags:
        name = (h.get("name", "") or h.get("hashtag", "")).lower().lstrip("#")
        current_views = h.get("viewCount", 0) or h.get("views", 0)
        prev_views = prev_lookup.get(name)

        if prev_views and prev_views > 0:
            pct_change = ((current_views - prev_views) / prev_views) * 100
            growths.append(pct_change)

    if not growths:
        return 50.0  # No matching hashtags to compare

    avg_growth = sum(growths) / len(growths)

    # Scale: 0% → 40, 5% → 60, 20%+ → 100, negative → down to 0
    if avg_growth < 0:
        score = max(0.0, 40.0 + avg_growth * 2.0)  # -20% → 0
    elif avg_growth < 5:
        score = 40.0 + avg_growth * 4.0  # 0% → 40, 5% → 60
    elif avg_growth < 20:
        score = 60.0 + (avg_growth - 5.0) * (40.0 / 15.0)  # 5% → 60, 20% → 100
    else:
        score = 100.0

    return normalize_score(score)


# ── Core functions ────────────────────────────────────────────────────────────

def scan_niche(niche_key: str, max_results: int = 5) -> dict:
    """Scan a single niche. Returns raw signals (videos, hashtags, products).

    Reuses existing scrapers: trend_scraper + hashtag_tracker + kalodata_scraper.
    """
    if niche_key not in NICHE_CATALOG:
        rprint(f"[red]Unknown niche: {niche_key}[/red]")
        return {"niche": niche_key, "videos": [], "hashtags": [], "products": [], "scanned_at": ""}

    niche = NICHE_CATALOG[niche_key]
    scanned_at = datetime.now(timezone.utc).isoformat()

    rprint(f"\n[bold cyan]Scanning niche:[/bold cyan] {niche_key}")

    # 1. Apify trending videos
    videos = []
    try:
        from src.scrapers.trend_scraper import scrape_trending_videos
        for query in niche["queries"]:
            results = scrape_trending_videos(query, max_results=max_results)
            videos.extend(results)
    except Exception as e:
        rprint(f"[yellow]Trend scraper failed for {niche_key}: {e}[/yellow]")

    # 2. Hashtag stats
    hashtags = []
    try:
        from src.scrapers.hashtag_tracker import scrape_hashtags
        hashtags = scrape_hashtags(niche["hashtags"], max_results=10)
    except Exception as e:
        rprint(f"[yellow]Hashtag tracker failed for {niche_key}: {e}[/yellow]")

    # 3. Kalodata products (optional — only if creds set)
    products = []
    if KALODATA_EMAIL:
        try:
            from src.scrapers.kalodata_scraper import scrape_products
            products = scrape_products(category=niche["kalodata_cat"])
        except Exception as e:
            rprint(f"[yellow]Kalodata scraper failed for {niche_key}: {e}[/yellow]")

    return {
        "niche": niche_key,
        "videos": videos,
        "hashtags": hashtags,
        "products": products,
        "scanned_at": scanned_at,
    }


def score_niche(scan_result: dict) -> dict:
    """Score a scanned niche. Returns scores + reasoning."""
    niche_key = scan_result["niche"]
    videos = scan_result.get("videos", [])
    hashtags = scan_result.get("hashtags", [])
    products = scan_result.get("products", [])

    # Load previous scan for momentum comparison
    previous_scan = load_latest(DATA_RAW_DIR, "niche_radar")
    previous_hashtags = None
    if previous_scan and isinstance(previous_scan, dict):
        for entry in previous_scan.get("results", []):
            if entry.get("niche") == niche_key:
                previous_hashtags = entry.get("hashtags", [])
                break

    # Calculate sub-scores
    engagement = calc_engagement_score(videos)
    velocity = calc_velocity_score(videos)
    gap = calc_gap_score(videos, products if products else None)
    momentum = calc_momentum_score(hashtags, previous_hashtags)

    # Weighted total
    total = (
        SCORING_WEIGHTS["engagement"] * engagement
        + SCORING_WEIGHTS["velocity"] * velocity
        + SCORING_WEIGHTS["gap"] * gap
        + SCORING_WEIGHTS["momentum"] * momentum
    )

    # Build reasoning
    reasons = []
    if engagement >= 60:
        reasons.append(f"High engagement ({engagement:.0f}/100)")
    elif engagement <= 30:
        reasons.append(f"Low engagement ({engagement:.0f}/100)")

    if velocity >= 60:
        reasons.append("Recent viral activity")
    if gap >= 60:
        reasons.append("Good demand/supply gap")
    if momentum >= 60:
        reasons.append("Hashtags growing")
    elif momentum <= 30:
        reasons.append("Hashtags declining")

    if not reasons:
        reasons.append("Average across all signals")

    # Extract top hooks for reference
    top_hooks = []
    from src.scrapers.trend_scraper import extract_hooks
    if videos:
        hooks = extract_hooks(videos[:5])
        top_hooks = [h["hook_text"] for h in hooks if h.get("hook_text")]

    return {
        "niche": niche_key,
        "kalodata_cat": NICHE_CATALOG.get(niche_key, {}).get("kalodata_cat", ""),
        "total_score": round(total, 1),
        "scores": {
            "engagement": round(engagement, 1),
            "velocity": round(velocity, 1),
            "gap": round(gap, 1),
            "momentum": round(momentum, 1),
        },
        "reasoning": ". ".join(reasons),
        "top_hooks": top_hooks[:3],
        "video_count": len(videos),
        "scanned_at": scan_result.get("scanned_at", ""),
    }


def scan_all_niches(quick: bool = False) -> list[dict]:
    """Scan and score all niches (or top 5 if quick=True). Returns sorted by score."""
    niche_keys = QUICK_SCAN_NICHES if quick else list(NICHE_CATALOG.keys())

    rprint(f"\n[bold]Scanning {len(niche_keys)} niches ({'quick' if quick else 'full'} scan)…[/bold]")

    results = []
    for i, key in enumerate(niche_keys, 1):
        rprint(f"\n[dim]({i}/{len(niche_keys)})[/dim]")
        scan = scan_niche(key)
        scored = score_niche(scan)
        # Attach raw data for saving
        scored["hashtags"] = scan.get("hashtags", [])
        results.append(scored)

        # Delay between Apify calls to avoid rate limits
        if i < len(niche_keys):
            time.sleep(2)

    # Sort by total score descending
    results.sort(key=lambda x: x["total_score"], reverse=True)

    # Save results
    save_data = {
        "scan_type": "quick" if quick else "full",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    save_json(save_data, "niche_radar", DATA_RAW_DIR)

    return results


def recommend_accounts(scored_niches: list[dict], num_accounts: int = 3) -> list[dict]:
    """Pick top N niches for new accounts. Ensures diversity (no two from same kalodata_cat)."""
    if not scored_niches:
        return []

    # Sort by score (should already be sorted, but ensure)
    sorted_niches = sorted(scored_niches, key=lambda x: x["total_score"], reverse=True)

    selected = []
    used_categories = set()

    for niche in sorted_niches:
        if len(selected) >= num_accounts:
            break

        cat = niche.get("kalodata_cat", "")

        # Skip if we already have this category (diversity enforcement)
        if cat in used_categories:
            continue

        # Skip zero-score niches (no data)
        if niche["total_score"] <= 0:
            continue

        selected.append(niche)
        if cat:
            used_categories.add(cat)

    # If diversity filtering left us short, fill from remaining (allow same category)
    if len(selected) < num_accounts:
        for niche in sorted_niches:
            if len(selected) >= num_accounts:
                break
            if niche not in selected and niche["total_score"] > 0:
                selected.append(niche)

    return selected


def build_niche_config(niche_key: str, scan_data: dict | None = None) -> dict:
    """Generate a pipeline_config.json for a specific niche account.

    Uses scan data to populate search queries, hashtags, product sources.
    Falls back to NICHE_CATALOG defaults if no scan data.
    """
    if niche_key not in NICHE_CATALOG:
        return {}

    catalog = NICHE_CATALOG[niche_key]

    # Start from current config as template
    base_config = load_pipeline_config()

    # Build niche-specific config
    config = {
        "niche": niche_key,
        "search_queries": catalog["queries"],
        "ad_keywords": [niche_key.replace("_", " ")],
        "hashtags": catalog["hashtags"],
        "max_results_per_query": base_config.get("max_results_per_query", 10),
        "num_scripts": base_config.get("num_scripts", 5),
        "processing": base_config.get("processing", {
            "min_hook_length": 15,
            "min_plays": 0,
            "sort_by": "engagement_rate",
        }),
        "music": base_config.get("music", {
            "enabled": True,
            "volume": 0.15,
        }),
        "tts": base_config.get("tts", {
            "enabled": True,
            "model": "eleven_multilingual_v2",
            "stability": 0.5,
            "similarity_boost": 0.75,
        }),
        "video_style": "product_showcase",
        "motion_method": "ken_burns",
        "product_sources": {
            "kalodata": {
                "categories": [catalog["kalodata_cat"].lower()],
                "sort_by": "revenue",
                "time_range": "last7Day",
                "max_results": 10,
            },
        },
    }

    # Enrich from scan data if available
    if scan_data:
        top_hooks = scan_data.get("top_hooks", [])
        if top_hooks:
            config["reference_hooks"] = top_hooks

    return config


def setup_accounts(recommendations: list[dict]) -> list[dict]:
    """Create dashboard accounts for recommended niches. Returns created accounts."""
    from src.dashboard.accounts import create_account, save_account_config

    created = []
    for rec in recommendations:
        niche_key = rec["niche"]
        name = niche_key.replace("_", " ").title()

        rprint(f"\n[cyan]Creating account:[/cyan] {name} ({niche_key})")

        account = create_account(name=name, niche=niche_key)

        # Generate and save niche-specific config
        config = build_niche_config(niche_key, scan_data=rec)
        save_account_config(account["id"], config)

        created.append(account)
        rprint(f"[green]Created:[/green] {account['name']} (ID: {account['id']})")

    return created


# ── Display ───────────────────────────────────────────────────────────────────

def display_results(results: list[dict]) -> None:
    """Display scored niches as a Rich table."""
    if not results:
        rprint("[yellow]No results to display.[/yellow]")
        return

    table = Table(title="Niche Radar Results", show_lines=True)
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Niche", style="cyan", max_width=20)
    table.add_column("Score", style="bold white", justify="right", width=6)
    table.add_column("Engage", justify="right", width=6)
    table.add_column("Velocity", justify="right", width=6)
    table.add_column("Gap", justify="right", width=6)
    table.add_column("Momentum", justify="right", width=6)
    table.add_column("Reasoning", style="dim", max_width=40)

    for i, r in enumerate(results, 1):
        scores = r.get("scores", {})

        # Color the total score
        total = r["total_score"]
        if total >= 60:
            score_str = f"[green]{total:.0f}[/green]"
        elif total >= 40:
            score_str = f"[yellow]{total:.0f}[/yellow]"
        else:
            score_str = f"[red]{total:.0f}[/red]"

        table.add_row(
            str(i),
            r["niche"].replace("_", " ").title(),
            score_str,
            f"{scores.get('engagement', 0):.0f}",
            f"{scores.get('velocity', 0):.0f}",
            f"{scores.get('gap', 0):.0f}",
            f"{scores.get('momentum', 0):.0f}",
            r.get("reasoning", "")[:40],
        )

    rprint(table)


def display_recommendations(recommendations: list[dict]) -> None:
    """Display account recommendations."""
    if not recommendations:
        rprint("[yellow]No recommendations available.[/yellow]")
        return

    rprint("\n[bold]Recommended Accounts[/bold]")
    rprint("─" * 50)

    for i, rec in enumerate(recommendations, 1):
        niche = rec["niche"].replace("_", " ").title()
        score = rec["total_score"]
        reasoning = rec.get("reasoning", "")
        cat = rec.get("kalodata_cat", "")

        rprint(f"\n  [bold cyan]{i}. {niche}[/bold cyan] (Score: {score:.0f}, Category: {cat})")
        rprint(f"     [dim]{reasoning}[/dim]")

        hooks = rec.get("top_hooks", [])
        if hooks:
            rprint(f"     Top hooks:")
            for hook in hooks[:2]:
                rprint(f"       • {hook[:60]}")


# ── CLI ───────────────────────────────────────────────────────────────────────

MENU = {
    "1": "Full scan (all 10 niches)",
    "2": "Quick scan (top 5 niches)",
    "3": "Scan specific niche",
    "4": "View latest results",
    "5": "Setup accounts from latest scan",
    "6": "Back",
}


def _view_latest() -> list[dict] | None:
    """Load and display the latest scan results."""
    data = load_latest(DATA_RAW_DIR, "niche_radar")
    if not data:
        rprint("[yellow]No previous scan found. Run a scan first.[/yellow]")
        return None

    results = data.get("results", []) if isinstance(data, dict) else []
    scan_type = data.get("scan_type", "unknown") if isinstance(data, dict) else "unknown"
    scanned_at = data.get("scanned_at", "") if isinstance(data, dict) else ""

    rprint(f"\n[dim]Scan type: {scan_type} | Scanned at: {scanned_at}[/dim]")
    display_results(results)
    return results


def run_cli():
    """Interactive CLI menu for Niche Radar."""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Niche Radar[/bold cyan]  [dim]Dynamic Niche Scanner[/dim]",
            border_style="cyan",
        )
    )

    if not APIFY_API_TOKEN:
        rprint("[red]WARNING: APIFY_API_TOKEN not set — live scans will fail[/red]")

    console.print()
    for key, label in MENU.items():
        style = "dim" if key == "6" else "white"
        console.print(f"  [{style}][bold]{key}[/bold]) {label}[/{style}]")

    console.print()
    choice = console.input("[bold cyan]Pick an option:[/bold cyan] ").strip()

    if choice == "1":
        results = scan_all_niches(quick=False)
        display_results(results)
        recommendations = recommend_accounts(results)
        display_recommendations(recommendations)

    elif choice == "2":
        results = scan_all_niches(quick=True)
        display_results(results)
        recommendations = recommend_accounts(results)
        display_recommendations(recommendations)

    elif choice == "3":
        rprint("\n[bold]Available niches:[/bold]")
        for key in NICHE_CATALOG:
            rprint(f"  • {key}")
        niche = console.input("\n[cyan]Enter niche key:[/cyan] ").strip()
        if niche in NICHE_CATALOG:
            scan = scan_niche(niche)
            scored = score_niche(scan)
            display_results([scored])
        else:
            rprint(f"[red]Unknown niche: {niche}[/red]")

    elif choice == "4":
        _view_latest()

    elif choice == "5":
        results = _view_latest()
        if results:
            recommendations = recommend_accounts(results)
            display_recommendations(recommendations)
            confirm = console.input("\n[cyan]Create these accounts? (y/n):[/cyan] ").strip().lower()
            if confirm == "y":
                created = setup_accounts(recommendations)
                rprint(f"\n[green]Created {len(created)} accounts![/green]")
            else:
                rprint("[dim]Cancelled.[/dim]")

    elif choice == "6":
        rprint("[dim]Back.[/dim]")
    else:
        rprint("[dim]Invalid option.[/dim]")


if __name__ == "__main__":
    run_cli()
