# -*- coding: utf-8 -*-
"""흐름 TestBed — **검증 케이스 정의** (여기만 고치면 된다)

★다른 세션이 자기 프로그램을 검증에 넣으려면 이 파일에 dict 하나만 추가하면 된다.
  하네스 본체(flow_scenarios.py)·롤백 서버(flow_server.py)는 건드릴 필요가 없다.

──────────────────────────────────────────────────────────────────────────
케이스 형식
  {
    "kind":  "F"  흐름(값이 제대로 적히는지) | "R" 규칙(제대로 막는지)
    "name":  화면·규칙 이름 (사람이 읽는 라벨)
    "method":"POST" | "GET"
    "path":  "/api/..."            ← 화면이 실제로 부르는 그 경로
    "body":  dict 또는 lambda ctx: dict     ← ctx = 픽스처(아래 FIXTURES 결과)
    "skip_if": lambda ctx: bool             (선택) True 면 SKIP

    # kind="F" 일 때
    "probe":  관측 이름(PROBES 키)          예: "원장MAT"
    "delta":  기대 증감                     예: +100
    "mirror": True 면 수불장·재고까지 3곳 일치를 요구(자재 계열만)

    # kind="R" 일 때
    "keyword": 거부 사유에 들어가야 할 말   예: "재고부족"
               (문구가 달라도 거부 자체가 되면 PASS — 문구는 참고용)
  }

규칙 케이스 판정
  · 거부(4xx 또는 ok:false) + **DB 무기록** 이어야 PASS
  · 통과해버리면 "미구현" 으로 보고된다(거부했는데 기록되면 FAIL)

★새 규칙을 만들면 반드시 여기에 [R] 케이스를 같이 추가한다
  (정본 STOCK_GATING_CLOSE_LOCK_RULES.md §0-★ — 규칙은 검증과 함께 산다).
──────────────────────────────────────────────────────────────────────────
"""

# ★검증 일자 — **오늘**로 자동 계산한다. 하드코딩하지 말 것.
#   2026-08-29 실측 사고: 여기가 "260828" 로 박혀 있었는데 날짜가 하루 넘어가자
#   케이스는 28일로 쓰고 서버 프로브(flow_server.PROBES 는 스코프 일자 = 오늘)는 29일을 봐서
#   **키팅 2건이 delta 0 으로 FAIL** 했다. 코드는 멀쩡한데 하네스가 거짓 실패를 낸 것이다.
#   거짓 실패는 진짜 실패보다 나쁘다 — 다음 사람이 하네스를 못 믿게 된다.
import datetime as _dt
YMD = _dt.date.today().strftime("%y%m%d")     # 검증 일자(미마감 구간 = 오늘)


# ── 픽스처 : 케이스에서 쓸 실데이터를 **쓰기 시작 전에** 모아둔다 ────────
#   ★쓰기가 시작된 뒤 별도 커넥션으로 원장을 읽으면 자기 미커밋 잠금에 걸려
#     무한 대기한다(2026-08-28 실측). 그래서 픽스처는 전부 여기서 선조회한다.
#   형식 (키, SQL, 행→ctx 반영 함수)
FIXTURES = [
    ("mat", """SELECT TOP 1 UPPER(LTRIM(RTRIM(a.MAT_CODE))), SUM(CAST(a.STOCK_QTY AS float))
                 FROM nx.mat_stock_daily a JOIN nx.item i ON i.item_code = a.MAT_CODE
                GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE)))
               HAVING SUM(CAST(a.STOCK_QTY AS float)) BETWEEN 500 AND 100000
                ORDER BY 2 DESC""",
     lambda ctx, r: ctx.update(mat=str(r[0]), avail=float(r[1]))),

    ("closed", """SELECT TOP 1 ptype, period FROM nx.period_close
                   WHERE domain='MAT' AND close_flag=1 ORDER BY period DESC""",
     lambda ctx, r: ctx.update(closed_ptype=str(r[0]), closed_period=str(r[1]))),

    ("kit", """SELECT TOP 1 UPPER(LTRIM(RTRIM(ITEM_CODE))), GAGONG_PROC_CODE, WORK_ORDER
                 FROM nx.stock_ledger WHERE STOCK_POINT='RDY' AND GAGONG_PROC_CODE IS NOT NULL
                ORDER BY MAINT_YMD DESC""",
     lambda ctx, r: ctx.update(kit_item=str(r[0]), kit_gpc=str(r[1]).strip(),
                               kit_wo=str(r[2] or "").strip())),

    # ★완제품(ASY) 게이트용 — '지금' 잔량이 있는 품목. 2502 기초만 큰 품목을 고르면
    #   이후 다 소진돼 오차단으로 오판한다(2026-08-29 실측: 5006AR4091D 기초 10,051 · 현재 0).
    #   ⟹ 제품재고조회 화면과 같은 식으로 현재 잔량을 계산해 고른다.
    # ★자재입고는 거래처(매입처) 필수다(다른 세션이 2026-08-28 검증 추가:
    #   "매입처 없는 입고는 매입마감·수불에서 누락된다"). 케이스가 안 따라가 FAIL 났다.
    ("matcust", """SELECT TOP 1 LTRIM(RTRIM(ISNULL(CUST_CODE,''))) FROM nx.PU_T_STOCK_MAINT
                    WHERE MAINT_TAG='9' AND ISNULL(CUST_CODE,'')<>''
                    GROUP BY LTRIM(RTRIM(ISNULL(CUST_CODE,''))) ORDER BY COUNT(*) DESC""",
     lambda ctx, r: ctx.update(matcust=str(r[0]).strip())),

    ("asy", """WITH MV AS (
                 SELECT UPPER(item_code) it, maint_qty q FROM nx.sa_t_stock_maint
                  WHERE maint_ymd>'250299'
                    AND ((maint_tag='P' AND ISNULL(in_part_code,'')='') OR maint_tag IN ('B','V','J','8','R','2'))
                 UNION ALL
                 SELECT UPPER(mat_code), maint_qty*-1 FROM nx.pu_t_stock_maint
                  WHERE maint_ymd>'250299' AND ISNULL(out_wh_gubun,'1')='2'
                 UNION ALL
                 SELECT UPPER(item_code), stock_qty FROM nx.sa_t_month_stock WHERE stock_yymm='2502')
               SELECT TOP 1 it, SUM(q) FROM MV GROUP BY it HAVING SUM(q) > 50 ORDER BY SUM(q) DESC""",
     lambda ctx, r: ctx.update(asy_item=str(r[0]).strip(), asy_qty=float(r[1] or 0))),

    ("sale_cust", """SELECT TOP 1 cust_code FROM nx.saleout_maint WHERE maint_tag='5'
                      GROUP BY cust_code ORDER BY COUNT(*) DESC""",
     lambda ctx, r: ctx.update(sale_cust=str(r[0]).strip())),

    # 창고간이동 검증용 — FROM 파트(P0001 가공창고)에 실제 재고가 있는 자재
    # ★가드가 보는 소스와 **같은 소스**로 고른다 — matissue 는 원장(stock_ledger) SUM 을 본다.
    #   미러(PR_T_MAT_STOCK_WH)에서 고르면 "가용 0" 으로 걸린다(2026-08-28 실측).
    ("mv_mat", """SELECT TOP 1 UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(MAINT_QTY AS float))
                    FROM nx.stock_ledger
                   WHERE STOCK_POINT='MAT' AND ISNULL(GAGONG_PROC_CODE,'')='P0001' AND MAT_CODE IS NOT NULL
                   GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))
                  HAVING SUM(CAST(MAINT_QTY AS float)) > 100 ORDER BY 2 DESC""",
     lambda ctx, r: ctx.update(mv_mat=str(r[0]), mv_avail=float(r[1]))),

    ("prod_item", """SELECT TOP 1 b.parent_code, COUNT(*)
                       FROM nx.bom b JOIN nx.item i ON i.item_code = b.parent_code
                      WHERE ISNULL(i.make_type,'') = '1'
                      GROUP BY b.parent_code HAVING COUNT(*) >= 2 ORDER BY COUNT(*) DESC""",
     lambda ctx, r: ctx.update(prod_item=str(r[0]).strip())),
]


