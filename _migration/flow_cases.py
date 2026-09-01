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

    # ★[E] 전 구간용 — **자재소요가 실제로 걸린** 업체를 고른다.
    #   아무 협력사나 고르면 계획 0행이 나와 "화면이 못 읽는다"고 오판한다.
    #   ⟹ plan_part_mat 에 행이 가장 많은 작업처 = 검증 가치가 가장 높은 업체.
    ("e_wc", """SELECT TOP 1 LTRIM(RTRIM(mat_work_center_code)), COUNT(*)
                  FROM nx.plan_part_mat WITH(NOLOCK)
                 WHERE ISNULL(mat_work_center_code,'')<>''
                 GROUP BY LTRIM(RTRIM(mat_work_center_code)) ORDER BY COUNT(*) DESC""",
     lambda ctx, r: ctx.update(e_wc=str(r[0]).strip(), e_wc_rows=int(r[1] or 0))),
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
    # ★자격증명이 없으면 SKIP — 비번을 repo 에 두지 않는 설계(_secret)라 미제공이 정상 상태다.
    #   FAIL 로 두면 "로그인 기능이 깨졌다"로 읽혀 다음 사람이 헛수고한다(2026-09-01).
    #   as_ 를 쓰는 뒤 케이스들은 러너가 알아서 SKIP 하는데, 이 케이스만 body 로 직접
    #   비번을 실어 보내 401 → FAIL 이 됐다.
    dict(kind="S", name="협력사 로그인 — 거래처코드가 실려 오는가", method="POST",
         path="/api/auth/login", body={"id": "flowcoop", "pw": ACCOUNTS["flowcoop"]},
         as_=None, expect=200, skip_if=lambda ctx: ACCOUNTS.get("flowcoop") is None,
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

# ── 재생 파일럿(2026-09-01 · 대표 지시) ─────────────────────────────────
#   REPLAY_YMD 가 설정됐을 때만 레거시 거래를 **우리 API 로 다시 입력**하는 케이스를 덧붙인다.
#   ★데이터를 직접 넣지 않는다 — 하네스가 HTTP 로 라우터를 부른다(그래야 게이트·검증이 걸린다).
#   평소 스위트에는 영향이 없다(환경변수 없으면 아무것도 안 붙는다).
import os as _os
if _os.environ.get('REPLAY_YMD'):
    try:
        # REPLAY_ITEM 이 있으면 **그 품번의 하루 흐름**만 재현한다(시드 → 키팅 → 생산 → 출하).
        # 없으면 종전대로 그날 전체를 유형별로 재생한다.
        if _os.environ.get('REPLAY_ITEM'):
            from replay_cases import build_flow_cases as _bfc
            CASES += _bfc(_os.environ['REPLAY_YMD'], _os.environ['REPLAY_ITEM'].strip())
        else:
            from replay_cases import build_replay_cases as _brc
            CASES += _brc(_os.environ['REPLAY_YMD'])
    except Exception as _e:
        print('  ★재생 케이스 로드 실패: %s' % _e)


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


# ══════════════════════════════════════════════════════════════════════
#  ★마감 멱등성 · 화면↔수불장 일치  (2026-08-30 · CLOSE_MGMT_CANON §30)
#
#  같은 기간을 두 번 마감했더니 값이 달랐다(SAL D 260828: 677,272,841 vs 703,546,042).
#  원인 = 캐시 키가 연월인데 값은 as-of 일자. **이걸 잡는 검증이 없어서 여태 안 걸렸다.**
#  ⟹ 상설로 남긴다. 마감은 그 시점을 확정하는 것이다.
# ══════════════════════════════════════════════════════════════════════

def _tot(res, *fields):
    """수불장/재고조회 응답에서 기말금액 합계를 뽑는다(응답 모양이 화면마다 다르다)."""
    if not isinstance(res, dict):
        return None
    t = res.get("totals")
    if isinstance(t, dict):
        for f in fields:
            if f in t:
                return round(float(t[f] or 0), 0)
    rows = res.get("rows") or []
    for f in fields:
        if rows and f in rows[0]:
            return round(sum(float(r.get(f) or 0) for r in rows), 0)
    return None


def _keep_tot(key, *fields):
    def chk(res, ctx):
        v = _tot(res, *fields)
        ctx[key] = v
        return (v is not None), f"기말금액 {v:,.0f}" if v is not None else "합계를 못 읽음"
    return chk


def _same_as(key, *fields):
    """앞서 저장한 값과 **같아야** 통과. 캐시 오염이 있으면 여기서 걸린다."""
    def chk(res, ctx):
        v = _tot(res, *fields)
        b = ctx.get(key)
        if v is None or b is None:
            return False, f"비교 불가 (기준 {b} · 이번 {v})"
        d = v - b
        return (abs(d) < 1.0), (f"{v:,.0f} vs 기준 {b:,.0f} "
                                f"({'같음' if abs(d) < 1 else f'★{d:+,.0f} 차이 — 캐시 오염 의심'})")
    return chk


IDEM_CASES = [
    # ── ① 캐시 오염 재발 방지 — 짧은 기간을 먼저 조회해도 전체 결과가 안 바뀌어야 한다 ──
    #    수정 전에는 '월초 as-of 단가'가 월 키 캐시에 박혀 이후 조회가 전부 그 단가로 평가됐다.
    dict(kind="S", name="[마감] ① 생산 수불장 — 기준값 확보", method="GET",
         path="/api/close/ledger?domain=PRD&d_from=260801&d_to=260828&nocache=1",
         as_="super", expect=200, check=_keep_tot("idem_prd", "sa", "ta")),

    dict(kind="S", name="[마감] ② 짧은 기간을 먼저 조회(캐시 오염 유발 시도)", method="GET",
         path="/api/close/ledger?domain=PRD&d_from=260801&d_to=260805&nocache=1",
         as_="super", expect=200,
         check=lambda res, ctx: (True, f"기말금액 {_tot(res,'sa','ta'):,.0f} (오염 유발용)")),

    dict(kind="S", name="[마감] ③ ★전체 기간 재조회 — 값이 그대로인가", method="GET",
         path="/api/close/ledger?domain=PRD&d_from=260801&d_to=260828&nocache=1",
         as_="super", expect=200, check=_same_as("idem_prd", "sa", "ta")),

    dict(kind="S", name="[마감] ④ 영업 수불장 — 기준값 확보", method="GET",
         path="/api/close/ledger?domain=SAL&d_from=260801&d_to=260828&nocache=1",
         as_="super", expect=200, check=_keep_tot("idem_sal", "sa", "ta")),

    dict(kind="S", name="[마감] ⑤ 영업 짧은 기간 먼저 조회", method="GET",
         path="/api/close/ledger?domain=SAL&d_from=260801&d_to=260805&nocache=1",
         as_="super", expect=200,
         check=lambda res, ctx: (True, f"기말금액 {_tot(res,'sa','ta'):,.0f} (오염 유발용)")),

    dict(kind="S", name="[마감] ⑥ ★영업 전체 재조회 — 값이 그대로인가", method="GET",
         path="/api/close/ledger?domain=SAL&d_from=260801&d_to=260828&nocache=1",
         as_="super", expect=200, check=_same_as("idem_sal", "sa", "ta")),

    # ── ② 화면 ↔ 수불장 일치 (대표 확정 '가': 값이 같아야 비교가 된다) ──
    dict(kind="S", name="[마감] ⑦ ★생산재고조회 = 생산 수불장", method="GET",
         path="/api/live/prodstock?frm=260801&to=260828",
         as_="super", expect=200,
         check=lambda res, ctx: _cmp_screen(res, ctx, "idem_prd", "amt", only_ledger=True)),

    dict(kind="S", name="[마감] ⑧ ★영업재고조회 = 영업 수불장", method="GET",
         path="/api/live/salesstock?dfrom=260801&dto=260828&zero=1",
         as_="super", expect=200,
         check=lambda res, ctx: _cmp_screen(res, ctx, "idem_sal", "amt", only_ledger=True)),
]


def _cmp_screen(res, ctx, key, fld, only_ledger=False):
    """화면 합계가 수불장 기준값과 같은가.
       ★**수불장 단가를 받은 행만** 센다(`cost_src='수불장(이동평균)'`).
         화면에는 수불장에 없는 품목(단가0·음수라 스냅샷에서 빠진 것)이 남아 있어
         전체 합계로 비교하면 축이 달라 항상 어긋난다. 없는 값을 만들지 않는다는 설계 그대로다."""
    rows = res.get("rows") or []
    if only_ledger:
        rows = [r for r in rows if r.get("cost_src") == "수불장(이동평균)"]
    v = round(sum(float(r.get(fld) or 0) for r in rows), 0)
    b = ctx.get(key)
    if b is None:
        return False, "수불장 기준값이 없다(앞 케이스 실패)"
    d = v - b
    return (abs(d) <= 5.0), (f"화면 {v:,.0f} vs 수불장 {b:,.0f} "
                             f"({'일치' if abs(d) <= 5 else f'★{d:+,.0f} 차이'}) · {len(rows)}행")


CASES += IDEM_CASES


# ══════════════════════════════════════════════════════════════════════
#  [E] 전 구간 프로세스 — 계획업로드부터 마감까지 한 줄로 (2026-09-01 신설)
# ══════════════════════════════════════════════════════════════════════
#  왜 만들었나
#    기존 케이스는 도메인별 조각이다(재고·마감·포털·인증). 전부 PASS 여도
#    **"계획을 올려서 → 소요를 뽑아 → 발주하고 → 받아서 → 만들고 → 팔고 → 마감한다"**
#    는 한 줄이 실제로 이어지는지는 아무도 안 봤다.
#    2026-08-31 에 실사용 버그 3건(자재입고 500·삭제버튼·요청수량 이중차감)이
#    한꺼번에 터진 곳이 정확히 이 구간이다 — 조각검증은 통과했는데 줄이 끊겼던 것이다.
#
#  ★이 그룹의 판정 원칙 — "다음 단계가 쓸 수 있는 값이 나왔는가"
#    단순히 200 이 아니라, **앞 단계 산출물이 뒷 단계의 입력으로 실제 연결되는지**를 본다.
#    예: ④파트별이 만든 제번을 ⑤자재소요가 쓰는가 / ⑤가 만든 소요를 협력사 계획이 보는가.
#    끊긴 곳이 있으면 그 지점이 정확히 드러난다.
#
#  ★순서 — 읽기 먼저, 쓰기 나중 (§9 하드룰)
#    E1~E9 는 조회·집계 위주라 **CASES 앞**에 놓는다(무거운 조회를 앞에 모은다).
#    쓰기가 쌓인 뒤에 계획 조회를 돌리면 45초+ 로 느려져 스위트가 무너진다.
#
#  ★편성 단계(①④⑤)를 여기서 **실행하지 않는다** — 이유
#    STEP6/STEP7 은 `DROP TABLE` 후 재생성이고 수백초가 걸린다. 공유 트랜잭션 하나에
#    그걸 태우면 뒤 케이스가 전부 잠금 대기에 걸린다(§6-2 와 같은 함정).
#    ⟹ **직전 편성 결과를 읽어 연결을 검증**한다. 편성 자체의 정합은 별도 대사 스크립트 몫.

def _rows(res):
    return (res.get("rows") if isinstance(res, dict) else None) or []


def _refused(res):
    """조회가 **거부**됐는가. 빈 결과와 구분해야 한다 —
       거부를 '데이터 없음'으로 읽으면 거짓 PASS 가 난다(2026-09-01 실측)."""
    return isinstance(res, dict) and res.get("ok") is False and res.get("detail")


def _keep(ctx, key, val):
    ctx[key] = val
    return val


E_CASES = [
    # ── E1. 계획 원본이 있는가 (파이프라인의 입구) ──────────────────
    dict(kind="S", name="[전구간] E1 계획업로드 — 원본이 있는가", method="GET",
         path="/api/plan/list?limit=5", as_="super", expect=200,
         check=lambda res, ctx: (
             len(_rows(res)) > 0,
             f"계획원본 {len(_rows(res))}행" if _rows(res)
             else "★계획 원본이 비어 있다 — 뒤 단계가 전부 무의미해진다")),

    # ── E2. 단계 실행 로그 — 어디까지 돌았는지 알 수 있는가 ──────────
    #    레거시는 버튼 아래 완료시각이 있다. 웹도 그게 보여야 운영이 된다.
    dict(kind="S", name="[전구간] E2 편성 단계 로그 — 어디까지 돌았나", method="GET",
         path="/api/planrev/job/status", as_="super", expect=200,
         check=lambda res, ctx: _e2_steps(res, ctx)),

    # ── E3. ④파트별계획 산출 — 다음 단계가 쓸 제번이 있는가 ──────────
    dict(kind="S", name="[전구간] E3 ④파트별계획 — 제번이 나왔는가", method="GET",
         path="/api/planrev/job/log?limit=200", as_="super", expect=200,
         check=lambda res, ctx: _e3_part(res, ctx)),

    # ── E4. ★④ → ⑤ 연결 — 파트별 제번을 자재소요가 실제로 쓰는가 ────
    #    2026-08-31 정합작업의 핵심 축. 여기가 끊기면 발주를 못 낸다.
    #    ★판정은 **레거시 대비**로 한다. 절대값으로 보면 안 된다 —
    #      `plan_part_mat` 에는 파트별계획을 거치지 않는 계열(WO=수주·직납품 등)이
    #      **설계상 정상적으로** 들어간다. 2026-09-01 첫 실행에서 이걸 "고아 4,478행,
    #      근거 없는 발주"로 오판했는데, 레거시에도 4,484행이 똑같이 있었다.
    #      ⟹ 우리만 있는 고아(=진짜 결함)와 양쪽 다 있는 고아(=정상 계열)를 갈라서 본다.
    dict(kind="S", name="[전구간] E4 ★④→⑤ 연결 — 자재소요 제번이 레거시와 같은가",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             SELECT (SELECT COUNT(DISTINCT RTRIM(work_order)) FROM nx.plan_part_dtl WITH(NOLOCK)),
                    (SELECT COUNT(DISTINCT RTRIM(work_order)) FROM nx.plan_part_mat WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.plan_part_mat m WITH(NOLOCK)
                      WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WITH(NOLOCK)
                                        WHERE RTRIM(d.work_order)=RTRIM(m.work_order))),
                    (SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT m WITH(NOLOCK)
                      WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_DTL d WITH(NOLOCK)
                                        WHERE RTRIM(d.WORK_ORDER)=RTRIM(m.WORK_ORDER)))""", "args": []},
         check=lambda res, ctx: _e4_link(res, ctx)),

    # ── E5. ⑤자재소요 → 협력사계획 연결 (업체별로 갈라지는가) ────────
    #    대표 지시(2026-09-01): 자재계획은 **업체별로** 봐야 원인이 드러난다.
    dict(kind="S", name="[전구간] E5 ⑤→협력사 — 업체별로 소요가 갈라지는가",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             SELECT COUNT(DISTINCT LTRIM(RTRIM(ISNULL(mat_work_center_code,'')))),
                    SUM(CASE WHEN ISNULL(mat_work_center_code,'')='' THEN 1 ELSE 0 END),
                    COUNT(*)
               FROM nx.plan_part_mat WITH(NOLOCK)""", "args": []},
         check=lambda res, ctx: _e5_vendor(res, ctx)),

    # ── E6. 협력사 계획현황 화면이 그 값을 보는가 (API 레벨) ──────────
    dict(kind="S", name="[전구간] E6 협력사 계획현황 — 화면이 소요를 읽는가", method="GET",
         path=lambda ctx: f"/api/partner/planstatus?wc={ctx.get('e_wc','')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("e_wc"),
         check=lambda res, ctx: (
             len(_rows(res)) > 0,
             f"업체 {ctx.get('e_wc')} · {len(_rows(res))}행" if _rows(res)
             else f"★업체 {ctx.get('e_wc')} 계획이 0행 — ⑤는 있는데 화면이 못 읽는다")),

    # ── E7. ★거래명세서 요청수량 — 발행분 이중차감이 없는가 ──────────
    #    2026-08-31 실사용 버그. 발행분은 set_input_req→iset_stk 로 이미 done 에 들어가는데
    #    req 에서 또 빼서 요청수량이 0 이 됐다 → 중복 발행이 났다.
    dict(kind="S", name="[전구간] E7 ★거래명세서 — 요청수량 이중차감이 없는가", method="GET",
         path=lambda ctx: f"/api/partner/deliv420?cust={ctx.get('e_wc','')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("e_wc"),
         check=lambda res, ctx: _e7_req(res, ctx)),

    # ── E8. 세트제외(공용품) 행이 맨 위에 오는가 ─────────────────────
    #    레거시와 같은 배치. 2026-08-31 신설분의 회귀 방지.
    dict(kind="S", name="[전구간] E8 거래명세서 — 세트제외가 맨 위에 오는가", method="GET",
         path=lambda ctx: f"/api/partner/deliv420?cust={ctx.get('e_wc','')}",
         as_="super", expect=200, skip_if=lambda ctx: not ctx.get("e_wc"),
         check=lambda res, ctx: _e8_setexc(res, ctx)),

    # ── E9. 자재입고 화면이 계획을 읽는가 (발주→입고 구간) ───────────
    # ★파라미터는 `base_ymd`+`days`(기준일 + 영업일수)다. `ymd_from/to` 가 아니다 —
    #   2026-09-01 첫 실행에서 400 "기준일자가 필요합니다" 로 걸렸다(케이스 오류였다).
    dict(kind="S", name="[전구간] E9 자재입고진행현황 — 계획이 보이는가", method="GET",
         path=lambda ctx: f"/api/matinput/list?base_ymd={YMD}&days=4&gubun=all",
         as_="super", expect=200,
         check=lambda res, ctx: (
             True, f"{len(_rows(res))}행 (0행이면 해당 기간 입고계획 없음 — 결함 아님)")),

    # ── E10. ★★업체별 자재계획 대사 — 레거시와 얼마나 맞는가 ─────────
    #    대표 지시(2026-09-01): "자재계획쪽은 업체별로 계획을 분석해보면 될 거 같네".
    #    자재 단위로만 보면 어느 협력사가 틀어졌는지 안 보인다. 업체별로 먼저 갈라
    #    문제 협력사를 특정하고, 그 안에서만 자재를 판다.
    #    ★용접봉(RAC*)은 공정 분리라 설계상 차이 — 제외하고 센다(CLAUDE.md §1-10).
    dict(kind="S", name="[전구간] E10 ★★업체별 자재계획 — 레거시와 대사", method="POST",
         path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             WITH W AS (SELECT LTRIM(RTRIM(mat_work_center_code)) wc,
                               LTRIM(RTRIM(mat_code)) mat, SUM(CAST(part_plan_qty AS float)) q
                          FROM nx.plan_part_mat WITH(NOLOCK)
                         WHERE ISNULL(mat_work_center_code,'')<>''
                           AND LTRIM(RTRIM(mat_code)) NOT LIKE 'RAC%'
                         GROUP BY LTRIM(RTRIM(mat_work_center_code)), LTRIM(RTRIM(mat_code))),
                  L AS (SELECT LTRIM(RTRIM(MAT_WORK_CENTER_CODE)) wc,
                               LTRIM(RTRIM(MAT_CODE)) mat, SUM(CAST(PART_PLAN_QTY AS float)) q
                          FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT WITH(NOLOCK)
                         WHERE ISNULL(MAT_WORK_CENTER_CODE,'')<>''
                           AND LTRIM(RTRIM(MAT_CODE)) NOT LIKE 'RAC%'
                         GROUP BY LTRIM(RTRIM(MAT_WORK_CENTER_CODE)), LTRIM(RTRIM(MAT_CODE))),
                  J AS (SELECT ISNULL(w.wc,l.wc) wc, ISNULL(w.mat,l.mat) mat,
                               ISNULL(w.q,0) wq, ISNULL(l.q,0) lq
                          FROM W w FULL OUTER JOIN L l ON l.wc=w.wc AND l.mat=w.mat)
             SELECT COUNT(DISTINCT wc), COUNT(*),
                    SUM(CASE WHEN ABS(wq-lq)>0.5 THEN 1 ELSE 0 END),
                    COUNT(DISTINCT CASE WHEN ABS(wq-lq)>0.5 THEN wc END),
                    SUM(CASE WHEN wq>lq+0.5 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN lq>wq+0.5 THEN 1 ELSE 0 END)
               FROM J""", "args": []},
         check=lambda res, ctx: _e10_vendor_diff(res, ctx)),

    # ── E11. 차이 큰 업체 TOP — 내일 아침 어디부터 볼지 ──────────────
    dict(kind="S", name="[전구간] E11 차이 큰 업체 TOP10 — 어디부터 볼까", method="POST",
         path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             WITH W AS (SELECT LTRIM(RTRIM(mat_work_center_code)) wc,
                               LTRIM(RTRIM(mat_code)) mat, SUM(CAST(part_plan_qty AS float)) q
                          FROM nx.plan_part_mat WITH(NOLOCK)
                         WHERE ISNULL(mat_work_center_code,'')<>''
                           AND LTRIM(RTRIM(mat_code)) NOT LIKE 'RAC%'
                         GROUP BY LTRIM(RTRIM(mat_work_center_code)), LTRIM(RTRIM(mat_code))),
                  L AS (SELECT LTRIM(RTRIM(MAT_WORK_CENTER_CODE)) wc,
                               LTRIM(RTRIM(MAT_CODE)) mat, SUM(CAST(PART_PLAN_QTY AS float)) q
                          FROM PARTNER_ERP.dbo.PR_T_PLAN_PART_MAT WITH(NOLOCK)
                         WHERE ISNULL(MAT_WORK_CENTER_CODE,'')<>''
                           AND LTRIM(RTRIM(MAT_CODE)) NOT LIKE 'RAC%'
                         GROUP BY LTRIM(RTRIM(MAT_WORK_CENTER_CODE)), LTRIM(RTRIM(MAT_CODE))),
                  J AS (SELECT ISNULL(w.wc,l.wc) wc, ISNULL(w.mat,l.mat) mat,
                               ISNULL(w.q,0) wq, ISNULL(l.q,0) lq
                          FROM W w FULL OUTER JOIN L l ON l.wc=w.wc AND l.mat=w.mat)
             SELECT TOP 10 j.wc, ISNULL(RTRIM(c.CUST_DESC),'') nm,
                    COUNT(*) n_mat, SUM(CASE WHEN ABS(wq-lq)>0.5 THEN 1 ELSE 0 END) n_diff,
                    SUM(wq-lq) qdiff
               FROM J j LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON RTRIM(c.CUST_CODE)=j.wc
              GROUP BY j.wc, ISNULL(RTRIM(c.CUST_DESC),'')
             HAVING SUM(CASE WHEN ABS(wq-lq)>0.5 THEN 1 ELSE 0 END) > 0
              ORDER BY SUM(CASE WHEN ABS(wq-lq)>0.5 THEN 1 ELSE 0 END) DESC""", "args": []},
         check=lambda res, ctx: _e11_top(res, ctx)),

    # ── E12. ★★작업처 오버라이드가 낡지 않았는가 (E10 불일치의 실제 원인) ──
    #    2026-09-01 최초 발견 경위:
    #      E10 이 "미래정밀(2096) −96,768 / 케이비(2266) +96,768" 을 잡았다.
    #      수량 합계는 정확히 일치하고 **업체 배정만 뒤바뀌어** 있었다.
    #      추적하니 소요의 작업처는 BOM 이 아니라 `nx.routing_edge.wc` 에서 온다
    #      (planrev._step7_sql: ov_wc = ISNULL(routing_edge.wc, 마스터)).
    #      `wc = COALESCE(wc_user, wc_live)` 이고 `wc_live` 는 `nx.item` 에서 시드되는데,
    #      **시드 이후 마스터가 바뀌면 routing_edge 가 옛 업체를 계속 물고 있다.**
    #      실측: nx.item 은 라이브와 불일치 0(최신)인데 wc_live 는 39행이 stale.
    #      ⟹ `POST /api/routing/sync` 한 번이면 해소된다.
    #
    #    ★이건 "계획이 틀렸다"로 보이지만 실제로는 **마스터 변경이 반영 안 된 것**이다.
    #      업체가 바뀌면 발주가 엉뚱한 협력사로 나가므로 조용히 두면 안 된다.
    dict(kind="S", name="[전구간] E12 ★작업처 오버라이드(routing_edge)가 최신인가",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             SELECT (SELECT COUNT(*) FROM nx.routing_edge WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.routing_edge re WITH(NOLOCK)
                       JOIN nx.item it WITH(NOLOCK)
                         ON UPPER(LTRIM(RTRIM(it.item_code)))=re.child_item
                      WHERE ISNULL(RTRIM(re.wc_live),'') <>
                            CASE WHEN RTRIM(ISNULL(it.work_code,''))>'' THEN RTRIM(it.work_code)
                                 ELSE RTRIM(ISNULL(it.in_cust,'')) END),
                    (SELECT COUNT(*) FROM nx.routing_edge WITH(NOLOCK)
                      WHERE ISNULL(RTRIM(wc_user),'')<>'')""", "args": []},
         check=lambda res, ctx: _e12_routing(res, ctx)),

    # ── E13. 협력사 입고 → 재고 반영 (받은 것이 재고가 되는가) ────────
    #    앞 구간(계획→발주→명세서)과 뒷 구간(재고→생산→출하)을 잇는 이음매.
    #    ★파생 위치 = `set_stock_maint.derived_flag` + `nx.PU_T_SET_MAT_STOCK` 이다.
    #      2026-09-01 첫 케이스는 `stock_ledger.STOCK_POINT='S'` 를 봤는데 그런 값은 없다
    #      (실측 분포: MAT 172,683 · RDY 19 · ASY 7 · PRD 1). 세트는 별도 재고 계열이다.
    dict(kind="S", name="[전구간] E13 세트입고 → 재고 파생이 이어지는가",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             SELECT (SELECT COUNT(*) FROM nx.set_stock_maint WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.set_stock_maint WITH(NOLOCK)
                      WHERE ISNULL(RTRIM(derived_flag),'')='1'),
                    (SELECT COUNT(DISTINCT sheet_no) FROM nx.set_stock_maint WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.PU_T_SET_MAT_STOCK WITH(NOLOCK))""",
               "args": []},
         check=lambda res, ctx: _e13_setin(res, ctx)),

    # ── E14. 재고 3곳 정합 — 원장·수불장·재고가 같은 값인가 ───────────
    #    [F] 케이스는 '쓸 때 3곳이 같이 움직이는가'를 본다.
    #    여기서는 **지금 이 순간 이미 쌓여 있는 데이터**가 정합한지를 본다.
    dict(kind="S", name="[전구간] E14 ★재고 3곳(원장·수불장·재고) 정합",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
    #    ★음수재고는 **레거시에도 있는 것**과 **웹에서만 생긴 것**을 갈라야 한다.
    #      2026-09-01 실측: 2행 중 5210A22409A(−17,279)는 레거시에도 그대로 있고
    #      (담당자 백플러시 소비로 원래부터 음수), AJR77144307-STS(−4)만 웹에서 생겼다.
    #      전자를 결함으로 세면 고칠 수 없는 FAIL 이 영구히 남아 하네스를 못 믿게 된다.
         body={"sql": """
             SELECT (SELECT COUNT(*) FROM nx.stock_ledger WITH(NOLOCK) WHERE STOCK_POINT='MAT'),
                    (SELECT COUNT(*) FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                      WHERE CAST(ISNULL(STOCK_QTY,0) AS float) < 0),
                    (SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH w WITH(NOLOCK)
                      WHERE CAST(ISNULL(w.STOCK_QTY,0) AS float) < 0
                        AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PU_T_MAT_STOCK_WH l WITH(NOLOCK)
                                        WHERE RTRIM(l.MAT_CODE)=RTRIM(w.MAT_CODE)
                                          AND ISNULL(RTRIM(l.GAGONG_PROC_CODE),'')
                                              =ISNULL(RTRIM(w.GAGONG_PROC_CODE),'')
                                          AND CAST(ISNULL(l.STOCK_QTY,0) AS float) < 0))""", "args": []},
         check=lambda res, ctx: _e14_stock3(res, ctx)),

    # ── E14b. ★재고 버킷이 창고당 1행인가 (유령행 재발 방지) ─────────
    #    2026-09-01 E14 가 음수재고를 잡아 추적하다 발견한 진짜 버그:
    #      자재재고 버킷키의 CUST_CODE 는 **창고 소유주 'Z99990' 고정**인데
    #      (라이브 7,762행 전부 Z99990), stock_update/delete 가 원장의 거래처(매입처)를
    #      버킷키로 써서 UPDATE 가 기존 행을 못 찾고 **새 행을 INSERT** 했다.
    #        AJR77144307-STS: [Z99990·IS0001=92] + [2005·IS0001=**-4**]
    #      → 같은 창고에 2행. 재고조회는 합을 보므로 값이 조용히 틀어진다.
    #    수정 = stock.py `_mat_mirror_edit` 에서 버킷키를 Z99990 으로 일원화.
    dict(kind="S", name="[전구간] E14b ★재고 버킷이 창고당 1행인가",
         method="POST", path="/api/_flow/sql", as_="super", expect=200,
         body={"sql": """
             SELECT (SELECT COUNT(*) FROM (
                       SELECT RTRIM(MAT_CODE) m, ISNULL(RTRIM(GAGONG_PROC_CODE),'') g
                         FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                        GROUP BY RTRIM(MAT_CODE), ISNULL(RTRIM(GAGONG_PROC_CODE),'')
                       HAVING COUNT(*) > 1) t),
                    (SELECT COUNT(DISTINCT ISNULL(RTRIM(CUST_CODE),''))
                       FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)),
                    (SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                      WHERE ISNULL(RTRIM(CUST_CODE),'') <> 'Z99990')""", "args": []},
         check=lambda res, ctx: _e14b_bucket(res, ctx)),

    # ── E15. 마감이 그 재고를 평가하는가 (파이프라인의 종점) ──────────
    dict(kind="S", name="[전구간] E15 마감 — 수불장이 값을 내는가", method="GET",
         path=lambda ctx: f"/api/close/ledger?domain=MAT&d_from={_ym_first()}&d_to={YMD}",
         as_="super", expect=200,
         check=lambda res, ctx: _e15_close(res, ctx)),
]


