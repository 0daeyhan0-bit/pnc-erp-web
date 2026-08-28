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
    return lambda ctx: {"screen": screen, "user": "flowverify",
                        "rows": [{"MAINT_YMD": YMD if ymd is None else ymd,
                                  "MAT_CODE": (ctx["mat"] if mat is None else mat), "qty": qty}]}


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
