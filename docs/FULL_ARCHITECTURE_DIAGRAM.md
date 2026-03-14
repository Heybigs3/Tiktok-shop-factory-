# TikTok Factory — Full Architecture Diagram

Unified Mermaid diagram of the complete pipeline. Renders natively on GitHub.

---

## Complete System Architecture

```mermaid
flowchart TD
    %% ── External Services ──────────────────────────
    subgraph ext["External Services"]
        direction LR
        APIFY["Apify Actors"]
        KALO["Kalodata Web UI"]
        CLAUDE["Claude API\n(Haiku + Sonnet)"]
        FFMPEG["FFmpeg"]
        ELEVEN["ElevenLabs TTS"]
        GEMINI["Gemini API"]
        MUAPI["Muapi SDK"]
        YTDLP["yt-dlp"]
        WHISPER["Whisper CLI"]
        TIKTOK["TikTok API\n(dormant)"]
    end

    %% ── Phase 0: DECIDE ────────────────────────────
    subgraph phase0["PHASE 0 — DECIDE"]
        NR["Niche Radar\n─────────────\nScan 10 niches\nScore: engagement (35%)\nvelocity (25%) · gap (20%)\nmomentum (20%)\n─────────────\nRecommend top 3\nGenerate pipeline_config"]
    end

    %% ── Phase 1: GATHER ────────────────────────────
    subgraph phase1["PHASE 1 — GATHER (parallel)"]
        direction LR
        TS["Trend Scraper\n(Apify)\n─────────────\ntrending_videos_*.json\nhooks · stats · musicMeta"]
        AS["Ads Scraper\n(Apify)\n─────────────\nads_*.json\nhooks · CTA · spend"]
        HT["Hashtag Tracker\n(Apify)\n─────────────\nhashtags_*.json\nviews · trend direction"]
        KS["Kalodata Scraper\n(Playwright)\n─────────────\nproducts_*.json\nrevenue · sales · images"]
    end

    subgraph processing["PHASE 1e — PROCESS"]
        HP["Hook Processor\n─────────────\nNormalize fields\nExtract hooks · Dedup\nFilter low-quality\nSort by engagement rate\n─────────────\nprocessed_hooks_*.json\nprocessed_ad_hooks_*.json"]
    end

    %% ── Phase 2: LEARN ─────────────────────────────
    subgraph phase2["PHASE 2 — LEARN (sequential)"]
        DL["Video Downloader\n(yt-dlp)\n─────────────\nTop N by engagement\nfrom trending_videos"]
        FE["Frame Extractor\n(FFmpeg)\n─────────────\nScene detection or\neven spacing → PNGs"]
        TR["Transcriber\n(Whisper CLI)\n─────────────\nAudio → text\nFalls back gracefully"]
        VA["Video Analysis\n(Claude Haiku)\n─────────────\nMultimodal: frames +\ntranscript → structured\nhook/visual/CTA analysis\n~$0.01/video"]
        SB["Style Bible\n(Claude Sonnet)\n─────────────\nAggregate all analyses\nColor palettes · Hook patterns\nPacing · CTA timing\n→ {niche}_style_bible.json"]
        CMP["Comparison\n(Claude API)\n─────────────\nOur videos vs top performers\nGaps: pacing · color ·\nhook style · CTA format"]
    end

    %% ── Phase 3: CREATE ────────────────────────────
    subgraph phase3["PHASE 3 — CREATE"]
        SG["Script Generator\n(Claude Haiku)\n─────────────\n6 inputs: hooks + ads +\nhashtags + products +\nStyle Bible + comparison gaps\n─────────────\nContent mode OR Product mode\n→ scripts_*.json"]
        TPL["templates.py\n─────────────\nSystem prompts\nPrompt builders\nMode selection"]
    end

    %% ── Phase 4: BUILD ─────────────────────────────
    subgraph phase4["PHASE 4 — BUILD"]
        IG["Image Generator\n(Gemini API)\n─────────────\n3 scenes per script\nMood + style prompts\nProduct image reference\n→ output/images/"]
        VG["Video Generator\n(Muapi SDK)\n─────────────\nAnimated clips\nAsync submit/poll\n→ output/clips/"]
        VB["Video Builder\n(FFmpeg)\n─────────────\nStyle Router:\n  Content → solid BG + text\n  Product → Ken Burns + overlays\nTikTok safe zones enforced"]
        TTS["TTS Narration\n(ElevenLabs)\n─────────────\nMood → voice mapping\nAudio drives timing"]
        PP["Post-Processing\n─────────────\nColor grading (eq filter)\nVignette overlay\nBackground music mix\nMood-based transitions\n→ output/videos/*.mp4\n1080×1920 @ 30fps"]
    end

    %% ── Phase 5: DELIVER ───────────────────────────
    subgraph phase5["PHASE 5 — DELIVER"]
        DASH["Dashboard\n(FastAPI + HTMX + Tailwind)\nlocalhost:8420\n─────────────\nVideos page · Products page\nSettings page\nMulti-account sidebar"]
        VAPOST["VA Posts Manually\n─────────────\nDownload video\nCopy caption + hashtags\nPost on TikTok app"]
        PUB["TikTok Publisher\n─────────────\nOAuth 2.0 flow\n⚠ Dormant until\napp approved"]
    end

    %% ── Data Layer ─────────────────────────────────
    subgraph data["Data Layer (timestamped JSON files)"]
        direction LR
        RAW["data/raw/"]
        PROC["data/processed/"]
        SCRIPTS["data/scripts/"]
        STYLES["data/style_bibles/"]
        FRAMES["data/frames/ +\ndata/transcripts/ +\ndata/analysis/"]
        ACCTS["data/accounts/{id}/\n(per-niche isolation\n⚠ not yet wired)"]
    end

    subgraph config["Configuration"]
        ENV[".env\nAPI keys"]
        PCFG["pipeline_config.json\nNiche settings · search queries\nad keywords · hashtags\nTTS · video style"]
        CFG["config.py\nPath constants\nAuto-loads .env"]
    end

    %% ── Planned Components ─────────────────────────
    subgraph planned["PLANNED (not yet built)"]
        direction LR
        TREND_PROF["Trend Profiler\nAnalyzed videos →\ngeneration blueprint"]
        DYN_MUSIC["Dynamic Music\nAI-generated\nper-video"]
        PERF_TRACK["Performance Tracker\nScrape own metrics\n24h + 72h"]
        FEEDBACK["Feedback Engine\nStyle → engagement\ncorrelation loop"]
        HEYGEN["HeyGen Avatars\nUGC-style AI\npresenters"]
    end

    %% ── CONNECTIONS ────────────────────────────────

    %% External service connections
    APIFY -.-> NR
    APIFY -.-> TS & AS & HT
    KALO -.-> KS
    CLAUDE -.-> VA & SB & CMP & SG
    FFMPEG -.-> FE & VB
    ELEVEN -.-> TTS
    GEMINI -.-> IG
    MUAPI -.-> VG
    YTDLP -.-> DL
    WHISPER -.-> TR
    TIKTOK -.-> PUB

    %% Phase 0 → Config
    NR ==>|"generates"| PCFG

    %% Config → Phase 1
    PCFG ==> TS & AS & HT & KS

    %% Phase 1 → Data
    TS --> RAW
    AS --> RAW
    HT --> RAW
    KS --> RAW

    %% Phase 1 → Processing
    RAW --> HP
    HP --> PROC

    %% Phase 1 → Phase 2
    RAW -->|"trending_videos URLs"| DL
    DL --> FE
    DL --> TR
    FE --> FRAMES
    TR --> FRAMES
    FRAMES --> VA
    VA --> SB
    SB --> STYLES
    SB --> CMP

    %% Phase 2 → Phase 3
    PROC -->|"hooks + ad hooks"| SG
    RAW -->|"hashtags + products"| SG
    STYLES -->|"Style Bible"| SG
    CMP -->|"comparison gaps"| SG
    TPL --> SG
    SG --> SCRIPTS

    %% Phase 3 → Phase 4
    SCRIPTS --> IG
    SCRIPTS --> VG
    SCRIPTS --> VB
    IG -->|"scene images"| VB
    VG -->|"animated clips"| VB
    VB --> TTS
    TTS --> PP

    %% Phase 4 → Phase 5
    PP --> DASH
    SCRIPTS -->|"captions + hashtags"| DASH
    DASH --> VAPOST
    PP -.->|"future"| PUB

    %% Feedback loop (planned)
    VAPOST -.->|"planned"| PERF_TRACK
    PERF_TRACK -.->|"planned"| FEEDBACK
    FEEDBACK -.->|"planned\nlearnings"| NR

    %% ── STYLES ─────────────────────────────────────
    style ext fill:#2d2d3f,stroke:#6c6c8a,color:#e0e0e0
    style phase0 fill:#0d2818,stroke:#2ecc71,color:#e0e0e0
    style phase1 fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
    style processing fill:#2a3a2a,stroke:#27ae60,color:#e0e0e0
    style phase2 fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style phase3 fill:#2a1a3a,stroke:#9b59b6,color:#e0e0e0
    style phase4 fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style phase5 fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
    style data fill:#2a2a3a,stroke:#9b59b6,color:#e0e0e0
    style config fill:#2a2a2a,stroke:#95a5a6,color:#e0e0e0
    style planned fill:#1a1a2a,stroke:#636e72,color:#95a5a6,stroke-dasharray: 5 5
```