# ── E 그룹 판정 함수 ──────────────────────────────────────────────────
def _ym_first():
    """이번 달 1일 YYMMDD."""
    import datetime as _d
    t = _d.date.today()
    return t.replace(day=1).strftime("%y%m%d")


def _e2_steps(res, ctx):
    """단계 로그 — 어느 단계가 언제 돌았는지 사람이 읽을 수 있게."""
    steps = (res or {}).get("steps") or {}
    if not steps:
        return True, "단계 로그 없음 — 아직 검토본으로 편성한 적이 없다(결함 아님)"
    lab = {"M": "①모델", "H": "②확정", "L": "③라인시간",
           "I": "④품목", "K": "④파트별", "T": "⑤자재소요", "S": "⑥협력사"}
    seen = []
    for k, v in steps.items():
        if not isinstance(v, dict):
            continue
        seen.append(f"{lab.get(k, k)}={v.get('status', '?')}"
                    f"({v.get('row_count') if v.get('row_count') is not None else '-'}행)")
    bad = [k for k, v in steps.items() if isinstance(v, dict) and v.get("status") == "ERR"]
    return (not bad), (" · ".join(seen) if not bad
                       else f"★실패단계 {bad} — {' · '.join(seen)}")


def _e3_part(res, ctx):
    """④단계가 실제로 완료된 적이 있는가."""
    rows = _rows(res)
    if not rows:
        return True, "편성 로그 없음 — 검토본 미실행(결함 아님)"
    ks = [r for r in rows if str((r.get("job_code") if isinstance(r, dict) else "")).strip() in ("K", "T")]
    if not ks:
        return True, f"로그 {len(rows)}건 · ④⑤ 기록 없음"
    ok = [r for r in ks if str(r.get("status", "")).strip() == "OK"]
    return (len(ok) > 0), (f"④⑤ 실행 {len(ks)}건 중 성공 {len(ok)}건"
                           if ok else "★④⑤ 가 한 번도 성공한 적이 없다")


