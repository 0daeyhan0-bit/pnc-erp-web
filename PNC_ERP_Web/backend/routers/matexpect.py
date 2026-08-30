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
from common import _nx, _conn, NxCostEngine
import nx_soyo_engine as _soyo  # 공용 소요엔진(prod_soyo) — 재구현 금지

router = APIRouter()

# ── per-item prod_soyo 사전계산 캐시(nx.item_mat_soyo) + BOM 서명 가드 ──
#   캐시=완제품별 per-unit 자재소요(BOM 안정→BOM 변경시만 무효). 완성수량·재고·매입은 라이브.
#   ★sync 비종속(nx.bom_line 소스 종속)→컷오버 후에도 유효. 서명가드로 stale 원천차단(무접촉).
_ENG = None


def _eng():
    global _ENG
    if _ENG is None:
        _ENG = NxCostEngine()   # bare(warm 불요·prod_soyo는 v_pr_bom lazy만 사용)
    return _ENG


def _bom_sig(cur):
    """nx.bom_line 서명(행수+체크섬). 어떤 변경이든(sync/bom_save) 감지."""
    cur.execute("SELECT COUNT(*), ISNULL(CHECKSUM_AGG(BINARY_CHECKSUM(bom_id,child_item,qty,ISNULL(qty_pr,qty),ISNULL(except_flag,0))),0) FROM nx.bom_line")
    r = cur.fetchone()
    return "%s:%s" % (r[0], r[1])


def _ensure_soyo_cache(cur):
    """캐시테이블 보장 + BOM 서명 대조. 변경시 캐시·엔진 무효(비움)→lazy 재빌드 유도."""
    global _ENG
    cur.execute("""IF OBJECT_ID('nx.item_mat_soyo') IS NULL CREATE TABLE nx.item_mat_soyo(
        item_code varchar(30) NOT NULL, mat_code varchar(30) NOT NULL, per_unit float,
        CONSTRAINT pk_item_mat_soyo PRIMARY KEY(item_code,mat_code))""")
    cur.execute("IF OBJECT_ID('nx.item_mat_soyo_meta') IS NULL CREATE TABLE nx.item_mat_soyo_meta(id int PRIMARY KEY, bom_sig varchar(80), built_dt datetime)")
    sig = _bom_sig(cur)
    cur.execute("SELECT bom_sig FROM nx.item_mat_soyo_meta WHERE id=1")
    r = cur.fetchone()
    if (not r) or (r[0] != sig):
        _ENG = None                              # 엔진 in-memory BOM 캐시도 무효(stale 방지)
        cur.execute("TRUNCATE TABLE nx.item_mat_soyo")
        cur.execute("DELETE FROM nx.item_mat_soyo_meta WHERE id=1")
        cur.execute("INSERT INTO nx.item_mat_soyo_meta(id,bom_sig,built_dt) VALUES(1,?,getdate())", sig)
    return sig


def _soyo_of(cur, item):
    """완제품 per-unit 자재소요 {mat:per} — 캐시 우선, miss시 prod_soyo 계산+캐시(lazy).
       빈 결과(leaf/무BOM)는 sentinel('')로 마킹해 재계산 방지."""
    cur.execute("SELECT mat_code, per_unit FROM nx.item_mat_soyo WHERE item_code=?", item)
    rows = cur.fetchall()
    if rows:
        return {r[0]: r[1] for r in rows if r[0]}
    so = _soyo.prod_soyo(_eng(), item)
    if so:
        cur.executemany("INSERT INTO nx.item_mat_soyo(item_code,mat_code,per_unit) VALUES(?,?,?)",
                        [(item, mc, float(per)) for mc, per in so.items()])
    else:
        cur.execute("INSERT INTO nx.item_mat_soyo(item_code,mat_code,per_unit) VALUES(?,'',0)", item)
    return so

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
        return "부자재"
    if ct == "6":
        return "협력사"  # 가공비 축 — 매입액 아님(집계 제외 대상)
    return "미분류"


# ── ★BOM 근본 분류 (MAKE_TYPE + nx.bom.role) — soyo/BOM 단일 기반 (사용자 2026-08-26) ──
#   MAKE_TYPE: 1제작·2외주·3구매·4사급·5외주직납 (soyo _MKMAP). role: nx.bom.role(원소재/부자재/완성부품/…).
_RAW_ROLES = {"제작동관", "매입동관", "판재강판"}                       # 원소재(원재료)
_ETC_ROLES = {"단열재", "체결부자재", "포장재", "전장부품", "매입기타"}   # 부자재(그외)


def _grp_bom(mat, mkmap, rolemap):
    role = rolemap.get(mat, ""); mt = mkmap.get(mat, "")
    if role in _RAW_ROLES:
        return "원소재"                       # 동관·강판 = 원소재(사급/구매/제작 무관)
    if role == "용접봉":
        return "용접봉"                       # 공정 처리(자재소요 제외)
    if mt == "4" or role == "완성부품":
        return "사급"                         # 사급부품(LG 지급)
    if mt in ("2", "5"):
        return "협력사"                       # 외주가공(가공비 축·제외)
    if mt == "1":
        return "제작"                         # 자체제작(EA는 매입 아님·소비 원소재는 중량축 추후)
    if mt == "3":
        return "부자재"                         # 구매(비원소재) = 부자재·소모품·이지링크
    if role in _ETC_ROLES:
        return "부자재"
    if role == "반제품":
        return "반제품"                       # 중간 반제품(추후 전개/판단)
    return "미분류"


