# -*- coding: utf-8 -*-
"""마감관리 (시스템관리 > 마감관리) — 일/월 마감 실행·해제 + 현황.

설계 근거(기록):
  · nextgen-erp-close-settlement : 마감=잠금 · 일마감⊂월마감 · 해제는 권한자+로그 ·
                                   소급은 재개방이 아니라 당월 소급조정(조정전표는 열린 일자에만)
  · nextgen-erp-material-close   : "마감 시점에 스냅샷 생성 = 다음달 기초재고. 월마감·일마감 동일 개념."
  · STOCK_GATING_CLOSE_LOCK_RULES: 규칙B 마감된 기간 CRUD 금지

★재설계(2026-08-27): 자재 스냅샷은 **마감이 직접 전표에서 파생**한다(원설계 복귀).
  기초(직전 확정 스냅샷 · 최초는 레거시 월마감 시드) + 그 기간 이동을 이동평균 전개 → 확정.
  이전에는 nx.mat_stock_daily(임시본)에서 복사했다 → 중복 저장·원천이 임시라 폐기.
  ⟹ mat_stock_daily · 빌더 · 임시화면이 불필요해진다(은퇴 대상).

1단계 범위 = 자재(MAT) 월·일 (스냅샷 확정 + 잠금) + 전 도메인 잠금.
  생산(PRD)·영업(SAL) 스냅샷은 tag 파생식 규명 후 2단계 — 지금은 잠금만 가능.
"""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _nx_tx, _conn, _d6

router = APIRouter()

DOMAINS = {"MAT": "자재", "PRD": "생산", "SAL": "영업"}
SNAP_READY = ("MAT", "PRD", "SAL")   # 스냅샷 확정 가능 도메인(PRD·SAL = 2026-08-27 추가, C2)


def _norm(domain, ptype, period):
    d = str(domain or "").strip().upper()
    t = str(ptype or "").strip().upper()
    p = "".join(ch for ch in str(period or "") if ch.isdigit())
    if d not in DOMAINS:
        raise HTTPException(400, f"도메인은 {'/'.join(DOMAINS)} 중 하나여야 합니다.")
    if t not in ("D", "M"):
        raise HTTPException(400, "마감유형은 D(일) 또는 M(월)이어야 합니다.")
    if t == "D":
        if len(p) == 8:
            p = p[2:]
        if len(p) != 6:
            raise HTTPException(400, "일마감 기간은 YYMMDD 형식이어야 합니다.")
    else:
        if len(p) == 6:
            p = p[:4]
        if len(p) != 4:
            raise HTTPException(400, "월마감 기간은 YYMM 형식이어야 합니다.")
    return d, t, p


def _is_closed(cur, domain, ptype, period):
    cur.execute("""SELECT close_flag FROM nx.period_close
                   WHERE domain=? AND ptype=? AND period=?""", domain, ptype, period)
    r = cur.fetchone()
    return bool(r and r[0])


def _prev_period(ptype, period):
    """직전 기간(연쇄 가드용). 일=전일, 월=전월."""
    if ptype == "M":
        y, m = int(period[:2]), int(period[2:])
        m -= 1
        if m == 0:
            m = 12; y -= 1
        return f"{y:02d}{m:02d}"
    import datetime as _dt
    d = _dt.date(2000 + int(period[:2]), int(period[2:4]), int(period[4:])) - _dt.timedelta(days=1)
    return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"


# ===================== 현황 =====================
@router.get("/api/close/status")
def close_status():
    """도메인별 마감 현황 = 우리 잠금(nx.period_close) 기준 + 참고로 산출물 최신일.
       ★기존 /api/live/closestatus 는 레거시 임시테이블 MAX()를 '최종마감'으로 표시해 부정확
         (PU_T_MONTH_STOCK_WH_DAILY 는 조회할 때마다 TRUNCATE되는 작업테이블) — 이 엔드포인트가 정본."""
    cn = _nx(); cur = cn.cursor()
    try:
        rows = []
        for d, dnm in DOMAINS.items():
            for t, tnm in (("D", "일마감"), ("M", "월마감")):
                cur.execute("""SELECT TOP 1 period, close_user, close_dt FROM nx.period_close
                               WHERE domain=? AND ptype=? AND close_flag=1 ORDER BY period DESC""", d, t)
                r = cur.fetchone()
                rows.append({"domain": d, "domain_nm": dnm, "ptype": t, "ptype_nm": tnm,
                             "last": (r[0] if r else None), "user": (r[1] if r else None),
                             "dt": (str(r[2]) if r and r[2] else None),
                             "snap_ready": 1 if d in SNAP_READY else 0})
        cur.execute("SELECT MAX(ymd) FROM nx.mat_stock_daily")   # 참고표시용(은퇴 예정)
        mat_src = cur.fetchone()[0]
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')"); asof = cur.fetchone()[0]
        return {"rows": rows, "asof": asof, "mat_daily_max": mat_src, "domains": DOMAINS}
    finally:
        cn.close()


