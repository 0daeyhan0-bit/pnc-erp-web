# -*- coding: utf-8 -*-
"""드리프트 정합 원가 게이트 (엔진 전/후 비교판 — 레거시 SP EXECUTE 권한부재로 SP오라클 대체).
논리: 정합 = nx.bom_line을 CS(레거시 SP의 소스)와 일치 → 엔진을 레거시에 더 가깝게만. 전/후 delta = 드리프트의 원가영향.
T = 드리프트 부모(union) + 드리프트 부모의 완제품 조상 + 앵커3 + 랜덤완제품. 앵커 불변 필수.
사용: python r_cost_gate.py before|after  → gate_<label>.json 저장. after 시 before와 자동 diff."""
import sys, os, json
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import pyodbc, db_client
from nx_cost_engine import NxCostEngine
LABEL=sys.argv[1] if len(sys.argv)>1 else 'now'
YMD='260630'; HERE=os.path.dirname(__file__)
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
ro=RO().cursor(); nn=NX().cursor()
# 드리프트 부모 union
ro.execute("SELECT ITEM_CODE,MAT_CODE FROM CS_M_ITEM_BOM WHERE FROM_APPLY_YMD<='991231' AND TO_APPLY_YMD>='260101' AND MAT_CODE NOT LIKE 'RAC%'")
CS=set(((r[0] or '').strip(),(r[1] or '').strip()) for r in ro.fetchall())
nn.execute("SELECT h.item_code,bl.child_item FROM nx.bom_header h JOIN nx.bom_line bl ON bl.bom_id=h.bom_id WHERE bl.child_item NOT LIKE 'RAC%'")
NX_=set(((r[0] or '').strip(),(r[1] or '').strip()) for r in nn.fetchall())
dpar=sorted({p for p,_ in (NX_-CS)} | {p for p,_ in (CS-NX_)})
# 드리프트 부모의 완제품 조상(CS 역전개, 최상위 '-'없는 제품) — 롤업 영향
CSchild2par={}
for p,ch in CS: CSchild2par.setdefault(ch,set()).add(p)
def top_ancestors(x, seen=None, depth=0):
    seen=seen or set()
    if x in seen or depth>10: return set()
    seen.add(x); pars=CSchild2par.get(x)
    if not pars: return {x} if '-' not in x else set()
    out=set()
    for p in pars: out|=top_ancestors(p,seen,depth+1)
    return out
anc=set()
for d in dpar: anc|=top_ancestors(d)
anc={a for a in anc if '-' not in a}
ro.execute("SELECT TOP 20 ITEM_CODE FROM PR_M_ITEM WHERE ISNULL(MAKE_TYPE,'')='1' AND ITEM_CODE NOT LIKE '%-%' ORDER BY NEWID()")
rnd=[(r[0] or '').strip() for r in ro.fetchall()]
bpath=os.path.join(HERE,'gate_before.json')
if LABEL=='after' and os.path.exists(bpath):
    T=sorted(json.load(open(bpath,encoding='utf-8')).keys())   # 동일셋 비교
else:
    T=sorted(set(dpar)|anc|{'AJR75563402','AJR75563503','AJR30077403'}|set(rnd))
print(f"[{LABEL}] T={len(T)} (드리프트부모{len(dpar)} + 완제품조상{len(anc)} + 앵커3 + 랜덤{len(rnd)})")
eng=NxCostEngine(); res={}
for it in T:
    try:
        s=eng.silwon(it,YMD); res[it]={"silwon":s.get('silwon',0),"jae":s.get('jae',0),"gagong":s.get('gagong',0)}
    except Exception as e:
        res[it]={"err":str(e)[:50]}
eng.close()
json.dump(res,open(os.path.join(HERE,f'gate_{LABEL}.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=1)
print(f"  gate_{LABEL}.json 저장 ({len(res)})  앵커 AJR75563402 silwon={res.get('AJR75563402',{}).get('silwon')}")
# after면 before와 diff
if LABEL=='after' and os.path.exists(bpath):
    B=json.load(open(bpath,encoding='utf-8'))
    chg=[]
    for it in T:
        b=B.get(it,{}); a=res.get(it,{})
        if 'silwon' not in b or 'silwon' not in a:
            if b.get('err')!=a.get('err'): chg.append((it,f"err변화 {b.get('err')}→{a.get('err')}"))
            continue
        db=round(a['silwon']-b['silwon'],2)
        if abs(db)>0.5: chg.append((it,f"silwon {b['silwon']}→{a['silwon']} (Δ{db})"))
    print(f"\n  === 전/후 원가 변화 {len(chg)}건 / {len(T)} ===")
    for c in chg[:30]: print("   ·", c[0], c[1])
    a0=B.get('AJR75563402',{}).get('silwon'); a1=res.get('AJR75563402',{}).get('silwon')
    print(f"\n  앵커 AJR75563402: {a0} → {a1}  {'✔불변' if a0==a1 else '✖변화!'}")
print("DONE")
