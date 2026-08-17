# -*- coding: utf-8 -*-
"""#1 bom/tree 이관 대조검증: src=nx vs src=cs API 결과 비교.
게이트: (a)raw 리프(용접봉 RAC 제외) 다중집합 일치, (b)비리프 노드 raw 일치, (c)정규화 표시(code!=raw) 적용.
샘플 = 최근 LG 납품 제품 + BOM 보유 상위 다수."""
import sys, urllib.request, json
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
n=NX().cursor()
from urllib.parse import quote
def api(item, src):
    u=f"http://127.0.0.1:8010/api/bom/tree?item={quote(item)}&src={src}"
    with urllib.request.urlopen(u, timeout=60) as f: return json.load(f)
def leaves_raw(rows):
    # 리프 = haskids=False, RAC(용접봉) 제외, raw 기준
    return sorted((r.get('raw',r['code']) for r in rows if not r['haskids'] and not (r.get('raw',r['code']) or '').startswith('RAC') and r['level']>0))
def nonleaf_raw(rows):
    return sorted((r.get('raw',r['code']) for r in rows if r['haskids'] and r['level']>0))
# 샘플: BOM 보유 부모 400 (다양)
import os
N=int(os.environ.get('NSAMPLE','80'))
n.execute(f"SELECT TOP {N} item_code FROM nx.bom_header ORDER BY NEWID()")
items=[(r[0] or '').strip() for r in n.fetchall()]
okL=okN=norm=bad=0; badlist=[]
for it in items:
    try:
        nx=api(it,'nx'); cs=api(it,'cs')
    except Exception as e:
        bad+=1; badlist.append((it,'API '+str(e)[:40])); continue
    nlv=leaves_raw(nx['rows']); clv=leaves_raw(cs['rows'])
    # 비리프: nx는 raw로, cs는 code(raw없음)로 → cs도 code 사용
    nnl=nonleaf_raw(nx['rows']); cnl=sorted((r['code'] for r in cs['rows'] if r['haskids'] and r['level']>0))
    leaf_ok = (nlv==clv)
    nonleaf_ok = (nnl==cnl)
    # 정규화 표시: nx rows 중 raw!=code 존재?(SUB 있으면)
    hasnorm = any(r.get('raw')!=r['code'] for r in nx['rows'])
    if leaf_ok: okL+=1
    if nonleaf_ok: okN+=1
    if hasnorm: norm+=1
    if not leaf_ok:
        bad+=1
        if len(badlist)<12: badlist.append((it, f"리프 nx-cs={sorted(set(nlv)-set(clv))[:3]} cs-nx={sorted(set(clv)-set(nlv))[:3]}"))
tot=len(items)
print(f"샘플 {tot}")
print(f"  (a)리프 raw 일치: {okL}/{tot}")
print(f"  (b)비리프 raw 일치: {okN}/{tot}")
print(f"  (c)정규화 표시 적용(SUB보유): {norm}/{tot}")
print(f"  불일치/에러: {bad}")
for b in badlist[:12]: print("   ✖", b[0], b[1])
print("DONE")
