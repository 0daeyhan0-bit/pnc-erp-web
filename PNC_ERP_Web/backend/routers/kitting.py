# -*- coding: utf-8 -*-
"""kitting 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_prod_stock_map, _latest_stock_map, _conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _lock_msg, _stock_short_msg, stock_changed)

router = APIRouter()


class _RollupCached(Exception):
    """410 재귀 BOM 롤업을 캐시로 대체할 때 그 블록만 건너뛰는 신호(에러 아님).
       롤업이 try/except Exception 으로 감싸여 있어 조기이탈에 예외를 쓴다."""
    pass


# ================= 준비실적처리(키팅) 그리드 (w_pr_input_460_new ≈ dw_pr_input_410_t1_new2) =================
@router.get("/api/kitting/grid")
def kitting_grid(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                 part: str = Query(""), pgroup: str = Query(""), line: str = Query(""),
                 assy: str = Query(""), jado: str = Query(""), gigan: int = Query(2),
                 wh_part: str = Query("IS0001"),
                 view: str = Query("전체"), unfin: str = Query("전체"), src: str = Query("new"),
                 limit: int = Query(20000)):
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
    # ★소스 3종(2026-08-26) — 410 과 동일 규칙.
    #   live = 레거시 라이브 · nx = 레거시 미러(nx) · new = ★웹 자체편성(신규DB, 기본값)
    #   계획 원천만 바꾸고 마스터·재고·실적은 nx 그대로 → '계획' 차이만 순수 비교.
    _src = str(src).strip()
    _PSCH = "PARTNER_ERP.dbo" if _src == "live" else "PARTNER_ERP_TEST3.nx"
    PLAN_T = ("PARTNER_ERP_TEST3.nx.v_plan_part_copy_new" if _src == "new"
              else f"{_PSCH}.PR_T_PLAN_PART_COPY")
    cn = _conn(); cur = cn.cursor()
    try:
        d6a = _d6(from_ymd) or _dt.now().strftime('%y%m%d')
        # ★날짜 지평 = 파트별 생산계획(410)과 동일 — 레거시 srw ue_retrieve 산식(2026-09-04 통일).
        #   종전엔 to = from + (기간-1) '달력일' 이라, 토/일·휴일이 끼면 그만큼 근무일 컬럼이 줄었다
        #   (예: 기준 09/04(금)·기간 2일 → 04금·05토 만 나오고 정작 다음 근무일 07월 이 안 보임).
        #   ⟹ to_ymd = base 초과 (기간-1)번째 **근무일**. 표시 컬럼은 base~to 전체 달력일(휴일도 컬럼으로는 나옴).
        #   근무일 = HR_M_CALENDAR(work_team='A', time_type='A', work_stats in 1/2/5/6)
        #            ∩ pr_m_line_calendar(work_stats<>4).  ※달력 정본 = line_calendar(미러 아님).
        gigan_n = max(1, int(gigan)); dates = []; d6b = d6a
        if gigan_n > 1:
            try:
                cur.execute("""SELECT SUBSTRING(MAX(calendar_yymd),3,6) FROM
                    (SELECT ROW_NUMBER() OVER (ORDER BY calendar_yymd) rn, calendar_yymd
                       FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR a WITH(NOLOCK)
                      WHERE work_team='A' AND calendar_yymd > ? AND time_type='A' AND work_stats IN ('1','2','5','6')
                        AND EXISTS (SELECT 1 FROM PARTNER_ERP_TEST3.nx.pr_m_line_calendar b WITH(NOLOCK)
                                    WHERE b.calendar_ymd=SUBSTRING(a.calendar_yymd,3,6) AND b.work_stats<>'4')) t
                    WHERE rn = ?""", '20' + d6a, gigan_n - 1)
                _r = cur.fetchone()
                if _r and _r[0]: d6b = str(_r[0])
            except Exception: pass
        try:   # 표시 컬럼 = base~to 전체 달력일(주말/휴일 포함)
            cur.execute("""SELECT CALENDAR_YYMD FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR
                WHERE WORK_TEAM='A' AND CALENDAR_YYMD>=? AND CALENDAR_YYMD<=? ORDER BY CALENDAR_YYMD""", '20' + d6a, '20' + d6b)
            for (_cy,) in cur.fetchall(): dates.append(str(_cy)[2:])
        except Exception: pass
        if not dates:   # 캘린더 미조회시 달력일 fallback(종전 동작)
            i = 0
            while _yadd(d6a, i) <= d6b and i < 60: dates.append(_yadd(d6a, i)); i += 1
            if not dates: dates = [d6a]
        d6b = dates[-1]
        # ★to_ymd 파라미터가 명시로 들어오면 그것을 우선(하위호환) — 지평을 다시 그 범위로 맞춘다.
        _to = _d6(to_ymd)
        if _to:
            d6b = _to
            dates = [x for x in dates if x <= d6b] or [d6a]
            i = 0   # 캘린더가 짧으면 달력일로 연장
            while dates[-1] < d6b and i < 60: dates.append(_yadd(dates[-1], 1)); i += 1
            d6b = dates[-1]
        whp = (wh_part.strip() or 'IS0001')
        # ★성능: SP #TEMP_CTE(투입파트 재귀BOM)를 메인쿼리 JOIN에서 분리 → KEYS set 선(先)조회 후 파이썬 필터
        #   (재귀CTE를 메인 GROUP 조인에 인라인하면 재구체화로 ~5초. 분리 시 ~1.5초. 값·색 로직 불변)
        keys = set()
        try:
            cur.execute(f"""
                ;WITH CTE (ITEM_CODE, MAT_CODE, GAGONG_PROC_CODE, WH_GAGONG_PROC_CODE, VIR_ITEM_FLAG) AS (
                     SELECT a.ITEM_CODE, B.MAT_CODE, B.GAGONG_PROC_CODE, B.WH_GAGONG_PROC_CODE, B.VIR_ITEM_FLAG
                       FROM {PLAN_T} a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom B WITH(NOLOCK) ON A.ITEM_CODE=B.ITEM_CODE
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
              MAX(ISNULL(a.PART_OUTPUT_HM,'')) inhm, ISNULL(ib.item_name,'') nm,
              MAX(ISNULL(lg.lgh,'')) lgh,
              ISNULL(pg.PROD_RATE,100) rate, ISNULL(st.st,0) st, MAX(CAST(ISNULL(a.USE_QTY,1) AS float)) useq,
              MIN(ISNULL(a.PLAN_YMD,'')) plan_ymd, SUM(CAST(a.PART_PLAN_QTY AS float)) pl
            FROM {PLAN_T} a WITH(NOLOCK)
            JOIN PARTNER_ERP_TEST3.nx.item b WITH(NOLOCK) ON a.ASSY_ITEM_CODE=b.ITEM_CODE
            JOIN PARTNER_ERP_TEST3.nx.item ib WITH(NOLOCK) ON a.ITEM_CODE=ib.ITEM_CODE
            JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg WITH(NOLOCK) ON a.GAGONG_PROC_CODE=pg.GAGONG_PROC_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK wk WITH(NOLOCK) ON wk.WORK_CODE=a.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu WITH(NOLOCK) ON cu.CUST_CODE=pg.IN_CUST_CODE
            LEFT JOIN (SELECT ITEM_CODE, SUM(CAST(ISNULL(TOT_ST,0) AS float)) st FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_PROC_GAGONG GROUP BY ITEM_CODE) st ON st.ITEM_CODE=a.ITEM_CODE
            LEFT JOIN (SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,'') swo, MIN(ORG_PLAN_YMD + ORG_OUTPUT_HM) lgh FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_DTL GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,'')) lg ON lg.WORK_ORDER=a.WORK_ORDER AND lg.swo=ISNULL(a.SPLIT_WORK_ORDER,'')
            WHERE {' AND '.join(w)}
            GROUP BY a.GAGONG_PROC_CODE, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE), ISNULL(pg.PART_GROUP_CODE,''),
              a.WORK_CODE, COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE), a.WORK_ORDER, a.SPLIT_WORK_ORDER,
              a.ASSY_ITEM_CODE, a.UPPER_ITEM_CODE, a.ITEM_CODE, a.PART_PLAN_YMD, ISNULL(ib.item_name,''),
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
                     "line": r["line"], "inhm": r["inhm"], "lgh": (r.get("lgh") or ''), "rate": float(r["rate"] or 100),
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
        # ★src(2026-08-23) = 410과 동일한 소스 전환.
        #   live = 라이브만(레거시 실시간) → 레거시 화면과 1:1 대사용
        #   nx(기본) = 라이브 + 웹이 올린 분 → 실무 조회(웹 실적까지 보임)
        _SRC_LIVE = (str(src).strip() == "live")
        rstock = {}; assystk = {}; saled = {}; nxcell = {}; midstk = {}; fixstk = {}
        matwh = {}; prwh = {}      # 자재창고(PU_T_MAT_STOCK_WH) / 파트창고+사급(PR_T_MAT_STOCK_WH) — 생산재고 컬럼용
        try:  # 준비재고: pu_t_ready_stock cust='Z99990', (proc_gubun=파트, item)
            # ★2026-08-18: 라이브(PARTNER_ERP.dbo) → nx 로 전환.
            #   웹 준비등록(/api/ready/commit)이 nx.PU_T_READY_STOCK 에 쓰므로, 라이브를 읽으면
            #   방금 등록한 준비재고가 화면에 0으로 보임(실제 사례: AJR30027707 S4 nx=5 / 라이브=0).
            # ★2026-08-23 재교정: nx 만 보면 이번엔 반대로, 레거시(w_pr_input_520)가 라이브에 쓴
            #   갱신분을 놓친다. nx 미러는 그 시점 이후 멈춰 있어 낡은 값이 그대로 남는다.
            #   (실측: AJR76582505 S11 → nx 207@08-21 16:51 / 라이브 159@08-24 11:08, 레거시화면=159)
            #   → ★2026-08-23 src 도입(사용자 확정): 410처럼 **소스를 사용자가 고른다**.
            #        src='live' → 라이브만 = 레거시 화면과 순수 대사(검증용)
            #        src='nx'(기본) → 라이브 + max(nx−라이브,0) = 레거시 최신값 + 웹 등록분
            #     구조: 미러가 라이브 재고를 nx 로 복사해두고 웹이 그 nx 를 읽어 쓴다.
            #     웹 준비등록(/api/ready/commit)도 같은 nx 테이블에 덧쓰므로 절대값만으로는
            #     "웹이 올린 분"과 "낡은 미러값"을 구분할 수 없다.
            #     ※미러가 멈추면(실측 2026-08-22 16:34 이후) nx 쪽에 낡은 값이 남아
            #       nx 모드에서 과다 표시될 수 있다(준비재고 26품목 +4,135). 그때는 live 로 대사.
            if _SRC_LIVE:
                cur.execute("""SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY)
                               FROM PARTNER_ERP_TEST3.nx.PU_T_READY_STOCK WHERE CUST_CODE='Z99990'
                               GROUP BY ITEM_CODE, PROC_GUBUN""")
                for rr in cur.fetchall(): rstock[(rr[0], rr[1] or '')] = float(rr[2] or 0)
            else:
                _lrs = {}; _nrs = {}
                cur.execute("""SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY)
                               FROM PARTNER_ERP_TEST3.nx.PU_T_READY_STOCK WHERE CUST_CODE='Z99990'
                               GROUP BY ITEM_CODE, PROC_GUBUN""")
                for rr in cur.fetchall(): _lrs[(rr[0], rr[1] or '')] = float(rr[2] or 0)
                try:
                    cur.execute("""SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY)
                                   FROM PARTNER_ERP_TEST3.nx.PU_T_READY_STOCK WHERE CUST_CODE='Z99990'
                                   GROUP BY ITEM_CODE, PROC_GUBUN""")
                    for rr in cur.fetchall(): _nrs[(rr[0], rr[1] or '')] = float(rr[2] or 0)
                except Exception: pass
                # ★2026-08-25 준비재고는 nx 가 정본(웹 준비등록이 여기에만 쓴다).
                #   라이브 값이 있으면 그 위에 nx 를 덮어쓴다 — max() 로는 차감이 안 잡혔다.
                rstock = dict(_lrs)
                for k, v in _nrs.items():
                    rstock[k] = v
        except Exception: pass
        try:  # ASSY 현재고: sa_t_item_stock (item)
            # ★라이브 + 웹실적(2026-08-20) — 병행운영 검증용.
            #   라이브 = 레거시 실시간(오늘 출하 반영). nx 잔액 = 어제23:59 미러 + 오늘 웹이 쓴 분.
            #   둘 중 하나만 보면 반쪽:
            #     라이브만 → 웹에서 실적 잡아도 재고가 안 변해 검증 불가
            #     nx만     → 오늘 레거시 출하가 안 빠져 키팅과 색이 갈림
            #   → 라이브 + max(nx−라이브, 0)
            #
            #   ※중복 감수(사용자 승인 2026-08-20): 같은 전표를 레거시·웹 양쪽에서 잡으면
            #     이중 계상될 수 있으나, 테스트 단계라 "웹 실적이 보이는 것"을 우선한다.
            #     (건단위 식별은 MAINT_SEQ 채번이 웹/레거시 각자 MAX+1 이라 충돌 → 불가)
            #   ★2026-08-23 src 도입: 410처럼 소스를 사용자가 고른다.
            #     src='live' → 라이브만(레거시와 순수 대사). src='nx'(기본) → 라이브+웹실적 병합.
            if _SRC_LIVE:
                cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                for rr in cur.fetchall(): assystk[rr[0]] = float(rr[1] or 0)
            else:
                _lv = {}; _nxv = {}
                cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                for rr in cur.fetchall(): _lv[rr[0]] = float(rr[1] or 0)
                try:
                    cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                    for rr in cur.fetchall(): _nxv[rr[0]] = float(rr[1] or 0)
                except Exception: pass
                # ★2026-08-25 ASSY재고 = 라이브·nx 잔액 중 '더 최근 갱신본'.
                #   원장 델타 가산은 금지 — 웹이 잔액도 함께 갱신하므로 이중계상이 된다
                #   (실측 SUB1: 실적+상위실적으로 잔액 0 이 정답인데 델타를 더해 -2).
                assystk = dict(_lv)
                try:
                    cur.execute("""SELECT ITEM_CODE, SUM(STOCK_QTY) FROM (
                                     SELECT ISNULL(l.ITEM_CODE,n.ITEM_CODE) ITEM_CODE,
                                            CASE WHEN n.ITEM_CODE IS NULL THEN l.STOCK_QTY
                                                 WHEN l.ITEM_CODE IS NULL THEN n.STOCK_QTY
                                                 WHEN ISNULL(n.UPDATE_DATETIME,'19000101')>=ISNULL(l.UPDATE_DATETIME,'19000101')
                                                      THEN n.STOCK_QTY ELSE l.STOCK_QTY END STOCK_QTY
                                       FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK l WITH(NOLOCK)
                                       FULL JOIN PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK n WITH(NOLOCK)
                                         ON l.ITEM_CODE=n.ITEM_CODE) u
                                   GROUP BY ITEM_CODE""")
                    assystk = {}
                    for _ra in cur.fetchall():
                        assystk[_ra[0]] = float(_ra[1] or 0)
                except Exception: pass
        except Exception: pass
        prdirect = {}
        try:  # ★파트재고(pr_stock) = 레거시 SP 완료풀과 동일 = PR_T_MAT_STOCK_WH만(mat_code). midstk 재귀롤업(사급/스태커 포함)은 SUB 과다 → 직접값 사용.
            # ★2026-08-18: 라이브 → nx 전환(준비재고와 동일 사유 — 웹 준비등록이 nx.PR_T_MAT_STOCK_WH 에 파트재고를 옮김)
            # ★2026-08-25 410 과 동일하게 이력계산으로 전환 — nx 잔액테이블은 레거시가 만든
            #   잔액의 행이 없어 '재고가 있는데 셀이 안 칠해지는' 원인이었다(SUB6 표시523/풀0).
            for _mk, _mv in _prod_stock_map(cur).items():
                if _mv: prdirect[_mk] = float(_mv)
        except Exception: pass
        # ★2026-08-25 사급(업체)재고를 충당풀 원천에 추가 — 410 과 동일 규칙.
        #   화면 생산재고엔 사급이 포함되는데 충당풀엔 빠져 있어, 사급만 있는 품목이
        #   "재고가 있는데 셀이 0/N 무색" 으로 나왔다(실측 AJJ30041902-SUB 8/25 키팅 0/2 ↔ 410 2/2).
        sagubstk = {}
        try:
            cur.execute("""SELECT ISNULL(n.MAT_CODE,l.MAT_CODE), SUM(
                             CASE WHEN n.MAT_CODE IS NULL THEN l.STOCK_QTY ELSE n.STOCK_QTY END)
                             FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK n WITH(NOLOCK)
                             FULL JOIN PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK l WITH(NOLOCK)
                               ON l.MAT_CODE=n.MAT_CODE
                            GROUP BY ISNULL(n.MAT_CODE,l.MAT_CODE)""")
            for rr in cur.fetchall(): sagubstk[rr[0]] = float(rr[1] or 0)
        except Exception: pass
        # ★2026-08-23 화면표시 전용(레거시 410 과 동일 정의) — 충당(prdirect/matwh/midstk)은 손대지 않는다.
        #   자재재고 = 그 품번 자체 자재창고 / 생산재고 = 파트창고+자재창고+사급재고
        #   원천은 라이브만(nx 미러가 멈추면 낡은 값이 max 합산에 살아남아 과다표시됨)
        dsp_mat = {}; dsp_pr = {}; dsp_sg = {}
        try:
            # ★2026-08-25 자재·사급재고 = 라이브∪nx 중 최신 갱신본(_latest_stock_map).
            #   자재창고는 nx 잔액이 웹실적을 즉시 반영하면서 미러본도 유지해 정확도가 높다
            #   (실측 7,740품목 중 7,511개=97% 가 이력계산 결과와 일치) → 잔액으로 충분.
            dsp_mat = _latest_stock_map(cur, "PU_T_MAT_STOCK_WH", "MAT_CODE",
                                        "CUST_CODE='Z99990' AND GAGONG_PROC_CODE NOT IN ('SA1','SA2','SB1','SB2')",
                                        ("CUST_CODE", "GAGONG_PROC_CODE"))
            # ★생산재고만 이력기준 공용계산 — nx 잔액이 미러 지연 시 웹실적만 담긴 반쪽 값이라
            #   라이브·nx 를 어떻게 조합해도 SUB1(정답0)·SUB6(정답23)을 동시에 못 맞춘다.
            dsp_pr = _prod_stock_map(cur)
            dsp_sg = _latest_stock_map(cur, "PU_T_SAGUB_STOCK", "MAT_CODE")
        except Exception: pass
        # ★중간공정 파트재고 롤업(SP #TEMP_MAT_STOCK T_SUB_CTE): 자재/생산/사급/스태커 재고 + 재귀BOM 도번고정 → tag70.
        #   ★필터 무관 전역 재고롤업이라 색(tag70)에만 영향(값/개수/계획합계는 매요청 라이브 재조회) → 90초 TTL 캐시로 재귀비용 회피(~2초 유지).
        _cache = getattr(kitting_grid, "_rollup_cache", None)
        _now = _dt.now().timestamp()
        if _cache and (_now - _cache["ts"] < 90) and _cache["mid"] and _cache.get("mwh") is not None:
            midstk = _cache["mid"]; fixstk = _cache["fix"]
            matwh = _cache["mwh"]; prwh = _cache["pwh"]   # ★생산재고 컬럼용도 캐시에 포함(빠지면 전 행 0)
        else:
            try:
                cur.execute("IF OBJECT_ID('tempdb..#tms') IS NOT NULL DROP TABLE #tms")   # 풀링 재사용 대비 선정리(#temp만, 가드 통과=IF 시작)
                cur.execute("""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code,
                               CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          -- ★파트창고(pr_t_mat_stock_wh)·자재창고(pu_t_mat_stock_wh) = 라이브 + 웹실적(2026-08-20).
                          --   웹 준비등록/바코드실적이 nx 쪽 창고를 움직이므로 그 분이 반영돼야 함.
                          --   라이브 + max(nx-라이브,0) 를 SQL 로 구현(FULL JOIN). 사급/스태커는 웹 미사용 → 라이브만.
                          FROM ( SELECT ISNULL(l.mat_code,n.mat_code) mat_code, 0 stock_qty,
                                        ISNULL(l.q,0) + CASE WHEN ISNULL(n.q,0) > ISNULL(l.q,0) THEN ISNULL(n.q,0)-ISNULL(l.q,0) ELSE 0 END pr_stock_qty
                                   FROM (SELECT mat_code, SUM(STOCK_QTY) q FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK) GROUP BY mat_code) l
                                   FULL JOIN (SELECT mat_code, SUM(STOCK_QTY) q FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK) GROUP BY mat_code) n
                                          ON l.mat_code=n.mat_code
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT ISNULL(l.mat_code,n.mat_code),
                                        ISNULL(l.q,0) + CASE WHEN ISNULL(n.q,0) > ISNULL(l.q,0) THEN ISNULL(n.q,0)-ISNULL(l.q,0) ELSE 0 END, 0
                                   FROM (SELECT mat_code, SUM(stock_qty) q FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2') GROUP BY mat_code) l
                                   FULL JOIN (SELECT mat_code, SUM(stock_qty) q FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2') GROUP BY mat_code) n
                                          ON l.mat_code=n.mat_code
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP_TEST3.nx.PU_T_STACKER_STOCK WITH(NOLOCK) ) s
                         GROUP BY s.mat_code HAVING SUM(s.stock_qty)<>0 OR SUM(s.pr_stock_qty)<>0
                        UNION ALL
                        SELECT cb.item_code, b.item_code, b.mat_code, 0, 0,
                               CONVERT(int, (CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.stock_qty) END) * b.use_qty)
                          FROM T_SUB_CTE cb JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1'
                    )
                    SELECT item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty INTO #tms FROM T_SUB_CTE OPTION(MAXRECURSION 0)""")
                cur.execute("SELECT mat_code, SUM(stock_qty), SUM(pr_stock_qty) FROM #tms GROUP BY mat_code")   # 자재+생산재고(item)
                for rr in cur.fetchall():
                    midstk[rr[0]] = float(rr[1] or 0) + float(rr[2] or 0)
                    # ★2026-08-23 생산재고 컬럼용 = 자재창고(PU_T_MAT_STOCK_WH) + 파트창고(PR_T_MAT_STOCK_WH).
                    #   기존엔 assystk(=SA_T_ITEM_STOCK)를 그대로 써서 ASSY재고와 늘 같은 값이었고,
                    #   레거시가 자재창고 1 을 보여주는 건에서 웹만 0 이 나왔다(AJR73803003 IS0001=1).
                    matwh[rr[0]] = float(rr[1] or 0)     # stock_qty = 자재창고분
                    prwh[rr[0]] = float(rr[2] or 0)      # pr_stock_qty = 파트창고+사급분
                cur.execute("SELECT upper_item_code, mat_code, SUM(fix_pr_stock_qty) FROM #tms GROUP BY upper_item_code, mat_code")  # 도번고정(upper,item)
                for rr in cur.fetchall(): fixstk[(rr[0], rr[1])] = float(rr[2] or 0)
                kitting_grid._rollup_cache = {"ts": _now, "mid": midstk, "fix": fixstk, "mwh": matwh, "pwh": prwh}
            except Exception: pass
        try:  # 출하: sa_t_sale_dtl (wo, split, item=assy, finish_flag='0') — ★결과 WORK_ORDER로 제한(전체 GROUP BY 3.7s→회피)
            wos = list({g["wo"] for g in rows if g["wo"]})
            for i in range(0, len(wos), 900):
                ck = wos[i:i + 900]; ph = ",".join("?" * len(ck))
                # ★출하 = 라이브 + 웹실적(2026-08-20) — ASSY재고와 동일 규칙.
                #   라이브 = 레거시 실시간 출하. nx = 어제23:59 미러 + 웹이 잡은 출하.
                #   웹에서 출하를 처리해도 화면에 보이도록 max(nx−라이브,0) 가산.
                #   ※중복 감수(테스트 단계) — 같은 WO를 양쪽에서 잡으면 이중 계상 가능.
                _sl = {}; _sn = {}
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): _sl[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
                try:
                    if _SRC_LIVE: raise StopIteration   # live=라이브 출하만(레거시 순수 대사)
                    cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                    for rr in cur.fetchall(): _sn[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
                except Exception: pass
                for _k2 in set(_sl) | set(_sn):
                    saled[_k2] = _sl.get(_k2, 0.0) + max(_sn.get(_k2, 0.0) - _sl.get(_k2, 0.0), 0.0)
        except Exception: pass
        try:  # ★Phase1: nx 셀단위 준비 flag = 단일원장 nx.stock_ledger(STOCK_POINT='RDY') SUM. (item×wo×파트gpc×일자INPUT_YMD)
            if _SRC_LIVE: raise StopIteration   # live=순수 레거시 대사 → 웹 셀 오버레이 제외(410 동일)
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
            g["part_ymd"] = min([c["ymd"] for c in g["_cells"].values()] or [''])   # 당일이전 셀 키(=최소 계획일)
            seq = ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
            # 1) 출하(sale, tag90) — pool=sa_t_sale_dtl[(wo,swo,assy)] (행별=제번단위 고유)
            _alloc(seq, saled.get((g["wo"], g["swo"], g["assy"]), 0.0), 90, 'finish')
        # ★2·3) 재고풀 = plan_part410과 동일한 도번단위 공유 충당(_shared): 같은 재고를 여러 행이 중복차감하던 버그(SP 대비 완료 과다) 수정.
        #   커서순(part_plan_ymd·output_hm·wo·swo) 그리디 소진 — 한 행이 쓰면 다음 행은 남은 것만.
        def _shared(keyfn, poolmap, tag, key):
            grp = {}
            for g in rows:
                for b, c in g["_cells"].items():
                    sd = (b if b != 'P' else (g["part_ymd"] or '999999'))
                    # ★2026-08-23 lgh(LG OUTPUT시간) 추가 = work_order 앞.
                    #   표시 정렬(rows.sort)에는 lgh 가 들어갔는데 충당 정렬에 없으면
                    #   "화면 위에서부터 채워지지 않는" 어긋남이 난다(제번 문자열순으로 충당).
                    #   최종납기=LG OUTPUT시간이라 이른 건이 먼저 재고를 받는다 → 화면 순서 = 충당 순서.
                    grp.setdefault(keyfn(g), []).append((c, sd, g.get("inhm") or '', g.get("plan_ymd") or '', g.get("output_hm") or g.get("inhm") or '', g.get("lgh") or '', g.get("wo") or '', g.get("swo") or ''))
            for k, lst in grp.items():
                pool = max(float(poolmap.get(k, 0.0) or 0), 0.0)
                if pool <= 0: continue
                lst.sort(key=lambda x: (x[1], x[2], x[3], x[4], x[5], x[6], x[7]))
                for c, sd, hm, _py, _ohm, _lgh, _wo, _swo in lst:
                    if pool <= 0: break
                    jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                    if jan <= 0: continue
                    if jan > pool: c[key] += pool; pool = 0.0
                    else:
                        c[key] += jan; pool -= jan
                        if tag > c["tag"] or c["tag"] == 0: c["tag"] = tag
        _assy_pool = {}; _fix_pool = {}; _mid_pool = {}
        for g in rows:
            ka = (g["assy"], g["upper"], g["item"], g["gpc"])
            if ka not in _assy_pool: _assy_pool[ka] = assystk.get(g["assy"], 0.0) * g["use_qty"]     # ASSY현재고(도번)×use — 도번단위 공유
            kf = (g["upper"], g["item"], g["gpc"])
            if kf not in _fix_pool: _fix_pool[kf] = max(fixstk.get((g["upper"], g["item"]), 0.0), 0.0)  # 도번고정재고
            km = (g["item"], g["gpc"])
            # ★2026-08-23 충당풀 = 파트창고(PR_T_MAT_STOCK_WH) + 자재창고(PU_T_MAT_STOCK_WH).
            #   기존엔 파트창고만 봐서, 자재창고에만 재고가 있는 건이 충당되지 않았다.
            #   (실측 AJR73803003: 파트창고 0 / 자재창고 1 → 웹 799/800, 레거시 800/800 노랑)
            #   화면 '생산재고' 컬럼과 동일 원천이라 "재고가 있으면 채워진다"가 성립한다.
            #   ★2026-08-25 사급 추가 — 화면 생산재고(파트+자재+사급)와 충당풀을 일치시킨다.
            if km not in _mid_pool:
                _mid_pool[km] = max(prdirect.get(g["item"], 0.0) + matwh.get(g["item"], 0.0)
                                    + sagubstk.get(g["item"], 0.0), 0.0)
        _shared(lambda g: (g["assy"], g["upper"], g["item"], g["gpc"]), _assy_pool, 70, 'finish')   # 2) ASSY 현재고
        # ★2026-08-23 도번고정재고(상위도번 재고 ×use_qty)를 완료풀에 포함 — 410 과 동일.
        #   화면엔 표시되면서 충당엔 빠져 "재고가 있는데 안 채워지던" 문제(실측 AJR30027711-SUB
        #   ASSY293+도번고정97=계획390, 웹 22/119 → 레거시 119/119).
        #   과거 제외 사유였던 SUB 과다(AJJ30041901-SUB)는 현재 fix=0 이라 재현되지 않음.
        #   초과 방지는 _shared 의 jan(=계획−완료) 상한이 담보한다.
        _shared(lambda g: (g["upper"], g["item"], g["gpc"]), _fix_pool, 70, 'finish')               # 2-1) 도번고정재고
        _shared(lambda g: (g["item"], g["gpc"]), _mid_pool, 70, 'finish')                           # 2-2) 중간공정 파트재고(=SP pr_stock)
        _shared(lambda g: (g["item"], g["gpc"]), rstock, 50, 'ready')                               # 3) 준비재고(→ready, 색tag50)
        # 4) ★nx 셀단위 준비 flag 오버레이(우리 확인분, 셀별) — 라이브 PU와 별도 합산(이중가산X), 커버 시 tag50 녹
        for g in rows:
            it = g["item"]
            seq = ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
            for c in seq:
                ck = g["part_ymd"] if c["bucket"] == 'P' else c["ymd"]
                nq = nxcell.get((it, g["wo"], g["gpc"], ck), 0.0)
                if nq > 0:
                    rem = max(c["plan"] - c["finish"] - c["ready"], 0.0)
                    if rem > 0: c["ready"] += min(nq, rem)
                    if c["plan"] > 0 and (c["finish"] + c["ready"]) >= c["plan"] and c["tag"] < 50: c["tag"] = 50
        for g in rows:
            it = g["item"]
            seq = ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
            # 셀 표시: finish_qty_NN = finish + ready; fin = tag매핑
            # ★drdy/prior_ready = 그 셀의 '준비(ready)'분만 = 준비취소 가능수량.
            #   dcov(=finish+ready)를 취소수량으로 쓰면 이미 생산실적이 잡힌 finish까지 취소하려 해서 과다취소.
            #   (2026-08-19: 이 화면이 쓰는 API가 /api/kitting/grid 임 — part410이 아님)
            g["dcov"] = {}; g["dfin"] = {}; g["drdy"] = {}
            pc = g["_cells"].get('P')
            g["prior_cover"] = round((pc["finish"] + pc["ready"]), 2) if pc else 0.0
            g["prior_ready"] = round(pc["ready"], 2) if pc else 0.0
            g["prior_fin"] = _TAG2FIN.get(pc["tag"], '0') if pc else '0'
            for y in g["days"]:
                c = g["_cells"].get(y)
                g["dcov"][y] = round((c["finish"] + c["ready"]), 2) if c else 0.0
                g["drdy"][y] = round(c["ready"], 2) if c else 0.0
                g["dfin"][y] = _TAG2FIN.get(c["tag"], '0') if c else '0'
            g["finish"] = round(sum(c["finish"] for c in g["_cells"].values()), 2)         # 완료수량=충당 finish합(SP finish_qty)
            g["ready_stock"] = round(max(rstock.get((it, g["gpc"]), 0.0), 0.0), 2)          # 준비재고(파트버킷)
            g["ready_qty"] = round(sum(c["ready"] for c in g["_cells"].values()), 2)        # 준비수량=충당 ready합(SP ready_qty)
            # ★생산재고 = 생산(파트)창고 + 자재창고 (2026-08-23, 사용자 확정)
            #   기존 assystk(SA_T_ITEM_STOCK)는 ASSY재고 컬럼과 중복이라 늘 같은 값이 나왔고,
            #   자재창고에만 재고가 있는 건은 0 으로 표시됐다(AJR73803003 자재창고 1 → 웹 0).
            # ★키팅 화면은 기존 정의 유지(파트창고+자재창고+사급) — 사급 분리는 410 만 적용.
            #   화면 컬럼이 고정배열이라 여기서 빼면 187건의 생산재고가 이유 없이 줄어든다
            #   (실측 AJJ30041902-SUB 200 → 73). 사급값은 별도 필드로도 함께 내려준다.
            g["prod_stock"] = round(dsp_pr.get(it, 0.0) + dsp_mat.get(it, 0.0) + dsp_sg.get(it, 0.0), 2)
            g["sagub_stock"] = round(dsp_sg.get(it, 0.0), 2)      # 사급(업체)재고 — 참고용
            g["assy_stock"] = round(assystk.get(g["assy"], 0.0), 2)
            g["sale"] = round(saled.get((g["wo"], g["swo"], g["assy"]), 0.0), 2)
            g["need_qty"] = round(max(g["plan_qty"] - g["ready_qty"], 0.0), 2)
            fins = [_TAG2FIN.get(c["tag"], '0') for c in g["_cells"].values() if c["plan"] > 0]
            g["fin"] = (g["prior_fin"] if g["prior_plan"] > 0 else (g["dfin"][min(g["days"])] if g["days"] else '0'))
            g["_done_all"] = bool(fins) and all(f in ('4', '6') for f in fins)
            g["_has_unkit"] = any(f == '0' for f in fins)
            g["splits"] = [{"gpc": g["gpc"], "gpcnm": g["gpcnm"], "prior_plan": g["prior_plan"], "days": dict(g["days"])}]
            del g["_cells"]
        for r in rows: r["done"] = (not r["_done_all"]); r["unkit"] = bool(r["_has_unkit"])   # ★미생산/미키팅 플래그 반환 → 프론트 즉시토글(재조회 없이 필터)
        uf = unfin.strip()
        if uf == '미생산':   rows = [r for r in rows if r["done"]]
        elif uf == '미키팅': rows = [r for r in rows if r["unkit"]]
        for r in rows: r.pop("_done_all", None); r.pop("_has_unkit", None)
        # 정렬 = 레거시 DW sort=: part_plan_ymd_output_hm → plan_ymd → gagong_proc_code → output_hm → work_order → split_work_order
        #   ★2026-08-20 실측 교정: 레거시는 "도번 블록"이 통째로 붙어 나온다.
        #     한 도번의 행이 시각으로 흩어져 있어도(예 AJR30133302 = 0851·0929·1145·1428·
        #     1430·1438·1511·1600·1625) 전부 연속 배치되고, 그 다음 도번이 이어짐.
        #     → 정렬키 = (파트, 그 도번의 최소 일자+시각, 도번) 으로 블록을 세우고,
        #       블록 안에서는 기존대로 일자+시각 → 제번 순.
        #     (레거시 화면 대조: AJR30133302 → AJR76703612(1032) → AJR76703602(1143)
        #      → AJR74289301(1300) 순서 일치)
        #     ※블록 기준은 "그 일자 안에서"의 최소 시각. 전 기간 최소로 잡으면 08/18·08/19에도
        #       있는 도번이 08/20 구간 맨 앞으로 끌려와 순서가 어긋남(실측 확인).
        _bmin = {}
        for x in rows:
            k = (x["gpc"] or "", x["part_ymd"] or "", x["item"] or "")
            v = x["inhm"] or ""
            if k not in _bmin or v < _bmin[k]:
                _bmin[k] = v
        #   ★2026-08-23 lgh(LG OUTPUT시간) 추가 = work_order 앞. PART INPUT(inhm)이 같은 행이
        #     여럿일 때 제번 문자열순으로 갈려 레거시와 순서가 달랐다(0004→000D→0026 vs 0026→002V→000D→0004).
        #     최종납기=LG OUTPUT시간이라 이른 건이 먼저. 파트별생산계획(410) 표시순서와도 동일해진다.
        #   ★★2026-09-01 line 을 inhm 앞으로 — 집계행이 라인별로 하나가 되게.
        #     프론트 집계는 **연속된 같은 (도번,라인)** 을 한 블록으로 묶는데(screens.prod.js:2480),
        #     종전엔 시각(inhm)이 라인보다 먼저라 C1 0800 → SVC 1700 → C1 1700 순으로 나왔고
        #     SVC 가 사이에 끼어 **C1 이 두 블록으로 갈렸다**(실측 AJR73965505: 211/105 로 분리).
        #     파트별계획(410)은 블록키가 gpc+item+line 뿐이라 316 한 행으로 나오는데
        #     키팅만 달라 보였다. 라인을 앞으로 올리면 같은 라인이 붙어 410 과 같아진다.
        #     ※대표 확정 규칙 = "추가계획(SVC) 라인만 나누고 나머지는 합계".
        rows.sort(key=lambda x: (x["gpc"] or "",
                                 x["part_ymd"] or "",
                                 _bmin.get((x["gpc"] or "", x["part_ymd"] or "", x["item"] or ""), ""),
                                 x["item"] or "",
                                 x.get("line") or "",
                                 x["inhm"] or "",
                                 x["plan_ymd"] or "", x.get("lgh") or "", x["wo"] or "", x["swo"] or ""))
        note = f"⚠ 상위 {limit}건 초과 — 투입파트·작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "src": (_src if _src in ("live", "nx", "new") else "nx"),
                "plan_src": PLAN_T,          # ★어느 계획테이블을 읽었는지 명시(대조용)
                "plan_sum": sum(r["plan_qty"] for r in rows), "ready_sum": sum(r["ready_qty"] for r in rows), "note": note}
    finally:
        cn.close()

# ================= 파트별 생산계획 (w_pr_input_410_new) — 키팅과 동일 SP grain·색상, 410 컬럼 =================
@router.get("/api/plan/part410/lines")
def plan_part410_lines(src: str = Query("new")):
    """파트별 생산계획 라인(LINE_NO) 드롭다운 — 실사용값(PR_T_PLAN_PART_COPY.LINE_NO) distinct.
       CA/CM/GR 등 part410 그리드의 실제 Line No 컬럼값 그대로.

       ★2026-09-04 명칭 보완(사용자 요청 "추가계획은 명칭도 추가"):
         레거시 410 라인 dddw 는 **한 목록에 두 부류**가 섞여 있다(실측 스크린샷 일치).
           ①양산 라인코드 — C1/CA/CD/CE/CG/CH/CJ/CK/CM/CP2/PA/RF2/RQ/SG (14개)
             = PR003 코드마스터에 없다 → 명칭이 없으므로 **코드만** 표시(레거시도 코드만 보인다).
           ②추가계획(주문구분) — AA=설치 · EZ=이지링크 · SVC=서비스 · KS=CKD(SAC) · KR=CKD(RAC)
             · DHZ=LG 콤프 · NG=불량대응 · GR=그린산업 · JI=Jig 제작 … (실사용 12~13개)
             = `CM_M_MASTER_DETAIL` KIND_CODE='PR003' 에 명칭이 있다 → **"코드 명칭"** 으로 표시.
         종전엔 nm=code 로 내보내 추가계획도 'AA'·'SVC' 처럼 코드만 보였다 → 무엇인지 알 수 없었다.
         ※명칭 원천은 /api/planinput/lines 와 같은 PR003. 코드체계가 다른 게 아니라 **겹친다**
           (라인칸에 양산라인과 주문구분이 함께 들어오는 구조).
       정렬 = 레거시 목록 순서와 같게 ①코드순 → ②PR003 SORT_SEQ 순."""
    _s = str(src).strip()
    SCH = "PARTNER_ERP.dbo" if _s == "live" else "PARTNER_ERP_TEST3.nx"
    _t = ("PARTNER_ERP_TEST3.nx.v_plan_part_copy_new" if _s == "new"
          else f"{SCH}.PR_T_PLAN_PART_COPY")
    cn = _conn(); cur = cn.cursor()
    try:
        # 명칭마스터(PR003) — 없거나 조회 실패해도 코드만으로 동작(드롭다운이 비지 않게)
        nm_map = {}; seq_map = {}
        try:
            cur.execute("""SELECT DETAIL_CODE, DETAIL_DESC, SORT_SEQ
                             FROM PARTNER_ERP_TEST3.nx.CM_M_MASTER_DETAIL WITH(NOLOCK)
                            WHERE KIND_CODE='PR003' AND ISNULL(USE_FLAG,'1')<>'0'""")
            for _c, _d, _q in cur.fetchall():
                _c = str(_c or "").strip()
                if not _c: continue
                _d = str(_d or "").strip()
                if _d and _d != _c: nm_map[_c] = _d
                try: seq_map[_c] = int(_q or 0)
                except Exception: seq_map[_c] = 0
        except Exception: pass
        cur.execute(f"""SELECT DISTINCT LTRIM(RTRIM(LINE_NO)) v FROM {_t} WITH(NOLOCK)
                        WHERE ISNULL(LTRIM(RTRIM(LINE_NO)),'')<>'' ORDER BY v""")
        used = [str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()]
        plain = [c for c in used if c not in nm_map]                  # ①양산 라인 = 코드만
        extra = sorted([c for c in used if c in nm_map],              # ②추가계획 = 코드 + 명칭
                       key=lambda c: (seq_map.get(c, 0), c))
        rows = ([{"code": c, "nm": c, "svc": False} for c in plain]
                + [{"code": c, "nm": f"{c} {nm_map[c]}", "desc": nm_map[c], "svc": True} for c in extra])
        return {"rows": rows}
    finally:
        cn.close()

@router.get("/api/plan/part410")
def plan_part410(from_ymd: str = Query(""), gigan: int = Query(2), wc: str = Query(""),
                 part: str = Query(""), line: str = Query(""), assy: str = Query(""), jado: str = Query(""),
                 wo: str = Query(""),
                 view: str = Query("전체"), unfin: str = Query("전체"), src: str = Query("new"),
                 wh_part: str = Query("IS0001"), limit: int = Query(20000)):
    """파트별 생산계획 그리드 — 레거시 SP `SP_PR_CREATE_PLAN_파트별_생산계획계산_생산준비등록_NEW` 로직 복제.
       ★키팅(/api/kitting/grid)과 동일 grain(gpc·wo·swo·assy·upper·item, 날짜피벗)·동일 충당·색상.
       ★src=nx(우리 PARTNER_ERP_TEST3.nx) | live(레거시 PARTNER_ERP.dbo 대사검증). live=nx셀오버레이 제외(순수 레거시).
       당김=CHANGE_DAY+','+(LOT_QTY-LAST_LOT_QTY)(전차수 대비 일자·수량 변경). 생산ST=(계획−완료)×item_st/3600.
       계상근무공수=일자ST/y_inwon(인원=PR_M_PROC_GAGONG⋈WORKER work_flag='1'). 라이브 RO(SP 미실행).

       ★2026-08-18 추가(레거시 대조 보완):
         · wo 파라미터(제번 WORK_ORDER LIKE 필터) 신규. ※프론트는 현재 클라이언트 즉시필터를 쓰므로 미사용이나 API로는 유효.
         · 응답 행에 레거시 410 재고컬럼 6종 노출(표시전용, 계산에 영향 없음):
             mat_stock(자재재고=midstk) · prod_stock(생산재고=partstk) · fix_stock(도번고정재고=fixstk[upper,item])
             assy_stock(ASSY재고=assystk) · sale_qty(출하=saled 미마감 SALE_DTL) · ready_stock(생산준비재고=rstock)
           → 원래 충당(allocation) 계산에만 쓰고 버리던 풀을 그대로 행에 붙인 것. 프론트 screens.prod.js SCREEN.partplan에서 컬럼 표시.
         · 라인 드롭다운용 /api/plan/part410/lines 신규(아래 별도 엔드포인트)."""
    from datetime import datetime as _dt, timedelta as _td
    def _yadd(y6, n):
        try: return (_dt.strptime('20' + y6, '%Y%m%d') + _td(days=n)).strftime('%y%m%d')
        except Exception: return y6
    # ★소스 3종(2026-08-26)
    #   live = 레거시 라이브 · nx = 레거시 미러(nx) · new = ★웹 자체편성(신규DB)
    #   new 는 계획 원천만 nx.v_plan_part_copy_new(=nx.plan_part_dtl 호환뷰)로 바꾸고,
    #   마스터·재고·실적은 nx 그대로 쓴다 → 레거시와 '계획' 차이만 순수 비교 가능.
    _src = str(src).strip()
    SCH = "PARTNER_ERP.dbo" if _src == "live" else "PARTNER_ERP_TEST3.nx"
    PLAN_T = ("PARTNER_ERP_TEST3.nx.v_plan_part_copy_new" if _src == "new"
              else f"{SCH}.PR_T_PLAN_PART_COPY")
    cn = _conn(); cur = cn.cursor()
    try:
        # ★편성(계획 업로드) 중이면 조회를 막고 **이유까지** 안내한다 (2026-09-04).
        #   편성은 nx.plan_part_dtl 을 재생성한다(K 49초 · T 29초). 그 사이 조회하면
        #   반쯤 만들어진/옛 데이터를 보게 되어 "숫자가 이상하다"는 오해가 난다.
        #   applock 은 편성끼리만 막으므로 조회쪽은 이 표시를 직접 본다.
        if _src == "new":
            _b = _msg = None
            try:
                from routers.planrev import plan_busy as _pb, busy_message as _bm
                _b = _pb(cur)
                if _b: _msg = _bm(_b, "파트별 생산계획")
            except HTTPException:
                raise
            except Exception:
                _b = None
            if _b:
                raise HTTPException(409, _msg or "계획 업로드(편성) 중입니다 — 잠시 후 다시 조회해 주세요.")
        d6a = _d6(from_ymd) or _dt.now().strftime('%y%m%d')
        # ★날짜 지평 = 레거시 srw ue_retrieve 산식 완전이식: to_ymd = base(기준일) 초과 (기간-1)번째 근무일.
        #   근무일 = HR_M_CALENDAR(work_team='A', time_type='A', work_stats in 1/2/5/6) ∩ pr_m_line_calendar(work_stats<>4). dates=base~to 전체 달력일(주말/휴일도 컬럼).
        gigan_n = max(1, int(gigan)); dates = []; d6b = d6a
        if gigan_n > 1:
            try:
                cur.execute("""SELECT SUBSTRING(MAX(calendar_yymd),3,6) FROM
                    (SELECT ROW_NUMBER() OVER (ORDER BY calendar_yymd) rn, calendar_yymd
                       FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR a WITH(NOLOCK)
                      WHERE work_team='A' AND calendar_yymd > ? AND time_type='A' AND work_stats IN ('1','2','5','6')
                        AND EXISTS (SELECT 1 FROM PARTNER_ERP_TEST3.nx.pr_m_line_calendar b WITH(NOLOCK)
                                    WHERE b.calendar_ymd=SUBSTRING(a.calendar_yymd,3,6) AND b.work_stats<>'4')) t
                    WHERE rn = ?""", '20' + d6a, gigan_n - 1)
                _r = cur.fetchone()
                if _r and _r[0]: d6b = str(_r[0])
            except Exception: pass
        try:   # 표시 컬럼 = base~to 전체 달력일(주말/휴일 포함)
            cur.execute("""SELECT CALENDAR_YYMD FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR
                WHERE WORK_TEAM='A' AND CALENDAR_YYMD>=? AND CALENDAR_YYMD<=? ORDER BY CALENDAR_YYMD""", '20' + d6a, '20' + d6b)
            for (_cy,) in cur.fetchall(): dates.append(str(_cy)[2:])
        except Exception: pass
        if not dates:   # 캘린더 미조회시 달력일 fallback
            i = 0
            while _yadd(d6a, i) <= d6b and i < 60: dates.append(_yadd(d6a, i)); i += 1
            if not dates: dates = [d6a]
        d6b = dates[-1]
        # ★레거시 SP(NEW2_오전오후)는 투입파트(WH) 필터 없음 — 전 GC_GUBUN='P'·GAGONG_PROC_SEQ=1 포함. (구 keys/wh_part 필터 제거: gpc≠BOM gpc 케이스 탈락 방지, wh_part 파라미터는 하위호환 위해 시그니처만 유지)
        w = ["a.part_plan_ymd<=?", "a.GC_GUBUN='P'", "a.GAGONG_PROC_SEQ=1"]; p = [d6b]
        if wc.strip():   w.append("a.WORK_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("a.GAGONG_PROC_CODE=?"); p.append(part.strip())
        if line.strip(): w.append("a.LINE_NO=?"); p.append(line.strip())
        if assy.strip(): w.append("a.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        if jado.strip(): w.append("a.ITEM_CODE LIKE ?"); p.append(f"%{jado.strip()}%")
        if wo.strip():   w.append("a.WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        cur.execute(f"""SELECT TOP {int(limit) * 40}
              a.ASSY_ITEM_CODE assy, a.UPPER_ITEM_CODE upper, a.ITEM_CODE item,
              a.GAGONG_PROC_CODE gpc, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE) gpcnm,
              ISNULL(pg.PART_GROUP_CODE,'') pgc, a.WORK_CODE wc,
              COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE) wcnm, MAX(ISNULL(a.LINE_NO,'')) line,
              a.WORK_ORDER wo, a.SPLIT_WORK_ORDER swo, a.PART_PLAN_YMD ymd,
              MAX(ISNULL(a.PART_OUTPUT_HM,'')) inhm, MAX(ISNULL(a.OUTPUT_HM,'')) output_hm, MAX(ISNULL(lg.lgh,'')) lgh, ISNULL(ib.item_name,'') nm,
              ISNULL(pg.PROD_RATE,100) rate, ISNULL(st.st,0) st, MAX(CAST(ISNULL(a.USE_QTY,1) AS float)) useq,
              MIN(ISNULL(a.PLAN_YMD,'')) plan_ymd,
              -- ★앞공정/현재공정 컬럼용(레거시 SP_..._NEW_250826 1285줄): PROC_SEQ=1이면 앞공정 0, 아니면 앞공정전표재고−현재공정전표재고
              MAX(ISNULL(a.PROC_SEQ,0)) proc_seq, MAX(ISNULL(a.GAGONG_PROC_SEQ,0)) gseq,
              MAX(ISNULL(a.PRIOR_GAGONG_PROC_CODE,'')) pgpc, MAX(ISNULL(a.PRIOR_GAGONG_PROC_SEQ,0)) pgseq,
              MAX(ISNULL(a.CHANGE_DAY,'')) change_day, SUM(CAST(ISNULL(a.LOT_QTY,0) AS float)) lot_qty,
              SUM(CAST(ISNULL(a.LAST_LOT_QTY,0) AS float)) last_lot_qty,
              SUM(CAST(a.PART_PLAN_QTY AS float)) pl
            FROM {PLAN_T} a WITH(NOLOCK)
            -- ★품목마스터는 소스토글과 무관하게 nx.item 고정(§1-9 클린 정본).
            --   {SCH}.item 으로 두면 src=live 에서 PARTNER_ERP.dbo.item(미존재) 을 찾아 500.
            JOIN PARTNER_ERP_TEST3.nx.item b WITH(NOLOCK) ON a.ASSY_ITEM_CODE=b.ITEM_CODE
            JOIN PARTNER_ERP_TEST3.nx.item ib WITH(NOLOCK) ON a.ITEM_CODE=ib.ITEM_CODE
            JOIN {SCH}.PR_M_PROC_GAGONG pg WITH(NOLOCK) ON a.GAGONG_PROC_CODE=pg.GAGONG_PROC_CODE
            LEFT JOIN {SCH}.PR_M_WORK wk WITH(NOLOCK) ON wk.WORK_CODE=a.WORK_CODE
            LEFT JOIN {SCH}.CM_M_CUST cu WITH(NOLOCK) ON cu.CUST_CODE=pg.IN_CUST_CODE
            LEFT JOIN (SELECT ITEM_CODE, GAGONG_PROC_CODE, SUM(CAST(ISNULL(TOT_ST,0) AS float)) st FROM {SCH}.PR_M_ITEM_PROC_GAGONG GROUP BY ITEM_CODE, GAGONG_PROC_CODE) st ON st.ITEM_CODE=a.ITEM_CODE AND st.GAGONG_PROC_CODE=a.GAGONG_PROC_CODE
            LEFT JOIN (SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,'') swo, MIN(ORG_PLAN_YMD + ORG_OUTPUT_HM) lgh FROM {SCH}.PR_T_PLAN_DTL GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,'')) lg ON lg.WORK_ORDER=a.WORK_ORDER AND lg.swo=ISNULL(a.SPLIT_WORK_ORDER,'')
            WHERE {' AND '.join(w)}
            GROUP BY a.GAGONG_PROC_CODE, COALESCE(pg.GAGONG_PROC_DESC, a.GAGONG_PROC_CODE), ISNULL(pg.PART_GROUP_CODE,''),
              a.WORK_CODE, COALESCE(wk.WORK_DESC, cu.CUST_DESC, a.WORK_CODE), a.WORK_ORDER, a.SPLIT_WORK_ORDER,
              a.ASSY_ITEM_CODE, a.UPPER_ITEM_CODE, a.ITEM_CODE, a.PART_PLAN_YMD, ISNULL(ib.item_name,''),
              ISNULL(pg.PROD_RATE,100), ISNULL(st.st,0)""", *p)
        cols = [d[0] for d in cur.description]
        raw = list(dict(zip(cols, r)) for r in cur.fetchall())   # ★keys(투입파트 WH='IS0001') 필터 제거 — 레거시 SP는 전 SEQ=1 GC_GUBUN='P' 포함(S5-2 등 gpc≠BOM gpc 케이스 탈락 방지)
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
                     "line": r["line"], "inhm": r["inhm"], "output_hm": (r["output_hm"] or ''), "lgh": (r["lgh"] or ''), "rate": float(r["rate"] or 100),
                     "item_st": float(r["st"] or 0) * 100.0 / (float(r["rate"] or 100) or 100),   # ★레거시 item_st = 그 파트(gpc) ST ÷ prod_rate × 100 (f_get_item_st_part/wk.prod_rate*100)
                     "use_qty": float(r["useq"] or 1),
                     "wo": r["wo"], "swo": r["swo"] or '', "plan_ymd": (r["plan_ymd"] or ''),
                     "change_day": (r["change_day"] or ''), "lot_qty": 0.0, "last_lot_qty": 0.0,
                     # ★앞공정/현재공정 산식 입력값(레거시 PR_T_PLAN_PART_COPY 원본컬럼)
                     "_proc_seq": int(r["proc_seq"] or 0), "_gseq": int(r["gseq"] or 0),
                     "_pgpc": (r["pgpc"] or '').strip(), "_pgseq": int(r["pgseq"] or 0),
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
        dsp_mat = {}; dsp_pr = {}; dsp_sg = {}   # 화면표시 전용(레거시 기준) — 자재창고 / 파트창고 / 사급재고
        # ★성능: 전역 재고 롤업(필터무관 rstock·assystk·midstk·fixstk = 색tag 전용, 값/계획합계는 매요청 라이브 재조회)을 src별 90초 TTL 캐시.
        #   재귀 #tms4 롤업(~2초)을 반복조회마다 재계산하던 것을 캐시 → 조회 고속화. 소스맵은 읽기전용(_alloc은 셀만 변경)이라 공유 안전.
        _ck = "live" if SCH.endswith("dbo") else "nx"
        _cache = getattr(plan_part410, "_stk_cache", {})
        _ent = _cache.get(_ck); _now = _dt.now().timestamp()
        # ★2026-08-25 캐시는 '무거운 것'만 — 재귀 BOM 롤업(midstk·fixstk, ~2초)뿐.
        #   나머지 단순 GROUP BY 는 실측 0.02~0.09초라 캐시할 이유가 없고,
        #   캐시에 넣으면 실적을 잡아도 최대 90초간 옛 값이 보인다(사용자 실측 ~20초 지연).
        #     준비재고 0.02 / ASSY재고 0.02 / 자재재고 0.04 / 생산재고 0.08 / 사급재고 0.09초
        #   → 준비재고·ASSY재고·파트재고·표시전용(dsp_*)은 매요청 재조회로 전환.
        _hit = bool(_ent and (_now - _ent["ts"] < 90) and _ent.get("m"))
        if _hit:
            midstk = _ent["m"]; fixstk = _ent["f"]      # 재귀 롤업만 캐시에서 복원
        if True:
            # ↓ 아래 블록(준비재고~표시전용)은 캐시 히트여도 항상 실행 = 즉시 반영.
            # ★준비재고 = nx 고정(키팅 line 113과 동일). 웹 준비등록(/api/ready/commit)이
            #   nx.PU_T_READY_STOCK 에 쓰므로 라이브를 읽으면 우리 등록분이 안 보임.
            #   (src=live 대사시에도 키팅과 같은 값이어야 두 화면 비교가 성립)
            try:
                cur.execute("SELECT ITEM_CODE, PROC_GUBUN, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.PU_T_READY_STOCK WHERE CUST_CODE='Z99990' GROUP BY ITEM_CODE, PROC_GUBUN")
                for rr in cur.fetchall(): rstock[(rr[0], rr[1] or '')] = float(rr[2] or 0)
            except Exception: pass
            # ★ASSY(완제품) 재고 = 라이브 + 웹실적(2026-08-20) — 키팅 grid 와 동일 규칙.
            #   라이브 + max(nx−라이브, 0). 중복 감수(테스트 단계) — 상세 사유는 grid 쪽 주석 참조.
            # ★2026-08-24 소스 분기 추가: src=live 면 라이브만 본다(키팅과 동일).
            #   기존엔 분기가 없어 '라이브 대사' 를 골라도 nx 가 섞여, 미러가 멈춘 동안
            #   낡은 nx 가 살아남았다(실측 AJR30122602: 라이브 40@08-24 15:35 /
            #   nx 150@08-22 → 웹 150, 레거시 40).
            try:
                _lv = {}; _nxv = {}
                cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                for rr in cur.fetchall(): _lv[rr[0]] = float(rr[1] or 0)
                if _ck == "live":
                    assystk = dict(_lv)
                else:
                    try:
                        cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
                        for rr in cur.fetchall(): _nxv[rr[0]] = float(rr[1] or 0)
                    except Exception: pass
                    # ★2026-08-25 웹 델타(SEQ>=20000) 가산 — max() 는 차감을 못 잡는다.
                    assystk = dict(_lv)
                    try:
                        cur.execute("""SELECT n.ITEM_CODE, SUM(n.MAINT_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT n WITH(NOLOCK)
                            WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT l WITH(NOLOCK)
                                              WHERE l.MAINT_YMD=n.MAINT_YMD AND l.MAINT_SEQ=n.MAINT_SEQ
                                                AND l.ITEM_CODE=n.ITEM_CODE AND l.MAINT_QTY=n.MAINT_QTY)
                            GROUP BY n.ITEM_CODE""")
                        for _ra in cur.fetchall():
                            assystk[_ra[0]] = assystk.get(_ra[0], 0.0) + float(_ra[1] or 0)
                    except Exception: pass
            except Exception: pass
            try:   # ★중간공정 파트재고(레거시 SP JOB 'B') = PR_T_MAT_STOCK_WH + PU_T_MAT_STOCK_WH by MAT_CODE(자도번), 무필터
                #   ★PR_T_MAT_STOCK_WH = nx(키팅 line 123과 동일) — 웹 준비등록이 자재를 여기로 옮김.
                #   ★PU_T_MAT_STOCK_WH(자재창고) = 라이브 + 웹실적(2026-08-20, ASSY와 동일 규칙).
                #     웹 바코드실적이 BOM 자재를 nx 자재창고에서 차감하므로 그 분도 반영돼야 함.
                # ★2026-08-24 src=live 면 파트창고도 라이브에서 읽는다(레거시 순수 대조).
                #   기본(nx)은 웹 준비등록이 옮긴 nx 파트창고를 본다.
                # ★2026-08-25 nx 파트창고는 '이력계산'으로 읽는다(_prod_stock_map).
                #   nx 잔액테이블은 레거시가 만든 잔액의 행이 없고 웹 델타만 담긴 반쪽 값이라,
                #   화면 생산재고(이력계산)에 523 이 보이는데 충당풀은 0 이라 셀이 안 칠해졌다
                #   (실측 AJR30027704-SUB6: 표시 523 / nx잔액 0 / 라이브잔액 25 → 셀 0/23 무색).
                #   src=live 는 레거시 순수대조라 라이브 잔액테이블 그대로 유지.
                if _ck == "live":
                    cur.execute("SELECT MAT_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK) GROUP BY MAT_CODE")
                    for rr in cur.fetchall(): partstk[rr[0]] = float(rr[1] or 0)
                else:
                    for _mk, _mv in _prod_stock_map(cur).items():
                        if _mv: partstk[_mk] = float(_mv)
                _ml = {}; _mn = {}
                cur.execute("SELECT MAT_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) GROUP BY MAT_CODE")
                for rr in cur.fetchall(): _ml[rr[0]] = float(rr[1] or 0)
                if _ck != "live":
                    try:
                        cur.execute("SELECT MAT_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) GROUP BY MAT_CODE")
                        for rr in cur.fetchall(): _mn[rr[0]] = float(rr[1] or 0)
                    except Exception: pass
                for _k3 in set(_ml) | set(_mn):
                    _v3 = _ml.get(_k3, 0.0) + max(_mn.get(_k3, 0.0) - _ml.get(_k3, 0.0), 0.0)
                    partstk[_k3] = partstk.get(_k3, 0.0) + _v3
                # ★2026-08-25 사급(업체)재고도 충당풀에 포함 — 색상 판정은 세 창고 합이어야 한다.
                #   화면에 사급 127 이 있는데 색이 안 칠해지던 원인(충당풀에 사급이 빠져 있었음).
                try:
                    cur.execute("""SELECT ISNULL(n.MAT_CODE,l.MAT_CODE), SUM(
                                     CASE WHEN n.MAT_CODE IS NULL THEN l.STOCK_QTY ELSE n.STOCK_QTY END)
                                     FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK n WITH(NOLOCK)
                                     FULL JOIN PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK l WITH(NOLOCK)
                                       ON l.MAT_CODE=n.MAT_CODE
                                    GROUP BY ISNULL(n.MAT_CODE,l.MAT_CODE)""")
                    for rr in cur.fetchall():
                        partstk[rr[0]] = partstk.get(rr[0], 0.0) + float(rr[1] or 0)
                except Exception: pass
                # ★2026-08-23 화면표시 전용 재고(dsp_*) — 충당(partstk/midstk)은 그대로 두고 표시만 레거시와 맞춘다.
                #   레거시 410 기준(실측 AJJ30041902-SUB: 자재재고 0 / 생산재고 127):
                #     자재재고 = 그 품번 자체의 자재창고(BOM 재귀롤업 아님)
                #     생산재고 = 파트창고 + 자재창고 + 사급재고(PU_T_SAGUB_STOCK)
                # ★2026-08-25 자재·사급재고 = 라이브∪nx 최신 갱신본(키팅과 동일 헬퍼).
                dsp_mat = _latest_stock_map(cur, "pu_t_mat_stock_wh", "MAT_CODE",
                                            "CUST_CODE='Z99990' AND GAGONG_PROC_CODE NOT IN ('SA1','SA2','SB1','SB2')",
                                            ("CUST_CODE", "GAGONG_PROC_CODE"))
                # ★생산재고만 이력기준 공용계산 — nx 잔액은 미러 지연 시 웹실적만 담긴
                #   반쪽 값이라, 라이브·nx 를 어떻게 조합해도 SUB1(0)·SUB6(23)을 동시에 못 맞춘다.
                #   생산입출고현황과 같은 원천을 쓰므로 두 화면 값이 일치한다.
                dsp_pr = _prod_stock_map(cur)          # {MAT_CODE: 전 파트 합계}
                dsp_sg = _latest_stock_map(cur, "PU_T_SAGUB_STOCK", "MAT_CODE")
            except Exception: pass
            # ★재귀 BOM 롤업(~2초)만 캐시 대상 — 히트면 위에서 복원했으므로 건너뛴다.
            try:
                if _hit: raise _RollupCached
                cur.execute("IF OBJECT_ID('tempdb..#tms4') IS NOT NULL DROP TABLE #tms4")
                cur.execute(f"""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code,
                               CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          -- ★파트/자재창고 = 라이브 + 웹실적(2026-08-20, 키팅 롤업과 동일 규칙)
                          FROM ( SELECT ISNULL(l.mat_code,n.mat_code) mat_code, 0 stock_qty,
                                        ISNULL(l.q,0) + CASE WHEN ISNULL(n.q,0) > ISNULL(l.q,0) THEN ISNULL(n.q,0)-ISNULL(l.q,0) ELSE 0 END pr_stock_qty
                                   FROM (SELECT mat_code, SUM(STOCK_QTY) q FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK) GROUP BY mat_code) l
                                   FULL JOIN (SELECT mat_code, SUM(STOCK_QTY) q FROM PARTNER_ERP_TEST3.nx.pr_t_mat_stock_wh WITH(NOLOCK) GROUP BY mat_code) n
                                          ON l.mat_code=n.mat_code
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT ISNULL(l.mat_code,n.mat_code),
                                        ISNULL(l.q,0) + CASE WHEN ISNULL(n.q,0) > ISNULL(l.q,0) THEN ISNULL(n.q,0)-ISNULL(l.q,0) ELSE 0 END, 0
                                   FROM (SELECT mat_code, SUM(stock_qty) q FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2') GROUP BY mat_code) l
                                   FULL JOIN (SELECT mat_code, SUM(stock_qty) q FROM PARTNER_ERP_TEST3.nx.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2') GROUP BY mat_code) n
                                          ON l.mat_code=n.mat_code
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP_TEST3.nx.PU_T_STACKER_STOCK WITH(NOLOCK) ) s
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
            # ★캐시는 무거운 재귀 롤업(midstk·fixstk)만. 나머지는 매요청 재조회하므로
            #   여기 담아두면 낡은 값이 되살아날 여지만 생긴다(실적 반영 지연의 원인).
            #   ★히트일 때는 다시 쓰지 않는다 — ts 가 갱신되면 캐시가 영원히 안 만료된다.
            if not _hit:
                _cache[_ck] = {"ts": _now, "m": midstk, "f": fixstk}
                plan_part410._stk_cache = _cache
        # ★출하는 항상 라이브 직독(2026-08-20) — 준비실적처리(키팅 /api/kitting/grid line 160)와 동일.
        #   기존엔 {SCH}(src 따라감)라 src=nx 일 때 nx.SA_T_SALE_DTL 을 봤는데, 최근 출하가 nx에
        #   아직 안 넘어와(실측: 라이브 305,335건 vs nx 305,285건) 같은 행이 두 화면에서
        #   다른 색으로 보였음(키팅=주황 출하완료 / 410=노랑 생산완료).
        #   예: WO 6I1M0BG2 AJR52676202 출하 1 — 라이브에만 존재.
        #   출하는 조회 전용(쓰기 없음)이라 라이브 직독이 안전.
        try:
            wos = list({g["wo"] for g in rows if g["wo"]})
            for i in range(0, len(wos), 900):
                ck = wos[i:i + 900]; ph = ",".join("?" * len(ck))
                # ★출하 = 라이브 + 웹실적(2026-08-20) — ASSY재고와 동일 규칙.
                #   라이브 = 레거시 실시간 출하. nx = 어제23:59 미러 + 웹이 잡은 출하.
                #   웹에서 출하를 처리해도 화면에 보이도록 max(nx−라이브,0) 가산.
                #   ※중복 감수(테스트 단계) — 같은 WO를 양쪽에서 잡으면 이중 계상 가능.
                _sl = {}; _sn = {}
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): _sl[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
                try:
                    if _ck == "live": raise StopIteration   # ★2026-08-24 live=라이브 출하만(레거시 대조)
                    cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP_TEST3.nx.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                    for rr in cur.fetchall(): _sn[(rr[0], rr[1] or '', rr[2])] = float(rr[3] or 0)
                except Exception: pass
                for _k2 in set(_sl) | set(_sn):
                    saled[_k2] = _sl.get(_k2, 0.0) + max(_sn.get(_k2, 0.0) - _sl.get(_k2, 0.0), 0.0)
        except Exception: pass
        # ★생산완료(70): 레거시 SP_..._NEW2_오전오후는 실제생산(PROD_DTL) 미사용 — "완료된 전표는 이미 ASSY재고·파트재고로 잡히므로 감안 불필요"(SP주석).
        #   → 아래 충당에서 assystk(ASSY재고)+partstk(중간파트재고)+jpstk(작업중 전표재고) 3풀로 완료 처리. (earliest_ymd는 참고용 미사용)
        _ = earliest_ymd
        # ★전표재고(J, tag40)=작업중 용접전표(PR_T_INDI_WELD_SHEET prod_fin_flag='0')의 최종공정 잔량(prod_qty−완료).
        #   ★2026-08-19 수정: 이 쿼리만 PARTNER_ERP.dbo 하드코딩이라, src=nx 여도 라이브를 봤음.
        #     → 웹(w_pr_input_520)에서 잡은 실적이 nx.PR_T_INDI_WELD_SHEET_DTL 에 쌓이는데
        #       410 화면의 현재공정(진주황)·전표재고가 영영 안 변하던 원인. SCH(=src) 따라가도록 교정.
        #   src별 90초 캐시(캐시키에 SCH 포함 — 안 그러면 live/nx 결과가 서로 섞임).
        jpstk = {}; jpseq = {}    # jpseq = (item,gpc,seq)별 전표재고 → 앞공정·현재공정 컬럼 산식용
        _jck = "jp:" + SCH
        _jent = _cache.get(_jck)
        if _jent and (_now - _jent["ts"] < 90):
            jpstk = _jent["j"]; jpseq = _jent.get("q", {})
        else:
            try:
                cur.execute(f"""
                    SELECT t.gagong_proc_code gpc, t.gagong_proc_seq seq, s.item_code item, SUM(t.prod_qty - s.finish_prod_qty) stk
                    FROM {SCH}.PR_T_INDI_WELD_SHEET_DTL t WITH(NOLOCK)
                    JOIN (SELECT t.sheet_no, t.gagong_proc_code, t.gagong_proc_seq, MAX(s.to_proc_seq) to_proc_seq, MAX(s.item_code) item_code,
                                 ISNULL((SELECT TOP 1 prod_qty FROM {SCH}.PR_T_INDI_WELD_SHEET_DTL WITH(NOLOCK) WHERE sheet_no=t.sheet_no ORDER BY proc_seq DESC),0) finish_prod_qty
                          FROM {SCH}.PR_T_INDI_WELD_SHEET_DTL t WITH(NOLOCK)
                          JOIN (SELECT b.sheet_no, b.gagong_proc_code, b.gagong_proc_seq, MAX(b.proc_seq) to_proc_seq, MAX(a.item_code) item_code
                                FROM {SCH}.PR_T_INDI_WELD_SHEET a WITH(NOLOCK) JOIN {SCH}.PR_T_INDI_WELD_SHEET_DTL b WITH(NOLOCK) ON a.sheet_no=b.sheet_no
                                WHERE a.prod_fin_flag='0' GROUP BY b.sheet_no, b.gagong_proc_code, b.gagong_proc_seq) s
                               ON t.sheet_no=s.sheet_no AND t.proc_seq=s.to_proc_seq
                          GROUP BY t.sheet_no, t.gagong_proc_code, t.gagong_proc_seq) s ON s.sheet_no=t.sheet_no AND s.to_proc_seq=t.proc_seq
                    WHERE t.gagong_proc_code IS NOT NULL
                    GROUP BY t.gagong_proc_code, t.gagong_proc_seq, s.item_code""")
                # ★(item,gpc) 집계 = 기존 충당용 / (item,gpc,seq) 집계 = 앞공정·현재공정 컬럼용(레거시 #TEMP_전표재고 그레인 동일)
                for rr in cur.fetchall():
                    _gpc, _seq, _it, _q = rr[0], rr[1], rr[2], float(rr[3] or 0)
                    jpstk[(_it, _gpc)] = jpstk.get((_it, _gpc), 0.0) + _q
                    jpseq[(_it, _gpc, int(_seq or 0))] = jpseq.get((_it, _gpc, int(_seq or 0)), 0.0) + _q
            except Exception: pass
            _cache[_jck] = {"ts": _now, "j": jpstk, "q": jpseq}
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
        # ★색: 90출하='6'(살구 #fac090) · 70생산='4'(노랑) · 50/10준비='3'(녹) · 30자재='2' · 0='0'(백,미키팅)
        # ★2026-08-18 수정: 40(작업중 전표=현재공정)을 '7'(진한주황)로 신설.
        #   기존엔 '0'(백)이었으나 레거시 화면 대조 결과 전표 잔량 셀도 완료색으로 표시됨(예: AJR76562804 13/13·2/2).
        #   단 출하완료(90,살구)와 같은 색이면 구분이 안 되므로 별도 코드 '7'로 분리(프론트 finBg에서 진한주황).
        #   미생산 판정은 여전히 finish 기반이라 이 색 변경이 건수에 영향 없음.
        _TAG2FIN = {90: '6', 70: '4', 40: '7', 50: '3', 10: '3', 30: '2'}
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
        def _shared(keyfn, poolmap, tag, key, force=False):
            grp = {}
            for g in rows:
                for b, c in g["_cells"].items():
                    sd = (b if b != 'P' else (g["part_ymd"] or '999999'))
                    # ★배분순서 = 레거시 SP 커서 order by (part_plan_ymd, part_output_hm, plan_ymd, output_hm, work_order, split_work_order) 완전이식 → 동순위 행 충당 일치
                    #   ★2026-08-23 lgh(LG OUTPUT시간) 추가 = work_order 앞. 당일이전 칸은 part_ymd·inhm·plan_ymd·ohm 이
                    #   전부 같은 행이 여러 건 몰려(동일 제번 분할) work_order 문자열순으로 갈리던 탓에
                    #   OUTPUT 13:15 건이 08:30 건보다 먼저 충당되는 역전이 났다. 최종납기=LG OUTPUT시간이라 이른 건이 먼저.
                    #   (화면 정렬 rows.sort 는 이미 lgh 를 wo 앞에 두고 있어 표시순서와도 일치)
                    grp.setdefault(keyfn(g), []).append((c, sd, g.get("inhm") or '', g.get("plan_ymd") or '', g.get("output_hm") or g.get("inhm") or '', g.get("lgh") or '', g.get("wo") or '', g.get("swo") or ''))
            for k, lst in grp.items():
                pool = max(float(poolmap.get(k, 0.0) or 0), 0.0)
                if pool <= 0: continue
                lst.sort(key=lambda x: (x[1], x[2], x[3], x[4], x[5], x[6], x[7]))
                for c, sd, hm, _py, _ohm, _lgh, _wo, _swo in lst:
                    if pool <= 0: break
                    jan = c["plan"] - c["finish"] - (c["ready"] if key == 'ready' else 0.0)
                    if jan <= 0: continue
                    if jan > pool: c[key] += pool; pool = 0.0
                    else:
                        c[key] += jan; pool -= jan
                        if force or tag > c["tag"] or c["tag"] == 0: c["tag"] = tag   # force=레거시 last-write(J 전표가 준비 태그 덮어씀)
        # ★생산완료(70): 레거시 SP_..._NEW2_오전오후 재현 = ASSY재고(×use) + 중간파트재고 2풀. (PROD_DTL 아님 — 완료전표는 이미 재고로 잡힘)
        # ★풀 그룹키에 gpc 포함 = 레거시 SP 그룹경계(A:assy,bomlvl,upper,item,PROC · B:item,PROC_SEQ) 이식. proc_seq↔gpc(파트) → 파트별 독립 풀(전체조회시 파트간 공유 방지, 파트필터시 동일).
        _assy_pool = {}; _part_pool = {}; _fixp = {}
        for g in rows:
            ka = (g["assy"], g["upper"], g["item"], g["gpc"])
            if ka not in _assy_pool: _assy_pool[ka] = assystk.get(g["assy"], 0.0) * g["use_qty"]   # 제품(ASSY)재고 = SA_T_ITEM_STOCK(도번)×use_qty
            kp = (g["item"], g["gpc"])
            if kp not in _part_pool: _part_pool[kp] = partstk.get(g["item"], 0.0)                   # 중간파트재고(자도번, 파트별 독립)
            # ★2026-08-23 도번고정재고(상위도번 재고 ×use_qty) 충당 추가.
            #   화면에는 표시되면서 충당에는 빠져 있어 "재고가 있는데 안 채워지는" 문제.
            #   실측 AJR30027711-SUB: ASSY재고 293 + 도번고정 97 = 계획 390 전량 충당돼야 한다
            #   (웹 22/119 → 레거시 119/119). 풀 단위 = (상위도번, 자도번, 파트).
            kx = (g["upper"], g["item"], g["gpc"])
            if kx not in _fixp: _fixp[kx] = max(fixstk.get((g["upper"], g["item"]), 0.0), 0.0)
        # ★레거시 pool 적용순서 A→B→C→J 완전이식: 준비재고(C)를 전표(J)보다 먼저 소진 → 키팅부품이 작업중전표로 먼저 빠지고 남은 준비재고만 녹색(이중 녹색표시 방지).
        _shared(lambda g: (g["assy"], g["upper"], g["item"], g["gpc"]), _assy_pool, 70, 'finish')   # A: 제품(ASSY)재고
        _shared(lambda g: (g["upper"], g["item"], g["gpc"]), _fixp, 70, 'finish')                   # A-2: 도번고정재고(상위도번 재고)
        _shared(lambda g: (g["item"], g["gpc"]), _part_pool, 70, 'finish')                          # B: 중간공정 파트재고(PR+PU_T_MAT_STOCK_WH by 자도번)
        _shared(lambda g: (g["item"], g["gpc"]), rstock, 50, 'ready')                      # C: 준비재고 → 색(녹)만·미생산 판정 제외 (전표보다 먼저 소진)
        _shared(lambda g: (g["item"], g["gpc"]), jpstk, 40, 'finish', force=True)          # J: 작업중 전표재고(용접시트, 라이브) → finish 가산, 준비 태그 덮어씀(레거시 last-write)
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
            g["dcov"] = {}; g["dfin"] = {}; g["drdy"] = {}
            pc = g["_cells"].get('P')
            # ★완료수량(분자)=생산실적(finish)만. 준비(키팅완료)는 숫자 아닌 색(녹)으로만 표시. 색tag는 최고단계(생산/키팅/미키팅) 유지.
            # ★drdy = 그 셀의 '준비(ready)'분만 = 준비취소 가능수량.
            #   dcov(=finish, 생산실적)는 준비취소로 되돌릴 수 없음.
            #   (2026-08-18 버그: 셀 18/18에서 18을 취소수량으로 넘겨 실제 준비 1개보다 과다 취소 시도)
            g["prior_cover"] = round(pc["finish"], 2) if pc else 0.0
            g["prior_ready"] = round(pc["ready"], 2) if pc else 0.0
            g["prior_fin"] = _TAG2FIN.get(pc["tag"], '0') if pc else '0'
            for y in g["days"]:
                c = g["_cells"].get(y)
                g["dcov"][y] = round(c["finish"], 2) if c else 0.0
                g["drdy"][y] = round(c["ready"], 2) if c else 0.0
                g["dfin"][y] = _TAG2FIN.get(c["tag"], '0') if c else '0'
            g["finish"] = round(sum(c["finish"] for c in g["_cells"].values()), 2)
            g["lot_diff"] = round(g["lot_qty"] - g["last_lot_qty"], 2)
            # ★레거시 410 재고 컬럼(화면표시용) — 충당에 쓰던 풀을 그대로 노출. 표시 전용(계산 영향 없음).
            # ★2026-08-23 표시값을 레거시 410 과 일치시킴(충당은 midstk/partstk 그대로 유지).
            #   자재재고 = 그 품번 자체 자재창고(기존 midstk 는 BOM 재귀롤업이라 213 처럼 부풀었음)
            #   생산재고 = 파트창고 + 자재창고 + 사급재고(기존 partstk 는 사급 누락 + nx 낡은값 혼입)
            #   실측 AJJ30041902-SUB: 레거시 자재 0 / 생산 127(=사급) ↔ 기존 웹 213 / 86
            # ★2026-08-25 세 컬럼을 창고별로 완전히 분리 — 서로 겹치지 않게 한다.
            #   구버전은 생산재고 = 파트창고+자재창고(+사급) 이라 파트창고가 0 이면
            #   자재재고와 똑같은 값이 두 컬럼에 표시됐다(실측 AJJ30041902-SUB 둘 다 73).
            #     자재재고 = 자재창고(PU_T_MAT_STOCK_WH)
            #     생산재고 = 파트창고(PR_T_MAT_STOCK_WH) — 이력기준 계산
            #     사급재고 = 사급(PU_T_SAGUB_STOCK)
            g["mat_stock"]   = round(dsp_mat.get(g["item"], 0.0), 2)                      # 자재재고(자재창고)
            g["prod_stock"]  = round(dsp_pr.get(g["item"], 0.0), 2)                       # 생산재고(파트창고만)
            g["sagub_stock"] = round(dsp_sg.get(g["item"], 0.0), 2)                       # 사급(업체)재고
            g["fix_stock"]   = round(fixstk.get((g["upper"], g["item"]), 0.0), 2)         # 도번고정재고(upper,item)
            g["assy_stock"]  = round(assystk.get(g["assy"], 0.0), 2)                      # ASSY재고(제품재고)
            g["sale_qty"]    = round(saled.get((g["wo"], g["swo"], g["assy"]), 0.0), 2)   # 출하(미마감 SALE_DTL)
            g["ready_stock"] = round(rstock.get((g["item"], g["gpc"]), 0.0), 2)           # 생산준비재고(키팅 준비분)
            # ★앞공정/현재공정 (레거시 SP_PR_CREATE_PLAN_파트별_생산계획계산_NEW_250826):
            #   현재공정 = #TEMP_전표재고[자기 gpc·gseq·item]  (작업중 전표의 그 공정 잔량)
            #   앞공정   = PROC_SEQ=1 → 0, else #TEMP_전표재고[PRIOR_gpc·PRIOR_seq·item] − 현재공정
            #   → 01라인(용접S5→조립S5-2)처럼 2공정인 경우, 뒷공정 실적이 잡히면 앞공정 잔량이 상계돼 0이 됨.
            _cur_jp = jpseq.get((g["item"], g["gpc"], g["_gseq"]), 0.0)
            _prv_jp = jpseq.get((g["item"], g["_pgpc"], g["_pgseq"]), 0.0) if g["_pgpc"] else 0.0
            g["cur_proc"]  = round(_cur_jp, 2)
            g["prev_proc"] = 0.0 if g["_proc_seq"] == 1 else round(_prv_jp - _cur_jp, 2)
            cells_p = [c for c in g["_cells"].values() if c["plan"] > 0]   # ★미생산=셀별 finish<plan(레거시 finish_qty<plan_qty). 전표(J)도 finish 채워 완료 산입(색=백과 무관)
            g["_done_all"] = bool(cells_p) and all(c["finish"] >= c["plan"] for c in cells_p)
            del g["_cells"]
            for _k in ("_proc_seq", "_gseq", "_pgpc", "_pgseq"): g.pop(_k, None)   # 앞공정 산식용 내부값 — 응답에서 제거
        for r in rows: r["done"] = bool(r.get("_done_all"))   # ★미생산여부 플래그 → 프론트가 전체 1회조회 후 미생산 토글을 즉시(재조회 없이) 필터
        uf = unfin.strip()
        if uf == '미생산': rows = [r for r in rows if not r["done"]]
        for r in rows: r.pop("_done_all", None)
        # ★정렬 = 레거시 DW setsort(자도번 기본 sort_flag='1'): part_group_code → part_plan_ymd_output_hm → item_code → plan_ymd → output_hm → lg_plan_ymd_output_hm → work_order → split_work_order
        #   ★2026-08-20: 준비실적처리(키팅 /api/kitting/grid)와 정렬을 통일.
        #     같은 도번의 행이 시각으로 흩어지면(예 AJR30133302 = 0851·1145·1428·1511)
        #     두 화면 순서가 달라져 대조가 안 됨 → 도번 블록을 통째로 붙인다.
        #     키 = 파트그룹 → 일자 → (그 일자 안 도번의 최소 시각) → 도번 → 시각 → …
        #     ※최소시각을 전 기간으로 잡으면 앞 일자에도 있는 도번이 끌려오므로 일자별로 산출.
        _bmin4 = {}
        for x in rows:
            k = (x["pgc"] or "", x["part_ymd"] or "", x["item"] or "")
            v = x["inhm"] or ""
            if k not in _bmin4 or v < _bmin4[k]:
                _bmin4[k] = v
        # ★2026-09-01 line 을 inhm 앞으로 — 키팅(/api/kitting/grid)과 동일 규칙.
        #   프론트 집계 블록키가 (도번,라인)이라 시각이 먼저면 SVC 가 끼어 같은 라인이 갈린다.
        rows.sort(key=lambda x: ((x["pgc"] or ""),
                                 (x["part_ymd"] or ""),
                                 _bmin4.get((x["pgc"] or "", x["part_ymd"] or "", x["item"] or ""), ""),
                                 (x["item"] or ""),
                                 (x.get("line") or ""),
                                 (x["inhm"] or ""),
                                 (x["plan_ymd"] or ""), (x["output_hm"] or ""), (x["lgh"] or ""),
                                 (x["wo"] or ""), (x["swo"] or "")))
        # ★item_st 정본 = 생산정보등록(생산공정순서) ST(초), ★그 파트(gpc)의 공정만 합산 ÷ prod_rate × 100 (레거시 f_get_item_st_part/wk.prod_rate*100 동일). nx우선(있으면 override), 없으면 레거시 PR_M_ITEM_PROC_GAGONG 유지.
        #   생산ST=(계획−완료)×item_st/3600. src=live(순수 레거시 대사)는 레거시값 유지.
        if str(src).strip() != "live":
            try:
                nxc2 = _nx(); nc2 = nxc2.cursor()
                items = list({g["item"] for g in rows if g["item"]}); nxst = {}
                for i in range(0, len(items), 900):
                    ck = items[i:i + 900]; ph = ",".join("?" * len(ck))
                    nc2.execute(f"SELECT item_code, gagong_proc_code, SUM(CAST(ISNULL(tot_st,0) AS float)) FROM nx.prodinfo_proc WHERE item_code IN ({ph}) GROUP BY item_code, gagong_proc_code", *ck)
                    for rr in nc2.fetchall(): nxst[(rr[0], rr[1])] = float(rr[2] or 0)
                nxc2.close()
                for g in rows:
                    if (g["item"], g["gpc"]) in nxst: g["item_st"] = nxst[(g["item"], g["gpc"])] * 100.0 / (float(g["rate"] or 100) or 100)   # 그 파트 ST ÷ prod_rate × 100
            except Exception: pass
        # 인원(y_inwon) — 레거시: COUNT(PR_M_PROC_GAGONG⋈WORKER work_flag='1', 파트필터 gpc·part_group like)
        # ★2026-08-25 화면은 전체를 한 번 받아 파트를 클라이언트에서 필터하므로(재조회 없음)
        #   인원도 파트별 맵(inwon_by)으로 같이 내려준다. 안 그러면 파트를 골라도
        #   계상근무공수가 늘 전체인원(111명)으로 나눠져 값이 틀린다.
        inwon = 0
        inwon_by = {}
        try:
            gp = (part.strip() or '%')
            cur.execute(f"""SELECT COUNT(*) FROM {SCH}.PR_M_PROC_GAGONG a
                JOIN {SCH}.PR_M_PROC_GAGONG_WORKER b ON a.GAGONG_PROC_CODE=b.GAGONG_PROC_CODE
                WHERE b.WORK_FLAG='1' AND a.GAGONG_PROC_CODE LIKE ?""", gp)
            inwon = int(cur.fetchone()[0] or 0)
            cur.execute(f"""SELECT a.GAGONG_PROC_CODE, COUNT(*) FROM {SCH}.PR_M_PROC_GAGONG a
                JOIN {SCH}.PR_M_PROC_GAGONG_WORKER b ON a.GAGONG_PROC_CODE=b.GAGONG_PROC_CODE
                WHERE b.WORK_FLAG='1' GROUP BY a.GAGONG_PROC_CODE""")
            inwon_by = {str(r[0]).strip(): int(r[1] or 0) for r in cur.fetchall()}
        except Exception: pass
        note = f"⚠ 상위 {limit}건 초과 — 파트·작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "src": (_src if _src in ("live", "nx", "new") else "nx"),
                "plan_src": PLAN_T,          # ★어느 계획테이블을 읽었는지 명시(대조용)
                "plan_sum": sum(r["plan_qty"] for r in rows), "inwon": inwon,
                "inwon_by": inwon_by, "note": note}
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
        lm = _lock_msg(nc, ymd)   # ★공통 마감잠금(정본 STOCK_GATING_CLOSE_LOCK_RULES.md)
        if lm: return {"ok": False, "detail": lm}
        nc.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        seq = int(nc.fetchone()[0] or 1)
        nc.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,GAGONG_PROC_CODE,
              WORK_ORDER,INPUT_YMD,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('RDY',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,'K1','Z99990',?,?,?,?,?,'키팅확인',?,GETDATE())""",
            seq, item, gpc, (wo or None), (ymd or None), qty, user)
        stock_changed("kitting_confirm")      # ★RDY 원장 변경 → 수불장 캐시 버림
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
        lm = _lock_msg(nc, ymd)   # ★공통 마감잠금
        if lm: return {"ok": False, "detail": lm}
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
