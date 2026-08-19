# -*- coding: utf-8 -*-
"""AJR75563402 LME 노드별 기여 — 엔진 +275.4 vs 레거시 −69.8. 어느 동부품이 과다인지."""
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import db_client as db
from nx_cost_engine import NxCostEngine
IT='AJR75563402'; YMD='260813'; ymcut='20'+YMD[:4]
eng=NxCostEngine()
out=eng._lme_nodes(IT,YMD,1.0)
print(f"[{IT}] 엔진 LME 합={eng.lme_total(IT,YMD):.1f} (레거시=−69.8)")
print(f"{'동부품':<20}{'LME기여':>12}{'중량':>10}{'재질':>8}{'diam':>8}{'thick':>8}{'lme_except':>10}")
tot=0
for node,amt in sorted(out.items(), key=lambda x:-abs(x[1])):
    info=eng._load_item(node)
    print(f"   {node:<18}{amt:>12.2f}{info['wt']:>10.4f}{info['metal']:>8}{info['diam']:>8.2f}{info['thick']:>8.2f}")
    tot+=amt
print(f"   합계={tot:.2f}")
# 각 동부품이 은납/명진/태국 어느 SUB 경로인지 + 레거시 CS에서 LME_EXCEPT
cn=db.get_connection(); cu=cn.cursor()
print("="*80)
print("[레거시 CS_M_ITEM_BOM에서 이 동부품들의 LME_EXCEPT_FLAG (은납 SUB 경로)]")
for node in out:
    cu.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), CAST(ISNULL(LME_EXCEPT_FLAG,0) AS int), CAST(ISNULL(CS_CALC_EXCEPT_FLAG,0) AS int)
       FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM WHERE LTRIM(RTRIM(MAT_CODE))=? AND LTRIM(RTRIM(ITEM_CODE)) LIKE 'AJR75563402%' AND ISNULL(TO_APPLY_YMD,'991231')>='260101'""", node)
    for r in cu.fetchall(): print(f"   {node:<18} 부모{r[0]:<20} LME_EXCEPT={r[1]} CS_EXCEPT={r[2]}")
cn.close(); eng.close()