def _save(screen, qty, ymd=None, mat=None):
    """자재 3화면 공통 payload — {screen, rows:[{MAINT_YMD, MAT_CODE, qty}]}
       ★ymd/mat 는 **None 일 때만** 기본값으로 채운다. `or` 를 쓰면 빈 문자열이
         기본값으로 되돌아가 '일자 누락' 같은 음성 케이스를 만들 수 없다(2026-08-28 실측)."""
    def _b(ctx):
        row = {"MAINT_YMD": YMD if ymd is None else ymd,
               "MAT_CODE": (ctx["mat"] if mat is None else mat), "qty": qty}
        # ★입고 계열은 거래처(매입처) 필수 — 없으면 "거래처(매입처)가 필요합니다" 로 거부된다.
        if screen == "receipt" and ctx.get("matcust"):
            row["CUST_CODE"] = ctx["matcust"]
        return {"screen": screen, "user": "flowverify", "rows": [row]}
    return _b


def _locked_ymd(ctx):
    """마감된 기간의 일자(월마감이면 그 달 15일)."""
    p = ctx.get("closed_period") or ""
    return p if ctx.get("closed_ptype") == "D" else (p + "15")


CASES = [
    # ══ [F] 흐름 : 자재 ═══════════════════════════════════════════════
    dict(kind="F", name="자재입고 (자재입고관리)", method="POST", path="/api/stock/save",
         body=_save("receipt", 100), probe="원장MAT", delta=+100, mirror=True),
    dict(kind="F", name="자재조정 (자재재고조정)", method="POST", path="/api/stock/save",
         body=_save("adjust", 50), probe="원장MAT", delta=+50, mirror=True),
    dict(kind="F", name="자재출고 (자재출고관리)", method="POST", path="/api/stock/save",
         body=_save("issue", 30), probe="원장MAT", delta=-30, mirror=True),
    dict(kind="F", name="자재반품", method="POST", path="/api/stock/save",
         body=_save("return", 15), probe="원장MAT", delta=-15, mirror=True),

    # 수정/삭제는 앞서 넣은 입고행(+100)을 대상으로 한다 → 하네스가 키를 찾아 채운다
    dict(kind="F", name="자재수정 stock_update", method="POST", path="/api/stock/update",
         needs_ledger_key=True, probe="원장MAT", delta=+50, mirror=True,
         body=lambda ctx: {"screen": "receipt", "MAINT_YMD": ctx["_kymd"], "MAINT_SEQ": ctx["_kseq"],
                           "qty": 150, "MAT_CODE": ctx["mat"], "user": "flowverify"}),
    dict(kind="F", name="자재삭제 stock_delete", method="POST", path="/api/stock/delete",
         probe="원장MAT", delta=-150, mirror=True,
         body=lambda ctx: {"MAINT_YMD": ctx["_kymd"], "MAINT_SEQ": ctx["_kseq"], "user": "flowverify"}),

    # ══ [F] 흐름 : 생산·영업 ══════════════════════════════════════════
    dict(kind="F", name="키팅 확인 (준비실적처리)", method="POST", path="/api/kitting/cell-confirm",
         probe="원장RDY", delta=+10, mirror=False,
         skip_if=lambda ctx: "kit_item" not in ctx,
         body=lambda ctx: {"item": ctx["kit_item"], "gpc": ctx["kit_gpc"], "wo": ctx["kit_wo"],
                           "ymd": YMD, "qty": 10, "user": "flowverify"}),
    dict(kind="F", name="생산실적 (공정별생산실적)", method="POST", path="/api/procreg/save",
         probe="공정실적수량", delta=+7, mirror=False,
         body=lambda ctx: {"prod_ymd": YMD, "item_code": ctx["mat"], "prod_qty": 7, "user": "flowverify"}),
    dict(kind="F", name="판매출고 (판매및출고등록)", method="POST", path="/api/saleout/save",
         probe="판매출고수량", delta=-5, mirror=False,
         skip_if=lambda ctx: "sale_cust" not in ctx,
         body=lambda ctx: {"out_cust": ctx["sale_cust"], "item_code": ctx["mat"], "out_qty": 5,
                           "out_ymd": YMD, "user": "flowverify"}),

    # ══ [R] 규칙 : 음수재고 차단 (예외 없음 §0-★) ═════════════════════
    dict(kind="R", name="자재출고 — 가용 초과(음수유발) 차단", method="POST", path="/api/stock/save",
         keyword="재고부족", body=lambda ctx: _save("issue", ctx["avail"] * 10 + 100000)(ctx)),
    dict(kind="R", name="자재반품 — 가용 초과 차단", method="POST", path="/api/stock/save",
         keyword="재고부족", body=lambda ctx: _save("return", ctx["avail"] * 10 + 100000)(ctx)),
    dict(kind="R", name="자재조정 — 감소로 음수 유발 차단", method="POST", path="/api/stock/save",
         keyword="음수재고", body=lambda ctx: _save("adjust", -(ctx["avail"] * 10 + 100000))(ctx)),

    # ══ [R] 규칙 : 마감기간 잠금 ══════════════════════════════════════
    dict(kind="R", name="자재 쓰기 — 마감기간 잠금", method="POST", path="/api/stock/save",
         keyword="마감", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: _save("receipt", 10, ymd=_locked_ymd(ctx))(ctx)),
    dict(kind="R", name="키팅 — 마감기간 잠금", method="POST", path="/api/kitting/cell-confirm",
         keyword="마감", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"item": ctx["mat"], "gpc": "P1", "ymd": _locked_ymd(ctx),
                           "qty": 1, "user": "flowverify"}),
    dict(kind="R", name="마감 권한 게이트 (무권한 사용자)", method="POST", path="/api/close/run",
         keyword="권한이 없습니다", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"domain": "MAT", "ptype": ctx["closed_ptype"],
                           "period": ctx["closed_period"], "user": "flowverify"}),
    dict(kind="R", name="마감 중복 실행 차단 (관리자)", method="POST", path="/api/close/run",
         keyword="이미 마감", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"domain": "MAT", "ptype": ctx["closed_ptype"],
                           "period": ctx["closed_period"], "user": "admin"}),
    dict(kind="R", name="마감 해제 권한 게이트 (조회전용 사용자)", method="POST", path="/api/close/cancel",
         keyword="권한이 없습니다", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"domain": "MAT", "ptype": ctx["closed_ptype"],
                           "period": ctx["closed_period"], "user": "kdev"}),

    # ══ [R] 규칙 : 생산실적 재고 게이트 (예외 없음) ═══════════════════
    dict(kind="R", name="백플러시 — 자재부족 차단", method="POST", path="/api/backflush/post",
         keyword="자재부족으로 생산실적 불가", skip_if=lambda ctx: "prod_item" not in ctx,
         body=lambda ctx: {"item": ctx["prod_item"], "prod_qty": 9999999,
                           "wo": "FLOWTEST", "user": "flowverify"}),
    dict(kind="R", name="공정별생산실적 — 자재부족 차단", method="POST", path="/api/procreg/save",
         keyword="자재부족으로 생산실적 등록 불가", skip_if=lambda ctx: "prod_item" not in ctx,
         body=lambda ctx: {"prod_ymd": YMD, "item_code": ctx["prod_item"],
                           "prod_qty": 9999999, "user": "flowverify"}),

    # ══ [R] 규칙 : 입력 유효성 ════════════════════════════════════════
    # ── 완제품(ASY) 재고 게이트 (2026-08-29 신설) ──────────────────────────
    #   정본 = common._finished_avail() = 제품재고조회 화면과 **동일 계산**.
    #   전수 대조: 잔량≠0 267품목 **불일치 0건**. 사전 차단율 0.05%(8월 1,876건 중 1건).
    dict(kind="R", name="출하실적 — 완제품 재고부족 차단", method="POST", path="/api/lgsale/save",
         keyword="재고부족", skip_if=lambda ctx: "asy_item" not in ctx,
         body=lambda ctx: {"work_order": "GATETEST", "item_code": ctx["asy_item"],
                           "sale_qty": ctx["asy_qty"] + 100000, "user": "flowverify"}),
    dict(kind="R", name="미등록 품목 차단", method="POST", path="/api/stock/save",
         keyword="미등록", body=_save("receipt", 10, mat="ZZ_NOT_EXIST_9999")),
    dict(kind="R", name="수량 0 차단", method="POST", path="/api/stock/save",
         keyword="0보다", body=_save("receipt", 0)),
    dict(kind="R", name="조정수량 0 차단", method="POST", path="/api/stock/save",
         keyword="0일 수 없", body=_save("adjust", 0)),
    dict(kind="R", name="일자 누락 차단", method="POST", path="/api/stock/save",
         keyword="일자", body=_save("receipt", 10, ymd="")),
    dict(kind="R", name="screen 오류 차단", method="POST", path="/api/stock/save",
         keyword="screen", body=lambda ctx: {"screen": "bogus", "rows": []}),
    # ══ [F] 흐름 : 생산 파트재고·창고이동 (2026-08-28 확장) ═══════════
    #   재고를 실제로 움직이는데 검증에 없던 화면들. 218개 쓰기 중 재고 이동 경로부터 채운다.
    dict(kind="F", name="출하실적 — 잔량 이내는 통과 (−ASY)", method="POST", path="/api/lgsale/save",
         probe="원장ASY", delta=-1, mirror=False,
         skip_if=lambda ctx: "asy_item" not in ctx,
         body=lambda ctx: {"work_order": "GATETEST", "item_code": ctx["asy_item"],
                           "sale_qty": 1, "user": "flowverify"}),
    dict(kind="F", name="생산파트재고조정 (stockmaint/save)", method="POST", path="/api/stockmaint/save",
         probe="원장PRD", delta=+40, mirror=False,
         body=lambda ctx: {"maint_ymd": YMD, "mat_code": ctx["mat"], "maint_tag": "4",
                           "part_code": "P0001", "maint_qty": 40, "maint_cost": 100,
                           "remarks": "flowverify", "user": "flowverify"}),
    dict(kind="F", name="자재 창고간이동 (matissue/save)", method="POST", path="/api/matissue/save",
         probe="원장PRD", delta=0, mirror=False,
         skip_if=lambda ctx: "mv_mat" not in ctx,
         body=lambda ctx: {"issue_ymd": YMD, "mat_code": ctx["mv_mat"],
                           "from_part_code": "P0001", "part_code": "P0002",
                           "issue_qty": 5, "remarks": "flowverify", "user": "flowverify"}),
    dict(kind="F", name="키팅 취소 (준비실적처리 cell-cancel)", method="POST", path="/api/kitting/cell-cancel",
         probe="원장RDY", delta=-10, mirror=False,
         skip_if=lambda ctx: "kit_item" not in ctx,
         body=lambda ctx: {"item": ctx["kit_item"], "gpc": ctx["kit_gpc"], "wo": ctx["kit_wo"],
                           "ymd": YMD, "qty": 10, "user": "flowverify"}),

    # ══ [R] 규칙 : 위 화면들도 같은 규칙을 지키는가 ════════════════════
    dict(kind="R", name="생산파트재고조정 — 수량 0 차단", method="POST", path="/api/stockmaint/save",
         keyword="0일 수 없",
         body=lambda ctx: {"maint_ymd": YMD, "mat_code": ctx["mat"], "maint_tag": "4",
                           "part_code": "P0001", "maint_qty": 0, "user": "flowverify"}),
    dict(kind="R", name="생산파트재고조정 — 마감기간 잠금", method="POST", path="/api/stockmaint/save",
         keyword="마감", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"maint_ymd": _locked_ymd(ctx), "mat_code": ctx["mat"], "maint_tag": "4",
                           "part_code": "P0001", "maint_qty": 10, "user": "flowverify"}),
    dict(kind="R", name="생산파트재고조정 — 파트코드 오류 차단", method="POST", path="/api/stockmaint/save",
         keyword="파트코드",
         body=lambda ctx: {"maint_ymd": YMD, "mat_code": ctx["mat"], "maint_tag": "4",
                           "part_code": "없는파트", "maint_qty": 10, "user": "flowverify"}),
    dict(kind="R", name="자재 창고간이동 — FROM파트 재고부족 차단", method="POST", path="/api/matissue/save",
         keyword="재고부족",
         body=lambda ctx: {"issue_ymd": YMD, "mat_code": ctx["mat"],
                           "from_part_code": "P0001", "part_code": "P0002",
                           "issue_qty": 99999999, "user": "flowverify"}),
    dict(kind="R", name="자재 창고간이동 — 같은 파트 차단", method="POST", path="/api/matissue/save",
         keyword="같습니다",
         body=lambda ctx: {"issue_ymd": YMD, "mat_code": ctx["mat"],
                           "from_part_code": "P0001", "part_code": "P0001",
                           "issue_qty": 1, "user": "flowverify"}),
    dict(kind="R", name="자재 창고간이동 — 수량 0 차단", method="POST", path="/api/matissue/save",
         keyword="0보다",
         body=lambda ctx: {"issue_ymd": YMD, "mat_code": ctx["mat"],
                           "from_part_code": "P0001", "part_code": "P0002",
                           "issue_qty": 0, "user": "flowverify"}),
    dict(kind="R", name="발주입고 — 미등록품목 차단", method="POST", path="/api/matrecv/receive",
         keyword="미등록",
         body=lambda ctx: {"ymd": YMD, "wh": "IS0001",
                           "rows": [{"item": "ZZ_NOT_EXIST_9999", "qty": 10}], "user": "flowverify"}),
    dict(kind="R", name="발주입고 — 마감기간 잠금", method="POST", path="/api/matrecv/receive",
         keyword="마감", skip_if=lambda ctx: not ctx.get("closed_period"),
         body=lambda ctx: {"ymd": _locked_ymd(ctx), "wh": "IS0001",
                           "rows": [{"item": ctx["mat"], "qty": 10}], "user": "flowverify"}),
]


