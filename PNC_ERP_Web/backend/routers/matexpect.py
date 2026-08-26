# -*- coding: utf-8 -*-
"""자재예상매입 (구매/자재 · 조회전용 · MRP성 조달계획).
   설계 정본 = _schema/MAT_EXPECTED_PURCHASE_DESIGN.md.
   ★기존 정본 소비(재구현 금지): 예상소요=nx.plan_part_mat(+plan_mat_source 업체배분),
     실적소요=nx_soyo_engine.prod_soyo. 현재고=mat_stock_daily. 매입실적=PU_T_STOCK_MAINT.
   구현 단계: ②-a 예상소요(본 파일 최초) → ②-b 실적소요 → ③ 넷팅/필요수량 → ④ 화면.
   조회전용: 라이브 RO(_conn)·nx 읽기(_nx). 쓰기 없음.
"""
import datetime as _dt
from fastapi import APIRouter, Query
from common import _nx, _conn, _get_cost_engine
import nx_soyo_engine as _soyo  # 공용 소요엔진(prod_soyo) — 재구현 금지

router = APIRouter()

# ── 3분류 (설계 §3): CUST_TYPE(PR011) + LG 원재료사급(동) override ──
#   원소재 = 4 절삭원자재·5 설치원자재 + LG 원재료사급(동) / 사급 = 1 유상사급부품 / 그외 = 7·8·9·A / 협력사 6 = 가공비축(매입 아님)
_RAWMAT_SAGUB = {"2237", "2238", "2235", "2236"}  # LG 원재료사급(동): LS메탈-사급·HAILIANG·JINTIAN·심양금속
_CT_NAME = {"1": "유상사급부품", "4": "절삭원자재", "5": "설치원자재", "6": "절삭협력",
            "7": "절삭부자재", "8": "설치부자재", "9": "소모품", "A": "이지링크"}


def _grp(cust_type, cust_code):
    ct = (str(cust_type or "")).strip()
    cc = (str(cust_code or "")).strip()
    if cc in _RAWMAT_SAGUB:
        return "원소재"
    if ct in ("4", "5"):
        return "원소재"
    if ct == "1":
        return "사급"
    if ct in ("7", "8", "9", "A"):
        return "그외"
    if ct == "6":
        return "협력사"  # 가공비 축 — 매입액 아님(집계 제외 대상)
    return "미분류"


def _last_day(y, m):
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else (30 if m != 2 else (29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28))


def _ranges(ym):
    """ym=YYYYMM → (실적구간[fr,to], 예상구간[fr,to]) YYMMDD. 없으면 None.
       현재월: 실적[1~어제]+예상[오늘~말일]. 과거월: 전부 실적. 미래월: 전부 예상."""
    y, m = int(ym[:4]), int(ym[4:6])
    yy = ym[2:4]
    d1 = f"{yy}{m:02d}01"
    dL = f"{yy}{m:02d}{_last_day(y, m):02d}"
    tod = _dt.date.today()
    tod6 = f"{tod.year % 100:02d}{tod.month:02d}{tod.day:02d}"
    ymmm = int(ym[:6])
    cur = tod.year * 100 + tod.month
    if ymmm < cur:                       # 과거월: 전부 실적
        return (d1, dL), None
    if ymmm > cur:                       # 미래월: 전부 예상
        return None, (d1, dL)
    # 현재월
    yest = tod - _dt.timedelta(days=1)
    yest6 = f"{yest.year % 100:02d}{yest.month:02d}{yest.day:02d}"
    act = (d1, yest6) if yest6 >= d1 else None      # 1일이 오늘이면 실적 없음
    exp = (tod6, dL)
    return act, exp


def _name_maps(cur):
    """mat_code→품명, cust_code→(거래처명, cust_type)."""
    cur.execute("SELECT item_code, item_name FROM nx.item")
    itnm = {str(r[0]).strip().upper(): (r[1] or "") for r in cur.fetchall()}
    cur.execute("SELECT cust_code, cust_name, cust_type FROM nx.cust")
    cust = {str(r[0]).strip(): (r[1] or "", str(r[2] or "").strip()) for r in cur.fetchall()}
    return itnm, cust


