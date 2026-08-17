# -*- coding: utf-8 -*-
# ★전 제품 R01 구조 스케일 빌드(note='R01') + 제품별 재료비 diff0 검증. 멱등. nx 쓰기.
import sys, time
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c=RO().cursor(); nx=NX(); w=nx.cursor()
w.execute("SELECT variant, canonical, category, route_gubun, route_vendor FROM nx.sub_alias")
ALIAS={r[0]:dict(canon=r[1],cat=r[2],g=r[3],ven=r[4]) for r in w.fetchall()}
c.execute("SELECT ITEM_CODE, MAT_CODE, USE_QTY FROM PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
EDGES=defaultdict(list)
for r in c.fetchall(): EDGES[(r[0] or '').strip()].append(((r[1] or '').strip(), float(r[2] or 1)))
c.execute("SELECT ITEM_CODE, ITEM_DESC FROM PR_M_ITEM")
NAME={(r[0] or '').strip():(r[1] or '') for r in c.fetchall()}
FR,TO='250101','260731'
c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=set(r[0].strip() for r in c.fetchall() if r[0])
def is_weld(ch):
    if '용접링' in ch or '용접링' in NAME.get(ch,''): return False
    if ch.startswith(('RAC','BCUP','3H008')): return True
    nm=NAME.get(ch,'')
    if 'Solder' in nm or '용접봉' in nm: return True
    if '은납' in nm and not EDGES.get(ch): return True   # ★은납재(리프)만 제외 — 은납 SUB조립품(자식보유)은 유지(Routing=실서브 반영)
    return False

def legacy_qty(item):
    out=defaultdict(float)
    def walk(node,cum,seen):
        for ch,q in EDGES.get(node,[]):
            if is_weld(ch): continue
            a=ALIAS.get(ch); rec = a and a['cat'] in ('SUB','SUB_SHARED','DISSOLVED')
            unc = ('-' in ch and not a and EDGES.get(ch))
            if rec or unc:
                if ch in seen: continue
                walk(ch,cum*q,seen|{ch})
            else: out[ch]+=cum*q
    walk(item,1.0,{item}); return out

def build(item):
    w.execute("SELECT route_id FROM nx.sourcing_route WHERE item_code=? AND route_no=1", item)   # ★현행(route_no=1) note무관 전삭제 → PILOT_R01 등 중복 통합
    for r in w.fetchall():
        w.execute("DELETE FROM nx.sourcing_route_line WHERE route_id=?", r[0]); w.execute("DELETE FROM nx.sourcing_route WHERE route_id=?", r[0])
    w.execute("""INSERT INTO nx.sourcing_route(item_code,route_no,route_name,vendor_code,gubun,current_flag,approve_flag,apply_from,note,ins_user)
                 OUTPUT INSERTED.route_id VALUES(?,?,?,?,?,?,?,?,?,?)""", item,1,f"{item}_R01","","자체",1,1,'2026-08-12','R01','R2scale')
    rid=w.fetchone()[0]; seq=[0]; lq=defaultdict(float)
    def emit(node,pl,seen,depth,cum):
        if node in seen or depth>10: return
        seen=seen|{node}
        for ch,qty in EDGES.get(node,[]):
            if is_weld(ch): continue
            a=ALIAS.get(ch); seq[0]+=1; s=seq[0]
            if a and a['cat']=='DISSOLVED':
                emit(ch,pl,seen,depth+1,cum*qty)
            elif a and a['cat'] in ('SUB','SUB_SHARED'):
                canon=a['canon']
                w.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,node_kind,parent_line,sub_item,child_item,child_name,qty,gubun,vendor_code)
                             OUTPUT INSERTED.line_id VALUES(?,?,?,?,?,?,?,?,?,?)""", rid,s,'SUB',pl,canon,canon,f"SUB {canon}",qty,a['g'],a['ven'] or '')
                lid=w.fetchone()[0]; emit(ch,lid,seen,depth+1,cum*qty)
            elif ('-' in ch and not a and EDGES.get(ch)):   # 미정규 '-'변형+자식 → 재귀 전개(pass-through)
                emit(ch,pl,seen,depth+1,cum*qty)
            else:
                g=(a['g'] if a else ''); v=(a['ven'] if a else '') or ''
                w.execute("""INSERT INTO nx.sourcing_route_line(route_id,sort_seq,node_kind,parent_line,child_item,child_name,qty,gubun,vendor_code)
                             VALUES(?,?,?,?,?,?,?,?,?)""", rid,s,'PART',pl,ch,NAME.get(ch,'')[:118],qty,g,v)
                lq[ch]+=cum*qty
    emit(item,None,set(),0,1.0)
    return lq

targets=sorted(p for p in shipped if EDGES.get(p))
print("스케일 대상:", len(targets)); t0=time.time()
npass=0; fails=[]
for i,p in enumerate(targets,1):
    lq=build(p); leg=legacy_qty(p)
    keys=set(lq)|set(leg)
    bad=[k for k in keys if abs(lq.get(k,0)-leg.get(k,0))>1e-6]
    if bad: fails.append((p,len(bad),bad[:3]))
    else: npass+=1
    if i%300==0: nx.commit(); print(f"  ...{i}/{len(targets)} ({time.time()-t0:.0f}s)")
nx.commit()
print(f"\n★재료비 diff0 PASS: {npass}/{len(targets)} · FAIL: {len(fails)}")
for f in fails[:15]: print("  FAIL", f)
w.execute("SELECT COUNT(*) FROM nx.sourcing_route WHERE note='R01'"); print("nx R01 route:", w.fetchone()[0])
w.execute("SELECT COUNT(*) FROM nx.sourcing_route_line l JOIN nx.sourcing_route r ON r.route_id=l.route_id WHERE r.note='R01'"); print("nx R01 라인:", w.fetchone()[0])
nx.close(); print("DONE")