# ── 차단 사유가 **왜 안 되는지** 를 담고 있는지 검사 (규칙 A-0-1) ──────
#   단순 "재고부족" 이 아니라 품목·소요·보유가 보여야 한다.
REASON_CHECKS = [
    dict(name="차단 사유 고지 (어느 자재·얼마 부족·어디 있는지)",
         method="POST", path="/api/backflush/post",
         must_contain=["준비재고", "자재재고", "소요"],
         skip_if=lambda ctx: "prod_item" not in ctx,
         body=lambda ctx: {"item": ctx["prod_item"], "prod_qty": 9999999,
                           "wo": "FLOWTEST", "user": "flowverify"}),
]


# ── 캐시 stale 검사 ────────────────────────────────────────────────────
#   ★캐시만 붙이고 무효화를 빼면 "재고가 움직였는데 화면은 옛 값" 이 된다.
#
#   ★2026-08-28 실측으로 확인된 것 — **수불장은 웹 입력분을 보지 않는다.**
#     수불장·마감 = 라이브 전표(PARTNER_ERP.dbo.PU_T_STOCK_MAINT)를 읽는다.
#     웹 쓰기(/api/stock/save) = nx.stock_ledger 에 쓴다.   ⟹ 축이 다르다.
#     이건 병행 테스트 기간의 **의도된 분리**다(CLOSE_MGMT_CANON §26):
#       재고 금액은 실데이터만 반영해야 하므로 마감은 라이브만 본다.
#     따라서 "웹 입고 → 수불장 기말 +100" 은 **성립하지 않는다.** 이 검사는 성립 조건이 없다.
#
#   그래서 캐시 무효화는 **값이 아니라 동작으로** 검증한다:
#     쓰기 직후 조회가 **재계산되는가**(캐시가 버려졌는가) = 응답시간이 캐시히트보다 확연히 길어짐.
#     ※컷오버 후 원장이 정본이 되면 그때 값 기반 검사로 바꾼다.
CACHE_CHECKS = [
    dict(name="캐시 무효화 — 재고 쓰기 후 수불장이 재계산되는가",
         ledger=lambda ctx: f"/api/close/ledger?domain=MAT&d_from={YMD[:4]}01&d_to={YMD}",
         write_path="/api/stock/save",
         write_body=lambda ctx: _save("receipt", 100)(ctx),
         mode="recompute"),      # 값이 아니라 '재계산 발생' 으로 판정
]


