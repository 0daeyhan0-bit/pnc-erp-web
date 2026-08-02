# -*- coding: utf-8 -*-
import sys, io, warnings, os
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("현재 접속 DB:", db_client.DB_DATABASE)
def cnt(t):
    try: return int(db_client.run_query(f"SELECT COUNT(*) c FROM {t}").iloc[0,0])
    except Exception as e: return f"(없음/에러: {str(e)[:40]})"
print("\n[원본 테이블]")
for t in ["PR_M_ITEM","PR_M_ITEM_COST","CM_M_CUST","PR_M_ITEM_BOM"]:
    print(f"  {t:<18}: {cnt(t)}")
print("\n[우리 차세대 스키마]")
for t in ["CM_ITEM_MST","CM_PARTNER","CM_PARTNER_ROLE","PR_BOM","PR_BOM_COMP","CM_ITEM_PRICE_HIST","CM_UOM"]:
    print(f"  {t:<18}: {cnt(t)}")
