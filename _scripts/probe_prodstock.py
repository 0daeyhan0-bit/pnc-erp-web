# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:120])

show("PR_T_MAT_STOCK_WH 상위8", "SELECT TOP 8 * FROM PR_T_MAT_STOCK_WH")
show("PART_CODE 분포(=창고/공정 구분?)", "SELECT PART_CODE, COUNT(*) c, COUNT(DISTINCT MAT_CODE) items, SUM(CASE WHEN STOCK_QTY>0 THEN 1 ELSE 0 END) pos FROM PR_T_MAT_STOCK_WH GROUP BY PART_CODE ORDER BY c DESC")
show("요약", "SELECT COUNT(*) rows, SUM(CASE WHEN STOCK_QTY>0 THEN 1 ELSE 0 END) pos, COUNT(DISTINCT MAT_CODE) items FROM PR_T_MAT_STOCK_WH")
# PART_CODE가 res_wh.wh_code 와 매칭되나
show("PART_CODE ∩ res_wh.wh_code", "SELECT DISTINCT p.PART_CODE, w.wh_name FROM PR_T_MAT_STOCK_WH p LEFT JOIN res_wh w ON LTRIM(RTRIM(w.wh_code))=LTRIM(RTRIM(p.PART_CODE))")
