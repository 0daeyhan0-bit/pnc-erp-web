# -*- coding: utf-8 -*-
# 정확 스코프: 변형의 실제 BOM 부모체인이 LG납품(출하)제품에 도달하는가 (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict, deque
def Lc():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
    return pyodbc.connect(cs)
c=Lc().cursor()
FR,TO='250101','260731'
c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=set(r[0].strip() for r in c.fetchall() if r[0])
print("LG납품(출하) 제품:", len(shipped))

# 활성 BOM 엣지 (부모 ITEM_CODE -> 자식 MAT_CODE), PR 생산 실사용
c.execute("SELECT ITEM_CODE, MAT_CODE FROM PR_M_ITEM_BOM WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
parents=defaultdict(set)   # child -> {parent}
for r in c.fetchall():
    p=(r[0] or '').strip(); ch=(r[1] or '').strip()
    if p and ch: parents[ch].add(p)

# 접미사 변형 = '-' 포함 + PR_M_ITEM 등록
c.execute("SELECT ITEM_CODE FROM PR_M_ITEM WHERE ITEM_CODE LIKE '%-%'")
allvar=set((r[0] or '').strip() for r in c.fetchall())
# 활성 BOM 자식인 변형만(=사용중 BOM)
active_child=set(ch for ch in parents if '-' in ch and ch in allvar)
print("활성 BOM 자식인 변형:", len(active_child))

# 부모체인 top-도달: 변형에서 위로 올라가 shipped 제품에 닿나
memo={}
def reaches_shipped(node, seen=None):
    if node in memo: return memo[node]
    if seen is None: seen=set()
    if node in seen: return False
    seen.add(node)
    if node in shipped:
        memo[node]=True; return True
    res=False
    for p in parents.get(node,()):
        if reaches_shipped(p, seen): res=True; break
    memo[node]=res; return res

inscope=[v for v in active_child if reaches_shipped(v)]
outscope=[v for v in active_child if v not in set(inscope)]
print(f"\n★실제 BOM부모체인이 LG납품제품 도달(정확 스코프): {len(inscope)}")
print(f"  도달못함(접두사만 맞고 실제 안 쓰임) 제외: {len(outscope)}")
print(f"  예(제외): {sorted(outscope)[:12]}")

# 이전 접두사 스코프(1505)와 비교: 접두사 base가 shipped인 변형
def prefix_base(code):
    for b in sorted(shipped,key=len,reverse=True):
        if code!=b and code.startswith(b+'-'): return b
    return None
prefix_scope=set(v for v in active_child if prefix_base(v))
print(f"\n[비교] 접두사기준 활성자식: {len(prefix_scope)}  vs  실제부모체인기준: {len(inscope)}")
diff=prefix_scope - set(inscope)
print(f"  접두사엔 있으나 실제 미도달(버그로 들어갔던): {len(diff)}  예:{sorted(diff)[:10]}")
print("DONE")