def _e4_link(res, ctx):
    """④ → ⑤ 연결. **레거시 대비**로 본다.

       ★파트별계획을 안 거치는 제번(WO=수주·직납품 등)은 레거시에도 있다 —
         절대값 0 을 요구하면 정상 구조를 결함으로 오판한다(2026-09-01 실측).
         레거시와의 **차이**가 벌어질 때만 우리 편성이 틀어진 것이다."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패 — 산출 테이블을 못 읽었다"
    part_wo, mat_wo, web_orphan, leg_orphan = (int(rows[0][i] or 0) for i in range(4))
    if part_wo == 0:
        return True, "④ 산출이 비어 있다 — 아직 편성 전(결함 아님)"
    d = web_orphan - leg_orphan
    tol = max(50, int(leg_orphan * 0.05))          # 레거시 대비 5% 또는 50행
    tail = (f"④ {part_wo:,}제번 → ⑤ {mat_wo:,}제번 · "
            f"파트별外 소요 웹 {web_orphan:,} / 레거시 {leg_orphan:,} ({d:+,})")
    if abs(d) <= tol:
        return True, tail + "  = 레거시와 같은 구조(수주·직납품 계열)"
    return False, ("★" + tail + f"  — 레거시와 {d:+,}행 차이(허용 ±{tol:,}). "
                   "우리 편성만 제번이 남거나 빠졌다")


def _e10_vendor_diff(res, ctx):
    """업체×자재 단위로 레거시와 대사. **어느 업체가 틀어졌는지**가 핵심 산출물."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    nwc, npair, ndiff, nwc_diff, n_over, n_short = (int(rows[0][i] or 0) for i in range(6))
    if npair == 0:
        return True, "⑤ 산출이 비어 있다 — 아직 편성 전(결함 아님)"
    ctx["e10_ndiff"] = ndiff
    pct = ndiff * 100.0 / npair
    tail = (f"업체 {nwc}곳 · 업체×자재 {npair:,}쌍 · 불일치 {ndiff:,}쌍({pct:.2f}%) "
            f"· 문제업체 {nwc_diff}곳 · 과다 {n_over:,} / 부족 {n_short:,}")
    # 어제(2026-08-31) 정합 후 기준선 = 부족 18 · 과다 0. 크게 벌어지면 회귀다.
    return (ndiff <= 200), (tail if ndiff <= 200
                            else "★" + tail + "  — 어제 기준선(부족18·과다0) 대비 회귀 의심")


