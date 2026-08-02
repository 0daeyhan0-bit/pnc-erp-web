# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc, pandas as pd
def live(sql):
    cs=(f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
    cn=pyodbc.connect(cs, readonly=True)
    try: return pd.read_sql(sql, cn)
    finally: cn.close()
def show(t,q):
    print(f"\n== {t} ==")
    try: print(live(q).to_string(index=False))
    except Exception as e: print("ERR",str(e)[:150])

show("PR_T_MONTH_STOCK_WH (생산 파트재고 월마감) 최신 월 TOP10","SELECT TOP 10 STOCK_YYMM, COUNT(*) cnt, SUM(stock_qty) tot FROM PR_T_MONTH_STOCK_WH GROUP BY STOCK_YYMM ORDER BY STOCK_YYMM DESC")
show("PU_T_MONTH_STOCK_WH (자재 월마감) 최신 월 TOP5","SELECT TOP 5 STOCK_YYMM, COUNT(*) cnt FROM PU_T_MONTH_STOCK_WH GROUP BY STOCK_YYMM ORDER BY STOCK_YYMM DESC")
