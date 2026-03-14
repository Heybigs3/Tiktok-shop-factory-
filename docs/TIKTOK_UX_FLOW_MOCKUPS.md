# TikTok Content Factory — UX Flow Mockups

> **For TikTok Developer App Review Submission**
> Convert this document to PDF before submitting.

---

## 1. Complete Publishing Flow Overview

This diagram shows the full user journey from login to post confirmation. Every decision point requires explicit user action — no auto-posting occurs at any step.

```mermaid
flowchart TD
    START([User launches Publisher]) --> LOGIN_CHECK{Saved token<br/>exists?}

    LOGIN_CHECK -->|No| OAUTH[Open TikTok OAuth<br/>login in browser]
    LOGIN_CHECK -->|Yes| EXPIRED{Token<br/>expired?}

    EXPIRED -->|Yes| REFRESH[Auto-refresh token<br/>using refresh_token]
    EXPIRED -->|No| RATE_CHECK

    OAUTH --> AUTHORIZE[User logs in &<br/>clicks Authorize]
    AUTHORIZE --> CALLBACK[OAuth callback<br/>captures code]
    CALLBACK --> TOKEN_EXCHANGE[Exchange code<br/>for access token]
    TOKEN_EXCHANGE --> SAVE_TOKEN[Save token locally]
    SAVE_TOKEN --> RATE_CHECK
    REFRESH --> RATE_CHECK

    RATE_CHECK{Daily post<br/>limit reached?}
    RATE_CHECK -->|Yes, 15/day| LIMIT_MSG[/"Display: Daily limit reached<br/>Try again tomorrow"/]
    LIMIT_MSG --> STOP([Exit])
    RATE_CHECK -->|No| CREATOR_INFO

    CREATOR_INFO[Call creator_info API<br/>Get privacy options &<br/>interaction settings]
    CREATOR_INFO --> CREATOR_DISPLAY[/"Display: Posting as<br/>[nickname] @[username]<br/>Posts today: X/15"/]

    CREATOR_DISPLAY --> VIDEO_SELECT[User selects video<br/>from output/videos/]
    VIDEO_SELECT --> PREVIEW[/"Display video preview:<br/>filename, size, script content<br/>(hook, body, CTA)"/]

    PREVIEW --> PRIVACY[User selects privacy level<br/>from API-provided options<br/>NO default value]
    PRIVACY --> INTERACTIONS[User toggles interactions<br/>Comment / Duet / Stitch<br/>ALL off by default]
    INTERACTIONS --> TITLE[User enters title/caption<br/>max 2200 chars]
    TITLE --> COMMERCIAL{User: Is this<br/>commercial content?}

    COMMERCIAL -->|No| CONFIRM
    COMMERCIAL -->|Yes| DISCLOSURE_TYPE{Must select at least one:<br/>Brand deal OR<br/>Own business}
    DISCLOSURE_TYPE --> CONFIRM

    CONFIRM[/"CONFIRM POST panel:<br/>• Video filename<br/>• Title<br/>• Privacy level<br/>• AI-generated content notice<br/>• Music Usage Confirmation<br/><br/>User must type 'yes' to proceed"/]

    CONFIRM --> CONSENT{User types<br/>'yes'?}
    CONSENT -->|No| CANCEL([Post cancelled])
    CONSENT -->|Yes| UPLOAD[Upload video to TikTok]
    UPLOAD --> LOG[Record post in daily log]
    LOG --> SUCCESS[/"Video submitted!<br/>Publish ID: [id]<br/>Check status with --status flag"/]
    SUCCESS --> DONE([Exit])

    style OAUTH fill:#1da1f2,color:#fff
    style AUTHORIZE fill:#1da1f2,color:#fff
    style CONFIRM fill:#f59e0b,color:#000
    style CONSENT fill:#f59e0b,color:#000
    style LIMIT_MSG fill:#ef4444,color:#fff
    style SUCCESS fill:#22c55e,color:#fff
    style CANCEL fill:#ef4444,color:#fff
```

---

## 2. Privacy Level Selection — No Default Value

TikTok requires that no default privacy level is pre-selected. The user must actively choose.

