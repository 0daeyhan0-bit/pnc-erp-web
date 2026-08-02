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
    except Exception as e: print("ERR",str(e)[:160])

show("pr_t_mat_stock_wh 컬럼","SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='pr_t_mat_stock_wh' ORDER BY ORDINAL_POSITION")
# 460 좌측 = pr_t_mat_stock_wh 그룹(part,mat) — 목표 9,784건 / 184,885
show("460 좌측 후보(part,mat 그룹)","SELECT COUNT(*) rows, SUM(sq) totstock FROM (SELECT part_code, mat_code, SUM(stock_qty) sq FROM pr_t_mat_stock_wh GROUP BY part_code, mat_code) x")
show("460 좌측(재고<>0만)","SELECT COUNT(*) rows, SUM(sq) totstock FROM (SELECT part_code, mat_code, SUM(stock_qty) sq FROM pr_t_mat_stock_wh GROUP BY part_code, mat_code HAVING SUM(stock_qty)<>0) x")
show("part_code 분포(top)","SELECT TOP 10 part_code, COUNT(*) c, SUM(stock_qty) s FROM pr_t_mat_stock_wh GROUP BY part_code ORDER BY c DESC")