# ── ★매입유형 분류 (확정입고집계표/경영리포트 정본과 동일) — 업체 CUST_TYPE + mgmt_vendor_gubun override ──
#   확정입고집계표(live_api receipt)·일일영업매입현황(dailypurissue)이 쓰는 _CT_NAME + _vgubun 그대로 재사용.
_CT_NAME = {"1": "유상사급-부품", "4": "절삭-원자재", "5": "설치-원자재", "6": "절삭-협력사",
            "7": "절삭-부자재", "8": "설치-부자재", "9": "소모품", "A": "이지링크"}


def _gubun(vendor, ov, custmap):
    """매입유형 = mgmt_vendor_gubun override(유상사급-원재료 등) ▷ 업체 CUST_TYPE(_CT_NAME)."""
    v = str(vendor or "").strip()
    if not v:
        return "미분류"
    g = ov.get(v)
    if g:
        return g
    ct = custmap.get(v, ("", ""))[1]
    return _CT_NAME.get(ct, ("기타(" + ct + ")") if ct else "미분류")


def _last_day(y, m):
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else (30 if m != 2 else (29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28))


def _ranges2(fr6, to6):
    """일자범위(YYMMDD) → (실적구간, 예상구간). 실적=[From~min(어제,To)]·예상=[max(오늘,From)~To]."""
    tod = _dt.date.today()
    tod6 = "%02d%02d%02d" % (tod.year % 100, tod.month, tod.day)
    yest = tod - _dt.timedelta(days=1)
    yest6 = "%02d%02d%02d" % (yest.year % 100, yest.month, yest.day)
    a_to = min(yest6, to6)
    act = (fr6, a_to) if fr6 <= a_to else None      # 실적[From~어제(또는 To)]
    e_fr = max(tod6, fr6)
    exp = (e_fr, to6) if e_fr <= to6 else None       # 예상[오늘(또는 From)~To]
    return act, exp


def _name_maps(cur):
    """mat_code→품명, cust_code→(거래처명, cust_type)."""
    cur.execute("SELECT item_code, item_name FROM nx.item")
    itnm = {str(r[0]).strip().upper(): (r[1] or "") for r in cur.fetchall()}
    cur.execute("SELECT cust_code, cust_name, cust_type FROM nx.cust")
    cust = {str(r[0]).strip(): (r[1] or "", str(r[2] or "").strip()) for r in cur.fetchall()}
    return itnm, cust