# ── 조회형 점검(쓰기 없음) : 리포트가 살아 있는지 ─────────────────────
READ_CHECKS = [
    dict(name="단가0·음수 제외 리포트(/api/close/anomaly)", method="GET",
         path=lambda ctx: f"/api/close/anomaly?domain=MAT&ptype=M&period={ctx.get('closed_period') or '2607'}"),
    dict(name="자재 수불장(/api/close/ledger)", method="GET",
         path=lambda ctx: f"/api/close/ledger?domain=MAT&d_from={YMD[:4]}01&d_to={YMD}"),
    dict(name="생산 수불장(/api/close/ledger?domain=PRD)", method="GET",
         path=lambda ctx: f"/api/close/ledger?domain=PRD&d_from={YMD[:4]}01&d_to={YMD}"),
]


# ══════════════════════════════════════════════════════════════════════
#  인증 · 소속 강제 · 세트입고  (협력사 포털 1단계, 2026-08-29)
#  정본 = _schema/PARTNER_PORTAL_DESIGN.md §10~12
# ══════════════════════════════════════════════════════════════════════

# ★하네스가 쓰는 개발 시드 계정.
#   운영 전환 전에 **반드시 비밀번호를 바꾼다**(바꾸면 환경변수로 넘긴다).
#   이 계정들은 PARTNER_ERP_TEST3 의 개발 시드이며, 화면(브라우저)에는 더 이상
#   비밀번호가 실려 나가지 않는다 — 여기 있는 것은 하네스가 로그인하기 위한 것이다.
import io
import os as _os
import json as _j


def _secret(key, env, dflt=None):
    """하네스 자격 — ①환경변수 ②repo 밖 .flow_secrets.json ③개발시드 기본값.
       ★비밀번호를 repo 에 넣지 않는다. 없으면 그 계정 케이스는 SKIP 된다(조용히 통과 아님)."""
    v = _os.environ.get(env)
    if v:
        return v
    try:
        _f = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".flow_secrets.json")
        return (_j.load(io.open(_f, encoding="utf-8")) or {}).get(key) or dflt
    except Exception:
        return dflt


# ★[F]/[R] 케이스의 기본 로그인 계정.
#   내부 API 전면 인증(2026-08-29) 이후로는 하네스도 로그인해야 화면 API 를 부를 수 있다.
#   케이스에 as_ 를 명시하면 그것이 우선하고, as_=None 이면 **무토큰**(비로그인 재현)이다.
DEFAULT_AS = "super"

ACCOUNTS = {
    "super":    _secret("super", "FLOW_PW_SUPER", "super"),     # 내부 · 시스템관리자
    "flowcoop": _secret("flowcoop", "FLOW_PW_COOP"),            # ★TestBed 협력사 전용(2096) — 배포금지
    "kdev":     _secret("kdev", "FLOW_PW_KDEV", "1234"),        # 내부 · 조회전용
}
COOP_CUST = "2096"          # 미래정밀 — 협력사 계정의 소속
OTHER_CUST = "2148"         # 대원산업 — '남의 것'


def _custs(res, *keys):
    """응답 rows 에서 거래처코드 집합을 뽑는다(컬럼명이 화면마다 달라 여러 개를 본다)."""
    out = set()
    for r in (res.get("rows") or []) if isinstance(res, dict) else []:
        for k in keys:
            v = r.get(k)
            if v is not None and str(v).strip():
                out.add(str(v).strip())
                break
    return out


def _only_mine(res, *keys):
    got = _custs(res, *keys)
    n = len(res.get("rows") or []) if isinstance(res, dict) else 0
    return (got <= {COOP_CUST}), f"{n}행 · 거래처 {sorted(got) or '없음'}"


