# Submission checklist

Run `.venv/Scripts/python scripts/check_submission.py` first: it checks everything below that the repo can check
(public repository, links filled in, video length, thumbnail, test counts, every quoted number against its data,
the key absent from git history, CI on the latest commit, the deadline) and prints what is left.

## Before you submit (only you can do these)

| Done | What | How |
| --- | --- | --- |
| [ ] | Make the repository public | `gh repo edit Dhruv-Deku/inkubit --visibility public --accept-visibility-change-consequences` |
| [ ] | Record the voice-over (optional, recommended) | Clipchamp: import `docs/video/inkubit-demo-v4.mp4`, read the blocks in `DEMO_SCRIPT.md` over their scenes |
| [ ] | Film your hand drawing a circuit (optional, about 10 s) | Phone, top-down, pen on white paper; put it before the title card |
| [ ] | Upload the video | YouTube, unlisted is fine; thumbnail `docs/thumbnail.png`; title "Inkubit: Meta's models propose, exact physics checks every number" |
| [ ] | Paste the video link | `SUBMISSION.md`, line "Demo video" |
| [ ] | Hosted demo (recommended) | Make the repo public, then open [the Koyeb deploy link](https://app.koyeb.com/deploy?type=git&builder=dockerfile&repository=github.com/Dhruv-Deku/inkubit&branch=main&name=inkubit&ports=7860;http;/&instance_type=free&regions=was), sign in with GitHub and press Deploy (free instance; add `META_API_KEY` as a secret for live models); paste the app URL into `SUBMISSION.md` ("Try it"), or delete that part |
| [ ] | Real IBM hardware run (optional, strongest proof) | `IBM_QUANTUM_TOKEN=...` in `.env`, then `scripts/hardware_check.py`; it writes `docs/HARDWARE.md` and the Evidence panel appears |
| [ ] | Run the checker again | `scripts/check_submission.py`: no TODO left except the optional ones you chose to skip |

## The form, field by field (all text is in `SUBMISSION.md`)

| Field | Where |
| --- | --- |
| Project name | "Inkubit" |
| Track and problem statement | Indie developer; Push the Frontier |
| Tagline | `SUBMISSION.md`, "Tagline" |
| Short description | `SUBMISSION.md`, "Short description" |
| Full description | `SUBMISSION.md`, from "At a glance" through "Honest by design" |
| How Meta's models are used | `SUBMISSION.md`, "How we used Meta's models" |
| Built with | Python 3.13, FastAPI, Qiskit, Qiskit Aer, PyMatching, SGP4, React 19, TypeScript, Vite; Muse Spark, Muse Wonder, SAM 3.1, Muse Image, Muse Voice Transcribe |
| Code | https://github.com/Dhruv-Deku/inkubit |
| Video | your YouTube link |
| Try it | your Koyeb app URL (if deployed) |
| Built during the hackathon | `SUBMISSION.md`, "Built during the hackathon"; the day-by-day table is in the README |

## What judges will see first

1. The video (2:35) and its thumbnail.
2. The README: the GIF, then "Results you can check in the app", each linked to its evidence.
3. The app: the **Guided tour** button (under two minutes) shows the best of it; every number on screen comes from a run.
