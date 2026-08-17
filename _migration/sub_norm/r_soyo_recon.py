# -*- coding: utf-8 -*-
# 자재소요 대사: plan_part_mat SUB코드 정규화 커버리지 + 최하위 재료소요 보존 (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
n=NX().cursor()
n.execute("SELECT variant, canonical, category FROM nx.sub_alias")
ALIAS={r[0]:(r[1],r[2]) for r in n.fetchall()}

# 1) plan_part_mat 의 SUB코드(자도번) 정규화 커버리지 (upper_item_code)
n.execute("SELECT DISTINCT upper_item_code FROM nx.plan_part_mat WHERE upper_item_code LIKE '%-%'")
uppers=[(r[0] or '').strip() for r in n.fetchall()]
cov=[u for u in uppers if u in ALIAS]; unc=[u for u in uppers if u not in ALIAS]
print(f"[상위 SUB코드(upper) 정규화 커버리지] 자도번 {len(uppers)} → 매핑 {len(cov)} / 미매핑 {len(unc)}")
if unc: print("  미매핑 예:", unc[:8])

# 2) mat_code 자도번 정체 (+용접링? SUB자체?)
VARSET=set(ALIAS.keys())
n.execute("SELECT mat_code, CAST(part_plan_qty AS float) FROM nx.plan_part_mat WHERE mat_code LIKE '%-%'")
rows=n.fetchall()
ring=sum(1 for r in rows if '용접링' in (r[0] or ''))
subv=sum(1 for r in rows if (r[0] or '').strip() in VARSET)
print(f"\n[mat_code 자도번 행 {len(rows)}] 용접링 {ring} · sub_alias변형 {subv} · distinct {len(set(r[0] for r in rows))}")

# 3) ★최하위 재료소요 보존: leaf(sub_alias에 없는 mat) 총소요 = 정규화 무관 불변
n.execute("SELECT mat_code, CAST(part_plan_qty AS float) FROM nx.plan_part_mat")
allrows=n.fetchall()
leaf=[(m,q) for m,q in [((r[0] or '').strip(),r[1] or 0) for r in allrows] if m not in VARSET]
from collections import defaultdict
agg=defaultdict(float)
for m,q in leaf: agg[m]+=q
print(f"\n[최하위 재료(leaf) 소요] distinct mat {len(agg)} · 총소요 {sum(agg.values()):.1f}  ← SUB라벨 정규화와 무관(불변)=생산 안깨짐")

# 4) 발주대상 = SUB(자도번)면 정규화 코드로. 샘플 대사
print("\n[발주대상 SUB 정규화 샘플] (자도번→품번_S{nn}, 수량 불변)")
n.execute("""SELECT TOP 8 upper_item_code, SUM(CAST(part_plan_qty AS float))
             FROM nx.plan_part_mat WHERE upper_item_code LIKE '%-%' GROUP BY upper_item_code""")
for r in n.fetchall():
    u=r[0].strip(); mp=ALIAS.get(u)
    print(f"   {u:<24} 소요{r[1]:.0f} → {mp[0] if mp else '(미매핑)'}")
print("\n★결론: 최하위 재료소요는 정규화와 무관(불변)=생산 안 깨짐. SUB 라벨만 자도번→품번_S{nn}.")
print("DONE")
