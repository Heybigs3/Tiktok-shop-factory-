# TikTok Factory — Architecture

Visual documentation of the full pipeline. All diagrams render natively on GitHub using [Mermaid](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams).

---

## 1. High-Level Pipeline

The four-phase pipeline. Each phase is independent — they communicate through timestamped JSON files on disk, not function calls.

```mermaid
flowchart TD
    subgraph ext["External Services"]
        Apify["☁️ Apify Actors"]
        Claude["☁️ Claude API"]
        FFmpeg["⚙️ FFmpeg"]
        TikTok["☁️ TikTok API"]
    end

    subgraph phase1["Phase 1 — Scraping"]
        S1[trend_scraper.py]
        S2[ads_scraper.py]
        S3[hashtag_tracker.py]
    end

    subgraph phase2["Phase 2 — Script Generation"]
        G1[script_generator.py]
        G2[templates.py]
    end

    subgraph phase3["Phase 3 — Video Rendering"]
        R1[video_builder.py]
    end

    subgraph phase4["Phase 4 — Publishing"]
        P1["tiktok_publisher.py<br/>(not started)"]
    end

    subgraph data["Data Layer (timestamped JSON)"]
        D1["data/raw/<br/>trending_videos_*.json<br/>ads_*.json<br/>hashtags_*.json"]
        D2["data/scripts/<br/>scripts_*.json"]
    end

    subgraph output["Output"]
        V["output/videos/<br/>{id}_{type}.mp4"]
    end

    ENV[".env<br/>API keys & config"] -.-> phase1
    ENV -.-> phase2
    ENV -.-> phase4

    Apify --> phase1
    phase1 --> D1
    D1 --> phase2
    Claude --> phase2
    phase2 --> D2
    D2 --> phase3
    FFmpeg --> phase3
    phase3 --> V
    V --> phase4
    phase4 --> TikTok

    style ext fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style phase1 fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
    style phase2 fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style phase3 fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style phase4 fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
    style data fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
    style output fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
```

---

## 2. Phase 1 — Scrapers

Three independent scrapers hit different Apify actors and write to `data/raw/`. Each follows the same pattern: `ApifyClient` → `actor.call()` → `iterate_items()` → extract/analyze → `save_json()`.

```mermaid
flowchart LR
    subgraph input["Search Input"]
        T1["search term"]
        T2["keyword + country"]
        T3["hashtag list"]
    end

    subgraph scrapers["Scrapers"]
        TS["trend_scraper.py<br/>scrape_trending_videos()"]
        AS["ads_scraper.py<br/>scrape_ads()"]
        HT["hashtag_tracker.py<br/>scrape_hashtags()<br/>find_trending_hashtags()"]
    end

    subgraph actors["Apify Actors"]
        A1["apify/tiktok-scraper"]
        A2["data_xplorer/<br/>tiktok-ads-library-fast"]
        A3["clockworks/<br/>tiktok-hashtag-scraper"]
    end

    subgraph processing["Hook Extraction"]
        E1["extract_hooks()<br/>first sentence <150 chars"]
        E2["analyze_ad_hooks()<br/>hook + CTA text"]
        E3["raw hashtag stats<br/>sorted by views"]
    end

    subgraph output["data/raw/"]
        O1["trending_videos_*.json<br/>{video_id, author,<br/>hook_text, stats}"]
        O2["ads_*.json<br/>{ad_id, advertiser,<br/>hook_text, cta_text}"]
        O3["hashtags_*.json<br/>{name, views, videos}"]
    end

    T1 --> TS --> A1 --> E1 --> O1
    T2 --> AS --> A2 --> E2 --> O2
    T3 --> HT --> A3 --> E3 --> O3

    style input fill:#1a2a1a,stroke:#2ecc71,color:#e0e0e0
    style scrapers fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
    style actors fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style processing fill:#2a3a2a,stroke:#27ae60,color:#e0e0e0
    style output fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
```

---

