# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live_read(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
        f"DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    conn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, conn)
    finally: conn.close()

Q = """
SELECT o.name, o.type_desc
FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
WHERE m.definition LIKE '%PU_T_MONTH_STOCK_WH%'
  AND m.definition LIKE '%input_qty%'
ORDER BY o.name
"""
for lbl, rd in (("TEST3", db_client.run_query), ("LIVE", live_read)):
    print(f"\n===== [{lbl}] PU_T_MONTH_STOCK_WH + input_qty 참조 SP =====")
    try: print(rd(Q).to_string(index=False))
    except Exception as e: print("ERR", str(e)[:120])

# 광범위: 이름에 260 또는 STOCK 들어가는 모든 프로시저 (수불 관련)
Q2 = "SELECT name FROM sys.objects WHERE type='P' AND (name LIKE '%260%' OR name LIKE '%_040%' OR name LIKE '%_160%' OR name LIKE '%STOCK%' OR name LIKE '%수불%') ORDER BY name"
print("\n===== [LIVE] type=P 중 260/160/040/STOCK/수불 이름 =====")
try: print(live_read(Q2).to_string(index=False))
except Exception as e: print("ERR", str(e)[:120])
