# -*- coding: utf-8 -*-
"""nx.bom_line.kitting 을 PR(현행 생산 BOM 정본)에 정렬 — 준비재고체크(ready_setcheck)·키팅 분류 diff0용.
   근본 = bom_line 재빌드가 KITTING_FLAG 를 온전히 안 가져와 810 엣지가 bl=0·PR=1 로 어긋남
     → setcheck 가 '키팅제외' 로 오분류(레거시 466=PR 기준은 포함). 실측(2026-09-08): 815 불일치(810=bl0/PR1).
   ★kitting_flag 는 소요/원가/전개(plan_explode·cost)에서 미참조 — 키팅/setcheck 분류 전용 → 정렬 무회귀.
   PR=현행 생산 BOM 정본(레거시 466 이 실제 사용). CS≡PR 가정은 일부 품목서 거짓(구조 자체가 다름) →
     kitting_flag 는 PR 기준으로 통일. 백업 nx.bom_line_kitting_bak. --commit 없으면 DRY.  §1-9-3 대사정합."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
CURH = "(SELECT h.bom_id,h.item_code FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv)"
PRAGG = "(SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it, UPPER(LTRIM(RTRIM(MAT_CODE))) mt, MAX(CASE WHEN ISNULL(KITTING_FLAG,'0')='1' THEN 1 ELSE 0 END) kit FROM nx.pr_m_item_bom WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))))"
WHERE = f"""FROM nx.bom_line bl JOIN {CURH} cur ON cur.bom_id=bl.bom_id
  JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE ISNULL(bl.kitting,0)<>pr.kit"""
c.execute("SELECT COUNT(*) " + WHERE)
print("정렬 대상(bom_line.kitting <> PR.kit) =", c.fetchone()[0])
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_kitting_bak','U') IS NULL SELECT bom_id,seq,kitting INTO nx.bom_line_kitting_bak FROM nx.bom_line")
r = c.execute("UPDATE bl SET bl.kitting=pr.kit " + WHERE).rowcount
print(f"UPDATE kitting: {r}행. 백업 nx.bom_line_kitting_bak")
c.execute("SELECT COUNT(*) " + WHERE)
left = c.fetchone()[0]; print(f"검증: kitting 불일치 잔여 = {left} ({'★PASS(PR 등가)' if left==0 else 'FAIL'})")
n.close()