AUTH_CASES = [
    # ── 로그인 전 : 아무것도 보이면 안 된다 ─────────────────────────
    dict(kind="S", name="무토큰 — 협력사 계획 조회", method="GET",
         path=f"/api/partner/planstatus?wc={OTHER_CUST}&from_ymd={YMD}&to_ymd={YMD}",
         as_=None, expect=401),
    dict(kind="S", name="무토큰 — 세트입고 송장목록", method="GET",
         path="/api/setin/list", as_=None, expect=401),
    dict(kind="S", name="무토큰 — 세트입고 실적", method="GET",
         path="/api/setstock/list", as_=None, expect=401),
    dict(kind="S", name="★무토큰 — 계정목록(예전엔 평문 비밀번호가 나왔다)", method="GET",
         path="/api/perm/users", as_=None, expect=401,
         check=lambda res, ctx: (("users" not in res), "계정 정보가 전혀 나오지 않음")),
    dict(kind="S", name="무토큰 — 입고 스캔", method="GET",
         path="/api/setstock/scan?barcode=700003", as_=None, expect=401),

    # ── 로그인 자체 ────────────────────────────────────────────────
    dict(kind="S", name="로그인 — 옳은 비밀번호", method="POST", path="/api/auth/login",
         body={"id": "super", "pw": ACCOUNTS["super"]}, as_=None, expect=200,
         check=lambda res, ctx: (bool(res.get("token")),
                                 f"{res.get('user',{}).get('nm')} · 유효 {res.get('expires_hours')}시간")),
    dict(kind="S", name="로그인 — 틀린 비밀번호", method="POST", path="/api/auth/login",
         body={"id": "super", "pw": "틀린비번!!"}, as_=None, expect=401,
         check=lambda res, ctx: ("올바르지 않습니다" in str(res.get("detail", "")),
                                 f"응답 = {res.get('detail')}")),
    dict(kind="S", name="★로그인 — 없는 계정도 같은 문구(존재 여부를 흘리지 않는다)",
         method="POST", path="/api/auth/login",
         body={"id": "없는계정xyz", "pw": "x"}, as_=None, expect=401,
         check=lambda res, ctx: ("올바르지 않습니다" in str(res.get("detail", ""))
                                 and "없" not in str(res.get("detail", ""))[:10],
                                 f"응답 = {res.get('detail')}")),
    dict(kind="S", name="무토큰 — 내 정보 조회", method="GET", path="/api/auth/me",
         as_=None, expect=401),
    dict(kind="S", name="협력사 로그인 — 거래처코드가 실려 오는가", method="POST",
         path="/api/auth/login", body={"id": "flowcoop", "pw": ACCOUNTS["flowcoop"]},
         as_=None, expect=200,
         check=lambda res, ctx: (res.get("user", {}).get("partner_code") == COOP_CUST,
                                 f"{res.get('user',{}).get('nm')} · 유형 {res.get('user',{}).get('utype')}"
                                 f" · 거래처코드 {res.get('user',{}).get('partner_code')}")),

    # ── ★소속 강제 : 협력사가 남의 코드를 넣으면 ────────────────────
    dict(kind="S", name=f"★협력사가 남의 코드({OTHER_CUST}) 로 송장목록", method="GET",
         path=f"/api/setin/list?cust={OTHER_CUST}", as_="flowcoop", expect=200,
         check=lambda res, ctx: _only_mine(res, "in_cust_code", "cust_code", "cust")),
    dict(kind="S", name=f"★협력사가 남의 코드({OTHER_CUST}) 로 입고실적", method="GET",
         path=f"/api/setstock/list?cust={OTHER_CUST}", as_="flowcoop", expect=200,
         check=lambda res, ctx: _only_mine(res, "cust_code", "in_cust_code")),
    dict(kind="S", name=f"★협력사가 남의 작업처({OTHER_CUST}) 로 계획조회", method="GET",
         path=f"/api/partner/planstatus?wc={OTHER_CUST}", as_="flowcoop", expect=200,
         check=lambda res, ctx: _only_mine(res, "MAT_WORK_CENTER_CODE", "wc", "cust_code")),
    dict(kind="S", name="협력사가 자기 코드로 거래명세서 (비교 기준)", method="GET",
         path=f"/api/partner/deliv420?cust={COOP_CUST}", as_="flowcoop", expect=200,
         check=lambda res, ctx: (ctx.update(
             _deliv_mine=_j.dumps(res.get("rows") or [], sort_keys=True, default=str)) or True,
             f"{len(res.get('rows') or [])}행 — 이걸 기준으로 다음 케이스와 비교한다")),
    dict(kind="S", name="★협력사가 남의 코드로 거래명세서 조회 = 자기 결과와 같은가",
         method="GET", path=f"/api/partner/deliv420?cust={OTHER_CUST}",
         as_="flowcoop", expect=200,
         check=lambda res, ctx: _deliv_same(res, ctx)),
    dict(kind="S", name="★그 결과가 내부가 보는 남의 데이터와는 다른가", method="GET",
         path=f"/api/partner/deliv420?cust={OTHER_CUST}", as_="super", expect=200,
         check=lambda res, ctx: (
             _j.dumps(res.get("rows") or [], sort_keys=True, default=str) != ctx.get("_deliv_mine"),
             f"내부가 본 {OTHER_CUST} = {len(res.get('rows') or [])}행 · "
             f"협력사가 받은 것과 {'다름 = 남의 데이터가 아니었다' if _j.dumps(res.get('rows') or [], sort_keys=True, default=str) != ctx.get('_deliv_mine') else '★같음'}")),

    # ── 내부 사용자는 종전대로 (회귀 없음) ──────────────────────────
    dict(kind="S", name=f"내부 사용자는 남의 코드({OTHER_CUST}) 조회 가능", method="GET",
         path=f"/api/setin/list?cust={OTHER_CUST}", as_="super", expect=200,
         check=lambda res, ctx: (True,
                                 f"{len(res.get('rows') or [])}행 · 거래처 "
                                 f"{sorted(_custs(res,'in_cust_code','cust_code'))[:3]}")),
    dict(kind="S", name="내부 사용자는 전체 조회 가능", method="GET",
         path="/api/setin/list", as_="super", expect=200,
         check=lambda res, ctx: (len(_custs(res, "in_cust_code", "cust_code")) >= 1,
                                 f"{len(res.get('rows') or [])}행 · 거래처 "
                                 f"{len(_custs(res,'in_cust_code','cust_code'))}곳")),

    # ── 남의 문서 (바코드·송장번호만 알면 되는 API) ─────────────────
    dict(kind="S", name="★협력사가 남의 송장 명세 열람", method="GET",
         path=lambda ctx: f"/api/setin/detail?sheet={ctx.get('other_sheet')}",
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("other_sheet")),
    dict(kind="S", name="내부는 그 송장이 열린다(회귀 없음)", method="GET",
         path=lambda ctx: f"/api/setin/detail?sheet={ctx.get('other_sheet')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("other_sheet"),
         check=lambda res, ctx: (True, f"자도번 {len(res.get('rows') or [])}종")),
    dict(kind="S", name="★협력사가 남의 송장을 발행", method="POST", path="/api/setin/issue",
         body=lambda ctx: {"items": [{"sheet": ctx.get("other_sheet"), "qty": 1}]},
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("other_sheet")),
    dict(kind="S", name="★협력사가 남의 거래명세표 열람", method="GET",
         path=lambda ctx: f"/api/partner/deliv420/invoice?barcode={ctx.get('other_bc')}",
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("other_bc")),
    dict(kind="S", name="★협력사가 남의 발행을 취소", method="POST",
         path="/api/partner/deliv420/cancel",
         body=lambda ctx: {"barcode": ctx.get("other_bc")},
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("other_bc")),
    dict(kind="S", name="자기 거래명세표는 열린다", method="GET",
         path=lambda ctx: f"/api/partner/deliv420/invoice?barcode={ctx.get('my_bc')}",
         as_="flowcoop", expect=200, skip_if=lambda ctx: not ctx.get("my_bc"),
         check=lambda res, ctx: (True, f"품목 {len(res.get('rows') or res.get('items') or [])}종")),

    # ── 입고 처리 = 우리가 받는 행위 → 협력사 거부 ──────────────────
    dict(kind="S", name="★협력사가 입고 스캔", method="GET",
         path="/api/setstock/scan?barcode=700003", as_="flowcoop", expect=403),
    dict(kind="S", name="★협력사가 입고 처리", method="POST", path="/api/setstock/receive",
         body={"barcode": "700003", "tag": "2"}, as_="flowcoop", expect=403),
    dict(kind="S", name="★협력사가 입고 취소", method="POST", path="/api/setstock/cancel",
         body={"barcode": "700003"}, as_="flowcoop", expect=403),
    dict(kind="S", name="★협력사가 입고취소 미리보기", method="GET",
         path="/api/setstock/cancel_preview?barcode=700003", as_="flowcoop", expect=403),

    # ── 계정 API ───────────────────────────────────────────────────
    dict(kind="S", name="★계정목록에 평문 비밀번호가 나오지 않는가", method="GET",
         path="/api/perm/users", as_="super", expect=200,
         check=lambda res, ctx: (all("pw" not in u for u in (res.get("users") or [])),
                                 f"{len(res.get('users') or [])}명 · pw 필드 "
                                 f"{sum(1 for u in (res.get('users') or []) if 'pw' in u)}개 · "
                                 f"비번설정 {sum(1 for u in (res.get('users') or []) if u.get('pw_set'))}명")),
    dict(kind="S", name="협력사는 자기 계정만 본다", method="GET", path="/api/perm/users",
         as_="flowcoop", expect=200,
         check=lambda res, ctx: (len(res.get("users") or []) == 1
                                 and (res.get("users") or [{}])[0].get("id") == "flowcoop",
                                 f"{len(res.get('users') or [])}명 = "
                                 f"{[u.get('id') for u in (res.get('users') or [])]}")),
    dict(kind="S", name="★협력사가 계정을 저장", method="POST", path="/api/perm/users",
         body={"users": [{"id": "hacker", "nm": "침입", "roles": ["시스템관리자"]}]},
         as_="flowcoop", expect=403),
    dict(kind="S", name="조회전용 내부 사용자도 계정 저장 불가", method="POST",
         path="/api/perm/users",
         body={"users": [{"id": "hacker2", "nm": "침입2", "roles": ["시스템관리자"]}]},
         as_="kdev", expect=403),
]


