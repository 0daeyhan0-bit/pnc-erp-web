# -*- coding: utf-8 -*-
"""gagong 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 가공생산진척관리(전표발행) (w_pr_input_420_new) — PR_T_PLAN_PART_DTL 스냅샷 직독 =================
@router.get("/api/gagong/prog420")
def gagong_prog420(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query("P2"),
                   part: str = Query(""), item: str = Query(""), jado: str = Query(""),
                   unfin: str = Query("전체"), limit: int = Query(3000)):
    """가공생산진척관리. ★레거시 암호화SP `SP_PR_가공생산진척관리_260602`(from,to,mat_work_code) 직접 실행 → 100% 동일.
       당일이전=index00, 기준일~기간=index01+. 완료=finish_qty_NN·셀색=color_NN(BGR long). 자도번작업처=assy_work_center(이름)."""
    cn = _conn(); cur = cn.cursor()
    try:
        import datetime as _dt
        d6f = _d6(from_ymd) if from_ymd else '260729'
        d6t = _d6(to_ymd) if to_ymd else d6f
        try:
            da = _dt.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6])); db = _dt.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6]))
        except Exception:
            da = db = _dt.date(2026, 7, 29)
        ndays = max(1, min(8, (db - da).days + 1))
        dates = [(da + _dt.timedelta(days=i)).strftime('%y%m%d') for i in range(ndays)]   # 기준일~기간
        cur.execute("EXEC [dbo].[SP_PR_가공생산진척관리_260602] ?, ?, ?", d6f, d6t, (wc.strip() or 'P2'))
        cols = [d[0].lower() for d in cur.description]; sp = [dict(zip(cols, r)) for r in cur.fetchall()]
        def _css(v):
            v = int(v or 0)
            if v in (16777215, 553648127) or v <= 0: return ''
            return 'background:#%02x%02x%02x' % (v % 256, (v // 256) % 256, (v // 65536) % 256)
        def _f(x):
            try: return float(x or 0)
            except Exception: return 0.0
        allitems = [x for x in ({str(r.get('c_item_code') or '') for r in sp} | {str(r.get('mat_code') or '') for r in sp}) if x]; nm = {}
        gpcs = [x for x in {str(r.get('gagong_proc_code') or '') for r in sp} if x]; gpn = {}
        for i in range(0, len(allitems), 1000):
            ck = allitems[i:i + 1000]; ph = ",".join("?" * len(ck))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ck)
            for a, b in cur.fetchall(): nm[a] = b
        if gpcs:
            ph = ",".join("?" * len(gpcs))
            cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *gpcs)
            for a, b in cur.fetchall(): gpn[a] = b
        rows = []
        for r in sp:
            assy = str(r.get('assy_item_code') or ''); mat = str(r.get('mat_code') or '')
            if item.strip() and item.strip().lower() not in assy.lower(): continue
            if jado.strip() and jado.strip().lower() not in mat.lower(): continue
            gpc = str(r.get('gagong_proc_code') or '')
            _wcc = str(r.get('mat_work_code') or '').strip() or (wc.strip())   # 자도번작업처 코드 정본=mat_work_code(P2 등)
            _wcd = _ITEM_WORK.get(_wcc, _wcc)                                    # 코드→이름(P2→가공)
            g = {"assy": assy, "jado": mat, "jnm": nm.get(mat, ''), "gpcnm": gpn.get(gpc, gpc),
                 "wcc": _wcc, "wcd": _wcd, "st": round(_f(r.get('item_st')) * _f(r.get('plan_qty')) / 3600.0, 2),
                 "plan_qty": _f(r.get('plan_qty')), "finish": _f(r.get('finish_qty')),
                 "sale": _f(r.get('sale_qty')), "prs": _f(r.get('pr_stock_qty')),
                 "assyst": _f(r.get('assy_stock_qty')), "fixst": _f(r.get('fix_pr_stock_qty')),
                 "wo": r.get('work_order') or '',
                 "prior_pl": _f(r.get('plan_qty_00')), "prior_fn": _f(r.get('finish_qty_00')), "prior_bg": _css(r.get('color_00')),
                 "days": {}, "done": {}, "colors": {}}
            for i in range(1, ndays + 1):
                ii = '%02d' % i; ymd = dates[i - 1]
                g["days"][ymd] = _f(r.get('plan_qty_' + ii)); g["done"][ymd] = _f(r.get('finish_qty_' + ii)); g["colors"][ymd] = _css(r.get('color_' + ii))
            rows.append(g)
        uf = unfin.strip()
        if uf == "미생산": rows = [r for r in rows if r["finish"] < r["plan_qty"]]
        elif uf == "미키팅": rows = [r for r in rows if r["prior_fn"] <= 0]   # 근사(SP에 키팅상태 미분리)
        rows = rows[:int(limit)]
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "plan_sum": sum(r["plan_qty"] for r in rows), "done_sum": sum(r["finish"] for r in rows), "note": ""}
    finally:
        cn.close()

# ================= 4주간 가공계획현황 (w_pr_outside_410_work) — 도번×라인×작업처, 자도번LIST 묶기 =================
@router.get("/api/gagong/plan4w")
def gagong_plan4w(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                  item: str = Query(""), part: str = Query(""), mat_flag: str = Query("1"), limit: int = Query(2500)):
    """레거시 정본 SP_PR_4주간_가공계획현황_250703 본문 인라인 재현(EXEC 권한없어 SELECT로).
       SP는 WO별 행 생성 → ★표시 grain=도번(c_item_code)로 묶음. 자도번LIST=f_find_cust_mat_list2,
       자도번작업처=mat_work_code(P2=가공, 필터), 작업처=work_center. dates[0]=plan_qty_01(당일이전누적 plan_ymd<=기준일),
       dates[k]=plan_qty_(k+1). 수량=ceiling(plan_qty×use_qty×prod_rate/100). 참조 _legacy_analysis/SP_DUMP."""
    import datetime as _dt, os, sys as _sys
    _bd = os.path.dirname(os.path.abspath(__file__))
    if _bd not in _sys.path: _sys.path.insert(0, _bd)
    from _sp_4wk import SQL_4WK
    cn = _conn(); cur = cn.cursor()
    try:
        d6f = _d6(from_ymd) if from_ymd else '260729'
        d6t = _d6(to_ymd) if to_ymd else None
        if not d6t:
            _y = _dt.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6])) + _dt.timedelta(days=30)
            d6t = _y.strftime('%y%m%d')
        wcp = (wc.strip() or 'P2'); mf = (mat_flag.strip() or '1')
        sql = SQL_4WK
        for k, v in [('@@WC@@', wcp), ('@@MAT@@', '%'), ('@@FLAG@@', mf),
                     ('@@FROM@@', d6f), ('@@TO@@', d6t), ('@@ITEM@@', '%')]:
            sql = sql.replace(k, "'%s'" % v)
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]; ix = {c: i for i, c in enumerate(cols)}
        def gv(r, n, d=None):
            i = ix.get(n); return r[i] if i is not None else d
        raw = cur.fetchall()
        # 날짜 캘린더: dates[0]=기준일(=plan_qty_01 당일이전누적), 이후 plan_qty_02..31
        da = _dt.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6]))
        db = _dt.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6]))
        dates = []; cu = da
        while cu <= db and len(dates) < 31: dates.append(cu.strftime('%y%m%d')); cu += _dt.timedelta(days=1)
        keyed = {}
        for r in raw:
            doban = str(gv(r, 'c_item_code', '') or '').strip()
            if not doban: continue
            g = keyed.get(doban)
            if not g:
                g = {"assy": doban, "nm": "", "awcnm": str(gv(r, 'mat_work_desc', '') or '').strip(),
                     "mwcnm": str(gv(r, 'work_center', '') or '').strip(), "jado": str(gv(r, 'mat_list', '') or '').strip(),
                     "line": str(gv(r, 'line_no', '') or '').strip(), "lot": 0.0, "matq": 0.0,
                     "days": {}, "done": {}, "colors": {}, "_wos": set()}
                keyed[doban] = g
            g["lot"] += float(gv(r, 'lot_qty', 0) or 0)
            g["matq"] += float(gv(r, 'plan_qty', 0) or 0)
            _wo = str(gv(r, 'work_order', '') or '').strip()
            if _wo: g["_wos"].add((_wo, str(gv(r, 'split_work_order', '') or '').strip()))
            for k, ymd in enumerate(dates):
                g["days"][ymd] = g["days"].get(ymd, 0.0) + float(gv(r, 'plan_qty_%02d' % (k+1), 0) or 0)
        rows = list(keyed.values())
        if item.strip(): rows = [g for g in rows if item.strip() in g["assy"]]
        if part.strip(): rows = [g for g in rows if part.strip() in g["jado"]]
        rows.sort(key=lambda x: x["assy"])
        capped = len(rows) > int(limit); rows = rows[:int(limit)]
        # 품명 채우기(도번=PR_M_ITEM)
        codes = [g["assy"] for g in rows]; nm = {}
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; qm = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM PR_M_ITEM WHERE ITEM_CODE IN ({qm})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        # 자도번LIST = f_find_cust_mat_list2 재현(함수 EXECUTE 거부) — SP CTE_BOM 로직으로 도번의 mat_work_code(P2)자재 BOM전개
        jadomap = {}
        if codes:
            from collections import defaultdict as _dd
            jm = _dd(list)
            for i in range(0, len(codes), 500):
                ch = codes[i:i+500]; vals = ",".join("(?)" for _ in ch)
                bomsql = f"""
                WITH SEED(item_code) AS (SELECT item_code FROM (VALUES {vals}) v(item_code)),
                CTE_BOM AS (
                  SELECT CONVERT(int,1) level_no, CONVERT(varchar(50),s.item_code) item_code, CONVERT(varchar(50),s.item_code) mat_code,
                     CONVERT(decimal(18,5),1) cum_use_qty, CONVERT(varchar(20),CASE WHEN c.work_code>'' THEN c.work_code ELSE c.in_cust_code END) mwc
                  FROM SEED s JOIN pr_m_item c ON c.item_code=s.item_code
                  UNION ALL
                  SELECT cb.level_no+1, cb.item_code, CONVERT(varchar(50),b.mat_code),
                     CONVERT(decimal(18,5), cb.cum_use_qty*b.use_qty),
                     CONVERT(varchar(20),CASE WHEN m.work_code>'' THEN m.work_code ELSE m.in_cust_code END)
                  FROM CTE_BOM cb JOIN pr_m_item_bom b ON cb.mat_code=b.item_code JOIN pr_m_item m ON b.mat_code=m.item_code
                  WHERE ISNULL(b.EXCEPT_FLAG,'0')='0' AND cb.level_no<10 )
                SELECT item_code, mat_code, SUM(CONVERT(float,cum_use_qty)) q
                FROM CTE_BOM WHERE mwc=? AND level_no>1 GROUP BY item_code, mat_code
                ORDER BY item_code, mat_code OPTION(MAXRECURSION 0)"""
                cur.execute(bomsql, *ch, wcp)
                for it, mc, q in cur.fetchall():
                    jm[str(it).strip()].append("%s{%d}" % (str(mc).strip(), int(q or 0)))
            jadomap = {k: ",".join(v) for k, v in jm.items()}
        # ★완료/색 = 준비실적처리(키팅, kitting_grid)와 동일 워터폴 이식: 출하(주황)→ASSY재고(노랑)→도번고정(노랑)→중간재고(노랑)→준비재고(녹) 순 계획일 충당.
        # 소스: 라이브 직독(SA_T_ITEM_STOCK·PU_T_READY_STOCK·SA_T_SALE_DTL + 중간재고롤업 kitting캐시). 도번(=ITEM_CODE) 단위 합산.
        assystk = {}; rstock = {}; saled = {}; midstk = {}; fixstk = {}
        try:
            cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
            for rr in cur.fetchall(): assystk[str(rr[0]).strip()] = float(rr[1] or 0)
        except Exception: pass
        try:
            cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PU_T_READY_STOCK WHERE CUST_CODE='Z99990' GROUP BY ITEM_CODE")
            for rr in cur.fetchall(): rstock[str(rr[0]).strip()] = float(rr[1] or 0)
        except Exception: pass
        try:  # 출하는 ★계획 WO로 제한(키팅과 동일, 무관 WO 출하 과다합산 방지). 키=(wo,swo,item)
            _pwos = list({wo for g in rows for (wo, sw) in g["_wos"]})
            for i in range(0, len(_pwos), 900):
                ck = _pwos[i:i+900]; ph = ",".join("?" * len(ck))
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): saled[(str(rr[0]).strip(), str(rr[1] or '').strip(), str(rr[2]).strip())] = float(rr[3] or 0)
        except Exception: pass
        try:  # 중간공정 자재/생산재고 롤업 = kitting_grid 캐시 재사용, 없으면 자체계산(전역·필터무관, 색tag70용)
            _rc = getattr(kitting_grid, "_rollup_cache", None)
            if not (_rc and _rc.get("mid")):
                cur.execute("IF OBJECT_ID('tempdb..#tms4') IS NOT NULL DROP TABLE #tms4")
                cur.execute("""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code, CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          FROM ( SELECT mat_code, 0 stock_qty, STOCK_QTY pr_stock_qty FROM pr_t_mat_stock_wh WITH(NOLOCK)
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN pr_m_item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2')
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PU_T_STACKER_STOCK WITH(NOLOCK) ) s
                         GROUP BY s.mat_code HAVING SUM(s.stock_qty)<>0 OR SUM(s.pr_stock_qty)<>0
                        UNION ALL
                        SELECT cb.item_code, b.item_code, b.mat_code, 0, 0, CONVERT(int, (CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.stock_qty) END) * b.use_qty)
                          FROM T_SUB_CTE cb JOIN pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1'
                    )
                    SELECT item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty INTO #tms4 FROM T_SUB_CTE OPTION(MAXRECURSION 0)""")
                _mid = {}; _fix = {}
                cur.execute("SELECT mat_code, SUM(stock_qty)+SUM(pr_stock_qty) FROM #tms4 GROUP BY mat_code")
                for rr in cur.fetchall(): _mid[str(rr[0]).strip()] = float(rr[1] or 0)
                cur.execute("SELECT upper_item_code, mat_code, SUM(fix_pr_stock_qty) FROM #tms4 GROUP BY upper_item_code, mat_code")
                for rr in cur.fetchall(): _fix[(str(rr[0]).strip(), str(rr[1]).strip())] = float(rr[2] or 0)
                import time as _tm
                kitting_grid._rollup_cache = {"ts": _tm.time(), "mid": _mid, "fix": _fix}
                _rc = kitting_grid._rollup_cache
            midstk = _rc["mid"]
            for (up, it), v in _rc.get("fix", {}).items(): fixstk[it] = fixstk.get(it, 0.0) + float(v or 0)
        except Exception: pass
        def _alloc4(cells, pool, tag, key):
            pool = max(float(pool or 0), 0.0)
            for c in cells:
                if pool <= 0: break
                jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                if jan <= 0: continue
                if jan > pool: c[key] += pool; pool = 0.0
                else:
                    c[key] += jan; pool -= jan
                    if tag > c["tag"] or c["tag"] == 0: c["tag"] = tag
        _TAGCOLOR = {90: '#fac090', 70: '#ffff00', 50: '#669900'}   # 출하주황·생산노랑·키팅녹
        for g in rows:
            g["nm"] = nm.get(g["assy"], "")
            if jadomap.get(g["assy"]): g["jado"] = jadomap[g["assy"]]
            g["matcnt"] = (g["jado"].count(",") + 1) if g["jado"] else 0
            it = g["assy"]
            cells = [{"ymd": d, "plan": g["days"].get(d, 0.0), "finish": 0.0, "ready": 0.0, "tag": 0} for d in dates]
            _sale = sum(saled.get((wo, sw, it), 0.0) for (wo, sw) in g["_wos"])   # 계획 WO 출하만
            _alloc4(cells, _sale, 90, 'finish')       # 출하 → 주황
            _alloc4(cells, assystk.get(it, 0.0), 70, 'finish')     # ASSY재고(생산완료) → 노랑
            # ★도번고정재고·중간공정재고는 완료에서 제외 — 레거시(w_pr_outside_410_work) 대조결과 in-progress라 완료 아님.
            #   (이 둘을 포함하면 ACJ75119301 완료 500(과다) vs 레거시 200. 제외 시 ASSY재고 200 = 레거시 일치)
            _alloc4(cells, rstock.get(it, 0.0), 50, 'ready')       # 준비재고(키팅) → 녹
            fintot = 0.0
            for c in cells:
                cov = c["finish"] + c["ready"]; g["done"][c["ymd"]] = round(cov, 2); fintot += cov
                g["colors"][c["ymd"]] = _TAGCOLOR.get(c["tag"], '')
            g["finish"] = round(fintot, 2)
            g["plan_qty"] = max(0.0, round(g["matq"] - fintot, 2))   # ★요청수량=자재−완료(미완료 잔량, 레거시 공식)
            g["fin"] = '0'
            g.pop("_wos", None)
        note = (f"⚠ 상위 {limit}건만 표시 — 도번/자도번으로 필터하세요." if capped else "")
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "plan_sum": sum(r["matq"] for r in rows), "done_sum": sum(r["finish"] for r in rows), "note": note}
    finally:
        cn.close()

