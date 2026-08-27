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
from common import _nx, _nx_tx, _conn

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
    cur.execute("SELECT ITEM_CODE FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_SGROUP LIKE '99%'")
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


def _month_end(period):
    """YYMM → 그 달 말일 YYMMDD."""
    import calendar as _cal
    y, m = 2000 + int(period[:2]), int(period[2:])
    return f"{period}{_cal.monthrange(y, m)[1]:02d}"


def _snap_mat_movavg(cur, ptype, period):   # ★DEPRECATED(§9 총평균 채택) — 대조·롤백용 보존
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
                      JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON a.MAT_CODE = m.ITEM_CODE
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
                     JOIN PARTNER_ERP.dbo.PR_M_ITEM m ON a.MAT_CODE = m.ITEM_CODE
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = 'T' GROUP BY a.MAT_CODE""", d_from, d_to)
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)
    cur.execute("""SELECT a.MAT_CODE, SUM(CAST(a.MAINT_QTY AS float))
                     FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT a
                    WHERE a.MAINT_YMD BETWEEN ? AND ? AND a.MAINT_TAG = '2' GROUP BY a.MAT_CODE""", d_from, d_to)
    for m, q in cur.fetchall():
        slot(m)["tq"] += float(q or 0)

    # 소모품(ITEM_SGROUP >= '990') 제외 + 품목마스터 미등록 탈락 (레거시 WHERE/JOIN 동일)
    cur.execute("SELECT ITEM_CODE, ISNULL(ITEM_SGROUP,'') FROM PARTNER_ERP.dbo.PR_M_ITEM")
    sg = {str(r[0]).strip().upper(): str(r[1]) for r in cur.fetchall()}
    R = {m: d for m, d in R.items() if m and m in sg and sg[m] < '990'}
    R = {m: d for m, d in R.items()          # 레거시 HAVING — 전부 0 이면 제외
         if any(abs(d[k]) > 1e-9 for k in ("bq", "ba", "iq", "ia", "oq", "oa", "tq", "ta"))}

    # 단가 마스터 폴백(레거시 UPDATE U3/V3). 레거시는 ITEM_COST×기준환율이나 환율은 창 변수 →
    # 원화 단가만 사용(외화 품목 2건 수준 차이, 검증기록 §7-2).
    cur.execute("""SELECT ITEM_CODE, ITEM_COST FROM (
                     SELECT ITEM_CODE, CAST(ITEM_COST AS float) ITEM_COST,
                            ROW_NUMBER() OVER(PARTITION BY ITEM_CODE ORDER BY COST_APPLY_YMD DESC) rn
                       FROM PARTNER_ERP.dbo.PR_M_ITEM_COST
                      WHERE COST_TAG = '1' AND COST_APPLY_YMD <= ?
                        AND ISNULL(CURRENCY,'KRW') IN ('KRW','')) t WHERE rn = 1""", d_to[:4] + '99')
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


def _snap_mat_month(cur, period):
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


def _snap_mat_day(cur, period):
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


def _snap_mat(cur, ptype, period):
    """자재 스냅샷 디스패처 — 월=총평균 확정 / 일=수량확정+직전 월단가 평가."""
    return _snap_mat_month(cur, period) if ptype == "M" else _snap_mat_day(cur, period)



# ===================== 마감/해제 권한 게이트 — C5 (2026-08-27) =====================
# 마감·해제는 회계 확정/되돌리기다 → **명시 권한자만**(deny by default).
#   ① 시스템관리자 role(nx.web_user 의 roles) → 허용
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
    # ① 시스템관리자
    try:
        cur.execute("SELECT udata FROM nx.web_user WHERE user_id='__ALL__'")
        r = cur.fetchone()
        if r and r[0]:
            import json as _json
            for x in (_json.loads(r[0]) or []):
                if str(x.get("id", "")).strip() == u and "시스템관리자" in (x.get("roles") or []):
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
    """스냅샷 멱등 적재. rows=[(item, loc, qty, amt, cost, inq, outq)]. 잔량 0 제외(대표 확정)."""
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain=? AND ptype=? AND period=?",
                domain, ptype, period)
    n = 0
    for item, loc, qty, amt, cost, inq, outq in rows:
        item = str(item or "").strip().upper()
        if not item or abs(qty) < 1e-9:      # 잔량 0 제외 — MAT 과 동일 규칙
            continue
        cur.execute("""INSERT INTO nx.stock_snapshot
                         (domain,ptype,period,item_code,loc,stock_qty,stock_amt,avg_cost,in_qty,out_qty,close_dt)
                       VALUES(?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                    domain, ptype, period, item[:50], str(loc or "")[:20],
                    round(qty, 4), round(amt, 4), round(cost, 4), round(inq, 4), round(outq, 4))
        n += 1
    return n


def _snap_prd(cur, ptype, period):
    """생산 스냅샷 = 생산재고조회(480) recipe 를 target 시점으로 확정. 반환 (행수, 기준일)."""
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


def _snap_sal(cur, ptype, period):
    """완성/제품 스냅샷 = 제품재고조회(040) recipe 를 target 시점으로 확정. 반환 (행수, 기준일)."""
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
    return n, f"{target}(제품재고조회 040 recipe)"


SNAPPERS = {"MAT": _snap_mat, "PRD": _snap_prd, "SAL": _snap_sal}


# ===================== 마감 실행 / 해제 =====================
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
