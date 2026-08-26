# -*- coding: utf-8 -*-
"""gagong 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_prod_stock_map, _conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

from routers.kitting import kitting_grid
router = APIRouter()

# ===== 가공생산진척관리 nx 재현본(레거시 암호화 SP 탈피) — 확정사양 _legacy_analysis/GAGONGPROG_420_NX_REBUILD_PLAN.md =====
@router.get("/api/gagong/prog420nx")
def gagong_prog420nx(from_ymd: str = Query(""), gigan: int = Query(2), wc: str = Query("P2"),
                     item: str = Query(""), jado: str = Query(""), unfin: str = Query("전체"),
                     plansrc: str = Query("new"), limit: int = Query(8000)):
    """가공생산진척관리 nx 재현. 그레인=(assy도번, 가공컴포넌트 item), WO집계.
       base=PR_T_PLAN_PART_COPY GC_GUBUN='Q' AND WORK_CODE=@wc GROUP BY (assy,item), 날짜피벗.
       finish=출하90(×use)→가공창고20(mat공유)→ASSY재고70(×use,행별)→자재30(pr+sg+stock,mat공유)→fix / 공유풀 assy정렬.
       ready=가공전표10(PR_T_INDI_CUTTING PROD_FLAG='0'). 색 90주황/70·30노랑/20민트/10녹/0백. 오라클 SP_PR_가공생산진척관리_260602와 diff0 목표."""
    from datetime import datetime as _dt, timedelta as _td
    def _yadd(y6, n):
        try: return (_dt.strptime('20' + y6, '%Y%m%d') + _td(days=n)).strftime('%y%m%d')
        except Exception: return y6
    S = "PARTNER_ERP_TEST3.nx"
    # ★계획원천 토글(2026-08-26) — 410·키팅·040 과 동일 규칙.
    #   nx(기본) = 레거시 편성 미러 / new = 웹 자체편성(신규DB, nx.plan_part_dtl 호환뷰)
    #   계획만 갈아끼우고 재고·실적은 그대로 → '계획' 차이만 순수 비교.
    _psrc = str(plansrc).strip()
    PLAN_T = (f"{S}.v_plan_part_copy_new" if _psrc == "new" else f"{S}.PR_T_PLAN_PART_COPY")
    wcc = (wc.strip() or 'P2')
    cn = _conn(); cur = cn.cursor()
    try:
        d6a = _d6(from_ymd) or _dt.now().strftime('%y%m%d')
        gigan_n = max(1, int(gigan)); dates = []; d6b = d6a
        if gigan_n > 1:
            try:
                cur.execute("""SELECT SUBSTRING(MAX(calendar_yymd),3,6) FROM
                    (SELECT ROW_NUMBER() OVER (ORDER BY calendar_yymd) rn, calendar_yymd FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR a WITH(NOLOCK)
                      WHERE work_team='A' AND calendar_yymd > ? AND time_type='A' AND work_stats IN ('1','2','5','6')
                        AND EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pr_m_line_calendar b WITH(NOLOCK) WHERE b.calendar_ymd=SUBSTRING(a.calendar_yymd,3,6) AND b.work_stats<>'4')) t
                    WHERE rn=?""", '20' + d6a, gigan_n - 1)
                _r = cur.fetchone()
                if _r and _r[0]: d6b = str(_r[0])
            except Exception: pass
        try:
            cur.execute("""SELECT CALENDAR_YYMD FROM PARTNER_ERP_TEST3.nx.HR_M_CALENDAR WHERE WORK_TEAM='A' AND CALENDAR_YYMD>=? AND CALENDAR_YYMD<=? ORDER BY CALENDAR_YYMD""", '20' + d6a, '20' + d6b)
            for (_cy,) in cur.fetchall(): dates.append(str(_cy)[2:])
        except Exception: pass
        if not dates:
            i = 0
            while _yadd(d6a, i) <= d6b and i < 60: dates.append(_yadd(d6a, i)); i += 1
            if not dates: dates = [d6a]
        d6b = dates[-1]
        # base: (assy, item) grain, part_plan_ymd 피벗
        w = ["a.GC_GUBUN='Q'", "a.WORK_CODE=?", "a.part_plan_ymd<=?"]; p = [wcc, d6b]
        if item.strip(): w.append("a.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if jado.strip(): w.append("a.ITEM_CODE LIKE ?"); p.append(f"%{jado.strip()}%")
        # ★그레인 = (assy, UPPER_ITEM_CODE, item). 오라클 raw 680행과 정확일치(=677유니크+3 SUB변형 upper별 분리행). (assy,item)으로 합치면 -S5-1/-S5-2가 뭉쳐 계획 과다.
        cur.execute(f"""SELECT a.ASSY_ITEM_CODE assy, a.ITEM_CODE item, a.PART_PLAN_YMD ymd,
              ISNULL(a.UPPER_ITEM_CODE,'') upper, MIN(a.BOM_LEVEL) bl, MAX(ISNULL(a.GAGONG_PROC_CODE,'')) gpc,
              MAX(CAST(ISNULL(a.USE_QTY,1) AS float)) useq, MIN(ISNULL(a.PLAN_YMD,'')) plan_ymd,
              MAX(ISNULL(a.PART_OUTPUT_HM,'')) phm, MAX(ISNULL(a.OUTPUT_HM,'')) ohm, MAX(ISNULL(a.WORK_ORDER,'')) wo,
              MAX(ISNULL(a.LINE_NO,'')) line_no, MAX(ISNULL(a.TUIP_GAGONG_PROC_CODE,'')) tuip,
              SUM(CAST(a.PART_PLAN_QTY AS float)) pl
            FROM {PLAN_T} a WITH(NOLOCK)
            WHERE {' AND '.join(w)}
            GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE, ISNULL(a.UPPER_ITEM_CODE,''), a.PART_PLAN_YMD""", *p)
        cols = [d[0] for d in cur.description]
        keyed = {}
        for rr in cur.fetchall():
            r = dict(zip(cols, rr)); ymd = r["ymd"]
            bucket = 'P' if ymd < d6a else (ymd if ymd in dates else None)
            if bucket is None: continue
            k = (r["assy"], r["upper"], r["item"]); g = keyed.get(k)
            if not g:
                g = {"assy": r["assy"], "item": r["item"], "upper": r["upper"] or '', "bl": int(r["bl"] or 0), "gpc": r["gpc"] or '',
                     "use": float(r["useq"] or 1), "plan_ymd": r["plan_ymd"] or '', "phm": r["phm"] or '',
                     "ohm": r["ohm"] or '', "wo": r["wo"] or '', "line_no": r["line_no"] or '', "tuip": r["tuip"] or '', "_cells": {}}
                keyed[k] = g
            c2 = g["_cells"].get(bucket)
            if not c2:
                c2 = {"ymd": ymd, "plan": 0.0, "fin": 0.0, "ready": 0.0, "tag": 0}; g["_cells"][bucket] = c2
            c2["plan"] += float(r["pl"] or 0)
        rows = list(keyed.values())
        assys = list({g["assy"] for g in rows}); mats = list({g["item"] for g in rows})
        # 풀 로드 (nx, 전부 오라클 diff0 검증됨)
        proc = {}; assyst = {}; jae = {}; fixm = {}; sale = {}; ing = {}
        # ★2026-08-25 가공파트(P0001) 재고도 이력기준 공용계산으로 통일.
        _psm = _prod_stock_map(cur, by_part=True)
        for (_m, _p), _v in _psm.items():
            if _p == 'P0001' and _v:
                proc[_m] = proc.get(_m, 0.0) + _v
        cur.execute(f"SELECT ITEM_CODE, SUM(STOCK_QTY) FROM {S}.sa_t_item_stock GROUP BY ITEM_CODE")
        for a, b in cur.fetchall(): assyst[a] = float(b or 0)
        # ★자재+생산+사급 = 합계(jae). 2026-08-20: 화면에서 3종을 나눠 보기 위해 개별값도 함께 반환.
        #   jae_m 자재창고(pu_t_mat_stock_wh) · jae_p 생산창고(pr_t_mat_stock_wh, P0001 제외) · jae_s 사급(PU_T_SAGUB_STOCK)
        jae_m = {}; jae_p = {}; jae_s = {}
        # ★2026-08-25 생산창고 = 이력기준 공용계산(410·키팅·생산입출고현황과 동일 원천).
        #   잔액 테이블은 nx 미러가 늦으면 웹실적만 담긴 반쪽 값이 되어 값이 어긋난다.
        #   여기선 P0001(가공파트)를 뺀 나머지 파트 합계가 필요하므로 파트별 맵을 쓴다.
        for (_m, _p), _v in _psm.items():          # 위에서 만든 맵 재사용(재계산 방지)
            if _p == 'P0001' or not _v:
                continue
            jae_p[_m] = jae_p.get(_m, 0.0) + _v
        cur.execute(f"SELECT MAT_CODE, SUM(STOCK_QTY) FROM {S}.pu_t_mat_stock_wh WHERE cust_code='Z99990' AND stock_qty<>0 GROUP BY MAT_CODE")
        for a, b in cur.fetchall(): jae_m[a] = float(b or 0)
        cur.execute(f"SELECT MAT_CODE, SUM(STOCK_QTY) FROM {S}.PU_T_SAGUB_STOCK WHERE stock_qty<>0 GROUP BY MAT_CODE")
        for a, b in cur.fetchall(): jae_s[a] = float(b or 0)
        # ★2026-08-25 원장 델타 가산은 쓰지 않는다 — 웹은 잔액도 함께 갱신하므로
        #   '잔액 + 원장델타' 는 이중계상이 된다(실측 SUB1: 0 + (-2) = -2, 정답 0).
        #   가공진척은 {S} 잔액(nx=미러+웹실적)을 그대로 쓴다.
        for _k in set(jae_m) | set(jae_p) | set(jae_s):
            jae[_k] = jae_m.get(_k, 0.0) + jae_p.get(_k, 0.0) + jae_s.get(_k, 0.0)

        # ★출고처(2026-08-20) — 레거시 w_pr_input_420_new 실측 규칙(6/6 일치).
        #   ① UPPER 품목의 거래처명(IN_CUST_CODE) = 외주 판매처
        #   ② 없으면 TUIP_GAGONG_PROC_CODE 공정명
        #   ③ 없으면 UPPER 품목의 작업처명(WORK_CODE)
        #   기존엔 wcc(P2 가공) 고정이라 전 행이 같은 값이었음.
        _uppers = list({g["upper"] for g in rows if g["upper"]})
        _tuips  = list({g["tuip"] for g in rows if g.get("tuip")})
        _ucust = {}; _uwork = {}; _tnm = {}
        for i in range(0, len(_uppers), 900):
            ch = _uppers[i:i+900]; ph2 = ",".join("?" * len(ch))
            cur.execute(f"""SELECT m.ITEM_CODE,
                     ISNULL((SELECT CUST_DESC FROM {S}.CM_M_CUST WHERE CUST_CODE=m.in_cust),''),
                     ISNULL((SELECT WORK_DESC FROM {S}.PR_M_WORK WHERE WORK_CODE=m.WORK_CODE),'')
                   FROM {S}.item m WITH(NOLOCK) WHERE m.ITEM_CODE IN ({ph2})""", *ch)
            for a, b, c3 in cur.fetchall():
                _ucust[a] = (b or '').strip(); _uwork[a] = (c3 or '').strip()
        for i in range(0, len(_tuips), 900):
            ch = _tuips[i:i+900]; ph2 = ",".join("?" * len(ch))
            cur.execute(f"""SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'')
                              FROM {S}.PR_M_PROC_GAGONG WITH(NOLOCK) WHERE GAGONG_PROC_CODE IN ({ph2})""", *ch)
            for a, b in cur.fetchall(): _tnm[a] = (b or '').strip()
        def _outsrc(g):
            u = g.get("upper") or ''
            return _ucust.get(u, '') or _tnm.get(g.get("tuip") or '', '') or _uwork.get(u, '')

        # ★치수(지름·두께·길이) = PR_M_ITEM (레거시 dw_pr_input_420_t1: max(d.item_diam) 등, d=자도번 품목)
        dim = {}
        for i in range(0, len(mats), 900):
            ch = mats[i:i+900]; ph2 = ",".join("?" * len(ch))
            cur.execute(f"""SELECT ITEM_CODE, ISNULL(diam,0), ISNULL(thick,0), ISNULL(length,0)
                              FROM {S}.item WITH(NOLOCK) WHERE ITEM_CODE IN ({ph2})""", *ch)
            for a, b, c3, d3 in cur.fetchall(): dim[a] = (b, c3, d3)
        # ★LG OUTPUT시간(2026-08-20) — 레거시 dw_pr_input_420_t1 실측:
        #     LEFT JOIN PR_T_PLAN_ITEM_DTL t
        #       ON a.plan_ymd=t.plan_ymd AND a.work_order=t.work_order
        #      AND a.split_work_order=t.split_work_order AND a.assy_item_code=t.c_item_code
        #     min(isnull(t.org_plan_ymd, a.plan_ymd)) / min(isnull(t.org_output_hm, a.output_hm))
        #   표시 = 'YY/MM/DD  HH:MM' (파워빌더 string(...,'@@/@@/@@') + '  ' + string(...,'@@:@@'))
        #   ※PR_T_PLAN_DTL 이 아니라 PR_T_PLAN_ITEM_DTL 이다(처음에 잘못 잡아 빈값이었음).
        lgo = {}
        try:
            cur.execute(f"""SELECT a.ASSY_ITEM_CODE, a.ITEM_CODE,
                       MIN(ISNULL(t.ORG_PLAN_YMD,  a.PLAN_YMD))  oy,
                       MIN(ISNULL(t.ORG_OUTPUT_HM, a.OUTPUT_HM)) oh
                  FROM {PLAN_T} a WITH(NOLOCK)
                  LEFT JOIN {S}.PR_T_PLAN_ITEM_DTL t WITH(NOLOCK)
                         ON a.PLAN_YMD=t.PLAN_YMD AND a.WORK_ORDER=t.WORK_ORDER
                        AND ISNULL(a.SPLIT_WORK_ORDER,'')=ISNULL(t.SPLIT_WORK_ORDER,'')
                        AND a.ASSY_ITEM_CODE=t.C_ITEM_CODE
                 WHERE a.GC_GUBUN='Q' AND a.WORK_CODE=? AND a.part_plan_ymd<=?
                 GROUP BY a.ASSY_ITEM_CODE, a.ITEM_CODE""", wcc, d6b)
            for aa, ii, oy, oh in cur.fetchall():
                y = str(oy or '').strip(); h = str(oh or '').strip()
                if len(y) >= 6:
                    v = f"{y[0:2]}/{y[2:4]}/{y[4:6]}"
                    if len(h) >= 4: v += f"  {h[0:2]}:{h[2:4]}"
                    lgo[(aa, ii)] = v
        except Exception:
            pass
        cur.execute(f"SELECT MAT_CODE, SUM(plan_qty) FROM {S}.PR_T_INDI_CUTTING WHERE PROD_FLAG='0' GROUP BY MAT_CODE")
        for a, b in cur.fetchall(): ing[a] = float(b or 0)
        # 출하: 레거시 SP는 (wo,swo) 커서행별 sale을 그 행 계획만큼만 인정(min). WO별 sale이 그 WO 계획 초과분은 다른 WO/파트로 넘어가지 않음.
        # → sale기여[(assy,item)] = Σ_wo MIN(wo_sale×use, wo_plan). (assy단위 총합 후 전체계획에 뿌리면 특정 WO의 대량출하가 무관 WO계획까지 채워 과다충당됨: AJR74844301 등)
        cur.execute(f"""SELECT assy, item, SUM(CASE WHEN wo_sale*useq < wo_plan THEN wo_sale*useq ELSE wo_plan END) cap
              FROM (SELECT p.ASSY_ITEM_CODE assy, p.ITEM_CODE item, p.WORK_ORDER wo, ISNULL(p.SPLIT_WORK_ORDER,'') swo,
                           SUM(CAST(p.PART_PLAN_QTY AS float)) wo_plan, MAX(CAST(ISNULL(p.USE_QTY,1) AS float)) useq,
                           ISNULL(MAX(sd.saleqty),0) wo_sale
                      FROM {PLAN_T} p WITH(NOLOCK)
                      LEFT JOIN (SELECT WORK_ORDER wo, ISNULL(SPLIT_WORK_ORDER,'') swo, ITEM_CODE, SUM(SALE_QTY) saleqty
                                 FROM {S}.SA_T_SALE_DTL WITH(NOLOCK) WHERE FINISH_FLAG='0'
                                 GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE) sd
                        ON sd.wo=p.WORK_ORDER AND sd.swo=ISNULL(p.SPLIT_WORK_ORDER,'') AND sd.ITEM_CODE=p.ASSY_ITEM_CODE
                     WHERE p.GC_GUBUN='Q' AND p.WORK_CODE=? AND p.part_plan_ymd<=?
                     GROUP BY p.ASSY_ITEM_CODE, p.ITEM_CODE, p.WORK_ORDER, ISNULL(p.SPLIT_WORK_ORDER,'')) t
              GROUP BY assy, item""", wcc, d6b)
        sale2 = {}
        for a, it, cap in cur.fetchall(): sale2[(a, it)] = float(cap or 0)
        # ★출하는 '제번(LOT) 단위 완결' — 그 제번이 출하되면 계획이 어제15/오늘5 로 쪼개져
        #   있어도 20 전부 끝난 것으로 본다(완제품재고와 달리 수량 소진식이 아님).
        #   → 출하가 잡힌 제번의 '계획 전량'을 출하충당 한도로 쓴다.
        cur.execute(f"""SELECT assy, item, SUM(wo_plan) cap
              FROM (SELECT p.ASSY_ITEM_CODE assy, p.ITEM_CODE item,
                           SUM(CAST(p.PART_PLAN_QTY AS float)) wo_plan,
                           ISNULL(MAX(sd.saleqty),0) wo_sale
                      FROM {PLAN_T} p WITH(NOLOCK)
                      LEFT JOIN (SELECT WORK_ORDER wo, ISNULL(SPLIT_WORK_ORDER,'') swo, ITEM_CODE, SUM(SALE_QTY) saleqty
                                 FROM {S}.SA_T_SALE_DTL WITH(NOLOCK) WHERE FINISH_FLAG='0'
                                 GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE) sd
                        ON sd.wo=p.WORK_ORDER AND sd.swo=ISNULL(p.SPLIT_WORK_ORDER,'') AND sd.ITEM_CODE=p.ASSY_ITEM_CODE
                     WHERE p.GC_GUBUN='Q' AND p.WORK_CODE=? AND p.part_plan_ymd<=?
                     GROUP BY p.ASSY_ITEM_CODE, p.ITEM_CODE, p.WORK_ORDER, ISNULL(p.SPLIT_WORK_ORDER,'')) t
             WHERE wo_sale > 0
             GROUP BY assy, item""", wcc, d6b)
        for a, it, cap in cur.fetchall(): sale2[(a, it)] = float(cap or 0)
        # fix(도번고정): 재귀 BOM 롤업 → 레거시 SP는 (UPPER_ITEM_CODE, MAT_CODE) 키로 매핑(부모재고를 하위에 use_qty로 전개)
        try:
            cur.execute(f"IF OBJECT_ID('tempdb..#tmsg') IS NOT NULL DROP TABLE #tmsg")
            cur.execute(f"""
                ;WITH T (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, sg_stock_qty, proc_stock_qty, fix_pr_stock_qty) AS (
                    SELECT s.mat_code, s.mat_code, s.mat_code, CONVERT(int,ISNULL(SUM(s.st),0)), CONVERT(int,ISNULL(SUM(s.pr),0)),
                           CONVERT(int,ISNULL(SUM(s.sg),0)), CONVERT(int,ISNULL(SUM(s.pc),0)), 0
                      FROM (SELECT mat_code, 0 st, STOCK_QTY pr, 0 sg, 0 pc FROM {S}.pr_t_mat_stock_wh WHERE stock_qty<>0 AND part_code<>'P0001'
                            UNION ALL SELECT mat_code, STOCK_QTY, 0,0,0 FROM {S}.pu_t_mat_stock_wh WHERE cust_code='Z99990' AND stock_qty<>0
                            UNION ALL SELECT mat_code, 0,0,STOCK_QTY,0 FROM {S}.PU_T_SAGUB_STOCK WHERE stock_qty<>0
                            UNION ALL SELECT mat_code, 0,0,0,STOCK_QTY FROM {S}.pr_t_mat_stock_wh WHERE stock_qty<>0 AND part_code='P0001') s
                     GROUP BY s.mat_code HAVING SUM(s.st)<>0 OR SUM(s.pr)<>0 OR SUM(s.sg)<>0 OR SUM(s.pc)<>0
                    UNION ALL
                    SELECT cb.item_code, b.item_code, b.mat_code, 0,0,0,0,
                           CONVERT(int,(CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.sg_stock_qty+cb.stock_qty+cb.proc_stock_qty) END)*b.use_qty)
                      FROM T cb JOIN {S}.pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1')
                SELECT upper_item_code, mat_code, SUM(fix_pr_stock_qty) fx INTO #tmsg FROM T GROUP BY upper_item_code, mat_code OPTION(MAXRECURSION 0)""")
            cur.execute("SELECT upper_item_code, mat_code, fx FROM #tmsg")
            for u, m, v in cur.fetchall(): fixm[(u, m)] = float(v or 0)
        except Exception: pass
        # 배분
        _TAGCLR = {90: '#fac090', 70: '#ffff00', 30: '#ffff00', 20: '#66ff99', 10: '#669900', 0: ''}
        def cellseq(g): return ([g["_cells"]['P']] if 'P' in g["_cells"] else []) + [g["_cells"][y] for y in dates if y in g["_cells"]]
        def alloc(g, pool, tag, key='fin'):
            pool = max(float(pool or 0), 0.0)
            for c2 in cellseq(g):
                if pool <= 0: break
                jan = c2["plan"] - c2["fin"] - (c2["ready"] if key == 'ready' else 0.0)
                if jan <= 0: continue
                take = min(jan, pool); c2[key] += take; pool -= take
                if take >= jan - 1e-9 and (tag > c2["tag"] or c2["tag"] == 0): c2["tag"] = tag
        def shared(keyfn, poolmap, tag, key='fin', sortkey=None):
            sk = sortkey or (lambda x: x["assy"])
            grp = {}
            for g in rows: grp.setdefault(keyfn(g), []).append(g)
            for k, gs in grp.items():
                pool = max(float(poolmap.get(k, 0.0) or 0), 0.0)
                if pool <= 0: continue
                for g in sorted(gs, key=sk):
                    for c2 in cellseq(g):
                        if pool <= 0: break
                        jan = c2["plan"] - c2["fin"]
                        if jan <= 0: continue
                        take = min(jan, pool); c2["fin"] += take; pool -= take
                        if take >= jan - 1e-9 and (tag > c2["tag"] or c2["tag"] == 0): c2["tag"] = tag
        # ★공유풀 소진순서 = 레거시 SP 커서순서(plan_ymd→part_output_hm→output_hm→wo). assy순 아님(같은 원소재를 여러 assy가 나눠쓸 때 이른 계획이 먼저 가져감).
        _cur = lambda x: (x["plan_ymd"], x["phm"], x["ohm"], x["assy"])
        # ★풀 적용순서 = finish_tag 내림차순(=우선순위): 출하90 → ASSY재고70 → 자재30·도번고정30 → 가공창고proc20 → 전표10.
        # 오라클 실측: proc재고가 커도 자재(pr_stock,tag30)를 먼저 씀(ADM72950717/4H00901J: proc907 있어도 자재6로 채움→색 노랑30). 즉 가공창고(20)가 재고풀 중 최하위.
        for g in rows: alloc(g, sale2.get((g["assy"], g["item"]), 0.0), 90)   # 출하90 행별(WO별 계획캡 합산, use 포함済)
        for g in rows: alloc(g, assyst.get(g["assy"], 0.0) * g["use"], 70)    # ASSY재고70 행별(자력)
        shared(lambda g: (g["upper"], g["item"]), fixm, 30, sortkey=_cur)     # 도번고정fix30 (upper,item)별 롤업
        shared(lambda g: g["item"], jae, 30, sortkey=_cur)                    # 자재30 mat공유(커서순) ★proc보다 먼저(tag30>20)
        shared(lambda g: g["item"], proc, 20, sortkey=lambda x: (x["bl"], x["plan_ymd"], x["phm"], x["ohm"], x["assy"]))  # 가공창고20 mat공유(원소재 우선→커서순), 재고풀 중 최하위
        for g in rows: alloc(g, ing.get(g["item"], 0.0), 10, 'ready')         # 전표10 ready
        # 표시필드: 품명(mat item명)·출고처(gpc명)·작업처·생산ST(item_st×plan/3600)
        nm = {}; gpn = {}; ist = {}
        for i in range(0, len(mats), 900):
            ck = mats[i:i + 900]; ph = ",".join("?" * len(ck))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(item_name,'') FROM {S}.item WHERE ITEM_CODE IN ({ph})", *ck)
            for a, b in cur.fetchall(): nm[a] = b
            cur.execute(f"SELECT ITEM_CODE, SUM(CAST(ISNULL(TOT_ST,0) AS float)) FROM {S}.PR_M_ITEM_PROC_GAGONG WHERE ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE", *ck)
            for a, b in cur.fetchall(): ist[a] = float(b or 0)
        gpcs = list({g["gpc"] for g in rows if g["gpc"]})
        if gpcs:
            ph = ",".join("?" * len(gpcs))
            cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM {S}.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *gpcs)
            for a, b in cur.fetchall(): gpn[a] = b
        _wcd = _ITEM_WORK.get(wcc, wcc)
        # 출력 (프론트 shape)
        out = []
        for g in rows:
            pc = g["_cells"].get('P'); days = {}; done = {}; colors = {}
            for y in dates:
                c2 = g["_cells"].get(y)
                if c2 and c2["plan"] > 0:
                    # ★일별/당일이전 완료 셀 = fin + ready(가공전표 PROD_FLAG='0'). 가공관점: 용접공정 이동전표 발행=가공완료(사용자 도메인규칙).
                    #   레거시 SP finish_qty_NN도 전표(tag10)를 완료로 포함 → 셀완료가 실완료(master)보다 클 수 있음. master(완료컬럼)는 fin만(전표 제외) 유지.
                    days[y] = round(c2["plan"], 0); done[y] = round(c2["fin"] + c2["ready"], 0)
                    colors[y] = ('background:' + _TAGCLR[c2["tag"]]) if _TAGCLR.get(c2["tag"]) else ''
            fin = round(sum(c2["fin"] for c2 in g["_cells"].values()), 0)
            plan = round(sum(c2["plan"] for c2 in g["_cells"].values()), 0)
            out.append({"assy": g["assy"], "jado": g["item"], "jnm": nm.get(g["item"], ''),
                        "gpcnm": gpn.get(g["gpc"], g["gpc"]), "wcc": wcc, "wcd": _outsrc(g),
                        "upper": g["upper"], "bl": g["bl"], "line_no": g.get("line_no", ''),
                        "diam": round(float(dim.get(g["item"], (0, 0, 0))[0] or 0), 2),
                        "thick": round(float(dim.get(g["item"], (0, 0, 0))[1] or 0), 2),
                        "length": round(float(dim.get(g["item"], (0, 0, 0))[2] or 0), 0),
                        "lgout": lgo.get((g["assy"], g["item"]), ''),
                        "jae_m": round(jae_m.get(g["item"], 0.0), 0),
                        "jae_p": round(jae_p.get(g["item"], 0.0), 0),
                        "jae_s": round(jae_s.get(g["item"], 0.0), 0),
                        "st": round(ist.get(g["item"], 0.0) * plan / 3600.0, 2),
                        "use": g["use"], "plan_qty": plan, "finish": fin,
                        "sale": round(sale2.get((g["assy"], g["item"]), 0.0), 0), "proc": round(proc.get(g["item"], 0.0), 0),
                        "assyst": round(assyst.get(g["assy"], 0.0), 0), "prs": round(jae.get(g["item"], 0.0), 0),
                        "fixst": round(fixm.get((g["upper"], g["item"]), 0.0), 0), "ing": round(ing.get(g["item"], 0.0), 0),
                        "prior_pl": round(pc["plan"], 0) if pc else 0, "prior_fn": round(pc["fin"] + pc["ready"], 0) if pc else 0,
                        "prior_bg": (('background:' + _TAGCLR[pc["tag"]]) if pc and _TAGCLR.get(pc["tag"]) else ''),
                        "wo": g.get("wo") or '', "days": days, "done": done, "colors": colors})
        # ★재고 충당(2026-08-20) — 레거시 w_pr_input_580 방식 이식.
        #   재고 '컬럼값'은 현재 보유량이라 깎지 않는다(그대로 표시).
        #   대신 재고로 덮이는 계획셀을 앞 일자부터 순서대로 소진시켜 셀에 색을 칠한다.
        #   충당순서(2026-08-20 사용자확정) =
        #     출하 → ASSY재고 → 사급재고 → 생산재고 → 자재재고 → 가공창고 → 가공전표발행
        #   (완제품에 가까운 쪽부터 소진. 580도 assy_stock_qty 부터 채운다)
        #   ※화면 컬럼은 자재·생산·사급을 분리 유지하되, 충당 판단은 세 재고의 합으로 한다
        #     (레거시 420 = '자재+생산+사급재고' 한 컬럼으로 합쳐 충당).
        _ORD = ("sale", "assyst", "jae_s", "jae_p", "jae_m", "proc", "ing")
        # 충당원별 셀색(레거시 420 범례) — 출하=주황, 가공창고=연두, 전표발행=녹색, 그외=노랑
        _CLR = {"sale": '#fac090', "proc": '#99ffcc', "ing": '#66ff99'}
        _COVER = '#ffff00'
        # ★ASSY재고(완제품)는 "Assy 1대분"이라 자도번마다 그 수량이 각각 적용된다.
        #   (레거시 420 실측: ASSY재고 2 → 자도번 5개 행이 모두 2씩 충당)
        # ★출하는 제번(LOT) 단위 완결 — sale2 가 '출하된 제번의 계획 전량'이라
        #   계획이 어제15/오늘5 로 쪼개져 있어도 20 전부 채워진다.
        #   (assy,jado) 로 묶어 그 자도번 계획을 순서대로 덮는다.
        def _pkey(k, r):
            if k in ("assyst", "sale"):
                return ("A", k, r["assy"], r["jado"])
            if k == "fixst":               # 도번고정=(상위도번,자도번) 단위
                return ("F", r["upper"], r["jado"])
            return ("J", r["jado"], k)     # 나머지=자도번 단위
        _pool = {}
        for r in out:
            for k in _ORD:
                _pool.setdefault(_pkey(k, r), float(r.get(k) or 0))
        # ※기존 완료분은 재고에서 차감하지 않는다.
        #   재고(자재15·가공5)는 '지금 남아있는' 수량이고, 완료분은 이미 소비돼
        #   그 잔량에 반영돼 있다. 또 빼면 이중차감이라 뒤 일자가 충당을 못 받음.
        #   → 계획셀의 미충족분(계획−완료)만 재고로 순서대로 덮는다.
        _cvd = set()      # 재고가 배정된 행(완료 컬럼 재계산 대상)
        # 앞 일자부터(당일이전 → dates 순), 같은 일자면 Assy도번 순
        for y in ['P'] + list(dates):
            for r in sorted(out, key=lambda x: x["assy"]):
                if y == 'P':
                    pl, dn = float(r.get("prior_pl") or 0), float(r.get("prior_fn") or 0)
                else:
                    pl, dn = float((r.get("days") or {}).get(y) or 0), float((r.get("done") or {}).get(y) or 0)
                # ★계획 전체를 재고로 덮는다(완료분 포함).
                #   예) 자재15 → 당일이전 10+5 를 채우고, 남은 가공창고5 가 20(목) 을 채움.
                #   완료가 이미 있어도 그 수량만큼 재고가 배정된 것으로 본다(레거시 420 동일).
                need = max(pl, 0.0)
                if need <= 0:
                    continue
                took = {}
                for k in _ORD:
                    if need <= 0:
                        break
                    pk = _pkey(k, r)
                    take = min(_pool[pk], need)
                    if take <= 0:
                        continue
                    _pool[pk] = round(_pool[pk] - take, 4)
                    need = round(need - take, 4)
                    took[k] = took.get(k, 0.0) + take
                if not took:
                    continue
                # 여러 재고로 나뉘면 가장 많이 충당한 원천의 색(동률이면 _ORD 우선순위)
                kmax = max(took, key=lambda k: (took[k], -_ORD.index(k)))
                bg = 'background:' + _CLR.get(kmax, _COVER)
                cov = round(sum(took.values()), 0)      # 이 셀에 배정된 재고수량
                # ★셀 완료 = "재고로 배정된 수량"(기존완료와 합치지 않는다).
                #   예) 자재15 → 당일이전 10/10·5/5, 가공창고5 → 20(목) 5/15.
                #   완료 컬럼(finish)은 아래에서 셀 합으로 재계산.
                # ★색은 '계획을 전부 충족'했을 때만 칠한다(부분충당 5/15 = 무색).
                full = cov >= round(pl, 0) - 1e-6
                if y == 'P':
                    r["prior_fn"] = cov
                    if full:
                        if not r.get("prior_bg"):
                            r["prior_bg"] = bg
                    else:
                        r["prior_bg"] = ''       # 부분충당 = 무색
                else:
                    r.setdefault("done", {})[y] = cov
                    if full:
                        if not (r.get("colors") or {}).get(y):
                            r.setdefault("colors", {})[y] = bg
                    else:
                        r.setdefault("colors", {})[y] = ''
                _cvd.add(id(r))
        # 완료 컬럼 = 재고배정 셀들의 합(당일이전 + 각 일자). 배정된 행만 갱신.
        for r in out:
            if id(r) in _cvd:
                r["finish"] = round(float(r.get("prior_fn") or 0)
                                    + sum(float(v or 0) for v in (r.get("done") or {}).values()), 0)
        uf = unfin.strip()
        if uf == "미생산": out = [r for r in out if r["finish"] < r["plan_qty"]]
        out = out[:int(limit)]
                # ★ASSY생산파트 드롭다운(2026-08-20) — 레거시 '전체/01라인(용접)/02라인/…' 과 동일 목록.
        #   결과에 실제로 쓰인 gpc 만 코드순으로.
        _pc = sorted({r["wcd"] for r in out if r.get("wcd")})
        parts = [{"code": c, "nm": c} for c in _pc]
        return {"dates": dates, "rows": out, "cnt": len(out),
                "plan_sum": sum(r["plan_qty"] for r in out), "done_sum": sum(r["finish"] for r in out),
                "note": ("nx재현·신규DB계획" if _psrc == "new" else "nx재현"),
                "plansrc": _psrc, "plan_src": PLAN_T,   # ★어느 계획을 읽었는지(대조용)
                "parts": parts}
    finally:
        cn.close()

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
            cur.execute(f"SELECT ITEM_CODE, ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({ph})", *ck)
            for a, b in cur.fetchall(): nm[a] = b
        if gpcs:
            ph = ",".join("?" * len(gpcs))
            cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE IN ({ph})", *gpcs)
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
    cn = _conn(); cur = cn.cursor()
    try:
        d6f = _d6(from_ymd) if from_ymd else '260729'
        d6t = _d6(to_ymd) if to_ymd else None
        if not d6t:
            _y = _dt.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6])) + _dt.timedelta(days=30)
            d6t = _y.strftime('%y%m%d')
        wcp = (wc.strip() or 'P2')
        # ★계획소스는 라이브 직독(PARTNER_ERP.dbo) — 레거시 SP가 라이브를 읽고, nx 계획미러는 이 조인분이 stale(6222 vs 9521행)이라 diff0 위해 라이브 필수. (nx 계획테이블 동기화는 컷오버 과제)
        S = "PARTNER_ERP.dbo"
        # 날짜 캘린더: dates[0]=기준일(=col1 당일이전누적 plan_ymd<=기준일), 이후 plan_ymd=기준일+1..
        da = _dt.date(2000+int(d6f[:2]), int(d6f[2:4]), int(d6f[4:6]))
        db = _dt.date(2000+int(d6t[:2]), int(d6t[2:4]), int(d6t[4:6]))
        dates = []; cu = da
        while cu <= db and len(dates) < 31: dates.append(cu.strftime('%y%m%d')); cu += _dt.timedelta(days=1)
        dateidx = {d: i for i, d in enumerate(dates)}
        # ★레거시 SP_PR_4주간_가공계획현황_250703 완전재현(EXEC 거부→인라인). 검증: 351/351도번·일자 diff0.
        #  TEMP_PLAN 5브랜치(PLAN_YMD=①②part_plan_ymd/③④⑤plan_ymd) → 값=ceiling(plan×use×rate/100), 일자=PLAN_YMD. temp테이블 대신 Python 머티리얼라이즈.
        import math as _math
        cur.execute(f"""SELECT c_item_code, work_order, split_work_order, ISNULL(line_no,'') line_no, plan_ymd, ISNULL(use_qty,1) use_qty, plan_qty, ISNULL(prod_rate,100) prod_rate FROM (
          SELECT T.PART_PLAN_YMD plan_ymd, A.C_ITEM_CODE c_item_code, A.WORK_ORDER work_order, A.SPLIT_WORK_ORDER split_work_order, A.LINE_NO line_no, A.USE_QTY use_qty, A.PLAN_QTY plan_qty, C.PROD_RATE prod_rate
            FROM {S}.PR_T_PLAN_PART_DTL_FOR_CUST t JOIN {S}.pr_t_plan_item_dtl a ON a.plan_ymd=t.plan_ymd AND a.work_order=t.work_order AND a.split_work_order=t.split_work_order AND a.c_item_code=t.item_code JOIN {S}.item c ON a.c_item_code=c.item_code WHERE t.proc_seq=1 AND t.gc_gubun='P'
          UNION ALL SELECT T.PART_PLAN_YMD, A.ITEM_CODE, A.WORK_ORDER, A.WORK_ORDER, A.LINE_NO, 1, A.PLAN_QTY, C.PROD_RATE
            FROM {S}.PR_T_PLAN_PART_DTL_FOR_CUST t JOIN {S}.PR_T_PLAN_INPUT a ON a.plan_ymd=t.plan_ymd AND a.work_order=t.work_order AND a.work_order=t.split_work_order AND a.item_code=t.item_code JOIN {S}.item c ON a.item_code=c.item_code WHERE t.proc_seq=1 AND t.gc_gubun='P'
          UNION ALL SELECT a.PLAN_YMD, A.C_ITEM_CODE, A.WORK_ORDER, A.SPLIT_WORK_ORDER, A.LINE_NO, A.USE_QTY, A.PLAN_QTY, C.PROD_RATE
            FROM {S}.PR_T_PLAN_ITEM_DTL a JOIN {S}.item c ON a.c_item_code=c.item_code WHERE a.PLAN_YMD>=? AND c.in_cust>''
          UNION ALL SELECT a.PLAN_YMD, A.ITEM_CODE, A.WORK_ORDER, A.WORK_ORDER, A.LINE_NO, 1, A.PLAN_QTY, C.PROD_RATE
            FROM {S}.PR_T_PLAN_INPUT a JOIN {S}.item c ON a.item_code=c.item_code WHERE a.PLAN_YMD>=? AND c.in_cust>''
          UNION ALL SELECT a.PLAN_YMD, A.ITEM_CODE, A.WORK_ORDER, A.WORK_ORDER, A.LINE_NO, 1, A.PLAN_QTY, C.PROD_RATE
            FROM {S}.PR_T_PLAN_INPUT a JOIN {S}.item c ON a.item_code=c.item_code WHERE a.PLAN_YMD>=? AND C.WORK_CODE=?
        ) x""", d6f, d6f, d6f, wcp)
        tprows = cur.fetchall()
        dobset = sorted({str(r[0]).strip() for r in tprows if r[0]})
        # P2 필터 = CTE_BOM(재귀 BOM전개, VALUES seed) 4조건: work_code=wcp·in_cust_code=''·경로첫등장(charindex)·mat_flag='1'(pr_m_mat 아님, ★라이브서 조회=nx엔 미러안됨). 도번set + 자도번LIST(mat).
        from collections import defaultdict as _dd
        p2set = set(); _jm = _dd(list)
        for i in range(0, len(dobset), 300):
            ch = dobset[i:i+300]; vals = ",".join("(?)" for _ in ch)
            cur.execute(f"""
              WITH SEED(item_code) AS (SELECT item_code FROM (VALUES {vals}) v(item_code)),
              CTE_BOM AS (
                SELECT CONVERT(int,1) level_no, CONVERT(varchar(50),s.item_code) item_code, CONVERT(varchar(50),s.item_code) mat_code,
                   CONVERT(varchar(20),c.work_code) work_code, CONVERT(varchar(20),c.in_cust) in_cust_code,
                   CONVERT(varchar(20),CASE WHEN c.work_code>'' THEN c.work_code ELSE c.in_cust END) mwc,
                   CONVERT(varchar(500),'||'+CASE WHEN c.work_code>'' THEN c.work_code ELSE c.in_cust END+'|') cum,
                   CONVERT(decimal(18,5),1) cum_use
                FROM SEED s JOIN {S}.item c ON c.item_code=s.item_code
                UNION ALL
                SELECT cb.level_no+1, cb.item_code, CONVERT(varchar(50),b.mat_code),
                   CONVERT(varchar(20),m.work_code), CONVERT(varchar(20),m.in_cust),
                   CONVERT(varchar(20),CASE WHEN m.work_code>'' THEN m.work_code ELSE m.in_cust END),
                   CONVERT(varchar(500),cb.cum+'|'+CASE WHEN m.work_code>'' THEN m.work_code ELSE m.in_cust END+'|'),
                   CONVERT(decimal(18,5),cb.cum_use*b.use_qty)
                FROM CTE_BOM cb JOIN {S}.pr_m_item_bom b ON cb.mat_code=b.item_code JOIN {S}.item m ON b.mat_code=m.item_code
                WHERE ISNULL(b.EXCEPT_FLAG,'0')='0' AND cb.level_no<10)
              SELECT item_code, mat_code, SUM(CONVERT(float,cum_use)) q FROM CTE_BOM cte
              WHERE work_code=? AND in_cust_code='' AND charindex('||'+mwc+'||',cum)=0
                AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP_TEST3.nx.pr_m_mat mm WHERE mm.mat_code=cte.mat_code)
              GROUP BY item_code, mat_code OPTION(MAXRECURSION 0)""", *ch, wcp)
            for it, mc, q in cur.fetchall():
                it = str(it).strip(); p2set.add(it); _jm[it].append("%s{%d}" % (str(mc).strip(), int(q or 0)))
        jadomap = {k: ",".join(v) for k, v in _jm.items()}
        # 도번(c_item_code) 그룹: 값=ceil(plan×use×rate/100) 행별합, 일자=PLAN_YMD 버킷(col0=<=기준일 누적)
        keyed = {}
        for cic, _wo, _swo, _ln, _py, _use, _pq, _rate in tprows:
            doban = str(cic or '').strip()
            if not doban or doban not in p2set: continue
            _py = str(_py or '').strip()
            v = float(_math.ceil(float(_pq or 0) * float(_use or 1) * float(_rate or 100) / 100.0))
            g = keyed.get(doban)
            if not g:
                g = {"assy": doban, "nm": "", "awcnm": _ITEM_WORK.get(wcp, wcp), "mwcnm": "",
                     "jado": jadomap.get(doban, ''), "line": str(_ln or '').strip(), "lot": 0.0, "matq": 0.0,
                     "days": {}, "done": {}, "colors": {}, "_wos": set()}
                keyed[doban] = g
            g["matq"] += v
            if str(_wo or '').strip(): g["_wos"].add((str(_wo).strip(), str(_swo or '').strip()))
            col = 0 if _py <= d6f else dateidx.get(_py)
            if col is not None and col < len(dates):
                ymd = dates[col]; g["days"][ymd] = g["days"].get(ymd, 0.0) + v
        for g in keyed.values(): g["lot"] = g["matq"]   # LOT수량 근사(레거시 r1=직전일 plan_dtl_daily, 추후 정밀화)
        rows = list(keyed.values())
        if item.strip(): rows = [g for g in rows if item.strip() in g["assy"]]
        if part.strip(): rows = [g for g in rows if part.strip() in g["jado"]]
        rows.sort(key=lambda x: x["assy"])
        capped = len(rows) > int(limit); rows = rows[:int(limit)]
        # 품명 채우기(도번=PR_M_ITEM)
        codes = [g["assy"] for g in rows]; nm = {}
        for i in range(0, len(codes), 900):
            ch = codes[i:i+900]; qm = ",".join("?" * len(ch))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(item_name,'') FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE IN ({qm})", *ch)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b
        # 자도번LIST(jadomap)은 위 P2필터 CTE_BOM에서 이미 산출됨(레거시 f_find_cust_mat_list2 = mat_work_code(P2)·in_cust''·mat_flag1 자재).
        # ★완료/색 = 준비실적처리(키팅, kitting_grid)와 동일 워터폴 이식: 출하(주황)→ASSY재고(노랑)→도번고정(노랑)→중간재고(노랑)→준비재고(녹) 순 계획일 충당.
        # 소스: 라이브 직독(SA_T_ITEM_STOCK·PU_T_READY_STOCK·SA_T_SALE_DTL + 중간재고롤업 kitting캐시). 도번(=ITEM_CODE) 단위 합산.
        assystk = {}; rstock = {}; saled = {}; midstk = {}; fixstk = {}
        try:
            cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP.dbo.SA_T_ITEM_STOCK GROUP BY ITEM_CODE")
            for rr in cur.fetchall(): assystk[str(rr[0]).strip()] = float(rr[1] or 0)
        except Exception: pass
        try:
            cur.execute("SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP.dbo.PU_T_READY_STOCK WHERE CUST_CODE='Z99990' GROUP BY ITEM_CODE")
            for rr in cur.fetchall(): rstock[str(rr[0]).strip()] = float(rr[1] or 0)
        except Exception: pass
        try:  # 출하는 ★계획 WO로 제한(키팅과 동일, 무관 WO 출하 과다합산 방지). 키=(wo,swo,item)
            _pwos = list({wo for g in rows for (wo, sw) in g["_wos"]})
            for i in range(0, len(_pwos), 900):
                ck = _pwos[i:i+900]; ph = ",".join("?" * len(ck))
                cur.execute(f"SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP.dbo.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND WORK_ORDER IN ({ph}) GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE", *ck)
                for rr in cur.fetchall(): saled[(str(rr[0]).strip(), str(rr[1] or '').strip(), str(rr[2]).strip())] = float(rr[3] or 0)
        except Exception: pass
        try:  # 중간공정 자재/생산재고 롤업 = kitting_grid 캐시 재사용, 없으면 자체계산(전역·필터무관, 색tag70용)
            _rc = getattr(kitting_grid, "_rollup_cache", None)
            if not (_rc and _rc.get("mid")):
                cur.execute("IF OBJECT_ID('tempdb..#tms4') IS NOT NULL DROP TABLE #tms4")
                cur.execute("""
                    ;WITH T_SUB_CTE (item_code, upper_item_code, mat_code, stock_qty, pr_stock_qty, fix_pr_stock_qty) AS (
                        SELECT s.mat_code, s.mat_code, s.mat_code, CONVERT(int, ISNULL(SUM(s.stock_qty),0)), CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)), 0
                          FROM ( SELECT mat_code, 0 stock_qty, STOCK_QTY pr_stock_qty FROM PARTNER_ERP.dbo.pr_t_mat_stock_wh WITH(NOLOCK)
                                 UNION ALL SELECT a.mat_code,0,a.STOCK_QTY FROM PARTNER_ERP.dbo.PU_T_SAGUB_STOCK a WITH(NOLOCK) JOIN PARTNER_ERP_TEST3.nx.item m WITH(NOLOCK) ON a.MAT_CODE=m.ITEM_CODE WHERE m.SAGUB_STOCK_FLAG='1'
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP.dbo.pu_t_mat_stock_wh WITH(NOLOCK) WHERE cust_code='Z99990' AND gagong_proc_code NOT IN ('SA1','SA2','SB1','SB2')
                                 UNION ALL SELECT mat_code, stock_qty, 0 FROM PARTNER_ERP.dbo.PU_T_STACKER_STOCK WITH(NOLOCK) ) s
                         GROUP BY s.mat_code HAVING SUM(s.stock_qty)<>0 OR SUM(s.pr_stock_qty)<>0
                        UNION ALL
                        SELECT cb.item_code, b.item_code, b.mat_code, 0, 0, CONVERT(int, (CASE WHEN cb.fix_pr_stock_qty<>0 THEN cb.fix_pr_stock_qty ELSE (cb.pr_stock_qty+cb.stock_qty) END) * b.use_qty)
                          FROM T_SUB_CTE cb JOIN PARTNER_ERP_TEST3.nx.pr_m_item_bom b WITH(NOLOCK) ON cb.mat_code=b.item_code WHERE ISNULL(b.except_flag,'0')<>'1'
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
                FROM PARTNER_ERP.dbo.PR_T_PROD_DTL_GAGONG p
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=p.GAGONG_PROC_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK_SINGLE ws ON ws.S_WORK_CODE=p.S_WORK_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.QA_M_MACHINE mm ON mm.MACH_CODE=p.MACH_CODE
                LEFT JOIN PARTNER_ERP.dbo.PR_T_INDI_CUTTING_PROC_GAGONG ic2 ON ic2.BOX_NO=p.BOX_NO
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
            w.append("(ma.in_cust LIKE ? OR mac.CUST_DESC LIKE ? OR maw.WORK_DESC LIKE ?)"); p += [f"%{wc.strip()}%"] * 3
        cur.execute(f"""SELECT TOP {int(limit)} ic.BOX_NO,
              ISNULL(ic.ITEM_CODE,'') doban, ISNULL(ic.MAT_CODE,'') jado,
              ISNULL(ma.in_cust,'') wcen, COALESCE(NULLIF(mac.CUST_DESC,''), maw.WORK_DESC, '') wcennm,
              ISNULL(CONVERT(varchar(20), ic.ITEM_DIAM), '') diam, ISNULL(CONVERT(varchar(20), ic.ITEM_THICK), '') thick,
              '' inspdt, ISNULL(ic.CUT_FLAG,'') cutflag, ISNULL(ic.CUT_USER_ID,'') cutuser,
              ISNULL(CONVERT(varchar(19), ic.CUT_DATETIME, 120), '') cutdt,
              ISNULL(ic.ASSY_ITEM_CODE,'') assy,
              COALESCE(NULLIF(aac.CUST_DESC,''), aaw.WORK_DESC, '') assywc,
              COALESCE(NULLIF(iac.CUST_DESC,''), iaw.WORK_DESC, '') dobanwc,
              COALESCE(wh.GAGONG_PROC_DESC, ic.WH_GAGONG_PROC_CODE, '') inwh,
              CONVERT(varchar(19), ic.PRINT_DATETIME, 120) prt, ISNULL(pn.proc_n,0) proc_n,
              ISNULL(ic.PLAN_QTY,0) plan_qty, ISNULL(ic.PROD_QTY,0) prod_qty,
              ISNULL(ic.PROD_FLAG,'0') prod_flag, ISNULL(ic.DEL_FLAG,'0') del_flag,
              ISNULL(ic.PRINT_USER_ID,'') prtuser
            FROM PARTNER_ERP_TEST3.nx.PR_T_INDI_CUTTING ic
            LEFT JOIN PARTNER_ERP_TEST3.nx.item ma ON ma.ITEM_CODE=ic.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST mac ON mac.CUST_CODE=ma.in_cust
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK maw ON maw.WORK_CODE=ma.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item ia ON ia.ITEM_CODE=ic.ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST iac ON iac.CUST_CODE=ia.in_cust
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK iaw ON iaw.WORK_CODE=ia.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item aa ON aa.ITEM_CODE=ic.ASSY_ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST aac ON aac.CUST_CODE=aa.in_cust
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK aaw ON aaw.WORK_CODE=aa.WORK_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG wh ON wh.GAGONG_PROC_CODE=ic.WH_GAGONG_PROC_CODE
            LEFT JOIN (SELECT BOX_NO, COUNT(*) proc_n FROM PARTNER_ERP.dbo.PR_T_INDI_CUTTING_PROC_GAGONG GROUP BY BOX_NO) pn ON pn.BOX_NO=ic.BOX_NO
            WHERE {' AND '.join(w)}
            ORDER BY ic.BOX_NO DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


# --- 컷팅간판 인쇄용 헬퍼 ---
def _sheet_procs(cur, jado):
    """공정순서: 공정명=PR_M_WORK_SINGLE.WORK_DESC(S_WORK_CODE), SPEC=STD_SIZE"""
    cur.execute("""SELECT TOP 10 ISNULL(w.WORK_DESC, CONVERT(varchar(20), d.S_WORK_CODE)),
                          ISNULL(d.STD_SIZE,'')
                     FROM nx.PR_M_ITEM_PROC_GAGONG d
                     LEFT JOIN nx.PR_M_WORK_SINGLE w ON w.S_WORK_CODE=d.S_WORK_CODE
                    WHERE d.ITEM_CODE=? ORDER BY d.PROC_SEQ""", jado)
    return [{"nm": (x[0] or '').strip(), "spec": (x[1] or '').strip()} for x in cur.fetchall()]

def _sheet_wh(cur, jado):
    """창고 = 첫 공정의 가공공정명(예 11라인(가공)/01라인(용접)), 라인 = GAGONG_GROUP_CODE"""
    cur.execute("""SELECT TOP 1 ISNULL(g.GAGONG_PROC_DESC, d.GAGONG_PROC_CODE),
                          ISNULL(CONVERT(varchar(20), w.GAGONG_GROUP_CODE),'')
                     FROM nx.PR_M_ITEM_PROC_GAGONG d
                     LEFT JOIN nx.PR_M_PROC_GAGONG g ON g.GAGONG_PROC_CODE=d.GAGONG_PROC_CODE
                     LEFT JOIN nx.PR_M_WORK_SINGLE w ON w.S_WORK_CODE=d.S_WORK_CODE
                    WHERE d.ITEM_CODE=? ORDER BY d.PROC_SEQ""", jado)
    r = cur.fetchone()
    return ((r[0] or '') if r else '', (r[1] or '') if r else '')

def _sheet_cat(cur, jado):
    """좌상단 구분(SVC/CA 등) = 품목 대분류코드"""
    try:
        cur.execute("SELECT TOP 1 ISNULL(lgroup,'') FROM nx.item WHERE ITEM_CODE=?", jado)
        r = cur.fetchone()
        return (r[0] or '').strip() if r else ''
    except Exception:
        return ''

def _sheet_draw(cur, jado):
    """도면 이미지(PR_M_ITEM_BLOB, FILE_TYPE='K') → data URI"""
    try:
        cur.execute("""SELECT TOP 1 MODULE_BLOB, ISNULL(FILE_EXT,'jpg')
                         FROM nx.PR_M_ITEM_BLOB
                        WHERE ITEM_CODE=? AND FILE_TYPE='K' AND MODULE_BLOB IS NOT NULL
                        ORDER BY MODULE_SEQ""", jado)
        r = cur.fetchone()
        if not r or not r[0]:
            return ''
        ext = (r[1] or 'jpg').lower().lstrip('.')
        mime = 'image/png' if ext == 'png' else 'image/jpeg'
        return "data:%s;base64,%s" % (mime, base64.b64encode(bytes(r[0])).decode())
    except Exception:
        return ''

# ===== 전표발행(컷팅간판 출력) — 레거시 w_pr_input_017 =====
# 채번: SELECT MAX(BOX_NO) → 더미 UPDATE로 테이블 락 → 행마다 +1 (레거시 동일)
# 저장: PR_T_INDI_CUTTING (PLAN_QTY/규격/PRINT_*). ★쓰기는 nx 만(§1).
@router.post("/api/gagong/sheet/issue")
def gagong_sheet_issue(payload: dict = Body(...)):
    rows = payload.get("rows") or []
    user = str(payload.get("user") or "웹")[:20]
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    items = []
    for r in rows:
        q = int(float(r.get("qty") or 0))
        jado = str(r.get("jado") or "").strip()
        if q > 0 and jado:
            items.append({"assy": str(r.get("assy") or "").strip(),
                          "upper": str(r.get("upper") or "").strip(),
                          "jado": jado, "qty": q})
    if not items:
        return {"ok": False, "msg": "발행할 행이 없습니다."}

    cn = _nx_tx(); cur = cn.cursor()
    try:
        # 테이블 락(레거시 방식) 후 채번
        cur.execute("SELECT ISNULL(MAX(BOX_NO),0) FROM nx.PR_T_INDI_CUTTING WITH(UPDLOCK,HOLDLOCK)")
        box = int(cur.fetchone()[0] or 0)
        sheets = []
        for it in items:
            box += 1
            cur.execute("""SELECT ISNULL(diam,0), ISNULL(thick,0), ISNULL(length,0),
                                  ISNULL(ITEM_WEIGHT,0), ISNULL(item_name,'')
                             FROM nx.item WHERE ITEM_CODE=?""", it["jado"])
            m = cur.fetchone() or (0, 0, 0, 0, '')
            cur.execute("""INSERT INTO nx.PR_T_INDI_CUTTING
                           (BOX_NO,LINE_NO,ITEM_DIAM,ITEM_THICK,ITEM_LENGTH,
                            ASSY_ITEM_CODE,ITEM_CODE,MAT_CODE,PLAN_YMD,PLAN_QTY,
                            PRINT_USER_ID,PRINT_DATETIME,PRINT_WINDOW_NAME,
                            CUT_QTY,CUT_FLAG,CUT_OUT_QTY,PROD_QTY,PROD_FLAG,DEL_FLAG,
                            WH_GAGONG_PROC_CODE,IN_GAGONG_PROC_CODE)
                           VALUES(?,'',?,?,?,?,?,?,?,?,?,getdate(),?,0,'0',0,0,'0','0','IS0001','P0001')""",
                        box, m[0], m[1], m[2],
                        it["assy"], (it["upper"] or it["assy"]), it["jado"], ymd, it["qty"],
                        user, 'w_pr_input_017')
            # 공정순서(간판 인쇄용): 공정명=S_WORK_CODE(작업명), SPEC=STD_SIZE
            procs = _sheet_procs(cur, it["jado"])
            whnm, lineno = _sheet_wh(cur, it["jado"])
            sheets.append({"box_no": box, "barcode": "CT%08d" % box,
                           "assy": it["assy"], "upper": it["upper"], "mat": it["jado"],
                           "matnm": m[4], "qty": it["qty"], "wh": "P0001",
                           "diam": float(m[0] or 0), "thick": float(m[1] or 0),
                           "length": float(m[2] or 0),
                           "weight": round(float(m[3] or 0) * it["qty"], 3),
                           "whnm": whnm, "lineno": lineno,
                           "ymd": ymd,          # ★2026-08-24 현장 생산일자(=PR_T_INDI_CUTTING.PLAN_YMD) 전표 표시용
                           "cat": _sheet_cat(cur, it["jado"]),
                           "draw": _sheet_draw(cur, it["jado"]),
                           "procs": procs})
        cn.commit()
        return {"ok": True, "cnt": len(sheets), "sheets": sheets,
                "msg": "전표발행 완료 %d건 (바코드 %s~%s)" % (
                    len(sheets), sheets[0]["barcode"], sheets[-1]["barcode"])}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()


# ===== 컷팅간판 수기입력 지원: 자도번 → 규격·공정순서·상위도번 자동조회 =====
@router.get("/api/gagong/sheet/lookup")
def gagong_sheet_lookup(jado: str = Query("")):
    j = (jado or "").strip()
    if not j:
        return {"ok": False}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT ISNULL(diam,0), ISNULL(thick,0), ISNULL(length,0),
                              ISNULL(ITEM_WEIGHT,0), ISNULL(item_name,''), ISNULL(WORK_CODE,''),
                              ISNULL(in_cust,'')
                         FROM nx.item WHERE ITEM_CODE=?""", j)
        m = cur.fetchone()
        if not m:
            return {"ok": False, "msg": "자도번 %s 없음" % j}
        # 상위도번(이 자도번을 쓰는 BOM 부모) 1건
        cur.execute("""SELECT TOP 1 b.ITEM_CODE FROM nx.PR_M_ITEM_BOM b
                        WHERE b.MAT_CODE=? AND ISNULL(b.EXCEPT_FLAG,'0')<>'1'""", j)
        up = cur.fetchone()
        upper = up[0] if up else ''
        # 작업처명
        cur.execute("""SELECT TOP 1 ISNULL(w.WORK_DESC,'') FROM nx.PR_M_WORK w WHERE w.WORK_CODE=?""", m[5])
        w = cur.fetchone()
        wcd = (w[0] if w and w[0] else '')
        if not wcd and m[6]:
            cur.execute("SELECT TOP 1 ISNULL(CUST_DESC,'') FROM nx.CM_M_CUST WHERE CUST_CODE=?", m[6])
            cc = cur.fetchone()
            wcd = cc[0] if cc else ''
        procs = _sheet_procs(cur, j)
        return {"ok": True, "jado": j, "matnm": m[4], "upper": upper, "wcd": wcd,
                "diam": float(m[0] or 0), "thick": float(m[1] or 0), "length": float(m[2] or 0),
                "weight": float(m[3] or 0),
                "procs": procs, "procstr": ",".join(x["nm"] for x in procs)}
    finally:
        cn.close()


# ===== 가공전표 삭제(발행취소) — 레거시 w_pr_processing_010 ue_deleterow_check =====
# 규칙(레거시 동일): 실적이 잡혀 있으면 삭제 불가.
#   PROD_QTY>0  → "이미 검사완료수량이 등록되어 삭제할 수 없습니다."
#   PROD_FLAG=1 → "이미 검사완료처리가 되어 삭제할 수 없습니다."
#   통과시 PR_T_PROD_DTL_GAGONG 삭제 → PR_T_INDI_CUTTING 삭제. ★nx 만.
@router.post("/api/gagong/sheet/delete")
def gagong_sheet_delete(payload: dict = Body(...)):
    boxes = payload.get("boxes") or []
    try:
        boxes = [int(b) for b in boxes if str(b).strip()]
    except Exception:
        return {"ok": False, "msg": "바코드번호 오류"}
    if not boxes:
        return {"ok": False, "msg": "삭제할 전표를 선택하세요."}
    cn = _nx_tx(); cur = cn.cursor()
    try:
        blocked, done = [], []
        for box in boxes:
            cur.execute("""SELECT ISNULL(PROD_QTY,0), ISNULL(PROD_FLAG,'0'), ISNULL(MAT_CODE,'')
                             FROM nx.PR_T_INDI_CUTTING WHERE BOX_NO=?""", box)
            r = cur.fetchone()
            if not r:
                blocked.append({"box": box, "why": "전표 없음"}); continue
            if float(r[0] or 0) > 0:
                blocked.append({"box": box, "why": "실적수량 %g 등록됨" % float(r[0])}); continue
            if str(r[1]) == '1':
                blocked.append({"box": box, "why": "실적처리 완료됨"}); continue
            cur.execute("SELECT COUNT(*) FROM nx.PU_T_CUT_DTL WHERE BOX_NO=?", box)
            if int(cur.fetchone()[0] or 0) > 0:
                blocked.append({"box": box, "why": "실적이력 있음"}); continue
            try:
                cur.execute("DELETE FROM nx.PR_T_PROD_DTL_GAGONG WHERE BOX_NO=?", box)
            except Exception:
                pass
            cur.execute("DELETE FROM nx.PR_T_INDI_CUTTING WHERE BOX_NO=?", box)
            done.append(box)
        cn.commit()
        msg = "삭제 %d건" % len(done)
        if blocked:
            msg += " · 불가 %d건(%s)" % (len(blocked),
                   ", ".join("%s:%s" % (b["box"], b["why"]) for b in blocked[:5]))
        return {"ok": True, "deleted": done, "blocked": blocked, "msg": msg}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()
