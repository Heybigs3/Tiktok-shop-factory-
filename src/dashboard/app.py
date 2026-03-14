"""app.py — FastAPI routes and API endpoints for the dashboard."""

import html
import subprocess
import sys
import threading
from pathlib import Path

from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.utils.config import OUTPUT_DIR, check_api_keys
from src.dashboard.accounts import (
    load_accounts,
    get_account,
    create_account,
    update_account,
    delete_account,
    get_account_config,
    save_account_config,
)
from src.dashboard.services import (
    match_scripts_to_videos,
    list_all_scripts,
    get_pipeline_status,
    clear_videos,
    hex_to_css,
)
from src.dashboard.queue_service import (
    load_queue,
    add_to_queue,
    update_queue_item,
    remove_from_queue,
    get_week_view,
)
from src.dashboard.product_service import (
    get_product_status,
    get_product_stats,
)
from src.dashboard.publish_service import (
    get_ready_to_post,
    get_posts_today,
    load_post_history,
    record_post,
    build_caption,
    load_posting_notes,
    save_posting_notes,
)
from src.dashboard.analyzer_service import (
    get_style_bible,
    get_comparison_report,
    get_analysis_stats,
    get_scraped_analysis_details,
    get_rendered_analysis_details,
)

# ── App setup ────────────────────────────────────────────────────────────────

DASHBOARD_DIR = Path(__file__).parent
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

app = FastAPI(title="TikTok Factory — Mission Control")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount video output directory for inline playback
if OUTPUT_DIR.exists():
    app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Add hex_to_css as a global template function
templates.env.globals["hex_to_css"] = hex_to_css


# ── Account context helper ──────────────────────────────────────────────────

def _get_active_account_id(request: Request) -> str:
    """Read account_id from cookie, default to 'default'."""
    return request.cookies.get("account_id", "default")


def _base_context(request: Request, active_page: str = "") -> dict:
    """Common template context: account list, active account, nav counts."""
    account_id = _get_active_account_id(request)
    accounts = load_accounts()
    active_account = get_account(account_id)
    if not active_account:
        active_account = get_account("default")
        account_id = "default"

    # Badge shows ready-to-post count (more useful for VA than total video count)
    ready_count = len(get_ready_to_post(account_id))

    return {
        "request": request,
        "accounts": accounts,
        "active_account": active_account,
        "account_id": account_id,
        "active_page": active_page,
        "video_count": ready_count,
    }


# ── Toast helper ─────────────────────────────────────────────────────────────

def _make_toast(message: str, toast_type: str = "success") -> str:
    """Return an OOB HTML snippet that injects a toast into #toast-container."""
    safe_message = html.escape(message)
    return (
        '<div id="toast-container" hx-swap-oob="afterbegin">'
        f'<div class="toast toast-{toast_type}" onclick="dismissToast(this)">{safe_message}</div>'
        '</div>'
    )


# ── In-memory pipeline run state (single-user local tool) ───────────────────

_pipeline_runs: dict[str, dict] = {}

PHASE_MODULES = {
    "scrape": "src.scrapers.trend_scraper",
    "generate": "src.generators.script_generator",
    "render": "src.renderers.video_builder",
}


def _run_phase_background(phase: str, module: str, account_id: str = "default"):
    """Run a pipeline phase in a background thread."""
    run_key = f"{account_id}_{phase}"
    _pipeline_runs[run_key] = {"status": "running", "error": None}
    try:
        result = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            _pipeline_runs[run_key] = {"status": "done", "error": None}
        else:
            stderr = result.stderr[-500:] if result.stderr else "Unknown error"
            _pipeline_runs[run_key] = {"status": "failed", "error": stderr}
    except subprocess.TimeoutExpired:
        _pipeline_runs[run_key] = {"status": "failed", "error": "Timed out (5 min)"}
    except Exception as e:
        _pipeline_runs[run_key] = {"status": "failed", "error": str(e)}


def _get_run(phase: str, account_id: str = "default") -> dict:
    """Get pipeline run status, checking both scoped and legacy keys."""
    run_key = f"{account_id}_{phase}"
    return _pipeline_runs.get(run_key, _pipeline_runs.get(phase, {}))


