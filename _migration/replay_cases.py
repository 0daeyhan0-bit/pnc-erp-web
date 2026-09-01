# -*- coding: utf-8 -*-
"""재생 케이스 — 레거시 거래를 **우리 화면 API 로 다시 입력**한다 (TestBed 편입).

대표 지시(2026-09-01)
  "꼭 프로그램을 사용해서 입력을 해야지 문제점들이 나올거야. **데이터만 밀어 넣지마.**"
  "그 재생기는 TEST BED 에 같이 넣는건 어때?"

★하드룰 — 이 파일은 **INSERT/UPDATE 를 한 줄도 하지 않는다.**
  레거시에서 거래를 **읽어** TestBed 케이스(dict)로 바꿀 뿐이고,
  실제 입력은 하네스가 **HTTP 로 우리 라우터를 호출**해서 한다.
  직접 INSERT 는 게이트·유효성·파생계산(원장·수불장·재고)을 전부 건너뛰므로
  **아무것도 검증되지 않는다.** 그게 "데이터 복사"와 "프로그램 입력"의 차이다.

★시간순 — 실제 업무는 자재입고 → 키팅 → 생산 → 출하 순으로 재고가 흐른다.
  유형별로 몰아 넣으면 앞 단계가 없어서 뒤 단계가 게이트에 막힌다(그건 우리 결함이 아니다).
  그래서 **전 유형을 시각으로 정렬해 한 줄로 섞어** 넣는다.

★모르는 것은 넣지 않는다 — 매핑이 확실한 거래만 케이스로 만들고,
  나머지는 **스킵하고 건수를 보고**한다. 추측으로 매핑하면 틀린 결과가 나오고,
  그 틀린 결과가 우리 프로그램 탓으로 보인다(그게 제일 나쁘다).

환경변수
  REPLAY_YMD    재생할 일자(YYMMDD) — 이게 있어야 케이스가 붙는다
  REPLAY_LIMIT  건수 제한(처음엔 작게)
  REPLAY_SINCE  'YYYY-MM-DD HH:MM:SS' 이후 입력분만 = **nx 에 아직 없는 구간**만 재생

어디에 대고 도나
  `_migration/flow_server.py`(롤백 모드 = commit 무력화) → **오염 0**.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))

# 대표 확정 10종 (2026-08-31 실측 · 생산+출하 거래건수 상위 완제품) = 고정 대조군
FIXED = ["MJU63357501", "AJJ75838625", "AJR73965506", "AJR73965505", "AJR73965606",
         "AJR73965607", "AJR30004702", "AJR30077403", "AJR76582506", "AJR76582505"]

LIMIT = int(os.environ.get("REPLAY_LIMIT", "0") or 0)
SINCE = os.environ.get("REPLAY_SINCE", "")
AUTO_TOP = int(os.environ.get("REPLAY_AUTO_TOP", "10") or 0)   # 오늘 도는 품번 자동 추가 수

_ITEMS = {}


def items_for(ymd):
    """재생 대상 = **고정 10종 + 그날 실제로 도는 상위 품번**(대표 확정 2026-09-01 'C').

       왜 — 고정 10종은 *어제* 많이 돈 품번이다. 오늘 그게 안 돌면 재생할 게 없다
       (실측: 09-01 08:00 기준 10종 거래 0행, 대신 AJR30133602 계열이 돌고 있었다).
       고정분은 **대조군**으로 남기고, 오늘 흐르는 것을 따라가야 재생이 놀지 않는다.
    """
    if ymd in _ITEMS:
        return _ITEMS[ymd]
    got = list(FIXED)
    if AUTO_TOP > 0:
        try:
            cur = _cur()
            cur.execute("""SELECT TOP (%d) x.code FROM (
                             SELECT LTRIM(RTRIM(ITEM_CODE)) code
                               FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT WHERE MAINT_YMD=?
                             UNION ALL
                             SELECT LTRIM(RTRIM(ITEM_CODE))
                               FROM PARTNER_ERP.dbo.PU_T_READY_STOCK_MAINT WHERE MAINT_YMD=?
                             UNION ALL
                             SELECT LTRIM(RTRIM(ITEM_CODE))
                               FROM PARTNER_ERP.dbo.PR_T_PROD_DTL WHERE PROD_YMD=?
                           ) x WHERE x.code<>'' GROUP BY x.code
                           ORDER BY COUNT(*) DESC""" % AUTO_TOP, ymd, ymd, ymd)
            for (cd,) in cur.fetchall():
                if cd not in got:
                    got.append(cd)
        except Exception as e:
            print("  ★재생: 오늘 품번 자동수집 실패 - %s" % str(e)[:100])
    _ITEMS[ymd] = got
    return got

# ══════════════════════════════════════════════════════════════════════
# ★★★재생 대상 판별 — "사람이 입력한 것"만 넣는다 (2026-08-31 실측으로 확정)
#
#   레거시 거래에는 두 종류가 섞여 있다.
#     ① 사람이 화면에서 입력한 것        → **재생 대상**
#     ② 그 입력 때문에 시스템이 자동 생성한 것 → **재생하면 안 된다**
#
#   ②를 재생하면 **이중 계상**이 된다. 우리 시스템도 ①을 받으면 ②를 스스로 만들기 때문이다.
#   그러니 ②는 입력이 아니라 **채점 기준**이다 —
#   "우리가 ①을 넣었을 때 ②에 해당하는 값이 나오는가" 가 이 파일럿의 진짜 질문이다.
#
#   INSERT_WINDOW(레거시 화면명)로 갈랐다. 260831 실측:
#     [자재 PU_T_STOCK_MAINT]
#       tag 9  w_pu_stock_057    75행  +194,370  발주입고        → ①
#       tag C  w_pu_stock_057_2 119행   +4,281   자재개별일괄입고 → ①
#       tag B  w_pr_input_460_new 2091행 -75,975 ★키팅 화면의 자동 자재차감 → ②
#       tag P  w_pr_input_260     46행           ★생산실적 파생          → ②
#       tag S/5/4 …                              세트·사급·기타(축이 달라 보류)
#     [준비 PU_T_READY_STOCK_MAINT]
#       tag 1  w_pr_input_460_new 384행  +8,325  키팅 확인 → ①
#       tag 2  w_pr_input_460_new  73행    -891  키팅 취소 → ①
#       tag A  w_pr_input_520/260 1035행 -14,760 ★준비재고 소진(생산 부산물) → ②
#     [완성 SA_T_STOCK_MAINT]
#       tag J  w_pr_input_040    420행  -59,118  출하등록 → ①
#       tag P  w_pr_input_260/520 203행  +8,180  ★생산입고 → ②
#     [생산자재 PR_T_STOCK_MAINT_MAT]
#       tag 4  dw_t2 / w_pr_input_260 1357행     ★생산 자재소비 → ②
#
#   ※보류(①인지 ②인지 더 봐야 하는 것)는 스킵하고 건수를 보고한다. 추측 매핑 금지.
# ══════════════════════════════════════════════════════════════════════
MAT_TAG2SCREEN = {"9": "receipt", "C": "receipt"}     # ① 자재입고 계열
MAT_DERIVED = {"B", "P"}                              # ② 파생 — 재생 금지(채점 기준)
KIT_CONFIRM, KIT_CANCEL, KIT_DERIVED = "1", "2", "A"  # ①확인 ①취소 ②파생


def _inl(ymd):
    return ",".join("'" + x + "'" for x in items_for(ymd))


def _cur():
    from common import _conn                       # 라이브 = 읽기 전용 가드
    return _conn().cursor()


def _since(col):
    return (" AND %s >= '%s'" % (col, SINCE)) if SINCE else ""


def _hms(v):
    return str(v or "000000").replace(":", "")


# ── 유형별 수집 : (정렬키, 케이스dict) 목록 ────────────────────────────
def _mat(cur, ymd):
    """자재수불 — 매핑이 확실한 태그만. 나머지는 스킵하고 센다."""
    cur.execute("""SELECT MAINT_YMD, ISNULL(MAINT_TAG,''), LTRIM(RTRIM(MAT_CODE)),
                          MAINT_QTY, ISNULL(CUST_CODE,''), CONVERT(varchar(8), INSERT_DATETIME, 108)
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT
                    WHERE MAINT_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s"""
                % (_inl(ymd), _since("INSERT_DATETIME")), ymd)
    out, skipped, derived = [], {}, 0
    for (my, tag, mat, qty, cust, hms) in cur.fetchall():
        q = float(qty or 0)
        if q == 0 or not mat:
            continue
        tg = str(tag).strip()
        if tg in MAT_DERIVED:
            derived += 1          # ★파생 — 재생하면 이중계상. 채점 기준으로만 쓴다
            continue
        scr = MAT_TAG2SCREEN.get(tg)
        if not scr:
            skipped[tg or "(공백)"] = skipped.get(tg or "(공백)", 0) + 1
            continue
        row = {"MAINT_YMD": str(my or "").strip(), "MAT_CODE": mat, "qty": q}
        if cust:
            row["CUST_CODE"] = str(cust).strip()
        out.append((_hms(hms), dict(
            kind="F", name="재생①자재 %s %s %+g" % (scr, mat, q),
            method="POST", path="/api/stock/save",
            probe="원장MAT", delta=q, mirror=True,
            body={"screen": scr, "user": "replay", "rows": [row]})))
    return out, skipped, derived


def _kit(cur, ymd):
    """준비실적(키팅). 양수=확인 / 음수=취소 로 본다.
       ★이 부호 해석은 실측으로 확인해야 한다 — 첫 실행 결과를 보고 정정한다."""
    cur.execute("""SELECT MAINT_YMD, ISNULL(MAINT_TAG,''), LTRIM(RTRIM(ITEM_CODE)), WORK_ORDER, SPLIT_WORK_ORDER,
                          PROC_GUBUN, MAINT_QTY, CONVERT(varchar(8), INSERT_DATETIME, 108)
                     FROM PARTNER_ERP.dbo.PU_T_READY_STOCK_MAINT
                    WHERE MAINT_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s"""
                % (_inl(ymd), _since("INSERT_DATETIME")), ymd)
    out, derived = [], 0
    for (my, tag, item, wo, swo, gpc, qty, hms) in cur.fetchall():
        q = float(qty or 0)
        tg = str(tag or "").strip()
        if q == 0:
            continue
        if tg == KIT_DERIVED:
            derived += 1          # ★준비재고 소진 = 생산실적의 부산물. 재생 금지
            continue
        if tg not in (KIT_CONFIRM, KIT_CANCEL):
            continue
        path = "/api/kitting/cell-confirm" if tg == KIT_CONFIRM else "/api/kitting/cell-cancel"
        out.append((_hms(hms), dict(
            kind="F", name="재생②키팅 %s %+g" % (item, q),
            method="POST", path=path,
            probe="원장RDY", delta=q, mirror=False,
            body={"item": item, "wo": str(wo or "").strip(), "swo": str(swo or "").strip(),
                  "gpc": str(gpc or "").strip(), "ymd": str(my or "").strip(),
                  "qty": abs(q), "user": "replay"})))
    return out, derived


def _prod(cur, ymd):
    cur.execute("""SELECT WORK_ORDER, SPLIT_WORK_ORDER, LTRIM(RTRIM(ITEM_CODE)), PROD_YMD, PROD_HMS,
                          LINE_NO, PROD_QTY, WORK_CODE, PART_CODE, S_WORK_CODE, FINISH_FLAG
                     FROM PARTNER_ERP.dbo.PR_T_PROD_DTL
                    WHERE PROD_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)""" % _inl(ymd), ymd)
    out = []
    for (wo, swo, item, pymd, phms, line, qty, work, part, sw, fin) in cur.fetchall():
        q = int(float(qty or 0))
        if q == 0:
            continue
        out.append((_hms(phms), dict(
            kind="F", name="재생③생산 %s x%d" % (item, q),
            method="POST", path="/api/procreg/save",
            probe="공정실적수량", delta=q, mirror=False,
            body={"prod_ymd": str(pymd or "").strip(), "prod_hms": str(phms or "").strip(),
                  "item_code": item, "work_order": str(wo or "").strip(),
                  "split_work_order": str(swo or "").strip(), "line_no": str(line or "").strip(),
                  "part_code": str(part or "").strip(), "work_code": str(work or "").strip(),
                  "s_work_code": sw, "finish_flag": str(fin or "0").strip(),
                  "prod_qty": q, "user": "replay"})))
    return out


def _ship(cur, ymd):
    """출하등록(MAINT_TAG='J'). ★일자는 서버가 정한다(payload 에 일자가 없다) →
       **오늘 거래를 오늘 재생**하는 방식에서만 의미가 있다."""
    cur.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), WORK_ORDER, SPLIT_WORK_ORDER,
                          MAINT_QTY, REMARKS, CONVERT(varchar(8), INSERT_DATETIME, 108)
                     FROM PARTNER_ERP.dbo.SA_T_STOCK_MAINT
                    WHERE MAINT_YMD=? AND MAINT_TAG='J' AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s"""
                % (_inl(ymd), _since("INSERT_DATETIME")), ymd)
    out = []
    for (item, wo, swo, qty, rm, hms) in cur.fetchall():
        q = abs(float(qty or 0))
        if q == 0 or not str(wo or "").strip():
            continue                       # 제번 없으면 API 가 거부한다(필수)
        out.append((_hms(hms), dict(
            kind="F", name="재생④출하 %s x%g" % (item, q),
            method="POST", path="/api/lgsale/save",
            probe="원장ASY", delta=-q, mirror=False,
            body={"work_order": str(wo).strip(), "split_work_order": str(swo or "").strip(),
                  "item_code": item, "sale_qty": q,
                  "remarks": (str(rm or "").strip() or "재생")[:100]})))
    return out


