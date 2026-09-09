# -*- coding: utf-8 -*-
"""★스키마 무접두 참조 교정 — TEST3.dbo(낡은 사본) → nx (2026-09-09)

★어떻게 찾았나 — 대표 지시로 soyo.py 를 검수하다 영업예상매출현황이
   **9월 조회에서 0행**이 나오는 것을 발견했다. 원인:

     soyo.py:325   FROM sa_t_plan_item_dtl        ← 스키마 무접두
     _conn()       DB=PARTNER_ERP_TEST3 · 기본스키마 dbo
     ⟹ nx 가 아니라 **TEST3.dbo** 를 읽는다.

     SA_T_PLAN_ITEM_DTL  TEST3.dbo 331,897행 (231016~**260819**)  ★8/19 에서 멈춤
                         TEST3.nx  346,670행 (231016~261009)
                         라이브     346,390행 (231016~261009)

   즉 **영업예상매출현황이 8/19 이후를 못 보고 있었다.** 달력 함수에서 겪은 것과 같은
   함정이다(§6-6 — f_get_relative_work_day_doosung 이 TEST3.dbo 달력을 읽어 4일 어긋남).

★전수 검출 결과 — dbo·nx 양쪽에 있는 96종 중 **무접두로 쓰는 곳 18곳 · 9종**
   전부 dbo 사본이 nx 보다 뒤처져 있다.

     PR_T_PLAN_INPUT           4곳  dbo 14,706  < nx 15,310
     SA_T_PLAN_ITEM_DTL        3곳  dbo 331,897 < nx 346,670   ★영업예상매출
     PR_M_ITEM                 2곳  dbo 24,093  < nx 24,154
     PR_M_ITEM_COST            2곳  dbo 125,349 < nx 131,461
     SA_T_SALE_DTL             2곳  dbo 298,285 < nx 310,435
     PR_M_ITEM_BOM             1곳  dbo 42,361  < nx 42,550
     PR_T_INDI_WELD_SHEET_DTL  1곳  dbo 115,076 < nx 120,386
     PR_T_PROD_DTL_STICKER     1곳  dbo 112,157 < nx 126,811   ★공정별 바코드실적
     PU_T_SET_INPUT_REQ_DTL    1곳  dbo 303,901 < nx 314,956
     (SA_T_ITEM_MOVE 은 양쪽 0행 — 무해하나 함께 접두어를 붙인다)

★무엇으로 바꾸나 — **클린 호환뷰가 있으면 그것, 없으면 nx.**
   SA_T_PLAN_ITEM_DTL → nx.sale_plan_item   (오늘 과거분 이관 완료, 라이브와 전수 일치)
   PR_T_PLAN_INPUT    → nx.prod_plan_input  (웹 정본)
   나머지             → nx.<이름>            (미러이나 dbo 사본보다 최신)

사용: python _migration\\fix_noprefix_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
BK = r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema\bk_noprefix_{}".format(STAMP)

# 무접두 이름 → 바꿀 대상
MAP = {
    "sa_t_plan_item_dtl": "nx.sale_plan_item",     # 웹 정본(과거분 이관 완료)
    "pr_t_plan_input":    "nx.prod_plan_input",    # 웹 정본
    "sa_t_sale_dtl":      "nx.SA_T_SALE_DTL",
    "pr_m_item_cost":     "nx.PR_M_ITEM_COST",
    "pr_m_item":          "nx.PR_M_ITEM",
    "pr_m_item_bom":      "nx.PR_M_ITEM_BOM",
    "pr_t_indi_weld_sheet_dtl": "nx.PR_T_INDI_WELD_SHEET_DTL",
    "pr_t_prod_dtl_sticker":    "nx.PR_T_PROD_DTL_STICKER",
    "pu_t_set_input_req_dtl":   "nx.PU_T_SET_INPUT_REQ_DTL",
    "sa_t_item_move":     "nx.SA_T_ITEM_MOVE",
}
# ★긴 이름 먼저(pr_m_item 이 pr_m_item_bom/cost 를 접두사로 품는다)
ORDER = sorted(MAP, key=len, reverse=True)

RD = os.path.join(BE, "routers")
FILES = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]

print("=" * 100)
print(" 스키마 무접두 교정 — TEST3.dbo(낡은 사본) → nx")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

tot = 0
for f in FILES:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    lines = open(p, encoding="utf-8").read().split("\n")
    out, n = [], 0
    for i, ln in enumerate(lines, 1):
        new = ln
        if not ln.lstrip().startswith("#"):
            for t in ORDER:
                # FROM/JOIN 뒤 스키마 없이 바로 이름인 것만
                RX = re.compile(r"\b(FROM|JOIN)(\s+)(?!PARTNER_ERP|nx\.|dbo\.|\{|#)\[?(" + t + r")\]?\b(?![_\w])", re.I)
                if not RX.search(new): continue
                new = RX.sub(lambda m: "{}{}{}".format(m.group(1), m.group(2), MAP[t]), new)
        if new != ln:
            n += 1
            print("   {:<16s} L{:<5d} {}".format(os.path.basename(f), i, new.strip()[:80]))
        out.append(new)
    tot += n
    if n and APPLY:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, os.path.basename(f)))
        open(p, "w", encoding="utf-8", newline="").write("\n".join(out))

print("\n" + "=" * 100)
print(" 치환 {}곳".format(tot))
if APPLY:
    print(" 백업 = {}".format(BK))
    bad = 0
    for f in FILES:
        p = os.path.join(BE, f)
        if not os.path.exists(p): continue
        for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
            if re.search(r"nx\.nx\.|PARTNER_ERP_TEST3\.nx\.nx\.", ln):
                print("   ★이중접두어 {} L{}".format(os.path.basename(f), i)); bad += 1
    print(" 이중접두어: {}".format("✔ 없음" if bad == 0 else "★{}곳".format(bad)))
else:
    print(" ※dry-run — 반영하려면 --apply")