@router.get("/api/matexpect")
def matexpect(axis: str = Query("prod"), frm: str = Query(""), to: str = Query(""), grp: str = Query("")):
    """자재예상매입 소요/넷팅. axis=prod|sale · frm~to=일자범위(YYYY-MM-DD) · grp.
       기초재고=From 직전 / 기말재고=To까지 / 소요·매입=From~To(실적[~어제]+예상[오늘~To])."""
    t = _dt.date.today()
    if not frm:
        frm = "%04d-%02d-01" % (t.year, t.month)
    if not to:
        to = t.isoformat()
    fr6 = frm.replace("-", "")[2:8]; to6 = to.replace("-", "")[2:8]
    tod6 = "%02d%02d%02d" % (t.year % 100, t.month, t.day)
    days = max(1, (_dt.date(int(to[:4]), int(to[5:7]), int(to[8:10])) - _dt.date(int(frm[:4]), int(frm[5:7]), int(frm[8:10]))).days + 1)
    act_rng, exp_rng = _ranges2(fr6, to6)
    nx = _nx(); cur = nx.cursor()
    try:
        itnm, cust = _name_maps(cur)
        # 자재 매입처(정본 in_cust) — 실적귀속 (설계 §4)
        cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(in_cust_code,'') FROM nx.PR_M_ITEM")
        incust = {r[0]: str(r[1]).strip() for r in cur.fetchall()}
        # ★분류 = 매입유형 (확정입고집계표 정본): 업체 CUST_TYPE(cust맵) + mgmt_vendor_gubun override
        try:
            cur.execute("SELECT cust_code, override_gubun FROM nx.mgmt_vendor_gubun")
            ov = {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
        except Exception:
            ov = {}
        agg = {}  # (mat, vendor) → {exp, act, buy}

        def _row(mat, vendor):
            k = (mat, vendor)
            if k not in agg:
                agg[k] = {"mat": mat, "vendor": vendor, "exp": 0.0, "act": 0.0, "buy": 0.0}
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
        # 완제품 완성수량 × per-unit 소요(사전계산 캐시) → 자재소요. 실적 vendor 귀속 = PR_M_ITEM.in_cust_code(설계 §4)
        if driver:
            _ensure_soyo_cache(cur)   # ★BOM 서명 가드: 변경(sync/bom_save)시 캐시·엔진 무효→재빌드
            items = [it for it, dq in driver.items() if dq]
            smap = {}; cached = set()
            for i in range(0, len(items), 1000):     # 배치 캐시읽기(IN, 파라미터 청크)
                chunk = items[i:i + 1000]
                ph = ",".join("?" * len(chunk))
                cur.execute("SELECT item_code, mat_code, per_unit FROM nx.item_mat_soyo WHERE item_code IN (%s)" % ph, *chunk)
                for it, mc, per in cur.fetchall():
                    cached.add(it)
                    if mc:
                        smap.setdefault(it, {})[mc] = per
            for it in items:                          # miss(prewarm 밖)만 lazy 계산+저장
                if it not in cached:
                    try:
                        so = _soyo_of(cur, it)
                        if so:
                            smap[it] = so
                    except Exception:
                        pass
            for it, dq in driver.items():             # 집계
                if not dq:
                    continue
                for mc, per in smap.get(it, {}).items():
                    _row(mc, incust.get(mc, ""))["act"] += per * dq

        # ── ③-a 재고(nx.mat_stock_daily·C13 정본): 기초재고(From 직전)·기말재고(To 일자까지·미래면 오늘) ──
        def _stock_map(bound, op):
            cur.execute("SELECT mat_code, stock_qty FROM (SELECT UPPER(LTRIM(RTRIM(mat_code))) mat_code, stock_qty, "
                        "ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(mat_code))) ORDER BY ymd DESC) rn "
                        "FROM nx.mat_stock_daily WHERE ymd %s ?) t WHERE rn=1" % op, bound)
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}
        base_stock = _stock_map(fr6, "<")               # 기초재고(From 직전·필요수량 기준점·이중계상 방지)
        cur_stock = _stock_map(min(to6, tod6), "<=")    # 기말재고(To 일자까지)

        # ── ③-b 매입실적(실제 구매입고): 원소재·부자재=자재창고입고(tag9)+수입(_C P) / 사급=세트입고(tag S). 내부이동 C·G·H 제외 ──
        buy_to = min(to6, tod6)
        if fr6 <= buy_to:
            lv2 = _conn(); lc2 = lv2.cursor()
            try:
                for tag in ("9", "S"):
                    lc2.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(CUST_CODE,''), SUM(CAST(MAINT_QTY AS float)) "
                                "FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT WHERE MAINT_TAG=? AND MAINT_YMD BETWEEN ? AND ? "
                                "GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), CUST_CODE", tag, fr6, buy_to)
                    for mc, cc, q in lc2.fetchall():
                        _row(mc, str(cc or "").strip())["buy"] += float(q or 0)
                lc2.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(CUST_CODE,''), SUM(CAST(MAINT_QTY AS float)) "
                            "FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C WHERE DIVISION='P' AND MAINT_YMD BETWEEN ? AND ? "
                            "GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), CUST_CODE", fr6, buy_to)
                for mc, cc, q in lc2.fetchall():
                    _row(mc, str(cc or "").strip())["buy"] += float(q or 0)
            finally:
                lv2.close()

        # ── 조립: 분류·이름·필터 ──
        rows = []
        for (mat, vendor), v in agg.items():
            cnm, _cty = cust.get(vendor, ("", ""))       # 표시용 vendor명(소요/매입처)
            g = _gubun(vendor, ov, cust)                  # ★분류 = 매입유형(업체 CUST_TYPE + override), 확정입고집계표 동일
            if grp and grp != "전체" and g != grp:
                continue
            tot = v["exp"] + v["act"]
            if abs(tot) + abs(v["buy"]) < 1e-9:
                continue
            rows.append({
                "mat_code": mat, "mat_name": itnm.get(mat, ""),
                "vendor_code": vendor, "vendor_name": cnm, "grp": g,
                "exp_qty": round(v["exp"], 2), "act_qty": round(v["act"], 2), "tot_qty": round(tot, 2),
                "buy_qty": round(v["buy"], 2),                     # 매입실적(실제 구매입고)
                "base_qty": round(base_stock.get(mat, 0.0), 2),   # 기초재고(월초)
                "cur_qty": round(cur_stock.get(mat, 0.0), 2),     # 현재고(참고)
            })
        # ── ③-c 상시보유·필요수량·적정성 (자재×업체 세분 유지·재고는 소요비율 배분→Σ=자재레벨 일치) ──
        cur.execute("SELECT cust_code, ISNULL(lead_time_days,0) FROM nx.cust")
        lead_cust = {str(r[0]).strip(): (r[1] or 0) for r in cur.fetchall()}
        cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(pur_lead_time,0) FROM nx.item_sub")
        lead_item = {r[0]: (r[1] or 0) for r in cur.fetchall()}
        # days(기간일수) = 상단에서 계산(일평균소요 분모)
        tot_mat = {}
        for r in rows:
            tot_mat[r["mat_code"]] = tot_mat.get(r["mat_code"], 0.0) + r["tot_qty"]
        for r in rows:
            tm = tot_mat.get(r["mat_code"], 0.0)
            ratio = (r["tot_qty"] / tm) if tm > 1e-9 else 0.0
            base_v = r["base_qty"] * ratio                # 재고 소요비율 배분(Σ_업체 = 자재 기초재고)
            cur_v = r["cur_qty"] * ratio
            lt = lead_item.get(r["mat_code"]) or lead_cust.get(r["vendor_code"], 0) or 0   # 품목 override ▷ 거래처 기본(L/T 표시용)
            need = max(0.0, r["tot_qty"] - base_v - 0.0)   # 필요수량 = max(0, 총소요 − 기초재고 − 미착(0)) ★상시보유 개념 제거
            r["base_qty"] = round(base_v, 2); r["cur_qty"] = round(cur_v, 2)
            r["lead_days"] = int(lt); r["safety_qty"] = 0.0; r["misak_qty"] = 0.0
            r["need_qty"] = round(need, 2)
            r["fit_qty"] = round(r["buy_qty"] - need, 2)  # 적정성 = 매입실적 − 필요수량 (+과매입 / −부족)

        rows.sort(key=lambda r: -r["tot_qty"])
        # 분류 요약
        summ = {}
        for r in rows:
            s = summ.setdefault(r["grp"], {"grp": r["grp"], "mats": 0, "tot": 0.0, "need": 0.0, "buy": 0.0, "fit": 0.0})
            s["mats"] += 1; s["tot"] += r["tot_qty"]; s["need"] += r["need_qty"]; s["buy"] += r["buy_qty"]; s["fit"] += r["fit_qty"]
        return {
            "frm": frm, "to": to, "axis": axis, "days": days,
            "act_range": act_rng, "exp_range": exp_rng,
            "rows": rows, "cnt": len(rows), "summary": list(summ.values()),
            "note": "②소요(예상 plan_part_mat + 실적 제품입고P/출하×prod_soyo 캐시) + ③넷팅(재고 mat_stock_daily·상시보유 리드타임×일평균·매입 tag9/S/수입·필요수량 max(0,소요+상시보유−기초−미착)·적정성 매입−필요). 자재×업체 세분·재고는 소요비율 배분(Σ=자재).",
        }
    finally:
        nx.close()


