# -*- coding: utf-8 -*-
"""soyo 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= ★자재소요 정본 엔진 (레거시 STEP5→6→7 충실이식, 수량100%·총량1.00000x 검증) =================
# STEP5 nx.plan_item_dtl(LOT합산·모델→ASSY 유효일자, EXCEPT미적용) → STEP6 nx.plan_part_dtl(10레벨BOM+가공공정 공정전이)
#  → STEP7 nx.plan_part_mat(사급중단 NOT EXISTS PART_DTL + 최하위집계 + charindex중복 + 용접봉sgroup910 제외=공정처리).
# 검증: 설계2건(용접봉·체결SUB이중계상)제외시 웹 vs 레거시 PR_T_PLAN_PART_MAT 수량완전일치100%. [[newerp-plan-soyo-verify]]
_P = "PARTNER_ERP.dbo."

@router.post("/api/plan/compose_mat")
def plan_compose_mat(payload: dict = Body(...)):
    nx = _nx(); cur = nx.cursor()
    try:
        # ── STEP M 신규모델생성(주문⋈계획 제번조인, use=CEILING(order/lot), 3중제외) ──
        cur.execute("DELETE FROM nx.model_bom WHERE REMARKS='신규모델자동'")
        cur.execute("""INSERT INTO nx.model_bom(MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO,REMARKS,INS_DT)
            SELECT p.model_no, r.item_code,
               MAX(CASE WHEN r.order_qty<p.lot THEN 1 ELSE CEILING(CAST(r.order_qty AS float)/NULLIF(p.lot,0)) END),
               MIN(p.plan_ymd),'999999','신규모델자동',getdate()
            FROM (SELECT RTRIM(MODEL_NO) model_no,WORK_ORDER,MAX(TOTAL_QTY) lot,MIN(PLAN_YMD) plan_ymd
                  FROM nx.plan_dtl WHERE ISNULL(MODEL_NO,'')>'' GROUP BY RTRIM(MODEL_NO),WORK_ORDER) p
            JOIN (SELECT RTRIM(ITEM_CODE) item_code,WORK_ORDER,SUM(ORDER_QTY) order_qty
                  FROM nx.recv_dtl WHERE ISNULL(ITEM_CODE,'')>'' GROUP BY RTRIM(ITEM_CODE),WORK_ORDER) r ON p.WORK_ORDER=r.WORK_ORDER
            WHERE NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_M_MODEL_BOM b WHERE b.MODEL_NO=p.model_no AND b.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM nx.model_bom m WHERE m.MODEL_NO=p.model_no AND m.C_ITEM_CODE=r.item_code)
              AND NOT EXISTS(SELECT 1 FROM PARTNER_ERP.dbo.PR_M_MODEL_BOM_EXCEPT e WHERE e.MODEL_NO=p.model_no AND e.C_ITEM_CODE=r.item_code)
            GROUP BY p.model_no,r.item_code""")
        # ── STEP5 nx.plan_item_dtl: (제번,모델) LOT합산 → 모델→ASSY 전개(유효일자, ★EXCEPT미적용) ──
        from collections import defaultdict as _dd
        mbom = _dd(list)
        cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,MAKE_YMD,TO_APPLY_YMD FROM PARTNER_ERP.dbo.PR_M_MODEL_BOM")
        for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        cur.execute("SELECT MODEL_NO,C_ITEM_CODE,USE_QTY,APPLY_FROM,APPLY_TO FROM nx.model_bom")
        for m, ci, uq, my, ty in cur.fetchall(): mbom[str(m).strip()].append((str(ci).strip(), float(uq or 1), str(my or '').strip(), str(ty or '').strip()))
        recvmap = _dd(set)
        cur.execute("SELECT DISTINCT WORK_ORDER,ITEM_CODE FROM PARTNER_ERP.dbo.sa_t_recv_dtl WHERE WORK_ORDER>''")
        for wo, ic in cur.fetchall(): recvmap[str(wo).strip()].add(str(ic).strip())
        prate = {}
        cur.execute("SELECT ITEM_CODE, ISNULL(PROD_RATE,100) FROM PARTNER_ERP.dbo.PR_M_ITEM")
        for ic, pr in cur.fetchall(): prate[str(ic).strip()] = float(pr or 100)
        cur.execute("""IF OBJECT_ID('nx.plan_item_dtl') IS NULL CREATE TABLE nx.plan_item_dtl(
            PLAN_YMD varchar(6),WORK_ORDER varchar(20),SPLIT_WORK_ORDER varchar(30),C_ITEM_CODE varchar(20),
            USE_QTY decimal(18,5),LOT_QTY int,PLAN_QTY int,ORG_PLAN_YMD varchar(6),LINE_NO varchar(6),OUTPUT_HM varchar(4),PROD_RATE numeric(9,2))""")
        cur.execute("DELETE FROM nx.plan_item_dtl")
        cur.execute("SELECT WORK_ORDER,MODEL_NO,SUM(CAST(PLAN_QTY AS int)),MIN(PLAN_YMD) FROM nx.plan_dtl WHERE PLAN_QTY>0 GROUP BY WORK_ORDER,MODEL_NO")
        irows = []; lot = _dd(int)
        for wo, model, pq, ymd in cur.fetchall():
            wos = str(wo).strip(); mk = str(model).strip(); pq = int(pq or 0); ymd = str(ymd).strip()
            cand = mbom.get(mk); assys = None
            if cand:
                best = {}
                for a, mq, my, ty in cand:
                    if (not my or my <= ymd) and (not ty or ty >= ymd):
                        if a not in best or my > best[a][1]: best[a] = (mq, my)
                assys = [(a, best[a][0]) for a in best]
            if not assys:
                rc = recvmap.get(wos); assys = [(a, 1.0) for a in rc] if rc else None
            if not assys: continue
            for a, mq in assys:
                irows.append([ymd, wos, wos, a, mq, 0, pq, ymd, '', '0800', prate.get(a, 100)]); lot[wos] = max(lot[wos], pq)
        for rr in irows: rr[5] = lot[rr[1]]
        cur.fast_executemany = True
        cur.executemany("INSERT INTO nx.plan_item_dtl(PLAN_YMD,WORK_ORDER,SPLIT_WORK_ORDER,C_ITEM_CODE,USE_QTY,LOT_QTY,PLAN_QTY,ORG_PLAN_YMD,LINE_NO,OUTPUT_HM,PROD_RATE) VALUES(?,?,?,?,?,?,?,?,?,?,?)", irows)
        # ── STEP6 nx.plan_part_dtl: 10레벨 BOM전개 → 가공공정 → 공정전이지점 ──
        _step6_sql(cur)
        # ── STEP7 nx.plan_part_mat: 사급중단+최하위집계+charindex+용접봉(sgroup910)제외 ──
        _step7_sql(cur)
        # ── 조달 프로파일 오버레이 → nx.plan_mat_source (공급방식·공급처·수량) ──
        #   ①활성 프로파일 있으면 supply_gubun·vendor·배분(alloc) ②없으면 BOM기본(MAKE_TYPE→매입/사급/외주/자체 + IN_CUST vendor).
        cur.execute("""IF OBJECT_ID('nx.plan_mat_source') IS NULL CREATE TABLE nx.plan_mat_source(
            WORK_ORDER varchar(20),MAT_CODE varchar(20),SUPPLY_GUBUN varchar(20),VENDOR_CODE varchar(20),
            QTY decimal(18,3),SOURCE varchar(10),COMPOSE_DT datetime DEFAULT getdate())""")
        cur.execute("DELETE FROM nx.plan_mat_source")
        MKF = {}; INCF = {}
        cur.execute("SELECT ITEM_CODE, ISNULL(MAKE_TYPE,''), ISNULL(IN_CUST_CODE,'') FROM PARTNER_ERP.dbo.PR_M_ITEM")
        for ic, mkt, inc in cur.fetchall(): ic = str(ic).strip(); MKF[ic] = str(mkt).strip(); INCF[ic] = str(inc).strip()
        PRF = {}
        cur.execute("SELECT item_code, supply_gubun, ISNULL(vendor_code,''), ISNULL(alloc_ratio,100) FROM nx.sourcing_profile WHERE is_active=1 AND is_internal=0")
        for ic, sg, v, al in cur.fetchall(): PRF.setdefault(str(ic).strip(), []).append((str(sg).strip(), str(v).strip(), float(al or 100)))
        _MKMAP = {'1': '자체', '2': '외주가공', '3': '매입', '4': '유상사급', '5': '외주완성'}  # '자체'=프로파일 라벨과 통일
        cur.execute("SELECT work_order, mat_code, SUM(CAST(part_plan_qty AS float)) FROM nx.plan_part_mat GROUP BY work_order, mat_code")
        srows = []
        for wo, mat, qty in cur.fetchall():
            wo = str(wo).strip(); mat = str(mat).strip(); qty = float(qty or 0)
            ps = PRF.get(mat)
            if ps:
                for sg, v, al in ps: srows.append((wo, mat, sg, v, qty * al / 100.0, '프로파일'))
            else:
                srows.append((wo, mat, _MKMAP.get(MKF.get(mat, ''), '미지정'), INCF.get(mat, ''), qty, 'BOM기본'))
        cur.fast_executemany = True
        cur.executemany("INSERT INTO nx.plan_mat_source(WORK_ORDER,MAT_CODE,SUPPLY_GUBUN,VENDOR_CODE,QTY,SOURCE) VALUES(?,?,?,?,?,?)", srows)
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT work_order) FROM nx.plan_part_mat")
        n, woc = cur.fetchone()
        return {"ok": True, "item_lines": len(irows), "mat_lines": int(n), "mat_work_orders": int(woc), "sourcing_lines": len(srows)}
    finally:
        nx.close()

@router.get("/api/plan/sourcing")
def plan_sourcing(mode: str = Query("gubun"), gubun: str = Query(""), vendor: str = Query(""),
                  mat: str = Query(""), wo: str = Query("")):
    """조달 소요 조회. mode=gubun(공급방식별 집계)·vendor(공급처별)·detail(제번×자재 명세)."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_mat_source') IS NULL SELECT 1 WHERE 1=0")
        w = ["1=1"]; p = []
        if gubun.strip(): w.append("s.SUPPLY_GUBUN=?"); p.append(gubun.strip())
        if vendor.strip(): w.append("s.VENDOR_CODE=?"); p.append(vendor.strip())
        if mat.strip(): w.append("s.MAT_CODE LIKE ?"); p.append(f"%{mat.strip()}%")
        if wo.strip(): w.append("s.WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        wh = " AND ".join(w)
        try:
            if mode == "vendor":
                cur.execute(f"""SELECT s.SUPPLY_GUBUN, s.VENDOR_CODE, ISNULL(cu.CUST_DESC,'') vname,
                    COUNT(DISTINCT s.MAT_CODE) mats, SUM(s.QTY) qty FROM nx.plan_mat_source s
                    LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON s.VENDOR_CODE COLLATE DATABASE_DEFAULT=cu.CUST_CODE COLLATE DATABASE_DEFAULT
                    WHERE {wh} GROUP BY s.SUPPLY_GUBUN, s.VENDOR_CODE, cu.CUST_DESC ORDER BY SUM(s.QTY) DESC""", p)
            elif mode == "detail":
                cur.execute(f"""SELECT TOP 2000 s.WORK_ORDER, s.MAT_CODE, ISNULL(it.ITEM_DESC,'') mname, s.SUPPLY_GUBUN,
                    s.VENDOR_CODE, ISNULL(cu.CUST_DESC,'') vname, s.QTY, s.SOURCE FROM nx.plan_mat_source s
                    LEFT JOIN PARTNER_ERP.dbo.PR_M_ITEM it ON s.MAT_CODE COLLATE DATABASE_DEFAULT=it.ITEM_CODE COLLATE DATABASE_DEFAULT
                    LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON s.VENDOR_CODE COLLATE DATABASE_DEFAULT=cu.CUST_CODE COLLATE DATABASE_DEFAULT
                    WHERE {wh} ORDER BY s.QTY DESC""", p)
            else:  # gubun
                cur.execute(f"""SELECT s.SUPPLY_GUBUN, COUNT(DISTINCT s.MAT_CODE) mats, SUM(s.QTY) qty,
                    SUM(CASE WHEN s.SOURCE='프로파일' THEN s.QTY ELSE 0 END) prof_qty FROM nx.plan_mat_source s
                    WHERE {wh} GROUP BY s.SUPPLY_GUBUN ORDER BY SUM(s.QTY) DESC""", p)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            return {"ok": True, "mode": mode, "rows": rows}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "rows": []}
    finally:
        nx.close()