# ── Page routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def videos_page(request: Request, week_offset: int = 0):
    """Videos page — ready-to-post cards, week strip, video gallery, post history."""
    ctx = _base_context(request, "videos")
    account_id = ctx["account_id"]

    # Ready-to-post data (from publish service)
    ready_videos = get_ready_to_post(account_id)
    posts_today = get_posts_today(account_id)
    posting_notes = load_posting_notes(account_id)

    # Pre-build caption for each video
    for video in ready_videos:
        video["_caption"] = build_caption(video.get("script") or {})

    # Week strip data
    today = datetime.now().date()
    this_monday = today - timedelta(days=today.weekday())
    start_date = this_monday + timedelta(weeks=week_offset)
    week_data = get_week_view(account_id, start_date)

    # Video gallery (simplified — no filters, no unrendered)
    videos = match_scripts_to_videos(account_id)

    # Recent posts (last 3, newest first)
    recent_posts = list(reversed(load_post_history(account_id)))[:3]

    ctx.update({
        "ready_videos": ready_videos,
        "posts_today": posts_today,
        "posting_notes": posting_notes,
        "week_data": week_data,
        "week_offset": week_offset,
        "today": today.isoformat(),
        "videos": videos,
        "recent_posts": recent_posts,
    })
    return templates.TemplateResponse(request, "videos.html", ctx)


@app.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    """Products tracking page — simplified for VA."""
    ctx = _base_context(request, "products")
    account_id = ctx["account_id"]

    product_statuses = get_product_status(account_id)
    stats = get_product_stats(account_id)

    ctx.update({
        "products": product_statuses,
        "stats": stats,
    })
    return templates.TemplateResponse(request, "products.html", ctx)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page — pipeline, config, analysis, accounts."""
    ctx = _base_context(request, "settings")
    account_id = ctx["account_id"]

    # Pipeline data
    status = get_pipeline_status(account_id)
    config = get_account_config(account_id)
    api_keys = check_api_keys()
    runs = {}
    for phase in PHASE_MODULES:
        runs[phase] = _get_run(phase, account_id)
    runs["publish"] = {}

    # Analysis data
    style_bible = get_style_bible()
    report = get_comparison_report()
    stats = get_analysis_stats()

    ctx.update({
        "phases": status,
        "config": config,
        "api_keys": api_keys,
        "runs": runs,
        "style_bible": style_bible,
        "report": report,
        "stats": stats,
    })
    return templates.TemplateResponse(request, "settings.html", ctx)


# ── Redirects for old routes ─────────────────────────────────────────────────

@app.get("/pipeline")
async def pipeline_redirect():
    return RedirectResponse(url="/settings#pipeline", status_code=302)

@app.get("/queue")
async def queue_redirect():
    return RedirectResponse(url="/", status_code=302)

@app.get("/publish")
async def publish_redirect():
    return RedirectResponse(url="/", status_code=302)

@app.get("/accounts")
async def accounts_redirect():
    return RedirectResponse(url="/settings#accounts", status_code=302)

@app.get("/analyze")
async def analyze_redirect():
    return RedirectResponse(url="/settings#analyze", status_code=302)


# ── Account API endpoints ───────────────────────────────────────────────────

# TODO: Replace HX-Redirect with partial swap to avoid full-page reload
@app.post("/api/accounts/{account_id}/activate", response_class=HTMLResponse)
async def activate_account(request: Request, account_id: str):
    """Set the active account cookie and redirect."""
    account = get_account(account_id)
    if not account:
        return HTMLResponse("Account not found", status_code=404)
    response = HTMLResponse("", status_code=200, headers={"HX-Redirect": "/"})
    response.set_cookie("account_id", account_id, max_age=31536000)
    return response


@app.get("/api/accounts")
async def api_accounts_list():
    """JSON list of all accounts."""
    return load_accounts()


@app.post("/api/accounts", response_class=HTMLResponse)
async def api_create_account(request: Request):
    """Create a new account. Returns HTMX fragment."""
    form = await request.form()
    name = form.get("name", "").strip()
    niche = form.get("niche", "").strip()
    if not name:
        return HTMLResponse(
            _make_toast("Account name is required", "error"),
            status_code=400,
        )
    account = create_account(name, niche)
    toast = _make_toast(f"Created account: {account['name']}")
    # Return redirect to reload the page
    return HTMLResponse(toast, headers={"HX-Redirect": "/settings#accounts"})


@app.put("/api/accounts/{account_id}", response_class=HTMLResponse)
async def api_update_account(request: Request, account_id: str):
    """Update an account. Returns HTMX fragment."""
    form = await request.form()
    updates = {}
    if form.get("name"):
        updates["name"] = form["name"].strip()
    if form.get("niche"):
        updates["niche"] = form["niche"].strip()
    updated = update_account(account_id, updates)
    if not updated:
        return HTMLResponse("Not found", status_code=404)
    toast = _make_toast(f"Updated: {updated['name']}")
    return HTMLResponse(toast, headers={"HX-Redirect": "/settings#accounts"})


@app.delete("/api/accounts/{account_id}", response_class=HTMLResponse)
async def api_delete_account(request: Request, account_id: str):
    """Delete an account. Blocks deletion of default."""
    if not delete_account(account_id):
        return HTMLResponse(
            _make_toast("Cannot delete this account", "error"),
            status_code=400,
        )
    toast = _make_toast("Account deleted")
    return HTMLResponse(toast, headers={"HX-Redirect": "/settings#accounts"})


# ── Video/Script API endpoints ──────────────────────────────────────────────

@app.get("/api/videos")
async def api_videos(request: Request):
    """JSON list of video metadata."""
    account_id = _get_active_account_id(request)
    videos = match_scripts_to_videos(account_id)
    for v in videos:
        v["path"] = str(v["path"])
        if v.get("script"):
            v["script"].pop("_timing", None)
    return videos


@app.get("/api/scripts")
async def api_scripts(request: Request):
    """JSON list of all scripts."""
    account_id = _get_active_account_id(request)
    return list_all_scripts(account_id)


@app.get("/api/script/{script_id}", response_class=HTMLResponse)
async def api_script_detail(request: Request, script_id: str):
    """Return HTML fragment for a single script's details (slide-out panel)."""
    account_id = _get_active_account_id(request)
    scripts = list_all_scripts(account_id)
    script = None
    for s in scripts:
        if s.get("script_id", "")[:8] == script_id[:8]:
            script = s
            break

    if not script:
        return HTMLResponse('<div class="p-6 text-gray-500">Script not found</div>')

    return templates.TemplateResponse(request, "_script_detail.html", {
        "script": script,
    })