# ================= v2 재구성: 자재매입현황(예상/실적) — MAT_EXPECTED_PURCHASE_DESIGN §11 =================
def _ovmap(cur):
    try:
        cur.execute("SELECT cust_code, override_gubun FROM nx.mgmt_vendor_gubun")
        return {str(r[0]).strip(): str(r[1]).strip() for r in cur.fetchall()}
    except Exception:
        return {}


def _rawmat_set(cur):
    """원소재(동관/강판 등) mat_code 집합 = nx.item.metal_gubun≠빈. 예상 EA에서 제외(중량 별도계산)."""
    cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item WHERE ISNULL(LTRIM(RTRIM(metal_gubun)),'')<>''")
    return {r[0] for r in cur.fetchall()}


def _ensure_copper_cache(cur):
    """완제품 per-unit 규격별 동중량 캐시(nx.item_copper_spec) + BOM 서명 가드(item_mat_soyo와 동일 패턴)."""
    cur.execute("""IF OBJECT_ID('nx.item_copper_spec') IS NULL CREATE TABLE nx.item_copper_spec(
        item_code varchar(30) NOT NULL, metal varchar(20), diam float, thick float, kg float)""")
    cur.execute("IF OBJECT_ID('nx.item_copper_meta') IS NULL CREATE TABLE nx.item_copper_meta(id int PRIMARY KEY, bom_sig varchar(80), built_dt datetime)")
    sig = _bom_sig(cur)
    cur.execute("SELECT bom_sig FROM nx.item_copper_meta WHERE id=1")
    r = cur.fetchone()
    if (not r) or (r[0] != sig):
        cur.execute("TRUNCATE TABLE nx.item_copper_spec")
        cur.execute("DELETE FROM nx.item_copper_meta WHERE id=1")
        cur.execute("INSERT INTO nx.item_copper_meta(id,bom_sig,built_dt) VALUES(1,?,getdate())", sig)


def _copper_of(cur, item, eng):
    """완제품 per-unit 규격별 동중량 {(metal,diam,thick):kg} — 캐시 우선, miss시 copper_by_spec(설치 포함)."""
    cur.execute("SELECT metal,diam,thick,kg FROM nx.item_copper_spec WHERE item_code=?", item)
    rows = cur.fetchall()
    if rows:
        return {(r[0], r[1], r[2]): r[3] for r in rows if r[0] is not None}
    sp = _soyo.copper_by_spec(eng, item)
    if sp:
        cur.executemany("INSERT INTO nx.item_copper_spec(item_code,metal,diam,thick,kg) VALUES(?,?,?,?,?)",
                        [(item, str(k[0]), float(k[1] or 0), float(k[2] or 0), float(v)) for k, v in sp.items()])
    else:
        cur.execute("INSERT INTO nx.item_copper_spec(item_code,metal,diam,thick,kg) VALUES(?,NULL,0,0,0)", item)
    return sp


