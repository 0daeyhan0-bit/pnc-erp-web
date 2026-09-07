# -*- coding: utf-8 -*-
"""nx.bom_line.sagub_default 를 PR_M_ITEM_BOM.SAGUB_FLAG(레거시 현행 정본, §3 sagub 정본소스)에 정합.
   근본 = bom_line 재구축이 레거시 SAGUB_FLAG 편집을 못 따라감 → sagub_default 드리프트.
   ★sagub_default 소비자 = prodsheet 재고차감(sag=0만 차감)·weight_explode 중량정산(sag≠1)·setin 사급소진.
     ⟹ 적용 후 원가·중량·prodsheet 다중 검증 필수(레거시 대비 수렴 확인).
   규칙: 현행헤더 bom_line 엣지 sagub_default 가 PR(item,mat MAX)과 다르면 PR값으로. 백업 nx.bom_line_sagub_bak. --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
CURH = "(SELECT h.bom_id,h.item_code FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv)"
PRAGG = "(SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,UPPER(LTRIM(RTRIM(MAT_CODE))) mt,MAX(CAST(ISNULL(SAGUB_FLAG,'0') AS int)) sf FROM nx.pr_m_item_bom WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))),UPPER(LTRIM(RTRIM(MAT_CODE))))"
WHERE = f"""FROM nx.bom_line bl JOIN {CURH} cur ON cur.bom_id=bl.bom_id
  JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE (CASE WHEN ISNULL(bl.sagub_default,0)=1 THEN 1 ELSE 0 END) <> pr.sf"""
c.execute("SELECT COUNT(*) " + WHERE)
print("sagub_default 정합 대상(bom_line≠PR) =", c.fetchone()[0])
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_sagub_bak','U') IS NULL SELECT bom_id,seq,sagub_default INTO nx.bom_line_sagub_bak FROM nx.bom_line")
r = c.execute("UPDATE bl SET bl.sagub_default=pr.sf " + WHERE).rowcount
print(f"UPDATE sagub_default: {r}행. 백업 nx.bom_line_sagub_bak")
c.execute("SELECT COUNT(*) " + WHERE)
left = c.fetchone()[0]
print(f"검증: sagub 불일치 잔여 = {left} ({'PASS' if left == 0 else 'FAIL'})")
n.close()