@app.get("/api/status")
async def api_status(request: Request):
    """Pipeline status, API keys, and config."""
    account_id = _get_active_account_id(request)
    return {
        "phases": get_pipeline_status(account_id),
        "api_keys": check_api_keys(),
        "config": get_account_config(account_id),
    }


# ── Pipeline control endpoints ──────────────────────────────────────────────

@app.delete("/api/videos", response_class=HTMLResponse)
async def delete_videos(request: Request):
    """Delete all rendered videos. Returns updated Render phase card + toast."""
    account_id = _get_active_account_id(request)
    count = clear_videos(account_id)

    phase_id = "render"
    phase_data = get_pipeline_status(account_id)[phase_id]
    run = _get_run(phase_id, account_id)

    card_html = templates.TemplateResponse(request, "_pipeline_card.html", {
        "phase_id": phase_id,
        "phase": phase_data,
        "run": run,
    }).body.decode()

    toast_html = _make_toast(f"Cleared {count} video(s)")
    return HTMLResponse(card_html + toast_html)


@app.post("/api/pipeline/{phase}", response_class=HTMLResponse)
async def trigger_phase(request: Request, phase: str):
    """Trigger a pipeline phase. Returns HTMX fragment with polling."""
    if phase not in PHASE_MODULES:
        return HTMLResponse(
            f'<div class="p-4 text-red-400">Unknown phase: {phase}</div>',
            status_code=400,
        )

    account_id = _get_active_account_id(request)
    run = _get_run(phase, account_id)

    # Don't start if already running
    if run.get("status") == "running":
        return templates.TemplateResponse(request, "_pipeline_card.html", {
            "phase_id": phase,
            "phase": get_pipeline_status(account_id)[phase],
            "run": run,
        })

    # Start background run
    module = PHASE_MODULES[phase]
    thread = threading.Thread(
        target=_run_phase_background,
        args=(phase, module, account_id),
    )
    thread.daemon = True
    thread.start()

    return templates.TemplateResponse(request, "_pipeline_card.html", {
        "phase_id": phase,
        "phase": get_pipeline_status(account_id)[phase],
        "run": _get_run(phase, account_id),
    })


@app.post("/api/pipeline/run-all", response_class=HTMLResponse)
async def trigger_run_all(request: Request):
    """Chain all phases: scrape → generate → render in background."""
    account_id = _get_active_account_id(request)

    def _run_all():
        for phase in ["scrape", "generate", "render"]:
            module = PHASE_MODULES[phase]
            _run_phase_background(phase, module, account_id)
            run_key = f"{account_id}_{phase}"
            if _pipeline_runs.get(run_key, {}).get("status") == "failed":
                break

    thread = threading.Thread(target=_run_all)
    thread.daemon = True
    thread.start()

    toast = _make_toast("Pipeline started: Scrape → Generate → Render", "info")
    return HTMLResponse(toast)


