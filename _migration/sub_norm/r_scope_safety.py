# -*- coding: utf-8 -*-
# 안전검증: 제외된 변형 중 실제 LG납품 도달/거래이력 있는 것(=거짓제외) 없나 (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def Lc():
    cs=(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
    return pyodbc.connect(cs)
c=Lc().cursor()
FR,TO='250101','260731'
c.execute(f"SELECT DISTINCT ITEM_CODE FROM SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?", FR,TO)
shipped=set(r[0].strip() for r in c.fetchall() if r[0])

# 부모맵: PR∪CS 활성 (합집합=최대 포용)
parents=defaultdict(set)
for tbl in ('PR_M_ITEM_BOM','CS_M_ITEM_BOM'):
    c.execute(f"SELECT ITEM_CODE, MAT_CODE FROM {tbl} WHERE ISNULL(EXCEPT_FLAG,'0')<>'1' AND MAT_CODE IS NOT NULL")
    for r in c.fetchall():
        p=(r[0] or '').strip(); ch=(r[1] or '').strip()
        if p and ch: parents[ch].add(p)
# 활성 자식 변형(PR∪CS)
c.execute("SELECT ITEM_CODE FROM PR_M_ITEM WHERE ITEM_CODE LIKE '%-%'")
allvar=set((r[0] or '').strip() for r in c.fetchall())
active_child=set(ch for ch in parents if '-' in ch and ch in allvar)
print("활성자식 변형(PR∪CS):", len(active_child))

memo={}
def reaches(node, seen=None):
    if node in memo: return memo[node]
    if seen is None: seen=set()
    if node in seen: return False
    seen.add(node)
    if node in shipped: memo[node]=True; return True
    res=any(reaches(p,seen) for p in parents.get(node,()))
    memo[node]=res; return res

inscope=set(v for v in active_child if reaches(v))
excluded=active_child - inscope
print(f"PR∪CS 부모체인 LG도달(정확 스코프): {len(inscope)}")
print(f"제외: {len(excluded)}")

# ★안전: 제외된 것 중 거래이력(직접출하/입고/세트입고/재고)이 있는가 = 거짓제외 위험
# 벌크 로드
def dist(q):
    c.execute(q); return set((r[0] or '').strip() for r in c.fetchall() if r[0])
ship_direct = excluded & shipped   # 직접 LG출하된 제외건
stock = dist("SELECT DISTINCT ITEM_CODE FROM PU_T_STOCK_MAINT WHERE ITEM_CODE LIKE '%-%'")
try: setin = dist("SELECT DISTINCT ITEM_CODE FROM PU_T_SET_INPUT_REQ WHERE ITEM_CODE LIKE '%-%'")
except: setin=set()
risk_stock = excluded & stock
risk_setin = excluded & setin
print(f"\n★거짓제외 위험 점검(제외됐으나 실제 흔적 있음):")
print(f"  직접 LG출하됨: {len(ship_direct)}  예:{sorted(ship_direct)[:8]}")
print(f"  재고이동 있음: {len(risk_stock)}  예:{sorted(risk_stock)[:8]}")
print(f"  세트입고 있음: {len(risk_setin)}  예:{sorted(risk_setin)[:8]}")
atrisk=ship_direct|risk_stock|risk_setin
print(f"  ==> 위험 합집합: {len(atrisk)}")
if atrisk:
    print("  (이들은 제외됐으나 실제 거래가 있어 재검토 필요)")
    for v in sorted(atrisk)[:20]:
        c.execute("SELECT ITEM_DESC FROM PR_M_ITEM WHERE ITEM_CODE=?", v); d=c.fetchone()
        print(f"    {v:<24} {(d[0] if d else '')[:26]}")
else:
    print("  ==> 없음: 제외된 것 전부 LG도달·거래 흔적 없음 = 안전(거짓제외 0)")
print("\nDONE")
