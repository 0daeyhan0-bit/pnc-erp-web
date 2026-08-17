# -*- coding: utf-8 -*-
"""단일BOM 운영통일 옵션1: nx.bom_line의 소요-view(except_flag≠1)를 PR_M_ITEM_BOM 소요(EXCEPT_FLAG≠1)에 정합.
 원가엔진은 cs_calc_except만 필터(except_flag 미사용, lines() 확인) → except_flag 변경·cs_calc_except=1 엣지추가는 원가 무영향.
 규칙:
  - PR 소요엣지가 nx에 except_flag=1로 있으면 → except_flag=0 (소요 포함)
  - PR 소요엣지가 nx에 아예 없으면 → 추가(except_flag=0, cs_calc_except=1[원가제외], qty=PR)  ※부모 헤더 없으면 생성, 자식 nx.item 없으면 최소생성
  - nx 소요-view에 있는데 PR 소요에 없으면 → except_flag=1 (소요 제외)
 백업 nx.bom_line_bak_soyorec / nx.bom_header_bak_soyorec. --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
def S(x): return (str(x).strip() if x is not None else '')
# PR 소요 엣지(except≠1): (p,c)->qty
pr = {}
for r in c.execute("SELECT LTRIM(RTRIM(ITEM_CODE)),LTRIM(RTRIM(MAT_CODE)),USE_QTY FROM nx.PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1'").fetchall():
    pr[(S(r[0]), S(r[1]))] = float(r[2] or 0)
# nx.bom_line 엣지: (p,c)->(bom_id,seq,except_flag,cs_calc_except)  최신헤더
nx = {}
for r in c.execute("""SELECT LTRIM(RTRIM(h.item_code)),LTRIM(RTRIM(b.child_item)),b.bom_id,b.seq,b.except_flag
     FROM nx.bom_header h
     JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv
     JOIN nx.bom_line b ON b.bom_id=h.bom_id""").fetchall():
    nx[(S(r[0]), S(r[1]))] = (int(r[2]), int(r[3]), int(r[4] or 0))
# 헤더맵(최신), nx.item 존재
hdr = {S(r[0]): int(r[1]) for r in c.execute("""SELECT h.item_code,h.bom_id FROM nx.bom_header h
     JOIN (SELECT item_code,MAX(ISNULL(version,1)) mv FROM nx.bom_header GROUP BY item_code) mx ON mx.item_code=h.item_code AND ISNULL(h.version,1)=mx.mv""").fetchall()}
items = set(S(r[0]) for r in c.execute("SELECT item_code FROM nx.item").fetchall())
flip_in = [k for k in pr if k in nx and nx[k][2] == 1]          # except1→0 (소요 포함)
flip_out = [k for k in nx if k not in pr and nx[k][2] == 0]     # except0→1 (소요 제외)
add = [(k, pr[k]) for k in pr if k not in nx]                    # 추가
need_hdr = sorted(set(p for (p, cc), q in add if p not in hdr))
need_item = sorted(set(cc for (p, cc), q in add if cc not in items))
print(f"소요-view 정합 계획:")
print(f"  except 1→0(소요포함): {len(flip_in)}")
print(f"  except 0→1(소요제외): {len(flip_out)}")
print(f"  엣지 추가(except0·cs_calc_except1): {len(add)}  (헤더생성 {len(need_hdr)}부모 / nx.item생성 {len(need_item)})")
if DRY:
    print("DRY (--commit 로 적용)"); n.close(); sys.exit()
# 백업
for t in ('bom_line', 'bom_header'):
    c.execute(f"IF OBJECT_ID('nx.{t}_bak_soyorec','U') IS NULL SELECT * INTO nx.{t}_bak_soyorec FROM nx.{t}")
print("백업: nx.bom_line_bak_soyorec / nx.bom_header_bak_soyorec")
# nx.item 최소생성(누락 자식): item_code·item_name·item_type NOT NULL. 이름=live ITEM_DESC 우선. 멱등.
for it in need_item:
    if c.execute("SELECT COUNT(*) FROM nx.item WHERE item_code=?", it).fetchone()[0]: continue
    nm = c.execute("SELECT TOP 1 LTRIM(RTRIM(ITEM_DESC)) FROM nx.PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_CODE))=?", it).fetchone()
    nm = (nm[0] if nm and nm[0] else it)
    c.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,'')", it, nm)
# 헤더 생성(누락 부모): 부모도 nx.item FK → 없으면 먼저 생성. bom_id=IDENTITY → OUTPUT회수. 멱등.
for p in need_hdr:
    ex = c.execute("SELECT TOP 1 bom_id FROM nx.bom_header WHERE item_code=? ORDER BY ISNULL(version,1) DESC", p).fetchone()
    if ex:
        hdr[p] = int(ex[0]); continue
    if not c.execute("SELECT COUNT(*) FROM nx.item WHERE item_code=?", p).fetchone()[0]:
        nmp = c.execute("SELECT TOP 1 LTRIM(RTRIM(ITEM_DESC)) FROM nx.PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_CODE))=?", p).fetchone()
        c.execute("INSERT INTO nx.item(item_code,item_name,item_type) VALUES(?,?,'')", p, (nmp[0] if nmp and nmp[0] else p))
    bid = c.execute("INSERT INTO nx.bom_header(item_code,version,apply_from,status) OUTPUT INSERTED.bom_id VALUES(?,1,'2000-01-01','확정')", p).fetchone()[0]
    hdr[p] = int(bid)
# except flip
for (p, cc) in flip_in:
    bid, seq, _ = nx[(p, cc)]
    c.execute("UPDATE nx.bom_line SET except_flag=0 WHERE bom_id=? AND seq=?", bid, seq)
for (p, cc) in flip_out:
    bid, seq, _ = nx[(p, cc)]
    c.execute("UPDATE nx.bom_line SET except_flag=1 WHERE bom_id=? AND seq=?", bid, seq)
# 엣지 추가
nseq = {}
for (p, cc), q in add:
    bid = hdr[p]
    if bid not in nseq:
        nseq[bid] = c.execute("SELECT ISNULL(MAX(seq),0) FROM nx.bom_line WHERE bom_id=?", bid).fetchone()[0]
    nseq[bid] += 1
    c.execute("""INSERT INTO nx.bom_line(bom_id,seq,child_item,qty,node_type,cs_calc_except,lme_except,sagub_default,is_optional,except_flag,set_except,kitting,vir_item,remarks)
      VALUES(?,?,?,?,'키팅',1,0,0,0,0,0,0,0,'[soyorec 2026-08-13 PR소요정합 cs_except=1]')""", bid, nseq[bid], cc, q)
print(f"완료: flip_in {len(flip_in)} / flip_out {len(flip_out)} / add {len(add)}. 되돌리기: *_bak_soyorec")
n.close()
