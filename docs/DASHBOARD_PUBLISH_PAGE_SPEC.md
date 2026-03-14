# Dashboard Publish Page — Specification

## Context

We're submitting our app for TikTok's Content Posting API audit. TikTok reviewers need to see a web-based UI they can click through, and we need a human in the loop for every post. The solution: a VA (virtual assistant) uses a publish page on our existing dashboard to review, configure, and post videos. The account owner (David) does the one-time OAuth login. After that, the VA handles day-to-day publishing through the browser.

This page is the most important part of passing the TikTok audit. Every compliance requirement must be visible in the UI.

## Existing Dashboard

The dashboard already runs at `localhost:8420` using FastAPI + Jinja2 + HTMX + Pico CSS (dark theme). Two pages exist:

- **Studio** — video gallery with inline players and script details
- **Pipeline** — phase status with HTMX-powered run buttons

The publish page is a new third page.

## What the Publish Page Needs to Do

A VA with zero technical knowledge opens the dashboard, sees videos ready to post, picks one, configures settings, and publishes — all through point-and-click in the browser. No terminal, no commands, no code.

---

## Page Layout

### Top Bar
- Page title: "Publish to TikTok"
- Login status: "Logged in as **[nickname]** (@username)" or "Not logged in — [Login button]"
- Daily post counter: "Posts today: 3/15"

### Section 1: Video Queue
A card grid showing all rendered videos from `output/videos/` that haven't been posted yet. Each card shows:
- Video thumbnail (or inline `<video>` player with poster frame)
- Filename
- File size
- Date rendered
- Script preview (hook, body first 100 chars, CTA) — expandable
- "Select to Publish" button

The VA clicks a card to select it, which scrolls down to Section 2.

### Section 2: Post Settings (appears after video selection)
A form with these fields, in this exact order:

1. **Video Preview** — inline video player showing the selected video. The VA should be able to watch the full video before posting.

2. **Script Details** — full hook/body/CTA text from the source script (read-only, for VA reference)

3. **Title / Caption** — text input, max 2200 characters, with character counter. Pre-filled with suggested hashtags from the script if available. VA can edit freely.

4. **Privacy Level** — dropdown populated from the `creator_info` API. **No default selection.** Placeholder text: "Select who can see this video..." TikTok requires this — the VA must actively choose.

5. **Interaction Settings** — three checkboxes, **all unchecked by default**:
   - [ ] Allow Comments
   - [ ] Allow Duets
   - [ ] Allow Stitches

   If any are disabled in the creator's TikTok settings (from `creator_info`), show them greyed out with text: "Disabled in your TikTok settings"

6. **Commercial Content** — toggle switch, **off by default**. When turned on, two sub-options appear:
   - [ ] Paid partnership / brand deal
   - [ ] Promoting your own business

   **Validation:** If the toggle is on but neither box is checked, show an error and block the publish button. TikTok specifically tests for this.

7. **AI-Generated Content Notice** — non-editable info box:
   > "This video will be labeled as AI-generated content on TikTok."

8. **Music Usage Confirmation** — non-editable info box:
   > "By posting, you agree to TikTok's Music Usage Confirmation."

9. **Publish Button** — large, prominent. Disabled until:
   - Privacy level is selected
   - Commercial disclosure is valid (if enabled, at least one type selected)
   - The VA clicks a consent checkbox: "I confirm I want to post this video"

### Section 3: Post History
A table showing recent posts:

| Video | Title | Privacy | Posted At | Status | Publish ID |
|-------|-------|---------|-----------|--------|------------|

Status should auto-refresh (HTMX poll) showing: Processing → Published or Failed.

---

## OAuth Flow (One-Time Setup)

When no valid token exists, show a landing state:

> **Not connected to TikTok**
> The account owner needs to log in once to authorize posting.
> [Connect TikTok Account] button

Clicking the button triggers the OAuth flow (opens TikTok login in a new tab, callback to localhost:8585). After success, the page refreshes and shows the logged-in state.

The token auto-refreshes (365-day refresh token), so this should only need to happen once. If the token expires and can't be refreshed, show the login prompt again.

**Important:** Only the TikTok account owner should click this button. The VA uses the dashboard after login is complete.

---

## API Calls (Backend Routes to Add)

These are the FastAPI routes the publish page needs:

