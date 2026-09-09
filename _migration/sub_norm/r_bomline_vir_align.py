# -*- coding: utf-8 -*-
"""nx.bom_line.vir_item 을 PR_M_ITEM_BOM.VIR_ITEM_FLAG(레거시 현행 정본)에 정합.
   근본 = bom_line 재구축이 레거시의 최근 vir_item 편집(가상도번 지정)을 못 따라감 → SUB 재귀 누락/과다.
   ★vir_item 은 소요/재고차감 재귀에 영향(가상도번=1이면 펼침, 0이면 말단) → 편성·prodsheet 결과 좌우.
   ★원가엔진(material)도 bom_line 전개 → vir 변경이 원가에 영향 가능 → 적용 후 원가 diff0 검증 필수.
   규칙: 현행헤더(MAX version) bom_line 엣지의 vir_item 이 PR(item,mat MAX)과 다르면 PR값으로.
   백업 nx.bom_line_vir_bak. --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
CURH = "(SELECT h.bom_id,h.item_code FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv)"
PRAGG = "(SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,UPPER(LTRIM(RTRIM(MAT_CODE))) mt,MAX(CAST(ISNULL(VIR_ITEM_FLAG,'0') AS int)) vf FROM nx.pr_m_item_bom WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))),UPPER(LTRIM(RTRIM(MAT_CODE))))"
WHERE = f"""FROM nx.bom_line bl JOIN {CURH} cur ON cur.bom_id=bl.bom_id
  JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE (CASE WHEN ISNULL(bl.vir_item,0)=1 THEN 1 ELSE 0 END) <> pr.vf"""
c.execute("SELECT COUNT(*) " + WHERE)
print("vir 정합 대상(bom_line≠PR) =", c.fetchone()[0])
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_vir_bak','U') IS NULL SELECT bom_id,seq,vir_item INTO nx.bom_line_vir_bak FROM nx.bom_line")
r = c.execute("UPDATE bl SET bl.vir_item=pr.vf " + WHERE).rowcount
print(f"UPDATE vir_item: {r}행. 백업 nx.bom_line_vir_bak")
c.execute("SELECT COUNT(*) " + WHERE)
left = c.fetchone()[0]
print(f"검증: vir 불일치 잔여 = {left} ({'★PASS' if left == 0 else 'FAIL'})")
n.close()