def build_replay_cases(ymd):
    """레거시 거래 → TestBed 케이스 목록. 여기서 DB 를 쓰지 않는다(읽기만)."""
    try:
        cur = _cur()
        mats, skipped, mat_derived = _mat(cur, ymd)
        kits, kit_derived = _kit(cur, ymd)
        items = mats + kits + _prod(cur, ymd) + _ship(cur, ymd)
    except Exception as e:
        print("  ★재생: 레거시 조회 실패 - %s" % str(e)[:140])
        return []

    items.sort(key=lambda x: x[0])          # ★시각순 = 실제 업무 순서
    cases = [c for _, c in items]
    if LIMIT:
        cases = cases[:LIMIT]

    print("  재생 케이스 %d건 (%s · 10종 · 시각순%s)"
          % (len(cases), ymd, (" · SINCE %s" % SINCE) if SINCE else ""))
    print("     파생 제외 %d건 (자재 %d + 준비 %d) = 재생 금지, 채점 기준으로만 쓴다"
          % (mat_derived + kit_derived, mat_derived, kit_derived))
    if skipped:
        print("     ※자재수불 스킵 %d건 - 태그 매핑 미확정: %s"
              % (sum(skipped.values()),
                 ", ".join("tag %s×%d" % (k, v) for k, v in sorted(skipped.items(), key=lambda x: -x[1]))))
    return cases


