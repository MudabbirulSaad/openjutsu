# Frontend specification

Minimal guided studio: Prepare → Review → Generate → Export. Persistent central viewer; transport and timeline below; 320px stage inspector; compact Projects, Recipes, Settings navigation. Side-by-side and slider comparisons use synchronized proxies; paused exact review uses indexed frame images.

| Token | Light | Dark |
|---|---|---|
| Background | #F5F4F0 | #101215 |
| Panel | #FFFFFF | #191C20 |
| Text | #1B1E24 | #F0F1F2 |
| Secondary | #606671 | #A1A7B1 |
| Action | #1D4ED8 | #93C5FD |
| Action text | #FFFFFF | #101215 |

Self-hosted Inter; tabular timecodes; 4px spacing grid; 6–8px corners; visible SVG labels. System theme by default, with light/dark override. Matte surface texture and a small depth-contour shader never cover footage; freeze decorative animation during playback, GPU work, hidden tabs, and reduced motion.

Backend state controls available actions, blocking reasons, costs, reservations, and approvals. One event stream feeds snapshots. Preserve dirty edits through reconnects and stale revision errors. Never retry paid mutations automatically. Provider rows distinguish ordinary edits from continuation-capable drafts and show qualification status.

Keyboard-accessible trimming, frame stepping, annotation coordinates, labelled references, and resize-aware point mapping are required. Tablets use an inspector drawer; phones stack the workspace. Exact media coordinates ignore letterboxing. Errors remain inline and name the next available action. Settings show real hardware/model/provider readiness rather than simulated progress.
# Implementation contract

The guided studio uses `/api/jobs/{id}` as its state authority and a single ordered `/api/events` stream to refresh queries. Reconnection falls back to read-only polling. Mutations have retries disabled; paid controls are latched while an operation is pending. The server validates revision, approval, quote expiry, account and reservation atomically.

Unsaved recipes are retained in browser local storage with their base revision. A stale draft remains visible and cannot be submitted. Settings submit secrets directly to the backend and never read them back. Clip media uses normalized browser copies; paused review requests indexed PNG frames. Click coordinates exclude letterbox regions, with numeric point and box controls as keyboard alternatives.

UI availability means installed dependencies and files, not measured quality. Provider qualification requires a settled pilot and human scores. The default spending limit is zero. The studio shows uncertain submissions and provides dashboard-based reconciliation rather than an automatic retry.
