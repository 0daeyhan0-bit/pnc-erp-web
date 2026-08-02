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

NAME_LIKE = """
SELECT o.name, o.type_desc FROM sys.objects o
WHERE o.type IN ('P','FN','TF','IF')
  AND (o.name LIKE '%stock_260%' OR o.name LIKE '%STOCK_WH_DAILY%' OR o.name LIKE '%일별수불%'
       OR o.name LIKE '%일수불%' OR o.name LIKE '%pu_stock%' OR o.name LIKE '%자재%수불%')
ORDER BY o.name
"""
DEF_LIKE = """
SELECT o.name, o.type_desc FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id
WHERE m.definition LIKE '%MONTH_STOCK_WH_DAILY%' OR m.definition LIKE '%STOCK_WH_DAILY%'
ORDER BY o.name
"""
for lbl, rd in (("TEST3", db_client.run_query), ("LIVE", live_read)):
    print(f"\n===== [{lbl}] 이름에 260/일수불/pu_stock 포함 SP =====")
    try: print(rd(NAME_LIKE).to_string(index=False))
    except Exception as e: print("ERR", str(e)[:120])
    print(f"----- [{lbl}] 정의에 STOCK_WH_DAILY 참조 -----")
    try: print(rd(DEF_LIKE).to_string(index=False))
    except Exception as e: print("ERR", str(e)[:120])
