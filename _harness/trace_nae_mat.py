# -*- coding: utf-8 -*-
"""AJR75563503 내부재료 +850 갭 추적: 노드별 내부(nae) vs 실원가(sil) 재료 기여 대조."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from nx_cost_engine import NxCostEngine

eng = NxCostEngine()
ITEM = "AJR75563503"; ymd = "260630"; ymcut = "20" + ymd[:4]

def walk(node, q, lvl, seen):
    info = eng._load_item(node)
    exp_sil = eng._expandable(node, info, seen) if (info['cost_gubun'] != '3') else None
    exp_nae = eng._expandable_nae(node, seen) if (info['cost_gubun'] != '3') else None
    nm = ""
    try:
        eng.cur.execute("SELECT ISNULL(item_name,'') FROM nx.item WHERE item_code=?", node); r = eng.cur.fetchone(); nm = (r[0] or '')[:22]
    except Exception:
        pass
    lv_sil = 0.0 if exp_sil else eng._leaf_val(node, info, q, ymd, ymcut)
    lv_nae = 0.0 if exp_nae else eng._leaf_val_nae(node, info, q, ymd, ymcut)
    mark = ""
    if bool(exp_sil) != bool(exp_nae): mark += " ★전개차이"
    if abs(lv_sil - lv_nae) > 1: mark += f" ★leaf차이Δ{lv_nae-lv_sil:+.0f}"
    print(f"{'  '*lvl}L{lvl} {node:16} q={q:<7.3f} cg={info['cost_gubun'] or '-'} mk={info['make_type'] or '-'} inner={int(eng._inner_prod(info))} "
          f"sil={'전개' if exp_sil else f'{lv_sil:.0f}':>7} nae={'전개' if exp_nae else f'{lv_nae:.0f}':>7} {nm}{mark}")
    # 재귀: 내부는 exp_nae 기준(전공정 전개)
    if exp_nae:
        for c, qty, cx, f, t, lx in eng.lines(node):
            if cx: continue
            walk(c, q * qty, lvl + 1, seen | {node})

walk(ITEM, 1.0, 0, set())
print(f"\n내부재료 총={eng.material_nae(ITEM, ymd):.1f}  실원가재료 총={eng.material(ITEM, ymd):.1f}  앵커: 내부17408 / 실21227")
eng.close()
