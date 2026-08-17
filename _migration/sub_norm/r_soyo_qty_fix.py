# -*- coding: utf-8 -*-
"""단일BOM 소요 qty 정합(잔여): 소요qty(PR)≠원가qty(CS)인 원가공유 엣지 13건을 이중엣지로 분리.
 - 원본 엣지(cs_calc_except=0): 원가용 유지 + except_flag=1(소요 제외)
 - 소요복제 엣지 신설: PR qty, except_flag=0(소요), cs_calc_except=1(원가 제외)
 → 소요/조달=PR qty 정확, 원가=CS qty 불변(엔진 cs_calc_except만). 빈 child 엣지 정리.
 백업 nx.bom_line_bak_qtyfix. --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
def S(x): return str(x).strip() if x is not None else ''
pr = {}
for r in c.execute("SELECT LTRIM(RTRIM(ITEM_CODE)),LTRIM(RTRIM(MAT_CODE)),CONVERT(float,USE_QTY) FROM nx.PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND LTRIM(RTRIM(MAT_CODE)) NOT LIKE 'RAC%' AND MAT_CODE>''").fetchall():
    pr[(S(r[0]), S(r[1]))] = round(float(r[2] or 0), 4)
rows = c.execute("""SELECT LTRIM(RTRIM(h.item_code)),LTRIM(RTRIM(b.child_item)),CONVERT(float,b.qty),b.cs_calc_except,b.bom_id,b.seq
   FROM nx.bom_header h JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv
   JOIN nx.bom_line b ON b.bom_id=h.bom_id WHERE ISNULL(b.except_flag,0)=0 AND b.child_item NOT LIKE 'RAC%' AND b.child_item>''""").fetchall()
qd = []
for r in rows:
    k = (S(r[0]), S(r[1]))
    if k in pr and abs(pr[k]-float(r[2] or 0)) > 0.001 and int(r[3]) == 0:
        qd.append((k, pr[k], round(float(r[2] or 0), 4), int(r[4]), int(r[5])))
empty = c.execute("SELECT COUNT(*) FROM nx.bom_line WHERE ISNULL(LTRIM(RTRIM(child_item)),'')=''").fetchone()[0]
print(f"이중엣지 분리대상(원가공유 qty차): {len(qd)}건 / 빈 child 정리: {empty}건")
for x in qd: print(f"  {x[0][0]:<18}→{x[0][1]:<16} 소요PR={x[1]} 원가nx={x[2]}")
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
c.execute("IF OBJECT_ID('nx.bom_line_bak_qtyfix','U') IS NULL SELECT * INTO nx.bom_line_bak_qtyfix FROM nx.bom_line")
c.execute("DELETE FROM nx.bom_line WHERE ISNULL(LTRIM(RTRIM(child_item)),'')=''")
for (p, ch), prq, nxq, bid, seq in qd:
    # 원본: 소요 제외
    c.execute("UPDATE nx.bom_line SET except_flag=1 WHERE bom_id=? AND seq=?", bid, seq)
    # 소요복제: PR qty, 원가 제외
    ns = c.execute("SELECT ISNULL(MAX(seq),0)+1 FROM nx.bom_line WHERE bom_id=?", bid).fetchone()[0]
    c.execute("""INSERT INTO nx.bom_line(bom_id,seq,child_item,qty,node_type,cs_calc_except,lme_except,sagub_default,is_optional,except_flag,set_except,kitting,vir_item,remarks)
      VALUES(?,?,?,?,'키팅',1,0,0,0,0,0,0,0,'[qtyfix 소요PRqty cs_except=1]')""", bid, ns, ch, prq)
print(f"완료: 이중엣지 {len(qd)} + 빈엣지 정리 {empty}. 되돌리기: nx.bom_line_bak_qtyfix")
n.close()
