# -*- coding: utf-8 -*-
"""#1 bom/tree 올바른 검증: src=nx(nx.bom_line) 트리 리프 vs 레거시 SP 구조(실원가용 전개) 리프.
SP struct(get_oracle) = 실원가용 전개(cs_calc_except+매입중단). 용접봉(RAC) 제외, 자도번→base 정규화 후 대조. (pncind)"""
import sys, io, json, urllib.request
from urllib.parse import quote
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import pyodbc, db_client, cost_oracle as CO
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
YMD='260630'
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
ro=RO().cursor()
ro.execute("SELECT ITEM_CODE FROM PR_M_ITEM"); REAL=set((r[0] or '').strip() for r in ro.fetchall())
def norm(x):
    x=(x or '').strip()
    if '+용접링' in x: x=x.replace('+용접링','')
    if '-' in x:
        b1=x.rsplit('-',1)[0]; b2=x.rsplit('-',2)[0] if x.count('-')>=2 else None
        if b1 in REAL: return b1
        if b2 and b2 in REAL: return b2
    return x
def nx_leaves(item):
    u=f"http://127.0.0.1:8010/api/bom/tree?item={quote(item)}&src=nx"
    with urllib.request.urlopen(u,timeout=60) as f: d=json.load(f)
    return set(norm(r.get('raw',r['code'])) for r in d['rows'] if not r['haskids'] and r['level']>0 and not (r.get('raw','') or '').startswith('RAC'))
def sp_leaves(item, ocur):
    o=CO.get_oracle(item,YMD,ocur)
    # struct: {lv,code,qty}. 리프 = 자식없는 code(다음행 레벨이 더 깊지 않은 것). 간단화: BOTTOM = code가 부모로 안나타남
    st=o['struct']
    parents=set()
    for i,s in enumerate(st):
        # 부모 판정: 다음행이 더 깊은 레벨이면 부모
        if i+1<len(st) and st[i+1]['lv']>s['lv']: parents.add(s['code'])
    return set(norm(s['code']) for s in st if s['code'] not in parents and not s['code'].startswith('RAC') and s['lv']>0)
# 표본: SP 계산가능 완제품
ro.execute("SELECT TOP 40 ITEM_CODE FROM PR_M_ITEM WHERE ISNULL(MAKE_TYPE,'')='1' AND ITEM_CODE NOT LIKE '%-%' AND EXISTS(SELECT 1 FROM CS_M_ITEM_BOM b WHERE b.ITEM_CODE=PR_M_ITEM.ITEM_CODE) ORDER BY NEWID()")
items=[(r[0] or '').strip() for r in ro.fetchall()]
ocn=CO._conn(); ocur=ocn.cursor()
ok=bad=err=0; bads=[]
for it in items:
    try:
        nl=nx_leaves(it); sl=sp_leaves(it,ocur)
    except Exception as e:
        err+=1; continue
    if nl==sl: ok+=1
    else:
        bad+=1
        if len(bads)<12: bads.append((it, sorted(nl-sl)[:3], sorted(sl-nl)[:3]))
ocn.close()
print(f"#1 nx.bom_line 트리 vs 레거시 SP 구조 (정규화 리프): 일치 {ok} / 불일치 {bad} / 에러 {err} = {len(items)}")
for b in bads: print(f"  ✖ {b[0]} nx-SP={b[1]} SP-nx={b[2]}")
print("DONE")