@app.get("/api/pipeline/{phase}/status", response_class=HTMLResponse)
async def poll_phase_status(request: Request, phase: str):
    """Poll running phase status. Returns HTMX fragment + toast on finish."""
    account_id = _get_active_account_id(request)
    run = _get_run(phase, account_id)
    phase_data = get_pipeline_status(account_id).get(phase, {})

    card_html = templates.TemplateResponse(request, "_pipeline_card.html", {
        "phase_id": phase,
        "phase": phase_data,
        "run": run,
    }).body.decode()

    # Append toast when phase finishes
    status = run.get("status", "")
    if status == "done":
        card_html += _make_toast(f"{phase_data.get('label', phase)} completed!")
    elif status == "failed":
        card_html += _make_toast(f"{phase_data.get('label', phase)} failed", "error")

    return HTMLResponse(card_html)


# ── Config API ──────────────────────────────────────────────────────────────

@app.put("/api/config", response_class=HTMLResponse)
async def save_config(request: Request):
    """Save pipeline config edits for the active account."""
    account_id = _get_active_account_id(request)
    form = await request.form()

    config = get_account_config(account_id)
    # Update fields from form
    if form.get("niche"):
        config["niche"] = form["niche"].strip()
    if form.get("search_queries"):
        config["search_queries"] = [q.strip() for q in form["search_queries"].split(",") if q.strip()]
    if form.get("ad_keywords"):
        config["ad_keywords"] = [k.strip() for k in form["ad_keywords"].split(",") if k.strip()]
    if form.get("hashtags"):
        config["hashtags"] = [h.strip().lstrip("#") for h in form["hashtags"].split(",") if h.strip()]
    if form.get("num_scripts"):
        try:
            config["num_scripts"] = max(1, min(int(form["num_scripts"]), 20))
        except ValueError:
            pass

    save_account_config(account_id, config)
    return HTMLResponse(_make_toast("Config saved"))


# ── Queue API endpoints ─────────────────────────────────────────────────────

@app.get("/api/queue")
async def api_queue_list(request: Request):
    """JSON list of queue items."""
    account_id = _get_active_account_id(request)
    return load_queue(account_id)


@app.post("/api/queue", response_class=HTMLResponse)
async def api_add_to_queue(request: Request):
    """Add an item to the content queue."""
    account_id = _get_active_account_id(request)
    form = await request.form()

    script_id = form.get("script_id", "").strip()
    scheduled_date = form.get("scheduled_date", "").strip()
    scheduled_time = form.get("scheduled_time", "12:00").strip()

    # Try to get hook preview from the video/script
    hook_preview = ""
    if script_id:
        scripts = list_all_scripts(account_id)
        for s in scripts:
            if s.get("script_id", "")[:8] == script_id[:8]:
                hook_preview = s.get("hook", "")[:60]
                break

    item = add_to_queue(
        account_id,
        script_id=script_id,
        scheduled_date=scheduled_date,
        scheduled_time=scheduled_time,
        hook_preview=hook_preview,
    )
    toast = _make_toast(f"Added to queue: {hook_preview or script_id[:8] or 'item'}")
    return HTMLResponse(toast, headers={"HX-Redirect": "/"})


@app.put("/api/queue/{queue_id}", response_class=HTMLResponse)
async def api_update_queue_item(request: Request, queue_id: str):
    """Update a queue item (reschedule, change status)."""
    account_id = _get_active_account_id(request)
    form = await request.form()
    updates = {}
    if form.get("scheduled_date"):
        updates["scheduled_date"] = form["scheduled_date"].strip()
    if form.get("scheduled_time"):
        updates["scheduled_time"] = form["scheduled_time"].strip()
    if form.get("status"):
        updates["status"] = form["status"].strip()

    item = update_queue_item(account_id, queue_id, updates)
    if not item:
        return HTMLResponse("Not found", status_code=404)
    toast = _make_toast("Queue item updated")
    return HTMLResponse(toast, headers={"HX-Redirect": "/"})


@app.delete("/api/queue/{queue_id}", response_class=HTMLResponse)
async def api_remove_from_queue(request: Request, queue_id: str):
    """Remove an item from the queue."""
    account_id = _get_active_account_id(request)
    if not remove_from_queue(account_id, queue_id):
        return HTMLResponse("Not found", status_code=404)
    toast = _make_toast("Removed from queue")
    return HTMLResponse(toast, headers={"HX-Redirect": "/"})


