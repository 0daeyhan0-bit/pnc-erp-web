# -*- coding: utf-8 -*-
# 원가(재료비) diff0 검증: 리프별 누적소요량 레거시 vs R01 route (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
c=RO().cursor(); n=NX().cursor()
n.execute("SELECT variant, canonical, category FROM nx.sub_alias")
ALIAS={r[0]:dict(canon=r[1],cat=r[2]) for r in n.fetchall()}
c.execute("SELECT ITEM_CODE, MAT_CODE, USE_QTY FROM PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
EDGES=defaultdict(list)
for r in c.fetchall(): EDGES[(r[0] or '').strip()].append(((r[1] or '').strip(), float(r[2] or 1)))
c.execute("SELECT ITEM_CODE, ITEM_DESC FROM PR_M_ITEM")
NAME={(r[0] or '').strip():(r[1] or '') for r in c.fetchall()}
def is_weld(ch):
    if '용접링' in ch or '용접링' in NAME.get(ch,''): return False
    if ch.startswith(('RAC','BCUP','3H008')): return True
    nm=NAME.get(ch,'')
    return ('Solder' in nm or '용접봉' in nm or '은납' in nm)

def legacy_qty(item):
    out=defaultdict(float)
    def walk(node, cum, seen):
        for ch,q in EDGES.get(node,[]):
            if is_weld(ch): continue
            a=ALIAS.get(ch)
            if a and a['cat'] in ('SUB','SUB_SHARED','DISSOLVED'):
                if ch in seen: continue
                walk(ch, cum*q, seen|{ch})
            else:
                out[ch]+=cum*q
    walk(item,1.0,{item}); return out

def r01_qty(item):
    # PILOT_R01 route
    n.execute("SELECT route_id FROM nx.sourcing_route WHERE item_code=? AND note='PILOT_R01'", item)
    r=n.fetchone()
    if not r: return None
    rid=r[0]
    n.execute("SELECT line_id, parent_line, node_kind, child_item, sub_item, qty FROM nx.sourcing_route_line WHERE route_id=?", rid)
    lines={}; kids=defaultdict(list)
    for lid,pl,nk,ci,si,q in n.fetchall():
        lines[lid]=dict(pl=pl,nk=nk,code=(si if nk=='SUB' else ci),qty=float(q or 1))
        kids[pl].append(lid)
    out=defaultdict(float)
    def walk(lid, cum):
        for cl in kids.get(lid,[]):
            L=lines[cl]
            if L['nk']=='SUB': walk(cl, cum*L['qty'])
            else: out[L['code']]+=cum*L['qty']
    walk(None,1.0); return out

# PILOT_R01 대상
n.execute("SELECT DISTINCT item_code FROM nx.sourcing_route WHERE note='PILOT_R01'")
items=[r[0] for r in n.fetchall()]
print(f"{'제품':<16}{'리프수':>7}{'재료qty diff':>14}  판정")
allpass=True
for it in sorted(items):
    lq=legacy_qty(it); rq=r01_qty(it)
    keys=set(lq)|set(rq)
    bad=[(k, round(lq.get(k,0),4), round(rq.get(k,0),4)) for k in keys if abs(lq.get(k,0)-rq.get(k,0))>1e-6]
    ok = not bad
    allpass = allpass and ok
    print(f"  {it:<16}{len(keys):>6}{('0(일치)' if ok else str(len(bad))+'건 diff'):>14}  {'✔' if ok else '✖ '+str(bad[:2])}")
print(f"\n{'★전체 재료비 diff0 PASS' if allpass else '✖ 일부 불일치'}")
print("DONE")
