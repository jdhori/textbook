#!/usr/bin/env python3

"""
Video Accessibility Checker for Jupyter Book HTML

This script scans built HTML files (typically in _build/html)
and flags accessibility issues related to video embeds.

Why this exists:
Automated tools like axe-core do not reliably detect:
- Missing iframe titles
- Poor iframe labeling
- Missing transcripts near videos
- Platform-based caption issues (YouTube, YuJa, Kaltura, etc.)
- Autoplay and hidden control risks

This script supplements those gaps.

What it checks:
1. Iframe embeds (YouTube, Vimeo, etc.)
   - Missing title or aria-label (WCAG 4.1.2)
   - Generic titles like "video"
   - Autoplay usage (WCAG 2.2.2)
   - Hidden controls (WCAG 2.1.1)
   - Missing nearby transcript/caption indicators (WCAG 1.2.x)

2. Native <video> elements
   - Missing controls (WCAG 2.1.1)
   - Missing captions/subtitles (WCAG 1.2.2)
   - Missing description track (WCAG 1.2.3 / 1.2.5)
   - Autoplay behavior
   - Missing nearby transcript/audio description

Limitations:
- Cannot confirm captions exist inside third-party platforms
- Cannot evaluate caption quality
- Cannot detect audio description content, only presence hints

Usage:
python check-video-accessibility.py _build/html
"""

import sys
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
VIDEO_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "vimeo.com",
    "panopto",
    "kaltura",
    "yuja",
    "media.ucdavis.edu",
    "video.ucdavis.edu",
]

SUPPORT_WORDS = [
    "transcript",
    "caption",
    "captions",
    "subtitles",
    "audio description",
    "described video",
    "media alternative",
]

GENERIC_TITLES = [
    "",
    "video",
    "youtube",
    "youtube video",
    "iframe",
    "embedded content",
    "player",
    "video player",
]

def is_video_iframe(src):
    return any(domain in src.lower() for domain in VIDEO_DOMAINS)

def nearby_text(element):
    parent = element.find_parent()
    if not parent:
        return ""
    return parent.get_text(" ", strip=True).lower()

def has_support_text(element):
    text = nearby_text(element)
    return any(word in text for word in SUPPORT_WORDS)

def get_params(src):
    return parse_qs(urlparse(src).query)

def annotate_error(message):
    print(f"::error::{message}")

def annotate_warning(message):
    print(f"::warning::{message}")

def check_iframe(file, iframe):
    errors = []
    warnings = []

    src = iframe.get("src", "").strip()
    if not src or not is_video_iframe(src):
        return errors, warnings

    title = iframe.get("title", "").strip()
    aria = iframe.get("aria-label", "").strip()
    name = title or aria

    if not name:
        errors.append(f"{file}: Missing iframe title/aria-label → {src}")

    elif name.lower() in GENERIC_TITLES:
        warnings.append(f"{file}: Generic iframe title '{name}' → {src}")

    if not has_support_text(iframe):
        warnings.append(f"{file}: No transcript/caption context near video → {src}")

    params = get_params(src)

    if params.get("autoplay", ["0"])[0] == "1":
        warnings.append(f"{file}: Autoplay detected → {src}")

    if params.get("controls", ["1"])[0] == "0":
        errors.append(f"{file}: Controls disabled → {src}")

    if "youtube" in src:
        if not (
            params.get("cc_load_policy", ["0"])[0] == "1"
            or "caption" in nearby_text(iframe)
        ):
            warnings.append(f"{file}: YouTube embed lacks caption hint → {src}")

    if "autoplay" in iframe.get("allow", "").lower():
        warnings.append(f"{file}: iframe allows autoplay → {src}")

    return errors, warnings

def check_video(file, video):
    errors = []
    warnings = []

    if not video.has_attr("controls"):
        errors.append(f"{file}: <video> missing controls")

    if video.has_attr("autoplay"):
        warnings.append(f"{file}: <video> uses autoplay")

    tracks = video.find_all("track")

    has_captions = any(
        t.get("kind", "").lower() in ["captions", "subtitles"]
        for t in tracks
    )

    has_descriptions = any(
        t.get("kind", "").lower() == "descriptions"
        for t in tracks
    )

    if not has_captions:
        errors.append(f"{file}: <video> missing captions/subtitles")

    if not has_descriptions:
        warnings.append(f"{file}: <video> missing description track")

    if not has_support_text(video):
        warnings.append(f"{file}: <video> missing transcript/audio description context")

    return errors, warnings

def write_summary(errors, warnings):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    with open(path, "a") as f:
        f.write("# Video Accessibility Report\n\n")

        if errors:
            f.write("## ❌ Required Fixes\n")
            for e in errors:
                f.write(f"- {e}\n")

        if warnings:
            f.write("\n## ⚠️ Review Items\n")
            for w in warnings:
                f.write(f"- {w}\n")

        f.write("\n## Fix Guide\n")
        f.write("| Issue | Fix |\n")
        f.write("|------|-----|\n")
        f.write("| Missing iframe title | Add descriptive title |\n")
        f.write("| Generic title | Replace with meaningful description |\n")
        f.write("| Missing captions | Add captions/subtitles |\n")
        f.write("| Missing transcript | Add transcript near video |\n")
        f.write("| Autoplay | Remove autoplay |\n")
        f.write("| No controls | Enable controls |\n")

def main():
    if len(sys.argv) != 2:
        print("Usage: script.py <html-dir>")
        sys.exit(2)

    root = Path(sys.argv[1]).resolve()
    if not root.exists():
        print("Directory not found")
        sys.exit(2)

    all_errors = []
    all_warnings = []

    for file in root.rglob("*.html"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "lxml")

            for iframe in soup.find_all("iframe"):
                e, w = check_iframe(file.name, iframe)
                all_errors.extend(e)
                all_warnings.extend(w)

            for video in soup.find_all("video"):
                e, w = check_video(file.name, video)
                all_errors.extend(e)
                all_warnings.extend(w)
        except Exception as ex:
            annotate_warning(f"Failed to read or parse {file.name}: {ex}")

    for e in all_errors:
        annotate_error(e)

    for w in all_warnings:
        annotate_warning(w)

    write_summary(all_errors, all_warnings)

    if all_errors:
        print("\nFix required issues above.\n")
        sys.exit(1)

    print("Checks passed.")


if __name__ == "__main__":
    main()