def expected_totals(ymd):
    """레거시가 그날 만든 **순변화** = 우리가 내야 할 값(채점 기준).

       ★왜 순합인가 — 우리는 사람 입력(①)만 재생하지만, 그걸 받은 우리 시스템은
         파생(②)을 스스로 만든다. 그러므로 비교는 개별 행이 아니라 **원장 축의 순변화**다.
           예) 준비재고 = 키팅확인(+) + 키팅취소(-) + 생산소진(-) 을 다 더한 값.
       ★프로브 축(원장MAT/RDY/ASY/공정실적수량)에 맞춰 돌려준다.
       ★안 맞으면 그 자체가 발견이다 — 재생하지 못한 유형이 있다는 뜻이거나,
         우리 파생 계산이 레거시와 다르다는 뜻이다. 어느 쪽인지는 사람이 판단한다.
    """
    cur = _cur()
    inl = _inl(ymd)
    out = {}

    def one(sql):
        cur.execute(sql, ymd)
        return float(cur.fetchone()[0] or 0)

    # ★재생과 **같은 구간**을 세야 한다. SINCE 로 자르고 재생했으면 기준값도 그 구간이다.
    #   (2026-09-01 실측 교훈: 전체를 세고 일부만 재생해 놓고 "차이" 라고 읽으면 오진이다.)
    sc = _since("INSERT_DATETIME")
    out["원장RDY"] = one("""SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0)
                              FROM PARTNER_ERP.dbo.PU_T_READY_STOCK_MAINT
                             WHERE MAINT_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s""" % (inl, sc))
    out["원장MAT"] = one("""SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0)
                              FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT
                             WHERE MAINT_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s""" % (inl, sc))
    out["원장ASY"] = one("""SELECT ISNULL(SUM(CAST(MAINT_QTY AS float)),0)
                              FROM PARTNER_ERP.dbo.SA_T_STOCK_MAINT
                             WHERE MAINT_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)%s""" % (inl, sc))
    # ★생산실적에는 INSERT_DATETIME 이 없다(UPDATE_DATETIME·PROD_HMS 뿐) → 구간 절단 불가.
    #   재생도 같은 이유로 전량을 넣으므로 여기서도 전량을 센다(축이 어긋나지 않는다).
    out["공정실적수량"] = one("""SELECT ISNULL(SUM(CAST(PROD_QTY AS float)),0)
                              FROM PARTNER_ERP.dbo.PR_T_PROD_DTL
                             WHERE PROD_YMD=? AND LTRIM(RTRIM(ITEM_CODE)) IN (%s)""" % inl)
    return out
