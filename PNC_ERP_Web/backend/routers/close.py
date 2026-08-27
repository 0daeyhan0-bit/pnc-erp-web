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
SNAP_READY = ("MAT",)      # 스냅샷 확정이 가능한 도메인(1단계). 그 외는 잠금만.


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


def _snap_mat(cur, ptype, period):
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
        if not mat:
            continue
        cur.execute("""INSERT INTO nx.stock_snapshot(domain,ptype,period,item_code,stock_qty,stock_amt,avg_cost,close_dt)
                       VALUES('MAT',?,?,?,?,?,?,GETDATE())""",
                    ptype, period, mat[:50], round(q, 4), round(q * a, 4), round(a, 4))
        n += 1
    return n, f"{target}({src}·기초 {base_ymd})"


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
            n, asof = _snap_mat(cur, t, p)
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