def _e13_setin(res, ctx):
    """협력사에게 받은 세트가 재고로 파생되는가.
       파생 = set_stock_maint.derived_flag='1' + nx.PU_T_SET_MAT_STOCK 잔액."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    n_in, n_drv, n_sheet, n_stk = (int(rows[0][i] or 0) for i in range(4))
    if n_in == 0:
        return True, "세트입고 없음 — 아직 받은 것이 없다(결함 아님)"
    pct = n_drv * 100.0 / n_in
    tail = (f"세트입고 {n_in:,}건({n_sheet:,}송장) · 파생완료 {n_drv:,}건({pct:.1f}%) "
            f"· 세트재고 {n_stk:,}행")
    if n_drv == 0:
        return False, f"★입고 {n_in:,}건인데 파생 0건 — 받았는데 재고가 안 늘었다"
    if n_stk == 0:
        return False, f"★{tail} — 파생 표시는 됐는데 세트재고가 비어 있다"
    return True, tail


def _e14_stock3(res, ctx):
    """원장·수불장·재고 3곳이 다 살아 있고 음수재고가 없는가."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    n_led, n_maint, n_wh, n_neg, n_neg_web = (int(rows[0][i] or 0) for i in range(5))
    empty = [n for n, v in (("원장", n_led), ("수불장", n_maint), ("재고", n_wh)) if v == 0]
    if empty:
        return False, f"★{'/'.join(empty)} 가 비어 있다 — 3곳 정합을 잴 수 없다"
    tail = f"원장(MAT) {n_led:,} · 수불장 {n_maint:,} · 재고 {n_wh:,}"
    if n_neg == 0:
        return True, tail + " · 음수재고 0"
    # 레거시에도 있는 음수는 우리가 만든 것이 아니다 — 참고로만 알린다.
    n_legacy = n_neg - n_neg_web
    if n_neg_web == 0:
        return True, (tail + f" · 음수재고 {n_neg}행(전부 레거시에도 있음 — 기존 데이터)")
    return False, (f"★{tail} · **웹에서 생긴 음수재고 {n_neg_web}행**"
                   f"(레거시 유래 {n_legacy}행은 제외) — 음수차단 규칙을 우회한 경로가 있다")