@router.get("/api/close/calendar")
def close_calendar(domain: str = Query("MAT"), ym: str = Query("")):
    """일자별 마감 캘린더(해당 월). 월마감돼 있으면 그 달 전 일자를 마감으로 본다(일마감 ⊂ 월마감)."""
    d, _t, y = _norm(domain, "M", ym or "0000")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT period FROM nx.period_close
                       WHERE domain=? AND ptype='D' AND close_flag=1 AND period LIKE ?""", d, y + "%")
        days = {r[0] for r in cur.fetchall()}
        return {"domain": d, "ym": y, "month_closed": 1 if _is_closed(cur, d, "M", y) else 0,
                "closed_days": sorted(days)}
    finally:
        cn.close()


# ===================== 자재 스냅샷 = f(전표)  ★재설계 2026-08-27 =====================
# 원설계 복귀([[nextgen-erp-material-close]]): "스냅샷 = f(원장) — 마감 시 그 기간 수불을 실거래에서
#   파생 → 확정. 언제든 재계산 대사 가능 → 드리프트 구조적 차단."
# 이전 구현은 nx.mat_stock_daily(임시본)에서 '복사'했다 → 같은 값이 두 곳에 존재하고 원천이 임시.
#   이제 마감이 직접 이동평균을 전개한다 ⟹ mat_stock_daily·빌더·임시화면 불필요.
#
# 이동평균 규칙(빌더 matclose_movavg_build.py 에서 이사 — 우리 버그 4건 수정 포함):
#   · 매입(PU_T_STOCK_MAINT tag 9·S + 도입 PU_T_STOCK_MAINT_C DIVISION='P' ×환율) = 평균단가 갱신
#     new_avg = (전일qty×전일avg + 매입amt) / (전일qty + 매입qty)
#   · 이동·반품·가공·출고·조정 = 현재 평균 불변 (net 만 반영)
#   · ★재고 ≤ 0 에서 매입 refill = 단가 리셋(잔재 폐기) — 마이너스재고 평균 폭발 방지
#   · 도입 수입은 외화 → ×EXCHANGE_RATE 로 KRW 환산
#   · 소모품(sgroup 99%)은 신규 진입 제외(기존 보유분은 유지)
#   · amt = qty × avg 강제
# ★소스 = 라이브 dbo (nx 미러는 sync 지연으로 stale — 기록 [[newerp-matclose-movavg]])

def _mat_consum(cur):
    """소모품 집합(신규 진입 제외용)."""
    # ★소스 = nx.item(정본). 종전엔 은퇴 대상 미러 nx.PR_M_ITEM 를 읽었다 —
    #   리더 이관(PR#66~75)이 끝난 뒤 새로 쓴 코드에 다시 들어온 회귀였다(2026-08-27).
    #   실측: 소모품 집합 226 = 226, 양쪽 차 0 ⟹ 값 변화 없음.
    cur.execute("SELECT item_code FROM PARTNER_ERP_TEST3.nx.item WHERE sgroup LIKE '99%'")
    return {str(r[0]).strip().upper() for r in cur.fetchall()}


# ★품번은 UPPER+TRIM 로 정규화한다. 테이블마다 표기가 달라(시드 '-F&T' vs 이동 '-f&t')
#   정규화 없이 dict 키를 만들면 SQL Server(대소문자 무구분) PK 와 충돌한다 — 2026-08-27 실제 발생.
def _mat_moves(cur, d_from, d_to):
    """[d_from, d_to] 일자별 자재 이동 → {ymd: {mat: {net,pos,neg,pq,pamt}}}. 소스=라이브 dbo."""
    out = {}

    def slot(y, m):
        return out.setdefault(y, {}).setdefault(
            m, {"net": 0.0, "pos": 0.0, "neg": 0.0, "pq": 0.0, "pamt": 0.0})

    cur.execute("""SELECT MAINT_YMD, UPPER(LTRIM(RTRIM(MAT_CODE))),
          SUM(CAST(MAINT_QTY AS float)),
          SUM(CASE WHEN MAINT_QTY>0 THEN CAST(MAINT_QTY AS float) ELSE 0 END),
          SUM(CASE WHEN MAINT_QTY<0 THEN -CAST(MAINT_QTY AS float) ELSE 0 END),
          SUM(CASE WHEN MAINT_TAG IN('9','S') THEN CAST(MAINT_QTY AS float) ELSE 0 END),
          SUM(CASE WHEN MAINT_TAG IN('9','S') THEN CAST(MAINT_AMT AS float) ELSE 0 END)
        FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT
        WHERE MAINT_YMD BETWEEN ? AND ? AND MAT_CODE IS NOT NULL
        GROUP BY MAINT_YMD, UPPER(LTRIM(RTRIM(MAT_CODE)))""", d_from, d_to)
    for y, m, net, pos, neg, pq, pamt in cur.fetchall():
        d = slot(y, m)
        d["net"] += net or 0; d["pos"] += pos or 0; d["neg"] += neg or 0
        d["pq"] += pq or 0;   d["pamt"] += pamt or 0

    # 도입: P=수입입고(매입, 외화→KRW) / 그 외(Q)=수출출고
    cur.execute("""SELECT MAINT_YMD, UPPER(LTRIM(RTRIM(MAT_CODE))), DIVISION,
          SUM(CAST(MAINT_QTY AS float)),
          SUM(CAST(MAINT_AMT AS float)*ISNULL(CAST(EXCHANGE_RATE AS float),1))
        FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C
        WHERE MAINT_YMD BETWEEN ? AND ? AND MAT_CODE IS NOT NULL
        GROUP BY MAINT_YMD, UPPER(LTRIM(RTRIM(MAT_CODE))), DIVISION""", d_from, d_to)
    for y, m, div, q, amtk in cur.fetchall():
        d = slot(y, m); q = q or 0; amtk = amtk or 0
        if str(div or "").strip() == "P":
            d["net"] += q; d["pos"] += q; d["pq"] += q; d["pamt"] += amtk
        else:
            d["net"] -= q; d["neg"] += q
    return out


def _mat_step(state, moves, consum):
    """하루 전개(이동평균). state={mat:[qty,avg]} in-place 갱신, 반환={mat:(qty,amt,avg,in,out)}."""
    res = {}
    for mat in set(state) | set(moves):
        q0, a0 = state.get(mat, [0.0, 0.0])
        mv = moves.get(mat) or {"net": 0.0, "pos": 0.0, "neg": 0.0, "pq": 0.0, "pamt": 0.0}
        if mat in consum and mat not in state:      # 신규 소모품 제외(기존 보유분은 유지)
            continue
        pq, pamt = mv["pq"], mv["pamt"]
        if pq > 0:
            # ★재고>0 이면 가중평균, 재고≤0 이면 단가 리셋(마이너스재고 평균폭발 방지)
            avg = ((q0 * a0 + pamt) / (q0 + pq)) if q0 > 0 else (pamt / pq)
        else:
            avg = a0
        qty = q0 + mv["net"]
        state[mat] = [qty, avg]
        res[mat] = (qty, qty * avg, avg, mv["pos"], mv["neg"])
    return res


def _mat_base(cur, target):
    """기초 상태 = target 직전의 가장 최근 확정 스냅샷. 없으면 레거시 월마감으로 시드.
       반환 (state, base_ymd, source)."""
    cur.execute("""SELECT TOP 1 period FROM nx.stock_snapshot
                   WHERE domain='MAT' AND ptype='D' AND period < ? ORDER BY period DESC""", target)
    r = cur.fetchone()
    if r:
        base = r[0]
        cur.execute("""SELECT item_code, stock_qty, avg_cost FROM nx.stock_snapshot
                       WHERE domain='MAT' AND ptype='D' AND period=?""", base)
        return ({str(x[0]).strip().upper(): [float(x[1] or 0), float(x[2] or 0)] for x in cur.fetchall()},
                base, "확정 스냅샷")
    # ★최초 마감 시드 = 레거시 월마감(직전월 기말). 빌더의 기초(2606 월말 픽스)와 동일 기준.
    y, m = int(target[:2]), int(target[2:4])
    m -= 1
    if m == 0:
        m = 12; y -= 1
    prev_ym = f"{y:02d}{m:02d}"
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(STOCK_QTY AS float)), SUM(CAST(STOCK_AMT AS float))
                     FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH
                    WHERE STOCK_YYMM=? AND CUST_CODE='Z99990' AND MAT_CODE IS NOT NULL
                    GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", prev_ym)
    st = {}
    for mat, q, a in cur.fetchall():
        q = float(q or 0); a = float(a or 0)
        st[mat] = [q, (a / q) if q else 0.0]
    if not st:
        raise HTTPException(400, f"기초를 찾을 수 없습니다 — 직전 확정 스냅샷도, 레거시 월마감({prev_ym})도 없습니다.")
    return st, prev_ym + "말", f"레거시 월마감 {prev_ym} 시드"


def _today6():
    import datetime as _dt
    return _dt.date.today().strftime("%y%m%d")


def _shift_ymd(ymd, days):
    """YYMMDD ± days. 파싱 불가면 원본 반환(방어)."""
    import datetime as _dt
    try:
        d = _dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])) + _dt.timedelta(days=days)
        return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"
    except Exception:
        return ymd


def _next_ymd(ymd):
    return _shift_ymd(ymd, 1)


def _prev_ymd(ymd):
    return _shift_ymd(ymd, -1)


def _month_end(period):
    """YYMM → 그 달 말일 YYMMDD."""
    import calendar as _cal
    y, m = 2000 + int(period[:2]), int(period[2:])
    return f"{period}{_cal.monthrange(y, m)[1]:02d}"


def _snap_mat_movavg_old(cur, ptype, period):
    # ★★사용 금지 — 구 이동평균(오류 6개 포함: 입고tag 9,S만 / 수입 MAINT_AMT×환율 /
    #   검사미통과 미제외 / 소모품 LIKE '99%' / 마스터 미조인 / 품목키 미정규화).
    #   정본은 아래 _snap_mat (§12-3 교정본). 이 함수는 '교정 전후 대조' 목적으로만 남긴다.
    """★마감 = f(전표). 기초(직전 확정) + 그 기간 이동을 이동평균 전개 → target 시점 확정.
       멱등(같은 키 DELETE 후 재삽입). 반환 (행수, 기준일)."""
    target = period if ptype == "D" else _month_end(period)
    state, base_ymd, src = _mat_base(cur, target)
    d_from = base_ymd[:6]
    # 기초 다음날부터 target 까지 전개 (기초일 자체는 이미 반영된 상태)
    import datetime as _dt
    try:
        b = _dt.date(2000 + int(d_from[:2]), int(d_from[2:4]), int(d_from[4:6])) + _dt.timedelta(days=1)
        start = f"{b.year % 100:02d}{b.month:02d}{b.day:02d}"
    except ValueError:                       # 시드('...말') → 그 달 다음날부터
        start = f"{int(d_from[:4]) + 1:04d}01" if int(d_from[2:4]) < 12 else f"{int(d_from[:2]) + 1:02d}0101"
    consum = _mat_consum(cur)
    moves = _mat_moves(cur, start, target) if start <= target else {}
    for ymd in sorted(moves):                # 이동이 있는 날만 전개(없는 날은 상태 불변 = 이월)
        if ymd <= target:
            _mat_step(state, moves[ymd], consum)
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain='MAT' AND ptype=? AND period=?", ptype, period)
    n = 0
    for mat, (q, a) in state.items():
        # ★잔량 0 품목은 스냅샷에서 제외(대표 확정 2026-08-27). 빌더(mat_stock_daily)와 동일 규칙.
        #   state 에는 남겨 이월시키되 '확정 재고'로는 적재하지 않는다. 0에서 재입고시 단가는
        #   어차피 리셋(재고<=0 refill 규칙)이라 avg 유실 없음. 음수는 실재고이므로 유지.
        if not mat or abs(q) < 1e-9:
            continue
        cur.execute("""INSERT INTO nx.stock_snapshot(domain,ptype,period,item_code,stock_qty,stock_amt,avg_cost,close_dt)
                       VALUES('MAT',?,?,?,?,?,?,GETDATE())""",
                    ptype, period, mat[:50], round(q, 4), round(q * a, 4), round(a, 4))
        n += 1
    return n, f"{target}({src}·기초 {base_ymd})"




# ===================== 총평균법(레거시 정본) — 대표 결정 2026-08-27 §9 =====================
# 정본 = src_extracted/sa_stock_01/w_pu_stock_160.srw (레거시 자재 월마감).
#   기간 = **역월 1개월**. 단가는 월말 1회 확정:
#       STOCK_COST = FLOOR(STOCK_AMT / STOCK_QTY)
#       STOCK_QTY  = BASIC_QTY + INPUT_QTY - OUTPUT_QTY + TRANS_QTY
#       STOCK_AMT  = BASIC_AMT + INPUT_AMT - OUTPUT_AMT + TRANS_AMT
#   ★이동평균은 은퇴(§9). 이유: 원가엔진이 avg_cost 를 참조하지 않고(0건), 게이팅은 수량만 쓴다.
#     그리고 총평균은 이동평균에서 우리가 고쳤던 결함 3개를 구조적으로 안 겪는다
#     (수입금액=TAXPAYERS 원화 → 환율 무관 · 월단위 → 마이너스 평균폭발 없음 · 입고 tag 에 P 포함).
#   재현 검증 = _migration/legacy_total_avg_verify.py
#     2606/2607 품목집합 diff0 · 수량 100.00% · 단가 99.81/99.79%(잔차는 전부 알고리즘 외 사유).

TA_IN_TAGS = ('3', '9', 'C', 'G', 'H', 'S', 'P', 'R')      # 자재입고
TA_OUT_TAGS = ('1', '4', '5', '6', '8', 'A', 'B', 'J')     # 자재출고


def _ta_rnd(x):
    """T-SQL ROUND(x,0) = 반올림(.5 는 0 에서 먼 쪽). 파이썬 round() 는 은행가반올림이라 못 씀."""
    import math as _m
    return _m.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)


def _ta_build(cur, d_from, d_to, basic):
    """레거시 160 월마감 재현(기간형). [d_from,d_to] = 그 달 1일~대상일(월마감이면 1일~말일).
       basic={mat:(qty,amt)} 기초. 반환 {mat:{...}} (sq/sa/sc 포함).
       ★키는 UPPER+TRIM 정규화 — 레거시는 CI 콜레이션이라 GROUP BY 가 대소문자를 합친다
         (동Body vs 동BODY. 정규화 안 하면 수량이 갈라짐 = 실제 겪은 버그)."""
    R = {}

    def slot(m):
        m = str(m or "").strip().upper()
        return R.setdefault(m, {"bq": 0.0, "ba": 0.0, "iq": 0.0, "ia": 0.0,
                                "oq": 0.0, "oa": 0.0, "tq": 0.0, "ta": 0.0, "tc": 0.0, "oc": 0.0})

    for m, (q, a) in basic.items():
        d = slot(m); d["bq"] += q; d["ba"] += a

    ph_in = ','.join('?' * len(TA_IN_TAGS))
    cur.execute(f"""SELECT a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(a.MAINT_AMT AS float))
                      FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                      JOIN PARTNER_ERP_TEST3.nx.item m ON a.MAT_CODE = m.ITEM_CODE
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_QTY <> 0
                       AND a.MAINT_TAG IN ({ph_in})
                       AND NOT (ISNULL(a.INSP_FLAG,'N') IN ('S','F') AND ISNULL(a.INSP_PROC_FLAG,'0') <> '1')
                     GROUP BY a.MAT_CODE""", d_from, d_to, *TA_IN_TAGS)
    for m, q, a in cur.fetchall():
        d = slot(m); d["iq"] += float(q or 0); d["ia"] += float(a or 0)

    # 수입(도입): division<>'Q' = 입고(금액 = TAXPAYERS 과세표준, 이미 원화) / 'Q' = 수출출고
    cur.execute("""SELECT a.MAT_CODE, a.DIVISION, SUM(CAST(a.MAINT_QTY AS float)),
                          SUM(CAST(ISNULL(a.TAXPAYERS,0) AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C a
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.WH_CUST_CODE = 'Z99990'
                    GROUP BY a.MAT_CODE, a.DIVISION""", d_from, d_to)
    for m, div, q, tax in cur.fetchall():
        d = slot(m); q = float(q or 0)
        if str(div or "").strip() == 'Q':
            d["oq"] += q
        else:
            d["iq"] += q; d["ia"] += float(tax or 0)

    ph_out = ','.join('?' * len(TA_OUT_TAGS))
    cur.execute(f"""SELECT a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                      FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ({ph_out})
                     GROUP BY a.MAT_CODE""", d_from, d_to, *TA_OUT_TAGS)
    for m, q in cur.fetchall():
        slot(m)["oq"] += float(q or 0)

    cur.execute("""SELECT a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                     JOIN PARTNER_ERP_TEST3.nx.item m ON a.MAT_CODE = m.ITEM_CODE
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = 'T' GROUP BY a.MAT_CODE""", d_from, d_to)
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)
    cur.execute("""SELECT a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = '2' GROUP BY a.MAT_CODE""", d_from, d_to)
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)

    # 소모품(ITEM_SGROUP >= '990') 제외 + 품목마스터 미등록 탈락 (레거시 WHERE/JOIN 동일)
    cur.execute("SELECT ITEM_CODE, ISNULL(sgroup,'') FROM PARTNER_ERP_TEST3.nx.item")
    sg = {str(r[0]).strip().upper(): str(r[1]) for r in cur.fetchall()}
    R = {m: d for m, d in R.items() if m and m in sg and sg[m] < '990'}
    R = {m: d for m, d in R.items()          # 레거시 HAVING — 전부 0 이면 제외
         if any(abs(d[k]) > 1e-9 for k in ("bq", "ba", "iq", "ia", "oq", "oa", "tq", "ta"))}

    # 단가 마스터 폴백(레거시 UPDATE U3/V3). 레거시는 ITEM_COST×기준환율이나 환율은 창 변수 →
    # 원화 단가만 사용(외화 품목 2건 수준 차이, 검증기록 §7-2).
    # ★2026-08-31 단가 소스 이관: 라이브 dbo.PR_M_ITEM_COST → 정본 nx.price_item('매입', DO_NOT_USE §18).
    #   컷오버 시 라이브 차단→폴백 금지(§1-9-1). COST_TAG='1'=price_type='매입'. LG 사급가(vendor='LG')는 실매입원가
    #   아니므로 제외(라이브엔 없음). 라이브 vs 클린 전품목 대조: 9834/9872 동일, 잔여 38=동일데이터·같은날짜 동점
    #   (라이브도 비결정적이던 것)·이 mcost는 최후폴백(기초0·입고0)만 쓰여 영향 극미. main_flag/vendor tiebreak 로 결정화.
    cur.execute("""SELECT ITEM_CODE, ITEM_COST FROM (
                     SELECT LTRIM(RTRIM(item_code)) ITEM_CODE, CAST(price AS float) ITEM_COST,
                            ROW_NUMBER() OVER(PARTITION BY LTRIM(RTRIM(item_code)) ORDER BY apply_ymd DESC,
                                              ISNULL(main_flag,'') DESC, LTRIM(RTRIM(ISNULL(vendor_code,''))) ASC) rn
                       FROM PARTNER_ERP_TEST3.nx.price_item
                      WHERE price_type = N'매입' AND apply_ymd <= ?
                        AND ISNULL(currency,'KRW') IN ('KRW','')
                        AND LTRIM(RTRIM(ISNULL(vendor_code,''))) <> 'LG') t WHERE rn = 1""", d_to[:4] + '99')
    mcost = {str(r[0]).strip().upper(): float(r[1] or 0) for r in cur.fetchall()}

    for m, d in R.items():                   # TRANS 금액 (레거시 UPDATE 순서 U1~U4)
        den = d["bq"] + d["iq"]; num = d["ba"] + d["ia"]
        if d["tq"] != 0 and d["oq"] == 0 and (d["bq"] + d["iq"] + d["tq"]) == 0:
            d["ta"] = -num
            d["tc"] = _ta_rnd(abs(num / den)) if den != 0 else 0
        if d["tq"] != 0 and d["tc"] == 0 and d["ta"] == 0:
            d["ta"] = _ta_rnd(abs(num * d["tq"] / den)) * (1 if d["tq"] > 0 else -1) if den != 0 else 0
            d["tc"] = _ta_rnd(abs(num / den)) if den != 0 else 0
        if d["bq"] == 0 and d["iq"] == 0 and d["tq"] != 0 and d["tc"] == 0:
            d["tc"] = mcost.get(m, 0.0)
        if d["tq"] != 0 and d["tc"] != 0 and d["ta"] == 0:
            d["ta"] = d["tc"] * d["tq"]

    for m, d in R.items():                   # OUTPUT 금액 (레거시 UPDATE 순서 V1~V4)
        den = d["bq"] + d["iq"] + d["tq"]; num = d["ba"] + d["ia"] + d["ta"]
        if d["oq"] != 0 and (den - d["oq"]) == 0:
            d["oa"] = num
            d["oc"] = _ta_rnd(abs(num / den)) if den != 0 else 0
        if d["oq"] != 0 and d["oc"] == 0 and d["oa"] == 0:
            d["oa"] = _ta_rnd(abs(num * d["oq"] / den)) * (1 if d["oq"] > 0 else -1) if den != 0 else 0
            d["oc"] = _ta_rnd(abs(num / den)) if den != 0 else 0
        if d["bq"] == 0 and d["iq"] == 0 and d["oq"] != 0 and d["oc"] == 0:
            d["oc"] = mcost.get(m, 0.0)
        if d["oq"] != 0 and d["oc"] != 0 and d["oa"] == 0:
            d["oa"] = d["oc"] * d["oq"]

    import math as _m
    for d in R.values():
        d["sq"] = d["bq"] + d["iq"] - d["oq"] + d["tq"]
        d["sa"] = d["ba"] + d["ia"] - d["oa"] + d["ta"]
        d["sc"] = _m.floor(d["sa"] / d["sq"]) if d["sq"] != 0 else 0
    return R


def _ta_basic(cur, yymm):
    """그 달의 기초 = 직전월 기말. 우리 확정 월스냅샷 우선, 없으면 레거시 PU_T_MONTH_STOCK_WH.
       반환 (basic{mat:(qty,amt)}, prev_ym, 출처)."""
    y, m = int(yymm[:2]), int(yymm[2:])
    m -= 1
    if m == 0:
        m = 12; y -= 1
    prev = f"{y:02d}{m:02d}"
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), SUM(stock_qty), SUM(stock_amt)
                     FROM nx.stock_snapshot WHERE domain='MAT' AND ptype='M' AND period=?
                    GROUP BY UPPER(LTRIM(RTRIM(item_code)))""", prev)
    rows = cur.fetchall()
    if rows:
        return {str(r[0]): (float(r[1] or 0), float(r[2] or 0)) for r in rows}, prev, "확정 월스냅샷"
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(STOCK_QTY AS float)), SUM(CAST(STOCK_AMT AS float))
                     FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH
                    WHERE STOCK_YYMM=? AND CUST_CODE='Z99990' AND MAT_CODE IS NOT NULL
                    GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", prev)
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(400, f"기초를 찾을 수 없습니다 — 직전월({prev}) 확정 스냅샷도 레거시 월마감도 없습니다.")
    return {str(r[0]): (float(r[1] or 0), float(r[2] or 0)) for r in rows}, prev, f"레거시 월마감 {prev} 시드"


def _snap_mat_month_totalavg(cur, period):   # ★총평균(레거시 방식) — 차이 리포트·대조용 보존
    """자재 월마감 = 총평균법. 반환 (행수, 기준설명)."""
    basic, prev, src = _ta_basic(cur, period)
    R = _ta_build(cur, period + '01', _month_end(period), basic)
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain='MAT' AND ptype='M' AND period=?", period)
    n = 0
    for mat, d in R.items():
        if abs(d["sq"]) < 1e-9:              # 잔량 0 제외(대표 확정)
            continue
        cur.execute("""INSERT INTO nx.stock_snapshot
                         (domain,ptype,period,item_code,loc,stock_qty,stock_amt,avg_cost,in_qty,out_qty,close_dt)
                       VALUES('MAT','M',?,?,'',?,?,?,?,?,GETDATE())""",
                    period, mat[:50], round(d["sq"], 4), round(d["sa"], 4), round(d["sc"], 4),
                    round(d["iq"], 4), round(d["oq"], 4))
        n += 1
    return n, f"{_month_end(period)}(총평균법·기초 {prev} {src})"