### GET /api/publish/status
Returns login status, creator info, and daily post count.
```json
{
  "logged_in": true,
  "creator_nickname": "David",
  "creator_username": "david_creates",
  "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
  "comment_disabled": false,
  "duet_disabled": false,
  "stitch_disabled": true,
  "posts_today": 3,
  "max_posts_per_day": 15,
  "pre_audit_mode": false
}
```

### GET /api/publish/queue
Returns list of videos ready to publish (from `output/videos/`), with matched script data.
```json
{
  "videos": [
    {
      "filename": "e0f141c6_trending.mp4",
      "path": "output/videos/e0f141c6_trending.mp4",
      "size_kb": 2340,
      "rendered_at": "2026-03-12T14:30:00",
      "script": {
        "hook": "You won't believe...",
        "body": "Here's the thing about...",
        "cta": "Follow for more!",
        "suggested_hashtags": ["#fyp", "#skincare"]
      }
    }
  ]
}
```

### POST /api/publish/post
Accepts the form data and performs the publish. The backend handles `init_video_post()` + `upload_video_file()` + recording to the post log.
```json
{
  "video_path": "output/videos/e0f141c6_trending.mp4",
  "title": "Check this out! #fyp #skincare",
  "privacy_level": "PUBLIC_TO_EVERYONE",
  "disable_comment": false,
  "disable_duet": true,
  "disable_stitch": true,
  "brand_content_toggle": false,
  "brand_organic_toggle": false
}
```
Response:
```json
{
  "success": true,
  "publish_id": "abc123",
  "message": "Video submitted to TikTok"
}
```

### GET /api/publish/history
Returns recent post history with status.
```json
{
  "posts": [
    {
      "video": "e0f141c6_trending.mp4",
      "title": "Check this out!",
      "privacy": "PUBLIC_TO_EVERYONE",
      "posted_at": "2026-03-12T15:00:00",
      "publish_id": "abc123",
      "status": "published"
    }
  ]
}
```

### POST /api/publish/login
Triggers the OAuth flow. Returns success/failure after the callback completes.

---

## Compliance Checklist (Non-Negotiable)

These are TikTok audit requirements. Every one must be visible in the UI:

- [ ] Privacy dropdown has NO default value — user must actively select
- [ ] Interaction toggles ALL off by default — user opts in
- [ ] Disabled interactions greyed out based on creator_info API
- [ ] Commercial content toggle off by default
- [ ] If commercial is on, at least one disclosure type must be selected (block publish otherwise)
- [ ] AI-generated content notice displayed before publish
- [ ] Music Usage Confirmation text displayed before publish
- [ ] Explicit consent checkbox before publish button
- [ ] `is_aigc: true` sent in every post (backend handles this — hardcoded in `tiktok_api.py`)
- [ ] `creator_info` API called before every post to get fresh privacy options
- [ ] Daily post limit enforced (15/day) — publish button disabled when limit reached
- [ ] Video preview available before posting (VA must be able to watch the video)

---

## Pre-Audit Warning

If `privacy_level_options` from the API only contains `["SELF_ONLY"]`, show a yellow banner:

> **Pre-Audit Mode:** Your TikTok app hasn't passed the audit yet. All posts will be private (Only Me). Maximum 5 users can post per 24 hours.

---

## Design Notes

- Use the existing Pico CSS dark theme — keep it consistent with Studio and Pipeline pages
- HTMX for interactivity (form submissions, status polling, queue refresh) — no build step
- The form should work on a single page with no page reloads (HTMX partial swaps)
- Mobile-responsive — a VA might use this on a tablet
- Keep it simple — this is for a non-technical person. No jargon, no developer terminology
- Use clear labels and helper text under each form field explaining what it does

## Existing Code to Reuse

All publishing logic already exists in the `src/publishers/` package:
- `oauth_server.py` — `get_valid_token()`, `login()`, `load_token()`, `is_token_expired()`
- `tiktok_api.py` — `query_creator_info()`, `init_video_post()`, `upload_video_file()`, `check_post_status()`
- `tiktok_publisher.py` — `_load_post_log()`, `_get_posts_today()`, `_record_post()`, `_check_daily_limit()`, `_find_script_for_video()`

The dashboard just needs to wrap these in FastAPI routes and render them in HTML. Don't rewrite the publishing logic — import and call the existing functions.

## Navigation

Add "Publish" as a third nav item alongside Studio and Pipeline in the dashboard header.
