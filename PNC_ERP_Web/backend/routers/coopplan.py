# -*- coding: utf-8 -*-
"""coopplan 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 협력사 ①: 협력사계획현황 (w_pr_outside_040) — nx.plan_part 편성결과 =================
@router.get("/api/partner/workcenters")
def partner_workcenters(src: str = Query("nx")):
    """자도번작업처(협력사/내부공정) 목록. src=legacy → 라이브 PR_T_PLAN_PART_MAT(레거시 협력사계획, 당김 반영).
       src=nx(기본) → 우리 편성 nx.plan_part_mat."""
    if src == "legacy":
        cn = _conn(); cur = cn.cursor()
        try:
            cur.execute("""SELECT pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) nm, COUNT(*) n
                FROM PR_T_PLAN_PART_MAT pp
                LEFT JOIN PR_M_WORK w ON w.WORK_CODE=pp.MAT_WORK_CENTER_CODE
                LEFT JOIN CM_M_CUST cu ON cu.CUST_CODE=pp.MAT_WORK_CENTER_CODE
                WHERE pp.MAT_WORK_CENTER_CODE>'' GROUP BY pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE)
                ORDER BY COUNT(*) DESC""")
            return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
        finally:
            cn.close()
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        try:
            cur.execute(f"""SELECT pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) nm, COUNT(*) n
                FROM nx.plan_part_mat pp
                LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                WHERE pp.MAT_WORK_CENTER_CODE>'' GROUP BY pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE)
                ORDER BY COUNT(*) DESC""")
            return {"rows": [{"cc": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]}
        except Exception:
            return {"rows": []}
    finally:
        nx.close()

def _qint(v):
    f = float(v or 0)
    return int(f) if f == int(f) else round(f, 2)

# ================= ★완료수량(fulfillment) 엔진 — 레거시 SP + 510 창 충실이식 =================
# 원천: nx.dbo.[SP_PR_4주간계획현황_LIVE](레거시 SP_PR_4주간계획현황_251126을 LIVE 읽기용으로 이식.
#   PARTNER_ERP.dbo 로 전 테이블 한정=라이브 직독, 쓰기0. 당김 f_reld_doosung_live=라이브 HR_M_CALENDAR).
# 완료수량 c_fin = 출하(sale) + 완제품재고 배분(prod, ASSY재고 공유풀) + 세트/입고대기 재고배분(공유풀).
#   레거시 창(w_pr_outside_510.srw ue_set_dd_color/생산수량적용/자재수량적용) 로직을 파이썬 재현.
#   ★재고는 c_item_code(도번) 단위 공유풀 — 여러 제번이 나눠 소진(과다계상 방지). 일자-major 배분.
_SPL = "SP_PR_4주간계획현황_LIVE"

def _sp_live_rows(cur, cust, from_ymd, to_ymd, flag, item="%", matcode="%", workcode="%"):
    """SP_LIVE 1회 실행 → base grid 행 dict 리스트(라이브 직독)."""
    cur.execute("SET NOCOUNT ON; EXEC dbo.[" + _SPL + "] ?,?,?,?,?,?,?",
                from_ymd, to_ymd, flag, item, matcode, workcode, cust)
    cols = rows = None
    while True:
        if cur.description:
            cols = [c[0] for c in cur.description]; rows = cur.fetchall()
        if not cur.nextset(): break
    if not cols: return []
    ix = {c: i for i, c in enumerate(cols)}
    def G(r, c): return r[ix[c]] if c in ix else None
    out = []
    for r in rows:
        days = [int(G(r, 'plan_qty_%02d' % i) or 0) for i in range(1, 32)]
        minidx = next((i for i, d in enumerate(days) if d > 0), 99)
        out.append({'wo': str(G(r, 'work_order') or ''), 'swo': str(G(r, 'split_work_order') or ''),
            'assy': str(G(r, 'c_item_code') or ''), 'cust': str(G(r, 'mat_in_cust_code') or ''),
            'line': str(G(r, 'line_no') or ''), 'output_hm': str(G(r, 'output_hm') or ''),
            'excel': int(G(r, 'excel_seq') or 0), 'minidx': minidx,
            'plan': int(G(r, 'plan_qty') or 0), 'days': days, 'over': int(G(r, 'over_plan_qty') or 0),
            'lot': float(G(r, 'lot_qty') or 0), 'use': float(G(r, 'use_qty') or 1), 'rate': float(G(r, 'prod_rate') or 100),
            'sale': int(G(r, 'sale_qty') or 0), 'assy_stock': int(G(r, 'assy_stock_qty') or 0),
            'iset_stk': int(G(r, 'input_set_qty') or 0), 'ireq': int(G(r, 'input_req_qty') or 0),
            'work_center': str(G(r, 'work_center') or ''), 'work_code': str(G(r, 'work_code') or ''),
            'in_cust': str(G(r, 'in_cust_code') or ''),
            'model': str(G(r, 'model_no') or ''), 'nm': '', 'lot_qty': int(G(r, 'lot_qty') or 0),
            'insp': str(G(r, 'insp_flag') or '0'), 'pack': int(G(r, 'pack_qty') or 0),
            'mat_list': str(G(r, 'mat_list') or ''), 'sagub_list': str(G(r, 'sagub_list') or '')})
    return out

def _sim510(rows):
    """레거시 w_pr_outside_510 창 배분 로직 이식 → 각 행에 c_fin(완료)·c_input(요청)·prod 세팅.
       재고=도번(cust,assy) 공유풀, 일자-major 순차배분. (출하+완제품재고+세트/입고대기)."""
    from collections import defaultdict
    for r in rows:
        pd = r['days']; iset = [0]*31
        ll_lot = math.ceil(r['lot']*r['use']*r['rate']/100.0); allplan = r['plan']+r['over']
        if ll_lot < allplan: ll_lot = allplan
        q = r['sale'] - (ll_lot - allplan)               # 지난계획 차감 후 출하 적용
        for i in range(31):
            if q <= 0: break
            if pd[i] > 0:
                if q >= pd[i]: iset[i] = pd[i]; q -= pd[i]
                else:
                    if iset[i] < q: iset[i] = q
                    q = 0
        r['iset'] = iset; r['prod'] = 0
    g = defaultdict(list)
    for r in rows: g[(r['cust'], r['assy'])].append(r)
    # 완제품재고(ASSY) 공유풀 배분
    for k, rs in g.items():
        rs.sort(key=lambda r: (r['minidx'], r['line'], r['output_hm'], r['swo'], r['excel']))
        pool = max((r['assy_stock'] for r in rs), default=0)
        for i in range(31):
            if pool <= 0: break
            for r in rs:
                if pool <= 0: break
                need = r['days'][i] - r['iset'][i]
                if need > 0:
                    give = min(need, pool); r['prod'] += give; r['iset'][i] += give; pool -= give
    for r in rows:
        r['c_fin'] = r['prod'] + r['sale']; r['c_input'] = max(0, r['plan'] - r['c_fin'])
    # 세트재고+입고대기 공유풀 배분(완료 가산·요청 차감)
    for k, rs in g.items():
        rs.sort(key=lambda r: (r['minidx'], r['line'], r['output_hm'], r['swo'], r['excel']))
        pool = max((r['iset_stk'] + r['ireq'] for r in rs), default=0)
        for i in range(31):
            if pool <= 0: break
            for r in rs:
                if pool <= 0: break
                if r['days'][i] > 0:
                    need = r['days'][i] - r['iset'][i]
                    if need > 0:
                        give = min(need, pool); r['iset'][i] += give
                        r['c_fin'] += give; r['c_input'] = max(0, r['c_input'] - give); pool -= give
    return rows

def _fulfillment(cust, from_ymd, to_ymd, item="%", matcode="%", workcode="%"):
    """cust(협력사) 완료수량 산출: SP_LIVE(flag 1·2) → 중복제거 → _sim510.
       반환: (per_key, merged) — per_key[(swo,assy)]=(c_fin,c_input,plan); merged=도번(cust,assy) 병합행리스트."""
    nx = _nx(); cur = nx.cursor()
    try:
        seen = {}; rows = []
        for flag in ('1', '2'):
            for r in _sp_live_rows(cur, cust, from_ymd, to_ymd, flag, item, matcode, workcode):
                k = (r['wo'], r['swo'], r['assy'])
                if k in seen:  # 제작/사급 양쪽에 걸린 도번=동일 base, 중복 제거
                    if r['sagub_list'] and not seen[k]['sagub_list']: seen[k]['sagub_list'] = r['sagub_list']
                    continue
                seen[k] = r; rows.append(r)
    finally:
        nx.close()
    _sim510(rows)
    per_key = {}
    for r in rows:
        k = (r['swo'], r['assy'])
        pf, pi, pp = per_key.get(k, (0, 0, 0))
        per_key[k] = (pf + r['c_fin'], pi + r['c_input'], pp + r['plan'])
    return per_key, rows

def _planstatus_legacy(from_ymd, to_ymd, wc, part, assy, line, gubun):
    """★레거시 4주간 계획수량(w_pr_outside_410) 충실재현 — 라이브 PR_T_PLAN_PART_MAT 직독(읽기전용).
       원천 dw_pr_outside_040_t1 계열. 행 grain=도번(자도번작업처×제번×라인×assy_item_code), 일자매트릭스=part_plan_ymd(협력사 당김 CUST_MAINT_DAY 반영), 값=part_plan_qty.
       컬럼(레거시 동일): SEQ·자도번작업처·라인·작업처·도번·자도번LIST·사급·LOT수량·자재수량·완료수량·요청수량·품목정보·일자별.
       당김은 협력사계획_생성 SP가 part_plan_ymd에 baked(f_get_relative_work_day_doosung). 완료수량=레거시 라이브 실적조인 원천 미확정(담당확인)."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        d6f = _d6(from_ymd) if from_ymd else None
        d6t = _d6(to_ymd) if to_ymd else None
        if d6t: w.append("pp.part_plan_ymd<=?"); p.append(d6t)
        if wc.strip():   w.append("pp.mat_work_center_code=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.mat_code LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.assy_item_code LIKE ?"); p.append(f"%{assy.strip()}%")
        if line.strip(): w.append("pp.line_no=?"); p.append(line.strip())
        if gubun == "외주":   w.append("(pp.work_code IS NULL OR pp.work_code='')")   # 거래처(협력사)만
        elif gubun == "자체": w.append("pp.work_code>''")                              # 내부공정(P1/P2)
        where = " AND ".join(w)
        CAP_PARTS = 40000
        # 부품(자도번) 레벨 raw → 파이썬에서 도번 단위 롤업(자도번LIST·일자매트릭스). 값=part_plan_qty(자재), 요청=plan_qty(발주).
        cur.execute(f"""SELECT TOP {CAP_PARTS} pp.mat_work_center_code wc, pp.split_work_order wo, ISNULL(pp.line_no,'') line,
              pp.assy_item_code assy, pp.mat_code mat, pp.mat_flag matflag,
              CAST(pp.lot_qty AS float) lot, CAST(pp.plan_qty AS float) planq, CAST(pp.part_plan_qty AS float) partq,
              pp.part_plan_ymd ppy
            FROM PR_T_PLAN_PART_MAT pp
            WHERE {where}
            ORDER BY pp.mat_work_center_code, pp.split_work_order, pp.assy_item_code, pp.mat_code""", *p)
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        capped = len(raw) >= CAP_PARTS
        base = d6f or (min((r["ppy"] for r in raw if r["ppy"]), default=None))
        def _bucket(ppy):
            return base if (base and ppy and ppy <= base) else ppy
        # 기준일 + 캘린더일 연속전개(빈 일자컬럼 포함). base..d6t.
        dates = {_bucket(r["ppy"]) for r in raw if r["ppy"]}
        if base and d6t:
            import datetime as _dt
            try:
                cu = _dt.date(2000+int(base[:2]), int(base[2:4]), int(base[4:6]))
                end = _dt.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6])); n = 0
                while cu <= end and n < 45:
                    dates.add(cu.strftime('%y%m%d')); cu += _dt.timedelta(days=1); n += 1
            except Exception:
                pass
        dates = sorted(dates)
        # 도번(assy) 단위 롤업
        keyed = {}
        for r in raw:
            k = (r["wc"], r["wo"], r["line"], r["assy"])
            g = keyed.get(k)
            if not g:
                g = {"wc": r["wc"], "wo": r["wo"], "line": r["line"], "assy": r["assy"],
                     "lot": 0.0, "reqq": 0.0, "matq": 0.0, "sagub": False, "parts": {}, "days": {}, "tot": 0.0}
                keyed[k] = g
            g["lot"] = max(g["lot"], float(r["lot"] or 0))
            g["reqq"] = max(g["reqq"], float(r["planq"] or 0))   # 요청수량=발주(도번 order qty)
            pq = float(r["partq"] or 0); g["matq"] += pq          # 자재수량=자도번 part_plan_qty 합
            if str(r["matflag"] or "") == "2": g["sagub"] = True
            mc = str(r["mat"] or "").strip()
            if mc: g["parts"][mc] = g["parts"].get(mc, 0.0) + pq
            d = _bucket(r["ppy"]); g["days"][d] = g["days"].get(d, 0.0) + pq; g["tot"] += pq
        rows = list(keyed.values())
        # 배치 이름조회: 자도번작업처(work/cust), 도번(assy) 마스터(작업처·품명·규격)
        def _batch(codes, sql):
            m = {}; codes = sorted({c for c in codes if c})
            for i in range(0, len(codes), 900):
                ch = codes[i:i+900]; ph = ",".join("?" * len(ch))
                cur.execute(sql.format(ph=ph), *ch)
                for rr in cur.fetchall(): m[str(rr[0]).strip()] = rr
            return m
        wccodes = {g["wc"] for g in rows}; assycodes = {g["assy"] for g in rows}
        workm = _batch(wccodes, "SELECT WORK_CODE, WORK_DESC FROM PR_M_WORK WHERE WORK_CODE IN ({ph})")
        custm = _batch(wccodes, "SELECT CUST_CODE, CUST_DESC FROM CM_M_CUST WHERE CUST_CODE IN ({ph})")
        # 도번 마스터(작업처=assy의 work/incust, 품명, 규격)
        assym = _batch(assycodes, "SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(WORK_CODE,''), ISNULL(IN_CUST_CODE,''), ISNULL(ITEM_SPEC,''), ISNULL(ITEM_DIAM,0), ISNULL(ITEM_THICK,0), ISNULL(ITEM_LENGTH,0) FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})")
        # assy 작업처 코드도 이름 필요 → 추가 조회
        awc = {str(v[2]).strip() for v in assym.values() if str(v[2]).strip()}
        aic = {str(v[3]).strip() for v in assym.values() if str(v[3]).strip()}
        workm2 = _batch(awc, "SELECT WORK_CODE, WORK_DESC FROM PR_M_WORK WHERE WORK_CODE IN ({ph})")
        custm2 = _batch(aic, "SELECT CUST_CODE, CUST_DESC FROM CM_M_CUST WHERE CUST_CODE IN ({ph})")
        def nm_of(code):
            c = str(code or "").strip()
            if c in workm: return workm[c][1]
            if c in custm: return custm[c][1]
            if c in workm2: return workm2[c][1]
            if c in custm2: return custm2[c][1]
            return c
        for g in rows:
            g["wcnm"] = nm_of(g["wc"])
            am = assym.get(str(g["assy"]).strip())
            if am:
                g["nm"] = am[1]
                awcc = str(am[2]).strip(); aicc = str(am[3]).strip()
                g["workcenter"] = nm_of(awcc) if awcc else (nm_of(aicc) if aicc else "")
                spec = str(am[4]).strip()
                if not spec:
                    dd, tt, ll = float(am[5] or 0), float(am[6] or 0), float(am[7] or 0)
                    if dd or tt or ll: spec = f"Ø{_qint(dd)}×{_qint(tt)}×{_qint(ll)}"
                g["spec"] = spec
            else:
                g["nm"] = ""; g["workcenter"] = ""; g["spec"] = ""
            items = sorted(g["parts"].items())
            g["part"] = ", ".join(f"{mc}{{{_qint(q)}}}" for mc, q in items)  # 자도번LIST(도번{수량})
            g["jcnt"] = len(items)
            g["lot"] = _qint(g["lot"]); g["reqq"] = _qint(g["reqq"]); g["matq"] = _qint(g["matq"])
            g["doneq"] = None   # ⚠ 완료수량: 레거시 라이브 실적조인 원천 미확정 → 담당확인(추측채움 금지)
            g["days"] = {k2: _qint(v2) for k2, v2 in g["days"].items()}; g["tot"] = _qint(g["tot"])
            g.pop("parts", None)
        rows.sort(key=lambda x: (x["wcnm"] or "", x["line"], x["wo"], x["assy"]))
        for i, g in enumerate(rows, 1): g["seq"] = i
        note = "레거시 4주간 계획수량(w_pr_outside_410)·라이브 PR_T_PLAN_PART_MAT 직독(당김반영)."
        # ★완료수량(fulfillment): 협력사(외주) 지정 시 레거시 SP_LIVE + 510창 배분으로 실제값 채움.
        #   요청수량=계획−완료. 재고=도번 공유풀(과다계상 방지). 자체(내부공정)/전체는 협력사 컨텍스트 없음→미표시.
        if gubun == "외주" and wc.strip() and d6t:
            try:
                fut_from = base or d6f or d6t
                per_key, _m = _fulfillment(wc.strip(), fut_from, d6t)
                nmatch = 0
                for g in rows:
                    hit = per_key.get((str(g["wo"]), str(g["assy"])))
                    if hit is not None:
                        cfin, cinp, pplan = hit
                        g["doneq"] = _qint(cfin); g["reqq"] = _qint(cinp); nmatch += 1
                    else:
                        g["doneq"] = 0  # SP 결과에 없음=완료 0(요청=발주 유지)
                note += f" 완료수량=출하+완제품재고+세트/입고대기 재고배분(레거시 SP_LIVE+510창, 매칭 {nmatch}/{len(rows)}건)."
            except Exception as e:
                note += f" ⚠완료수량 계산 오류: {str(e)[:90]}"
        else:
            note += " 완료수량=협력사(외주) 지정 시 표시(레거시는 협력사별 화면)."
        if capped: note = f"⚠ 부품 {CAP_PARTS:,}행 상한 — 자도번작업처/제번으로 좁히세요. " + note
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "sum_qty": _qint(sum(g["matq"] for g in rows)), "note": note}
    finally:
        cn.close()