def _rawmat_rows(cur, driver, to6):
    """원소재(동관/강판) 사급/직매입 rawmat_rows — 예상/실적 공용.
       driver={완제품:수량}(예상=계획·실적=리시빙+직거래) × LG BOM supply_type(lg_dong_split):
       사급=Assembly Pull(LG 지급) · 직매입=Supplier(공급사 조달). 단가=nx.price_metal std_price(LG사급가) as-of,
       규격 미등록시 같은재질 최근접 폴백(동 kg단가 LME지배·price_src 정확/근접 표기)."""
    import nx_lgbom_engine as _lgbom
    items = [it for it, q in driver.items() if q]
    ap_ver = "20%s-%s-%s" % (to6[:2], to6[2:4], to6[4:6])
    dsplit = _lgbom.lg_dong_split(cur, ap_ver, models=set(items))
    sagub_agg = {}; jik_agg = {}                        # (metal,diam,thick) -> kg
    for it, q in driver.items():
        if not q:
            continue
        d = dsplit.get(it, {}) or {}
        for sp, w in (d.get("sagub", {}) or {}).items():
            sagub_agg[sp] = sagub_agg.get(sp, 0.0) + w * q
        for sp, w in (d.get("jikmae", {}) or {}).items():
            jik_agg[sp] = jik_agg.get(sp, 0.0) + w * q
    # ── 원소재단가 as-of(std_price=LG사급가·LME중심) + 규격 미등록시 같은재질 최근접 폴백 ──
    ymcut = to6[:4]
    cur.execute("SELECT LTRIM(RTRIM(metal_gubun)), diam, thick, CAST(std_price AS float), apply_ym "
                "FROM nx.price_metal WHERE apply_ym<=? AND std_price IS NOT NULL", ymcut)
    pm_latest = {}
    for mg, d, th, pr, ay in cur.fetchall():
        k = (str(mg).strip(), float(d or 0), float(th or 0)); ay = str(ay or "")
        if k not in pm_latest or ay > pm_latest[k][0]:
            pm_latest[k] = (ay, float(pr or 0))
    pm = {k: v[1] for k, v in pm_latest.items()}
    by_metal = {}
    for (mg, d, th), pr in pm.items():
        by_metal.setdefault(mg, []).append((d, th, pr))

    def _mp(metal, diam, thick):
        if pm.get((metal, diam, thick)):
            return pm[(metal, diam, thick)], "정확"
        cand = by_metal.get(metal)
        if not cand:
            return 0.0, "없음"
        best = min(cand, key=lambda x: (abs(x[0] - diam), abs(x[1] - thick)))
        return best[2], "근접"

    rows = []
    for gub, gagg in (("사급", sagub_agg), ("직매입", jik_agg)):
        for (metal, diam, thick), kg in gagg.items():
            if abs(kg) < 1e-6:
                continue
            up, psrc = _mp(metal, diam, thick)
            rows.append({"sagub_gubun": gub, "metal": metal, "diam": round(diam, 2), "thick": round(thick, 2),
                         "kg": round(kg, 1), "price": round(up), "amt": round(kg * up), "price_src": psrc})
    rows.sort(key=lambda r: (r["sagub_gubun"] != "사급", -r["amt"]))
    return rows