## 3. Phase 2 — Script Generation

Loads the latest scraped hooks, builds a prompt, calls Claude, and parses the response into enriched script objects.

```mermaid
flowchart TD
    subgraph input["Load Hooks"]
        L1["load_latest(DATA_RAW_DIR, 'trending_videos')"]
        L2["load_latest(DATA_RAW_DIR, 'ads')"]
    end

    subgraph prompt["Prompt Assembly"]
        BP["build_user_prompt()<br/>Top 10 trending hooks (with play counts)<br/>+ Top 10 ad hooks (with CTAs)<br/>→ request N unique scripts"]
        SP["SYSTEM_PROMPT<br/>Role: viral TikTok scriptwriter<br/>Output: JSON array of {hook, body, cta, style_notes}"]
    end

    subgraph api["Claude API Call"]
        CL["claude-haiku-4-5-20251001<br/>max_tokens: 4096"]
    end

    subgraph parse["Response Processing"]
        PS["parse_scripts()<br/>• Parse JSON array from response<br/>• Add script_id (UUID)<br/>• Determine source_type<br/>  (trending / ad / mixed)<br/>• Calculate duration<br/>  (word_count / 3 sec)"]
    end

    subgraph output["data/scripts/"]
        O["scripts_*.json<br/>[{hook, body, cta, style_notes,<br/>script_id, source_type,<br/>estimated_duration_sec}, ...]"]
    end

    L1 --> BP
    L2 --> BP
    SP --> CL
    BP --> CL
    CL --> PS
    PS --> O

    style input fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style prompt fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style api fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style parse fill:#2a3a4a,stroke:#2980b9,color:#e0e0e0
    style output fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
```

---

## 4. Phase 3 — Video Rendering

Each script becomes a 9:16 vertical video with three sections (hook → body → CTA), concatenated and encoded as H.264.

```mermaid
flowchart TD
    subgraph input["Load Scripts"]
        LS["load_latest(DATA_SCRIPTS_DIR, 'scripts')"]
    end

    subgraph checks["Preflight"]
        CF["check_ffmpeg()"]
        FP["Verify Inter-Bold.ttf<br/>assets/fonts/"]
    end

    subgraph per_script["Per Script"]
        CT["calculate_timing()<br/>hook: 3s, body: variable (min 4s),<br/>cta: 3s, total from duration"]

        subgraph sections["build_section() × 3"]
            S1["HOOK<br/>font: 72px<br/>wrap: 20 chars"]
            S2["BODY<br/>font: 48px<br/>wrap: 30 chars"]
            S3["CTA<br/>font: 64px<br/>wrap: 25 chars"]
        end

        CONCAT["ffmpeg.concat()<br/>hook + body + cta"]
    end

    subgraph encode["Encoding"]
        ENC["libx264 / yuv420p<br/>1080×1920 @ 30fps<br/>bg: #1a1a2e / text: white"]
    end

    subgraph output["output/videos/"]
        MP4["{script_id[:8]}_{source_type}.mp4"]
    end

    LS --> checks --> per_script
    CT --> S1 & S2 & S3
    S1 --> CONCAT
    S2 --> CONCAT
    S3 --> CONCAT
    CONCAT --> ENC --> MP4

    style input fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style checks fill:#2a2a2a,stroke:#95a5a6,color:#e0e0e0
    style per_script fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style sections fill:#4a3a2a,stroke:#d35400,color:#e0e0e0
    style encode fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style output fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
```

---

## 5. Phase 4 — TikTok Publishing (Planned)

Not yet implemented. Must pass TikTok's API audit. See [`docs/TIKTOK_API_COMPLIANCE.md`](TIKTOK_API_COMPLIANCE.md) for full requirements.