# ================= 가공전표이력현황 (w_pr_processing_010) — BOX_NO 마스터-디테일 =================
@router.get("/api/gagong/jeohist")
def gagong_jeohist(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                   item: str = Query(""), jado: str = Query(""), box_no: str = Query(""), limit: int = Query(500)):
    """가공전표이력. box_no 없으면 좌측 마스터(전표=바코드 목록), 있으면 우측 디테일(공정순서별).
       원천: 최신 PR_T_INDI_CUTTING(전표) + PR_T_INDI_CUTTING_PROC_GAGONG(공정 S_WORK_CODE=가공공정, STD_SIZE=작업표준)."""
    cn = _conn(); cur = cn.cursor()
    try:
        if box_no.strip():   # ---- 우측 디테일: BOX_NO 공정 실적(★레거시 정본 PR_T_PROD_DTL_GAGONG) ----
            # 가공공정=S_WORK_CODE(PR_M_WORK_SINGLE 컷팅/축관…), 파트=GAGONG_PROC_CODE, 설비=MACH_CODE(QA_M_MACHINE), 생산완료=PROD_QTY.
            # 공정횟수(WORK_QTY)·작업표준(STD_SIZE)은 PROD_DTL_GAGONG 부재 → INDI_CUTTING_PROC_GAGONG 보충(있을 때만, 없으면 NULL=담당확인).
            cur.execute("""SELECT p.PROC_SEQ, p.GAGONG_PROC_CODE gpc,
                  COALESCE(NULLIF(pg.GAGONG_PROC_DESC,''), p.GAGONG_PROC_CODE) partnm,
                  ISNULL(p.S_WORK_CODE,'') swork, ISNULL(ws.WORK_DESC,'') sworknm,
                  ISNULL(p.MACH_CODE,'') mach, ISNULL(mm.MACH_DESC,'') machnm,
                  ISNULL(p.PROD_QTY,0) doneq, ic2.WORK_QTY proc_cnt, ic2.STD_SIZE std
                FROM PR_T_PROD_DTL_GAGONG p
                LEFT JOIN PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=p.GAGONG_PROC_CODE
                LEFT JOIN PR_M_WORK_SINGLE ws ON ws.S_WORK_CODE=p.S_WORK_CODE
                LEFT JOIN QA_M_MACHINE mm ON mm.MACH_CODE=p.MACH_CODE
                LEFT JOIN PR_T_INDI_CUTTING_PROC_GAGONG ic2 ON ic2.BOX_NO=p.BOX_NO
                     AND ISNULL(ic2.S_WORK_CODE,'')=ISNULL(p.S_WORK_CODE,'') AND ic2.PROC_SEQ=p.PROC_SEQ
                WHERE p.BOX_NO=?
                ORDER BY p.PROC_SEQ, p.PROD_SEQ""", box_no.strip())
            cols = [d[0] for d in cur.description]
            det = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["doneq"] = float(d["doneq"] or 0)
                d["proc_cnt"] = (float(d["proc_cnt"]) if d["proc_cnt"] is not None else None)   # None=담당확인(원천부재)
                d["std"] = (str(d["std"]).strip() if d["std"] is not None else None)
                det.append(d)
            return {"box_no": box_no.strip(), "detail": det, "cnt": len(det)}
        # ---- 좌측 마스터: 전표(바코드) 목록 (레거시 w_pr_processing_010 전 컬럼) ----
        # ★필터=전표출력기간=PRINT_DATETIME(PLAN_YMD 아님), 자도번=MAT_CODE. 작업처명=work_code→이름 or in_cust→벤더명.
        w = ["CONVERT(date, ic.PRINT_DATETIME) BETWEEN ? AND ?"]
        p = [(from_ymd or "2000-01-01"), (to_ymd or "2099-12-31")]
        if item.strip(): w.append("ic.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")   # 도번=상위도번=ITEM_CODE
        if jado.strip(): w.append("ic.MAT_CODE LIKE ?"); p.append(f"%{jado.strip()}%")     # 자도번=MAT_CODE
        if wc.strip():   # ★작업처(레거시 cust_code 필터) = 자도번 매입처/작업처 코드·명
            w.append("(ma.IN_CUST_CODE LIKE ? OR mac.CUST_DESC LIKE ? OR maw.WORK_DESC LIKE ?)"); p += [f"%{wc.strip()}%"] * 3
        cur.execute(f"""SELECT TOP {int(limit)} ic.BOX_NO,
              ISNULL(ic.ITEM_CODE,'') doban, ISNULL(ic.MAT_CODE,'') jado,
              ISNULL(ma.IN_CUST_CODE,'') wcen, COALESCE(NULLIF(mac.CUST_DESC,''), maw.WORK_DESC, '') wcennm,
              ISNULL(CONVERT(varchar(20), ic.ITEM_DIAM), '') diam, ISNULL(CONVERT(varchar(20), ic.ITEM_THICK), '') thick,
              '' inspdt, ISNULL(ic.CUT_FLAG,'') cutflag, ISNULL(ic.CUT_USER_ID,'') cutuser,
              ISNULL(CONVERT(varchar(19), ic.CUT_DATETIME, 120), '') cutdt,
              ISNULL(ic.ASSY_ITEM_CODE,'') assy,
              COALESCE(NULLIF(aac.CUST_DESC,''), aaw.WORK_DESC, '') assywc,
              COALESCE(NULLIF(iac.CUST_DESC,''), iaw.WORK_DESC, '') dobanwc,
              COALESCE(wh.GAGONG_PROC_DESC, ic.WH_GAGONG_PROC_CODE, '') inwh,
              CONVERT(varchar(19), ic.PRINT_DATETIME, 120) prt, ISNULL(pn.proc_n,0) proc_n
            FROM PR_T_INDI_CUTTING ic
            LEFT JOIN PR_M_ITEM ma ON ma.ITEM_CODE=ic.MAT_CODE
            LEFT JOIN CM_M_CUST mac ON mac.CUST_CODE=ma.IN_CUST_CODE
            LEFT JOIN PR_M_WORK maw ON maw.WORK_CODE=ma.WORK_CODE
            LEFT JOIN PR_M_ITEM ia ON ia.ITEM_CODE=ic.ITEM_CODE
            LEFT JOIN CM_M_CUST iac ON iac.CUST_CODE=ia.IN_CUST_CODE
            LEFT JOIN PR_M_WORK iaw ON iaw.WORK_CODE=ia.WORK_CODE
            LEFT JOIN PR_M_ITEM aa ON aa.ITEM_CODE=ic.ASSY_ITEM_CODE
            LEFT JOIN CM_M_CUST aac ON aac.CUST_CODE=aa.IN_CUST_CODE
            LEFT JOIN PR_M_WORK aaw ON aaw.WORK_CODE=aa.WORK_CODE
            LEFT JOIN PR_M_PROC_GAGONG wh ON wh.GAGONG_PROC_CODE=ic.WH_GAGONG_PROC_CODE
            LEFT JOIN (SELECT BOX_NO, COUNT(*) proc_n FROM PR_T_INDI_CUTTING_PROC_GAGONG GROUP BY BOX_NO) pn ON pn.BOX_NO=ic.BOX_NO
            WHERE {' AND '.join(w)}
            ORDER BY ic.BOX_NO DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()