# ── Product API endpoints ───────────────────────────────────────────────────

@app.get("/api/products")
async def api_products_list(request: Request):
    """JSON list of products with pipeline status."""
    account_id = _get_active_account_id(request)
    return get_product_status(account_id)


# ── Publish API endpoints ────────────────────────────────────────────────────

@app.post("/api/publish/record", response_class=HTMLResponse)
async def publish_record_post(request: Request):
    """Record a post (mark as posted/skipped). Returns toast + refreshes page."""
    account_id = _get_active_account_id(request)
    form = await request.form()

    video_filename = form.get("video_filename", "").strip()
    script_id = form.get("script_id", "").strip()
    caption_used = form.get("caption_used", "").strip()
    tiktok_url = form.get("tiktok_url", "").strip()
    notes = form.get("notes", "").strip()
    status = form.get("status", "posted").strip()
    queue_id = form.get("queue_id", "").strip()

    if not video_filename:
        return HTMLResponse(
            _make_toast("Video filename is required", "error"),
            status_code=400,
        )

    record_post(
        account_id,
        video_filename=video_filename,
        script_id=script_id,
        caption_used=caption_used,
        tiktok_url=tiktok_url,
        notes=notes,
        queue_id=queue_id,
        status=status,
    )

    label = "Posted" if status == "posted" else "Skipped"
    toast = _make_toast(f"{label}: {video_filename}")

    ready_count = len(get_ready_to_post(account_id))
    posts_today_count = get_posts_today(account_id)
    badge_oob = (
        f'<span id="ready-badge" hx-swap-oob="true" '
        f'class="bg-gold/20 text-gold text-sm font-semibold px-3 py-1 rounded-full">'
        f'{ready_count} ready</span>'
    )
    today_oob = (
        f'<span id="today-badge" hx-swap-oob="true" '
        f'class="bg-mood-calm/20 text-mood-calm text-sm font-semibold px-3 py-1 rounded-full">'
        f'{posts_today_count} posted today</span>'
    )
    return HTMLResponse(toast + badge_oob + today_oob)


@app.get("/api/publish/history", response_class=HTMLResponse)
async def publish_history(request: Request):
    """Return post history HTML fragment."""
    account_id = _get_active_account_id(request)
    history = load_post_history(account_id)
    # Show newest first, limit to last 20
    history = list(reversed(history))[:20]

    if not history:
        return HTMLResponse(
            '<div class="bg-navy-800 rounded-xl border border-navy-600 p-8 text-center">'
            '<p class="text-gray-500">No posts recorded yet. Mark a video as posted to start tracking.</p>'
            '</div>'
        )

    rows = []
    for post in history:
        tiktok_link = ""
        raw_url = post.get("tiktok_url", "")
        if raw_url and raw_url.startswith(("http://", "https://")):
            safe_url = html.escape(raw_url, quote=True)
            tiktok_link = f'<a href="{safe_url}" target="_blank" rel="noopener" class="text-gold hover:underline">View</a>'

        status_class = "text-mood-calm" if post.get("status") == "posted" else "text-gray-400"
        caption_preview = (post.get("caption_used") or "")[:50]
        if len(post.get("caption_used", "")) > 50:
            caption_preview += "..."

        posted_at = post.get("posted_at", "")[:16].replace("T", " ")

        safe_filename = html.escape(post.get("video_filename", ""))
        safe_caption = html.escape(caption_preview)
        safe_status = html.escape(post.get("status", ""))
        safe_notes = html.escape(post.get("notes", ""))

        rows.append(
            f'<tr class="border-t border-navy-600">'
            f'<td class="px-4 py-3 text-sm text-white">{safe_filename}</td>'
            f'<td class="px-4 py-3 text-sm text-gray-400">{safe_caption}</td>'
            f'<td class="px-4 py-3 text-sm text-gray-500">{posted_at}</td>'
            f'<td class="px-4 py-3 text-sm">{tiktok_link}</td>'
            f'<td class="px-4 py-3 text-sm {status_class} uppercase font-semibold">{safe_status}</td>'
            f'<td class="px-4 py-3 text-sm text-gray-500">{safe_notes}</td>'
            f'</tr>'
        )

    table_html = (
        '<div class="bg-navy-800 rounded-xl border border-navy-600 overflow-hidden">'
        '<table class="w-full">'
        '<thead><tr class="text-xs text-gray-500 uppercase tracking-wider">'
        '<th class="px-4 py-3 text-left">Video</th>'
        '<th class="px-4 py-3 text-left">Caption</th>'
        '<th class="px-4 py-3 text-left">Posted At</th>'
        '<th class="px-4 py-3 text-left">TikTok</th>'
        '<th class="px-4 py-3 text-left">Status</th>'
        '<th class="px-4 py-3 text-left">Notes</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table></div>'
    )

    return HTMLResponse(table_html)