```mermaid
flowchart TD
    subgraph auth["OAuth 2.0 Flow"]
        A1["Redirect user to TikTok login"]
        A2["Receive auth code callback"]
        A3["Exchange for access_token"]
    end

    subgraph creator["Creator Info Query"]
        CI["GET /creator_info/<br/>• Available privacy levels<br/>• Interaction settings<br/>• Posting restrictions"]
    end

    subgraph ui["Compliant Upload UI"]
        PRV["Video preview"]
        DD["Privacy dropdown<br/>(no default selection)"]
        CB["Checkboxes: Comment, Duet, Stitch<br/>(unchecked by default,<br/>disabled if unavailable)"]
        CD["Commercial content disclosure<br/>(optional toggle)"]
        CON["Consent button<br/>+ declaration text"]
    end

    subgraph post["Direct Post API"]
        DP["POST /video/upload/<br/>+ POST /video/publish/"]
    end

    subgraph limits["Rate Limits"]
        RL["Pre-audit: 5 users/24h,<br/>private visibility only<br/>Post-audit: ~15 posts/day/account"]
    end

    A1 --> A2 --> A3
    A3 --> CI
    CI --> ui
    PRV --> CON
    DD --> CON
    CB --> CON
    CD --> CON
    CON --> DP
    DP -.-> limits

    style auth fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
    style creator fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
    style ui fill:#3a2a2a,stroke:#c0392b,color:#e0e0e0
    style post fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style limits fill:#2a2a2a,stroke:#95a5a6,color:#e0e0e0
```

---

## 6. Data Schema Flow

How data transforms as it moves through the pipeline.

```mermaid
flowchart LR
    subgraph raw["Phase 1 Output"]
        R1["Trending Hook<br/>─────────<br/>video_id: str<br/>author: str<br/>hook_text: str<br/>stats: {plays, likes,<br/>shares, comments}"]
        R2["Ad Hook<br/>─────────<br/>ad_id: str<br/>advertiser: str<br/>hook_text: str<br/>cta_text: str<br/>estimated_spend: str"]
    end

    subgraph scripts["Phase 2 Output"]
        SC["Script<br/>─────────<br/>hook: str<br/>body: str<br/>cta: str<br/>style_notes: str<br/>script_id: UUID<br/>source_type: trending<br/>  | ad | mixed<br/>estimated_duration_sec: int"]
    end

    subgraph video["Phase 3 Output"]
        VD["MP4 Video<br/>─────────<br/>1080×1920 @ 30fps<br/>H.264 / yuv420p<br/>3 sections:<br/>hook → body → cta<br/>dark bg + white text"]
    end

    subgraph publish["Phase 4 Output"]
        TK["TikTok Post<br/>─────────<br/>Published video<br/>+ privacy settings<br/>+ interaction toggles"]
    end

    R1 -->|"top 10 hooks<br/>+ play counts"| SC
    R2 -->|"top 10 hooks<br/>+ CTAs"| SC
    SC -->|"per script"| VD
    VD -->|"upload"| TK

    style raw fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
    style scripts fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style video fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style publish fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
```

---

## 7. Project Structure

```mermaid
flowchart TD
    ROOT["tiktok-factory/"]

    subgraph src["src/"]
        UTILS["utils/<br/>config.py — env + paths<br/>data_io.py — JSON save/load"]
        SCRAPERS["scrapers/<br/>trend_scraper.py<br/>ads_scraper.py<br/>hashtag_tracker.py"]
        GENERATORS["generators/<br/>script_generator.py<br/>templates.py"]
        RENDERERS["renderers/<br/>video_builder.py"]
    end

    subgraph data_dir["data/"]
        RAW["raw/ — scraped hooks"]
        PROCESSED["processed/ — (reserved)"]
        SCRIPTS["scripts/ — generated scripts"]
    end

    subgraph output_dir["output/"]
        VIDEOS["videos/ — rendered MP4s"]
    end

    subgraph tests_dir["tests/"]
        CONF["conftest.py — fixtures + skip logic"]
        TF["test_templates.py"]
        TP["test_parse_scripts.py"]
        TD["test_data_io.py"]
        TV["test_video_builder.py"]
        TI["test_integration.py"]
    end

    subgraph other["Config & Docs"]
        ENV[".env — API keys (gitignored)"]
        REQ["requirements.txt"]
        PYTEST["pytest.ini"]
        RUNNER["run_tests.py — menu-driven"]
        CLAUDE["CLAUDE.md"]
        DOCS["docs/<br/>TIKTOK_API_COMPLIANCE.md<br/>ARCHITECTURE.md"]
        ASSETS["assets/fonts/Inter-Bold.ttf"]
    end

    ROOT --- src
    ROOT --- data_dir
    ROOT --- output_dir
    ROOT --- tests_dir
    ROOT --- other

    UTILS -.->|"imported by all modules"| SCRAPERS & GENERATORS & RENDERERS

    style src fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style data_dir fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
    style output_dir fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
    style tests_dir fill:#2a3a2a,stroke:#27ae60,color:#e0e0e0
    style other fill:#2a2a2a,stroke:#95a5a6,color:#e0e0e0
```

