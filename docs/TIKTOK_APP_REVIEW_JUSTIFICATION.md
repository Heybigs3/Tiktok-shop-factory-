# TikTok Developer App Review — Written Justification

## Application Name
TikTok Content Factory

## What does your app do?
TikTok Content Factory is a content creation tool that helps creators produce short-form vertical videos optimized for TikTok. The app analyzes trending content patterns, generates video scripts, and renders ready-to-post videos. Creators review, customize, and publish videos to their TikTok accounts through a fully interactive consent-driven flow.

## Why does your app need TikTok integration?
Our app generates videos specifically formatted for TikTok (9:16 vertical, under 60 seconds). The Content Posting API integration allows creators to publish directly from the tool after previewing their content and configuring all post settings. Without the API, creators must manually transfer video files and re-enter captions — a friction point that discourages consistent posting.

## How does your app benefit TikTok users?
1. **More high-quality content on TikTok** — Our tool produces polished, trend-aligned videos that contribute to a vibrant content ecosystem. Every video is reviewed and approved by the creator before posting.
2. **Lowers the barrier to content creation** — Creators who struggle with scripting, editing, or production can use our tool to produce professional-quality content, increasing their posting consistency and audience growth.
3. **Proper AI content disclosure** — All videos posted through our app are automatically labeled as AI-generated content (`is_aigc: true`), ensuring transparency with viewers per TikTok's community guidelines.
4. **Full creator control** — The publishing flow requires explicit consent at every step: video selection, privacy level, interaction settings, commercial disclosure, and final confirmation. No content is ever posted without the creator's direct approval.

## How do you handle user data?
- **OAuth 2.0 tokens** are stored locally on the user's machine (not on external servers). Tokens are auto-refreshed and never transmitted to third parties.
- **No user data is collected or stored** beyond the OAuth token needed for posting.
- **No analytics, tracking, or user profiling** is performed.

## What scopes does your app request?
| Scope | Purpose |
|-------|---------|
| `user.info.basic` | Display creator nickname and avatar during publish flow |
| `video.upload` | Upload video files to TikTok |
| `video.publish` | Post videos to creator's TikTok profile |

## Content Compliance
- All content is AI-generated and labeled as such (`is_aigc: true`)
- No branding, watermarks, or promotional overlays are added to videos
- Commercial content disclosure is supported (brand partnerships and own-business promotion)
- Creator must explicitly consent before every post
- Privacy level is selected by the creator with no default value
- Interaction settings (comments, duets, stitches) are all disabled by default
- Daily posting is capped at 15 posts per creator to respect API rate limits

## Expected Usage
- **Daily active creators:** 1-5 (small team / individual creators)
- **Posts per day:** 5-10 across all users
- **Content type:** Short-form vertical videos (15-60 seconds)

## Contact Information
[Fill in: your name, email, company/organization name]
