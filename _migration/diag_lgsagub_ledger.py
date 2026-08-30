# -*- coding: utf-8 -*-
"""LG사급현황 · 사급부품 월별수불 — 기말금액이 마이너스인 원인 진단 (2026-08-30)

의문 (대표)
  "소요보다 입고가 대부분 많은데 왜 금액이 마이너스로 나오는가"

무엇을 재나
  엔드포인트(`recvcompare_parts_ledger`)와 **같은 방식**으로 월별 수량·금액을 뽑고,
  입고·소요의 **단가 축**을 나란히 놓는다.
    입고단가 = in_amt / in_qty      (nx.lg_sagub_actual 의 실제 금액)
    소요단가 = out_amt / out_qty    (전기간 평균단가 × 소요수량)
  둘이 다르면 수량이 남아도 금액은 마이너스가 된다.

읽기 전용. 아무것도 쓰지 않는다.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
_BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, os.path.abspath(_BE))
os.chdir(os.path.abspath(_BE))

from routers.lgsagub import recvcompare_parts_ledger          # noqa: E402
from common import _nx                                        # noqa: E402


def won(v):
    return f"{v:>16,.0f}"


def main():
    j = recvcompare_parts_ledger(from_ym="", to_ym="")
    rows = j["rows"]

    print("=" * 118)
    print("  사급부품 월별수불 — 수량은 남는데 금액은 마이너스인가")
    print("=" * 118)
    print(f"  {'월':<7}{'입고수량':>12}{'입고금액':>17}{'입고단가':>10}"
          f"{'소요수량':>12}{'소요금액':>17}{'소요단가':>10}{'기말수량':>11}{'기말금액':>17}")
    for r in rows:
        iq, ia = r["in_kg"], r["in_amt"]
        oq, oa = r["soyo_bom_kg"], r["soyo_bom_amt"]
        ip = ia / iq if iq else 0
        op = oa / oq if oq else 0
        print(f"  {r['ym']:<7}{iq:>12,.0f}{ia:>17,.0f}{ip:>10,.0f}"
              f"{oq:>12,.0f}{oa:>17,.0f}{op:>10,.0f}{r['close_bom_kg']:>11,.0f}{r['close_bom_amt']:>17,.0f}")

    ti = sum(r["in_amt"] for r in rows); to = sum(r["soyo_bom_amt"] for r in rows)
    tiq = sum(r["in_kg"] for r in rows); toq = sum(r["soyo_bom_kg"] for r in rows)
    print("\n  ── 전기간 합계 ──")
    print(f"    입고 {tiq:>12,.0f}개 {ti:>18,.0f}원   단가 {ti/tiq if tiq else 0:>10,.0f}")
    print(f"    소요 {toq:>12,.0f}개 {to:>18,.0f}원   단가 {to/toq if toq else 0:>10,.0f}")
    print(f"    수량차 {tiq-toq:>+12,.0f}개   금액차 {ti-to:>+18,.0f}원")

    # ── 왜 단가가 다른가: 입고 품목구성 vs 소요 품목구성 ──
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), SUM(ISNULL(qty,0)), SUM(ISNULL(amt,0))
                       FROM nx.lg_sagub_actual WHERE UPPER(item_name) NOT LIKE '%TUBE%'
                       GROUP BY UPPER(LTRIM(RTRIM(item_code)))""")
        osp = {r[0]: (float(r[1] or 0), float(r[2] or 0)) for r in cur.fetchall()}
        n0 = [k for k, (q, a) in osp.items() if q and a == 0]
        q0 = [k for k, (q, a) in osp.items() if q == 0]
        print("\n  ── 평균단가 산출 기반(전기간 OSP, NOT TUBE) ──")
        print(f"    품목 {len(osp)}종 · 금액0 인데 수량있음 {len(n0)}종 · 수량0 {len(q0)}종")
        if n0:
            print(f"      ★금액0 품목 예: {', '.join(n0[:8])}")
            zq = sum(osp[k][0] for k in n0)
            print(f"      이 품목들 수량합 {zq:,.0f}개 — **입고금액에는 0으로, 소요단가에도 0으로** 들어간다")
    finally:
        nx.close()


if __name__ == "__main__":
    main()
