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
