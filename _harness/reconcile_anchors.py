# -*- coding: utf-8 -*-
"""내부원가 갭 규명: 현재 실원가 vs 기록앵커 → 드리프트(데이터변경) vs 엔진갭 판별."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from nx_cost_engine import NxCostEngine

# 기록앵커(memory newerp-cost-verify-harness, 260630)
ANCH = {
    "AJR75563402": {"sil": 5722.2, "nae": 6068, "nae_jae": 4015},
    "AJR75563503": {"sil": 21494, "nae_jae": 17408},
    "AJR30077403": {"nae": 28170},   # 라벨 불명확
}
eng = NxCostEngine()
ymd = "260630"
for it, a in ANCH.items():
    s = eng.silwon(it, ymd)
    n = eng.naewon(it, ymd)
    print(f"\n===== {it} =====")
    print(f"  실원가: 재료{s['jae']:.1f} 가공{s['gagong']:.1f} 일반{s['ilban']:.0f} 운반{s['unban']:.0f} 이윤{s['profit']:.0f} = {s['silwon']:.1f}  (앵커 실원가={a.get('sil','?')})")
    print(f"  내부원가: 재료{n['jae']:.1f} 가공{n['gagong']:.1f} 일반{n['ilban']:.0f} 운반{n['unban']:.0f} 이윤{n['profit']:.0f} = {n['naewon']:.1f}  (앵커 내부원가={a.get('nae','?')} 내부재료={a.get('nae_jae','?')})")
    if 'sil' in a:
        d = s['silwon'] - a['sil']
        print(f"  → 실원가 vs 앵커: Δ{d:+.1f}  {'데이터불변(엔진갭 의심)' if abs(d)<1 else '데이터드리프트(실원가도 변함)'}")
eng.close()