def _e14b_bucket(res, ctx):
    """자재재고 버킷이 (자재,창고)당 1행인가 + CUST_CODE 가 Z99990 단일인가."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    dup, n_cc, n_notz = (int(rows[0][i] or 0) for i in range(3))
    if dup == 0 and n_notz == 0:
        return True, f"중복 버킷 0 · CUST_CODE {n_cc}종(전부 Z99990)"
    msg = []
    if dup:
        msg.append(f"★(자재,창고) 중복 {dup}건 — 같은 창고에 2행, 재고 합계가 틀어진다")
    if n_notz:
        msg.append(f"★CUST_CODE≠Z99990 {n_notz}행 — 버킷키에 거래처가 섞였다")
    return False, " / ".join(msg) + "  조치: stock.py _mat_mirror_edit 버킷키 확인 + 유령행 정리"


def _e15_close(res, ctx):
    """마감(수불장)이 실제로 값을 내는가 = 파이프라인 종점이 살아 있는가."""
    rows = _rows(res)
    if not rows:
        return True, "수불장 행 없음 — 해당 기간 거래 없음(결함 아님)"
    def _n(r, *ks):
        for k in ks:
            if isinstance(r, dict) and r.get(k) is not None:
                try:
                    return float(r[k] or 0)
                except Exception:
                    return 0.0
        return 0.0
    ea = sum(_n(r, "ea", "end_amt", "ta") for r in rows)
    return True, f"자재 수불장 {len(rows):,}행 · 기말금액 {ea:,.0f}"


def _e12_routing(res, ctx):
    """routing_edge 의 라이브 시드(wc_live)가 마스터를 따라가고 있는가.

       ★사용자 편집(wc_user)은 **의도된 오버라이드**라 stale 이 아니다 — 세지 않는다.
         stale 은 '아무도 손대지 않았는데 옛 업체가 남아 있는' 것이다."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    total, stale, edited = (int(rows[0][i] or 0) for i in range(3))
    if total == 0:
        return True, "routing_edge 비어 있음 — 아직 시드 전"
    tail = f"엣지 {total:,}행 · 사용자편집 {edited:,}행 · 라이브시드 stale {stale:,}행"
    if stale == 0:
        return True, tail + "  = 마스터와 동기 상태"
    return False, ("★" + tail + "  — 마스터가 바뀌었는데 반영이 안 됐다. "
                   "이 자재는 **엉뚱한 협력사로 발주가 나간다**. "
                   "조치: POST /api/routing/sync 실행")


