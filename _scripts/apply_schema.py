# -*- coding: utf-8 -*-
import sys, io, os, re, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
NEWERP = r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP"
sys.path.insert(0, NEWERP)
import db_client

sql_file = sys.argv[1] if len(sys.argv) > 1 else "item_master_v2.sql"
sql_path = os.path.join(NEWERP, sql_file)
with open(sql_path, "r", encoding="utf-8") as f:
    script = f.read()

# Split into batches on lines that are exactly 'GO' (case-insensitive), ignore comment-only/empty batches
batches = re.split(r'(?im)^[ \t]*GO[ \t]*$', script)

def is_executable(b):
    # strip block/line comments to see if anything remains
    nc = re.sub(r'/\*.*?\*/', '', b, flags=re.S)
    nc = re.sub(r'(?m)^\s*--.*$', '', nc)
    return nc.strip() != ''

ok, fail = 0, 0
for i, b in enumerate(batches, 1):
    if not is_executable(b):
        continue
    preview = " ".join(b.split())[:80]
    try:
        db_client.execute_query(b)
        ok += 1
        print(f"[{i}] OK: {preview}")
    except Exception as e:
        fail += 1
        print(f"[{i}] FAIL: {preview}\n     -> {e}")

print(f"\n=== DONE: {ok} ok, {fail} fail ===")