def _deliv_same(res, ctx):
    """협력사가 남의 코드로 부른 결과가 **자기 코드로 부른 결과와 같은가**.
       같으면 요청값이 무시된 것 = 소속 강제가 걸린 것이다."""
    mine = ctx.get("_deliv_mine")
    got = _j.dumps(res.get("rows") or [], sort_keys=True, default=str)
    n = len(res.get("rows") or [])
    if mine is None:
        return False, "기준 케이스가 먼저 돌지 않았다"
    return (got == mine), (f"{n}행 · 자기코드({COOP_CUST}) 결과와 "
                           f"{'동일 = 요청값이 무시됐다' if got == mine else '★다름 = 남의 것이 샜다'}")


# ── 세트입고 왕복 : 발행 → 입고 → 중복차단 → 취소 → 재입고 ──────────
def _keep(key):
    def f(res, ctx):
        ctx[key] = res
        return True, ""
    return f


SETIN_CASES = [
    dict(kind="S", name="① 송장 발행 (계획편성분)", method="POST", path="/api/setin/issue",
         body=lambda ctx: {"items": [{"sheet": ctx.get("plan_sheet"), "qty": 10}]},
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (ctx.update(setbc=str(res.get("barcode") or "")) or
                                 bool(res.get("barcode")),
                                 f"SET바코드 {res.get('barcode')} 채번 · {res.get('count')}건")),
    dict(kind="S", name="② 스캔 — 입고 전에는 경고가 없어야", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('setbc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (not res.get("warn"),
                                 f"협력사 {res.get('custnm')} · 도번 {len(res.get('rows') or [])}종 · "
                                 f"이미입고 {res.get('already')}건 · 경고 {res.get('warn') or '없음'}")),
    dict(kind="S", name="③ 입고 — 재고 파생까지 생기는가", method="POST",
         path="/api/setstock/receive",
         body=lambda ctx: {"barcode": ctx.get("setbc"), "tag": "2", "user": "flowverify"},
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (ctx.update(posted=res.get("ledger_posted")) or
                                 res.get("received", 0) > 0,
                                 f"입고 {res.get('received')}건 · 자도번 재고파생 "
                                 f"{res.get('ledger_posted')}행")),
    dict(kind="S", name="④ ★같은 송장을 또 스캔하면 경고가 뜨는가", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('setbc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (bool(res.get("warn")),
                                 f"이미입고 {res.get('already')}건 · 경고 = {res.get('warn')}")),
    dict(kind="S", name="⑤ ★중복 입고는 막히는가 (재고가 두 배 되는 사고)", method="POST",
         path="/api/setstock/receive",
         body=lambda ctx: {"barcode": ctx.get("setbc"), "tag": "2", "user": "flowverify"},
         as_="super", expect=409, skip_if=lambda ctx: not ctx.get("plan_sheet")),
    dict(kind="S", name="⑥ 입고취소 미리보기 — 무엇이 되돌아가나", method="GET",
         path=lambda ctx: f"/api/setstock/cancel_preview?barcode={ctx.get('setbc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (res.get("recv_cnt", 0) > 0,
                                 f"입고 {res.get('recv_cnt')}건 · 재고파생 {res.get('ledger_cnt')}행 / "
                                 f"{res.get('ledger_qty')}개")),
    dict(kind="S", name="⑦ ★입고취소 — 3곳이 모두 되돌아가는가", method="POST",
         path="/api/setstock/cancel",
         body=lambda ctx: {"barcode": ctx.get("setbc"), "user": "flowverify", "reason": "검증"},
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: _cancel_check(res, ctx)),
    dict(kind="S", name="⑧ 취소 후 경고가 사라지는가", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('setbc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (not res.get("warn") and res.get("already") == 0,
                                 f"이미입고 {res.get('already')}건 · 경고 {res.get('warn') or '없음'}")),
    dict(kind="S", name="⑨ 취소 후 다시 입고할 수 있는가", method="POST",
         path="/api/setstock/receive",
         body=lambda ctx: {"barcode": ctx.get("setbc"), "tag": "2", "user": "flowverify"},
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("plan_sheet"),
         check=lambda res, ctx: (res.get("received", 0) > 0,
                                 f"재입고 {res.get('received')}건 · 재고파생 {res.get('ledger_posted')}행")),
    dict(kind="S", name="⑩ 없는 바코드 취소 — 사유가 명확한가", method="POST",
         path="/api/setstock/cancel", body={"barcode": "999999999"},
         as_="super", expect=404),
]


def _cancel_check(res, ctx):
    """취소 후 **DB 를 직접 확인**한다 — 응답만 믿지 않는다."""
    sql = ctx.get("_sql")
    bc = ctx.get("setbc")
    if not sql or not bc:
        return bool(res.get("ok")), "DB 확인 불가"
    mnt = sql("SELECT COUNT(*) FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'", bc)
    led = sql("SELECT COUNT(*) FROM nx.stock_ledger WHERE SHEET_NO=? AND MAINT_TAG='S'",
              int(bc) if str(bc).isdigit() else 0)
    req = sql("SELECT status, COUNT(*) FROM nx.set_input_req WHERE barcode_no=? GROUP BY status", bc)
    n_m = mnt[0][0] if mnt else -1
    n_l = led[0][0] if led else -1
    stat = [(str(r[0]).strip(), r[1]) for r in req]
    ok = (n_m == 0) and (n_l == 0) and all(s == "10" for s, _ in stat)
    return ok, (f"{res.get('msg')}\n           "
                f"DB 확인 → 입고거래 {n_m}건 · 재고파생 {n_l}행 · 송장상태 {stat}")