```mermaid
flowchart TD
    API[creator_info API returns<br/>privacy_level_options list]
    API --> DISPLAY[/"Display options from API only:<br/><br/>1. Everyone (Public)<br/>2. Friends (Mutual Followers)<br/>3. Followers Only<br/>4. Only Me (Private)<br/><br/>NO option is pre-selected"/]

    DISPLAY --> INPUT[User types a number]
    INPUT --> VALID{Valid<br/>selection?}
    VALID -->|No| ERROR[/"Please enter a number<br/>between 1 and N"/]
    ERROR --> INPUT
    VALID -->|Yes| SELECTED[/"Selected: [option name]"/]
    SELECTED --> CONTINUE([Continue to next step])

    PRE_AUDIT{Only SELF_ONLY<br/>available?}
    API --> PRE_AUDIT
    PRE_AUDIT -->|Yes| WARNING[/"Note: App has not passed audit.<br/>All posts will be PRIVATE.<br/>Max 5 users per 24 hours."/]
    WARNING --> DISPLAY
    PRE_AUDIT -->|No| DISPLAY

    style WARNING fill:#f59e0b,color:#000
    style ERROR fill:#ef4444,color:#fff
```

---

## 3. Interaction Settings — All Off By Default

TikTok requires all interaction toggles to be OFF by default. Disabled settings must be greyed out.

```mermaid
flowchart TD
    INFO[creator_info API returns:<br/>comment_disabled, duet_disabled,<br/>stitch_disabled]

    INFO --> C_CHECK{comment_disabled<br/>= true?}
    C_CHECK -->|Yes| C_GREY[/"Comments: DISABLED<br/>(greyed out — turned off<br/>in your TikTok settings)"/]
    C_CHECK -->|No| C_ASK[/"Allow Comments? (y/N)<br/>Default: OFF"/]

    INFO --> D_CHECK{duet_disabled<br/>= true?}
    D_CHECK -->|Yes| D_GREY[/"Duets: DISABLED<br/>(greyed out — turned off<br/>in your TikTok settings)"/]
    D_CHECK -->|No| D_ASK[/"Allow Duets? (y/N)<br/>Default: OFF"/]

    INFO --> S_CHECK{stitch_disabled<br/>= true?}
    S_CHECK -->|Yes| S_GREY[/"Stitches: DISABLED<br/>(greyed out — turned off<br/>in your TikTok settings)"/]
    S_CHECK -->|No| S_ASK[/"Allow Stitches? (y/N)<br/>Default: OFF"/]

    C_ASK --> RESULT
    C_GREY --> RESULT
    D_ASK --> RESULT
    D_GREY --> RESULT
    S_ASK --> RESULT
    S_GREY --> RESULT

    RESULT([Continue with settings])

    style C_GREY fill:#6b7280,color:#fff
    style D_GREY fill:#6b7280,color:#fff
    style S_GREY fill:#6b7280,color:#fff
```

---

## 4. Commercial Content Disclosure Flow

TikTok requires commercial content disclosure to be OFF by default. If enabled, at least one disclosure type must be selected.

```mermaid
flowchart TD
    START[/"Is this commercial content? (y/N)<br/>Default: No"/]

    START -->|No| DONE_NO([brand_content=false<br/>brand_organic=false])

    START -->|Yes| WARN[/"You indicated this is commercial content.<br/>You must select at least one:"/]

    WARN --> BRAND[/"Paid partnership / brand deal? (y/N)"/]
    BRAND --> OWN[/"Promoting your own business? (y/N)"/]

    OWN --> CHECK{At least one<br/>selected?}

    CHECK -->|Yes| DONE_YES([Return selections])

    CHECK -->|No| BLOCK[/"You must select at least one option.<br/>TikTok requires a disclosure type."/]
    BLOCK --> RETRY{Try again?}
    RETRY -->|Yes| BRAND
    RETRY -->|No| FALLBACK([Commercial content disabled<br/>brand_content=false<br/>brand_organic=false])

    style BLOCK fill:#ef4444,color:#fff
    style DONE_YES fill:#22c55e,color:#fff
    style DONE_NO fill:#22c55e,color:#fff
    style FALLBACK fill:#f59e0b,color:#000
```

---

## 5. Final Confirmation Panel

This is the last screen the user sees before posting. They must type "yes" to proceed.

```mermaid
flowchart TD
    PANEL[/"━━━━━━ CONFIRM POST ━━━━━━<br/><br/>Video: product_abc123.mp4<br/>Title: Check out this amazing product! #fyp<br/>Privacy: Everyone (Public)<br/><br/>⚠ AI-Generated Content: This video will be<br/>labeled as AI-generated content on TikTok.<br/><br/>By posting, you confirm this is your content<br/>and you want it published to your TikTok account.<br/><br/>By posting, you agree to TikTok's<br/>Music Usage Confirmation.<br/><br/>Note: It may take a few minutes for the video<br/>to appear on your profile after posting.<br/>━━━━━━━━━━━━━━━━━━━━━━━━━"/]

    PANEL --> PROMPT[/"Post this video to TikTok? (yes/no)"/]
    PROMPT --> DECISION{User types<br/>'yes'?}
    DECISION -->|yes| UPLOAD([Proceed to upload])
    DECISION -->|anything else| CANCEL([Post cancelled])

    style PANEL fill:#f59e0b,color:#000
    style UPLOAD fill:#22c55e,color:#fff
    style CANCEL fill:#ef4444,color:#fff
```