---

## 8. Test Infrastructure

```mermaid
flowchart LR
    subgraph entry["Entry Points"]
        MENU["run_tests.py<br/>Interactive menu<br/>──────────<br/>1: All unit tests<br/>2: Templates<br/>3: Script parsing<br/>4: Data I/O<br/>5: Video builder<br/>6: Integration<br/>7: Everything"]
        CLI["pytest CLI<br/>direct invocation"]
    end

    subgraph config["conftest.py"]
        BANNER["Session banner<br/>API key + FFmpeg status"]
        SKIP["Auto-skip logic<br/>─────────<br/>@pytest.mark.integration<br/>→ skip if no ANTHROPIC_API_KEY<br/><br/>@pytest.mark.ffmpeg<br/>→ skip if no FFmpeg on PATH"]
        FIX["Shared fixtures<br/>─────────<br/>sample_trending_hooks<br/>sample_ad_hooks<br/>sample_claude_response<br/>sample_script<br/>tmp_data_dir"]
        SUM["Session summary<br/>Rich results table"]
    end

    subgraph tests["Test Modules"]
        T1["test_templates.py<br/>Prompt building,<br/>constant validation"]
        T2["test_parse_scripts.py<br/>JSON parsing, source types,<br/>duration calculation"]
        T3["test_data_io.py<br/>Save/load round-trips<br/>(uses tmp_path)"]
        T4["test_video_builder.py<br/>Wrapping, escaping,<br/>timing, FFmpeg render"]
        T5["test_integration.py<br/>Live Claude API calls"]
    end

    subgraph results["Expected Results"]
        PASS["33 pass"]
        SKIPN["2 skip<br/>(integration w/o API key)"]
    end

    MENU --> config
    CLI --> config
    BANNER --> SKIP
    SKIP --> FIX --> tests
    tests --> SUM --> results

    style entry fill:#2a2a2a,stroke:#95a5a6,color:#e0e0e0
    style config fill:#2a3a2a,stroke:#27ae60,color:#e0e0e0
    style tests fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style results fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
```

---

## Quick Reference

| Phase | Module | External Dep | Input | Output |
|-------|--------|-------------|-------|--------|
| 1 | `trend_scraper.py` | Apify (`apify/tiktok-scraper`) | search term | `trending_videos_*.json` |
| 1 | `ads_scraper.py` | Apify (`data_xplorer/tiktok-ads-library-fast`) | keyword | `ads_*.json` |
| 1 | `hashtag_tracker.py` | Apify (`clockworks/tiktok-hashtag-scraper`) | hashtag list | `hashtags_*.json` |
| 2 | `script_generator.py` | Claude API (`claude-haiku-4-5-20251001`) | hooks JSON | `scripts_*.json` |
| 3 | `video_builder.py` | FFmpeg (`libx264`) | scripts JSON | `{id}_{type}.mp4` |
| 4 | `tiktok_publisher.py` | TikTok Content Posting API | MP4 video | TikTok post |