def _snap_mat_day_totalavg(cur, period):     # ★총평균 일 평가 — 대조용 보존
    """자재 일마감 = **수량 확정 + 직전 확정 월단가로 평가**(총평균법의 표준 처리).
       단가는 월말에 1회 확정되므로, 월중 일마감은 그 시점 수량을 굳히고 금액은 월단가로 매긴다.
       반환 (행수, 기준설명)."""
    ym = period[:4]
    basic, prev, src = _ta_basic(cur, ym)
    # 그 달 1일 ~ period 까지만 반영한 '부분월' 전개(같은 엔진, 기간만 잘라 씀)
    R = _ta_build(cur, ym + '01', period, basic)
    # 단가 = 직전 확정 월단가(없으면 기초 amt/qty). 월말 확정 전까지의 평가단가.
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), avg_cost FROM nx.stock_snapshot
                     WHERE domain='MAT' AND ptype='M' AND period=?""", prev)
    pc = {str(r[0]): float(r[1] or 0) for r in cur.fetchall()}
    if not pc:
        pc = {m: ((a / q) if q else 0.0) for m, (q, a) in basic.items()}
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain='MAT' AND ptype='D' AND period=?", period)
    n = 0
    for mat, d in R.items():
        if abs(d["sq"]) < 1e-9:
            continue
        c = pc.get(mat, 0.0)
        cur.execute("""INSERT INTO nx.stock_snapshot
                         (domain,ptype,period,item_code,loc,stock_qty,stock_amt,avg_cost,in_qty,out_qty,close_dt)
                       VALUES('MAT','D',?,?,'',?,?,?,?,?,GETDATE())""",
                    period, mat[:50], round(d["sq"], 4), round(d["sq"] * c, 4), round(c, 4),
                    round(d["iq"], 4), round(d["oq"], 4))
        n += 1
    return n, f"{period}(수량확정·단가는 {prev} 월확정단가)"


def _snap_mat_totalavg(cur, ptype, period):   # ★총평균 디스패처 — 대조용 보존
    return _snap_mat_month_totalavg(cur, period) if ptype == "M" else _snap_mat_day_totalavg(cur, period)



# ===================== 이동평균법(신고 평가방법) — 확정 §12 =====================
# 세무사 확인: 신고된 재고자산 평가방법 = **이동평균법 + 저가법**.
#   ★레거시(w_pu_stock_160)는 총평균으로 돈다 = 신고 방법과 불일치.
#     따라서 자재 단가는 레거시 diff0 대상이 아니다(차이는 리포트로 노출 — §12-1).
#   ★분류 축·데이터 원천·제외기준은 총평균 작업에서 규명한 레거시 정본을 그대로 쓴다(§12-3).
#     기존 우리 이동평균의 오류 6개(입고tag 9,S만 / 수입 MAINT_AMT×환율 / 검사미통과 미제외 /
#     소모품 LIKE '99%' / 마스터 미조인 / 품목키 미정규화)를 여기서 교정한다.
#   ★일 단위 묶음 = 건별과 동일: (q0·a0+Σamt)/(q0+Σqty) 는 순차적용과 결과가 같고
#     출고는 평균을 바꾸지 않는다. 그래서 일 단위 전개로 충분하다.
#   저가법(NRV)은 별도 레이어 — 미구현(§12-4, 재무제표용은 추후).

def _mv_moves(cur, d_from, d_to):
    """[d_from,d_to] 일자별 자재 이동 → {ymd: {mat: {net,inq,outq,trans,pq,pamt}}}.
       pq/pamt = **평균단가를 갱신하는 입고**(레거시 입고 tag + 수입). 그 외는 평균 불변."""
    out = {}

    def slot(y, m):
        m = str(m or "").strip().upper()
        return out.setdefault(y, {}).setdefault(
            m, {"net": 0.0, "inq": 0.0, "outq": 0.0, "trans": 0.0, "pq": 0.0, "pamt": 0.0})

    ph_in = ','.join('?' * len(TA_IN_TAGS))
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE,
                           SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(a.MAINT_AMT AS float))
                      FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                      JOIN PARTNER_ERP_TEST3.nx.item m ON a.MAT_CODE = m.ITEM_CODE
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_QTY <> 0
                       AND a.MAINT_TAG IN ({ph_in})
                       AND NOT (ISNULL(a.INSP_FLAG,'N') IN ('S','F') AND ISNULL(a.INSP_PROC_FLAG,'0') <> '1')
                     GROUP BY a.MAINT_YMD, a.MAT_CODE""", d_from, d_to, *TA_IN_TAGS)
    for y, m, q, amt in cur.fetchall():
        d = slot(y, m); q = float(q or 0)
        d["inq"] += q; d["pq"] += q; d["pamt"] += float(amt or 0)

    # 수입(도입): DIVISION<>'Q' = 입고(금액 TAXPAYERS, 이미 원화·평균갱신) / 'Q' = 수출출고
    cur.execute("""SELECT a.MAINT_YMD, a.MAT_CODE, a.DIVISION,
                          SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(ISNULL(a.TAXPAYERS,0) AS float))
                     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_C a
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.WH_CUST_CODE = 'Z99990'
                    GROUP BY a.MAINT_YMD, a.MAT_CODE, a.DIVISION""", d_from, d_to)
    for y, m, div, q, tax in cur.fetchall():
        d = slot(y, m); q = float(q or 0)
        if str(div or "").strip() == 'Q':
            d["outq"] += q
        else:
            d["inq"] += q; d["pq"] += q; d["pamt"] += float(tax or 0)

    ph_out = ','.join('?' * len(TA_OUT_TAGS))
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                      FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ({ph_out})
                     GROUP BY a.MAINT_YMD, a.MAT_CODE""", d_from, d_to, *TA_OUT_TAGS)
    for y, m, q in cur.fetchall():
        slot(y, m)["outq"] += float(q or 0)

    cur.execute("""SELECT a.MAINT_YMD, a.MAT_CODE, SUM(-CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                     JOIN PARTNER_ERP_TEST3.nx.item m ON a.MAT_CODE = m.ITEM_CODE
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = 'T'
                    GROUP BY a.MAINT_YMD, a.MAT_CODE""", d_from, d_to)
    for y, m, q in cur.fetchall():
        slot(y, m)["trans"] += float(q or 0)
    cur.execute("""SELECT a.MAINT_YMD, a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = '2'
                    GROUP BY a.MAINT_YMD, a.MAT_CODE""", d_from, d_to)
    for y, m, q in cur.fetchall():
        slot(y, m)["trans"] += float(q or 0)

    for y in out:
        for d in out[y].values():
            d["net"] = d["inq"] - d["outq"] + d["trans"]
    return out


def _mv_scope(cur):
    """평가 대상 품목 집합 = 품목마스터 등록 + 소모품(sgroup>='990') 제외.
       ★소스 = nx.item (정본). 레거시 PR_M_ITEM 이 아니다 —
         sgroup 소유권이 nx.item 으로 이관됐고(PR#84, r_item_sync 에서 sgroup 제외)
         용접봉 240 신설·용접링 230 통합 같은 재분류가 레거시엔 반영되지 않는다.
       실측(2026-08-27): 이 전환으로 현재 스냅샷에서 빠지는 품목 0건 = 안전."""
    cur.execute("SELECT ITEM_CODE FROM PARTNER_ERP_TEST3.nx.item WHERE ISNULL(sgroup,'') < '990'")
    return {str(r[0]).strip().upper() for r in cur.fetchall()}


def _mv_step(state, moves, scope):
    """하루 이동평균 전개. state={mat:[qty,avg]} in-place.
       ★규칙1 재고<=0 에서 매입 refill = 단가 리셋(마이너스재고 평균폭발 방지 — 검증된 우리 규칙).
       """
    for mat, mv in moves.items():
        if mat not in scope:                 # 소모품·미등록 = 평가 대상 아님
            continue
        q0, a0 = state.get(mat, [0.0, 0.0])
        pq, pamt = mv["pq"], mv["pamt"]
        if pq > 0:
            avg = ((q0 * a0 + pamt) / (q0 + pq)) if q0 > 0 else (pamt / pq)
        else:
            avg = a0
        state[mat] = [q0 + mv["net"], avg]


_MAT_BUY_CACHE = {}       # yymm -> {item: 실매입 가중평균단가}   ★T4 성능: 월 단위 캐시


def _mv_buyprice(cur, target):
    """실매입 전표 가중평균단가 = Σ매입금액 / Σ매입수량 (as-of target).
       ★용도: 이동평균 전개 후에도 단가가 0 인 품목의 **보정**.
         전개구간에 매입이 없으면 기초 단가가 그대로 유지되는데, 레거시 기초에 금액이 0 으로
         들어온 품목은 영원히 0 이 된다(실측 2026-08-27: 자재 단가0 170건 중 73건이 이 경우).
         재고자산을 0 으로 누락시키는 것보다 **실제 지불가로 계상**하는 것이 정확하다.
       ※이동평균법 자체를 바꾸는 것이 아니라 **결함 기초를 보정**하는 것이다."""
    # ★캐시 키 = as-of 일자 전체(2026-08-30) — 값이 as-of 누계인데 월 키를 쓰면
    #   월초에 먼저 부른 값이 그 달 전체에 박힌다(_PRD_PX_CACHE 와 같은 결함).
    ck = str(target)
    if ck in _MAT_BUY_CACHE:
        return _MAT_BUY_CACHE[ck]
    ph_in = ','.join('?' * len(TA_IN_TAGS))
    cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(a.MAT_CODE))),
                          SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(a.MAINT_AMT AS float))
                     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD <= ? AND a.MAINT_QTY <> 0
                      AND a.MAINT_TAG IN ({ph_in})
                      AND NOT (ISNULL(a.INSP_FLAG,'N') IN ('S','F') AND ISNULL(a.INSP_PROC_FLAG,'0') <> '1')
                    GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE)))""", target, *TA_IN_TAGS)
    px = {}
    for it, q, amt in cur.fetchall():
        q = float(q or 0); amt = float(amt or 0)
        if q > 0 and amt > 0:
            px[str(it)] = amt / q
    _MAT_BUY_CACHE[ck] = px
    return px


# ★★기초 연쇄에는 **제외분(nx.stock_snapshot_drop)도 반드시 포함**한다 (2026-08-28 결함수정).
#   제외(단가0·음수·잔량0)는 "재고자산 평가에서 빼는 것"이지 "없던 일로 하는 것"이 아니다.
#   기초에서까지 빼면 다음 기간이 **0에서 시작**해 음수가 소리 없이 사라지고 재고가 늘어난 것처럼 보인다.
#   실측: 11588O-1 은 2606 기말 −190(음수)로 제외 → 2607 이 0에서 출발해 2042(정답 1852).
#   대표가 미리 지적한 바로 그 문제 — "당월에 반영됐고… 그럼 다음달에도 반영이 안되는거 아니야?"
#   ⟹ 표시·평가에서만 빼고, **수량·금액의 연속성은 유지**한다.
def _snapshot_rows(cur, domain, ptype, period, with_loc=False):
    """확정 스냅샷 ∪ 제외분. 기초 복원 전용."""
    cols = "UPPER(LTRIM(RTRIM(item_code))), ISNULL(loc,''), stock_qty, stock_amt, avg_cost" if with_loc            else "UPPER(LTRIM(RTRIM(item_code))), '', stock_qty, stock_amt, avg_cost"
    sql = f"SELECT {cols} FROM nx.stock_snapshot WHERE domain=? AND ptype=? AND period=?"
    cur.execute(sql, domain, ptype, period)
    out = list(cur.fetchall())
    try:
        cur.execute(sql.replace("nx.stock_snapshot", "nx.stock_snapshot_drop"), domain, ptype, period)
        out += list(cur.fetchall())
    except Exception:
        pass            # drop 테이블이 아직 없으면(구 데이터) 스냅샷만으로 진행
    return out


def _mv_base(cur, target):
    """기초 = target 직전의 가장 최근 확정 스냅샷(일·월 통합). 없으면 레거시 월마감 시드.
       반환 (state{mat:[qty,avg]}, base_ymd, 출처)."""
    cur.execute("""SELECT TOP 1 period FROM nx.period_close
                    WHERE domain='MAT' AND ptype='D' AND close_flag=1 AND period < ?
                    ORDER BY period DESC""", target)
    r = cur.fetchone()
    cand = [(r[0], "D", r[0])] if r else []
    # ★"가장 최신 월마감" 하나만 보고 target 보다 뒤면 버리면 안 된다 — 그러면 그 아래
    #   쓸 수 있는 월마감이 있는데도 **레거시 시드로 떨어진다**(2026-08-28 실측).
    #   같은 기간을 마감엔진과 수불장이 서로 다른 기초로 계산해 금액이 394건 갈렸다.
    #   ⟹ target 보다 앞선 월마감 중 **가장 최신**을 고른다.
    cur.execute("""SELECT period FROM nx.period_close
                    WHERE domain='MAT' AND ptype='M' AND close_flag=1
                    ORDER BY period DESC""")
    for (per,) in cur.fetchall():
        if _month_end(per) < target:
            cand.append((_month_end(per), "M", per)); break
    if cand:
        ymd, pt, per = max(cand, key=lambda x: x[0])
        # ★단가는 stock_amt/stock_qty 로 복원한다 — avg_cost 는 decimal(18,4) 반올림본이라
        #   그걸 그대로 기초로 쓰면 매 기간 반올림 오차가 누적된다(금액 항등식 위반 29건 실측).
        #   금액이 정본, 단가는 파생. qty=0 이면 저장 단가로 폴백.
        st = {}
        for _it, _lo, _q, _a, _av in _snapshot_rows(cur, 'MAT', pt, per):
            x = (_it, _q, _a, _av)
            q = float(x[1] or 0); amt = float(x[2] or 0)
            st[str(x[0])] = [q, (amt / q) if q else float(x[3] or 0)]
        if st:
            return st, ymd, f"확정 스냅샷({'일' if pt == 'D' else '월'}마감 {per})"
    # 최초 시드 = 레거시 월마감(직전월 기말). ★레거시는 총평균이라 시드 단가만 총평균 기준이다.
    #   이후는 우리 이동평균으로 전개되므로 시간이 지나며 이동평균 기준으로 수렴한다(§12-1).
    y, m = int(target[:2]), int(target[2:4])
    m -= 1
    if m == 0:
        m = 12; y -= 1
    prev = f"{y:02d}{m:02d}"
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), SUM(CAST(STOCK_QTY AS float)), SUM(CAST(STOCK_AMT AS float))
                     FROM PARTNER_ERP.dbo.PU_T_MONTH_STOCK_WH
                    WHERE STOCK_YYMM=? AND CUST_CODE='Z99990' AND MAT_CODE IS NOT NULL
                    GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", prev)
    st = {}
    for mat, q, a in cur.fetchall():
        q = float(q or 0); a = float(a or 0)
        st[str(mat)] = [q, (a / q) if q else 0.0]
    if not st:
        raise HTTPException(400, f"기초를 찾을 수 없습니다 — 직전 확정 스냅샷도 레거시 월마감({prev})도 없습니다.")
    return st, _month_end(prev), f"레거시 월마감 {prev} 시드"


def _snap_mat(cur, ptype, period):
    """★자재 마감 = 이동평균법(신고 평가방법 §12). 기초(직전 확정) + 그 기간 전표를 일자별 전개.
       월마감 = 그 달 말일까지 전개(= 말일 일마감과 동일). 멱등. 반환 (행수, 기준설명)."""
    import datetime as _dt
    target = period if ptype == "D" else _month_end(period)
    state, base_ymd, src = _mv_base(cur, target)
    try:
        b = _dt.date(2000 + int(base_ymd[:2]), int(base_ymd[2:4]), int(base_ymd[4:6])) + _dt.timedelta(days=1)
        start = f"{b.year % 100:02d}{b.month:02d}{b.day:02d}"
    except ValueError:
        start = base_ymd
    scope = _mv_scope(cur)
    moves = _mv_moves(cur, start, target) if start <= target else {}
    for ymd in sorted(moves):
        if ymd <= target:
            _mv_step(state, moves[ymd], scope)
    # ★단가 보정 — 전개 후에도 0 인 품목은 **실매입 전표 가중평균**으로 채운다(위 _mv_buyprice 주석).
    #   실측(2026-08-27): 자재 단가0 170건 중 73건이 '매입 이력은 있는데 전개구간에 매입이 없어
    #   레거시 기초 금액0 이 그대로 굳은' 경우였다.
    buypx = _mv_buyprice(cur, target)
    fixed = 0
    for mat, v in state.items():
        if abs(v[1]) < 1e-9 and abs(v[0]) > 1e-9:
            c = buypx.get(mat, 0.0)
            if c:
                v[1] = c; fixed += 1
    # 그 기간 입·출 누계(스냅샷 참고컬럼)
    agg = {}
    for ymd in sorted(moves):
        if ymd > target:
            continue
        for mat, mv in moves[ymd].items():
            a = agg.setdefault(mat, [0.0, 0.0])
            a[0] += mv["inq"]; a[1] += mv["outq"]
    out_rows = []
    for mat, (q, a) in state.items():
        if not mat or mat not in scope:                   # 소모품·미등록 제외(잔량0 은 _snap_bulk 가 처리)
            continue
        i, o = agg.get(mat, (0.0, 0.0))
        out_rows.append((mat, "", q, q * a, a, i, o))
    n = _snap_bulk(cur, "MAT", ptype, period, out_rows)
    return n, f"{target}(이동평균·기초 {base_ymd} {src}·단가보정 {fixed})"



