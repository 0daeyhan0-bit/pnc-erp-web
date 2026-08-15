# -*- coding: utf-8 -*-
"""kitting 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 준비실적처리(키팅) 그리드 (w_pr_input_460_new ≈ dw_pr_input_410_t1_new2) =================
@router.get("/api/kitting/grid")
def kitting_grid(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                 part: str = Query(""), pgroup: str = Query(""), line: str = Query(""),
                 assy: str = Query(""), jado: str = Query(""), gigan: int = Query(2),
                 wh_part: str = Query("IS0001"),
                 view: str = Query("전체"), unfin: str = Query("전체"), limit: int = Query(20000)):
    """준비실적처리(키팅) 그리드 — ★레거시 정본 SP `SP_PR_CREATE_PLAN_파트별_생산계획계산_생산준비등록_NEW` 로직 복제(실행X, .sql 이식).
       source=PR_T_PLAN_PART_COPY, 필터 GC_GUBUN='P'(생산파트)·GAGONG_PROC_SEQ=1·투입파트(WH_GAGONG_PROC_CODE=@wh_part, 기본 IS0001, BOM CTE).
       ★본행 grain = (GAGONG_PROC_CODE, WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, UPPER_ITEM_CODE, ITEM_CODE).
       당일이전(plan_qty_00)=part_plan_ymd<from · 일자셀=from+N(달력일). 재고충당 순서=출하(sa_t_sale_dtl,tag90)→ASSY재고(sa_t_item_stock×use,tag70)
       →준비재고(pu_t_ready_stock cust=Z99990·proc=파트,tag50). finish_qty_NN=finish+ready. finish_tag→color: 90주황/70노랑/50·10녹/30회색/else백.
       입력값=라이브 직독, 색=SP로직 복제. ★라이브 PARTNER_ERP 읽기전용(SP 미실행)."""
    from datetime import datetime as _dt, timedelta as _td
    def _yadd(y6, n):
        try: return (_dt.strptime('20' + y6, '%Y%m%d') + _td(days=n)).strftime('%y%m%d')
        except Exception: return y6
    cn = _conn(); cur = cn.cursor()
    try:
        d6a = _d6(from_ymd) or _dt.now().strftime('%y%m%d')
        d6b = _d6(to_ymd) or _yadd(d6a, max(0, int(gigan) - 1))   # to = from + (기간-1) 달력일
        dates = [_yadd(d6a, i) for i in range(max(1, int(gigan)))]  # 지평 일자셀(달력일)
        whp = (wh_part.strip() or 'IS0001')
        # ★성능: SP #TEMP_CTE(투입파트 재귀BOM)를 메인쿼리 JOIN에서 분리 → KEYS set 선(先)조회 후 파이썬 필터
        #   (재귀CTE를 메인 GROUP 조인에 인라인하면 재구체화로 ~5초. 분리 시 ~1.5초. 값·색 로직 불변)
        keys = set()
        try:
            cur.execute("""
                ;WITH CTE (ITEM_CODE, MAT_CODE, GAGONG_PROC_CODE, WH_GAGONG_PROC_CODE, VIR_ITEM_FLAG) AS (
                     SELECT a.ITEM_CODE, B.MAT_CODE, B.GAGONG_PROC_CODE, B.WH_GAGONG_PROC_CODE, B.VIR_ITEM_FLAG
                       FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_COPY a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom B WITH(NOLOCK) ON A.ITEM_CODE=B.ITEM_CODE
                      WHERE a.part_plan_ymd BETWEEN '' AND ? AND a.GC_GUBUN='P'
                     UNION ALL
                     SELECT a.ITEM_CODE, B.MAT_CODE, B.GAGONG_PROC_CODE, B.WH_GAGONG_PROC_CODE, B.VIR_ITEM_FLAG
                       FROM CTE a JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom B WITH(NOLOCK) ON A.MAT_CODE=B.ITEM_CODE WHERE A.VIR_ITEM_FLAG='1'
                )
                SELECT DISTINCT ITEM_CODE, GAGONG_PROC_CODE FROM CTE WHERE WH_GAGONG_PROC_CODE=? OPTION(MAXRECURSION 0)""", d6b, whp)
            for rr in cur.fetchall(): keys.add((rr[0], rr[1]))
        except Exception: pass
        w = ["a.part_plan_ymd<=?", "a.GC_GUBUN='P'", "a.GAGONG_PROC_SEQ=1"]; p = [d6b]
        if wc.strip():     w.append("a.WORK_CODE=?"); p.append(wc.strip())
        if part.strip():   w.append("a.GAGONG_PROC_CODE=?"); p.append(part.strip())
        if line.strip():   w.append("a.LINE_NO=?"); p.append(line.strip())
        if assy.strip():   w.append("a.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")   # 도번 필터=ASSY
        if jado.strip():   w.append("a.ITEM_CODE LIKE ?"); p.append(f"%{jado.strip()}%")          # 자도번 필터=도번(item)
        if pgroup.strip(): w.append("pg.PART_GROUP_CODE=?"); p.append(pgroup.strip())
        cur.execute(f"""SELECT TOP {int(limit) * 40}
              a.ASSY_ITEM_CODE assy, a.UPPER_ITEM_CODE upper, a.ITEM_CODE item,
              a.GAGONG_PROC_CODE gpc, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE) gpcnm,
              ISNULL(pg.PART_GROUP_CODE,'') pgc, a.WORK_CODE wc,
              COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE) wcnm, MAX(ISNULL(a.LINE_NO,'')) line,
              a.WORK_ORDER wo, a.SPLIT_WORK_ORDER swo, a.PART_PLAN_YMD ymd,
              MAX(ISNULL(a.PART_OUTPUT_HM,'')) inhm, ISNULL(ib.ITEM_DESC,'') nm,
              ISNULL(pg.PROD_RATE,100) rate, ISNULL(st.st,0) st, MAX(CAST(ISNULL(a.USE_QTY,1) AS float)) useq,
              MIN(ISNULL(a.PLAN_YMD,'')) plan_ymd, SUM(CAST(a.PART_PLAN_QTY AS float)) pl
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_COPY a WITH(NOLOCK)
            JOIN PARTNER_ERP_TEST3.nx.pr_m_item b WITH(NOLOCK) ON a.ASSY_ITEM_CODE=b.ITEM_CODE
            JOIN PARTNER_ERP_TEST3.nx.pr_m_item ib WITH(NOLOCK) ON a.ITEM_CODE=ib.ITEM_CODE
            JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg WITH(NOLOCK) ON a.GAGONG_PROC_CODE=pg.GAGONG_PROC_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK wk WITH(NOLOCK) ON wk.WORK_CODE=a.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu WITH(NOLOCK) ON cu.CUST_CODE=pg.IN_CUST_CODE
            LEFT JOIN (SELECT ITEM_CODE, SUM(CAST(ISNULL(TOT_ST,0) AS float)) st FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG GROUP BY ITEM_CODE) st ON st.ITEM_CODE=a.ITEM_CODE
            WHERE {' AND '.join(w)}
            GROUP BY a.GAGONG_PROC_CODE, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE), ISNULL(pg.PART_GROUP_CODE,''),
              a.WORK_CODE, COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE), a.WORK_ORDER, a.SPLIT_WORK_ORDER,
              a.ASSY_ITEM_CODE, a.UPPER_ITEM_CODE, a.ITEM_CODE, a.PART_PLAN_YMD, ISNULL(ib.ITEM_DESC,''),
              ISNULL(pg.PROD_RATE,100), ISNULL(st.st,0)""", *p)
        cols = [d[0] for d in cur.description]
        raw = [d for d in (dict(zip(cols, r)) for r in cur.fetchall()) if (d["item"], d["gpc"]) in keys]   # ★투입파트 KEYS 필터
        # ── 본행 grain = (gpc,wo,swo,assy,upper,item), 일자셀 = 달력일 피벗 ──
        keyed = {}
        for r in raw:
            q = float(r["pl"] or 0); ymd = r["ymd"]
            bucket = 'P' if ymd < d6a else (ymd if ymd in dates else None)
            if bucket is None: continue   # to 초과분 방어(WHERE로 이미 <=to)
            k = (r["gpc"], r["wo"], r["swo"] or '', r["assy"], r["upper"] or '', r["item"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["assy"], "upper": r["upper"] or '', "item": r["item"], "nm": r["nm"],
                     "gpc": r["gpc"], "gpcnm": r["gpcnm"], "pgc": r["pgc"], "wc": r["wc"], "wcnm": r["wcnm"],
                     "line": r["line"], "inhm": r["inhm"], "rate": float(r["rate"] or 100),
                     "item_st": float(r["st"] or 0), "use_qty": float(r["useq"] or 1),
                     "wo": r["wo"], "swo": r["swo"] or '', "plan_ymd": (r["plan_ymd"] or ''),
                     "days": {}, "prior_plan": 0.0, "plan_qty": 0.0, "_cells": {}}
                keyed[k] = g
            if (r["plan_ymd"] or '') and (not g["plan_ymd"] or (r["plan_ymd"] or '') < g["plan_ymd"]): g["plan_ymd"] = r["plan_ymd"]
            cell = g["_cells"].get(bucket)
            if not cell:
                cell = {"bucket": bucket, "ymd": ymd, "plan": 0.0, "finish": 0.0, "ready": 0.0, "tag": 0}
                g["_cells"][bucket] = cell
            cell["plan"] += q
            if bucket == 'P': g["prior_plan"] += q
            else: g["days"][bucket] = g["days"].get(bucket, 0.0) + q
            g["plan_qty"] += q
        rows = list(keyed.values())
        capped = len(rows) >= int(limit); rows = rows[:int(limit)]
        # ── 충당 소스 조회(라이브 직독, SP 소스와 동일) ──
        rstock = {}; assystk = {}; saled = {}; nxcell = {}; midstk = {}; fixstk = {}
        try:  # 준비재고: pu_t_ready_stock cust='Z99990', (proc_gubun=파트, item)
            cur.execute("SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.PU_T_READY_STOCK WHERE CUST_CODE='Z99990' GROUP BY ITEM_CODE, PROC_GUBUN")
            for rr in cur.fetchall(): rstock[(rr[0], rr[1] or '')] = float(rr[2] or 0)
        except Exception: pass
        try:  # ASSY 현재고: sa_t_item_stock (item)
            cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
            for rr in cur.fetchall(): assystk[rr[0]] = float(rr[1] or 0)
        except Exception: pass
        # ★중간공정 파트재고 롤업(SP #TEMP_MAT_STOCK T_SUB_CTE): 자재/생산/사급/스태커 재고 + 재귀BOM 도번고정 → tag70.
        #   ★필터 무관 전역 재고롤업이라 색(tag70)에만 영향(값/개수/계획합계는 매요청 라이브 재조회) → 90초 TTL 캐시로 재귀비용 회피(~2초 유지).
        _cache = getattr(kitting_grid, "_rollup_cache", None)
        _now = _dt.now().timestamp()
        if _cache and (_now - _cache["ts"] < 90) and _cache["mid"]:
            midstk = _cache["mid"]; fixstk = _cache["fix"]
        else:
            try:
                cur.execute("IF OBJECT_ID('tempdb..#tms') IS NOT NULL DROP TABLE #tms")   # 풀링 재사용 대비 선정리(#temp만, 가드 통과=IF 시작)
                cur.execute("""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code,
                               CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          FROM ( SELECT mat_code, 0 stock_qty, STOCK_QTY pr_stock_qty FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK)
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.pr_m_item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2')
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP_TEST3.nx.PU_T_STACKER_STOCK WITH(NOLOCK) ) s
                         GROUP BY s.mat_code HAVING SUM(s.stock_qty)<>0 OR SUM(s.pr_stock_qty)<>0
                        UNION ALL
                        SELECT cb.item_code, b.item_code, b.mat_code, 0, 0,
                               CONVERT(int, (CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.stock_qty) END) * b.use_qty)
                          FROM T_SUB_CTE cb JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1'
                    )
                    SELECT item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty INTO #tms FROM T_SUB_CTE OPTION(MAXRECURSION 0)""")
                cur.execute("SELECT mat_code, SUM(stock_qty), SUM(pr_stock_qty) FROM #tms GROUP BY mat_code")   # 자재+생산재고(item)
                for rr in cur.fetchall(): midstk[rr[0]] = float(rr[1] or 0) + float(rr[2] or 0)
                cur.execute("SELECT upper_item_code, mat_code, SUM(fix_pr_stock_qty) FROM #tms GROUP BY upper_item_code, mat_code")  # 도번고정(upper,item)
                for rr in cur.fetchall(): fixstk[(rr[0], rr[1])] = float(rr[2] or 0)
                kitting_grid._rollup_cache = {"ts": _now, "mid": midstk, "fix": fixstk}
            except Exception: pass
        try:  # 출하: sa_t_sale_dtl (wo, split, item=assy, finish_flag='0') — ★결과 WORK_ORDER로 제한(전체 GROUP BY 3.7s→회피)
            wos = list({g["wo"] for g in rows if g["wo"]})
            for i in range(0, len(wos), 900):
                ck = wos[i:i + 900]; ph = ",".join("?" * len(ck))
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): saled[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
        except Exception: pass
        try:  # ★Phase1: nx 셀단위 준비 flag = 단일원장 nx.stock_ledger(STOCK_POINT='RDY') SUM. (item×wo×파트gpc×일자INPUT_YMD)
            nxc = _nx(); nc = nxc.cursor()
            nc.execute("""SELECT ITEM_CODE, ISNULL(WORK_ORDER,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(INPUT_YMD,''), ISNULL(SUM(MAINT_QTY),0)
                FROM nx.stock_ledger WHERE STOCK_POINT='RDY'
                GROUP BY ITEM_CODE, ISNULL(WORK_ORDER,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(INPUT_YMD,'')""")
            for rr in nc.fetchall(): nxcell[(rr[0], rr[1], rr[2], rr[3])] = float(rr[4] or 0)
            nxc.close()
        except Exception: pass
        # finish_tag → color(fin) 매핑: 90출하→'6' / 70생산→'4' / 50·10준비→'3' / 30자재→'2' / else '0'
        _TAG2FIN = {90: '6', 70: '4', 40: '4', 50: '3', 10: '3', 30: '2'}   # 40=전표재고(J) 완료군
        def _alloc(cellseq, pool, tag, key):
            """SP 커서 재고충당: 계획순 셀에 pool 충당. 완전충당 셀=tag, 부분=태그유지. key='finish' or 'ready'."""
            pool = max(float(pool or 0), 0.0)
            for c in cellseq:
                if pool <= 0: break
                jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                if jan <= 0: continue
                if jan > pool:
                    c[key] += pool; pool = 0.0                       # 부분충당 → tag 미변경(NULL)
                else:
                    c[key] += jan; pool -= jan
                    if tag > c["tag"] or c["tag"] == 0: c["tag"] = tag  # 완전충당 → tag(최고단계 유지)
        for g in rows:
            it = g["item"]
            g["part_ymd"] = min([c["ymd"] for c in g["_cells"].values()] or [''])   # 당일이전 셀 키(=최소 계획일)
            seq = ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
            # 1) 출하(sale, tag90) — pool=sa_t_sale_dtl[(wo,swo,assy)]
            _alloc(seq, saled.get((g["wo"], g["swo"], g["assy"]), 0.0), 90, 'finish')
            # 2) ASSY 현재고(tag70) — pool=sa_t_item_stock[assy] × use_qty
            _alloc(seq, assystk.get(g["assy"], 0.0) * g["use_qty"], 70, 'finish')
            # 2-1) 도번고정재고(tag70) — pool=재귀BOM 롤업 fixstk[(upper,item)] (SP 도번고정 감안)
            _alloc(seq, max(fixstk.get((g["upper"], it), 0.0), 0.0), 70, 'finish')
            # 2-2) 중간공정 파트재고(tag70) — pool=자재재고+생산재고 midstk[item] (SP 파트재고 감안)
            _alloc(seq, max(midstk.get(it, 0.0), 0.0), 70, 'finish')
            # 3) 준비재고(tag50) — pool=pu_t_ready_stock[(item,파트)]  → ready_qty
            _alloc(seq, max(rstock.get((it, g["gpc"]), 0.0), 0.0), 50, 'ready')
            # 4) ★nx 셀단위 준비 flag 오버레이(우리 확인분, 셀별) — 라이브 PU와 별도 합산(이중가산X), 커버 시 tag50 녹
            for c in seq:
                ck = g["part_ymd"] if c["bucket"] == 'P' else c["ymd"]
                nq = nxcell.get((it, g["wo"], g["gpc"], ck), 0.0)
                if nq > 0:
                    rem = max(c["plan"] - c["finish"] - c["ready"], 0.0)
                    if rem > 0: c["ready"] += min(nq, rem)
                    if c["plan"] > 0 and (c["finish"] + c["ready"]) >= c["plan"] and c["tag"] < 50: c["tag"] = 50
            # 셀 표시: finish_qty_NN = finish + ready; fin = tag매핑
            g["dcov"] = {}; g["dfin"] = {}
            pc = g["_cells"].get('P')
            g["prior_cover"] = round((pc["finish"] + pc["ready"]), 2) if pc else 0.0
            g["prior_fin"] = _TAG2FIN.get(pc["tag"], '0') if pc else '0'
            for y in g["days"]:
                c = g["_cells"].get(y)
                g["dcov"][y] = round((c["finish"] + c["ready"]), 2) if c else 0.0
                g["dfin"][y] = _TAG2FIN.get(c["tag"], '0') if c else '0'
            g["finish"] = round(sum(c["finish"] for c in g["_cells"].values()), 2)         # 완료수량=충당 finish합(SP finish_qty)
            g["ready_stock"] = round(max(rstock.get((it, g["gpc"]), 0.0), 0.0), 2)          # 준비재고(파트버킷)
            g["ready_qty"] = round(sum(c["ready"] for c in g["_cells"].values()), 2)        # 준비수량=충당 ready합(SP ready_qty)
            g["prod_stock"] = round(assystk.get(it, 0.0), 2)
            g["assy_stock"] = round(assystk.get(g["assy"], 0.0), 2)
            g["sale"] = round(saled.get((g["wo"], g["swo"], g["assy"]), 0.0), 2)
            g["need_qty"] = round(max(g["plan_qty"] - g["ready_qty"], 0.0), 2)
            fins = [_TAG2FIN.get(c["tag"], '0') for c in g["_cells"].values() if c["plan"] > 0]
            g["fin"] = (g["prior_fin"] if g["prior_plan"] > 0 else (g["dfin"][min(g["days"])] if g["days"] else '0'))
            g["_done_all"] = bool(fins) and all(f in ('4', '6') for f in fins)
            g["_has_unkit"] = any(f == '0' for f in fins)
            g["splits"] = [{"gpc": g["gpc"], "gpcnm": g["gpcnm"], "prior_plan": g["prior_plan"], "days": dict(g["days"])}]
            del g["_cells"]
        uf = unfin.strip()
        if uf == '미생산':   rows = [r for r in rows if not r["_done_all"]]
        elif uf == '미키팅': rows = [r for r in rows if r["_has_unkit"]]
        for r in rows: r.pop("_done_all", None); r.pop("_has_unkit", None)
        # 정렬 = 레거시 DW sort=: part_plan_ymd_output_hm → plan_ymd → gagong_proc_code → output_hm → work_order → split_work_order
        rows.sort(key=lambda x: ((x["part_ymd"] or "") + (x["inhm"] or ""), x["plan_ymd"] or "",
                                 x["gpc"] or "", x["inhm"] or "", x["wo"] or "", x["swo"] or ""))
        note = f"⚠ 상위 {limit}건 초과 — 투입파트·작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "plan_sum": sum(r["plan_qty"] for r in rows), "ready_sum": sum(r["ready_qty"] for r in rows), "note": note}
    finally:
        cn.close()

# ================= 파트별 생산계획 (w_pr_input_410_new) — 키팅과 동일 SP grain·색상, 410 컬럼 =================
@router.get("/api/plan/part410")
def plan_part410(from_ymd: str = Query(""), gigan: int = Query(2), wc: str = Query(""),
                 part: str = Query(""), line: str = Query(""), assy: str = Query(""), jado: str = Query(""),
                 view: str = Query("전체"), unfin: str = Query("전체"), src: str = Query("nx"),
                 wh_part: str = Query("IS0001"), limit: int = Query(20000)):
    """파트별 생산계획 그리드 — 레거시 SP `SP_PR_CREATE_PLAN_파트별_생산계획계산_생산준비등록_NEW` 로직 복제.
       ★키팅(/api/kitting/grid)과 동일 grain(gpc·wo·swo·assy·upper·item, 날짜피벗)·동일 충당·색상.
       ★src=nx(우리 PARTNER_ERP_TEST3.nx) | live(레거시 PARTNER_ERP.dbo 대사검증). live=nx셀오버레이 제외(순수 레거시).
       당김=CHANGE_DAY+','+(LOT_QTY-LAST_LOT_QTY)(전차수 대비 일자·수량 변경). 생산ST=(계획−완료)×item_st/3600.
       계상근무공수=일자ST/y_inwon(인원=PR_M_PROC_GAGONG⋈WORKER work_flag='1'). 라이브 RO(SP 미실행)."""
    from datetime import datetime as _dt, timedelta as _td
    def _yadd(y6, n):
        try: return (_dt.strptime('20' + y6, '%Y%m%d') + _td(days=n)).strftime('%y%m%d')
        except Exception: return y6
    SCH = "PARTNER_ERP.dbo" if str(src).strip() == "live" else "PARTNER_ERP_TEST3.nx"
    cn = _conn(); cur = cn.cursor()
    try:
        d6a = _d6(from_ymd) or _dt.now().strftime('%y%m%d')
        # ★날짜 지평 = 레거시 srw ue_retrieve 산식 완전이식: to_ymd = base(기준일) 초과 (기간-1)번째 근무일.
        #   근무일 = HR_M_CALENDAR(work_team='A', time_type='A', work_stats in 1/2/5/6) ∩ pr_m_line_calendar(work_stats<>4). dates=base~to 전체 달력일(주말/휴일도 컬럼).
        gigan_n = max(1, int(gigan)); dates = []; d6b = d6a
        if gigan_n > 1:
            try:
                cur.execute("""SELECT SUBSTRING(MAX(calendar_yymd),3,6) FROM
                    (SELECT ROW_NUMBER() OVER (ORDER BY calendar_yymd) rn, calendar_yymd
                       FROM PARTNER_ERP.dbo.HR_M_CALENDAR a WITH(NOLOCK)
                      WHERE work_team='A' AND calendar_yymd > ? AND time_type='A' AND work_stats IN ('1','2','5','6')
                        AND EXISTS (SELECT 1 FROM PARTNER_ERP.dbo.pr_m_line_calendar b WITH(NOLOCK)
                                    WHERE b.calendar_ymd=SUBSTRING(a.calendar_yymd,3,6) AND b.work_stats<>'4')) t
                    WHERE rn = ?""", '20' + d6a, gigan_n - 1)
                _r = cur.fetchone()
                if _r and _r[0]: d6b = str(_r[0])
            except Exception: pass
        try:   # 표시 컬럼 = base~to 전체 달력일(주말/휴일 포함)
            cur.execute("""SELECT CALENDAR_YYMD FROM PARTNER_ERP.dbo.HR_M_CALENDAR
                WHERE WORK_TEAM='A' AND CALENDAR_YYMD>=? AND CALENDAR_YYMD<=? ORDER BY CALENDAR_YYMD""", '20' + d6a, '20' + d6b)
            for (_cy,) in cur.fetchall(): dates.append(str(_cy)[2:])
        except Exception: pass
        if not dates:   # 캘린더 미조회시 달력일 fallback
            i = 0
            while _yadd(d6a, i) <= d6b and i < 60: dates.append(_yadd(d6a, i)); i += 1
            if not dates: dates = [d6a]
        d6b = dates[-1]
        whp = (wh_part.strip() or 'IS0001')
        # ★성능: 투입파트 KEYS(재귀 BOM, wc/part/assy 필터무관 · to일자+투입파트만 의존)를 (src,to,whp)별 90초 TTL 캐시.
        keys = set()
        _kck = (("live" if SCH.endswith("dbo") else "nx"), d6b, whp)
        _kcache = getattr(plan_part410, "_keys_cache", {})
        _kent = _kcache.get(_kck); _now0 = _dt.now().timestamp()
        if _kent and (_now0 - _kent["ts"] < 90):
            keys = _kent["k"]
        else:
            try:
                cur.execute(f"""
                    ;WITH CTE (ITEM_CODE, MAT_CODE, GAGONG_PROC_CODE, WH_GAGONG_PROC_CODE, VIR_ITEM_FLAG) AS (
                         SELECT a.ITEM_CODE, B.MAT_CODE, B.GAGONG_PROC_CODE, B.WH_GAGONG_PROC_CODE, B.VIR_ITEM_FLAG
                           FROM {SCH}.PR_T_PLAN_PART_COPY a WITH(NOLOCK) JOIN {SCH}.pr_m_item_bom B WITH(NOLOCK) ON A.ITEM_CODE=B.ITEM_CODE
                          WHERE a.part_plan_ymd BETWEEN '' AND ? AND a.GC_GUBUN='P'
                         UNION ALL
                         SELECT a.ITEM_CODE, B.MAT_CODE, B.GAGONG_PROC_CODE, B.WH_GAGONG_PROC_CODE, B.VIR_ITEM_FLAG
                           FROM CTE a JOIN {SCH}.pr_m_item_bom B WITH(NOLOCK) ON A.MAT_CODE=B.ITEM_CODE WHERE A.VIR_ITEM_FLAG='1'
                    )
                    SELECT DISTINCT ITEM_CODE, GAGONG_PROC_CODE FROM CTE WHERE WH_GAGONG_PROC_CODE=? OPTION(MAXRECURSION 0)""", d6b, whp)
                for rr in cur.fetchall(): keys.add((rr[0], rr[1]))
            except Exception: pass
            _kcache[_kck] = {"ts": _now0, "k": keys}
            plan_part410._keys_cache = _kcache
        w = ["a.part_plan_ymd<=?", "a.GC_GUBUN='P'", "a.GAGONG_PROC_SEQ=1"]; p = [d6b]
        if wc.strip():   w.append("a.WORK_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("a.GAGONG_PROC_CODE=?"); p.append(part.strip())
        if line.strip(): w.append("a.LINE_NO=?"); p.append(line.strip())
        if assy.strip(): w.append("a.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        if jado.strip(): w.append("a.ITEM_CODE LIKE ?"); p.append(f"%{jado.strip()}%")
        cur.execute(f"""SELECT TOP {int(limit) * 40}
              a.ASSY_ITEM_CODE assy, a.UPPER_ITEM_CODE upper, a.ITEM_CODE item,
              a.GAGONG_PROC_CODE gpc, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE) gpcnm,
              ISNULL(pg.PART_GROUP_CODE,'') pgc, a.WORK_CODE wc,
              COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE) wcnm, MAX(ISNULL(a.LINE_NO,'')) line,
              a.WORK_ORDER wo, a.SPLIT_WORK_ORDER swo, a.PART_PLAN_YMD ymd,
              MAX(ISNULL(a.PART_OUTPUT_HM,'')) inhm, ISNULL(ib.ITEM_DESC,'') nm,
              ISNULL(pg.PROD_RATE,100) rate, ISNULL(st.st,0) st, MAX(CAST(ISNULL(a.USE_QTY,1) AS float)) useq,
              MIN(ISNULL(a.PLAN_YMD,'')) plan_ymd,
              MAX(ISNULL(a.CHANGE_DAY,'')) change_day, SUM(CAST(ISNULL(a.LOT_QTY,0) AS float)) lot_qty,
              SUM(CAST(ISNULL(a.LAST_LOT_QTY,0) AS float)) last_lot_qty,
              SUM(CAST(a.PART_PLAN_QTY AS float)) pl
            FROM {SCH}.PR_T_PLAN_PART_COPY a WITH(NOLOCK)
            JOIN {SCH}.pr_m_item b WITH(NOLOCK) ON a.ASSY_ITEM_CODE=b.ITEM_CODE
            JOIN {SCH}.pr_m_item ib WITH(NOLOCK) ON a.ITEM_CODE=ib.ITEM_CODE
            JOIN {SCH}.PR_M_PROC_GAGONG pg WITH(NOLOCK) ON a.GAGONG_PROC_CODE=pg.GAGONG_PROC_CODE
            LEFT JOIN {SCH}.PR_M_WORK wk WITH(NOLOCK) ON wk.WORK_CODE=a.WORK_CODE
            LEFT JOIN {SCH}.CM_M_CUST cu WITH(NOLOCK) ON cu.CUST_CODE=pg.IN_CUST_CODE
            LEFT JOIN (SELECT ITEM_CODE, SUM(CAST(ISNULL(TOT_ST,0) AS float)) st FROM {SCH}.PR_M_ITEM_PROC_GAGONG GROUP BY ITEM_CODE) st ON st.ITEM_CODE=a.ITEM_CODE
            WHERE {' AND '.join(w)}
            GROUP BY a.GAGONG_PROC_CODE, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE), ISNULL(pg.PART_GROUP_CODE,''),
              a.WORK_CODE, COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE), a.WORK_ORDER, a.SPLIT_WORK_ORDER,
              a.ASSY_ITEM_CODE, a.UPPER_ITEM_CODE, a.ITEM_CODE, a.PART_PLAN_YMD, ISNULL(ib.ITEM_DESC,''),
              ISNULL(pg.PROD_RATE,100), ISNULL(st.st,0)""", *p)
        cols = [d[0] for d in cur.description]
        raw = [d for d in (dict(zip(cols, r)) for r in cur.fetchall()) if (d["item"], d["gpc"]) in keys]
        keyed = {}; earliest_ymd = d6a   # 생산실적 풀 하한(최소 계획일=밀린계획 시작)
        for r in raw:
            q = float(r["pl"] or 0); ymd = r["ymd"]
            bucket = 'P' if ymd < d6a else (ymd if ymd in dates else None)
            if bucket is None: continue
            if ymd and ymd < earliest_ymd: earliest_ymd = ymd
            k = (r["gpc"], r["wo"], r["swo"] or '', r["assy"], r["upper"] or '', r["item"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["assy"], "upper": r["upper"] or '', "item": r["item"], "nm": r["nm"],
                     "gpc": r["gpc"], "gpcnm": r["gpcnm"], "pgc": r["pgc"], "wc": r["wc"], "wcnm": r["wcnm"],
                     "line": r["line"], "inhm": r["inhm"], "rate": float(r["rate"] or 100),
                     "item_st": float(r["st"] or 0), "use_qty": float(r["useq"] or 1),
                     "wo": r["wo"], "swo": r["swo"] or '', "plan_ymd": (r["plan_ymd"] or ''),
                     "change_day": (r["change_day"] or ''), "lot_qty": 0.0, "last_lot_qty": 0.0,
                     "days": {}, "prior_plan": 0.0, "plan_qty": 0.0, "_cells": {}}
                keyed[k] = g
            if (r["plan_ymd"] or '') and (not g["plan_ymd"] or (r["plan_ymd"] or '') < g["plan_ymd"]): g["plan_ymd"] = r["plan_ymd"]
            g["lot_qty"] += float(r["lot_qty"] or 0); g["last_lot_qty"] += float(r["last_lot_qty"] or 0)
            if (r["change_day"] or '') and not g["change_day"]: g["change_day"] = r["change_day"]
            cell = g["_cells"].get(bucket)
            if not cell:
                cell = {"bucket": bucket, "ymd": ymd, "plan": 0.0, "finish": 0.0, "ready": 0.0, "tag": 0}
                g["_cells"][bucket] = cell
            cell["plan"] += q
            if bucket == 'P': g["prior_plan"] += q
            else: g["days"][bucket] = g["days"].get(bucket, 0.0) + q
            g["plan_qty"] += q
        rows = list(keyed.values())
        capped = len(rows) >= int(limit); rows = rows[:int(limit)]
        rstock = {}; assystk = {}; saled = {}; nxcell = {}; midstk = {}; fixstk = {}; partstk = {}
        # ★성능: 전역 재고 롤업(필터무관 rstock·assystk·midstk·fixstk = 색tag 전용, 값/계획합계는 매요청 라이브 재조회)을 src별 90초 TTL 캐시.
        #   재귀 #tms4 롤업(~2초)을 반복조회마다 재계산하던 것을 캐시 → 조회 고속화. 소스맵은 읽기전용(_alloc은 셀만 변경)이라 공유 안전.
        _ck = "live" if SCH.endswith("dbo") else "nx"
        _cache = getattr(plan_part410, "_stk_cache", {})
        _ent = _cache.get(_ck); _now = _dt.now().timestamp()
        if _ent and (_now - _ent["ts"] < 90):
            rstock = _ent["r"]; assystk = _ent["a"]; midstk = _ent["m"]; fixstk = _ent["f"]; partstk = _ent.get("p", {})
        else:
            try:
                cur.execute(f"SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY) FROM {SCH}.PU_T_READY_STOCK WHERE CUST_CODE='Z99990' GROUP BY ITEM_CODE, PROC_GUBUN")
                for rr in cur.fetchall(): rstock[(rr[0], rr[1] or '')] = float(rr[2] or 0)
            except Exception: pass
            try:
                cur.execute(f"SELECT ITEM_CODE, SUM(STOCK_QTY) FROM {SCH}.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                for rr in cur.fetchall(): assystk[rr[0]] = float(rr[1] or 0)
            except Exception: pass
            try:   # ★중간공정 파트재고(레거시 SP JOB 'B') = PR_T_MAT_STOCK_WH + PU_T_MAT_STOCK_WH by MAT_CODE(자도번), 무필터
                cur.execute(f"SELECT MAT_CODE, SUM(STOCK_QTY) FROM (SELECT MAT_CODE, STOCK_QTY FROM {SCH}.pr_t_mat_stock_wh WITH(NOLOCK) UNION ALL SELECT MAT_CODE, STOCK_QTY FROM {SCH}.pu_t_mat_stock_wh WITH(NOLOCK)) T GROUP BY MAT_CODE")
                for rr in cur.fetchall(): partstk[rr[0]] = float(rr[1] or 0)
            except Exception: pass
            try:
                cur.execute("IF OBJECT_ID('tempdb..#tms4') IS NOT NULL DROP TABLE #tms4")
                cur.execute(f"""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code,
                               CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          FROM ( SELECT mat_code, 0 stock_qty, STOCK_QTY pr_stock_qty FROM {SCH}.pr_t_mat_stock_wh WITH(NOLOCK)
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM {SCH}.PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN {SCH}.pr_m_item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM {SCH}.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2')
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM {SCH}.PU_T_STACKER_STOCK WITH(NOLOCK) ) s
                         GROUP BY s.mat_code HAVING SUM(s.stock_qty)<>0 OR SUM(s.pr_stock_qty)<>0
                        UNION ALL
                        SELECT cb.item_code, b.item_code, b.mat_code, 0, 0,
                               CONVERT(int, (CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.stock_qty) END) * b.use_qty)
                          FROM T_SUB_CTE cb JOIN {SCH}.pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1'
                    )
                    SELECT item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty INTO #tms4 FROM T_SUB_CTE OPTION(MAXRECURSION 0)""")
                cur.execute("SELECT mat_code, SUM(stock_qty), SUM(pr_stock_qty) FROM #tms4 GROUP BY mat_code")
                for rr in cur.fetchall(): midstk[rr[0]] = float(rr[1] or 0) + float(rr[2] or 0)
                cur.execute("SELECT upper_item_code, mat_code, SUM(fix_pr_stock_qty) FROM #tms4 GROUP BY upper_item_code, mat_code")
                for rr in cur.fetchall(): fixstk[(rr[0], rr[1])] = float(rr[2] or 0)
            except Exception: pass
            _cache[_ck] = {"ts": _now, "r": rstock, "a": assystk, "m": midstk, "f": fixstk, "p": partstk}
            plan_part410._stk_cache = _cache
        try:
            wos = list({g["wo"] for g in rows if g["wo"]})
            for i in range(0, len(wos), 900):
                ck = wos[i:i + 900]; ph = ",".join("?" * len(ck))
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM {SCH}.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): saled[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
        except Exception: pass
        # ★생산완료(70): 레거시 SP_..._NEW2_오전오후는 실제생산(PROD_DTL) 미사용 — "완료된 전표는 이미 ASSY재고·파트재고로 잡히므로 감안 불필요"(SP주석).
        #   → 아래 충당에서 assystk(ASSY재고)+partstk(중간파트재고)+jpstk(작업중 전표재고) 3풀로 완료 처리. (earliest_ymd는 참고용 미사용)
        _ = earliest_ymd
        # ★전표재고(J, tag40)=작업중 용접전표(PR_T_INDI_WELD_SHEET prod_fin_flag='0')의 최종공정 잔량(prod_qty−완료). SHEET헤더는 라이브에만 존재 → 항상 라이브 직독. src별 90초 캐시.
        jpstk = {}
        _jck = "jp"
        _jent = _cache.get(_jck)
        if _jent and (_now - _jent["ts"] < 90):
            jpstk = _jent["j"]
        else:
            try:
                cur.execute("""
                    SELECT t.gagong_proc_code gpc, s.item_code item, SUM(t.prod_qty - s.finish_prod_qty) stk
                    FROM PARTNER_ERP.dbo.PR_T_INDI_WELD_SHEET_DTL t WITH(NOLOCK)
                    JOIN (SELECT t.sheet_no, t.gagong_proc_code, t.gagong_proc_seq, MAX(s.to_proc_seq) to_proc_seq, MAX(s.item_code) item_code,
                                 ISNULL((SELECT TOP 1 prod_qty FROM PARTNER_ERP.dbo.PR_T_INDI_WELD_SHEET_DTL WITH(NOLOCK) WHERE sheet_no=t.sheet_no ORDER BY proc_seq DESC),0) finish_prod_qty
                          FROM PARTNER_ERP.dbo.PR_T_INDI_WELD_SHEET_DTL t WITH(NOLOCK)
                          JOIN (SELECT b.sheet_no, b.gagong_proc_code, b.gagong_proc_seq, MAX(b.proc_seq) to_proc_seq, MAX(a.item_code) item_code
                                FROM PARTNER_ERP.dbo.PR_T_INDI_WELD_SHEET a WITH(NOLOCK) JOIN PARTNER_ERP.dbo.PR_T_INDI_WELD_SHEET_DTL b WITH(NOLOCK) ON a.sheet_no=b.sheet_no
                                WHERE a.prod_fin_flag='0' GROUP BY b.sheet_no, b.gagong_proc_code, b.gagong_proc_seq) s
                               ON t.sheet_no=s.sheet_no AND t.proc_seq=s.to_proc_seq
                          GROUP BY t.sheet_no, t.gagong_proc_code, t.gagong_proc_seq) s ON s.sheet_no=t.sheet_no AND s.to_proc_seq=t.proc_seq
                    WHERE t.gagong_proc_code IS NOT NULL
                    GROUP BY t.gagong_proc_code, s.item_code""")
                for rr in cur.fetchall(): jpstk[(rr[1], rr[0])] = jpstk.get((rr[1], rr[0]), 0.0) + float(rr[2] or 0)
            except Exception: pass
            _cache[_jck] = {"ts": _now, "j": jpstk}
            plan_part410._stk_cache = _cache
        if str(src).strip() != "live":   # ★nx 셀단위 준비 flag 오버레이(우리 확인분) — 라이브 대사시 제외
            try:
                nxc = _nx(); nc = nxc.cursor()
                nc.execute("""SELECT ITEM_CODE, ISNULL(WORK_ORDER,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(INPUT_YMD,''), ISNULL(SUM(MAINT_QTY),0)
                    FROM nx.stock_ledger WHERE STOCK_POINT='RDY'
                    GROUP BY ITEM_CODE, ISNULL(WORK_ORDER,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(INPUT_YMD,'')""")
                for rr in nc.fetchall(): nxcell[(rr[0], rr[1], rr[2], rr[3])] = float(rr[4] or 0)
                nxc.close()
            except Exception: pass
        _TAG2FIN = {90: '6', 70: '4', 40: '4', 50: '3', 10: '3', 30: '2'}   # 40=전표재고(J) 완료군
        # ★충당 = 준비실적처리(키팅 /api/kitting/grid)와 100% 동일 검증엔진: 셀단위 pool 배분(출하90→ASSY×use/도번고정/중간공정70→준비50)+nx오버레이.
        #   410·460은 같은 SP라 숫자 동일해야 함 → 키팅의 검증된 충당을 그대로 사용. 생산ST=finish만 차감(준비 제외).
        for g in rows:
            g["part_ymd"] = min([c["ymd"] for c in g["_cells"].values()] or [''])
        # 1) 출하완료(90): WO단위 출하실적(SA_T_SALE_DTL) — 행별
        def _alloc(cellseq, pool, tag, key):
            pool = max(float(pool or 0), 0.0)
            for c in cellseq:
                if pool <= 0: break
                jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                if jan <= 0: continue
                if jan > pool: c[key] += pool; pool = 0.0
                else:
                    c[key] += jan; pool -= jan
                    if tag > c["tag"] or c["tag"] == 0: c["tag"] = tag
        for g in rows:
            seq = ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
            _alloc(seq, saled.get((g["wo"], g["swo"], g["assy"]), 0.0) * g["use_qty"], 90, 'finish')   # 출하×use_qty(레거시 SALE×USE_QTY)
        # 2)생산완료(70)=생산실적 / 3)키팅완료(50)=준비재고 : ★도번단위 풀 공유·날짜순 충당(WO별 재부여 방지→실제 생산/준비량 만큼만 완료).
        def _shared(keyfn, poolmap, tag, key):
            grp = {}
            for g in rows:
                for b, c in g["_cells"].items():
                    sd = (b if b != 'P' else (g["part_ymd"] or '999999'))
                    # ★배분순서 = 레거시 SP 커서 order by (part_plan_ymd, part_output_hm, plan_ymd, work_order, split_work_order) 이식 → 동순위 행 충당 일치
                    grp.setdefault(keyfn(g), []).append((c, sd, g["inhm"] or '', g["plan_ymd"] or '', g["wo"] or '', g["swo"] or ''))
            for k, lst in grp.items():
                pool = max(float(poolmap.get(k, 0.0) or 0), 0.0)
                if pool <= 0: continue
                lst.sort(key=lambda x: (x[1], x[2], x[3], x[4], x[5]))
                for c, sd, hm, _py, _wo, _swo in lst:
                    if pool <= 0: break
                    jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                    if jan <= 0: continue
                    if jan > pool: c[key] += pool; pool = 0.0
                    else:
                        c[key] += jan; pool -= jan
                        if tag > c["tag"] or c["tag"] == 0: c["tag"] = tag
        # ★생산완료(70): 레거시 SP_..._NEW2_오전오후 재현 = ASSY재고(×use) + 중간파트재고 2풀. (PROD_DTL 아님 — 완료전표는 이미 재고로 잡힘)
        _assy_pool = {}
        for g in rows:
            k = (g["assy"], g["upper"], g["item"])
            if k not in _assy_pool: _assy_pool[k] = assystk.get(g["assy"], 0.0) * g["use_qty"]   # 제품(ASSY)재고 = SA_T_ITEM_STOCK(도번)×use_qty
        _shared(lambda g: (g["assy"], g["upper"], g["item"]), _assy_pool, 70, 'finish')   # A: 제품(ASSY)재고
        _shared(lambda g: g["item"], partstk, 70, 'finish')                               # B: 중간공정 파트재고(PR+PU_T_MAT_STOCK_WH by 자도번)
        _shared(lambda g: (g["item"], g["gpc"]), jpstk, 40, 'finish')                      # J: 작업중 전표재고(용접시트, 라이브) → finish 가산
        _shared(lambda g: (g["item"], g["gpc"]), rstock, 50, 'ready')       # C: 준비재고(도번+파트) → 색(녹)만·미생산 판정 제외
        # 4) nx 셀단위 준비 오버레이(우리 웹 확인분, src=nx만)
        for g in rows:
            it = g["item"]
            for b, c in g["_cells"].items():
                ck = g["part_ymd"] if b == 'P' else c["ymd"]
                nq = nxcell.get((it, g["wo"], g["gpc"], ck), 0.0)
                if nq > 0:
                    rem = max(c["plan"] - c["finish"] - c["ready"], 0.0)
                    if rem > 0: c["ready"] += min(nq, rem)
                    if c["plan"] > 0 and (c["finish"] + c["ready"]) >= c["plan"] and c["tag"] < 50: c["tag"] = 50
        for g in rows:
            g["dcov"] = {}; g["dfin"] = {}
            pc = g["_cells"].get('P')
            # ★완료수량(분자)=생산실적(finish)만. 준비(키팅완료)는 숫자 아닌 색(녹)으로만 표시. 색tag는 최고단계(생산/키팅/미키팅) 유지.
            g["prior_cover"] = round(pc["finish"], 2) if pc else 0.0
            g["prior_fin"] = _TAG2FIN.get(pc["tag"], '0') if pc else '0'
            for y in g["days"]:
                c = g["_cells"].get(y)
                g["dcov"][y] = round(c["finish"], 2) if c else 0.0
                g["dfin"][y] = _TAG2FIN.get(c["tag"], '0') if c else '0'
            g["finish"] = round(sum(c["finish"] for c in g["_cells"].values()), 2)
            g["lot_diff"] = round(g["lot_qty"] - g["last_lot_qty"], 2)
            fins = [_TAG2FIN.get(c["tag"], '0') for c in g["_cells"].values() if c["plan"] > 0]
            g["_done_all"] = bool(fins) and all(f in ('4', '6') for f in fins)
            del g["_cells"]
        uf = unfin.strip()
        if uf == '미생산': rows = [r for r in rows if not r["_done_all"]]
        for r in rows: r.pop("_done_all", None)
        rows.sort(key=lambda x: ((x["part_ymd"] or "") + (x["inhm"] or ""), x["plan_ymd"] or "",
                                 x["item"] or "", x["wo"] or "", x["swo"] or ""))
        # ★item_st 정본 = 생산정보등록(생산공정순서) ST(초) 합계 · nx우선(nx.prodinfo_proc 있으면 override, 없으면 레거시 PR_M_ITEM_PROC_GAGONG 유지).
        #   생산ST=(계획−완료)×item_st/3600. src=live(순수 레거시 대사)는 레거시값 유지.
        if str(src).strip() != "live":
            try:
                nxc2 = _nx(); nc2 = nxc2.cursor()
                items = list({g["item"] for g in rows if g["item"]}); nxst = {}
                for i in range(0, len(items), 900):
                    ck = items[i:i + 900]; ph = ",".join("?" * len(ck))
                    nc2.execute(f"SELECT item_code, SUM(CAST(ISNULL(tot_st,0) AS float)) FROM nx.prodinfo_proc WHERE item_code IN ({ph}) GROUP BY item_code", *ck)
                    for rr in nc2.fetchall(): nxst[rr[0]] = float(rr[1] or 0)
                nxc2.close()
                for g in rows:
                    if g["item"] in nxst: g["item_st"] = nxst[g["item"]]
            except Exception: pass
        # 인원(y_inwon) — 레거시: COUNT(PR_M_PROC_GAGONG⋈WORKER work_flag='1', 파트필터 gpc·part_group like)
        inwon = 0
        try:
            gp = (part.strip() or '%')
            cur.execute(f"""SELECT COUNT(*) FROM {SCH}.PR_M_PROC_GAGONG a
                JOIN {SCH}.PR_M_PROC_GAGONG_WORKER b ON a.GAGONG_PROC_CODE=b.GAGONG_PROC_CODE
                WHERE b.WORK_FLAG='1' AND a.GAGONG_PROC_CODE LIKE ?""", gp)
            inwon = int(cur.fetchone()[0] or 0)
        except Exception: pass
        note = f"⚠ 상위 {limit}건 초과 — 파트·작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows), "src": ("live" if SCH.endswith("dbo") else "nx"),
                "plan_sum": sum(r["plan_qty"] for r in rows), "inwon": inwon, "note": note}
    finally:
        cn.close()

def _kit_cell_guard(item, wo, swo, gpc, ymd, qty, assy):
    """셀 확인/취소 서버 가드(라이브 RO): 월마감(PU_T_MONTH_READY_STOCK) 이후·출하완료분 금지. (ok, detail)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cellm = _d6(ymd) if ymd else ''
        try:
            cur.execute("SELECT ISNULL(MAX(stock_yymm),'0000') FROM PARTNER_ERP_TEST3.nx.pu_t_month_ready_stock")
            mclose = (cur.fetchone()[0] or '0000')
        except Exception:
            mclose = '0000'
        if cellm and len(cellm) == 6 and cellm <= (mclose + '99'):   # 셀 일자가 마감월 이내면 금지
            return (False, f"월마감({mclose}) 완료 일자 — 확인/취소 불가")
        if assy and qty > 0:   # 출하완료분 금지(sa_t_sale_dtl 미마감 출하 ≥ 셀잔량)
            try:
                cur.execute("SELECT ISNULL(SUM(SALE_QTY),0) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER=? AND ISNULL(SPLIT_WORK_ORDER,'')=? AND ITEM_CODE=?",
                            wo, (swo or ''), assy)
                if float(cur.fetchone()[0] or 0) >= qty:
                    return (False, "출하완료분 — 키팅 확인 불가")
            except Exception: pass
        return (True, "")
    finally:
        cn.close()

@router.post("/api/kitting/cell-confirm")
def kitting_cell_confirm(payload: dict = Body(...)):
    """준비실적처리 셀단위 준비완료 등록(레거시 250창 우클릭 '확인'). flag-only(자재무차감) — nx.ready_ledger INSERT(tag '1').
       키=item_code·work_order·proc_code(파트gpc)·plan_ymd(셀 일자, 당일이전=행 part_ymd). qty=셀 잔량(계획−완료). ★쓰기 nx만."""
    item = (payload.get("item") or "").strip(); wo = (payload.get("wo") or "").strip()
    swo = (payload.get("swo") or "").strip(); gpc = (payload.get("gpc") or "").strip()
    ymd = _d6(payload.get("ymd") or ""); qty = float(payload.get("qty") or 0)
    assy = (payload.get("assy") or "").strip()
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not item or not gpc or qty <= 0: return {"ok": False, "detail": "item·파트·수량(>0) 필수"}
    ok, detail = _kit_cell_guard(item, wo, swo, gpc, ymd, qty, assy)
    if not ok: return {"ok": False, "detail": detail}
    nx = _nx(); nc = nx.cursor()
    try:  # ★Phase1: 단일원장 nx.stock_ledger(STOCK_POINT='RDY', tag K1=+확인). 셀키=item·wo·gpc·plan_ymd(INPUT_YMD). flag-only(자재무차감)
        nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        seq = int(nc.fetchone()[0] or 1)
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,GAGONG_PROC_CODE,
              WORK_ORDER,INPUT_YMD,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('RDY',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,'K1','Z99990',?,?,?,?,?,'키팅확인',?,GETDATE())""",
            seq, item, gpc, (wo or None), (ymd or None), qty, user)
        return {"ok": True, "qty": qty}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        nx.close()

@router.post("/api/kitting/cell-cancel")
def kitting_cell_cancel(payload: dict = Body(...)):
    """준비실적처리 셀단위 준비취소(레거시 250창 우클릭 '취소'). ★Phase1: nx.stock_ledger(RDY) 상쇄 INSERT(tag K2, −qty). 잔량 이내. 쓰기 nx만."""
    item = (payload.get("item") or "").strip(); wo = (payload.get("wo") or "").strip()
    swo = (payload.get("swo") or "").strip(); gpc = (payload.get("gpc") or "").strip()
    ymd = _d6(payload.get("ymd") or ""); assy = (payload.get("assy") or "").strip()
    user = (str(payload.get("user", "") or "").strip() or "웹사용자")[:20]
    if not item or not gpc: return {"ok": False, "detail": "item·파트 필수"}
    nx = _nx(); nc = nx.cursor()
    try:  # 셀 현재 net(RDY 원장 우리 flag) 계산 → 그 이내로 취소
        nc.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='RDY'
              AND ITEM_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=? AND ISNULL(WORK_ORDER,'')=? AND ISNULL(INPUT_YMD,'')=?""",
                   item, gpc, (wo or ''), (ymd or ''))
        cur_net = float(nc.fetchone()[0] or 0)
        if cur_net <= 0: return {"ok": False, "detail": "취소할 준비완료(우리 확인분) 없음"}
        req = float(payload.get("qty") or 0)
        cancel = min(req, cur_net) if req > 0 else cur_net
        ok, detail = _kit_cell_guard(item, wo, swo, gpc, ymd, cancel, assy)
        if not ok: return {"ok": False, "detail": detail}
        nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        seq = int(nc.fetchone()[0] or 1)
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,GAGONG_PROC_CODE,
              WORK_ORDER,INPUT_YMD,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('RDY',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,'K2','Z99990',?,?,?,?,?,'키팅취소',?,GETDATE())""",
            seq, item, gpc, (wo or None), (ymd or None), -cancel, user)
        return {"ok": True, "qty": cancel}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200]}
    finally:
        nx.close()
