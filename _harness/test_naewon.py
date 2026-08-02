# -*- coding: utf-8 -*-
"""내부용(내부원가) 엔진 자체검증: 성분합계 정합 + 내부 vs 실원가 관계.
   ★SP-diff0 사인오프는 EXECUTE 권한 복구 후 cost_oracle.py로 별도."""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from nx_cost_engine import NxCostEngine

eng = NxCostEngine()
items = ["AJR75563402", "AJR75563503", "AJR30077403", "AJR30008101", "AJR75462802", "AJR77224501"]
ymd = "260630"
hdr = f"{'품번':16} {'내부재료':>9} {'내부가공':>9} {'일반':>7} {'운반':>6} {'이윤':>7} {'내부원가':>10} | {'실가공':>8} {'가공관계':10} | 합계정합"
print(hdr)
print("-" * len(hdr))
for it in items:
    try:
        n = eng.naewon(it, ymd)
        s = eng.silwon(it, ymd)
        calc = round(n["jae"] + n["gagong"] + n["ilban"] + n["unban"] + n["profit"], 2)
        okc = "OK" if abs(calc - n["naewon"]) < 0.5 else f"X({calc})"
        rel = "내부>=실 OK" if n["gagong"] >= s["gagong"] - 0.5 else f"X 내부<{s['gagong']:.0f}"
        print(f"{it:16} {n['jae']:>9.0f} {n['gagong']:>9.0f} {n['ilban']:>7.0f} {n['unban']:>6.0f} {n['profit']:>7.0f} {n['naewon']:>10.0f} | {s['gagong']:>8.0f} {rel:10} | {okc}")
    except Exception as e:
        print(f"{it:16} 오류 {str(e)[:70]}")
eng.close()