# ===================== 마감/해제 권한 게이트 — C5 (2026-08-27) =====================
# 마감·해제는 회계 확정/되돌리기다 → **명시 권한자만**(deny by default).
#   ① 시스템관리자 role(nx.app_user 의 roles) → 허용
#   ② nx.user_perm 에 (user, sid='close', can_edit=1) 행이 있으면 허용
#   ③ 그 외 전부 거부(403)
# ★한계(정직히 기록): 이 앱은 세션 인증이 없고 사용자 식별은 프론트 localStorage 다.
#   즉 payload 의 user 는 위조 가능하며, 이 게이트는 **오조작 방지**지 보안 인증이 아니다.
#   진짜 인증은 로그인/세션 도입 시 함께 해결해야 한다(별도 과제).
PERM_SID = "close"

def _assert_can_close(cur, user, what="마감"):
    u = str(user or "").strip()
    if not u:
        raise HTTPException(403, f"{what} 권한을 확인할 수 없습니다 — 사용자 정보가 없습니다.")
    # ① 시스템관리자 — 정본 nx.app_user (2026-08-29 이관. 예전 nx.web_user JSON 은 은퇴)
    try:
        cur.execute("SELECT roles FROM nx.app_user WHERE user_id=? AND ISNULL(status,'사용')='사용'", u)
        r = cur.fetchone()
        if r and r[0]:
            import json as _json
            if "시스템관리자" in (_json.loads(r[0]) or []):
                return "시스템관리자"
    except Exception:
        pass          # 계정 테이블이 아직 없으면 ②로 판정(권한 없으면 어차피 거부)
    # ② 개별 부여 권한
    try:
        cur.execute("""SELECT can_edit FROM nx.user_perm WHERE user_id=? AND sid=?""", u, PERM_SID)
        r = cur.fetchone()
        if r and int(r[0] or 0) == 1:
            return "개별권한"
    except Exception:
        pass
    raise HTTPException(403, f"{what} 권한이 없습니다({u}) — 시스템관리자 또는 '마감관리' 수정권한이 필요합니다.")


# ===================== 생산(PRD) · 영업(SAL) 스냅샷 — C2 (2026-08-27) =====================
# ★소스 선택 근거: nx.stock_ledger 는 PRD/ASY 가 0행(§4-C 실측) → 원장으로는 스냅샷을 만들 수 없다.
#   대신 게이팅 캐논 §4-C 표가 정본으로 지정한 **레거시 재현 recipe** 를 그대로 쓴다.
#     · 생산 = live_api._prodstock  (레거시 w_pr_stock_480 · 2026-08-19 diff0 검증)
#     · 완성 = live_api.salesstock  (레거시 w_pr_stock_040 · 2026-08-19 diff0 검증)
#   즉 자재와 동일한 원칙 — "확정 스냅샷은 검증된 정본 recipe 를 그 시점으로 굳힌다".
# ★생산은 2축(품목 × 라인). 가공창고(P0001)=loc '' / 용접은 라인코드를 loc 에 담는다.

def _snap_write(cur, domain, ptype, period, rows):
    """스냅샷 멱등 적재 — 배치 INSERT 위임(T4 성능). rows=[(item, loc, qty, amt, cost, inq, outq)]."""
    return _snap_bulk(cur, domain, ptype, period, rows)


def _snap_prd_recipe(cur, ptype, period):
    """★DEPRECATED(§12-8 이동평균 채택) — 480 recipe 직확정. 수량 대조용으로 보존."""
    from live_api import _prodstock
    target = period if ptype == "D" else _month_end(period)
    rows = _prodstock(target[:4], frm=target[:4] + "01", to=target)
    out = []
    for r in rows:
        # stage=GAGONG/WELD · loc=용접 라인코드(가공은 '')
        loc = ("" if str(r.get("stage")) == "GAGONG" else str(r.get("loc") or ""))
        qty = float(r.get("qty") or 0)
        cost = float(r.get("cost") or 0)
        out.append((r.get("cd"), loc, qty, qty * cost, cost,
                    float(r.get("inq") or 0), float(r.get("outq") or 0)))
    n = _snap_write(cur, "PRD", ptype, period, out)
    return n, f"{target}(생산재고조회 480 recipe)"


def _snap_sal_recipe(cur, ptype, period):
    """★DEPRECATED — 040 recipe 직확정(단가 = as-of 판가 × 수량). **이동평균이 아니다.**
       수량 대조용으로만 보존. 확정은 아래 `_snap_sal`(이동평균) 을 쓴다."""
    from live_api import salesstock
    target = period if ptype == "D" else _month_end(period)
    res = salesstock(dfrom=target[:4] + "01", dto=target, source="live", zero="1")
    out = []
    for r in (res.get("rows") or []):
        qty = float(r.get("qty") or 0)
        cost = float(r.get("cost") or 0)
        out.append((r.get("cd") or r.get("mat"), "", qty, qty * cost, cost,
                    float(r.get("inq") or 0), float(r.get("outq") or 0)))
    n = _snap_write(cur, "SAL", ptype, period, out)
    return n, f"{target}(제품재고조회 040 recipe·DEPRECATED)"


def _snap_sal(cur, ptype, period):
    """★영업 마감 = **판가 기반 이동평균**(신고 평가방법 §7-4, 대표 확정 2026-08-27).

       ★2026-08-28 결함수정: 종전엔 040 recipe 를 그대로 확정해 **as-of 판가 × 수량** 이었다.
         판가가 오르면 **기초 재고까지 전량 신규 판가로 재평가**된다 = 이동평균이 아니다.
         실측(2607): 7/9 판가 인상 품목 33건에서 수불장(이동평균)과 금액이 갈렸다.
           6851A20037L  기초단가 36,786 → 판가 37,597
             마감 940×37,597 = 35,341,180  vs  이동평균 34,578,840
         ⟹ 수불장과 **같은 엔진(_sal_ledger)** 을 호출해 확정한다(§21: 같은 값은 한 곳에서)."""
    target = period if ptype == "D" else _month_end(period)
    rows, _breaks, basis = _sal_ledger(cur, target[:4] + "01", target)
    out = [(r["cd"], "", r["sq"], r["sa"], r["avg"], r["iq"], r["oq"]) for r in rows]
    n = _snap_bulk(cur, "SAL", ptype, period, out)
    return n, f"{target}(판가 이동평균·{basis})"


# ===================== 생산(PRD) 이동평균 — 매입가 기반 (§12-8) =====================
# 축 = (품목 × 재고위치). 가공창고 P0001 = loc '' · 용접은 라인코드.
# 이동 원천 = 레거시 생산재고조회 480(`live_api._prodstock`) 과 **같은 UNION 분기**를 일자별로 편 것.
#   ★480 은 기간 요약이라 일자별 전개가 안 된다 → 같은 분기·같은 부호로 일자 컬럼을 살려 재작성.
#     분기·부호가 480 과 일치하는지는 검증 게이트(수량 diff0)로 확인한다.
# 단가 = 그 품목의 자재(MAT) 확정 스냅샷 avg_cost, 없으면 pr_m_item_cost(cost_tag='1') 최신.
#   ※MAT avg_cost 는 월말값이라 월중 입고엔 근사(§12-8 기록).

def _prd_moves(cur, d_from, d_to):
    """[d_from,d_to] 일자별 생산창고 이동 → {ymd: {(item,loc): {net,inq,outq,adj}}}."""
    T3 = "PARTNER_ERP_TEST3.nx."
    out = {}

    def slot(y, item, loc):
        k = (str(item or "").strip().upper(), "" if str(loc or "").strip() == "P0001" else str(loc or "").strip())
        return out.setdefault(y, {}).setdefault(k, {"net": 0.0, "inq": 0.0, "outq": 0.0, "adj": 0.0})

    # ① 자재→생산 이동(tag B, 자재출고라 음수 → 생산창고 입고)
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code, SUM(-CAST(a.MAINT_QTY AS float))
                      FROM {T3}PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.maint_tag='B' AND ISNULL(a.out_wh_gubun,'1')='1'
                     GROUP BY a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["inq"] += float(q or 0)

    # ② 절단 입고
    cur.execute(f"""SELECT a.cut_ymd, a.mat_code, a.gagong_proc_code, SUM(CAST(a.cut_QTY AS float))
                      FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl
                            UNION ALL SELECT n.* FROM {T3}pu_t_cut_dtl n
                             WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pu_t_cut_dtl l
                                               WHERE l.BOX_NO=n.BOX_NO AND l.CUT_YMD=n.CUT_YMD AND l.CUT_HMS=n.CUT_HMS)) a
                     WHERE a.cut_ymd BETWEEN ? AND ?
                     GROUP BY a.cut_ymd, a.mat_code, a.gagong_proc_code""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["inq"] += float(q or 0)

    # ③ 생산창고 반납(tag T) — 480 과 동일 부호(outq = −MAINT_QTY)
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code, SUM(-CAST(a.MAINT_QTY AS float))
                      FROM {T3}PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.maint_tag='T' AND ISNULL(a.out_wh_gubun,'3')='3'
                     GROUP BY a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["outq"] += float(q or 0)

    # ④ tag C 출고
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code, SUM(CAST(a.MAINT_QTY AS float))
                      FROM {T3}PU_T_STOCK_MAINT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.maint_tag='C'
                     GROUP BY a.MAINT_YMD, a.MAT_CODE, a.to_gagong_proc_code""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["outq"] += float(q or 0)

    # ⑤ 생산실적(제품입고 중복분 제외)
    cur.execute(f"""SELECT a.prod_ymd, a.item_code, a.stock_part_code, SUM(CAST(a.prod_qty AS float))
                      FROM {T3}pr_t_prod_dtl a
                     WHERE a.prod_ymd BETWEEN ? AND ? AND a.stock_part_code>''
                       AND NOT EXISTS(SELECT 1 FROM {T3}sa_t_stock_maint s
                                       WHERE s.maint_ymd=a.prod_ymd AND s.item_code=a.item_code
                                         AND s.in_part_code=a.stock_part_code)
                     GROUP BY a.prod_ymd, a.item_code, a.stock_part_code""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["inq"] += float(q or 0)

    # ⑥ 제품수불 in_part 입고
    cur.execute(f"""SELECT a.maint_ymd, a.item_code, a.IN_PART_CODE, SUM(CAST(a.MAINT_QTY AS float))
                      FROM {T3}sa_t_stock_maint a
                     WHERE a.maint_ymd BETWEEN ? AND ? AND a.in_part_code>''
                     GROUP BY a.maint_ymd, a.item_code, a.IN_PART_CODE""", d_from, d_to)
    for y, it, lo, q in cur.fetchall():
        slot(y, it, lo)["inq"] += float(q or 0)

    # ⑦⑧⑨ 생산 자재수불(PR_T_STOCK_MAINT_MAT) — tag3 입고 / tag1·2 조정 / tag4 출고
    cur.execute(f"""SELECT a.MAINT_YMD, a.MAT_CODE, a.PART_CODE, a.MAINT_TAG, SUM(CAST(a.MAINT_QTY AS float))
                      FROM {T3}PR_T_STOCK_MAINT_MAT a
                     WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG IN ('1','2','3','4')
                     GROUP BY a.MAINT_YMD, a.MAT_CODE, a.PART_CODE, a.MAINT_TAG""", d_from, d_to)
    for y, it, lo, tg, q in cur.fetchall():
        d = slot(y, it, lo); q = float(q or 0); tg = str(tg).strip()
        if tg == '3':   d["inq"] += q
        elif tg == '4': d["outq"] += -q
        else:           d["adj"] += q          # '1','2'

    for y in out:
        for d in out[y].values():
            d["net"] = d["inq"] - d["outq"] + d["adj"]
    return out


# ★★캐시 키 = **as-of 일자 전체**(2026-08-30 결함수정).
#   종전엔 연월(yymm)만 키로 썼는데 **값은 as-of 일자로 계산**된다(apply_ymd<=target).
#   그래서 일마감을 260801→260828 로 연속으로 돌리면 **260801 단가가 캐시에 박혀
#   그 달 전체가 월초 단가로 평가**됐다 → 같은 기간을 다시 마감하면 값이 달라졌다(비멱등).
#   실측(2026-08-30): SAL D 260828 일괄 677,272,841 vs 단독 703,546,042 (+26,273,201).
#   ⟹ 마감은 그 시점을 확정하는 것이다. 돌릴 때마다 달라지면 어느 것이 맞는지 알 수 없다.
_PRD_PX_CACHE = {}        # yymmdd -> (px, incust)


def _prd_price(cur, target):
    """★생산재고 단가 결정 체인 (§13-5). 반환 ({item: (단가, 출처)}, incust).
       ★T4 성능(2026-08-27): 측정 3.28초/회. 구성요소가 전부 **월 단위로 사실상 불변**이라
         (① MAT 월스냅샷 ②' 실매입 as-of 누계 ③ PR_M_ITEM_COST as-of 최신) **연월 캐시**한다.
         일마감 31회면 31번 반복되던 전체 스캔이 1번으로 줄어든다.
         ※근사 명시: 월 내 단가 변동은 반영되지 않는다. 정밀이 필요하면 캐시 키를 일자로 낮춘다.
         ① 자재(MAT) 확정 스냅샷 avg_cost                   ← 자재로 관리되는 품목
         ②' **실매입 전표 가중평균**(Σ매입금액/Σ매입수량)     ← 실제 지불가. 마스터보다 신뢰도 높음
         ② BOM 있으면 부품 매입가 합산(원가엔진 material_u)  ← SUB
         ③ PR_M_ITEM_COST 거래처 완화: 2228 → 품목 매입처 → 아무 거래처(최신)
         ④ 없으면 0 (리포트 대상)
       ★레거시처럼 거래처를 하드 분기하지 않는다 — 그러면 P1(용접) 68품목이 통째로 0 이 된다(§13-1)."""
    _ck = str(target)              # ★as-of 일자 전체(연월만 쓰면 월초 단가가 달 전체에 박힌다)
    if _ck in _PRD_PX_CACHE:
        return _PRD_PX_CACHE[_ck]
    px = {}

    # ① 자재 확정 스냅샷 (금액/수량으로 복원 — avg_cost 는 반올림본)
    cur.execute("""SELECT TOP 1 period FROM nx.period_close
                    WHERE domain='MAT' AND ptype='M' AND close_flag=1 AND period <= ? ORDER BY period DESC""",
                target[:4])
    r = cur.fetchone()
    if r:
        cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), stock_qty, stock_amt, avg_cost
                         FROM nx.stock_snapshot WHERE domain='MAT' AND ptype='M' AND period=?""", r[0])
        for it, q, amt, av in cur.fetchall():
            q = float(q or 0); amt = float(amt or 0)
            v = (amt / q) if q else float(av or 0)
            if v:
                px[str(it)] = (v, "MAT스냅샷")

    # ★②' 실매입 전표 가중평균 (Σ매입금액 / Σ매입수량, as-of target)
    #    단가 마스터(PR_M_ITEM_COST)보다 **실제로 지불한 가격**이 신뢰도가 높다.
    #    실증(2026-08-27): 용접링 BCUP 단가0 7품목 중 6품목이 실매입 전표를 갖고 있었다
    #    (신성소재 2204·성보스프링 2274 매입). 마스터에는 없어서 놓치던 것.
    ph_in = ','.join('?' * len(TA_IN_TAGS))
    cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(a.MAT_CODE))),
                          SUM(CAST(a.MAINT_QTY AS float)), SUM(CAST(a.MAINT_AMT AS float))
                     FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD <= ? AND a.MAINT_QTY <> 0
                      AND a.MAINT_TAG IN ({ph_in})
                      AND NOT (ISNULL(a.INSP_FLAG,'N') IN ('S','F') AND ISNULL(a.INSP_PROC_FLAG,'0') <> '1')
                    GROUP BY UPPER(LTRIM(RTRIM(a.MAT_CODE)))""", target, *TA_IN_TAGS)
    for it, q, amt in cur.fetchall():
        k = str(it)
        if k in px:
            continue
        q = float(q or 0); amt = float(amt or 0)
        if q > 0 and amt > 0:
            px[k] = (amt / q, "실매입전표")

    # ③ PR_M_ITEM_COST — 거래처 우선순위 2228 → 매입처 → 아무 거래처 (각각 as-of 최신)
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(i.item_code))), LTRIM(RTRIM(ISNULL(i.in_cust,'')))
                     FROM PARTNER_ERP_TEST3.nx.item i""")
    incust = {str(a): b for a, b in cur.fetchall()}
    # ★단가정본 = nx.price_item '매입' (DO_NOT_USE §18). 종전엔 라이브 dbo.PR_M_ITEM_COST 직독 —
    #   컷오버에 죽는 코드였다. 정렬은 원본 그대로 **적용일 기준**(MAIN_FLAG 미사용)이라 클린으로 그대로 옮겨진다.
    #   실측(거래처별 as-of 최신): 공통 16,875 중 **실제 값차이 0**(112건은 전부 반올림 ≤0.001).
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(item_code))), LTRIM(RTRIM(ISNULL(vendor_code,''))), price FROM (
                     SELECT item_code, vendor_code, CAST(price AS float) price,
                            ROW_NUMBER() OVER(PARTITION BY item_code, vendor_code ORDER BY apply_ymd DESC) rn
                       FROM PARTNER_ERP_TEST3.nx.price_item
                      WHERE price_type='매입' AND apply_ymd <= ?) t WHERE rn=1""", target)
    bycust = {}
    for it, cu, c in cur.fetchall():
        bycust.setdefault(str(it), {})[str(cu)] = float(c or 0)
    for it, m in bycust.items():
        if it in px:
            continue
        v = m.get("2228") or m.get(incust.get(it, "")) or next((x for x in m.values() if x), 0.0)
        if v:
            src = "COST2228" if m.get("2228") else ("COST매입처" if m.get(incust.get(it, "")) else "COST임의")
            px[it] = (float(v), src)
    _PRD_PX_CACHE[_ck] = (px, incust)
    return px, incust


