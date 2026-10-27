# Meta Global AI Developer Hackathon: what matters for Q-Canvas

Collected on 2026-10-28 from the official pages (saved copies in this folder:
`cerebralvalley.md`, `meta-event.html`). Official sources:

- https://cerebralvalley.ai/e/meta-ai-developer-hackathon
- https://dev.meta.ai/events/global-hackathon

## Dates (ET)

| When | What |
| --- | --- |
| Oct 26 | Kickoff |
| Oct 27 to Nov 4 | Workshops and Discord office hours |
| **Nov 4, 9:00 PM ET** | **Submissions due** (Cerebral Valley portal; Nov 5 UTC) |
| Nov 4 to Nov 8 | Judging |
| Nov 9 | Live finals and winners |

## Tracks and judging (official wording)

- **Indie developer track** (individuals and students): "Judged on creativity,
  technical ambition, and whether it works." This is our track.
- Startup track: technical execution and production readiness.

Themes: "Build for Your World" and **"Push the Frontier"** ("accelerate a
scientific experiment, or unlock a better way to understand and control a
physical system"). Q-Canvas enters Push the Frontier.

A third-party listing (internshala) quotes weights of Impact 30%, Use of Meta
AI tooling 25%, Technical depth 20%, Demo 25%. That is **not** on the official
pages, so treat it as unverified; it is still a sensible checklist.

## Models we are expected to use

The official page names: Muse Spark series, Muse Wonder, Muse Image, SAM 3.1
(all on Meta Model API), Meta open-weight models, and the Muse Code coding agent.
Every participant got $150 of Model API credits.

## What this means for the build

1. "Whether it works" is a judging criterion: the offline mock path must make
   every screen work even if the API is down, and must say so on screen.
2. "Use of Meta tooling": four Meta models, each doing a job only it can do
   (SAM 3.1 finds the drawn parts, Muse Spark reads and explains, Muse Spark
   repairs code, Muse Image draws the clean diagram). Shown live in the log
   with the model ID next to every call.
3. "Technical ambition": independent verification, a self-repair loop, noise
   models and an analytic network model, not a thin wrapper.
4. Demo: the paper-to-verified-code moment and a visible fail, diagnose,
   repair, pass.

Official rules were to be published at kickoff; check the portal for the
submission form fields (video length, repo link, description) before Nov 4.
