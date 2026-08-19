# -*- coding: utf-8 -*-
"""AJR75563402 원가 +345 노드 트레이스: 엔진 leaf 전개 vs 레거시 오라클 struct 수량 대조."""
import sys, io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\_harness')
import cost_oracle as CO
from nx_cost_engine import NxCostEngine
IT='AJR75563402'; YMD='260813'; ymcut='20'+YMD[:4]
eng=NxCostEngine()

# 엔진 leaf 전개 (material_split 로직 복제 + leaf 금액수집)
leaves={}  # code -> [qty, val]
def walk(node, q, seen):
    info=eng._load_item(node)
    if (info['cost_gubun']!='3' or info['make_type']=='1') and eng._expandable(node, info, seen):
        for c,qty,cx,f,t,lx in eng.lines(node):
            if cx: continue
            walk(c, qty*q, seen|{node})
    else:
        v=eng._leaf_val(node, info, q, YMD, ymcut)
        e=leaves.setdefault(node,[0.0,0.0]); e[0]+=q; e[1]+=v
info0=eng._load_item(IT)
if (info0['cost_gubun']!='3' or info0['make_type']=='1') and eng._expandable(IT, info0, set()):
    for c,qty,cx,f,t,lx in eng.lines(IT):
        if cx: continue
        walk(c, qty, {IT})
else:
    walk(IT,1.0,set())

# 오라클 struct → 코드별 누적 qty (레거시 전개)
o=CO.get_oracle(IT,YMD)
ostruct={}
for s in o['struct']:
    ostruct.setdefault(s['code'],0.0)
    ostruct[s['code']]+=s['qty']
print(f"[{IT}] 엔진 재료={o['sil']['jae']:.1f}(레거시) vs nx={eng.material(IT,YMD):.1f}")
print(f"엔진 leaf수={len(leaves)} · 오라클 struct 코드수={len(ostruct)}")
print("="*95)
print(f"{'코드':<20}{'엔진qty':>10}{'엔진금액':>12}{'오라클qty(전노드)':>16}  판정")
allc=sorted(set(leaves)|set(ostruct))
over=0.0
for c in allc:
    eq=leaves.get(c,[0,0]); oq=ostruct.get(c)
    ev=eq[1]
    tag=''
    if c not in ostruct: tag='★엔진에만(과다?)'; over+=ev
    elif c not in leaves: tag='(오라클 struct에만—중간노드/제작)'
    else:
        if abs(eq[0]-oq)>0.0001: tag=f'★qty다름 Δ{eq[0]-oq:+.4f}'
    if tag:
        print(f"{c:<20}{eq[0]:>10.4f}{ev:>12.1f}{(oq if oq is not None else 0):>16.4f}  {tag}")
print("="*95)
print(f"엔진에만 있는 leaf 금액합(과다 후보)={over:.1f}")
eng.close()
