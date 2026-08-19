# -*- coding: utf-8 -*-
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import db_client as db, cost_oracle as CO
o=CO.get_oracle('AJR75563402','260813')
print("[레거시 실원가SP struct] (lv,code,qty):")
for s in o['struct']: print(f"   lv{s['lv']} {s['code']:<22} qty={s['qty']}")
print("  MJU 포함?", [s['code'] for s in o['struct'] if s['code'].startswith('MJU')])
# 엔진 은납 SUB 전개: 은납의 자식들
from nx_cost_engine import NxCostEngine
eng=NxCostEngine()
print("\n[엔진 nx.bom_line — AJR75563402-은납 자식들]")
for c,qty,cx,f,t,lx in eng.lines('AJR75563402-은납'):
    info=eng._load_item(c)
    print(f"   {c:<20} qty={qty} cx={cx} lme_ex={lx} | make={info['make_type']} in_cust={info['in_cust']} wt={info['wt']} metal={info['metal']}")
# 은납 SUB 자체 속성
i=eng._load_item('AJR75563402-은납')
print(f"\n[은납 SUB 속성] make={i['make_type']} in_cust={i['in_cust']} cg={i['cost_gubun']} inner_prod={eng._inner_prod(i)}")
cn=db.get_connection(); cu=cn.cursor()
cu.execute("SELECT ISNULL(MAKE_TYPE,''),ISNULL(IN_CUST_CODE,'') FROM PARTNER_ERP.dbo.PR_M_ITEM WHERE ITEM_CODE='AJR75563402-은납'")
r=cu.fetchone(); print(f"[레거시 PR_M_ITEM 은납] MAKE={r[0] if r else '없음'} IN_CUST={r[1] if r else '?'}")
cu.execute("SELECT ISNULL(MAKE_TYPE,''),ISNULL(IN_CUST_CODE,'') FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM cs JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON m.ITEM_CODE=cs.MAT_CODE WHERE cs.ITEM_CODE='AJR75563402' AND cs.MAT_CODE LIKE 'AJR75563402-%' AND ISNULL(cs.TO_APPLY_YMD,'991231')>='260101'")
print("[레거시 CS: AJR75563402의 SUB자식 make/in_cust]", [tuple(x) for x in cu.fetchall()])
cn.close(); eng.close()
