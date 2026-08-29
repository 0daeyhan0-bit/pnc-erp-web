# -*- coding: utf-8 -*-
"""nx.bom_line 공정 메타(gagong_proc·s_work·wh_gagong·in_gagong·proc_gubun) 빈값 채움 (BOMLINE_PROCMETA_GAP_260829.md).
   근본=r_bomline_soyo_reconcile 등 엣지추가 도구가 소요엣지 INSERT시 proc 메타 미채움 → 660엣지(+s_work 등) 빈값.
   ★소비자 확인: nx.bom_line.gagong_proc는 plan/원가/backflush 로직에서 미참조(STEP7=item_PROC_GAGONG, backflush=명시 미사용).
     bom.py 표시용만. ⟹ 채워도 무회귀. prodsheet clean walker(mat,gagong_proc grain) 이관 위한 소스 완성.
   규칙: nx.bom_line 필드가 **빈값**이고 PR(item,mat 유일)에 값 있으면 채움(비파괴·비어있는 것만). 백업 nx.bom_line_procmeta_bak. --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
# PR 집계(item,mat) — 유효기간내 MAX(결정적, gagong_proc는 유일 확인됨)
PRAGG = """(SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it, UPPER(LTRIM(RTRIM(MAT_CODE))) mt,
   MAX(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))) gpc, MAX(LTRIM(RTRIM(ISNULL(S_WORK_CODE,'')))) sw,
   MAX(LTRIM(RTRIM(ISNULL(WH_GAGONG_PROC_CODE,'')))) wh, MAX(LTRIM(RTRIM(ISNULL(IN_GAGONG_PROC_CODE,'')))) ig,
   MAX(LTRIM(RTRIM(ISNULL(PROC_GUBUN,'')))) pg
   FROM nx.pr_m_item_bom WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101'
   GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), UPPER(LTRIM(RTRIM(MAT_CODE))))"""
CURH = "(SELECT h.bom_id,h.item_code FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv)"
fields = [('gagong_proc','gpc'), ('s_work','sw'), ('wh_gagong','wh'), ('in_gagong','ig'), ('proc_gubun','pg')]
print("빈값 채움 대상(필드별, nx.bom_line 빈값 & PR 값있음):")
plan = {}
for col, prc in fields:
    c.execute(f"""SELECT COUNT(*) FROM {CURH} cur JOIN nx.bom_line bl ON bl.bom_id=cur.bom_id
      JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
      WHERE ISNULL(LTRIM(RTRIM(bl.{col})),'')='' AND pr.{prc}<>''""")
    plan[col] = c.fetchone()[0]; print(f"  {col}: {plan[col]}")
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_procmeta_bak','U') IS NULL SELECT bom_id,seq,gagong_proc,s_work,wh_gagong,in_gagong,proc_gubun INTO nx.bom_line_procmeta_bak FROM nx.bom_line")
print("백업: nx.bom_line_procmeta_bak")
for col, prc in fields:
    r = c.execute(f"""UPDATE bl SET bl.{col}=pr.{prc}
      FROM nx.bom_line bl JOIN {CURH} cur ON cur.bom_id=bl.bom_id
      JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
      WHERE ISNULL(LTRIM(RTRIM(bl.{col})),'')='' AND pr.{prc}<>''""").rowcount
    print(f"  UPDATE {col}: {r}행")
# 검증: gagong_proc 빈값 잔여(PR값있음) = 0
c.execute(f"""SELECT COUNT(*) FROM {CURH} cur JOIN nx.bom_line bl ON bl.bom_id=cur.bom_id
  JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE ISNULL(LTRIM(RTRIM(bl.gagong_proc)),'')='' AND pr.gpc<>''""")
left = c.fetchone()[0]; print(f"검증: gagong_proc 빈값 잔여 = {left} ({'★PASS' if left==0 else 'FAIL'})")
n.close()
