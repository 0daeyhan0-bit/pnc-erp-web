# -*- coding: utf-8 -*-
"""가공창고 이동계획(580) — SP vs 웹버전 전수 대조 게이트. 조회 전용(DB 무변경)

  ★목적
    nx.SP_PR_가공창고_이동계획_WEBPLAN 을 Python 으로 재구현한
    routers/move580web.py 가 **같은 값**을 내는지 확인한다.
    대표 확정(2026-09-08): "웹버전으로 해도 계획이 비슷해야 해" = diff0.

  ★비교 방법
    · 행 키 = assy_item_code + item_code + GOLE_IN_CUST_CODE + GOLE_GAGONG_PROC_CODE
      (실측 239행에서 유일. SP 최종 SELECT 에 ORDER BY 가 없어 순서가 비결정적이라
       순서가 아니라 **키로 맞춰** 비교한다)
    · 컬럼 = 기본 46 + 피벗 128(plan_qty_NN·finish_qty_NN·finish_tag_NN·color_NN)
    · 수치는 오차 0.001 이내면 같다고 본다(decimal↔float 표기차)

  사용: python _migration/move580_diff.py [from to work_code] ...
        인자 없으면 기본 3벌(P2/오늘~내일, P1/같은기간, P2/다음주)
"""
import sys, os, io, time

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _conn
import routers.move580web as W

SP = "[PARTNER_ERP_TEST3].[nx].[SP_PR_가공창고_이동계획_WEBPLAN]"
PU = "IS0001"
KEY = ("assy_item_code", "item_code", "GOLE_IN_CUST_CODE", "GOLE_GAGONG_PROC_CODE")

NUMC = set()
for n in range(32):
    ii = "%02d" % n
    NUMC |= {"plan_qty_" + ii, "finish_qty_" + ii, "finish_tag_" + ii, "color_" + ii}
NUMC |= {"plan_qty", "finish_qty", "sale_qty", "assy_stock_qty", "stock_qty",
         "pr_stock_qty", "fix_stock_qty", "jp_print_qty", "use_qty", "proc_seq",
         "mat_use_qty", "prod_rate", "item_st", "c_height",
         "KIT_WH_STOCK_QTY", "WH_STOCK_QTY", "STACKER_STOCK_QTY", "OTHER_STOCK_QTY"}


def _k(d):
    return tuple(str(d.get(c) or "").strip() for c in KEY)


def _same(c, a, b):
    if c in NUMC:
        try:
            return abs(float(a or 0) - float(b or 0)) <= 0.001
        except Exception:
            pass
    return str(a or "").strip() == str(b or "").strip()


def run_case(cur, frm, to, wc):
    print("\n" + "=" * 100)
    print(" 케이스  기간 {}~{}  작업처 {}".format(frm, to, wc))
    print("=" * 100)

    t0 = time.time()
    cur.execute("SET NOCOUNT ON; EXEC " + SP + " ?,?,?,?,?,?", frm, to, wc, PU, "%", "")
    while cur.description is None:
        if not cur.nextset():
            break
    cols = [d[0] for d in cur.description]
    sp = [dict(zip(cols, r)) for r in cur.fetchall()]
    t_sp = time.time() - t0

    t0 = time.time()
    web = W.compute(cur, frm, to, wc, PU)
    t_web = time.time() - t0

    print("   SP  {:>5,}행  {:>6.1f}s   /   웹  {:>5,}행  {:>6.1f}s".format(
        len(sp), t_sp, len(web), t_web))

    sm, wm = {}, {}
    for r in sp:
        sm.setdefault(_k(r), []).append(r)
    for r in web:
        wm.setdefault(_k(r), []).append(r)
    dup_s = sum(1 for v in sm.values() if len(v) > 1)
    dup_w = sum(1 for v in wm.values() if len(v) > 1)
    if dup_s or dup_w:
        print("   ★키 중복 — SP {} · 웹 {}".format(dup_s, dup_w))

    only_s = [k for k in sm if k not in wm]
    only_w = [k for k in wm if k not in sm]
    both = [k for k in sm if k in wm]
    print("   공통 {:,} · SP만 {:,} · 웹만 {:,}".format(len(both), len(only_s), len(only_w)))

    for k in only_s[:5]:
        print("      ★SP만: assy={} item={} cust={} proc={}".format(*k))
    for k in only_w[:5]:
        print("      ★웹만: assy={} item={} cust={} proc={}".format(*k))

    # 컬럼별 불일치 집계
    bad = {}
    samples = []
    for k in both:
        a, b = sm[k][0], wm[k][0]
        for c in cols:
            if c in ("prod_rate",):     # SP 는 이 컬럼이 중복 선택돼 값이 겹친다
                continue
            if not _same(c, a.get(c), b.get(c)):
                bad[c] = bad.get(c, 0) + 1
                if len(samples) < 12:
                    samples.append((k, c, a.get(c), b.get(c)))

    tot = len(both) * max(1, len(cols))
    nbad = sum(bad.values())
    print("\n   컬럼 {} × 공통행 {:,} = {:,} 비교   불일치 {:,}".format(
        len(cols), len(both), tot, nbad))
    if bad:
        print("\n   {:<26s} {:>8s}".format("컬럼", "불일치"))
        for c, n in sorted(bad.items(), key=lambda x: -x[1])[:15]:
            print("   {:<26s} {:>8,}".format(c, n))
        print("\n   [표본]")
        for k, c, a, b in samples:
            print("      {} {} {} {}".format(*k))
            print("         {:<24s} SP={!r:<22} 웹={!r}".format(c, a, b))

    ok = (not only_s and not only_w and nbad == 0)
    print("\n   {}".format("✅ diff0 통과" if ok else "★불일치 — 아래 내용 확인"))
    return ok


def main():
    args = sys.argv[1:]
    cn = _conn(); cur = cn.cursor()
    try:
        if len(args) >= 3:
            cases = [(args[0], args[1], args[2])]
        else:
            cur.execute("""SELECT FORMAT(GETDATE(),'yyMMdd'),
                                  FORMAT(DATEADD(day,1,GETDATE()),'yyMMdd'),
                                  FORMAT(DATEADD(day,7,GETDATE()),'yyMMdd'),
                                  FORMAT(DATEADD(day,8,GETDATE()),'yyMMdd')""")
            a, b, c, d = [str(x).strip() for x in cur.fetchone()]
            cases = [(a, b, "P2"), (a, b, "P1"), (c, d, "P2")]
        allok = True
        for frm, to, wc in cases:
            allok = run_case(cur, frm, to, wc) and allok
        print("\n" + "=" * 100)
        print(" 총평: {}".format("✅ 전 케이스 diff0" if allok else "★불일치 있음"))
        print("=" * 100)
        return 0 if allok else 1
    finally:
        cur.close(); cn.close()


if __name__ == "__main__":
    sys.exit(main())
