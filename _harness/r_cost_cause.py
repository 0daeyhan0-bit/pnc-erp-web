# -*- coding: utf-8 -*-
"""AJR75563402 원가 +345 원인규명: (A)except_flag 되돌림→원가 무관증명 (B)cs_calc_except stale 여부."""
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import db_client as db, cost_oracle as CO
from nx_cost_engine import NxCostEngine
IT='AJR75563402'; YMD='260813'

cn=db.get_connection(); cu=cn.cursor()
# bom_id 찾기
cu.execute("SELECT bom_id FROM nx.bom_header WHERE LTRIM(RTRIM(item_code))=?", IT)
r=cu.fetchone(); bid=r[0] if r else None
print(f"[{IT}] bom_id={bid}")

# ===== (B) cs_calc_except stale 여부: nx vs 레거시 CS =====
print("="*80); print("[B] nx.bom_line.cs_calc_except vs 레거시 CS_M_ITEM_BOM (stale 여부)")
cu.execute(f"""SELECT bl.child_item, ISNULL(bl.cs_calc_except,0) nxcs,
    (SELECT CAST(ISNULL(cs.CS_CALC_EXCEPT_FLAG,0) AS int) FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM cs
      WHERE LTRIM(RTRIM(cs.ITEM_CODE))=? AND LTRIM(RTRIM(cs.MAT_CODE))=LTRIM(RTRIM(bl.child_item)) AND ISNULL(cs.TO_APPLY_YMD,'991231')>='260101') legcs
   FROM nx.bom_line bl WHERE bl.bom_id=? ORDER BY bl.seq""", IT, bid)
stale=0
for child,nxcs,legcs in cu.fetchall():
    tag='' if (legcs is not None and int(nxcs)==int(legcs)) else '  ★STALE' if legcs is not None else '  (레거시無)'
    if '★' in tag: stale+=1
    print(f"   {child:<18} nx_cs={nxcs}  레거시_cs={legcs}{tag}")
print(f"   → cs_calc_except stale 자식수={stale}")

# ===== (A) except_flag 되돌림 → 원가 무관 증명 =====
print("="*80); print("[A] except_flag old로 되돌림 → material 동일한지(원가 무관 증명)")
eng=NxCostEngine()
m_now=eng.material(IT,YMD); print(f"   현재(new_ef) material={m_now:.1f}")
# 되돌림
cu.execute("UPDATE bl SET bl.except_flag=bk.old_ef FROM nx.bom_line bl JOIN nx.bom_line_exceptbak_260819 bk ON bk.bom_id=bl.bom_id AND bk.seq=bl.seq WHERE bl.bom_id=?", bid)
cn.commit()
eng.close(); eng=NxCostEngine()  # 캐시 회피 재생성
m_old=eng.material(IT,YMD); print(f"   되돌림(old_ef) material={m_old:.1f}")
# 재적용
cu.execute("UPDATE bl SET bl.except_flag=bk.new_ef FROM nx.bom_line bl JOIN nx.bom_line_exceptbak_260819 bk ON bk.bom_id=bl.bom_id AND bk.seq=bl.seq WHERE bl.bom_id=?", bid)
cn.commit()
eng.close(); eng=NxCostEngine()
m_re=eng.material(IT,YMD); print(f"   재적용(new_ef) material={m_re:.1f}")
print(f"   → except_flag 되돌림 원가변화={m_old-m_now:+.1f}  (0이면 원가 무관 증명)")
eng.close(); cn.close()
