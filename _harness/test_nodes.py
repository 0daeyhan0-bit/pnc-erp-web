# -*- coding: utf-8 -*-
"""naewon_nodes 방출 검증: 노드 재료/가공 합 = agg 총액 정합."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from nx_cost_engine import NxCostEngine
eng = NxCostEngine()
for it in ["AJR75563503", "AJR75563402"]:
    d = eng.naewon_nodes(it, "260630")
    smat = round(sum(r["mat"] for r in d["rows"]), 1)
    sgag = round(sum(r["gag"] for r in d["rows"]), 1)
    a = d["agg"]
    print(f"\n== {it} == 노드 {len(d['rows'])}개")
    print(f"  노드재료합={smat} vs agg재료={a['jae']}  {'OK' if abs(smat-a['jae'])<1 else 'X'}")
    print(f"  노드가공합={sgag} vs agg가공={a['gagong']}  {'OK' if abs(sgag-a['gagong'])<1 else 'X'}")
    print(f"  내부원가={a['naewon']} (재료{a['jae']}+가공{a['gagong']}+일반{a['ilban']}+운반{a['unban']}+이윤{a['profit']})")
    print("  샘플노드(상위8):")
    for r in d["rows"][:8]:
        print(f"    L{r['level']} {r['code']:16} q={r['qty']:<6.3f} cg={r['cost_gubun'] or '-'} 원소재단가={r['won']:<9.2f} 재료={r['mat']:<8.0f} 가공={r['gag']:<7.0f} 공정{r['nproc']} {r['name'][:16]}")
eng.close()
