# -*- coding: utf-8 -*-
# 정규화 매핑 확정(드래프트): 자도번 → 카테고리(SUB/LEAF_ROUTE/STUB) + 품번_S{nn}(공용=owner코드 공유) + route(vendor)
# 생산 실사용 PR_M_ITEM_BOM 기준. 읽기전용. 출력=sub_alias_draft.csv
import sys, csv, hashlib, re, os
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def Lc():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
    return pyodbc.connect(cs)
c=Lc().cursor()
FR,TO='250101','260731'
OUT=r'C:\Users\admin\AppData\Local\Temp\claude\d-----------100-AI-AGENT\02b63e35-1303-4eb0-8eb4-29df63d29c62\scratchpad'

c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=sorted(set(r[0].strip() for r in c.fetchall() if r[0]), key=len, reverse=True)
c.execute("SELECT ITEM_CODE, MAKE_TYPE, IN_CUST_CODE, ITEM_DESC FROM PR_M_ITEM")
allit={(r[0] or '').strip():dict(mk=str(r[1]).strip(),cust=(r[2] or '').strip(),desc=r[3]) for r in c.fetchall()}
def find_base(code):
    for b in shipped:
        if code!=b and code.startswith(b+'-'): return b
    return None
variants={code:find_base(code) for code in allit if '-' in code and find_base(code)}
# PR child-set
c.execute("SELECT ITEM_CODE, MAT_CODE, ISNULL(EXCEPT_FLAG,'0') FROM PR_M_ITEM_BOM WHERE ITEM_CODE LIKE '%-%'")
childmap=defaultdict(set)
for r in c.fetchall():
    it=(r[0] or '').strip(); mat=(r[1] or '').strip()
    if it in variants and str(r[2]).strip()!='1' and not mat.startswith('RAC'):
        childmap[it].add(mat)
def sig(v):
    cs=childmap.get(v,set())
    return hashlib.md5('|'.join(sorted(cs)).encode()).hexdigest()[:10] if cs else None
alnum=re.compile(r'^[A-Za-z0-9_\-&\.]+$')

# base별 구조 signature → 로컬 _S{nn}
by_base_sig=defaultdict(dict)   # base -> {sig: local_canon}
sig_bases=defaultdict(set)      # sig -> {base}
for v,b in variants.items():
    s=sig(v)
    if s: sig_bases[s].add(b)
for b in set(variants.values()):
    sigs=set(sig(v) for v in variants if variants[v]==b and sig(v))
    def childn(s):
        any_v=next(v for v in variants if variants[v]==b and sig(v)==s); return len(childmap[any_v])
    for i,s in enumerate(sorted(sigs, key=lambda s:(childn(s),s)),1):
        by_base_sig[b][s]=f"{b}_S{i:02d}"
# 공용: sig owner=min(base). canonical(sig)=owner의 로컬코드
def canon_of(s):
    owner=min(sig_bases[s])
    return by_base_sig[owner][s], owner, len(sig_bases[s])

rows=[]; cat=defaultdict(int)
for v,b in variants.items():
    s=sig(v); vendor=allit[v]['cust']; mk=allit[v]['mk']
    if s is None:
        # 구조없음 → LEAF_ROUTE 또는 STUB
        if not alnum.match(v):
            category='STUB'; canon=''; owner=''; nref=0
        else:
            category='LEAF_ROUTE'; canon=''; owner=''; nref=0   # base+route(vendor)로 흡수
    else:
        canon, owner, nref = canon_of(s)
        category='SUB_SHARED' if nref>1 else 'SUB'
    rows.append(dict(variant=v, base=b, category=category, canonical=canon, owner_base=owner,
                     n_ref_base=nref, route_vendor=vendor, make=mk, desc=allit[v]['desc']))
    cat[category]+=1

# CSV
p=os.path.join(OUT,'sub_alias_draft.csv')
with open(p,'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=['variant','base','category','canonical','owner_base','n_ref_base','route_vendor','make','desc'])
    w.writeheader()
    for r in rows: w.writerow(r)

canon_set=set(r['canonical'] for r in rows if r['canonical'])
shared_sigs=[s for s in sig_bases if len(sig_bases[s])>1]
leaf=[r for r in rows if r['category']=='LEAF_ROUTE']
leaf_novendor=[r for r in leaf if not r['route_vendor']]
print("===== 정규화 매핑 확정 드래프트 =====")
print(f"  변형 총: {len(rows)}")
for k in ['SUB','SUB_SHARED','LEAF_ROUTE','STUB']:
    print(f"    {k}: {cat[k]}")
print(f"  정규 SUB 코드(품번_S{{nn}}) 유니크: {len(canon_set)}")
print(f"  공용 signature(여러base): {len(shared_sigs)}  → 공용 정규SUB 코드: {len(set(canon_of(s)[0] for s in shared_sigs))}")
print(f"  LEAF_ROUTE 中 vendor 없음(흡수시 route 미상): {len(leaf_novendor)}  예:{[r['variant'] for r in leaf_novendor[:5]]}")
# 공용 최다 예시
top=sorted(shared_sigs, key=lambda s:len(sig_bases[s]), reverse=True)[:5]
print("  공용 최다 예시(코드·참조base수):")
for s in top:
    cc,ow,n=canon_of(s); print(f"    {cc}  ref_base={n}  예bases={sorted(sig_bases[s])[:4]}")
print(f"\n  CSV: {p}")
print("DONE")