# ★BOM 부품합산 단가 캐시 (T4 성능, 2026-08-27)
#   측정: 생산 일마감 21.4초 중 _prd_price_bom 이 34초(월마감 기준) = 병목 90%.
#   원인 ① 마감마다 NxCostEngine 을 새로 만들어 내부 캐시(_hasbom/_hdr/단가)가 매번 콜드
#        ② 같은 품목을 일마감 31회 동안 31번 재전개
#   대책: 엔진 싱글턴 + **(품목, 연월) 단위 결과 캐시**.
#   ★★2026-08-30 정정 — 위 '근사' 판단은 **틀렸다**. 실측으로 월중 변동이 확인됐다:
#     AJR30027712-SUB2  0801/0814 110,475 → 0828 108,879
#     AJJ73040839       0801/0814  13,049 → 0828  12,981   (표본 5개 중 2개가 변동)
#     월 키로 캐시하면 일마감을 연속으로 돌릴 때 **월초 값이 그 달 전체에 박혀 비멱등**이 된다.
#     ⟹ 예고대로 **캐시 키를 일자로 낮춘다**. 마감은 그 시점을 확정하는 것이므로 정확이 우선이다.
_BOM_PX_CACHE = {}        # (item, yymm) -> 단가(0 이면 못 구함)
_BOM_ENG = [None]


def _bom_engine():
    """원가엔진 — ★공용 싱글턴(`common._get_cost_engine`)을 쓴다.

       예전에는 여기서 `NxCostEngine()` 을 **따로** 만들었다. 그러면
       원가 화면이 이미 데워 둔 엔진을 못 쓰고 **매 프로세스마다 콜드 스타트**를 다시 겪는다
       (실측 2026-08-29: _prd_price_bom 1차 30.5초 / 2차 0.7초 — 차이가 전부 엔진 예열이다).
       공용 엔진은 `warm_all()` 예열 + 커넥션 헬스체크 + 락을 갖췄다. 하나만 쓰는 것이 옳다.
    """
    try:
        from common import _get_cost_engine, _COST_LOCK
        with _COST_LOCK:
            return _get_cost_engine()
    except Exception:
        pass
    # 공용 엔진을 못 얻으면 종전 방식으로 폴백(화면이 빈손이 되지 않게)
    eng = _BOM_ENG[0]
    try:
        if eng is not None and eng.alive():
            return eng
    except Exception:
        pass
    try:
        from common import NxCostEngine
        if NxCostEngine is None:
            return None
        _BOM_ENG[0] = NxCostEngine()
        return _BOM_ENG[0]
    except Exception:
        _BOM_ENG[0] = None
        return None


def _prd_price_bom(cur, target, need):
    """② BOM 부품 매입가 합산 — 단가를 못 구한 품목만 원가엔진 material_u 로 채운다(§13-5).
       원가엔진은 레거시 diff0 검증본이고 **라우팅이 필요없다**(가공비가 아니라 재료비라서).
       ★(품목,as-of일자) 캐시 + 엔진 싱글턴으로 반복 호출 시 재계산을 피한다."""
    out = {}
    if not need:
        return out
    ym = str(target)          # ★as-of 일자 전체(월 키는 월초 값이 달 전체에 박힌다)
    # ★BOM 이 없는 품목은 엔진에 넣지 않는다 — 어차피 0 이 나오는데 품목당 ~0.14초를 쓴다.
    #   실측(2026-08-28): 310품목 42.2초 소요 · 보강 **0건**. 전부 헛돌았다.
    #   ★★소스 교정(2026-08-29) — 이 필터가 `nx.bom` 을 봤는데 **엔진은 `nx.bom_header` 를 쓴다**
    #     (`NxCostEngine._load_hasbom`). SUB·은납 반제품은 `nx.bom` 에 부모로 없고
    #     `bom_header` 에만 있어 **전부 스킵**됐다 → 단가 0 → 재고금액에서 빠졌다.
    #     실측(용접 재고): 단가없음 98품번 중 84개 스킵 · 그중 76개는 엔진이 단가를 구할 수 있었다
    #           = **51,657,231원이 0 으로 계상**(AJR30027712-SUB2 7.7M · AJR30004702-SUB 5.9M …).
    #     ⟹ 필터 소스를 **엔진과 같은 `nx.bom_header`** 로 맞춘다. 헛도는 호출을 막는 목적은
    #        그대로 두면서, 엔진이 실제로 계산할 수 있는 품목을 놓치지 않는다.
    need = list(need)
    if need:
        has = set()
        for i in range(0, len(need), 500):
            part = [str(x).strip().upper() for x in need[i:i + 500]]
            ph = ",".join("?" * len(part))
            cur.execute(f"""SELECT DISTINCT UPPER(LTRIM(RTRIM(item_code))) FROM nx.bom_header
                             WHERE UPPER(LTRIM(RTRIM(item_code))) IN ({ph})""", *part)
            has |= {str(r[0]) for r in cur.fetchall()}
        skipped = [it for it in need if str(it).strip().upper() not in has]
        for it in skipped:                      # 조회 반복을 막기 위해 0 으로 캐시
            _BOM_PX_CACHE.setdefault((it, ym), 0.0)
        need = [it for it in need if str(it).strip().upper() in has]
    miss = [it for it in need if (it, ym) not in _BOM_PX_CACHE]
    if miss:
        eng = _bom_engine()
        if eng is not None:
            for it in miss:
                try:
                    _BOM_PX_CACHE[(it, ym)] = float(eng.material_u(it, target) or 0)
                except Exception:
                    _BOM_PX_CACHE[(it, ym)] = 0.0
        else:
            for it in miss:
                _BOM_PX_CACHE[(it, ym)] = 0.0
    for it in need:
        v = _BOM_PX_CACHE.get((it, ym), 0.0)
        if v:
            out[it] = (v, "BOM부품합산")
    return out


def _prd_base(cur, target):
    """기초 = 직전 확정 PRD 스냅샷. 없으면 레거시 2502 생산 월마감 시드."""
    # ★TOP 1 을 뽑고 나서 target 조건을 검사하면, 그 아래 쓸 수 있는 마감이 있어도
    #   레거시 시드로 떨어진다(MAT 에서 실측된 것과 같은 결함 — §19). 후보를 훑어 첫 유효분을 쓴다.
    cur.execute("""SELECT ptype, period FROM nx.period_close
                    WHERE domain='PRD' AND close_flag=1
                      AND (ptype='D' AND period < ? OR ptype='M')
                    ORDER BY CASE WHEN ptype='D' THEN period ELSE period+'99' END DESC""", target)
    for pt, per in cur.fetchall():
        end = per if pt == 'D' else _month_end(per)
        if end < target:
            st = {}
            for it, lo, q, amt, av in _snapshot_rows(cur, 'PRD', pt, per, with_loc=True):
                q = float(q or 0); amt = float(amt or 0)
                st[(str(it), str(lo))] = [q, (amt / q) if q else float(av or 0)]
            if st:
                return st, end, f"확정 스냅샷({'일' if pt=='D' else '월'}마감 {per})"
    cur.execute("""SELECT UPPER(LTRIM(RTRIM(A.MAT_CODE))), ISNULL(A.gagong_proc_code,''),
                          SUM(CAST(A.STOCK_QTY AS float))
                     FROM PARTNER_ERP_TEST3.nx.PR_T_MONTH_STOCK_WH A WHERE A.STOCK_YYMM='2502'
                    GROUP BY UPPER(LTRIM(RTRIM(A.MAT_CODE))), ISNULL(A.gagong_proc_code,'')""")
    seed = cur.fetchall()          # ★같은 커서로 _prd_price 를 호출하기 전에 결과를 반드시 소진할 것
    px, _ic = _prd_price(cur, '250228')  # (안 그러면 pending result set 이 날아가 기초가 빈다 — 실제 겪음)
    st = {}
    for it, lo, q in seed:
        lo = "" if str(lo).strip() == "P0001" else str(lo).strip()
        st[(str(it), lo)] = [float(q or 0), (px.get(str(it)) or (0.0,))[0]]
    if not st:
        raise HTTPException(400, "생산 기초를 찾을 수 없습니다 — 레거시 2502 생산 월마감도 없습니다.")
    return st, '250228', "레거시 2502 생산 월마감 시드"


def _snap_prd(cur, ptype, period):
    """★생산 마감 = 이동평균법(매입가 기반, §12-8). 축=(품목×재고위치). 반환 (행수, 기준설명)."""
    import datetime as _dt
    target = period if ptype == "D" else _month_end(period)
    state, base_ymd, src = _prd_base(cur, target)
    try:
        b = _dt.date(2000 + int(base_ymd[:2]), int(base_ymd[2:4]), int(base_ymd[4:6])) + _dt.timedelta(days=1)
        start = f"{b.year % 100:02d}{b.month:02d}{b.day:02d}"
    except ValueError:
        start = base_ymd
    px, _ic = _prd_price(cur, target)
    moves = _prd_moves(cur, start, target) if start <= target else {}
    # ★② BOM 부품합산 — ①③ 으로 못 채운 품목만 원가엔진으로 보강(§13-5)
    need = sorted({k[0] for ymd in moves for k in moves[ymd] if k[0] not in px}
                  | {k[0] for k in state if k[0] not in px})
    px.update(_prd_price_bom(cur, target, need))
    agg = {}
    for ymd in sorted(moves):
        if ymd > target:
            continue
        for k, mv in moves[ymd].items():
            q0, a0 = state.get(k, [0.0, 0.0])
            pq = mv["inq"]
            if pq > 0:                                    # 입고 = 그 시점 자재단가로 가중평균
                c = (px.get(k[0]) or (a0,))[0]
                avg = ((q0 * a0 + pq * c) / (q0 + pq)) if q0 > 0 else c
            else:
                avg = a0
            state[k] = [q0 + mv["net"], avg]
            a = agg.setdefault(k, [0.0, 0.0])
            a[0] += mv["inq"]; a[1] += mv["outq"]
    # ★단가 보정 — 전개구간에 생산창고 입고가 없어 기초 단가(0)가 그대로 굳은 품목은
    #   **자재(MAT) 단가를 그대로 받는다**. 생산재고 단가의 원천은 자재이므로 자재가 먼저 값을 갖고
    #   생산은 그것을 받는 것이 옳다(대표 지적 2026-08-27).
    #   실증: BCUP1S-2.4*20.2(OD) 는 자재 단가 158.51 이 있는데 2502 이후 생산창고 입고가 0건이라
    #        기초 시드 0 이 유지돼 생산에서만 단가0 이었다.
    fixed = 0
    for k, v in state.items():
        if abs(v[1]) < 1e-9:
            c = (px.get(k[0]) or (0.0,))[0]
            if c:
                v[1] = c; fixed += 1
    out_rows = []
    for (it, lo), (q, a) in state.items():
        i, o = agg.get((it, lo), (0.0, 0.0))
        out_rows.append((it, lo, q, q * a, a, i, o))
    n = _snap_bulk(cur, "PRD", ptype, period, out_rows)
    return n, f"{target}(이동평균·매입가·기초 {base_ymd} {src}·단가보정 {fixed})"


# ===================== 스냅샷 적재 — 배치 INSERT (T4 성능, 2026-08-27) =====================
# ★행 단위 cur.execute 로 넣으면 품목당 1회 왕복이라 자재 일마감 1건에 58초가 걸렸다(2,441행).
#   pyodbc fast_executemany + executemany 로 한 번에 보낸다. 값·결과는 동일.
_SNAP_INS = """INSERT INTO nx.stock_snapshot
                 (domain,ptype,period,item_code,loc,stock_qty,stock_amt,avg_cost,in_qty,out_qty,close_dt)
               VALUES(?,?,?,?,?,?,?,?,?,?,GETDATE())"""


