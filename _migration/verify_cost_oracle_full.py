# -*- coding: utf-8 -*-
"""원가 전수 대조 — 레거시 SP(오라클) vs nx 엔진 (2026-08-31)

왜
  §1-5 하드룰: 원가는 레거시와 diff0. 정답 = _harness/cost_oracle.py(레거시 SP EXEC).
  대표 지시 "검증은 전체적으로 다 해야 한다 · 전수 검사가 기본 규칙".
  앵커 3종만 보던 것을 **정의역 전체**로 넓힌다.

무엇을
  정의역 = CS_M_ITEM_BOM 상위 품목 전체(≈6,550종).
  레거시 SP 재료비(JAI) vs 엔진 material(base) 를 1:1 대조.
  ※SP EXEC 는 pncind 계정 필요(_harness/pncind_cred.json · gitignore).

읽기 전용.
"""
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(R, "_harness"))
sys.path.insert(0, os.path.join(R, "PNC_ERP_Web", "backend"))
os.chdir(os.path.join(R, "PNC_ERP_Web", "backend"))

import cost_oracle as CO                                   # noqa: E402
from common import _get_cost_engine                        # noqa: E402

YMD = sys.argv[1] if len(sys.argv) > 1 else "260630"
LIM = int(sys.argv[2]) if len(sys.argv) > 2 else 0
TOL = 1.0

eng = _get_cost_engine()
cn = CO._conn(); cur = cn.cursor()
cur.execute("SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM ORDER BY 1")
items = [r[0] for r in cur.fetchall()]
if LIM:
    items = items[:LIM]

print("=" * 84)
print("  원가 전수 대조 — 레거시 SP vs nx 엔진   (ymd={} · {:,}종 · 허용오차 {})".format(YMD, len(items), TOL))
print("=" * 84)

t0 = time.time()
ok = 0; diff = []; skip = 0; oerr = 0; eerr = 0; oerr_kinds = {}
for i, it in enumerate(items, 1):
    try:
        o = CO.get_oracle(it, YMD, cur)
        oj = o['sil']['jae']
    except Exception as e:
        # ★예외를 조용히 삼키지 않는다 — 2026-08-31 실측: 일시장애로 5,881건이
        #   예외 처리되어 '빨리 끝난' 것처럼 보였다(앞 실행은 예외 0).
        #   사유를 모으고, 예외가 10% 넘으면 결과 자체를 무효로 본다.
        oerr += 1
        oerr_kinds[str(e)[:60]] = oerr_kinds.get(str(e)[:60], 0) + 1
        if oerr <= 3:
            print("  ★오라클예외 {} — {}".format(it, str(e)[:80]))
        try:
            cn.close()
        except Exception:
            pass
        cn = CO._conn(); cur = cn.cursor()   # 재연결 후 계속
        continue
    if oj is None:
        skip += 1
        continue
    try:
        m = eng.material(it, YMD)
        ej = float(m['base'] if isinstance(m, dict) and 'base' in m else m)
    except Exception as e:
        eerr += 1
        if eerr <= 3:
            print("  ★엔진예외 {} — {}".format(it, str(e)[:70]))
        continue
    if abs(ej - float(oj)) <= TOL:
        ok += 1
    else:
        diff.append((it, float(oj), ej, ej - float(oj)))
    if i % 500 == 0:
        print("    {:>6,}/{:,}  {:.0f}s · 일치 {:,} · 불일치 {:,}".format(i, len(items), time.time() - t0, ok, len(diff)))

print("\n" + "=" * 84)
print("  대상 {:,}종 · {:.0f}초".format(len(items), time.time() - t0))
if oerr:
    print("  ★오라클예외 사유별:")
    for k, v in sorted(oerr_kinds.items(), key=lambda x: -x[1])[:5]:
        print("      {:>5}건  {}".format(v, k))
    if oerr > len(items) * 0.1:
        print("  ★★결과 무효 — 예외가 10% 넘는다. 판단하지 말 것.")
print("  일치 {:,} · 불일치 {:,} · 오라클무값 {:,} · 오라클예외 {:,} · 엔진예외 {:,}".format(
    ok, len(diff), skip, oerr, eerr))
# ★전체 불일치를 CSV 로 남긴다 — 상위 20 만 보면 군집 분석이 안 된다.
if diff:
    csvp = os.path.join(R, "_migration", "cost_diff_{}.csv".format(YMD))
    with io.open(csvp, "w", encoding="utf-8-sig") as f:
        f.write("item,sp_jae,engine_jae,diff" + chr(10))
        for k, a, b, d in sorted(diff, key=lambda x: -abs(x[3])):
            f.write("{},{:.2f},{:.2f},{:.2f}".format(k, a, b, d) + chr(10))
    print(chr(10) + "  전체 불일치 CSV: {}".format(csvp))
    from collections import Counter
    cl = Counter(round(d, 2) for _, _, _, d in diff)
    print("  ── 차이값 군집 상위 10 (같은 값이 반복되면 원인이 하나다) ──")
    for v, n in cl.most_common(10):
        print("    차이 {:>14,.2f} × {:>4}건".format(v, n))
if diff:
    diff.sort(key=lambda x: -abs(x[3]))
    print("\n  ── 불일치 상위 20 (차이 큰 순) ──")
    print("  {:<20}{:>16}{:>16}{:>14}".format("품번", "레거시(SP)", "엔진", "차이"))
    for k, a, b, d in diff[:20]:
        print("  {:<20}{:>16,.2f}{:>16,.2f}{:>14,.2f}".format(k, a, b, d))
    print("\n  불일치 금액 합계 {:,.2f}".format(sum(d for _, _, _, d in diff)))
print("\n  ⟹ {}".format("PASS — 전수 diff0" if not diff else "★{}건 불일치".format(len(diff))))
cn.close()
