# -*- coding: utf-8 -*-
# 협력사 발주 대사: SUB 발주대상 협력사별 수량 = 자도번(레거시) vs 품번_S{nn}(정규화) 보존 (SELECT only)
import sys
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
from collections import defaultdict
def RO(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD};ApplicationIntent=ReadOnly')
def NX(): return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')
c=RO().cursor(); n=NX().cursor()
# sub_alias: variant → (canonical, route_vendor)
n.execute("SELECT variant, canonical, route_vendor, route_gubun FROM nx.sub_alias")
ALIAS={r[0]:dict(canon=r[1],ven=(r[2] or ''),g=r[3]) for r in n.fetchall()}
# 레거시 자도번 IN_CUST
c.execute("SELECT ITEM_CODE, IN_CUST_CODE, MAKE_TYPE FROM PR_M_ITEM WHERE ITEM_CODE LIKE '%-%'")
LEG={(r[0] or '').strip():((r[1] or '').strip(), str(r[2]).strip()) for r in c.fetchall()}

# plan_part_mat 의 SUB 발주대상(upper 자도번) 별 소요수량
n.execute("SELECT upper_item_code, SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat WHERE upper_item_code LIKE '%-%' GROUP BY upper_item_code")
subs=[((r[0] or '').strip(), r[1] or 0) for r in n.fetchall()]
print(f"SUB 발주대상: {len(subs)}")

leg_by_v=defaultdict(float); norm_by_v=defaultdict(float); noven=[]
for sub,qty in subs:
    a=ALIAS.get(sub)
    # 정규화 협력사 = sub_alias route_vendor (외주면)
    nv = a['ven'] if (a and a['g'] and a['g'].startswith('외주') and a['ven']) else ''
    # 레거시 협력사 = 자도번 IN_CUST (외주만)
    lv = LEG.get(sub,('',''))[0] if LEG.get(sub,('','' ))[1]=='2' else ''
    if nv: norm_by_v[nv]+=qty
    if lv: leg_by_v[lv]+=qty
    if (a and a['g'] and a['g'].startswith('외주')) and not nv and not lv:
        noven.append(sub)

# 협력사별 비교
vends=set(leg_by_v)|set(norm_by_v)
print(f"\n{'협력사':<8}{'레거시발주':>12}{'정규화발주':>12}  일치")
diff=0
for v in sorted(vends, key=lambda x:-max(leg_by_v.get(x,0),norm_by_v.get(x,0)))[:15]:
    l=leg_by_v.get(v,0); nn=norm_by_v.get(v,0)
    ok = abs(l-nn)<1e-6
    if not ok: diff+=1
    print(f"  {v:<8}{l:>12.0f}{nn:>12.0f}  {'✔' if ok else '✖'}")
print(f"\n협력사 수: 레거시 {len(leg_by_v)} · 정규화 {len(norm_by_v)} · 불일치 {diff}")
print(f"외주인데 협력사 미상(양쪽무): {len(noven)} 예:{noven[:5]}")
# 총 외주발주 수량
print(f"총 외주발주: 레거시 {sum(leg_by_v.values()):.0f} · 정규화 {sum(norm_by_v.values()):.0f}")
print("DONE")