---

## Data Flow Summary

```mermaid
flowchart LR
    subgraph in["Intelligence"]
        A["Niche Radar"] --> B["pipeline_config.json"]
    end

    subgraph gather["Gather"]
        B --> C["4 Scrapers\n(parallel)"]
        C --> D["Hook Processor"]
    end

    subgraph learn["Learn"]
        C -->|"top video URLs"| E["Download → Frames\n→ Transcribe → Analyze"]
        E --> F["Style Bible"]
    end

    subgraph create["Create"]
        D --> G["Script Generator"]
        F --> G
    end

    subgraph build["Build"]
        G --> H["Images + Clips\n→ Video Builder\n→ TTS + Music"]
    end

    subgraph deliver["Deliver"]
        H --> I["Dashboard\n→ VA Posts"]
    end

    I -.->|"planned\nfeedback loop"| A

    style in fill:#0d2818,stroke:#2ecc71,color:#e0e0e0
    style gather fill:#1a3a2a,stroke:#2ecc71,color:#e0e0e0
    style learn fill:#1a2a3a,stroke:#3498db,color:#e0e0e0
    style create fill:#2a1a3a,stroke:#9b59b6,color:#e0e0e0
    style build fill:#3a2a1a,stroke:#e67e22,color:#e0e0e0
    style deliver fill:#3a1a2a,stroke:#e74c3c,color:#e0e0e0
```

---

## Known Issue: Data Isolation Gap

```mermaid
flowchart TD
    subgraph problem["⚠ Current: Shared Global Paths"]
        CONFIG["config.py"] --> GLOBAL["data/raw/ (ONE folder)\ndata/scripts/ (ONE folder)\noutput/videos/ (ONE folder)"]
        GLOBAL --> BLEED["Niche A data bleeds\ninto Niche B scripts"]
    end

    subgraph solution["✓ Target: Per-Account Isolation"]
        ACCT["accounts.py\nget_account_paths(id)"] --> ISO["data/accounts/{id}/raw/\ndata/accounts/{id}/scripts/\ndata/accounts/{id}/output/"]
        ISO --> CLEAN["Each niche reads\nonly its own data"]
    end

    problem -.->|"fix needed"| solution

    style problem fill:#3a1a1a,stroke:#e74c3c,color:#e0e0e0
    style solution fill:#1a3a1a,stroke:#2ecc71,color:#e0e0e0
```
