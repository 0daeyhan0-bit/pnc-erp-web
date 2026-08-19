# -*- coding: utf-8 -*-
"""except_flag 재싱크된 품목들의 원가 diff0 검증 — 레거시 SP(오라클) vs nx엔진.
   원가는 cs_calc_except 별도라 무영향이어야 함. 재료비+전체성분 대조."""
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import db_client as db, cost_oracle as CO
from nx_cost_engine import NxCostEngine

cn=db.get_connection(); cu=cn.cursor()
# 재싱크 백업에서 영향받은 품목(부모 item_code) 수집
items=set()
try:
    cu.execute("""SELECT DISTINCT LTRIM(RTRIM(h.item_code)) FROM nx.bom_line_exceptbak_260819 bk
       JOIN nx.bom_line l ON l.line_id=bk.line_id JOIN nx.bom_header h ON h.bom_id=l.bom_id""")
    items=set(r[0] for r in cu.fetchall() if r[0])
except Exception as e:
    print("백업조인 실패, 대체:", str(e)[:80])
if not items:
    try:
        cu.execute("SELECT DISTINCT LTRIM(RTRIM(item_code)) FROM nx.bom_line_exceptbak_260819")
        items=set(r[0] for r in cu.fetchall() if r[0])
    except Exception as e: print("대체도 실패:", str(e)[:80])
cn.close()
items=sorted(items)|{ } if False else sorted(set(items)|{'AJR75563402'})
print(f"영향품목 {len(items)}개 원가 대조 (ymd=260813)")
print("="*80)

eng=NxCostEngine()
YMD='260813'
okc=fail=err=0
for it in items:
    try:
        o=CO.get_oracle(it,YMD)
        mjae=eng.material(it,YMD)
        ojae=o['sil']['jae']
        d=mjae-ojae
        tag='✓diff0' if abs(d)<1 else f'✗Δ{d:+.1f}'
        if abs(d)<1: okc+=1
        else: fail+=1
        print(f"  {it:<22} nx재료={mjae:>12.1f}  레거시={ojae:>12.1f}  {tag}")
    except Exception as e:
        err+=1; print(f"  {it:<22} 오류 {str(e)[:50]}")
eng.close()
print("="*80)
print(f"재료비 diff0={okc} · 불일치={fail} · 오류={err} / 총{len(items)}")
