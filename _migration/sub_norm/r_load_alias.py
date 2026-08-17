# -*- coding: utf-8 -*-
# ★nx.sub_alias 적재: 자도번→품번_S{nn}·route (안전스코프·실제부모). 읽기=PARTNER_ERP, 쓰기=nx. 멱등.
import sys, re, hashlib
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def RO():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c=RO().cursor()
FR,TO='250101','260731'
c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=set(r[0].strip() for r in c.fetchall() if r[0])
c.execute("SELECT ITEM_CODE, MAKE_TYPE, IN_CUST_CODE, ITEM_DESC FROM PR_M_ITEM")
allit={(r[0] or '').strip():dict(mk=str(r[1]).strip(),cust=(r[2] or '').strip(),desc=(r[3] or '')) for r in c.fetchall()}
parents=defaultdict(set)
for tbl in ('PR_M_ITEM_BOM','CS_M_ITEM_BOM'):
    c.execute(f"SELECT ITEM_CODE, MAT_CODE FROM {tbl} WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
    for r in c.fetchall():
        p=(r[0] or '').strip(); ch=(r[1] or '').strip()
        if p and ch: parents[ch].add(p)
allvar=set(k for k in allit if '-' in k); active_child=set(ch for ch in parents if '-' in ch and ch in allvar)
memo={}
def reaches(n,seen=None):
    if n in memo: return memo[n]
    if seen is None: seen=set()
    if n in seen: return False
    seen.add(n)
    if n in shipped: memo[n]=True; return True
    res=any(reaches(p,seen) for p in parents.get(n,())); memo[n]=res; return res
def dist(q):
    c.execute(q); return set((r[0] or '').strip() for r in c.fetchall() if r[0])
stock=dist("SELECT DISTINCT ITEM_CODE FROM PU_T_STOCK_MAINT WHERE ITEM_CODE LIKE '%-%'")
try: setin=dist("SELECT DISTINCT ITEM_CODE FROM PU_T_SET_INPUT_REQ WHERE ITEM_CODE LIKE '%-%'")
except: setin=set()
scope=set(v for v in active_child if reaches(v) or v in stock or v in setin)
c.execute("SELECT ITEM_CODE, MAT_CODE FROM PR_M_ITEM_BOM WHERE ITEM_CODE LIKE '%-%' AND ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
childmap=defaultdict(set)
for r in c.fetchall():
    it=(r[0] or '').strip(); mat=(r[1] or '').strip()
    if it in scope and not mat.startswith('RAC'): childmap[it].add(mat)
def sig(v):
    s=childmap.get(v,set()); return hashlib.md5('|'.join(sorted(s)).encode()).hexdigest()[:10] if s else None
def rbase(v):
    ps=list(parents.get(v,())); return min(ps) if ps else v
by_base=defaultdict(lambda: defaultdict(list)); sig_bases=defaultdict(set)
struct=[v for v in scope if sig(v)]; leaf=[v for v in scope if not sig(v)]
for v in struct: by_base[rbase(v)][sig(v)].append(v); sig_bases[sig(v)].add(rbase(v))
local={}
for b,sm in by_base.items():
    for i,s in enumerate(sorted(sm.keys(), key=lambda s:(len(childmap[sm[s][0]]),s)),1): local[(b,s)]=f"{b}_S{i:02d}"
def canon(s): return local[(min(sig_bases[s]),s)]
TAI=re.compile(r'태국|F&T|J&I'); SANAE=re.compile(r'사내|컷팅|성형|절단|은납|도장|선행|용접|체결|저압|고압|고주파')
def route_of(v):
    d=allit[v]; desc=d['desc']; mk=d['mk']; cust=d['cust']
    if v=='4H00049A-1': return ('사내','')          # ★사용자 지정(자작)
    if cust: return ('외주',cust)
    if TAI.search(desc+v): return ('외주태국','2337')
    if SANAE.search(desc): return ('사내','')
    if mk=='1': return ('사내','')
    if mk=='3': return ('매입','')
    for p in parents.get(v,()):
        pc=allit.get(p,{}).get('cust')
        if pc: return ('외주',pc)
    return ('미상','')
rows=[]
for v in scope:
    s=sig(v)
    if s: cat='SUB_SHARED' if len(sig_bases[s])>1 else 'SUB'; cn=canon(s); nref=len(sig_bases[s])
    else: cat='LEAF' if re.match(r'^[A-Za-z0-9_\-&\.]+$',v) else 'STUB'; cn=None; nref=0
    g,ven=route_of(v)
    rows.append((v, rbase(v), cat, cn, 1 if cat=='SUB_SHARED' else 0, nref, g, ven, s, allit[v]['desc'][:180]))
print("적재 행수:", len(rows))

# nx 적재 (멱등: DROP+CREATE)
nx=NX(); w=nx.cursor()
w.execute("IF OBJECT_ID('nx.sub_alias','U') IS NOT NULL DROP TABLE nx.sub_alias")
w.execute("""CREATE TABLE nx.sub_alias(
  variant nvarchar(60) NOT NULL, real_base nvarchar(60), category nvarchar(20),
  canonical nvarchar(60) NULL, is_shared bit, n_ref_base int,
  route_gubun nvarchar(12), route_vendor nvarchar(20), sig nvarchar(16), item_desc nvarchar(200),
  load_dt datetime DEFAULT getdate())""")
w.fast_executemany=True
w.executemany("INSERT INTO nx.sub_alias(variant,real_base,category,canonical,is_shared,n_ref_base,route_gubun,route_vendor,sig,item_desc) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
nx.commit()
# 검증
w.execute("SELECT COUNT(*), COUNT(DISTINCT canonical), SUM(CASE WHEN category='SUB_SHARED' THEN 1 ELSE 0 END), SUM(CASE WHEN category='LEAF' THEN 1 ELSE 0 END), SUM(CASE WHEN route_gubun='미상' THEN 1 ELSE 0 END) FROM nx.sub_alias")
r=w.fetchone()
print(f"검증 nx.sub_alias: 총{r[0]} · 정규SUB코드{r[1]} · 공용변형{r[2]} · 리프{r[3]} · route미상{r[4]}")
w.execute("SELECT route_gubun, COUNT(*) FROM nx.sub_alias GROUP BY route_gubun ORDER BY COUNT(*) DESC")
print("  route분포:", [tuple(x) for x in w.fetchall()])
w.execute("SELECT variant, canonical, route_gubun, route_vendor FROM nx.sub_alias WHERE variant='4H00049A-1'")
print("  4H00049A-1:", w.fetchone())
nx.close(); print("DONE")