---

## 6. OAuth 2.0 Login Flow

```mermaid
sequenceDiagram
    participant User
    participant App as TikTok Factory
    participant Browser
    participant TikTok as TikTok OAuth
    participant Server as Local Server<br/>(port 8585)

    User->>App: Launch publisher
    App->>App: Check for saved token

    alt No token or expired
        App->>Server: Start callback server
        App->>Browser: Open TikTok auth URL
        Browser->>TikTok: Display login page
        User->>TikTok: Log in + Authorize
        TikTok->>Server: Redirect with auth code + state
        Server->>App: Return auth code
        App->>App: Verify state (CSRF protection)
        App->>TikTok: Exchange code for token
        TikTok->>App: Return access_token + refresh_token
        App->>App: Save token to data/tokens/
    else Valid token exists
        App->>App: Use saved token
    else Token expired, refresh available
        App->>TikTok: Refresh token request
        TikTok->>App: New access_token
        App->>App: Save updated token
    end

    App->>User: "Logged in to TikTok"
```

---

## 7. Daily Rate Limit Enforcement

```mermaid
flowchart TD
    LOGIN([User authenticated]) --> LOAD[Load post_log.json]
    LOAD --> COUNT[Count posts today<br/>for this creator's open_id]
    COUNT --> CHECK{posts_today<br/>>= 15?}

    CHECK -->|Yes| BLOCKED[/"Daily post limit reached<br/>(15 posts today).<br/>TikTok allows max 15 posts<br/>per day via API.<br/>Try again tomorrow."/]
    BLOCKED --> EXIT([Exit])

    CHECK -->|No| SHOW[/"Posts today: X/15<br/>(remaining: Y)"/]
    SHOW --> CONTINUE([Continue to publish flow])

    AFTER_POST([Successful upload]) --> RECORD[Write to post_log.json:<br/>date → open_id → count+1]

    style BLOCKED fill:#ef4444,color:#fff
    style SHOW fill:#22c55e,color:#fff
```

---

## 8. API Call Sequence — Publishing a Video

```mermaid
sequenceDiagram
    participant User
    participant App as TikTok Factory
    participant API as TikTok API

    Note over App: Step 1 — Get creator info (REQUIRED before every post)
    App->>API: POST /v2/post/publish/creator_info/query/
    API->>App: privacy_level_options, interaction settings,<br/>creator nickname/username
    App->>User: Display creator info + options

    Note over User: Steps 2-5 — User configures post settings
    User->>App: Select video, privacy, interactions, title
    User->>App: Configure commercial content disclosure
    User->>App: Type "yes" to confirm

    Note over App: Step 6 — Initialize post
    App->>API: POST /v2/post/publish/video/init/<br/>{privacy_level, title, is_aigc: true,<br/>disable_comment, disable_duet, disable_stitch,<br/>brand_content_toggle, brand_organic_toggle}
    API->>App: {publish_id, upload_url}

    Note over App: Step 7 — Upload video file
    App->>API: PUT upload_url<br/>Content-Type: video/mp4<br/>Content-Range: bytes 0-N/N
    API->>App: 200 OK

    App->>User: "Video submitted! Publish ID: [id]"

    Note over App: Optional — Check status
    App->>API: POST /v2/post/publish/status/fetch/<br/>{publish_id}
    API->>App: {status: processing/published/failed}
```

---

## How to Convert to PDF

### Option A: VS Code
1. Install the "Markdown Preview Mermaid Support" extension
2. Install the "Markdown PDF" extension
3. Open this file → Ctrl+Shift+P → "Markdown PDF: Export (pdf)"

### Option B: Mermaid Live Editor
1. Go to [mermaid.live](https://mermaid.live)
2. Paste each diagram individually
3. Export as PNG or SVG
4. Compile into a PDF using any document tool

### Option C: GitHub
1. Push this file to a GitHub repo
2. GitHub renders Mermaid diagrams natively
3. Print the rendered page to PDF (Ctrl+P → Save as PDF)
