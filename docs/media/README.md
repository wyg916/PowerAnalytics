# Media provenance

The repository uses two different asset classes and keeps them explicit.

## Real product captures

All files under `screenshots/` were extracted frame-by-frame from recordings of the running PowerAnalytics project. They are not generated interface mockups.

| File | Recording | Capture point | What was verified |
|---|---|---:|---|
| `dashboard.webp` | Main product recording | 00:01:40 | Full dashboard; no login, desktop, or error dialog |
| `forecast-24h.webp` | Main product recording | 00:12:12 | 24-hour forecast with visible peak tooltip |
| `forecast-analysis.webp` | Main product recording | 00:15:00 | Peak/valley analysis and model evaluation |
| `strategy-evidence.webp` | Main product recording | 00:17:10 | Strategy review and evidence details |
| `model-center.webp` | Main product recording | 00:51:20 | Active/Candidate model view; no skeleton state |
| `ai-short-memory.webp` | AI rescue recording | 00:09:00 | Correct risk preference, focus period, and answer order |
| `ai-long-memory.webp` | AI rescue recording | 00:11:00 | New-session preference recall and structured brief |
| `knowledge-base.webp` | AI rescue recording | 00:12:20 | 83 documents and 8,339 chunks visible in the recorded environment |
| `rag-citation.webp` | AI rescue recording | 00:17:00 | Answer with three expanded knowledge citations |

Frames were scaled without stretching and padded to `1600 × 900`. Every WebP file is below 1.5 MB. The original source recordings are not committed or distributed.

The project owner confirmed on 2026-08-30 that the included first-party project content, visible labels, documents, figures, and captures may be published. The frames were reviewed to exclude login screens, desktop content, secrets, and unrelated identities. This confirmation applies only to the files committed here; it does not grant rights to third-party documents that a downstream user may later import.

## Published project demo

The final edited demo is published in two delivery formats. Neither copy is stored as a Git blob.

### Native README player

- GitHub attachment: [open the native player](https://github.com/user-attachments/assets/149a3576-f137-4806-a25f-cfa50092647b)
- Uploaded file: `poweranalytics-project1-github-promo-inline-720p.mp4`
- Media: 2:00, `1280 × 720`, 30 fps, H.264 High / AAC-LC
- File size: `9,434,160` bytes
- SHA-256: `98e9cd6c069d5484a241df2769d6de178336a4c8772f2566108778049c6e85ef`

The bare attachment URL is placed directly in `README.md` and `README_EN.md`, so GitHub renders its native inline player. It does not autoplay or force a download.

### HD Release copy

- File: `poweranalytics-project1-github-promo-zh-cn-1080p.mp4`
- Release: [`v2.12.1-open-source.1`](https://github.com/wyg916/PowerAnalytics/releases/tag/v2.12.1-open-source.1)
- Release asset: [optional 1080p MP4 download](https://github.com/wyg916/PowerAnalytics/releases/download/v2.12.1-open-source.1/poweranalytics-project1-github-promo-zh-cn-1080p.mp4)
- Media: 2:00, `1920 × 1080`, 30 fps, H.264 High / AAC-LC
- File size: `21,642,960` bytes
- SHA-256: `249adf38133663311bf9f277e28284c4f176e407d7fe57bd9bd4648cdffbf96e`

The footage comes from the running project, not a generated UI mockup. Both public copies were derived from the owner-supplied final edit; only the closing contact card was corrected to the canonical `github.com/wyg916/PowerAnalytics` address. Narration, subtitles, and feature footage were retained. Raw masters and failed takes remain excluded.

## Brand artwork

- `banner.png` is an original project banner created for this repository.
- `social-preview.png` is an original social-preview composition created for this repository.
- These abstract graphics do not represent product functionality and do not replace the real screenshots above.

No third-party project logo, banner, product screenshot, or raw source recording is included.