def _e11_top(res, ctx):
    """차이 큰 업체 TOP10 — 내일 아침 어디부터 볼지 그대로 읽히게 출력한다."""
    # ★조회 자체가 거부되면 '차이 없음'이 아니다. 2026-09-01 실측: SQL 가드에 막혀
    #   rows 가 비었는데 "전 업체 일치"로 PASS 가 났다. 거짓 PASS 는 진짜 실패보다 나쁘다.
    if isinstance(res, dict) and res.get("ok") is False:
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return True, "차이나는 업체 없음 — 전 업체 레거시와 일치"
    out = []
    for r in rows[:10]:
        wc, nm, n_mat, n_diff, qdiff = r[0], r[1], int(r[2] or 0), int(r[3] or 0), float(r[4] or 0)
        out.append(f"{wc}({nm or '?'}) 불일치 {n_diff}/{n_mat}쌍 수량차 {qdiff:+,.0f}")
    return True, "차이 업체 — " + " · ".join(out)


def _e5_vendor(res, ctx):
    """업체별로 소요가 갈라지는가. 작업처 없는 행은 **발주를 낼 수 없는 행**이다."""
    if _refused(res):
        return False, f"★조회 거부 — {res.get('detail')}"
    rows = _rows(res)
    if not rows:
        return False, "★조회 실패"
    nvendor, noblank, total = (int(rows[0][i] or 0) for i in range(3))
    if total == 0:
        return True, "⑤ 산출이 비어 있다 — 아직 편성 전(결함 아님)"
    pct = noblank * 100.0 / total
    return (pct < 5.0), (f"업체 {nvendor}곳 · {total:,}행 · 작업처없음 {noblank:,}행({pct:.1f}%)"
                         + ("" if pct < 5.0 else "  ★작업처 미매핑이 많다 — 이 행은 발주가 안 나간다"))


