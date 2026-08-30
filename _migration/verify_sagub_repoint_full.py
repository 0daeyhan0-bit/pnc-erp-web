# -*- coding: utf-8 -*-
"""sagub_whole 소스 리포인트 전수검증 (2026-08-31)

무엇을 바꿨나
  nx_cost_engine.sagub_whole 의 사급부품 집합(_sag310)을
  라이브 dbo.PR_M_ITEM 직독 → 정본 nx.item 으로 리포인트(§0 규칙1·컷오버 대비).

전수 = sagub_whole 의 **전체 정의역**(CS_M_ITEM_BOM 상위 품목 6,550종)을 돌려
       옛 소스와 새 소스의 값을 1:1 대조한다. 표본 아님.

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

from common import _get_cost_engine                       # noqa: E402

YMD = sys.argv[1] if len(sys.argv) > 1 else "260831"
eng = _get_cost_engine(); cur = eng.cur

cur.execute("SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) FROM PARTNER_ERP.dbo.PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_SGROUP))='310'")
OLD = set(r[0] for r in cur.fetchall())
cur.execute("SELECT DISTINCT LTRIM(RTRIM(item_code)) FROM PARTNER_ERP_TEST3.nx.item WHERE LTRIM(RTRIM(sgroup))='310'")
NEW = set(r[0] for r in cur.fetchall())
cur.execute("SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) FROM PARTNER_ERP.dbo.CS_M_ITEM_BOM ORDER BY 1")
ITEMS = [r[0] for r in cur.fetchall()]

print("=" * 80)
print("  sagub_whole 리포인트 전수검증  (ymd={})".format(YMD))
print("=" * 80)
print("  옛(미러) {}종 · 새(정본) {}종 · 집합차 {}".format(len(OLD), len(NEW), sorted(OLD ^ NEW)))
print("  정의역(CS_M_ITEM_BOM 상위) {:,}종 — 표본 아님, 전수\n".format(len(ITEMS)))

t0 = time.time()
diff = []; err = 0; nz = 0; to = tn = 0.0
for i, it in enumerate(ITEMS, 1):
    try:
        eng._sag310 = OLD
        a = round(float(eng.sagub_whole(it, YMD) or 0), 2)
        eng._sag310 = NEW
        b = round(float(eng.sagub_whole(it, YMD) or 0), 2)
    except Exception as e:
        err += 1
        if err <= 3:
            print("  ★예외 {} — {}".format(it, str(e)[:70]))
        continue
    to += a; tn += b
    if a:
        nz += 1
    if a != b:
        diff.append((it, a, b))
    if i % 500 == 0:
        print("    {:>6,}/{:,}  경과 {:.0f}s · 불일치 {}".format(i, len(ITEMS), time.time() - t0, len(diff)))

print("\n" + "=" * 80)
print("  검증 {:,}종 · 예외 {} · 값이 0 아닌 품목 {:,}종 · {:.0f}초".format(len(ITEMS), err, nz, time.time() - t0))
print("  합계 old = {:,.2f}".format(to))
print("  합계 new = {:,.2f}".format(tn))
print("  차이     = {:,.2f}   ·   불일치 {}건".format(tn - to, len(diff)))
for k, a, b in diff[:20]:
    print("    ★{:<18} old={:,.2f} new={:,.2f}".format(k, a, b))
print("\n  ⟹ {}".format("PASS — 전수 diff0" if (not diff and not err and nz) else "★FAIL — 확인 필요"))
