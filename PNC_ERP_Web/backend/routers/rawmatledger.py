# -*- coding: utf-8 -*-
"""협력사 원소재(동관) 수불장 — 규격축(협력사 × 재질·외경), 단위 KG.
   불출(협력사입고,+) = 자재불출 tag5 원소재(210·KG·E/G) 규격별 kg  (자재불출집계표 소스)
   소진(협력사출고,−) = 입고완제품 × 동중량(견적서 규격별·coop 협의치수)  (소요엔진 weight_explode 계열)
   잔량 = 기초0(2026-07) + Σ불출 − Σ소진, 업체별 마감window. 정산 = 잔량×(현물−사급가).
   ★계산부 = weight_calc.compute_quote_lme(ym) 재사용(협력사별 specs=규격별 out/in/diff/amt). 여기선 2607~선택월 누적.
   ★조회 전용. 절삭 협력사(_COOP_CUST_VENDOR) 대상.
"""
from fastapi import APIRouter, Query, Request
from routers.auth import require_user, scope_cust
import weight_calc as W

router = APIRouter()
START_YM = "2607"           # 원소재 수불 개시(기초0)

_LME_CACHE = {}             # ym -> compute_quote_lme(ym) 결과(월 5s·캐시)

def _lme(ym):
    if ym not in _LME_CACHE:
        _LME_CACHE[ym] = W.compute_quote_lme(ym)
    return _LME_CACHE[ym]

def _months(to_ym):
    """START_YM ~ to_ym(YYMM) 월 리스트."""
    def idx(s): return int(s[:2]) * 12 + (int(s[2:]) - 1)
    a, b = idx(START_YM), idx(to_ym)
    return [f"{k//12:02d}{k%12+1:02d}" for k in range(a, b + 1)]

def _accum(to_ym):
    """2607~to_ym 누적: {cust: {(mat,od): {out,in,amt}}} + 협력사명·현물/사급(최신월)."""
    acc = {}; latest = {}
    for ym in _months(to_ym):
        r = _lme(ym)
        for cc, d in r.items():
            for s in d.get("specs", []):
                key = (s["mat"] or "일반", s["od"])
                e = acc.setdefault(cc, {}).setdefault(key, {"out": 0.0, "in": 0.0, "amt": 0.0})
                e["out"] += (s["out"] or 0); e["in"] += (s["in"] or 0); e["amt"] += (s["amt"] or 0)
                latest[(cc, key)] = (s["spot"], s["sagub"])
    return acc, latest


@router.get("/api/rawmatledger/list")
def rawmatledger_list(request: Request, cust: str = Query(""), to_ym: str = Query(""),
                      mat: str = Query(""), sign: str = Query("")):
    """좌: (협력사 × 동관 규격) 불출/소진/잔량 kg + 정산. to_ym=YYMM(기본 최신 데이터월).
       ★소속 강제 — 협력사 계정은 자기 것만."""
    cust = scope_cust(require_user(request), cust)
    to_ym = (to_ym or "").strip() or _latest_ym()
    acc, latest = _accum(to_ym)
    rows = []
    for cc, specs in acc.items():
        if cust and cc != cust:
            continue
        for (m, od), e in specs.items():
            if mat and mat not in m:
                continue
            bal = round(e["out"] - e["in"], 1)
            if sign == "1" and not bal > 0.5: continue
            if sign == "-1" and not bal < -0.5: continue
            if sign == "0" and abs(bal) > 0.5: continue
            sp, sg = latest.get((cc, (m, od)), (None, None))
            rows.append({"cust_code": cc, "custnm": _CUSTNM.get(cc, cc), "mat": m, "od": od,
                         "sent": round(e["out"], 1), "used": round(e["in"], 1), "bal": bal,
                         "spot": sp, "sagub": sg, "amt": round(e["amt"])})
    rows.sort(key=lambda r: (r["custnm"], -abs(r["amt"])))
    custs = sorted({(cc, _CUSTNM.get(cc, cc)) for cc in acc}, key=lambda x: x[1])
    tot = {"sent": round(sum(r["sent"] for r in rows), 1), "used": round(sum(r["used"] for r in rows), 1),
           "bal": round(sum(r["bal"] for r in rows), 1), "amt": round(sum(r["amt"] for r in rows))}
    return {"rows": rows, "custs": [{"code": c, "nm": n} for c, n in custs], "tot": tot, "to_ym": to_ym}


@router.get("/api/rawmatledger/detail")
def rawmatledger_detail(request: Request, cust: str = Query(...), mat: str = Query(...),
                        od: float = Query(...), to_ym: str = Query("")):
    """우: 선택 (협력사 × 규격) 월별 불출/소진 + running balance(기초0 @2607)."""
    cust = scope_cust(require_user(request), cust)
    to_ym = (to_ym or "").strip() or _latest_ym()
    bal = 0.0; out = []
    for ym in _months(to_ym):
        r = _lme(ym).get(cust, {})
        o = i = 0.0
        for s in r.get("specs", []):
            if (s["mat"] or "일반") == mat and abs((s["od"] or 0) - od) < 0.001:
                o += (s["out"] or 0); i += (s["in"] or 0)
        prev = bal; bal = prev + (o - i)
        out.append({"ym": ym, "in_qty": round(o, 1), "out_qty": round(i, 1),
                    "prev_qty": round(prev, 1), "stock_qty": round(bal, 1)})
    return {"rows": out, "final_qty": round(bal, 1)}


# 협력사명 + 최신 데이터월 (weight_calc._COOP_CUST_VENDOR 기반)
_CUSTNM = {}
def _latest_ym():
    import datetime
    return datetime.datetime.now().strftime("%y%m")

def _load_custnm():
    if _CUSTNM:
        return
    try:
        cn = W._ro(); cur = cn.cursor()
        codes = list(W._COOP_CUST_VENDOR.keys())
        ph = ",".join("?" for _ in codes)
        cur.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM nx.CM_M_CUST WHERE CUST_CODE IN ({ph})", *codes)
        for c, n in cur.fetchall():
            _CUSTNM[str(c).strip()] = str(n).strip()
        cn.close()
    except Exception:
        pass
_load_custnm()
