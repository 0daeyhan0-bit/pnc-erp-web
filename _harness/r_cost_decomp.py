# -*- coding: utf-8 -*-
"""AJR75563402 원가 +345 완전분해: base/LME/RAC용접봉/proc_weld 상태 vs 오라클 성분."""
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import db_client as db, cost_oracle as CO
from nx_cost_engine import NxCostEngine
IT='AJR75563402'; YMD='260813'; ymcut='20'+YMD[:4]
eng=NxCostEngine()

o=CO.get_oracle(IT,YMD)
print(f"[오라클 성분] jae={o['sil']['jae']:.1f} won={o['sil']['won']:.1f} bu={o['sil']['bu']:.1f} lme={o['sil']['lme']:.1f}")
print(f"[오라클 weld] {o['weld']}")
# 엔진 성분
base=sum(eng._value_node(c, qty, YMD, ymcut, {IT}) for c,qty,cx,f,t,lx in eng.lines(IT) if not cx)
lme=eng.lme_u(IT,YMD)
print(f"[엔진 성분] base(비cx leaf합)={base:.1f} LME_u={lme:.1f} material합={eng.material(IT,YMD):.1f}")
print(f"[엔진 split] {eng.material_split(IT,YMD)}")
print("="*80)
# 엔진 lines (top) — RAC/cx 표시
print("[엔진 AJR75563402 직계 lines]")
for c,qty,cx,f,t,lx in eng.lines(IT):
    print(f"   {c:<20} qty={qty} cx(cs_calc_except)={cx} lme_except={lx}")
print("="*80)
# proc_weld 상태 (RAC30599327)
cn=db.get_connection(); cu=cn.cursor()
print("[nx.proc_weld — AJR75563402 계열 용접봉 상태]")
try:
    cu.execute("""SELECT parent_item, weld_item, use_qty, ISNULL(cs_calc_except,0), ISNULL(lme_except,0)
       FROM nx.proc_weld WHERE LTRIM(RTRIM(parent_item)) LIKE 'AJR75563402%'""")
    for r in cu.fetchall(): print(f"   부모{r[0]:<20} {r[1]:<16} use_qty={r[2]} cs_calc_except={r[3]} lme_except={r[4]}")
except Exception as e: print("   proc_weld 조회오류:", str(e)[:60])
# 레거시 CS_M_ITEM_BOM에서 RAC30599327 cs_calc_except (은납 부모)
print("[레거시 CS_M_ITEM_BOM — 은납 SUB의 RAC30599327]")
cu.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), CAST(ISNULL(CS_CALC_EXCEPT_FLAG,0) AS int), CAST(USE_QTY AS float)
   FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM WHERE LTRIM(RTRIM(MAT_CODE))='RAC30599327' AND LTRIM(RTRIM(ITEM_CODE)) LIKE 'AJR75563402%' AND ISNULL(TO_APPLY_YMD,'991231')>='260101'""")
for r in cu.fetchall(): print(f"   부모{r[0]:<20} CS_CALC_EXCEPT={r[1]} USE_QTY={r[2]}")
cn.close(); eng.close()