@router.get("/api/sales/forecast")
def sales_forecast(base: str = Query("")):
    """★영업예상매출현황 라이브 API (레거시 dw_pr_plan_190 재현, 정적스냅샷 대체).
       소스=sa_t_plan_item_dtl(union1)+pr_t_plan_input(union4). 단가=pr_m_item_cost(COST_TAG in S/E=LG판매가, 품목단위 최신, cust무관) KRW.
       gross=차감전(=라이브190). net=차감후=gross − union4(pr_t_plan_input)의 첫계획일 과대분 제거. [[nextgen-erp-sales-forecast-190]]"""
    cn = _conn(); cur = cn.cursor()
    try:
        b = _d6(base) if base.strip() else None
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
        today = str(cur.fetchone()[0])
        b = b or today
        # union1(sa_t_plan_item_dtl) + union4(pr_t_plan_input), item×ymd×src
        cur.execute(f"""
          SELECT C_ITEM_CODE item, PLAN_YMD ymd, 'u1' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM sa_t_plan_item_dtl WHERE PLAN_YMD>=? GROUP BY C_ITEM_CODE, PLAN_YMD
          UNION ALL
          SELECT ITEM_CODE item, PLAN_YMD ymd, 'u4' src, SUM(CAST(PLAN_QTY AS float)) q
            FROM pr_t_plan_input WHERE PLAN_YMD>=? GROUP BY ITEM_CODE, PLAN_YMD""", b, b)
        src = [(str(a).strip(), str(y).strip(), str(s).strip(), float(qq or 0)) for a, y, s, qq in cur.fetchall()]
        if not src:
            return {"base": b, "days": [], "rows": []}
        base_ymd = min(y for _, y, _, _ in src)  # 첫 계획일(차감 기준)
        # 단가: COST_TAG in (S,E) 최신 COST_APPLY_YMD, 품목단위(cust무관)
        cur.execute("""SELECT c.ITEM_CODE, c.ITEM_COST FROM pr_m_item_cost c
            JOIN (SELECT ITEM_CODE, MAX(COST_APPLY_YMD) mx FROM pr_m_item_cost WHERE COST_TAG IN('S','E') GROUP BY ITEM_CODE) m
              ON c.ITEM_CODE=m.ITEM_CODE AND c.COST_APPLY_YMD=m.mx WHERE c.COST_TAG IN('S','E')""")
        cost = {}
        for ic, ct in cur.fetchall():
            k = str(ic).strip()
            if k not in cost: cost[k] = float(ct or 0)
        cur.execute("SELECT ITEM_CODE, ISNULL(ITEM_DESC,''), ISNULL(WORK_CODE,'') FROM PR_M_ITEM")
        nmm = {}; wcm = {}
        for ic, d, wc in cur.fetchall(): k = str(ic).strip(); nmm[k] = d; wcm[k] = str(wc).strip()
        agg = {}; days = set()
        for item, ymd, s, qty in src:
            days.add(ymd)
            g = agg.get(item)
            if not g:
                g = {"item": item, "nm": nmm.get(item, ""), "wc": wcm.get(item, ""), "cost": cost.get(item, 0), "gdays": {}, "ndays": {}}
                agg[item] = g
            g["gdays"][ymd] = g["gdays"].get(ymd, 0) + qty
            if not (s == 'u4' and ymd == base_ymd):   # ★차감: pr_t_plan_input(u4) 첫날분 제외
                g["ndays"][ymd] = g["ndays"].get(ymd, 0) + qty
        rows = []
        for g in agg.values():
            gq = sum(g["gdays"].values()); nq = sum(g["ndays"].values()); c = g["cost"]
            g["gq"] = gq; g["nq"] = nq; g["gamt"] = round(gq * c); g["namt"] = round(nq * c)
            rows.append(g)
        return {"base": base_ymd, "days": sorted(days), "rows": rows,
                "gross_amt": round(sum(r["gamt"] for r in rows)), "net_amt": round(sum(r["namt"] for r in rows))}
    finally:
        cn.close()