@router.get("/api/partner/planstatus")
def partner_planstatus(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                       part: str = Query(""), assy: str = Query(""), line: str = Query(""),
                       gubun: str = Query("외주"), src: str = Query("nx")):
    """협력사(납품업체)별 자도번 일자계획. gubun: 외주(협력사=CUST, 기본)/자체(내부공정=WORK)/전체.
       src=legacy → 라이브 PR_T_PLAN_PART_MAT(레거시 4주간 계획수량 w_pr_outside_410, 당김반영) 직독.
       src=nx(기본) → 우리 편성 nx.plan_part_mat(레거시 STEP5→6→7 100%검증). 가공처=mat_work_center_code, 자도번=mat_code."""
    if src == "legacy":
        return _planstatus_legacy(from_ymd, to_ymd, wc, part, assy, line, gubun)
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        C = " COLLATE DATABASE_DEFAULT"
        w = ["1=1"]; p = []
        if from_ymd: w.append("pp.PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        if line.strip(): w.append("pd.LINE_NO=?"); p.append(line.strip())
        if gubun == "외주":   w.append("w.WORK_CODE IS NULL AND cu.CUST_CODE IS NOT NULL")  # 거래처(협력사)만
        elif gubun == "자체": w.append("w.WORK_CODE IS NOT NULL")                            # 내부공정(P1/P2)
        # ★정본 nx.plan_part_mat은 자재단위라 행수가 큼(외주 5만+) → 브라우저 과부하 방지: 자도번(part)×가공처 단위로 먼저 집계(일자는 유지)
        #   후 상한(CAP). 필터(가공처/제번/자도번) 걸면 좁혀짐.
        CAP = 4000
        try:
            cur.execute(f"""SELECT TOP {CAP} pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) wcnm,
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, ISNULL(i.ITEM_DESC,'') nm,
                  ISNULL(pd.LINE_NO,'') line, ISNULL(pd.MODEL_NO,'') model, SUM(CAST(pp.PART_PLAN_QTY AS float)) q
                FROM nx.plan_part_mat pp
                LEFT JOIN (SELECT WORK_ORDER, MAX(LINE_NO) LINE_NO, MAX(MODEL_NO) MODEL_NO FROM nx.plan_dtl GROUP BY WORK_ORDER) pd ON pd.WORK_ORDER=pp.WORK_ORDER
                LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK w ON w.WORK_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON cu.CUST_CODE{C}=pp.MAT_WORK_CENTER_CODE{C}
                LEFT JOIN PARTNER_ERP.dbo.PR_M_ITEM i ON i.ITEM_CODE{C}=pp.MAT_CODE{C}
                WHERE {' AND '.join(w)}
                GROUP BY pp.PLAN_YMD, pp.MAT_WORK_CENTER_CODE, COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE),
                  pp.WORK_ORDER, pp.ASSY_ITEM_CODE, pp.MAT_CODE, i.ITEM_DESC, pd.LINE_NO, pd.MODEL_NO
                ORDER BY wcnm, pp.WORK_ORDER, pp.MAT_CODE""", *p)
        except Exception as e:
            return {"dates": [], "rows": [], "cnt": 0, "sum_qty": 0, "note": "편성 먼저 실행(생산계획업로드 → 🧾자재소요·조달 편성). 오류: " + str(e)[:120]}
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        capped = len(raw) >= CAP
        dates = sorted({r["PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["MAT_WORK_CENTER_CODE"], r["WORK_ORDER"], r["ASSY_ITEM_CODE"], r["MAT_CODE"])
            g = keyed.get(k)
            if not g:
                g = {"wc": r["MAT_WORK_CENTER_CODE"], "wcnm": r["wcnm"], "wo": r["WORK_ORDER"], "assy": r["ASSY_ITEM_CODE"],
                     "part": r["MAT_CODE"], "nm": r["nm"], "line": r["line"], "model": r["model"], "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["q"] or 0); g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["line"], x["wo"], x["part"]))
        note = f"⚠ 결과가 많아 상위 {CAP}건만 표시했습니다. 협력사(가공처)·제번·자도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows), "sum_qty": sum(float(r["q"] or 0) for r in raw), "note": note}
    finally:
        nx.close()