def _matbuy_exp(fr6, to6, frm, to):
    """예상 탭(계획 베이스, 설계 §11-2): 부품/부자재/사급 EA 넷팅(원소재 제외).
       추가발주 = max(0, 소요 − 재고 − 기발주) · 총매입금액 = (기발주 + 추가발주) × 매입단가(as-of).
       ★소요=plan_part_mat×plan_mat_source(소요엔진 STEP7) · 재고=mat_stock_daily(C13) ·
         기발주=PU_T_PURCHASE_DTL 미입고잔량 · 단가=NxCostEngine.pur_price."""
    nx = _nx(); cur = nx.cursor()
    try:
        itnm, cust = _name_maps(cur)
        ov = _ovmap(cur)
        rawset = _rawmat_set(cur)
        cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(in_cust_code,'') FROM nx.PR_M_ITEM")
        incust = {r[0]: str(r[1]).strip() for r in cur.fetchall()}
        agg = {}

        def _row(mat, vendor):
            k = (mat, vendor)
            if k not in agg:
                agg[k] = {"mat": mat, "vendor": vendor, "soyo": 0.0, "po": 0.0}
            return agg[k]

        # ── 예상소요(EA) = plan_part_mat × plan_mat_source 업체배분 + SUPPLY_GUBUN(공급방식) ──
        #   ★매입 대상 = SUPPLY_GUBUN 매입/유상사급/외주완성/미지정. 제외: 원소재(중량별도)·자체(제작·발주아님 §8)·외주가공(가공비축).
        #   (실측 검증 2026-08-30: 자체=제작 163k=미분류의 정체 / 외주가공=가공비 10k. plan_mat_source.SUPPLY_GUBUN 정본 소비.)
        cur.execute("""
            SELECT UPPER(LTRIM(RTRIM(ppm.mat_code))) mat, ISNULL(r.vendor_code,'') vendor,
                   ISNULL(r.supply_gubun,'') sg,
                   SUM(CAST(ppm.part_plan_qty AS float) * ISNULL(r.ratio,1.0)) qty
            FROM nx.plan_part_mat ppm
            LEFT JOIN (
                SELECT s.work_order, UPPER(LTRIM(RTRIM(s.mat_code))) mat_code, s.vendor_code,
                       LTRIM(RTRIM(s.SUPPLY_GUBUN)) supply_gubun,
                       CAST(s.qty AS float)/NULLIF(t.tot,0) ratio
                FROM nx.plan_mat_source s
                JOIN (SELECT work_order, UPPER(LTRIM(RTRIM(mat_code))) mat_code, SUM(CAST(qty AS float)) tot
                      FROM nx.plan_mat_source GROUP BY work_order, UPPER(LTRIM(RTRIM(mat_code)))) t
                  ON t.work_order=s.work_order AND t.mat_code=UPPER(LTRIM(RTRIM(s.mat_code)))
            ) r ON r.work_order=ppm.work_order AND r.mat_code=UPPER(LTRIM(RTRIM(ppm.mat_code)))
            WHERE ppm.plan_ymd BETWEEN ? AND ?
            GROUP BY UPPER(LTRIM(RTRIM(ppm.mat_code))), ISNULL(r.vendor_code,''), ISNULL(r.supply_gubun,'')""", fr6, to6)
        for mat, vendor, sg, qty in cur.fetchall():
            if mat in rawset:
                continue                                   # 원소재는 중량 별도(§11-2)
            if (sg or "").strip() in ("자체", "외주가공"):
                continue                                   # 자체=제작(발주아님)·외주가공=가공비(매입아님) — §8
            _row(mat, str(vendor or "").strip())["soyo"] += float(qty or 0)
        mat_soyo_set = {mat for (mat, vendor) in agg.keys()}   # 매입 소요 자재(기발주도 이 집합만)

        # ── 현재고(mat_stock_daily·C13) — 오늘까지 최신 ──
        t = _dt.date.today()
        tod6 = "%02d%02d%02d" % (t.year % 100, t.month, t.day)
        cur.execute("SELECT mat_code, stock_qty FROM (SELECT UPPER(LTRIM(RTRIM(mat_code))) mat_code, stock_qty, "
                    "ROW_NUMBER() OVER (PARTITION BY UPPER(LTRIM(RTRIM(mat_code))) ORDER BY ymd DESC) rn "
                    "FROM nx.mat_stock_daily WHERE ymd<=?) t WHERE rn=1", tod6)
        stock = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

        # ── 기발주 = PU_T_PURCHASE_DTL 미입고잔량 by (mat, vendor) ──
        lv = _conn(); lc = lv.cursor()
        try:
            lc.execute("""SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(CUST_CODE,''),
                          SUM(CAST(PUR_QTY AS float)-CAST(ISNULL(IN_QTY,0) AS float)-CAST(ISNULL(CANCEL_QTY,0) AS float))
                       FROM PARTNER_ERP.dbo.PU_T_PURCHASE_DTL WHERE ISNULL(IN_FINISH_FLAG,'N')<>'Y'
                       GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE))), CUST_CODE""")
            for mat, cc, remain in lc.fetchall():
                rem = float(remain or 0)
                cc = str(cc or "").strip()
                if rem <= 0 or mat in rawset or mat not in mat_soyo_set:
                    continue                                # 매입 소요 자재만(자체/외주가공·비계획 po-only 제외)
                if cc and cc not in cust:
                    continue                                # ★없는 업체(거래처마스터 미등재)=컷오버 삭제대상 오래된 발주 제외(SW/LGE/P진티엔 등 2023 stale)
                _row(mat, cc)["po"] += rem
        finally:
            lv.close()

        # ── 매입단가 as-of 배치 로드(price_type='매입') — 행마다 pur_price 호출(느림) 대체 ──
        mats = list({mat for (mat, vendor) in agg.keys()})
        price_rows = {}   # mat -> [(vendor, apply_ymd, price, cur)]
        for i in range(0, len(mats), 1000):
            chunk = mats[i:i + 1000]
            ph = ",".join("?" * len(chunk))
            cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(LTRIM(RTRIM(vendor_code)),''), ISNULL(apply_ymd,''), "
                        "CAST(price AS float), ISNULL(LTRIM(RTRIM(currency)),'KRW') FROM nx.price_item "
                        "WHERE price_type=N'매입' AND price IS NOT NULL AND UPPER(LTRIM(RTRIM(item_code))) IN (%s)" % ph, *chunk)
            for it, vc, ay, pr, cc in cur.fetchall():
                price_rows.setdefault(it, []).append((str(vc).strip(), str(ay or "").strip(), float(pr or 0), str(cc or "KRW").strip()))
        fx = {"KRW": 1.0}
        try:
            cur.execute("SELECT LTRIM(RTRIM(currency)), CAST(rate AS float) FROM (SELECT currency, rate, "
                        "ROW_NUMBER() OVER (PARTITION BY currency ORDER BY apply_ymd DESC) rn FROM nx.fx_rate) t WHERE rn=1")
            for cc, rt in cur.fetchall():
                fx[str(cc).strip()] = float(rt or 1)
        except Exception:
            pass

        def _asof_price(mat, vendor, ymd):
            lst = price_rows.get(mat)
            if not lst:
                return 0.0
            cand = [x for x in lst if x[1] and x[1] <= ymd] or lst      # as-of ≤ ymd (없으면 전체)
            vp = [x for x in cand if x[0] == vendor]                    # 지정 vendor 우선
            pick = max(vp or cand, key=lambda x: x[1])                  # 최신 apply_ymd
            return pick[2] * fx.get(pick[3], 1.0)                       # 외화→KRW

        # ── 재고 소요비율 배분 → 넷팅 → 단가·금액 ──
        tot_mat = {}
        for (mat, vendor), v in agg.items():
            tot_mat[mat] = tot_mat.get(mat, 0.0) + v["soyo"]
        rows = []
        for (mat, vendor), v in agg.items():
            tm = tot_mat.get(mat, 0.0)
            ratio = (v["soyo"] / tm) if tm > 1e-9 else 0.0
            stk = stock.get(mat, 0.0) * ratio
            add = max(0.0, v["soyo"] - stk - v["po"])
            up = float(_asof_price(mat, vendor or "", to6) or 0.0)
            buy_qty = v["po"] + add
            rows.append({
                "mat_code": mat, "mat_name": itnm.get(mat, ""),
                "vendor_code": vendor, "vendor_name": cust.get(vendor, ("", ""))[0],
                "grp": _gubun(vendor, ov, cust),
                "soyo_qty": round(v["soyo"], 2), "stock_qty": round(stk, 2),
                "po_qty": round(v["po"], 2), "add_qty": round(add, 2),
                "unit_price": round(up, 2), "buy_amt": round(buy_qty * up),
            })
        rows = [r for r in rows if abs(r["soyo_qty"]) + abs(r["po_qty"]) > 1e-9]
        rows.sort(key=lambda r: -r["buy_amt"])

        # ── 원소재(동관/강판) 사급/직매입 = 완제품 계획(nx.plan_item_dtl) × LG BOM supply_type (공용헬퍼) ──
        cur.execute("SELECT UPPER(LTRIM(RTRIM(C_ITEM_CODE))), SUM(CAST(PLAN_QTY AS float)) FROM nx.plan_item_dtl "
                    "WHERE PLAN_YMD BETWEEN ? AND ? AND PLAN_QTY>0 GROUP BY UPPER(LTRIM(RTRIM(C_ITEM_CODE)))", fr6, to6)
        plan_fin = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
        rawmat_rows = _rawmat_rows(cur, plan_fin, to6)

        return {"tab": "exp", "frm": frm, "to": to, "rows": rows, "cnt": len(rows), "rawmat_rows": rawmat_rows,
                "note": "예상=계획베이스 EA(plan_part_mat×배분, 원소재 제외) 넷팅 + 원소재 사급/직매입(완제품계획×LG BOM supply_type). 추가발주=max(0,소요−재고−기발주)·총매입금액=(기발주+추가발주)×매입단가."}
    finally:
        nx.close()


