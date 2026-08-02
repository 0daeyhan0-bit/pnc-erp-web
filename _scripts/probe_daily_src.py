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

print("== DAILY 테이블 컬럼 ==")
print(", ".join(db_client.run_query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_MONTH_STOCK_WH_DAILY' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))

print("\n== [LIVE] 260717 gagong_proc_code 분포 (자재창고 코드) ==")
print(live_read("SELECT gagong_proc_code, COUNT(*) cnt FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD='260717' GROUP BY gagong_proc_code ORDER BY cnt DESC").to_string(index=False))

print("\n== [LIVE] 260717 샘플 3행 (활동 큰 것) ==")
print(live_read("""SELECT TOP 3 mat_code, gagong_proc_code, basic_qty, basic_amt, input_qty, input_amt, output_qty, output_amt, trans_qty, trans_amt, stock_qty, stock_amt, last_in_ymd
FROM PU_T_MONTH_STOCK_WH_DAILY WHERE cust_code='Z99990' AND STOCK_YMD='260717' AND input_qty>0 ORDER BY input_amt DESC""").to_string(index=False))

print("\n== 자재 원시 이동 후보: PU_T_STOCK_MAINT 컬럼 ==")
try:
    print(", ".join(db_client.run_query("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_STOCK_MAINT' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
except Exception as e: print("ERR", str(e)[:100])