CASES += AUTH_CASES + SETIN_CASES

# 세트입고 왕복용 픽스처 (쓰기 전에 미리 읽는다)
FIXTURES += [
    ("plan_sheet", """SELECT TOP 1 h.sheet_no, COUNT(d.mat_code)
                        FROM nx.set_input_req h
                        JOIN nx.set_input_req_dtl d ON d.sheet_no = h.sheet_no
                       WHERE h.status='00' AND h.remarks='PLAN_COMPOSE'
                       GROUP BY h.sheet_no ORDER BY COUNT(d.mat_code) DESC""",
     lambda ctx, r: ctx.update(plan_sheet=str(r[0]).strip(), plan_dtl=int(r[1]))),

    ("other_sheet", """SELECT TOP 1 sheet_no FROM nx.set_input_req
                        WHERE in_cust_code<>'2096' AND ISNULL(in_cust_code,'')<>''""",
     lambda ctx, r: ctx.update(other_sheet=str(r[0]).strip())),

    ("other_bc", """SELECT TOP 1 barcode_no FROM nx.deliv_issue
                     WHERE cust_code<>'2096' AND ISNULL(barcode_no,'')<>''""",
     lambda ctx, r: ctx.update(other_bc=str(r[0]).strip())),

    ("my_bc", """SELECT TOP 1 barcode_no FROM nx.deliv_issue
                  WHERE cust_code='2096' AND ISNULL(barcode_no,'')<>'' AND status<>'99'""",
     lambda ctx, r: ctx.update(my_bc=str(r[0]).strip())),
]


# ══════════════════════════════════════════════════════════════════════
#  협력사 포털 전 구간 — 실제 사용 순서대로 + DB 확인 (2026-08-29)
#  정본 = _schema/PARTNER_PORTAL_DESIGN.md §14~15
#
#  흐름: 협력사 홈 → 발행 → QR → 출발 → (담당자) 스캔 → 입고 → 취소
#  ★응답만 믿지 않는다. 각 단계마다 ctx["_sql"] 로 **미커밋 DB 를 직접 조회**해
#    행이 실제로 생겼는지/상태가 바뀌었는지 확인한다.
# ══════════════════════════════════════════════════════════════════════

def _sql1(ctx, q, *a):
    """단일값 조회. 하네스 헬퍼(ctx['_sql'])는 미커밋 상태를 본다."""
    r = ctx["_sql"](q, *a)
    return (r[0][0] if r and r[0] else None)


def _pf_home(res, ctx):
    """① 협력사 홈 — 화면이 첫 화면에서 받는 것. 발행할 송장을 여기서 고른다."""
    ready = res.get("ready") or []
    ctx["pf_ready"] = ready[:2]
    return (res.get("cust") == COOP_CUST and isinstance(res.get("plan"), list),
            f"거래처 {res.get('cust')} · 계획 {len(res.get('plan') or [])}행 · "
            f"발행대기 {res.get('ready_cnt')}건 · 발행한송장 {len(res.get('issued') or [])}건")


def _pf_issue(res, ctx):
    """② 발행 — ★DB 에 barcode_no 가 채번되고 상태가 00→10 이 됐는가."""
    bc = str(res.get("barcode") or "").strip()
    ctx["pf_bc"] = bc
    if not bc:
        return False, f"바코드 미채번 · {res}"
    sheets = [x["sheet"] for x in (ctx.get("pf_ready") or [])]
    n10 = _sql1(ctx, "SELECT COUNT(*) FROM nx.set_input_req WHERE barcode_no=? AND status='10'", bc)
    st0 = _sql1(ctx, f"""SELECT COUNT(*) FROM nx.set_input_req
                          WHERE sheet_no IN ({','.join('?' * len(sheets))}) AND status='00'""", *sheets) if sheets else 0
    return (n10 == len(sheets) and st0 == 0),             f"SET{bc} · DB 확인 → 발행(10) {n10}건 / 요청(00) 잔여 {st0}건 (고른 것 {len(sheets)}건)"


def _pf_qr(res, ctx):
    """③ QR — SVG 가 나오는가. 마이크로 QR 이면 폰·리더기가 못 읽는다(표준 QR 강제 확인)."""
    s = res if isinstance(res, str) else str(res)
    # ★segno 의 SVG 는 width/height + <path> 다 — viewBox 가 없다(내 검사식이 틀렸던 부분).
    #   ★실측(2026-08-29): 표준 v1 = 21모듈 → (21+4)*6 = **150px**
    #                      마이크로 M3 = 15모듈 → (15+4)*6 = **114px**
    #   마이크로 QR 은 폰 카메라·리더기 상당수가 못 읽는다 → 140px 미만이면 FAIL.
    import re as _re
    m = _re.search(r'width="(\d+)"', s)
    w = int(m.group(1)) if m else 0
    return ("<svg" in s and "<path" in s and w >= 140),            f"{len(s):,}바이트 · width={w}px ⟹ {'표준 QR(v1=150px)' if w >= 140 else '★마이크로 QR(114px) — 폰·리더기가 못 읽는다'}"


def _pf_depart(res, ctx):
    """④ 출발 — ★DB 상태가 10→20 이 됐는가."""
    bc = ctx.get("pf_bc")
    n20 = _sql1(ctx, "SELECT COUNT(*) FROM nx.set_input_req WHERE barcode_no=? AND status='20'", bc)
    return (res.get("ok") and n20 > 0), f"{res.get('msg')} · DB 확인 → 출발(20) {n20}건"


def _pf_scan(res, ctx):
    """⑤ 담당자 스캔 — 확인 화면에 협력사·도번이 나오는가(즉시 입고하지 않는다)."""
    rows = res.get("rows") or []
    ctx["pf_scanq"] = sum(float(r.get("qty") or 0) for r in rows)
    return (res.get("cust") == COOP_CUST and len(rows) > 0),            f"{res.get('custnm')} · 도번 {len(rows)}종 · {ctx['pf_scanq']:,.0f}개 · 경고 {res.get('warn') or '없음'}"


def _pf_receive(res, ctx):
    """⑥ ★입고 — 데이터가 실제로 들어갔는가. 세 곳을 전부 확인한다."""
    bc = ctx.get("pf_bc")
    mnt = _sql1(ctx, "SELECT COUNT(*) FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'", bc)
    led = _sql1(ctx, "SELECT COUNT(*) FROM nx.stock_ledger WHERE SHEET_NO=? AND MAINT_TAG='S'",
                int(bc) if str(bc).isdigit() else 0)
    n90 = _sql1(ctx, "SELECT COUNT(*) FROM nx.set_input_req WHERE barcode_no=? AND status='90'", bc)
    ctx["pf_led"] = led
    return (res.get("received", 0) > 0 and mnt > 0 and n90 > 0),            (f"응답 입고 {res.get('received')}건 · 재고파생 {res.get('ledger_posted')}행\n           "
            f"DB 확인 → 입고거래 {mnt}건 · 원장(S) {led}행 · 입고완료(90) {n90}건")