def _snap_bulk(cur, domain, ptype, period, rows):
    """rows=[(item, loc, qty, amt, cost, inq, outq)] → 멱등 DELETE 후 배치 적재. 반환 행수.

       ★확정 스냅샷 제외 규칙 (대표 확정)
         ① 빈 품번 · 잔량 0
         ② **단가 0**   — 단가 원천이 없는 것은 **잘못된 재고일 확률이 높다**(2026-08-28).
         ③ **음수 수량** — 실물이 음수일 수 없다. 컷오버 정리대상(X1).
       ★②③ 은 **수량·금액 모두** 스냅샷에서 뺀다(행 자체를 적재하지 않음).
         빠진 것들은 `/api/close/anomaly` 리포트로 노출되어 사라지지 않는다.
       ※이 규칙 때문에 레거시(단가0·음수 포함)와 수량 대조 시 범위를 맞춰야 한다
         — 레거시 중 "잔량>0 AND 단가<>0" 과 비교."""
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain=? AND ptype=? AND period=?", domain, ptype, period)
    cur.execute("IF OBJECT_ID('nx.stock_snapshot_drop','U') IS NOT NULL DELETE FROM nx.stock_snapshot_drop "
                "WHERE domain=? AND ptype=? AND period=?", domain, ptype, period)
    data = []; drop = []
    for item, loc, q, amt, cost, inq, outq in rows:
        item = str(item or "").strip().upper()
        if not item or abs(q) < 1e-9:          # ① 빈 품번·잔량0
            continue
        rc = round(cost, 4)                    # ★저장되는 값(반올림 후)으로 판정해야 한다.
        if q < 0:                              # ③ 음수 수량 → 제외 + 기록
            drop.append((item, str(loc or ""), q, amt, rc, "음수수량")); continue
        if abs(rc) < 1e-9:                     # ② 단가0 → 제외 + 기록. 반올림 전 값으로 보면
            drop.append((item, str(loc or ""), q, amt, rc, "단가0")); continue
        data.append((domain, ptype, period, item[:50], str(loc or "")[:20],
                     round(q, 4), round(amt, 4), rc, round(inq, 4), round(outq, 4)))
    # ★제외분 보존 — '잘못된 재고'가 조용히 사라지지 않게 남긴다(대표 확정 2026-08-28).
    #   컷오버 때 이 목록은 **이관하지 않는다**(X1). 매달 무엇을 인식하지 않았는지 추적 가능.
    cur.execute("""IF OBJECT_ID('nx.stock_snapshot_drop','U') IS NULL
        CREATE TABLE nx.stock_snapshot_drop(
          domain varchar(10) NOT NULL, ptype char(1) NOT NULL, period varchar(6) NOT NULL,
          item_code varchar(50) NOT NULL, loc varchar(20) NOT NULL CONSTRAINT DF_drop_loc DEFAULT(''),
          stock_qty decimal(18,4) NULL, stock_amt decimal(18,4) NULL, avg_cost decimal(18,4) NULL,
          reason varchar(20) NULL, close_dt datetime NULL)""")
    if drop:
        cur.executemany("""INSERT INTO nx.stock_snapshot_drop
              (domain,ptype,period,item_code,loc,stock_qty,stock_amt,avg_cost,reason,close_dt)
            VALUES(?,?,?,?,?,?,?,?,?,GETDATE())""",
            [(domain, ptype, period, it[:50], lo[:20], round(q, 4), round(a, 4), c, rs)
             for it, lo, q, a, c, rs in drop])
    if not data:
        return 0
    try:
        cur.fast_executemany = True
    except Exception:
        pass
    cur.executemany(_SNAP_INS, data)
    return len(data)


SNAPPERS = {"MAT": _snap_mat, "PRD": _snap_prd, "SAL": _snap_sal}


# ===================== 마감 실행 / 해제 =====================
@router.get("/api/close/anomaly")
def close_anomaly(domain: str = Query("MAT"), ptype: str = Query("M"), period: str = Query("")):
    """★확정 스냅샷 **제외분** 리포트 — "무엇을 재고로 인식하지 않았는가".

       마감 계산은 당월 입·출고를 전부 반영한다. 그 **결과**가 아래면 확정 재고에서 뺀다:
         ② **단가 0**   — 단가 원천이 없다 = 잘못된 재고일 확률이 높다
         ③ **음수 수량** — 우리 시스템은 음수를 허용하지 않는다
                          (실제 가드 = routers/stock.py 의 `_mat_avail` 비교 — 2026-08-28 구동 검증)
       뺀 것은 `nx.stock_snapshot_drop` 에 보존되어 **여기서 드러난다**(대표 확정 2026-08-28
       "잘못된 것이 보여지게 하는 것이 맞다"). **컷오버 때 이 재고는 이관하지 않는다**(X1).
       각 항목에 원인 분류를 붙여 조치 주체를 알 수 있게 한다."""
    d = str(domain).strip().upper(); t = str(ptype).strip().upper(); p = str(period).strip()
    cn = _nx(); cur = cn.cursor()
    try:
        if not p:                       # 기간 미지정 = 그 도메인의 최종 확정 기간
            cur.execute("""SELECT TOP 1 period FROM nx.period_close
                            WHERE domain=? AND ptype=? AND close_flag=1 ORDER BY period DESC""", d, t)
            r = cur.fetchone()
            if not r:
                return {"domain": d, "ptype": t, "period": None, "rows": [], "summary": {}}
            p = r[0]
        cur.execute("SELECT COUNT(*), ISNULL(SUM(stock_qty),0), ISNULL(SUM(stock_amt),0) FROM nx.stock_snapshot "
                    "WHERE domain=? AND ptype=? AND period=?", d, t, p)
        kn, kq, ka = cur.fetchone()
        cur.execute("""IF OBJECT_ID('nx.stock_snapshot_drop','U') IS NULL SELECT TOP 0 '' item_code, '' loc,
                          CAST(0 AS decimal(18,4)) stock_qty, CAST(0 AS decimal(18,4)) stock_amt,
                          CAST(0 AS decimal(18,4)) avg_cost, '' reason
                       ELSE SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(loc,''), stock_qty, stock_amt, avg_cost, ISNULL(reason,'')
                              FROM nx.stock_snapshot_drop WHERE domain=? AND ptype=? AND period=?""", d, t, p)
        drops = [(str(a), str(b), float(c or 0), float(e or 0), float(f or 0), str(g)) for a, b, c, e, f, g in cur.fetchall()]
        # 원인 분류 — 매입 전표 유무/금액 유무
        buy = {}
        if drops:
            ph = ','.join('?' * len(TA_IN_TAGS))
            cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))),
                                   SUM(CAST(MAINT_QTY AS float)), SUM(CAST(MAINT_AMT AS float))
                              FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT
                             WHERE MAINT_TAG IN ({ph}) GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", *TA_IN_TAGS)
            buy = {str(a): (float(b or 0), float(c or 0)) for a, b, c in cur.fetchall()}
        cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item")
        nm = {str(a): b for a, b in cur.fetchall()}

        def cause(it, reason):
            # ★라벨 주의: buy 는 **전 기간** 매입 이력이다. 마감 시점(as-of) 단가와 다르다.
            #   실측(2026-08-28): 단가0 제외분 56건은 **레거시 월마감도 전부 단가 0**
            #   = 우리가 못 채운 게 아니라 애초에 단가원이 없다. "회수가능" 표현은 오해를 부른다.
            if reason == "음수수량":
                return "음수재고 — 미기록 입고 또는 과대 출고. 컷오버 미이관"
            b = buy.get(it)
            if b and b[0] > 0 and b[1] > 0: return "단가0 — 과거 매입이력은 있으나 마감시점 단가 없음"
            if b and b[0] > 0:              return "단가0 — 금액0 입고만 있음"
            if not b:                       return "단가0 — 매입이력 없음"
            return "단가0 — 기타"

        rows = [{"kind": rs, "item": it, "nm": nm.get(it, ""), "loc": lo,
                 "qty": round(q, 3), "amt": round(a, 0), "cost": c, "cause": cause(it, rs)}
                for it, lo, q, a, c, rs in sorted(drops, key=lambda x: -abs(x[2]))[:1000]]
        from collections import Counter
        return {"domain": d, "ptype": t, "period": p,
                "kept": {"품목": kn, "수량": round(float(kq), 3), "금액": round(float(ka), 0)},
                "summary": {"제외 총건": len(drops),
                            "단가0": sum(1 for x in drops if x[5] == "단가0"),
                            "음수수량": sum(1 for x in drops if x[5] == "음수수량"),
                            "제외 수량": round(sum(x[2] for x in drops), 3),
                            "제외 금액": round(sum(x[3] for x in drops), 0),
                            "원인별": dict(Counter(r["cause"] for r in rows))},
                "rows": rows}
    finally:
        cn.close()


@router.post("/api/close/run")
def close_run(payload: dict = Body(...)):
    """마감 실행 = ①스냅샷 확정(가능 도메인) + ②잠금.
       가드: 이미 마감 / 직전 기간 미마감(기초 연쇄의존) / 미래 기간."""
    d, t, p = _norm(payload.get("domain"), payload.get("ptype"), payload.get("period"))
    user = str(payload.get("user", "") or "web").strip()
    # ★원자성: 스냅샷 확정과 잠금은 한 트랜잭션(부분실패 시 스냅샷만 남는 사고 방지 — 게이트C에서 실제 발생)
    cn = _nx_tx(); cur = cn.cursor()
    try:
        _assert_can_close(cur, user, "마감")
        _ledger_cache_clear()      # ★확정값이 바뀌므로 수불장 캐시를 버린다
        if _is_closed(cur, d, t, p):
            raise HTTPException(409, f"{DOMAINS[d]} {p} 는 이미 마감되었습니다.")
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd'), FORMAT(GETDATE(),'yyMM')")
        today, curym = cur.fetchone()
        if (t == "D" and p > today) or (t == "M" and p > curym):
            raise HTTPException(400, f"미래 기간({p})은 마감할 수 없습니다.")
        # ★연쇄 가드 — 직전 기간이 마감돼 있어야 한다(기초가 이어짐). 단 첫 마감은 예외.
        cur.execute("SELECT COUNT(*) FROM nx.period_close WHERE domain=? AND ptype=? AND close_flag=1", d, t)
        if cur.fetchone()[0]:
            prev = _prev_period(t, p)
            if not _is_closed(cur, d, t, prev):
                cur.execute("""SELECT TOP 1 period FROM nx.period_close
                               WHERE domain=? AND ptype=? AND close_flag=1 ORDER BY period DESC""", d, t)
                last = cur.fetchone()[0]
                if p > last:
                    raise HTTPException(409, f"직전 기간({prev})이 마감되지 않았습니다 — 마감은 순서대로 해야 합니다(최종 마감 {last}).")
        n, asof = (0, None)
        if d in SNAP_READY:
            if d == "MAT":
                # ★자재 확정이 바뀌면 **자재 단가를 참조하는 캐시만** 낡는다 → 그것만 무효화.
                #   _BOM_PX_CACHE(BOM 부품합산)는 원가엔진이 단가마스터를 읽으므로 자재 마감과 무관하다.
                #   이걸 같이 지웠더니 자재 마감마다 생산이 콜드 재계산(241초)돼
                #   트랜잭션 커넥션이 유휴로 끊기는 사고가 났다(2026-08-27). 범위를 좁힌다.
                _PRD_PX_CACHE.clear(); _MAT_BUY_CACHE.clear()
            n, asof = SNAPPERS[d](cur, t, p)
        note = ((f"스냅샷 {n}품목(기준 {asof})" + ("" if str(asof)==str(p if t=="D" else "") or (t=="D" and str(asof)==str(p)) else " ※이월"))
                if d in SNAP_READY else "잠금만(스냅샷 2단계)")
        # ★UPSERT — 해제 후 재마감이 가능해야 한다(PK=domain+ptype+period, 기존행은 flag=0으로 남아있음)
        cur.execute("""UPDATE nx.period_close SET close_flag=1, close_user=?, close_dt=GETDATE(),
                              reopen_user=NULL, reopen_dt=NULL, note=?
                        WHERE domain=? AND ptype=? AND period=?""", user, note, d, t, p)
        if cur.rowcount == 0:
            cur.execute("""INSERT INTO nx.period_close(domain,ptype,period,close_flag,close_user,close_dt,note)
                           VALUES(?,?,?,1,?,GETDATE(),?)""", d, t, p, user, note)
        cn.commit()
        return {"ok": True, "domain": d, "ptype": t, "period": p, "snapshot_rows": n, "snapshot_asof": asof,
                "msg": f"{DOMAINS[d]} {'일' if t=='D' else '월'}마감 완료" + (f" · 스냅샷 {n:,}품목 확정" if n else " · 잠금만(스냅샷은 2단계)")}
    finally:
        cn.close()


@router.post("/api/close/cancel")
def close_cancel(payload: dict = Body(...)):
    """마감 해제(reopen) = 잠금 해제 + 확정 스냅샷 제거 + 로그.
       가드: 미마감 / 후속 기간이 마감돼 있으면 해제 불가(기초 연쇄의존)."""
    d, t, p = _norm(payload.get("domain"), payload.get("ptype"), payload.get("period"))
    user = str(payload.get("user", "") or "web").strip()
    cn = _nx_tx(); cur = cn.cursor()      # ★원자성: 스냅샷 제거 + 잠금해제 동시
    try:
        _assert_can_close(cur, user, "마감 해제")
        _ledger_cache_clear()      # ★확정값이 바뀌므로 수불장 캐시를 버린다
        if not _is_closed(cur, d, t, p):
            raise HTTPException(409, f"{DOMAINS[d]} {p} 는 마감 상태가 아닙니다.")
        cur.execute("""SELECT TOP 1 period FROM nx.period_close
                       WHERE domain=? AND ptype=? AND close_flag=1 AND period>? ORDER BY period""", d, t, p)
        nxt = cur.fetchone()
        if nxt:
            raise HTTPException(409, f"후속 기간({nxt[0]})이 마감되어 있어 해제할 수 없습니다 — 최근 기간부터 순서대로 해제하세요.")
        cur.execute("DELETE FROM nx.stock_snapshot WHERE domain=? AND ptype=? AND period=?", d, t, p)
        removed = cur.rowcount
        cur.execute("""UPDATE nx.period_close SET close_flag=0, reopen_user=?, reopen_dt=GETDATE()
                       WHERE domain=? AND ptype=? AND period=?""", user, d, t, p)
        cn.commit()
        return {"ok": True, "domain": d, "ptype": t, "period": p, "snapshot_removed": removed,
                "msg": f"{DOMAINS[d]} {'일' if t=='D' else '월'}마감 해제 완료" + (f" · 확정 스냅샷 {removed:,}품목 제거" if removed else "")}
    finally:
        cn.close()


# ===================== C7 · 수불장 = 확정 스냅샷(기초) + 전표(이동) 파생 =====================
# ★정본 설계 = STOCK_CLOSE_HANDOFF.md §7-1.
#   "수불장은 원장이 아니라 **파생 뷰**다. 저장하지 않고 매번 계산한다."
#     기말 = 기초(직전 확정 스냅샷) + 입고 − 출고 ± 조정
#   ⟹ 저장하지 않으므로 드리프트가 구조적으로 생길 수 없다.
#
# ★왜 만드나(C7): 지금 자재수불장 화면(live_api.matledger)은 레거시 임시테이블을 읽는다.
#     월 = PU_T_MONTH_STOCK_WH
#     일 = PU_T_MONTH_STOCK_WH_DAILY  ← 레거시 w_pu_stock_260 이 **조회할 때마다 TRUNCATE** 하는 임시테이블
#   즉 일자 수불장 내용이 "누가 언제 조회했느냐"에 따라 바뀐다. 이 화면을 여기로 옮긴다.
#
# ★엔진 재사용: 마감이 쓰는 것과 **완전히 같은** _mv_base/_mv_moves/_mv_step 을 쓴다.
#   화면과 마감이 다른 식으로 계산하면 값이 갈린다(그게 미러/클린 드리프트의 원인이었다).
#   그래서 여기서 다시 계산하지 않고 마감 엔진을 그대로 호출한다.
# ===================== 생산(PRD) 수불장 — 마감과 동일 전개 =====================
# ★_snap_prd 와 **같은 순서**로 돈다(기초 → 단가 → 일자 전개 → 단가0 보정).
#   화면이 따로 계산하면 값이 갈린다 — §21 교훈. 여기서 새로 짜지 않고 같은 헬퍼만 호출한다.
#   축 = (품목 × 재고위치). 가공창고 P0001 = loc '' · 용접은 라인코드.
# ★수불장 결과 캐시 — 같은 (도메인,기간) 재조회를 즉시 응답한다.
#   실측(2026-08-28) 생산 수불장 콜드 54초(단가 13 + 이동 20 + BOM 20). 화면에서 못 쓴다.
#   ★캐시는 **조회 전용**이다. 재고를 바꾸는 쓰기가 나면 반드시 _ledger_cache_clear() 로 버린다
#     — 안 그러면 화면이 옛 값을 보여준다(하드룰: 캐시 stale 금지, PERF_OPTIMIZATION_DESIGN).
_LEDGER_CACHE = {}
_LEDGER_CACHE_MAX = 12