@app.get("/api/publish/notes", response_class=HTMLResponse)
async def publish_get_notes(request: Request):
    """Return posting notes."""
    account_id = _get_active_account_id(request)
    notes = load_posting_notes(account_id)
    return HTMLResponse(notes)


@app.put("/api/publish/notes", response_class=HTMLResponse)
async def publish_save_notes(request: Request):
    """Save posting notes, return toast."""
    account_id = _get_active_account_id(request)
    form = await request.form()
    notes = form.get("notes", "").strip()
    save_posting_notes(account_id, notes)
    return HTMLResponse(_make_toast("Posting notes saved"))


@app.get("/api/publish/caption/{video_filename}")
async def publish_get_caption(request: Request, video_filename: str):
    """Return pre-built caption text for a video."""
    account_id = _get_active_account_id(request)
    videos = match_scripts_to_videos(account_id)
    for v in videos:
        if v["filename"] == video_filename:
            caption = build_caption(v.get("script") or {})
            return {"caption": caption}
    return {"caption": ""}


# ── Analyze API endpoints ─────────────────────────────────────────────────────

def _run_analyze_background(action: str, account_id: str = "default"):
    """Run an analyzer action in a background thread."""
    import subprocess
    import sys

    run_key = f"{account_id}_analyze_{action}"
    _pipeline_runs[run_key] = {"status": "running", "error": None}

    module_map = {
        "download": "src.analyzers.video_downloader",
        "analyze": "src.analyzers",
        "compare": None,  # handled inline
    }

    if action == "compare":
        try:
            from src.analyzers.comparison import compare_videos
            result = compare_videos()
            if result:
                _pipeline_runs[run_key] = {"status": "done", "error": None}
            else:
                _pipeline_runs[run_key] = {"status": "failed", "error": "Comparison returned no results"}
        except Exception as e:
            _pipeline_runs[run_key] = {"status": "failed", "error": str(e)}
        return

    module = module_map.get(action)
    if not module:
        _pipeline_runs[run_key] = {"status": "failed", "error": f"Unknown action: {action}"}
        return

    try:
        result = subprocess.run(
            [sys.executable, "-c",
             f"from {module} import {'download_top_videos' if action == 'download' else 'run_full_pipeline'}; "
             f"{'download_top_videos' if action == 'download' else 'run_full_pipeline'}()"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            _pipeline_runs[run_key] = {"status": "done", "error": None}
        else:
            stderr = result.stderr[-500:] if result.stderr else "Unknown error"
            _pipeline_runs[run_key] = {"status": "failed", "error": stderr}
    except subprocess.TimeoutExpired:
        _pipeline_runs[run_key] = {"status": "failed", "error": "Timed out (10 min)"}
    except Exception as e:
        _pipeline_runs[run_key] = {"status": "failed", "error": str(e)}


@app.post("/api/analyze/download", response_class=HTMLResponse)
async def analyze_download(request: Request):
    """Download top videos for analysis in background."""
    account_id = _get_active_account_id(request)
    thread = threading.Thread(
        target=_run_analyze_background,
        args=("download", account_id),
    )
    thread.daemon = True
    thread.start()
    return HTMLResponse(_make_toast("Downloading top videos...", "info"))


@app.post("/api/analyze/run", response_class=HTMLResponse)
async def analyze_run(request: Request):
    """Run video analysis pipeline in background."""
    account_id = _get_active_account_id(request)
    thread = threading.Thread(
        target=_run_analyze_background,
        args=("analyze", account_id),
    )
    thread.daemon = True
    thread.start()
    return HTMLResponse(_make_toast("Analyzing all videos...", "info"))


@app.post("/api/analyze/compare", response_class=HTMLResponse)
async def analyze_compare(request: Request):
    """Run comparison between scraped and rendered videos."""
    account_id = _get_active_account_id(request)
    thread = threading.Thread(
        target=_run_analyze_background,
        args=("compare", account_id),
    )
    thread.daemon = True
    thread.start()
    return HTMLResponse(_make_toast("Running comparison...", "info"))
