# -*- coding: utf-8 -*-
"""원가 100%(변형선택): nx.bom_line.cs_calc_except 플래그를 레거시 CS_M_ITEM_BOM과 동기화.
구조(엣지) 불변 — 어느 벤더변형이 현행(원가계산)인지 플래그만 CS 정본에 맞춤. SP게이트로 검증.
백업 nx.bom_line_bak_flagsync. --commit 없으면 계획(불일치 수)만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY=('--commit' not in sys.argv)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=n.cursor()
# CS 현행 플래그(제품×자식 → except). 중복시 MAX(제외우선? 아니 현행=0 우선). CS는 (item,mat) 현행 1행 가정, 중복은 MIN(0우선)
CSFLAG="""(SELECT MIN(CASE WHEN ISNULL(cs.CS_CALC_EXCEPT_FLAG,'0')='1' THEN 1 ELSE 0 END)
   FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM cs
   WHERE cs.ITEM_CODE COLLATE DATABASE_DEFAULT=h.item_code COLLATE DATABASE_DEFAULT
     AND cs.MAT_CODE COLLATE DATABASE_DEFAULT=bl.child_item COLLATE DATABASE_DEFAULT
     AND cs.FROM_APPLY_YMD<='991231' AND cs.TO_APPLY_YMD>='260101')"""
# 불일치 수(CS에 매칭행 있고 플래그 다른 것)
q=f"""SELECT COUNT(*) FROM nx.bom_line bl JOIN nx.bom_header h ON h.bom_id=bl.bom_id
   WHERE {CSFLAG} IS NOT NULL AND ISNULL(bl.cs_calc_except,0) <> {CSFLAG}"""
mis=c.execute(q).fetchone()[0]
print(f"cs_calc_except 불일치(CS 매칭행 존재): {mis}건")
if DRY:
    print("DRY (--commit 실행)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_bak_flagsync','U') IS NOT NULL DROP TABLE nx.bom_line_bak_flagsync")
c.execute("SELECT * INTO nx.bom_line_bak_flagsync FROM nx.bom_line")
print("백업 nx.bom_line_bak_flagsync:", c.execute("SELECT COUNT(*) FROM nx.bom_line_bak_flagsync").fetchone()[0])
c.execute(f"""UPDATE bl SET cs_calc_except = {CSFLAG}
   FROM nx.bom_line bl JOIN nx.bom_header h ON h.bom_id=bl.bom_id
   WHERE {CSFLAG} IS NOT NULL AND ISNULL(bl.cs_calc_except,0) <> {CSFLAG}""")
print("동기화 완료. 되돌리기: nx.bom_line_bak_flagsync 복원")
n.close()
