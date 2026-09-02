# -*- coding: utf-8 -*-
"""마감 이월(override) 정합 테스트베드 — 집계표 ↔ 마감(목록) 동일반영 검증.

증명: 이월(nx.magam_carry_ovr)을 토글하면 **집계표와 마감 목록이 각 월에서 똑같은 금액만큼 이동**한다.
  · 매입: 자재입고집계표(live_api.receipt) ↔ 자재매입마감(purmagam.purmagam_list)
  · 매출: 자재불출집계표(live_api.dispatch tag5) ↔ 자재매출마감(salemagam.salemagam_list)
  · 출발월(당월)에서 빠지고 도착월(차월)에서 붙는 금액이 양쪽에서 동일해야 PASS.

배경(2026-09-03): 마감 목록이 `_sale_win_ovr`(pull-in 미포함)을 써서 **도착월에서 집계표와 갈렸다**.
  → 마감 목록/라인을 집계표와 동일한 공용창 `common._win_ovr`로 통일해 해소. 본 테스트가 그 회귀 가드.

★가역: 임시 override(ins_user='verify')를 넣고 반드시 삭제. 실행 후 nx 오염 0.
사용: python _schema/magam_carry_consistency_testbed.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "PNC_ERP_Web", "backend"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "New_ERP"))
import live_api
from routers import purmagam, salemagam
from common import _carry_ovr_set
import db_client


def vtot(rows, cc, k):
    return round(sum(float(r.get(k) or 0) for r in rows if str(r["cc"]) == cc), 0)


def _cleanup():
    cn = db_client.get_connection(); c = cn.cursor()
    c.execute("DELETE FROM PARTNER_ERP_TEST3.nx.magam_carry_ovr WHERE ins_user='verify'")
    cn.commit(); c.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.magam_carry_ovr WHERE ins_user='verify'")
    n = c.fetchone()[0]; cn.close(); return n


def toggle(kind, Y, NY, pick_sql, measure):
    cn = db_client.get_connection(); cur = cn.cursor()
    cur.execute(pick_sql); r = cur.fetchone(); cn.close()
    if not r:
        print(f"[{kind}] 대상 품목 없음 — SKIP"); return None
    cc, mat, ymd, amt = str(r[0]), str(r[1]), str(r[2]), float(r[3])
    print(f"\n[{kind}] cc={cc} mat={mat} ymd={ymd} 금액={amt:,.0f}  프레임 {Y}->{NY}")
    base = measure(cc, Y, NY)
    ok = False
    try:
        _carry_ovr_set(kind, Y, cc, mat, ymd, carry=True, usr="verify")
        a = measure(cc, Y, NY)
        d = [round(x - b, 0) for b, x in zip(base, a)]
        s1 = abs(d[0] - d[1]) < 2; s2 = abs(d[2] - d[3]) < 2; ok = s1 and s2
        print(f"  Δ{Y}: 집계표={d[0]:,.0f} 마감={d[1]:,.0f} {'동일' if s1 else '★불일치'} | "
              f"Δ{NY}: 집계표={d[2]:,.0f} 마감={d[3]:,.0f} {'동일' if s2 else '★불일치'}")
        print(f"  >>> {kind} 이월 집계표·마감 동일반영: {'PASS' if ok else 'FAIL'}")
    finally:
        _cleanup()
        rest = measure(cc, Y, NY)
        print(f"  원복: {'OK' if abs(rest[0]-base[0])<2 and abs(rest[1]-base[1])<2 else '★실패'}")
    return ok


def pur_measure(cc, Y, NY):
    return (vtot(live_api.receipt(gijun="close", ym=Y)["rows"], cc, "kamt"),
            vtot(purmagam.purmagam_list(ym=Y)["rows"], cc, "amt"),
            vtot(live_api.receipt(gijun="close", ym=NY)["rows"], cc, "kamt"),
            vtot(purmagam.purmagam_list(ym=NY)["rows"], cc, "amt"))


def sale_measure(cc, Y, NY):
    return (vtot(live_api.dispatch(gijun="close", ym=Y)["rows"], cc, "kamt"),
            vtot(salemagam.salemagam_list(ym=Y)["rows"], cc, "amt"),
            vtot(live_api.dispatch(gijun="close", ym=NY)["rows"], cc, "kamt"),
            vtot(salemagam.salemagam_list(ym=NY)["rows"], cc, "amt"))


def main():
    print("=== 마감 이월 정합 검증 (집계표 ↔ 마감) ===")
    T = "PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT"
    results = []
    results.append(toggle("PUR", "2609", "2610",
        f"SELECT TOP 1 CUST_CODE,MAT_CODE,MAINT_YMD,MAINT_AMT FROM {T} "
        f"WHERE MAINT_TAG IN ('9','S','C','G','H') AND MAINT_YMD>='260901' AND MAINT_YMD<='260915' AND MAINT_AMT>0 ORDER BY MAINT_AMT",
        pur_measure))
    results.append(toggle("SALE", "2608", "2609",
        f"SELECT TOP 1 CUST_CODE,MAT_CODE,MAINT_YMD,MAINT_AMT FROM {T} "
        f"WHERE MAINT_TAG='5' AND MAINT_YMD>='260801' AND MAINT_YMD<='260815' AND MAINT_AMT>0 ORDER BY MAINT_AMT",
        sale_measure))
    passed = sum(1 for x in results if x)
    skipped = sum(1 for x in results if x is None)
    failed = sum(1 for x in results if x is False)
    print(f"\n=== 결과: PASS {passed} · FAIL {failed} · SKIP {skipped} ===")
    print("verify 잔여:", _cleanup())
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
