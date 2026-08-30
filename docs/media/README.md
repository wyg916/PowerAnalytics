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

Frames were scaled without stretching and padded to `1600 × 900`. Every WebP file is below 1.5 MB. The source recordings are not committed, modified, or distributed.

The project owner confirmed on 2026-08-30 that the included first-party project content, visible labels, documents, figures, and captures may be published. The frames were reviewed to exclude login screens, desktop content, secrets, and unrelated identities. This confirmation applies only to the files committed here; it does not grant rights to third-party documents that a downstream user may later import.

## Brand artwork

- `banner.png` is an original project banner created for this repository.
- `social-preview.png` is an original social-preview composition created for this repository.
- These abstract graphics do not represent product functionality and do not replace the real screenshots above.

No third-party project logo, banner, product screenshot, or source recording is included.
