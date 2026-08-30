# -*- coding: utf-8 -*-
"""nx.bom_line.gagong_proc 잔여 non-empty 차이(122)를 PR로 정렬 (BOMLINE_PROCMETA_GAP_260829.md §잔여122).
   빈값채움(r_bomline_procmeta_fill) 후 남은 = nx.bom(기존DB 원빌드)이 PR과 다른 non-empty(nx'S1'↔PR'S4' 등).
   ★gagong_proc는 로직 소비자 없음(plan=item_PROC_GAGONG·backflush 미사용·bom.py 표시만) → 정렬 무회귀. PR=현행 생산공정 정본.
   ★gagong_proc만(다른 proc필드 non-empty차는 미대상). 백업=nx.bom_line_procmeta_bak(fill때 원값 보존). --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
CURH = "(SELECT h.bom_id,h.item_code FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv)"
PRAGG = "(SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))) it,UPPER(LTRIM(RTRIM(MAT_CODE))) mt,MAX(LTRIM(RTRIM(ISNULL(GAGONG_PROC_CODE,'')))) gpc FROM nx.pr_m_item_bom WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))),UPPER(LTRIM(RTRIM(MAT_CODE))))"
WHERE = f"""FROM nx.bom_line bl JOIN {CURH} cur ON cur.bom_id=bl.bom_id
  JOIN {PRAGG} pr ON pr.it=UPPER(LTRIM(RTRIM(cur.item_code))) AND pr.mt=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE ISNULL(LTRIM(RTRIM(bl.gagong_proc)),'')<>'' AND ISNULL(LTRIM(RTRIM(bl.gagong_proc)),'')<>pr.gpc AND pr.gpc<>''"""
c.execute("SELECT COUNT(*) "+WHERE)
print("정렬 대상(non-empty·nx≠PR·PR값있음) =", c.fetchone()[0])
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_procmeta_bak','U') IS NULL SELECT bom_id,seq,gagong_proc,s_work,wh_gagong,in_gagong,proc_gubun INTO nx.bom_line_procmeta_bak FROM nx.bom_line")
r = c.execute("UPDATE bl SET bl.gagong_proc=pr.gpc "+WHERE).rowcount
print(f"UPDATE gagong_proc: {r}행. 백업 nx.bom_line_procmeta_bak")
c.execute(f"""SELECT COUNT(*) FROM {CURH} cur JOIN nx.bom_line bl ON bl.bom_id=cur.bom_id
  JOIN nx.pr_m_item_bom pr ON UPPER(LTRIM(RTRIM(pr.ITEM_CODE)))=UPPER(LTRIM(RTRIM(cur.item_code))) AND UPPER(LTRIM(RTRIM(pr.MAT_CODE)))=UPPER(LTRIM(RTRIM(bl.child_item)))
  WHERE ISNULL(LTRIM(RTRIM(bl.gagong_proc)),'')<>ISNULL(LTRIM(RTRIM(pr.GAGONG_PROC_CODE)),'')""")
left = c.fetchone()[0]; print(f"검증: gagong_proc 전체 불일치 잔여 = {left} ({'★PASS(PR 완전등가)' if left==0 else 'FAIL'})")
n.close()
