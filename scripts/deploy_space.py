"""Publish Inkubit to a Hugging Face Space (Docker SDK) in public mode.

    pip install huggingface_hub && hf auth login          # once, with a token that can write
    .venv/Scripts/python scripts/deploy_space.py <user>/inkubit [--with-key] [--dry-run]

Stages only what the image needs (no .env, no node_modules, no videos, no tests), seeds the model-answer cache with
the small cached answers so the samples run instantly and cost nothing, writes the Space README header and uploads.
Public mode is set in the Dockerfile: code written by a model is never executed and billed calls stop at
INKUBIT_DAILY_CALLS (300) a day. --with-key stores META_API_KEY from .env as an encrypted Space secret (it never
goes into the files); without it the Space runs on the labelled offline models.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"__pycache__", "node_modules", "dist", ".inkubit_cache", "tests", "seed_cache", ".pytest_cache"}
SEED_LIMIT = 900_000  # bytes: small cached answers only (large image generations stay out)

SPACE_README = """---
title: Inkubit
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Sketch, say or photograph a quantum idea; exact physics checks it
---

# Inkubit

Meta's models (Muse Spark, Muse Wonder, SAM 3.1, Muse Image, Muse Voice Transcribe) turn sketches, photos, papers and
speech into quantum experiments, and exact simulation checks every number before you see it.

Public mode: code written by a model is never executed here, and live model calls are capped per day (after that the
app answers with its labelled offline models). Source, tests and every design decision:
https://github.com/Dhruv-Deku/inkubit
"""


def stage(dest: Path) -> int:
    def copy_tree(src: Path, dst: Path) -> None:
        for p in src.rglob("*"):
            rel = p.relative_to(src)
            if any(part in SKIP_DIRS for part in rel.parts) or p.suffix in (".pyc", ".mp4"):
                continue
            target = dst / rel
            if p.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)

    for name in ("Dockerfile", ".dockerignore", "LICENSE"):
        shutil.copy2(ROOT / name, dest / name)
    copy_tree(ROOT / "backend", dest / "backend")
    copy_tree(ROOT / "examples", dest / "examples")
    copy_tree(ROOT / "frontend", dest / "frontend")
    (dest / "README.md").write_text(SPACE_README, encoding="utf-8")
    seeded = 0
    cache = ROOT / "backend" / ".inkubit_cache"
    for p in cache.rglob("*.json") if cache.exists() else []:
        if p.stat().st_size <= SEED_LIMIT:
            target = dest / "backend" / "seed_cache" / p.relative_to(cache)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            seeded += 1
    return seeded


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or "/" not in args[0]:
        sys.exit(__doc__)
    repo_id = args[0]
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        seeded = stage(dest)
        files = sum(1 for p in dest.rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())
        print(f"staged {files} files ({size / 1e6:.1f} MB), {seeded} cached answers seeded")
        bad = [p for p in dest.rglob("*") if p.is_file() and p.name.startswith(".env")]
        if bad:
            sys.exit(f"refusing to upload secrets: {bad}")
        if "--dry-run" in sys.argv:
            return
        try:
            from huggingface_hub import HfApi
        except ImportError:
            sys.exit("pip install huggingface_hub, then hf auth login")
        api = HfApi()
        api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
        api.upload_folder(folder_path=str(dest), repo_id=repo_id, repo_type="space",
                          commit_message="Deploy Inkubit (public mode)")
        if "--with-key" in sys.argv:
            from dotenv import dotenv_values

            key = dotenv_values(ROOT / ".env").get("META_API_KEY") or os.environ.get("META_API_KEY")
            if not key:
                sys.exit("no META_API_KEY in .env")
            api.add_space_secret(repo_id, "META_API_KEY", key)
            print("META_API_KEY stored as an encrypted Space secret")
        print(f"uploaded: https://huggingface.co/spaces/{repo_id} (the image builds in a few minutes)")


if __name__ == "__main__":
    main()
