# -*- coding: utf-8 -*-
"""인덱스 효과 측정 하네스(BEFORE/AFTER 동일코드). 대표 필터쿼리 실행시간(ms) min/median.
   필터값=런타임 자동선정(최빈)이라 before/after 동일. 인수: 라벨(before/after)."""
import sys, io, time, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
TAG = sys.argv[1] if len(sys.argv)>1 else 'run'
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = cn.cursor()

# 필터값 자동선정(최빈/샘플)
mat = c.execute("SELECT TOP 1 MAT_CODE FROM nx.PU_T_STOCK_MAINT WHERE MAT_CODE>'' GROUP BY MAT_CODE ORDER BY COUNT(*) DESC").fetchone()[0]
wo  = c.execute("SELECT TOP 1 WORK_ORDER FROM nx.SA_T_SALE_DTL WHERE WORK_ORDER>'' GROUP BY WORK_ORDER ORDER BY COUNT(*) DESC").fetchone()[0]
# 원가/BOM 공통 존재 ITEM (CS_M_ITEM_BOM 부모 중 PR_M_ITEM_COST에도 있는 것)
itm = c.execute("SELECT TOP 1 b.ITEM_CODE FROM nx.CS_M_ITEM_BOM b WHERE EXISTS(SELECT 1 FROM nx.PR_M_ITEM_COST k WHERE k.ITEM_CODE=b.ITEM_CODE) GROUP BY b.ITEM_CODE ORDER BY COUNT(*) DESC").fetchone()[0]
print(f"[{TAG}] 필터값 mat={mat!r} wo={wo!r} item={itm!r}")

TESTS = [
 ("PU_STOCK_MAINT by MAT", "SELECT COUNT(*),SUM(MAINT_QTY) FROM nx.PU_T_STOCK_MAINT WHERE MAT_CODE=?", (mat,)),
 ("PU_STOCK_MAINT ym+MAT", "SELECT COUNT(*) FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD>='260101' AND MAT_CODE=?", (mat,)),
 ("PR_STOCK_MAINT_MAT MAT", "SELECT COUNT(*) FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAT_CODE=?", (mat,)),
 ("SA_STOCK_MAINT ITEM",   "SELECT COUNT(*) FROM nx.SA_T_STOCK_MAINT WHERE ITEM_CODE=?", (mat,)),
 ("SA_SALE_DTL by WO",     "SELECT COUNT(*) FROM nx.SA_T_SALE_DTL WHERE WORK_ORDER=?", (wo,)),
 ("PR_PROD_DTL by WO",     "SELECT COUNT(*) FROM nx.PR_T_PROD_DTL WHERE WORK_ORDER=?", (wo,)),
 ("PR_M_ITEM_COST ITEM",   "SELECT COUNT(*) FROM nx.PR_M_ITEM_COST WHERE ITEM_CODE=?", (itm,)),
 ("CS_M_ITEM_BOM ITEM",    "SELECT COUNT(*) FROM nx.CS_M_ITEM_BOM WHERE ITEM_CODE=?", (itm,)),
 ("plan_part_mat by WO",   "SELECT COUNT(*) FROM nx.plan_part_mat WHERE WORK_ORDER=?", (wo,)),
 ("BOM재귀CTE(원가전개)",  """WITH b AS (
      SELECT ITEM_CODE,MAT_CODE,0 lv FROM nx.CS_M_ITEM_BOM WHERE ITEM_CODE=?
      UNION ALL
      SELECT x.ITEM_CODE,x.MAT_CODE,b.lv+1 FROM nx.CS_M_ITEM_BOM x JOIN b ON x.ITEM_CODE=b.MAT_CODE WHERE b.lv<10)
      SELECT COUNT(*) FROM b OPTION(MAXRECURSION 20)""", (itm,)),
]
N=6
print(f"[{TAG}] {'query':28s} {'min_ms':>9s} {'med_ms':>9s}")
tot=0
for label,sql,p in TESTS:
    ts=[]
    for _ in range(N):
        t0=time.perf_counter(); c.execute(sql,p); c.fetchall(); ts.append((time.perf_counter()-t0)*1000)
    mn,md=min(ts),statistics.median(ts); tot+=md
    print(f"[{TAG}] {label:28s} {mn:9.1f} {md:9.1f}")
print(f"[{TAG}] {'TOTAL(median합)':28s} {'':>9s} {tot:9.1f}")
cn.close()