def _pf_cancel(res, ctx):
    """⑦ 입고취소 — 세 곳이 **전부** 되돌아갔는가."""
    bc = ctx.get("pf_bc")
    mnt = _sql1(ctx, "SELECT COUNT(*) FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'", bc)
    led = _sql1(ctx, "SELECT COUNT(*) FROM nx.stock_ledger WHERE SHEET_NO=? AND MAINT_TAG='S'",
                int(bc) if str(bc).isdigit() else 0)
    st = ctx["_sql"]("SELECT status, COUNT(*) FROM nx.set_input_req WHERE barcode_no=? GROUP BY status", bc)
    stat = [(str(r[0]).strip(), r[1]) for r in st]
    ok = (mnt == 0 and led == 0 and all(a == "10" for a, _ in stat))
    return ok, (f"{res.get('msg')}\n           "
                f"DB 확인 → 입고거래 {mnt}건 · 원장(S) {led}행 · 송장상태 {stat}")


def _pf_final(res, ctx):
    """⑧ 협력사 홈에 되돌아온 것이 보이는가(화면이 다시 발행 대기로 잡는다)."""
    inv = {x["nm"]: x["cnt"] for x in (res.get("inv") or [])}
    return (res.get("cust") == COOP_CUST), f"상태별 {inv}"


PORTAL_CASES = [
    dict(kind="S", name="[포털] ① 협력사 홈 — 첫 화면 데이터", method="GET",
         path="/api/partner/my?days=14", as_="flowcoop", expect=200, check=_pf_home),

    # ── 유형별 분기 : 세트입고를 안 쓰는 협력사(76곳) 도 홈이 열려야 한다 ──
    #   ★쓰기 케이스보다 **먼저** 둔다 — 하네스는 트랜잭션을 끝까지 열어 두므로
    #     쓰기가 쌓인 뒤에는 plan_part_mat 스캔(=planstatus)이 급격히 느려진다.
    dict(kind="S", name="[포털] ⑭ 세트입고 안 쓰는 협력사(부자재) 홈", method="GET",
         path="/api/partner/my?cust=2136", as_="super", expect=200,
         check=lambda res, ctx: (res.get("cust") == "2136",
                                 f"{res.get('custnm')} · 계획 {len(res.get('plan') or [])}행 · "
                                 f"발행대기 {res.get('ready_cnt')}건 "
                                 f"⟹ 송장 탭은 화면에서 숨긴다(빈 화면 방지)")),

    dict(kind="S", name="[포털] ② ★송장 발행 — DB 에 채번·상태전이 되는가", method="POST",
         path="/api/setin/issue", as_="flowcoop", expect=200,
         body=lambda ctx: {"items": [{"sheet": x["sheet"], "qty": x["qty"]}
                                     for x in (ctx.get("pf_ready") or [])]},
         skip_if=lambda ctx: not ctx.get("pf_ready"), check=_pf_issue),

    dict(kind="S", name="[포털] ③ QR 발급(SVG)", method="GET",
         path=lambda ctx: f"/api/partner/qr?barcode={ctx.get('pf_bc')}",
         as_="flowcoop", expect=200, skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_qr),

    dict(kind="S", name="[포털] ④ ★남의 바코드 QR 은 막히나", method="GET",
         path=lambda ctx: f"/api/partner/qr?barcode={ctx.get('other_bc')}",
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("other_bc")),

    dict(kind="S", name="[포털] ⑤ ★출발 처리 — DB 상태 10→20", method="POST",
         path="/api/partner/depart", as_="flowcoop", expect=200,
         body=lambda ctx: {"barcode": ctx.get("pf_bc")},
         skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_depart),

    dict(kind="S", name="[포털] ⑥ 이미 출발한 것 재처리 차단", method="POST",
         path="/api/partner/depart", as_="flowcoop", expect=409,
         body=lambda ctx: {"barcode": ctx.get("pf_bc")},
         skip_if=lambda ctx: not ctx.get("pf_bc")),

    dict(kind="S", name="[포털] ⑦ ★협력사는 입고 스캔 불가(담당자 몫)", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('pf_bc')}",
         as_="flowcoop", expect=403, skip_if=lambda ctx: not ctx.get("pf_bc")),

    dict(kind="S", name="[포털] ⑧ 담당자 스캔 — 확인 화면", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('pf_bc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_scan),

    dict(kind="S", name="[포털] ⑨ ★입고 — 입고거래·원장·상태 3곳에 들어갔나", method="POST",
         path="/api/setstock/receive", as_="super", expect=200,
         body=lambda ctx: {"barcode": ctx.get("pf_bc"), "tag": "2", "user": "flowverify"},
         skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_receive),

    dict(kind="S", name="[포털] ⑩ ★출발한 송장도 입고되나(20 누락 재발 방지)", method="GET",
         path=lambda ctx: f"/api/setstock/scan?barcode={ctx.get('pf_bc')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("pf_bc"),
         check=lambda res, ctx: (bool(res.get("warn")),
                                 "입고 뒤라 경고가 떠야 정상 — " + str(res.get("warn"))[:80])),

    dict(kind="S", name="[포털] ⑪ 중복 입고 차단", method="POST",
         path="/api/setstock/receive", as_="super", expect=409,
         body=lambda ctx: {"barcode": ctx.get("pf_bc"), "tag": "2"},
         skip_if=lambda ctx: not ctx.get("pf_bc")),

    dict(kind="S", name="[포털] ⑫ ★입고취소 — 3곳이 전부 되돌아가나", method="POST",
         path="/api/setstock/cancel", as_="super", expect=200,
         body=lambda ctx: {"barcode": ctx.get("pf_bc"), "user": "flowverify", "reason": "TestBed"},
         skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_cancel),

    dict(kind="S", name="[포털] ⑬ 협력사 홈에 반영", method="GET",
         path="/api/partner/my?days=14", as_="flowcoop", expect=200,
         skip_if=lambda ctx: not ctx.get("pf_bc"), check=_pf_final),

    dict(kind="S", name="[포털] ⑮ 내부 계정이 cust 없이 부르면 사유가 명확한가", method="GET",
         path="/api/partner/my", as_="super", expect=400),
]

# ★★케이스 순서 규칙 — **읽기 먼저, 쓰기 나중** (2026-08-29 실측으로 확정)
#   하네스는 트랜잭션 하나를 끝까지 열어 둔다(no-commit). 쓰기가 쌓일수록
#   `plan_part_mat`·`deliv_issue` 같은 큰 테이블 스캔이 급격히 느려진다
#   (운영 0.24s / 쓰기 누적 후 45s+ 타임아웃). **제품 결함이 아니라 하네스 특성**이다.
#   ⟹ 무거운 조회 케이스(소속강제·포털 홈)는 앞에, 쓰기 왕복은 뒤에 둔다.
#      AUTH(조회 위주) → PORTAL(홈 조회 + 왕복) → SETIN(왕복) → [F]/[R](쓰기)
#   ※각 케이스는 probe 델타로 판정하므로 순서를 바꿔도 판정 자체는 영향받지 않는다.
_i = CASES.index(SETIN_CASES[0])
CASES[_i:_i] = PORTAL_CASES
