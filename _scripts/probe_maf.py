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

for it in ('MAF66426701','MGZ62928801'):
    show(f"{it} pu_t_month_stock_wh 2606 (gagong별)","SELECT gagong_proc_code, cust_code, stock_qty FROM pu_t_month_stock_wh WHERE mat_code='"+it+"' AND stock_yymm='2606'")
    show(f"{it} PU_T_MAT_STOCK_WH 현재고","SELECT gagong_proc_code, cust_code, stock_qty FROM PU_T_MAT_STOCK_WH WHERE mat_code='"+it+"'")
    show(f"{it} 07월 이동 건수","SELECT COUNT(*) c FROM pu_t_stock_maint WHERE mat_code='"+it+"' AND maint_ymd>='260701'")
