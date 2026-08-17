# -*- coding: utf-8 -*-
# ★공정 정규화: 자도번 nx.routing → 품번_S{nn} 복사 + 공용 routing 일치 검증. nx 쓰기·멱등.
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
n=NX(); w=n.cursor()
# canonical → 소스 자도번들
w.execute("SELECT canonical, variant FROM nx.sub_alias WHERE category IN ('SUB','SUB_SHARED') AND canonical IS NOT NULL")
canon2vars=defaultdict(list)
for r in w.fetchall(): canon2vars[r[0]].append(r[1])
# 자도번별 routing (item_code=자도번) — 공정 시그니처
w.execute("SELECT item_code, proc_code, work_qty, prod_uph, calc_gubun, sort_seq FROM nx.routing WHERE item_code LIKE '%-%'")
rt=defaultdict(list)
for r in w.fetchall(): rt[(r[0] or '').strip()].append((r[1],float(r[2] or 0),float(r[3] or 0),r[4],r[5]))
def sig(rows): return tuple(sorted((p,round(wq,3)) for p,wq,uph,cg,sq in rows if wq>0))

# 기존 canonical routing 정리(멱등)
w.execute("DELETE FROM nx.routing WHERE item_code LIKE '%[_]S[0-9][0-9]'")
ins=0; nocanon=0; mism=[]
for canon, vars_ in canon2vars.items():
    # routing 보유 자도번 소스
    srcs=[v for v in vars_ if rt.get(v)]
    if not srcs: nocanon+=1; continue
    # 공용 routing 일치 검증
    sigs=set(sig(rt[v]) for v in srcs)
    if len(sigs)>1: mism.append((canon, len(sigs)))
    src=srcs[0]  # 대표(첫 소스)
    for p,wq,uph,cg,sq in rt[src]:
        w.execute("""INSERT INTO nx.routing(p_item,item_code,proc_code,work_qty,prod_uph,calc_gubun,sort_seq)
                     VALUES(?,?,?,?,?,?,?)""", '', canon, p, wq, uph, cg, sq)
        ins+=1
n.commit()
print(f"공정 정규화: canonical {len(canon2vars)}개 中 routing 복사 {len(canon2vars)-nocanon} (공정없는 SUB {nocanon})")
print(f"  삽입 routing 행: {ins}")
print(f"  ★공용 routing 불일치(자도번들 공정 다름): {len(mism)}  예:{mism[:6]}")
# 검증: canonical routing == 소스 자도번 routing (샘플)
print("\n검증 샘플:")
for canon in list(canon2vars)[:4]:
    w.execute("SELECT proc_code, work_qty FROM nx.routing WHERE item_code=? AND work_qty>0 ORDER BY proc_code", canon)
    got=[(r[0],float(r[1])) for r in w.fetchall()]
    src=[v for v in canon2vars[canon] if rt.get(v)]
    exp=sorted([(p,wq) for p,wq,uph,cg,sq in rt[src[0]] if wq>0]) if src else []
    print(f"  {canon}: nx={sorted(got)}  == 소스({src[0] if src else '-'}) {sorted(exp)}  {'✔' if sorted(got)==sorted(exp) else '✖'}")
w.execute("SELECT COUNT(DISTINCT item_code) FROM nx.routing WHERE item_code LIKE '%[_]S[0-9][0-9]'")
print(f"\nnx.routing _S 키(정규화후): {w.fetchone()[0]}")
n.close(); print("DONE")
