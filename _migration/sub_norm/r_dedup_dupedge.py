# -*- coding: utf-8 -*-
"""(A) 중복 BOM 엣지 dedup — 생산 소요 2배 해소 (2026-08-29, PLAN_DOUBLECOUNT_ROOTCAUSE_260829.md).
   nx.bom_line 최신헤더에 같은 (부모→자식)이 2행(cs_calc=0 + cs_calc=1, 둘 다 except=0)이면 v_pr_bom이 둘 다 계상 → 생산 소요 2배.
   레거시 PR_M_ITEM_BOM은 1엣지 = 정답. dedup = 중복 중 cs_calc=1 행만 except_flag=1(생산 제외). 남는 cs_calc=0 행 qty_pr=레거시.
   ★원가 무영향: nx_cost_engine은 except_flag 미참조(cs_calc_except만) — 코드로 확인. cs_calc_except 미변경.
   = r_bomline_soyo_reconcile.py §99-102 dedup의 수술적 단독본. 백업 nx.bom_line_dedupA_bak. --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
SEL = """WITH cur AS (SELECT h.bom_id FROM nx.bom_header h
   JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx
     ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv),
 dup AS (SELECT c2.bom_id, b.child_item FROM cur c2 JOIN nx.bom_line b ON b.bom_id=c2.bom_id
   GROUP BY c2.bom_id,b.child_item HAVING COUNT(*)>1)
 SELECT b.bom_id, b.seq FROM nx.bom_line b JOIN dup d ON b.bom_id=d.bom_id AND b.child_item=d.child_item
 WHERE CAST(b.cs_calc_except AS int)=1 AND CAST(ISNULL(b.except_flag,0) AS int)=0"""
tgt = c.execute(SEL).fetchall()
print(f"dedup 대상(중복 cs_calc=1·except=0 행) = {len(tgt)}")
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
# 백업(멱등)
c.execute("IF OBJECT_ID('nx.bom_line_dedupA_bak','U') IS NULL SELECT * INTO nx.bom_line_dedupA_bak FROM nx.bom_line WHERE 1=0")
for bid, seq in tgt:
    c.execute("INSERT INTO nx.bom_line_dedupA_bak SELECT * FROM nx.bom_line WHERE bom_id=? AND seq=?", bid, seq)
    c.execute("UPDATE nx.bom_line SET except_flag=1 WHERE bom_id=? AND seq=?", bid, seq)
print(f"COMMIT: {len(tgt)}행 except_flag=1. 백업 nx.bom_line_dedupA_bak. 되돌리기=백업행 except_flag=0 복원.")
# 검증: 잔여 중복(cs_calc=1·except=0) = 0
left = c.execute(SEL).fetchone()
left_n = len(c.execute(SEL).fetchall())
print(f"검증: 잔여 dedup대상 = {left_n} ({'★PASS' if left_n==0 else 'FAIL'})")
n.close()