@router.get("/api/matexpect")
def matexpect(axis: str = Query("prod"), ym: str = Query(""), grp: str = Query("")):
    """자재예상매입 소요 (②-a 예상소요 우선). axis=prod|sale · ym=YYYYMM · grp=원소재|사급|그외|전체.
       현재: 예상구간 소요(plan_part_mat×plan_mat_source 업체배분, 날짜필터) → 자재×업체×분류.
       ②-b(실적)·③(넷팅)은 후속. act_qty는 현재 0(스텁)."""
    if not ym:
        t = _dt.date.today(); ym = f"{t.year}{t.month:02d}"
    ym = ym.replace("-", "")[:6]
    act_rng, exp_rng = _ranges(ym)
    nx = _nx(); cur = nx.cursor()
    try:
        itnm, cust = _name_maps(cur)
        agg = {}  # (mat, vendor) → {exp, act}

        def _row(mat, vendor):
            k = (mat, vendor)
            if k not in agg:
                agg[k] = {"mat": mat, "vendor": vendor, "exp": 0.0, "act": 0.0}
            return agg[k]

        # ── ②-a 예상소요: 날짜필터 plan_part_mat × plan_mat_source 업체배분비율 ──
        if exp_rng:
            cur.execute("""
                SELECT UPPER(LTRIM(RTRIM(ppm.mat_code))) mat, ISNULL(r.vendor_code,'') vendor,
                       SUM(CAST(ppm.part_plan_qty AS float) * ISNULL(r.ratio,1.0)) qty
                FROM nx.plan_part_mat ppm
                LEFT JOIN (
                    SELECT s.work_order, UPPER(LTRIM(RTRIM(s.mat_code))) mat_code, s.vendor_code,
                           CAST(s.qty AS float)/NULLIF(t.tot,0) ratio
                    FROM nx.plan_mat_source s
                    JOIN (SELECT work_order, UPPER(LTRIM(RTRIM(mat_code))) mat_code, SUM(CAST(qty AS float)) tot
                          FROM nx.plan_mat_source GROUP BY work_order, UPPER(LTRIM(RTRIM(mat_code)))) t
                      ON t.work_order=s.work_order AND t.mat_code=UPPER(LTRIM(RTRIM(s.mat_code)))
                ) r ON r.work_order=ppm.work_order AND r.mat_code=UPPER(LTRIM(RTRIM(ppm.mat_code)))
                WHERE ppm.plan_ymd BETWEEN ? AND ?
                GROUP BY UPPER(LTRIM(RTRIM(ppm.mat_code))), ISNULL(r.vendor_code,'')""",
                exp_rng[0], exp_rng[1])
            for mat, vendor, qty in cur.fetchall():
                _row(mat, str(vendor or "").strip())["exp"] += float(qty or 0)

        # ── ②-b 실적소요: 완제품 완성수량 × prod_soyo(per-unit) ──
        #   드라이버(완제품 완성수량, 사용자 확정 2026-08-26):
        #     생산축(prod) = 제품입고(SA_T_STOCK_MAINT tag P = 바코드 가공 완제품 완성) + 설치·이지링크(출하 중 P에 없는 완제품)
        #     영업축(sale) = 출하실적(SA_T_SALE_DTL 전 완제품)
        #   ★제품입고 P = 완제품(ASSY)만 잡혀 SUB 이중계상 없음(생산완성→제품창고). 설치·이지링크는 바코드 미경유→출하로 보완.
        driver = {}
        if act_rng:
            lv = _conn(); lc = lv.cursor()
            try:
                if axis == "sale":
                    lc.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CAST(SALE_QTY AS float))
                        FROM PARTNER_ERP.dbo.SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?
                        GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", act_rng[0], act_rng[1])
                    for it, q in lc.fetchall():
                        driver[it] = driver.get(it, 0.0) + float(q or 0)
                else:  # 생산축
                    lc.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CAST(MAINT_QTY AS float))
                        FROM PARTNER_ERP.dbo.SA_T_STOCK_MAINT WHERE MAINT_TAG='P' AND MAINT_YMD BETWEEN ? AND ?
                        GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", act_rng[0], act_rng[1])
                    pset = set()
                    for it, q in lc.fetchall():
                        driver[it] = driver.get(it, 0.0) + float(q or 0); pset.add(it)
                    # 설치·이지링크 = 출하 중 제품입고(P)에 없는 완제품
                    lc.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CAST(SALE_QTY AS float))
                        FROM PARTNER_ERP.dbo.SA_T_SALE_DTL WHERE SALE_YMD BETWEEN ? AND ?
                        GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))""", act_rng[0], act_rng[1])
                    for it, q in lc.fetchall():
                        if it not in pset:
                            driver[it] = driver.get(it, 0.0) + float(q or 0)
            finally:
                lv.close()
        # 완제품 완성수량 × prod_soyo(per-unit) → 자재소요. 실적 vendor 귀속 = PR_M_ITEM.in_cust_code(설계 §4)
        if driver:
            eng = _get_cost_engine()
            cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(in_cust_code,'') FROM nx.PR_M_ITEM")
            incust = {r[0]: str(r[1]).strip() for r in cur.fetchall()}
            for it, dq in driver.items():
                if not dq:
                    continue
                try:
                    soyo = _soyo.prod_soyo(eng, it)
                except Exception:
                    continue
                for mc, per in soyo.items():
                    _row(mc, incust.get(mc, ""))["act"] += per * dq

        # ── 조립: 분류·이름·필터 ──
        rows = []
        for (mat, vendor), v in agg.items():
            cnm, cty = cust.get(vendor, ("", ""))
            g = _grp(cty, vendor)
            if g == "협력사":            # 가공비 축 제외
                continue
            if grp and grp != "전체" and g != grp:
                continue
            tot = v["exp"] + v["act"]
            if abs(tot) < 1e-9:
                continue
            rows.append({
                "mat_code": mat, "mat_name": itnm.get(mat, ""),
                "vendor_code": vendor, "vendor_name": cnm, "grp": g,
                "exp_qty": round(v["exp"], 2), "act_qty": round(v["act"], 2), "tot_qty": round(tot, 2),
            })
        rows.sort(key=lambda r: -r["tot_qty"])
        # 분류 요약
        summ = {}
        for r in rows:
            s = summ.setdefault(r["grp"], {"grp": r["grp"], "mats": 0, "tot": 0.0})
            s["mats"] += 1; s["tot"] += r["tot_qty"]
        return {
            "ym": ym, "axis": axis,
            "act_range": act_rng, "exp_range": exp_rng,
            "rows": rows, "cnt": len(rows), "summary": list(summ.values()),
            "note": "②-a 예상(plan_part_mat 배분)+②-b 실적(생산=제품입고P+설치/이지링크 출하·영업=출하 × prod_soyo). 넷팅(③) 후속.",
        }
    finally:
        nx.close()