def _matbuy_act(fr6, to6, frm, to):
    """실적 탭(설계 §11-3): 소요 = 리시빙(절삭) + 직거래출하(설치/이지링크) × prod_soyo · vs 매입실적.
       ★소요엔진만(prod_soyo 캐시 item_mat_soyo). 매입실적 = PU_T_STOCK_MAINT(9/S)+수입(_C P). 원소재 EA 제외."""
    nx = _nx(); cur = nx.cursor()
    try:
        itnm, cust = _name_maps(cur)
        ov = _ovmap(cur)
        rawset = _rawmat_set(cur)
        cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), ISNULL(in_cust_code,'') FROM nx.PR_M_ITEM")
        incust = {r[0]: str(r[1]).strip() for r in cur.fetchall()}
        cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))), ISNULL(LTRIM(RTRIM(cut_gubun)),'') FROM nx.item")
        cutg = {r[0]: r[1] for r in cur.fetchall()}

        # ── 드라이버(완제품 실적): 리시빙(절삭)=RECV_QTY · 직거래(설치/이지링크)=SALE_QTY ──
        driver = {}
        # ★net 리시빙(출고 C − 반품 R) — LG사급현황 리시빙비교(recvcompare)와 일관.
        cur.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), "
                    "SUM(CASE WHEN GUBUN='C' THEN CAST(RECV_QTY AS float) ELSE 0 END) "
                    "- SUM(CASE WHEN GUBUN='R' THEN CAST(RECV_QTY AS float) ELSE 0 END) "
                    "FROM nx.SA_T_LG_RECEIVING_DTL WHERE RECEIVING_YMD BETWEEN ? AND ? "
                    "GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))", fr6, to6)
        for it, q in cur.fetchall():
            if cutg.get(it, "") == "절삭":
                driver[it] = driver.get(it, 0.0) + float(q or 0)
        lv = _conn(); lc = lv.cursor()
        try:
            lc.execute("SELECT UPPER(LTRIM(RTRIM(ITEM_CODE))), SUM(CAST(SALE_QTY AS float)) FROM PARTNER_ERP.dbo.SA_T_SALE_DTL "
                       "WHERE SALE_YMD BETWEEN ? AND ? GROUP BY UPPER(LTRIM(RTRIM(ITEM_CODE)))", fr6, to6)
            for it, q in lc.fetchall():
                if cutg.get(it, "") in ("설치", "이지링크"):
                    driver[it] = driver.get(it, 0.0) + float(q or 0)
        finally:
            lv.close()

        agg = {}

        def _row(mat, vendor):
            k = (mat, vendor)
            if k not in agg:
                agg[k] = {"soyo": 0.0, "buy": 0.0}
            return agg[k]

        # ── 실적소요 = 드라이버 × prod_soyo(per-unit 캐시) ──
        if driver:
            _ensure_soyo_cache(cur)
            items = [it for it, dq in driver.items() if dq]
            smap = {}; cached = set()
            for i in range(0, len(items), 1000):
                chunk = items[i:i + 1000]
                ph = ",".join("?" * len(chunk))
                cur.execute("SELECT item_code, mat_code, per_unit FROM nx.item_mat_soyo WHERE item_code IN (%s)" % ph, *chunk)
                for it, mc, per in cur.fetchall():
                    cached.add(it)
                    if mc:
                        smap.setdefault(it, {})[mc] = per
            for it in items:
                if it not in cached:
                    try:
                        so = _soyo_of(cur, it)
                        if so:
                            smap[it] = so
                    except Exception:
                        pass
            nx.commit()
            for it, dq in driver.items():
                if not dq:
                    continue
                for mc, per in smap.get(it, {}).items():
                    if mc in rawset:
                        continue                            # 원소재는 EA 제외(중량 별도축)
                    _row(mc, incust.get(mc, ""))["soyo"] += per * dq

        # ── 매입실적 = PU_T_STOCK_MAINT(9/S) + 수입(_C DIVISION='P') by (mat, vendor) ──
        lv2 = _conn(); lc2 = lv2.cursor()
        try:
            for tag in ("9", "S"):
                lc2.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(CUST_CODE,''), SUM(CAST(MAINT_QTY AS float)) "
                            "FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT WHERE MAINT_TAG=? AND MAINT_YMD BETWEEN ? AND ? "
                            "GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), CUST_CODE", tag, fr6, to6)
                for mc, cc, q in lc2.fetchall():
                    _row(mc, str(cc or "").strip())["buy"] += float(q or 0)
            lc2.execute("SELECT UPPER(LTRIM(RTRIM(MAT_CODE))), ISNULL(CUST_CODE,''), SUM(CAST(MAINT_QTY AS float)) "
                        "FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C WHERE DIVISION='P' AND MAINT_YMD BETWEEN ? AND ? "
                        "GROUP BY UPPER(LTRIM(RTRIM(MAT_CODE))), CUST_CODE", fr6, to6)
            for mc, cc, q in lc2.fetchall():
                _row(mc, str(cc or "").strip())["buy"] += float(q or 0)
        finally:
            lv2.close()

        rows = []
        for (mat, vendor), v in agg.items():
            if abs(v["soyo"]) + abs(v["buy"]) < 1e-9:
                continue
            rows.append({"mat_code": mat, "mat_name": itnm.get(mat, ""),
                         "vendor_code": vendor, "vendor_name": cust.get(vendor, ("", ""))[0],
                         "grp": _gubun(vendor, ov, cust),
                         "soyo_qty": round(v["soyo"], 2), "buy_qty": round(v["buy"], 2)})
        rows.sort(key=lambda r: -r["soyo_qty"])
        # ── 원소재(동관/강판) 사급/직매입 = 완제품 실적(driver) × LG BOM supply_type (예상과 동일 공용헬퍼) ──
        rawmat_rows = _rawmat_rows(cur, driver, to6)
        return {"tab": "act", "frm": frm, "to": to, "rows": rows, "cnt": len(rows), "rawmat_rows": rawmat_rows,
                "note": "실적=리시빙(절삭)+직거래출하(설치/이지링크)×prod_soyo 소요 vs 매입실적(PU_T_STOCK_MAINT 9/S+수입P) + 원소재 사급/직매입(실적×LG BOM supply_type). 원소재 EA 제외."}
    finally:
        nx.close()


@router.get("/api/matbuy")
def matbuy(tab: str = Query("exp"), frm: str = Query(""), to: str = Query("")):
    """자재매입현황(예상/실적) — 설계 §11. tab=exp(오늘~+4주 계획) | act(오늘~−4주 실적)."""
    t = _dt.date.today()
    if tab == "act":
        if not to:
            to = t.isoformat()
        if not frm:
            frm = (t - _dt.timedelta(days=28)).isoformat()
    else:
        if not frm:
            frm = t.isoformat()
        if not to:
            to = (t + _dt.timedelta(days=28)).isoformat()
    fr6 = frm.replace("-", "")[2:8]; to6 = to.replace("-", "")[2:8]
    if tab == "act":
        return _matbuy_act(fr6, to6, frm, to)
    return _matbuy_exp(fr6, to6, frm, to)