def _ledger_cache_clear():
    """재고 쓰기·마감 후 호출 — 수불장 캐시를 통째로 버린다."""
    _LEDGER_CACHE.clear()
    _PRD_PX_CACHE.clear()
    _SAL_PX_CACHE.clear()


def ledger_cached(cur, domain, fr6, to6):
    """★생산/영업 수불장 — **캐시 공유 진입점**. (rows, breaks, basis) 반환.

       왜 함수로 빼나 — 캐시가 엔드포인트 안에만 있으면 다른 화면(생산재고조회)이
       같은 계산을 **처음부터 다시** 한다(실측 2026-08-29: 재고조회 41초).
       여기로 모으면 수불장을 한 번 본 뒤 재고조회는 즉시, 반대도 같다.
       ★캐시는 조회 전용 — 재고 쓰기 후에는 `_ledger_cache_clear()` 가 버린다.
    """
    ck = (domain, fr6, to6)
    if ck in _LEDGER_CACHE:
        return _LEDGER_CACHE[ck]
    rows, breaks, basis = (_prd_ledger if domain == "PRD" else _sal_ledger)(cur, fr6, to6)
    # ★_attach_item_info 를 캐시 안에서 부른다 — 밖에 두면 최종입고일 집계(170만행)를
    #   매 조회마다 다시 돌아 캐시가 무의미해진다(2026-08-28 실측: 2차도 11초).
    _attach_item_info(cur, rows, to6)
    if len(_LEDGER_CACHE) >= _LEDGER_CACHE_MAX:
        _LEDGER_CACHE.pop(next(iter(_LEDGER_CACHE)))
    _LEDGER_CACHE[ck] = (rows, breaks, basis)
    return _LEDGER_CACHE[ck]


def _prd_ledger(cur, fr6, to6):
    """생산 수불장 행 목록 + 불변식 위반. 반환 (rows, breaks)."""
    state, base_ymd, src = _prd_base(cur, fr6)
    # 기초 스냅샷 시점 ~ 조회 시작 전날까지는 전표로 이월(이중계상 금지 §7-7 #2)
    pre_start, pre_end = _next_ymd(base_ymd), _prev_ymd(fr6)
    # ★단가는 **조회 종료일 기준 하나**로 전 구간을 전개한다 — 마감(_snap_prd)과 동일.
    #   _prd_price 는 as-of 일자로 매입 누계를 계산하는데 캐시는 **월 단위**다.
    #   기간 시작일로 먼저 호출하면 '월초 as-of' 단가가 캐시에 박혀 기간 전체에 쓰이고,
    #   같은 2607 을 마감은 월말 단가로 전개해 값이 갈린다(2026-08-28 실측: 금액차 216건,
    #   AAA31179503 단가 2,906 vs 마감 2,699). ⟹ 호출 시점을 마감과 맞춘다.
    px, _ic = _prd_price(cur, to6)

    def _step(st, mv_day, px):
        """하루 전개 — _snap_prd 본문과 동일 식."""
        for k, mv in mv_day.items():
            q0, a0 = st.get(k, [0.0, 0.0])
            pq = mv["inq"]
            if pq > 0:
                c = (px.get(k[0]) or (a0,))[0]
                avg = ((q0 * a0 + pq * c) / (q0 + pq)) if q0 > 0 else c
            else:
                avg = a0
            st[k] = [q0 + mv["net"], avg]

    if pre_start <= pre_end:
        pre = _prd_moves(cur, pre_start, pre_end)
        for y in sorted(pre):
            _step(state, pre[y], px)
    begin = {k: [v[0], v[1]] for k, v in state.items()}

    moves = _prd_moves(cur, fr6, to6)
    need = sorted({k[0] for y in moves for k in moves[y] if k[0] not in px}
                  | {k[0] for k in state if k[0] not in px})
    px.update(_prd_price_bom(cur, to6, need))

    agg = {}
    for y in sorted(moves):
        for k, mv in moves[y].items():
            a = agg.setdefault(k, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0,
                                   "adj": 0.0, "adjamt": 0.0})
            a["inq"] += mv["inq"]; a["outq"] += mv["outq"]; a["adj"] += mv["adj"]
            a["inamt"] += mv["inq"] * ((px.get(k[0]) or (0.0,))[0])
        _step(state, moves[y], px)
        for k, mv in moves[y].items():           # 출고·조정은 갱신 후 평균으로(§22 실측)
            _av = state.get(k, [0.0, 0.0])[1]
            agg[k]["outamt"] += mv["outq"] * _av
            agg[k]["adjamt"] += mv["adj"] * _av

    # 단가0 보정 — 자재 단가를 승계(§14: 자재가 먼저 단가를 갖고 생산은 받는다)
    for st_ in (begin, state):
        for k, v in st_.items():
            if abs(v[1]) < 1e-9:
                c = (px.get(k[0]) or (0.0,))[0]
                if c:
                    v[1] = c

    rows, breaks = [], []
    for k in sorted(set(begin) | set(agg) | set(state)):
        if not str(k[0] or "").strip():      # 빈 품번 제외 — 마감(_snap_bulk)과 같은 규칙
            continue
        bq, bavg = begin.get(k, [0.0, 0.0])
        a = agg.get(k, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0, "adj": 0.0, "adjamt": 0.0})
        eq, eavg = state.get(k, [0.0, 0.0])
        if (abs(bq) < 1e-9 and abs(a["inq"]) < 1e-9 and abs(a["outq"]) < 1e-9
                and abs(a["adj"]) < 1e-9 and abs(eq) < 1e-9):
            continue
        if abs((bq + a["inq"] - a["outq"] + a["adj"]) - eq) > 0.001:
            breaks.append({"item": k[0], "loc": k[1], "축": "수량", "기초": round(bq, 4),
                           "입고": round(a["inq"], 4), "출고": round(a["outq"], 4),
                           "조정": round(a["adj"], 4), "기말": round(eq, 4)})
        _ba, _ea = bq * bavg, eq * eavg
        _va = _ea - (_ba + a["inamt"] - a["outamt"] + a["adjamt"])
        rows.append({"cd": k[0], "loc": k[1], "va": round(_va, 2),
                     "bq": round(bq, 4), "ba": round(_ba, 2),
                     "iq": round(a["inq"], 4), "ia": round(a["inamt"], 2),
                     "oq": round(a["outq"], 4), "oa": round(a["outamt"], 2),
                     "tq": round(a["adj"], 4), "ta": round(a["adjamt"], 2),
                     "sq": round(eq, 4), "sa": round(_ea, 2), "avg": round(eavg, 4)})
    return rows, breaks, f"기초 {base_ymd} {src}"


# ===================== 영업(SAL) 수불장 — 판가 기반 이동평균 =====================
# ★정본: STOCK_CLOSE_HANDOFF.md §7-4 — 영업은 **판가 기반 이동평균**(대표 확정 2026-08-27).
#   축 = 품목(위치 없음). 이동 원천 = 레거시 제품재고조회 040(`live_api.salesstock`) 과
#   **같은 UNION 분기**를 일자별로 편 것. 040 은 기간 요약이라 일자 전개가 안 되므로
#   분기·부호를 그대로 두고 일자 컬럼을 살려 재작성한다(생산 PRD 와 같은 방식).
# ★단가 = **nx.price_item 단일 소스**(사급가·LG판가 업로드 대상, vendor 1010/1020 · TAGS/TAGE).
#   레거시 미러 pr_m_item_cost 는 읽지 않는다 — 폴백도 없다(하드룰 CLAUDE.md §1-9-1).
def _sal_moves(cur, d_from, d_to):
    """[d_from,d_to] 일자별 완성품 이동 → {ymd: {item: {net,inq,outq,adj}}}. 040 분기 그대로."""
    T3 = "PARTNER_ERP_TEST3.nx."
    out = {}

    def slot(y, item):
        return out.setdefault(str(y), {}).setdefault(
            str(item or "").strip().upper(), {"net": 0.0, "inq": 0.0, "outq": 0.0, "adj": 0.0})

    # ① 생산입고(tag P, in_part 없음)  ② 창고입고(tag B,V)
    cur.execute(f"""SELECT a.maint_ymd, UPPER(a.item_code), SUM(CAST(a.maint_qty AS float))
                      FROM {T3}sa_t_stock_maint a
                     WHERE a.maint_ymd BETWEEN ? AND ? AND a.maint_qty<>0
                       AND ((a.maint_tag='P' AND ISNULL(a.in_part_code,'')='') OR a.maint_tag IN ('B','V'))
                     GROUP BY a.maint_ymd, UPPER(a.item_code)""", d_from, d_to)
    for y, it, q in cur.fetchall():
        slot(y, it)["inq"] += float(q or 0)

    # ③ 직납 자재입고(out_wh_gubun='2') — 부호 반전
    cur.execute(f"""SELECT a.maint_ymd, UPPER(a.mat_code), SUM(-CAST(a.maint_qty AS float))
                      FROM {T3}pu_t_stock_maint a
                     WHERE a.maint_ymd BETWEEN ? AND ? AND ISNULL(a.out_wh_gubun,'1')='2'
                     GROUP BY a.maint_ymd, UPPER(a.mat_code)""", d_from, d_to)
    for y, it, q in cur.fetchall():
        slot(y, it)["inq"] += float(q or 0)

    # ④ 창고출하(tag J,8,R)
    cur.execute(f"""SELECT a.maint_ymd, UPPER(a.item_code), SUM(-CAST(a.maint_qty AS float))
                      FROM {T3}sa_t_stock_maint a
                     WHERE a.maint_ymd BETWEEN ? AND ? AND a.maint_tag IN ('J','8','R') AND a.maint_qty<>0
                     GROUP BY a.maint_ymd, UPPER(a.item_code)""", d_from, d_to)
    for y, it, q in cur.fetchall():
        slot(y, it)["outq"] += float(q or 0)

    # ⑤ 재고조정(tag 2) — ★040 은 `qty = basic+inq-etc-outq` 로 **etc 를 뺀다**.
    #   여기서는 adj 를 더하는 형태로 통일하되 부호를 040 과 맞춘다(etc = −maint_qty 이므로 adj = +maint_qty).
    cur.execute(f"""SELECT a.maint_ymd, UPPER(a.item_code), SUM(CAST(a.maint_qty AS float))
                      FROM {T3}sa_t_stock_maint a
                     WHERE a.maint_ymd BETWEEN ? AND ? AND a.maint_tag='2' AND a.maint_qty<>0
                     GROUP BY a.maint_ymd, UPPER(a.item_code)""", d_from, d_to)
    for y, it, q in cur.fetchall():
        slot(y, it)["adj"] += float(q or 0)

    for y in out:
        for d in out[y].values():
            d["net"] = d["inq"] - d["outq"] + d["adj"]
    return out


_SAL_PX_CACHE = {}


def _sal_price(cur, target):
    """완성품 판가 = **`nx.price_item` 단일 소스** (사급가·LG판가 업로드 대상).
       vendor 1010=SAC / 1020=RAC · price_type TAGS=내수 / TAGE=수출 · apply_ymd as-of 최신.

       ★2026-08-28 교체: 종전엔 `pr_m_item_cost(S/E)`(레거시 미러)를 읽었다. 하드룰 위반이다
         (CLAUDE.md §1-9-1 · DO_NOT_USE_FIELDS §18 — 단가는 `nx.price_*` 단일 소스).
       ★**폴백 없음.** 미러로 되돌아가지 않는다. price_item 에 없으면 **단가 0 으로 드러낸다**
         (LG 판가 업로드 누락이므로 업로드로 풀 일이지, 몰래 옛 값을 끌어올 일이 아니다).
       ★왜 이게 컷오버에 필수인가: 레거시가 은퇴하면 미러 sync 자체가 사라져 `pr_m_item_cost` 는
         그 시점 값으로 얼어붙는다. 미러를 읽으면 **컷오버 후 재고 금액이 영원히 갱신되지 않는다.**
         실측 예고편 — AJR75712801 의 8/6 인상(275,425)이 미러에 안 와 옛 값(267,680)으로 평가됐다.
       ★★캐시 키 = **as-of 일자 전체**(2026-08-30 결함수정). 종전엔 연월만 키로 썼는데
         값은 as-of 일자다 → 일마감 연속 실행 시 월초 단가가 달 전체에 박혀 **비멱등**이었다
         (실측: D 260828 일괄 677,272,841 vs 단독 703,546,042)."""
    ck = str(target)
    if ck in _SAL_PX_CACHE:
        return _SAL_PX_CACHE[ck]
    cur.execute("""SELECT item_code, price FROM (
                     SELECT item_code, price,
                            ROW_NUMBER() OVER (PARTITION BY UPPER(item_code) ORDER BY apply_ymd DESC) rn
                       FROM nx.price_item
                      WHERE apply_ymd <= ? AND vendor_code IN ('1010','1020')
                        AND price_type IN ('TAGS','TAGE')) z
                    WHERE rn=1""", target)
    px = {str(r[0]).strip().upper(): float(r[1] or 0) for r in cur.fetchall()}
    _SAL_PX_CACHE[ck] = px
    return px


def _sal_base(cur, target):
    """기초 = target 직전 확정 SAL 스냅샷(∪제외분). 없으면 040 recipe 로 target 직전까지 계산."""
    cur.execute("""SELECT ptype, period FROM nx.period_close
                    WHERE domain='SAL' AND close_flag=1 AND (ptype='D' OR ptype='M')
                    ORDER BY CASE WHEN ptype='D' THEN period ELSE period+'99' END DESC""")
    for pt, per in cur.fetchall():
        end = per if pt == 'D' else _month_end(per)
        if end < target:
            st = {}
            for it, _lo, q, amt, av in _snapshot_rows(cur, 'SAL', pt, per):
                q = float(q or 0); amt = float(amt or 0)
                st[str(it)] = [q, (amt / q) if q else float(av or 0)]
            if st:
                return st, end, f"확정 스냅샷({'일' if pt == 'D' else '월'}마감 {per})"
    # 시드 = 040 recipe 를 target 직전까지 굴린 값(레거시 월기초 2502 부터)
    from live_api import salesstock
    prev = _prev_ymd(target)
    res = salesstock(dfrom=prev[:4] + "01", dto=prev, source="live", zero="1")
    px = _sal_price(cur, prev)
    st = {}
    for r in (res.get("rows") or []):
        cd = str(r.get("cd") or r.get("mat") or "").strip().upper()
        if not cd:
            continue
        q = float(r.get("qty") or 0)
        st[cd] = [q, px.get(cd, float(r.get("cost") or 0))]
    return st, prev, "040 recipe 시드"