def _step6_sql(cur):
    P = _P
    cur.execute("IF OBJECT_ID('nx.plan_part_temp') IS NOT NULL DROP TABLE nx.plan_part_temp")
    cur.execute(("""
    WITH CTE_BOM(assy_item_code, level_no, item_code, p_item_code, mat_code, cum_use_qty, in_cust_code, vir_item_flag, cum_item_code) AS (
      SELECT DISTINCT a.c_item_code,0,a.c_item_code,a.c_item_code,a.c_item_code,CONVERT(decimal(18,5),1),ISNULL(c.in_cust_code,''),'0',CONVERT(varchar(500),'{'+a.c_item_code+'}')
      FROM nx.plan_item_dtl a JOIN {P}PR_M_ITEM c ON a.c_item_code=c.item_code
      WHERE NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=a.c_item_code)
      UNION ALL
      SELECT cb.assy_item_code,cb.level_no+1,b.item_code,CASE cb.vir_item_flag WHEN '1' THEN cb.p_item_code ELSE b.item_code END,
             b.mat_code,CONVERT(decimal(18,5),cb.cum_use_qty*b.use_qty),ISNULL(c.in_cust_code,''),
             CASE b.vir_item_flag WHEN '1' THEN '1' ELSE '0' END,CONVERT(varchar(500),cb.cum_item_code+'{'+b.mat_code+'}')
      FROM CTE_BOM cb JOIN {P}PR_M_ITEM_BOM b ON cb.mat_code=b.item_code JOIN {P}PR_M_ITEM c ON b.mat_code=c.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1' AND cb.level_no<10 AND NOT EXISTS(SELECT 1 FROM {P}PR_M_MAT WHERE mat_code=b.mat_code))
    SELECT assy_item_code,level_no,item_code,MAX(p_item_code) p_item_code,mat_code,SUM(cum_use_qty) cum_use_qty,MAX(in_cust_code) in_cust_code,MAX(vir_item_flag) vir_item_flag
    INTO nx.plan_part_temp FROM CTE_BOM GROUP BY assy_item_code,level_no,item_code,mat_code OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_gagong') IS NOT NULL DROP TABLE nx.plan_part_gagong")
    cur.execute(("""SELECT a.assy_item_code,a.level_no,a.item_code,a.mat_code,a.p_item_code,a.vir_item_flag,b.proc_seq,g.gc_gubun,a.cum_use_qty,s.gagong_proc_code,b.gagong_proc_seq,b.s_work_code,ISNULL(b.lt_hr,0) lt_hr
    INTO nx.plan_part_gagong FROM nx.plan_part_temp a
    JOIN {P}PR_M_ITEM_PROC_GAGONG b ON a.mat_code=b.item_code JOIN {P}PR_M_WORK_SINGLE s ON b.s_work_code=s.s_work_code JOIN {P}PR_M_PROC_GAGONG g ON s.gagong_proc_code=g.gagong_proc_code
    WHERE a.vir_item_flag='0' AND ISNULL(a.in_cust_code,'') IN ('','2228')""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_swork') IS NOT NULL DROP TABLE nx.plan_part_swork")
    cur.execute(("""SELECT b.plan_ymd,b.work_order,b.split_work_order,a.assy_item_code,a.level_no AS bom_level,a.item_code AS upper_item_code,a.mat_code AS item_code,a.p_item_code,a.proc_seq,a.gc_gubun,
      b.line_no,a.cum_use_qty AS use_qty,b.lot_qty,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(c.prod_rate,100)/100) AS plan_qty,
      a.gagong_proc_code,a.gagong_proc_seq,a.s_work_code,a.lt_hr,CEILING(CONVERT(float,b.plan_qty)*ISNULL(b.use_qty,1)*ISNULL(c.prod_rate,100)/100)*a.cum_use_qty AS part_plan_qty
    INTO nx.plan_part_swork FROM nx.plan_part_gagong a JOIN nx.plan_item_dtl b ON a.assy_item_code=b.c_item_code JOIN {P}PR_M_ITEM c ON a.assy_item_code=c.item_code""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_dtl') IS NOT NULL DROP TABLE nx.plan_part_dtl")
    cur.execute("""SELECT a.* INTO nx.plan_part_dtl FROM nx.plan_part_swork a
      WHERE a.gagong_proc_code <> ISNULL((SELECT TOP 1 b.gagong_proc_code FROM nx.plan_part_swork b
        WHERE b.plan_ymd=a.plan_ymd AND b.work_order=a.work_order AND b.split_work_order=a.split_work_order AND b.assy_item_code=a.assy_item_code
          AND b.bom_level=a.bom_level AND b.upper_item_code=a.upper_item_code AND b.item_code=a.item_code AND b.proc_seq<a.proc_seq ORDER BY b.proc_seq DESC),'')""")

def _step7_sql(cur):
    P = _P
    cur.execute("IF OBJECT_ID('nx.plan_part_mat_tmp') IS NOT NULL DROP TABLE nx.plan_part_mat_tmp")
    cur.execute(("""
    WITH CTE_BOM(plan_ymd,work_order,split_work_order,assy_item_code,bom_level,upper_item_code,item_code,proc_seq,bom_mat_code,mat_work_center_code,cum_use_qty,cum_in_cust_code,mat_flag,use_qty,part_plan_qty,gc_gubun,cust_flag) AS (
      SELECT a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.item_code,
         CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust_code,'') END,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust_code,'') END+'|'),'1',a.use_qty,CONVERT(float,a.part_plan_qty)/NULLIF(a.use_qty,0),a.gc_gubun,'0'
      FROM nx.plan_part_dtl a JOIN {P}PR_M_ITEM c ON a.item_code=c.item_code WHERE a.proc_seq=1
      UNION ALL
      SELECT a.plan_ymd,a.work_order,a.split_work_order,a.c_item_code,0,a.c_item_code,a.c_item_code,1,a.c_item_code,
         CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust_code,'') END,CONVERT(decimal(18,5),a.use_qty),
         CONVERT(varchar(500),'||'+CASE WHEN c.work_code>'' THEN c.work_code ELSE ISNULL(c.in_cust_code,'') END+'|'),'1',a.use_qty,CEILING(CONVERT(float,a.plan_qty)*ISNULL(a.use_qty,1)*ISNULL(c.prod_rate,100)/100),'','1'
      FROM nx.plan_item_dtl a JOIN {P}PR_M_ITEM c ON a.c_item_code=c.item_code
      WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.item_code=a.c_item_code)
      UNION ALL
      SELECT cb.plan_ymd,cb.work_order,cb.split_work_order,cb.assy_item_code,cb.bom_level,cb.upper_item_code,cb.item_code,cb.proc_seq,b.mat_code,
         CASE WHEN m.work_code>'' THEN m.work_code ELSE ISNULL(m.in_cust_code,'') END,CONVERT(decimal(18,5),CASE WHEN cb.cum_use_qty=0 THEN 0 ELSE cb.cum_use_qty*b.use_qty END),
         CONVERT(varchar(500),cb.cum_in_cust_code+'|'+CASE WHEN m.work_code>'' THEN m.work_code ELSE ISNULL(m.in_cust_code,'') END+'|'),
         ISNULL((SELECT '2' FROM {P}PR_M_MAT WHERE mat_code=b.mat_code),'1'),cb.use_qty,cb.part_plan_qty,'','1'
      FROM CTE_BOM cb JOIN {P}PR_M_ITEM_BOM b ON cb.bom_mat_code=b.item_code JOIN {P}PR_M_ITEM m ON b.mat_code=m.item_code
      WHERE ISNULL(b.except_flag,'0')<>'1'
        AND NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WHERE d.plan_ymd=cb.plan_ymd AND d.work_order=cb.work_order AND d.split_work_order=cb.split_work_order
            AND d.assy_item_code=cb.assy_item_code AND d.bom_level=cb.bom_level+1 AND d.upper_item_code=b.item_code AND d.item_code=b.mat_code))
    SELECT * INTO nx.plan_part_mat_tmp FROM CTE_BOM
    WHERE CHARINDEX('||'+mat_work_center_code+'||',cum_in_cust_code)=0 AND NOT (cust_flag='0' AND gc_gubun='P') OPTION(MAXRECURSION 0)""").replace("{P}", P))
    cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NOT NULL DROP TABLE nx.plan_part_mat")
    # 최하위집계 + ★용접봉(sgroup910)=공정처리 제외
    cur.execute(("""SELECT a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code AS mat_code,
        SUM(a.part_plan_qty*a.cum_use_qty) AS part_plan_qty,MAX(a.mat_flag) mat_flag,MAX(a.mat_work_center_code) mat_work_center_code
    INTO nx.plan_part_mat FROM nx.plan_part_mat_tmp a
    WHERE NOT EXISTS(SELECT 1 FROM nx.plan_part_mat_tmp d WHERE d.work_order=a.work_order AND d.split_work_order=a.split_work_order AND d.assy_item_code=a.assy_item_code AND d.bom_level>a.bom_level AND d.bom_mat_code=a.bom_mat_code)
      AND NOT EXISTS(SELECT 1 FROM {P}PR_M_ITEM wj WHERE wj.item_code=a.bom_mat_code AND wj.item_sgroup='910')
    GROUP BY a.plan_ymd,a.work_order,a.split_work_order,a.assy_item_code,a.bom_level,a.upper_item_code,a.item_code,a.proc_seq,a.bom_mat_code""").replace("{P}", P))

@router.get("/api/plan/part")
def plan_part(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
              part: str = Query(""), assy: str = Query("")):
    # ★정본 파이프라인 전환: nx.plan_part(구 단일패스 98%) → nx.plan_part_mat(레거시 STEP5→6→7 100%검증).
    #   자도번(파트)=mat_code, 작업처=mat_work_center_code, 소요=part_plan_qty.
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.plan_part_mat') IS NULL SELECT 1 WHERE 1=0")
        w = ["1=1"]; p = []
        if from_ymd: w.append("pp.PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("pp.MAT_WORK_CENTER_CODE=?"); p.append(wc.strip())
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if assy.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{assy.strip()}%")
        try:
            cur.execute(f"""SELECT pp.PLAN_YMD, pp.ASSY_ITEM_CODE, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
                  COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE) wcnm, ISNULL(i.ITEM_DESC,'') nm,
                  SUM(CAST(pp.PART_PLAN_QTY AS float)) q
                FROM nx.plan_part_mat pp
                LEFT JOIN PARTNER_ERP.dbo.PR_M_WORK w ON w.WORK_CODE COLLATE DATABASE_DEFAULT=pp.MAT_WORK_CENTER_CODE COLLATE DATABASE_DEFAULT
                LEFT JOIN PARTNER_ERP.dbo.CM_M_CUST cu ON cu.CUST_CODE COLLATE DATABASE_DEFAULT=pp.MAT_WORK_CENTER_CODE COLLATE DATABASE_DEFAULT
                LEFT JOIN PARTNER_ERP.dbo.PR_M_ITEM i ON i.ITEM_CODE COLLATE DATABASE_DEFAULT=pp.MAT_CODE COLLATE DATABASE_DEFAULT
                WHERE {' AND '.join(w)}
                GROUP BY pp.PLAN_YMD, pp.ASSY_ITEM_CODE, pp.MAT_CODE, pp.MAT_WORK_CENTER_CODE,
                  COALESCE(w.WORK_DESC, cu.CUST_DESC, pp.MAT_WORK_CENTER_CODE), i.ITEM_DESC""", *p)
        except Exception:
            return {"dates": [], "rows": [], "part_count": 0, "sum_qty": 0, "note": "편성 먼저 실행(/compose_mat)"}
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        dates = sorted({r["PLAN_YMD"] for r in raw})
        keyed = {}
        for r in raw:
            k = (r["ASSY_ITEM_CODE"], r["MAT_CODE"], r["MAT_WORK_CENTER_CODE"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["ASSY_ITEM_CODE"], "part": r["MAT_CODE"], "nm": r["nm"], "wc": r["MAT_WORK_CENTER_CODE"],
                     "wcnm": r["wcnm"], "sg": "", "days": {}, "tot": 0}
                keyed[k] = g
            q = float(r["q"] or 0); g["days"][r["PLAN_YMD"]] = g["days"].get(r["PLAN_YMD"], 0) + q; g["tot"] += q
        rows = sorted(keyed.values(), key=lambda x: (x["wcnm"] or "", x["part"]))
        return {"dates": dates, "rows": rows, "part_count": len(rows), "sum_qty": sum(float(r["q"] or 0) for r in raw)}
    finally:
        nx.close()
