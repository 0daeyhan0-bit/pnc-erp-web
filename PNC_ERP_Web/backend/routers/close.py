# -*- coding: utf-8 -*-
"""마감관리 (시스템관리 > 마감관리) — 일/월 마감 실행·해제 + 현황.

설계 근거(기록):
  · nextgen-erp-close-settlement : 마감=잠금 · 일마감⊂월마감 · 해제는 권한자+로그 ·
                                   소급은 재개방이 아니라 당월 소급조정(조정전표는 열린 일자에만)
  · nextgen-erp-material-close   : "마감 시점에 스냅샷 생성 = 다음달 기초재고. 월마감·일마감 동일 개념."
  · STOCK_GATING_CLOSE_LOCK_RULES: 규칙B 마감된 기간 CRUD 금지

검증 근거(2026-08-27 전수대조): nx.mat_stock_daily 월말잔량 == 레거시 PU_T_MONTH_STOCK_WH
  2606 2,342/2,342 · 2607 2,534/2,534 = 100.00%, '레거시만' 1,195품목은 전부 재고0 → 갭 무해.
  ∴ 자재 스냅샷은 mat_stock_daily 를 확정(freeze)한다.

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
        cur.execute("SELECT MAX(ymd) FROM nx.mat_stock_daily")
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


# ===================== 스냅샷 확정 (마감 = f(원장) 확정) =====================
def _snap_mat(cur, ptype, period):
    """자재 스냅샷 확정 = nx.mat_stock_daily 의 해당 시점 잔량을 그대로 박는다(freeze).
       일마감=그 날 · 월마감=그 달 말일 시점. 재적재 멱등(같은 키 DELETE 후 재삽입).
       ★검증: 이 값이 레거시 PU_T_MONTH_STOCK_WH 와 2606/2607 전수 100.00% 일치(2026-08-27)."""
    if ptype == "D":
        asof = period
    else:                      # 월마감 = 그 달의 마지막 '데이터가 있는' 일자
        cur.execute("SELECT MAX(ymd) FROM nx.mat_stock_daily WHERE LEFT(ymd,4)=?", period)
        asof = cur.fetchone()[0]
        if not asof:
            raise HTTPException(400, f"{period} 월의 자재 일별잔량이 없습니다 — 일마감 빌더 실행 후 월마감하세요.")
    cur.execute("SELECT COUNT(*) FROM nx.mat_stock_daily WHERE ymd=?", asof)
    if not cur.fetchone()[0]:
        raise HTTPException(400, f"{asof} 자재 일별잔량이 없습니다 — 일마감 빌더(matclose_movavg_build.py) 실행 후 마감하세요.")
    cur.execute("DELETE FROM nx.stock_snapshot WHERE domain='MAT' AND ptype=? AND period=?", ptype, period)
    cur.execute("""INSERT INTO nx.stock_snapshot(domain,ptype,period,item_code,stock_qty,stock_amt,avg_cost,in_qty,out_qty,close_dt)
        SELECT 'MAT', ?, ?, UPPER(mat_code), SUM(stock_qty), SUM(stock_amt), MAX(avg_cost), SUM(in_qty), SUM(out_qty), GETDATE()
          FROM nx.mat_stock_daily WHERE ymd=? GROUP BY UPPER(mat_code)""", ptype, period, asof)
    return cur.rowcount, asof


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
        note = (f"스냅샷 {n}품목(기준 {asof})" if d in SNAP_READY else "잠금만(스냅샷 2단계)")
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
