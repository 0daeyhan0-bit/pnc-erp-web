# -*- coding: utf-8 -*-
"""마감 거래구분(판매/반품/수출·매입/수입) 검증.
  · 매출마감 전체 총액 == 자재불출집계표(dispatch)  · 매입마감 전체 == 자재입고집계표(receipt)
  · 구분별 합(판매+반품+수출 / 매입+수입) == 전체
  · 상세(detail) 당월 총액 == 목록 전체 총액(구분 포함) — 표본 벤더
무쓰기. 사용: python _schema/magam_gubun_testbed.py
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
_H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_H, "..", "PNC_ERP_Web", "backend"))
sys.path.insert(0, os.path.join(_H, "..", "..", "New_ERP"))
import live_api
from routers import salemagam, purmagam

def tot(rows, k): return round(sum(float(r.get(k) or 0) for r in rows), 0)

def run():
    P = F = 0
    for y in ["2607", "2608", "2609"]:
        # 매출
        dsp = tot(live_api.dispatch(gijun="close", ym=y)["rows"], "kamt")
        allt = tot(salemagam.salemagam_list(ym=y, gubun="")["rows"], "amt")
        s = tot(salemagam.salemagam_list(ym=y, gubun="판매")["rows"], "amt")
        r = tot(salemagam.salemagam_list(ym=y, gubun="반품")["rows"], "amt")
        q = tot(salemagam.salemagam_list(ym=y, gubun="수출")["rows"], "amt")
        ok1 = abs(dsp - allt) < 2 and abs((s + r + q) - allt) < 2
        print(f"[매출 {y}] 불출집계표={dsp:,.0f} 마감전체={allt:,.0f} (판매{s:,.0f}/반품{r:,.0f}/수출{q:,.0f}) {'PASS' if ok1 else 'FAIL'}")
        P += ok1; F += (not ok1)
        # 매입
        rc = tot(live_api.receipt(gijun="close", ym=y)["rows"], "kamt")
        pallt = tot(purmagam.purmagam_list(ym=y, gubun="")["rows"], "amt")
        pp = tot(purmagam.purmagam_list(ym=y, gubun="매입")["rows"], "amt")
        pi = tot(purmagam.purmagam_list(ym=y, gubun="수입")["rows"], "amt")
        ok2 = abs(rc - pallt) < 2 and abs((pp + pi) - pallt) < 2
        print(f"[매입 {y}] 입고집계표={rc:,.0f} 마감전체={pallt:,.0f} (매입{pp:,.0f}/수입{pi:,.0f}) {'PASS' if ok2 else 'FAIL'}")
        P += ok2; F += (not ok2)
    # 상세 정합(수출 벤더 표본)
    lst = salemagam.salemagam_list(ym="2608", gubun="")["rows"]
    exp = [x for x in lst if x.get("amt_export", 0) > 0]
    if exp:
        cc = exp[0]["cc"]; d = salemagam.salemagam_detail(ym="2608", cc=cc)
        dtot = round(sum(b["amt"] for it in d["items"] for b in it["byday"] if not b["carry"]), 0)
        ok3 = abs(dtot - exp[0]["amt"]) < 2
        print(f"[상세 매출 2608 cc={cc}] 목록전체={exp[0]['amt']:,.0f} 상세당월={dtot:,.0f} {'PASS' if ok3 else 'FAIL'}")
        P += ok3; F += (not ok3)
    print(f"\n=== PASS {P} · FAIL {F} ===")
    return 0 if F == 0 else 1

if __name__ == "__main__":
    sys.exit(run())
