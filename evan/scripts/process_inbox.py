#!/usr/bin/env python3
"""
process_inbox.py — Moves zips from evan/inbox/ to evan/userdatadump/
Run: python3 evan/scripts/process_inbox.py

1. Finds all .zip files in evan/inbox/
2. Extracts each, finds the submission ID (from filenames) and model name (from .py docstring)
3. Moves to evan/userdatadump/{model}_{submissionID}/
4. Deletes the zip from inbox
5. Prints summary for both claudes to see
"""

import os
import re
import json
import shutil
import zipfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # evan/
INBOX = REPO / "inbox"
DUMP = REPO / "userdatadump"


def find_submission_id(extracted_files):
    """Submission ID = the numeric filename stem shared by .json/.py/.log"""
    for f in extracted_files:
        name = Path(f).stem
        if name.isdigit():
            return name
    return None


def find_model_name(extracted_files):
    """Parse the .py file's docstring for model name (e.g. 'e1_crazy1', 'e1_v10')"""
    for f in extracted_files:
        if f.endswith(".py"):
            try:
                with open(f, "r") as fh:
                    content = fh.read(2000)  # first 2KB is enough
                # Look for e1_something in the first few lines
                match = re.search(r'\b(e1_\w+)', content)
                if match:
                    return match.group(1)
                # Fallback: look for any model-like name
                match = re.search(r'\b(BOT_\w+|trader_\w+)', content, re.IGNORECASE)
                if match:
                    return match.group(1)
            except Exception:
                pass
    return None


def parse_results(extracted_files):
    """Parse .json for quick score summary"""
    for f in extracted_files:
        if f.endswith(".json"):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                total = data.get("profit", "?")

                # Parse activities for per-product PnL
                activities = data.get("activitiesLog", "")
                lines = activities.strip().split("\n")
                e_pnl = t_pnl = "?"
                for line in reversed(lines[1:]):
                    parts = [p.strip() for p in line.split(";")]
                    if len(parts) >= 17:
                        product = parts[2]
                        pnl = parts[16]
                        if product == "EMERALDS" and e_pnl == "?":
                            e_pnl = pnl
                        elif product == "TOMATOES" and t_pnl == "?":
                            t_pnl = pnl
                    if e_pnl != "?" and t_pnl != "?":
                        break
                return total, e_pnl, t_pnl
            except Exception:
                pass
    return "?", "?", "?"


def process_zip(zip_path):
    """Process a single zip file from inbox"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Extract
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        # Find extracted files (flatten — some zips have subdirs)
        extracted = []
        for root, dirs, files in os.walk(tmpdir):
            for f in files:
                if not f.startswith(".") and not f.startswith("__"):
                    extracted.append(os.path.join(root, f))

        sub_id = find_submission_id(extracted)
        model = find_model_name(extracted)

        if not sub_id:
            print(f"  SKIP {zip_path.name}: no submission ID found")
            return None

        if not model:
            model = "unknown"

        folder_name = f"{model}_{sub_id}"
        dest = DUMP / folder_name

        # Check if already processed
        if dest.exists():
            print(f"  SKIP {zip_path.name}: {folder_name}/ already exists")
            zip_path.unlink()
            return None

        # Move files to destination
        dest.mkdir(parents=True, exist_ok=True)
        for f in extracted:
            fname = Path(f).name
            shutil.move(f, dest / fname)

        # Parse scores
        total, e_pnl, t_pnl = parse_results([str(dest / Path(f).name) for f in extracted])

        # Delete zip from inbox
        zip_path.unlink()

        return {
            "model": model,
            "sub_id": sub_id,
            "folder": folder_name,
            "total": total,
            "e_pnl": e_pnl,
            "t_pnl": t_pnl,
        }


def main():
    if not INBOX.exists():
        INBOX.mkdir(parents=True)
        print(f"Created inbox at {INBOX}")
        return

    zips = sorted(INBOX.glob("*.zip"))
    if not zips:
        print("Inbox empty — nothing to process.")
        return

    print(f"Found {len(zips)} zip(s) in inbox:\n")
    results = []

    for zp in zips:
        print(f"Processing {zp.name}...")
        result = process_zip(zp)
        if result:
            results.append(result)
            print(f"  -> {result['folder']}/")
            print(f"     Total: {result['total']}, E: {result['e_pnl']}, T: {result['t_pnl']}")

    if results:
        print(f"\n{'='*50}")
        print("SUMMARY — paste into REGISTRY.md:")
        print(f"{'='*50}")
        for r in results:
            print(f"| **{r['model']}** | — | — | — | **{r['total']}** | {r['e_pnl']} | {r['t_pnl']} | sub {r['sub_id']} |")
    else:
        print("\nNo new submissions processed.")


if __name__ == "__main__":
    main()
