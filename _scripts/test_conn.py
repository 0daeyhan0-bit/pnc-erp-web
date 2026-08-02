# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects")
from db_client import run_query

# 1) total table count
q_total = """
SELECT COUNT(*) AS total_tables
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE'
"""
print("=== TOTAL TABLES ===")
print(run_query(q_total).to_string(index=False))

# 2) BOM-related tables (name contains 'bom' case-insensitive)
q_bom = """
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE='BASE TABLE' AND LOWER(TABLE_NAME) LIKE '%bom%'
ORDER BY TABLE_NAME
"""
df = run_query(q_bom)
print(f"\n=== BOM-RELATED TABLES: {len(df)} ===")
print(df.to_string(index=False))
