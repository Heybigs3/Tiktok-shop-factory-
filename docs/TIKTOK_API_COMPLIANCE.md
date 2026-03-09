# TikTok Content Posting API — Compliance Rules

This document captures every rule our app must follow to pass TikTok's developer audit.
All rules sourced from TikTok's official developer documentation (March 2026).

---

## 1. Audit & Visibility Rules

- **Before audit:** All posted content is restricted to **private (SELF_ONLY)** visibility
- **Before audit:** Max **5 users** can post through the app in a 24-hour window
- **After audit:** Content can be posted with public visibility; restrictions are lifted
- **Post cap:** ~15 posts per day per creator account (shared across all API clients using Direct Post)
- TikTok does NOT guarantee an approval timeline — reviews are manual and can take days to weeks

## 2. User Consent & Control (Critical for Audit)

These are the rules TikTok cares about most. Violating any of these = audit failure.

### 2a. The user must always be in control
- Users must have **full awareness and control** of what is being posted to their TikTok account
- Display a **preview** of the content before posting
- Only start uploading content to TikTok **after the user has explicitly consented** (e.g., clicked a "Post" button)
- Show a **consent declaration** before the publish button

### 2b. Privacy level (who can see the video)
- Call the **`creator_info` API** to get the user's available `privacy_level_options`
- Display a **dropdown** with those options — the options shown must match what the API returns
- There must be **NO default value** — the user must manually select one
- Never hardcode or assume a privacy level

### 2c. Interaction settings (Comment, Duet, Stitch)
- Show checkboxes for Comment, Duet, and Stitch
- **None should be checked by default** — user must opt in
- If the `creator_info` API says an interaction is **disabled in the user's app settings**, grey out and disable that checkbox
- Duet and Stitch are **not applicable to photo posts** — only show "Allow Comment" for photos

### 2d. Account display
- The upload/export page must display the **creator's TikTok nickname** so the user knows which account they're posting to

### 2e. Processing notification
- Clearly notify users that after publishing, **it may take a few minutes** for the content to process and appear on their profile

## 3. Content Rules

### 3a. No branding on content
- **DO NOT** superimpose any brand name, logo, watermark, promotional branding, link, or promotional text on content shared to TikTok
- Violating this = deleted content or disabled account

### 3b. Commercial content disclosure
- If content promotes a brand, product, or service, the app must allow users to **disclose it as Commercial Content**
- This toggle must be **off by default**

### 3c. Original content
- The API is meant for **authentic creators posting original content**
- Do not use the API to spam, mass-post, or post content the user didn't create/approve

## 4. Security Rules

- **NEVER** share API credentials (client_key, client_secret) with third parties
- **NEVER** embed client_secret in open-source code or public repositories
- Store credentials securely (we use `.env` which is gitignored)
- Maintain appropriate technical and administrative controls for credential security

## 5. Developer Conduct

- Respond **immediately** to any TikTok communication about security, privacy, or compliance
- Be **clear and honest** about the app's purpose — no deceptive or misleading communication
- Do not create false identities on the TikTok Developer Site
- Do not use the API to attack, spam, or denial-of-service anyone
- Respect API **rate limits and throttling**
- Do not act in a manner detrimental to TikTok's reputation

## 6. Violations & Consequences

- TikTok may **audit your app at any time** (through monitoring, user complaints, etc.)
- Violations lead to **immediate revocation** of the integration
- Plus a **permanent ban** on all future integrations by the developer's account and business entity
- This is not a slap on the wrist — it's a one-strike-you're-out policy

---

## How This Affects Our Code (Implementation Checklist)

When building Phase 4 (Publisher), we must:

- [ ] Call `creator_info` API before every post to get fresh privacy/interaction options
- [ ] Build a CLI (or web) upload page that shows:
  - Creator's TikTok nickname
  - Video preview (or at minimum, file path + metadata)
  - Privacy level dropdown (no default, options from API)
  - Comment/Duet/Stitch checkboxes (unchecked by default, greyed out if disabled)
  - Commercial content toggle (off by default)
  - Consent declaration + explicit "Post" confirmation
- [ ] Show a "processing may take a few minutes" message after posting
- [ ] Never watermark or brand the rendered videos
- [ ] Store TikTok client_key and client_secret in `.env` only
- [ ] Implement OAuth flow to get user access tokens
- [ ] Handle token refresh (access tokens expire)
- [ ] Respect the ~15 posts/day/account limit

---

*Sources: [Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines), [Developer Guidelines](https://developers.tiktok.com/doc/our-guidelines-developer-guidelines), [Content Posting API Get Started](https://developers.tiktok.com/doc/content-posting-api-get-started), [Query Creator Info](https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info), [Direct Post Reference](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)*