def _sal_ledger(cur, fr6, to6):
    """영업 수불장 행 + 불변식 위반. 반환 (rows, breaks, basis)."""
    state, base_ymd, src = _sal_base(cur, fr6)
    px = _sal_price(cur, to6)                      # ★종료일 기준 단일 단가(§23 교훈)

    def _step(st, mv_day):
        for it, mv in mv_day.items():
            q0, a0 = st.get(it, [0.0, 0.0])
            pq = mv["inq"]
            if pq > 0:                             # 입고 = 그 시점 판가로 가중평균
                c = px.get(it, a0)
                avg = ((q0 * a0 + pq * c) / (q0 + pq)) if q0 > 0 else c
            else:
                avg = a0
            st[it] = [q0 + mv["net"], avg]

    pre_start, pre_end = _next_ymd(base_ymd), _prev_ymd(fr6)
    if pre_start <= pre_end:
        pre = _sal_moves(cur, pre_start, pre_end)
        for y in sorted(pre):
            _step(state, pre[y])
    begin = {k: [v[0], v[1]] for k, v in state.items()}

    moves = _sal_moves(cur, fr6, to6)
    agg = {}
    for y in sorted(moves):
        for it, mv in moves[y].items():
            a = agg.setdefault(it, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0,
                                    "adj": 0.0, "adjamt": 0.0})
            a["inq"] += mv["inq"]; a["outq"] += mv["outq"]; a["adj"] += mv["adj"]
            a["inamt"] += mv["inq"] * px.get(it, 0.0)
        _step(state, moves[y])
        for it, mv in moves[y].items():            # 출고·조정은 갱신 후 평균으로
            _av = state.get(it, [0.0, 0.0])[1]
            agg[it]["outamt"] += mv["outq"] * _av
            agg[it]["adjamt"] += mv["adj"] * _av

    # 단가0 보정 — ★같은 소스(nx.price_item) 안에서 as-of 값을 채우는 것이다.
    #   다른 테이블로 폴백하지 않는다(하드룰 §18). price_item 에 없으면 0 으로 남겨 드러낸다.
    for st_ in (begin, state):
        for it, v in st_.items():
            if abs(v[1]) < 1e-9:
                c = px.get(it, 0.0)
                if c:
                    v[1] = c

    rows, breaks = [], []
    for it in sorted(set(begin) | set(agg) | set(state)):
        if not str(it or "").strip():
            continue
        bq, bavg = begin.get(it, [0.0, 0.0])
        a = agg.get(it, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0, "adj": 0.0, "adjamt": 0.0})
        eq, eavg = state.get(it, [0.0, 0.0])
        if (abs(bq) < 1e-9 and abs(a["inq"]) < 1e-9 and abs(a["outq"]) < 1e-9
                and abs(a["adj"]) < 1e-9 and abs(eq) < 1e-9):
            continue
        if abs((bq + a["inq"] - a["outq"] + a["adj"]) - eq) > 0.001:
            breaks.append({"item": it, "축": "수량", "기초": round(bq, 4), "입고": round(a["inq"], 4),
                           "출고": round(a["outq"], 4), "조정": round(a["adj"], 4), "기말": round(eq, 4)})
        _ba, _ea = bq * bavg, eq * eavg
        _va = _ea - (_ba + a["inamt"] - a["outamt"] + a["adjamt"])
        rows.append({"cd": it, "loc": "", "va": round(_va, 2),
                     "bq": round(bq, 4), "ba": round(_ba, 2),
                     "iq": round(a["inq"], 4), "ia": round(a["inamt"], 2),
                     "oq": round(a["outq"], 4), "oa": round(a["outamt"], 2),
                     "tq": round(a["adj"], 4), "ta": round(a["adjamt"], 2),
                     "sq": round(eq, 4), "sa": round(_ea, 2), "avg": round(eavg, 4)})
    return rows, breaks, f"기초 {base_ymd} {src}"


def _mat_ledger(cur, fr6, to6, zero):
    """자재 수불장 계산 — 캐시 대상. 반환 (rows, breaks, basis).
       ★엔드포인트에서 직접 계산하던 것을 함수로 뺐다: PRD/SAL 과 같이 캐시에 태우기 위함.
         (2026-08-28 실측 — 캐시 없으면 매 조회 18초)"""
    # ── 기초 = fr6 직전의 확정 스냅샷까지 전개한 상태 ──────────────────
    #   ★_mv_base 는 "target 직전 확정 스냅샷"을 준다. 그 시점부터 fr6 전날까지는
    #     전표로 이어 붙여야 기초가 정확하다(이중계상 금지 — §7-7 #2).
    state, base_ymd, src = _mv_base(cur, fr6)
    scope = _mv_scope(cur)
    pre_start = _next_ymd(base_ymd)
    pre_end = _prev_ymd(fr6)
    if pre_start <= pre_end:
        pre = _mv_moves(cur, pre_start, pre_end)
        for y in sorted(pre):
            _mv_step(state, pre[y], scope)
    begin = {k: [v[0], v[1]] for k, v in state.items()}          # 기초 스냅
    # ── 기간 이동 ────────────────────────────────────────────────────
    moves = _mv_moves(cur, fr6, to6)
    # ★기초에도 단가보정을 적용한다 — 마감(_snap_mat)이 하는 것과 **같은 처리**여야
    #   같은 기간을 조회했을 때 금액이 갈리지 않는다(2026-08-28 실측: 33건 금액차의 원인).
    _bpx0 = _mv_buyprice(cur, _prev_ymd(fr6))
    for _m, _v in state.items():
        if abs(_v[1]) < 1e-9 and abs(_v[0]) > 1e-9:
            _c = _bpx0.get(_m, 0.0)
            if _c:
                _v[1] = _c
    agg = {}
    for y in sorted(moves):
        for mat, mv in moves[y].items():
            a = agg.setdefault(mat, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0,
                                     "trans": 0.0, "transamt": 0.0})
            a["inq"] += mv["inq"]; a["inamt"] += mv["pamt"]
            a["outq"] += mv["outq"]; a["trans"] += mv["trans"]
        _mv_step(state, moves[y], scope)
        # ★출고·조정 금액은 **그날 평균을 갱신한 뒤**의 단가로 잡는다.
        #   우리 엔진은 하루를 한 묶음으로 처리한다(§7-4) — 그날 입고가 평균을 올린 뒤
        #   그 평균으로 출고가 나간다. 갱신 전 단가를 쓰면 금액 항등식이 깨진다
        #   (2026-08-28 실측: 기초+입−출+조정 이 기말보다 1.46억 초과).
        #   검산: (q0+pq)·avg = q0·a0 + pamt 이므로
        #         기말금액 = (q0+inq−outq+trans)·avg = 기초금액 + 입고금액 − outq·avg + trans·avg
        for mat, mv in moves[y].items():
            _av = state.get(mat, [0.0, 0.0])[1]
            a = agg[mat]
            a["outamt"] += mv["outq"] * _av
            a["transamt"] += mv["trans"] * _av
    # ── 행 구성 ──────────────────────────────────────────────────────
    # 기말도 동일하게 보정(마감과 같은 순서: 전개 → 단가0 보정)
    _bpx = _mv_buyprice(cur, to6)
    for _m, _v in state.items():
        if abs(_v[1]) < 1e-9 and abs(_v[0]) > 1e-9:
            _c = _bpx.get(_m, 0.0)
            if _c:
                _v[1] = _c
    codes = {c for c in set(begin) | set(agg) | set(state) if c in scope and str(c or "").strip()}
    rows, breaks = [], []
    for c in sorted(codes):
        bq, bavg = begin.get(c, [0.0, 0.0])
        a = agg.get(c, {"inq": 0.0, "inamt": 0.0, "outq": 0.0, "outamt": 0.0,
                        "trans": 0.0, "transamt": 0.0})
        eq, eavg = state.get(c, [0.0, 0.0])
        if not zero and abs(bq) < 1e-9 and abs(a["inq"]) < 1e-9 and abs(a["outq"]) < 1e-9                and abs(a["trans"]) < 1e-9 and abs(eq) < 1e-9:
            continue
        # ★불변식 검산 — 어기면 버그다(§7-2). 화면에 숨기지 말고 드러낸다.
        #   수량축과 **금액축을 모두** 본다(금액만 깨지는 결함이 실제로 있었다).
        if abs((bq + a["inq"] - a["outq"] + a["trans"]) - eq) > 0.001:
            breaks.append({"item": c, "축": "수량", "기초": round(bq, 4), "입고": round(a["inq"], 4),
                           "출고": round(a["outq"], 4), "조정": round(a["trans"], 4),
                           "기말": round(eq, 4)})
        # ★금액축은 "평가조정"을 명시 열로 둔다 — 숨기지 않는다.
        #   이동평균에는 금액 항등식을 **의도적으로** 깨는 규칙이 둘 있다:
        #     ① 단가0 보정 — 전개 후에도 단가가 0 인 품목에 실매입 가중평균을 사후 주입(§13-5)
        #     ② 재고<=0 에서 매입 refill 시 단가 리셋 — 마이너스재고 평균폭발 방지
        #   둘 다 "이동"이 아니라 "단가를 고쳐 끼우는" 행위라 기초+입−출±조정 으로 설명되지 않는다.
        #   잔차를 버리거나 오차로 숨기면 화면 합계가 안 맞는다 ⟹ **평가조정(va)** 으로 드러낸다.
        #     기초금액 + 입고 − 출고 + 조정 + 평가조정 = 기말금액   (항상 성립)
        _ba, _ea = bq * bavg, eq * eavg
        _va = _ea - (_ba + a["inamt"] - a["outamt"] + a["transamt"])
        rows.append({"cd": c, "va": round(_va, 2),
                     "bq": round(bq, 4), "ba": round(bq * bavg, 2),
                     "iq": round(a["inq"], 4), "ia": round(a["inamt"], 2),
                     "oq": round(a["outq"], 4), "oa": round(a["outamt"], 2),
                     "tq": round(a["trans"], 4), "ta": round(a["transamt"], 2),
                     "sq": round(eq, 4), "sa": round(eq * eavg, 2), "avg": round(eavg, 4)})
    _attach_item_info(cur, rows, to6)
    return rows, breaks, (f"기초 {base_ymd} {src}" + (f" → 전표이월 {pre_start}~{pre_end}" if pre_start <= pre_end else ""))


@router.get("/api/close/ledger")
def close_ledger(domain: str = Query("MAT"), d_from: str = Query(""), d_to: str = Query(""),
                 zero: int = Query(0), q: str = Query(""), nocache: int = Query(0)):
    """수불장(파생). [d_from,d_to] 기간의 품목별 기초·입·출·조정·기말 + 이동평균 단가.
       zero=1 이면 기초·이동·기말이 모두 0 인 품목도 표시(기본 숨김).
       q = 품번/품명 부분일치 필터.
       ★불변식 기초+입−출±조정=기말 을 서버에서 검산해 breaks 로 돌려준다(0이어야 정상)."""
    d = (domain or "MAT").strip().upper()
    if d not in ("MAT", "PRD", "SAL"):
        raise HTTPException(400, "자재(MAT)·생산(PRD)·영업(SAL)만 지원합니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        to6 = _d6(d_to) or _today6()
        fr6 = _d6(d_from) or (to6[:4] + "01")
        if fr6 > to6:
            fr6, to6 = to6, fr6
        if d in ("PRD", "SAL"):
            # ★재고조회와 **같은 캐시**를 쓴다(ledger_cached) — 한쪽을 본 뒤 다른 쪽은 즉시.
            #   nocache=1 = **검증 전용** 우회. 멱등성 시험은 캐시를 맞으면 무의미해진다
            #   (같은 객체를 돌려주니 항상 '같음'이 나온다). TestBed 가 이걸 쓴다.
            if int(nocache or 0):
                _LEDGER_CACHE.pop((d, fr6, to6), None)
            rows, breaks, basis = ledger_cached(cur, d, fr6, to6)
            if q:
                k = q.strip().upper()
                rows = [r for r in rows if k in r["cd"] or k in str(r.get("nm", "")).upper()]
            tot = {f: round(sum(r[f] for r in rows), 2)
                   for f in ("bq", "ba", "iq", "ia", "oq", "oa", "tq", "ta", "va", "sq", "sa")}
            va_rows = [r["cd"] for r in rows if abs(r["va"]) > 1.0]
            return {"domain": d, "from": fr6, "to": to6, "count": len(rows), "rows": rows,
                    "totals": tot, "basis": basis, "invariant_breaks": breaks,
                    "valuation_adjust": {"count": len(va_rows), "amount": tot["va"],
                                         "items": va_rows[:50],
                                         "why": "단가0 보정·단가 리셋 — 이동이 아니라 단가를 고쳐 끼운 분"},
                    "note": ("생산 수불장 = 확정 스냅샷 기초 + 480 분기 전표 파생. 축=(품목×재고위치)." if d == "PRD"
                             else "영업 수불장 = 확정 스냅샷 기초 + 040 분기 전표 파생. 단가=판가 기반 이동평균.")}
        _ck = (d, fr6, to6, zero)
        if _ck in _LEDGER_CACHE:
            rows, breaks, basis = _LEDGER_CACHE[_ck]
        else:
            rows, breaks, basis = _mat_ledger(cur, fr6, to6, zero)
            if len(_LEDGER_CACHE) >= _LEDGER_CACHE_MAX:
                _LEDGER_CACHE.pop(next(iter(_LEDGER_CACHE)))
            _LEDGER_CACHE[_ck] = (rows, breaks, basis)
        if q:
            k = q.strip().upper()
            rows = [r for r in rows if k in r["cd"] or k in str(r.get("nm", "")).upper()]
        tot = {f: round(sum(r[f] for r in rows), 2)
               for f in ("bq", "ba", "iq", "ia", "oq", "oa", "tq", "ta", "va", "sq", "sa")}
        va_rows = [r["cd"] for r in rows if abs(r["va"]) > 1.0]
        return {"domain": d, "from": fr6, "to": to6, "count": len(rows), "rows": rows, "totals": tot,
                "basis": basis,
                "invariant_breaks": breaks,
                "valuation_adjust": {"count": len(va_rows), "amount": tot["va"], "items": va_rows[:50],
                                     "why": "단가0 보정·마이너스재고 단가리셋 — 이동이 아니라 단가를 고쳐 끼운 분(설계상 정상)"},
                "note": "확정 스냅샷 + 전표 파생(저장 안 함). 단가=이동평균. 레거시 임시테이블 미사용."}
    finally:
        cn.close()


def _attach_item_info(cur, rows, to6=None):
    """품번 → 품명/규격/단위/소분류/매입처/최종입고일. ★정본 = nx.item(미러 아님, CLAUDE.md §1-9).
       ★컬럼을 임의로 줄이지 않는다(CLAUDE.md §1-6) — 기존 자재수불장 화면이 쓰던 항목을 모두 채운다."""
    if not rows:
        return
    codes = [r["cd"] for r in rows]
    info, lastin = {}, {}
    for i in range(0, len(codes), 500):
        part = codes[i:i + 500]
        ph = ",".join("?" * len(part))
        cur.execute(f"""SELECT UPPER(i.item_code), ISNULL(i.item_name,''), ISNULL(i.item_spec,''),
                               ISNULL(i.unit,''), ISNULL(i.sgroup,''), ISNULL(i.in_cust,''),
                               ISNULL(c.cust_desc,''), ISNULL(c.cust_type,'')
                          FROM nx.item i
                          LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE = i.in_cust
                         WHERE UPPER(i.item_code) IN ({ph})""", *part)
        for cd, nm, sp, un, sg, ic, cnm, ct in cur.fetchall():
            info[cd] = (nm, sp, un, sg, ic, cnm, ct)
    if to6:
        # ★최종입고일 = 입고 tag 전표의 마지막 일자(조회 종료일까지). 라이브 전표가 정본.
        #   ★청크마다 돌리면 170만행을 8번 스캔한다 — **한 번만** 집계하고 파이썬에서 룩업한다.
        _ph = ",".join("?" * len(TA_IN_TAGS))
        cur.execute(f"""SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), MAX(MAINT_YMD)
                          FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT
                         WHERE MAINT_YMD <= ? AND MAINT_TAG IN ({_ph}) AND MAT_CODE IS NOT NULL
                         GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE)))""", to6, *TA_IN_TAGS)
        for cd, ymd in cur.fetchall():
            lastin[cd] = str(ymd or "")
    for r in rows:
        nm, sp, un, sg, ic, cnm, ct = info.get(r["cd"], ("", "", "", "", "", "", ""))
        r["nm"] = nm; r["spec"] = sp; r["unit"] = un; r["sg"] = sg
        r["custcd"] = ic; r["cust"] = cnm; r["ctype"] = ct
        r["lastin"] = lastin.get(r["cd"], "")
