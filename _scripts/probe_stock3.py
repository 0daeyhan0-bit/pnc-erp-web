# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def cols(t):
    print(f"\n-- {t} --")
    try: print(", ".join(db_client.run_query(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION")['COLUMN_NAME'].tolist()))
    except Exception as e: print("ERR:",str(e)[:100])
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:120])

for t in ["PU_T_MONTH_STOCK_WH_DAILY","PU_T_MONTH_STOCK_WH","PU_T_MAT_STOCK_WH_LAST","WH_T_MAT_STOCK"]:
    cols(t)
show("PU_T_MONTH_STOCK_WH_DAILY 상위3", "SELECT TOP 3 * FROM PU_T_MONTH_STOCK_WH_DAILY")
# PU_T_MAT_STOCK_WH: GAGONG_PROC_CODE 분포 (이게 창고/공정 구분인가)
show("PU_T_MAT_STOCK_WH: GAGONG_PROC_CODE 분포", "SELECT GAGONG_PROC_CODE, COUNT(*) c, COUNT(DISTINCT MAT_CODE) items FROM PU_T_MAT_STOCK_WH GROUP BY GAGONG_PROC_CODE ORDER BY c DESC")
show("PU_T_MAT_STOCK_WH: CUST_CODE 분포(사급owner?)", "SELECT TOP 8 CUST_CODE, COUNT(*) c FROM PU_T_MAT_STOCK_WH GROUP BY CUST_CODE ORDER BY c DESC")
# 재고 있는(>0) 자재 건수
show("PU_T_MAT_STOCK_WH 재고>0 요약", "SELECT COUNT(*) rows_all, SUM(CASE WHEN STOCK_QTY>0 THEN 1 ELSE 0 END) rows_pos, COUNT(DISTINCT MAT_CODE) items FROM PU_T_MAT_STOCK_WH")