def _e7_req(res, ctx):
    """요청수량 = 계획 − 완료 여야 한다. 발행분을 또 빼면 음수이거나 0 이 된다.

       ★판정: 계획>완료 인데 요청이 0 인 행이 다수면 이중차감을 의심한다.
         (정상적으로 0 인 행도 있으므로 '전부 0' 일 때만 결함으로 본다)"""
    rows = _rows(res)
    if not rows:
        return True, "행 없음 — 해당 업체 계획 없음"
    def _f(r, *ks):
        for k in ks:
            if r.get(k) is not None:
                try:
                    return float(r.get(k) or 0)
                except Exception:
                    return 0.0
        return 0.0
    neg = [r for r in rows if _f(r, "req", "req_qty") < 0]
    live = [r for r in rows if _f(r, "plan", "plan_qty") > _f(r, "done", "fin_qty")]
    zero = [r for r in live if _f(r, "req", "req_qty") <= 0]
    if neg:
        return False, f"★요청수량 음수 {len(neg)}행 — 이중차감"
    if live and len(zero) == len(live):
        return False, (f"★잔여가 있는 {len(live)}행 전부 요청수량 0 — 이중차감 의심 "
                       f"(발행분을 done 과 req 양쪽에서 빼고 있다)")
    return True, (f"{len(rows)}행 · 잔여있는 행 {len(live)} 중 요청0 {len(zero)}행 "
                  f"(음수 0 · 전부0 아님 = 정상)")


def _e8_setexc(res, ctx):
    """세트제외(공용품)는 레거시처럼 맨 위에 모여야 한다."""
    rows = _rows(res)
    se = [i for i, r in enumerate(rows) if r.get("setexc")]
    if not se:
        return True, f"{len(rows)}행 · 세트제외 없음(이 업체는 해당 없음)"
    top = list(range(len(se)))
    return (se == top), (f"세트제외 {len(se)}행 · 맨 위 배치 {'정상' if se == top else '★어긋남 %s' % se[:6]}"
                         f" (전체 {len(rows)}행)")


# ★E 그룹은 **CASES 앞**에 놓는다 — 무거운 조회를 먼저(§9 순서 규칙).
CASES = E_CASES + CASES
