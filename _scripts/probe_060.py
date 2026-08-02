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

# 좌측 목록 후보 (목표 7,651건 / 재고합 299,913.0076)
show("PU_T_MAT_STOCK_WH (IS0001/Z99990)","SELECT COUNT(*) rows, COUNT(DISTINCT mat_code) mats, SUM(stock_qty) stock FROM PU_T_MAT_STOCK_WH WHERE gagong_proc_code='IS0001' AND cust_code='Z99990'")
show("PU_T_MAT_STOCK_WH 컬럼","SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_MAT_STOCK_WH' ORDER BY ORDINAL_POSITION")
show("PU_T_MAT_STOCK (Z99990)","SELECT COUNT(*) rows, SUM(stock_qty) stock FROM PU_T_MAT_STOCK WHERE cust_code='Z99990'")
# part_code 분포 (자도번=part? or gagong?)
show("PU_T_MAT_STOCK_WH part_code 분포(top)","SELECT TOP 5 part_code, COUNT(*) c FROM PU_T_MAT_STOCK_WH WHERE cust_code='Z99990' GROUP BY part_code ORDER BY c DESC")
