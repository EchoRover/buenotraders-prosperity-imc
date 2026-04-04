"""
Drop zip files into userdatadump/ and run this script.
It will:
1. Find any unnamed zips (not matching our naming pattern)
2. Extract them, identify the submission ID and algo
3. Rename zip and folder properly
4. Copy json to logs/
5. Print a quick PnL summary
"""

import os
import json
import csv
import io
import zipfile
import shutil
import re

DUMP_DIR = os.path.join(os.path.dirname(__file__), '..', 'userdatadump')
LOGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
DUMP_DIR = os.path.abspath(DUMP_DIR)
LOGS_DIR = os.path.abspath(LOGS_DIR)

def process_zip(zip_path):
    """Process a single zip file."""
    with zipfile.ZipFile(zip_path) as z:
        jsons = [f for f in z.namelist() if f.endswith('.json')]
        if not jsons:
            print(f"  SKIP: no .json in {zip_path}")
            return
        sid = jsons[0].replace('.json', '').split('/')[-1]

    # Check if already processed
    basename = os.path.basename(zip_path)
    if re.match(r'e1_|arjun_|laddoo_|friend_|tutorial_', basename):
        return  # already named

    # Extract to temp dir
    temp_dir = os.path.join(DUMP_DIR, f'_temp_{sid}')
    os.makedirs(temp_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(temp_dir)

    # Find the json and get profit + algo name
    jpath = os.path.join(temp_dir, f'{sid}.json')
    pypath = os.path.join(temp_dir, f'{sid}.py')

    with open(jpath) as f:
        jdata = json.load(f)

    profit = jdata.get('profit', 0)

    # Try to identify algo from .py
    algo_name = 'unknown'
    if os.path.exists(pypath):
        with open(pypath) as f:
            code = f.read(500)
        # Match patterns
        for pattern, name in [
            ('LADDOO', 'laddoo'),
            ('e1_v10', 'e1_v10'), ('e1_v9', 'e1_v9'), ('e1_v8', 'e1_v8'),
            ('e1_v7', 'e1_v7'), ('e1_v6', 'e1_v6'), ('e1_v5', 'e1_v5'),
            ('e1_v4', 'e1_v4'), ('e1_v3', 'e1_v3'), ('e1_v2', 'e1_v2'),
            ('e1_v1', 'e1_v1'), ('e1_p', 'e1_probe'),
            ('crazy', 'e1_crazy'),
            ('trader_v4', 'lakshan_v4'), ('trader_v3', 'lakshan_v3'),
            ('prosperity04', 'arjun'),
        ]:
            if pattern.lower() in code.lower():
                algo_name = name
                break

    # Per-product PnL
    activities = jdata.get('activitiesLog', '')
    e_pnl = t_pnl = 0
    if activities:
        reader = csv.DictReader(io.StringIO(activities), delimiter=';')
        rows = list(reader)
        e_rows = [r for r in rows if r['product'] == 'EMERALDS']
        t_rows = [r for r in rows if r['product'] == 'TOMATOES']
        if e_rows:
            e_pnl = float(e_rows[-1]['profit_and_loss'])
        if t_rows:
            t_pnl = float(t_rows[-1]['profit_and_loss'])

    # Rename
    new_name = f'{algo_name}_{sid}'
    new_zip = os.path.join(DUMP_DIR, f'{new_name}.zip')
    new_dir = os.path.join(DUMP_DIR, new_name)

    os.rename(temp_dir, new_dir)
    os.rename(zip_path, new_zip)

    # Copy to logs
    shutil.copy(os.path.join(new_dir, f'{sid}.json'), os.path.join(LOGS_DIR, f'{new_name}.json'))

    print(f"  {new_name}: {profit:.0f} (E:{e_pnl:.0f} T:{t_pnl:.0f})")


def main():
    print(f"Scanning {DUMP_DIR} for unprocessed zips...\n")
    found = 0
    for f in sorted(os.listdir(DUMP_DIR)):
        if not f.endswith('.zip'):
            continue
        if re.match(r'e1_|arjun_|laddoo_|friend_|tutorial_|lakshan_', f):
            continue
        found += 1
        print(f"Processing: {f}")
        process_zip(os.path.join(DUMP_DIR, f))

    if found == 0:
        print("No new zips to process. All clean.")
    print("\nDone.")


if __name__ == '__main__':
    main()
