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

show("각 수불테이블의 최신 일자 (07/16까지 있나?)", """
SELECT 'PU_T_STOCK_MAINT' t, MAX(MAINT_YMD) max_ymd FROM PU_T_STOCK_MAINT
UNION ALL SELECT 'PR_T_STOCK_MAINT_MAT', MAX(MAINT_YMD) FROM PR_T_STOCK_MAINT_MAT
UNION ALL SELECT 'pu_t_cut_dtl', MAX(cut_ymd) FROM pu_t_cut_dtl
UNION ALL SELECT 'pr_t_prod_dtl', MAX(prod_ymd) FROM pr_t_prod_dtl
UNION ALL SELECT 'sa_t_stock_maint', MAX(maint_ymd) FROM sa_t_stock_maint
""")
# 07/01~07/16 P0001 관련 수불 건수 (TEST3에 7월 데이터가 얼마나 있나)
show("PU_T_STOCK_MAINT 7월 일자별 건수", """
SELECT MAINT_YMD, COUNT(*) c FROM PU_T_STOCK_MAINT WHERE MAINT_YMD BETWEEN '260701' AND '260731' GROUP BY MAINT_YMD ORDER BY MAINT_YMD
""")
