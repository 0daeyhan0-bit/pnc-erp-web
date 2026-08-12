# -*- coding: utf-8 -*-
"""생산실적 도메인 라우터 — 생산실적현황(010)·파트별생산실적(090)·파트원장·공정별실적.
   app.py에서 분리(다중세션 충돌방지). 공유헬퍼는 common.py에서 import."""
from fastapi import APIRouter, Query
from common import _conn, _d6, _num, _nx, _nx_tx, _b

router = APIRouter()

@router.get("/api/prodresult/list")
def prodresult_list(from_ymd: str = Query(""), to_ymd: str = Query(""), swork: str = Query(""),
                    line: str = Query(""), item: str = Query(""), tag: str = Query(""), gubun: str = Query("1")):
    """생산실적현황(레거시 w_pr_list_010) — 작업장(WORK_CODE)×일자×구분(PROD_TAG) 집계 평면리스트.
       ★실측확정: LOT수량=COUNT(DISTINCT ITEM_CODE)·생산수량=SUM(PROD_QTY)·필요ST=SUM(f_get_item_st_day(item,ymd)×qty)/60·구분=PROD_TAG(1양산/2셀).
       ★필요ST=PARTNER_ERP_TEST3.dbo.f_stday_live(전체 품목ST=레거시 f_get_item_st_day 복제, PARTNER_ERP 라우팅). 소스=PR_T_PROD_DTL(레거시 dw_pr_list_010_l2 정본, 작업장뷰).
       주의: 010은 090(파트별)과 달리 PROD_DTL 작업장뷰라 용접/가공 합집합 불필요·f_stday_live로 양산2924.1·blank16518.6 둘다 정확. tag='1'양산/'2'셀."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["d.PROD_YMD>''"]; p = []
        if from_ymd: w.append("d.PROD_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("d.PROD_YMD<=?"); p.append(_d6(to_ymd))
        if swork.strip(): w.append("ISNULL(d.WORK_CODE,'')=?"); p.append(swork.strip())   # 작업장코드 P1(용접)/P2(가공) 정확일치
        if line.strip():  w.append("ISNULL(d.LINE_NO,'')=?"); p.append(line.strip())      # 라인 드롭다운 정확일치
        if item.strip():  w.append("d.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if tag.strip() in ('1', '2'): w.append("ISNULL(d.PROD_TAG,'')=?"); p.append(tag.strip())
        gb = (gubun or "1").strip()
        if gb == "2":   # 도번(ITEM_CODE)별 상세
            cur.execute(f"""SELECT d.ITEM_CODE,
                  ISNULL((SELECT TOP 1 ITEM_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=d.ITEM_CODE),'') inm,
                  d.PROD_YMD, ISNULL(d.LINE_NO,'') line, ISNULL(d.PROD_TAG,'') tag,
                  SUM(d.PROD_QTY) qty,
                  SUM(PARTNER_ERP_TEST3.dbo.f_stday_live(d.ITEM_CODE, d.PROD_YMD)*d.PROD_QTY)/60.0 st
                FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL d WHERE {' AND '.join(w)}
                GROUP BY d.ITEM_CODE, d.PROD_YMD, ISNULL(d.LINE_NO,''), ISNULL(d.PROD_TAG,'')
                ORDER BY d.PROD_YMD, d.ITEM_CODE, ISNULL(d.PROD_TAG,'')""", *p)
            rows = [{"item": str(r[0]).strip(), "inm": str(r[1]).strip(), "ymd": str(r[2]),
                     "line": str(r[3]).strip(), "tag": str(r[4]).strip(),
                     "gubun": {'1': '양산', '2': '셀'}.get(str(r[4]).strip(), ''),
                     "qty": float(r[5] or 0), "st": round(float(r[6] or 0), 1)} for r in cur.fetchall()]
            return {"mode": "2", "rows": rows, "cnt": len(rows),
                    "sum_qty": sum(r["qty"] for r in rows), "sum_st": round(sum(r["st"] for r in rows) / 60.0, 1)}
        # gb == "1": 작업장별 일별 집계 (기본)
        cur.execute(f"""SELECT ISNULL(d.WORK_CODE,'') wc,
              ISNULL((SELECT TOP 1 WORK_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_WORK WHERE WORK_CODE=d.WORK_CODE),'') wcnm,
              d.PROD_YMD, ISNULL(d.PROD_TAG,'') tag,
              COUNT(DISTINCT d.ITEM_CODE) lot, SUM(d.PROD_QTY) qty,
              SUM(PARTNER_ERP_TEST3.dbo.f_stday_live(d.ITEM_CODE, d.PROD_YMD)*d.PROD_QTY)/60.0 st
            FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL d WHERE {' AND '.join(w)}
            GROUP BY d.WORK_CODE, d.PROD_YMD, ISNULL(d.PROD_TAG,'')
            ORDER BY d.PROD_YMD, d.WORK_CODE, ISNULL(d.PROD_TAG,'')""", *p)
        rows = [{"wc": str(r[0]).strip(), "wcnm": str(r[1]).strip(), "ymd": str(r[2]), "tag": str(r[3]).strip(),
                 "gubun": {'1': '양산', '2': '셀'}.get(str(r[3]).strip(), ''),
                 "lot": int(r[4] or 0), "qty": float(r[5] or 0), "st": round(float(r[6] or 0), 1)} for r in cur.fetchall()]
        return {"mode": "1", "rows": rows, "cnt": len(rows), "sum_lot": sum(r["lot"] for r in rows),
                "sum_qty": sum(r["qty"] for r in rows), "sum_st": round(sum(r["st"] for r in rows) / 60.0, 1)}  # footer=Σ(분)/60=시간(레거시 DW group trailer)
    finally:
        cn.close()

@router.get("/api/prodresult/filters")
def prodresult_filters():
    """생산실적현황 필터 드롭다운 소스 — 작업장코드(PR_M_WORK P1용접/P2가공)·라인(LINE_NO 실값)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT WORK_CODE, WORK_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_WORK ORDER BY WORK_CODE")
        works = [{"code": str(r[0]).strip(), "name": str(r[1]).strip()} for r in cur.fetchall() if str(r[0]).strip()]
        cur.execute("SELECT DISTINCT LINE_NO FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL WHERE LINE_NO>'' AND PROD_YMD>='260101' ORDER BY LINE_NO")
        lines = [str(r[0]).strip() for r in cur.fetchall() if str(r[0]).strip()]
        return {"works": works, "lines": lines}
    finally:
        cn.close()

def _sticker_result(cur, from_ymd, to_ymd, part, item, worker, gb):
    """레거시 w_pr_list_090 조회종류 7(바코드)/5(가간판)/6(스티커) — PR_T_PROD_DTL_STICKER 공정단위 상세.
       ★실측확정(스크린샷 앵커 정확일치): 소스=PR_T_PROD_DTL_STICKER + PR_T_INDI_WELD_SHEET_DTL(TOT_ST) + QA_M_MACHINE(설비명).
       분할: 7=전체(9408)·5=BARCODE 'GP%'(가간판9035)·6=BARCODE '00%'(스티커373). 날짜=PROD_DATETIME(YYMMDD).
       공정ST: 7=TOT_ST×수량, 5/6=TOT_ST×수량/60. 파트=PROC_CODE→PR_M_PROC_GAGONG. 필터 파트/도번/작업자(WORKER_CODE)."""
    w = ["s.PROD_DATETIME IS NOT NULL"]; p = []
    if from_ymd: w.append("CONVERT(varchar(6),s.PROD_DATETIME,12)>=?"); p.append(_d6(from_ymd))
    if to_ymd:   w.append("CONVERT(varchar(6),s.PROD_DATETIME,12)<=?"); p.append(_d6(to_ymd))
    if gb == "5": w.append("s.BARCODE LIKE 'GP%'")
    elif gb == "6": w.append("s.BARCODE LIKE '00%'")
    if part.strip(): w.append("ISNULL(s.PROC_CODE,'')=?"); p.append(part.strip())
    if item.strip(): w.append("s.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
    if worker.strip(): w.append("s.WORKER_CODE LIKE ?"); p.append(f"%{worker.strip()}%")
    cur.execute(f"""SELECT s.PROC_CODE,
          ISNULL((SELECT TOP 1 GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=s.PROC_CODE),'') partnm,
          s.S_WORK_CODE, s.ITEM_CODE, ISNULL(s.PROD_TAG,'') tag, s.PROD_QTY,
          x.tot, s.WORKER_CODE, s.MACH_CODE,
          ISNULL((SELECT TOP 1 MACH_DESC FROM PARTNER_ERP_TEST3.nx.QA_M_MACHINE WHERE MACH_CODE=s.MACH_CODE),'') machnm,
          s.STA_DATETIME, s.PROD_DATETIME, s.BARCODE, s.SHEET_NO, s.PROC_SEQ,
          s.UPDATE_USER_ID, s.UPDATE_DATETIME, s.UPDATE_IP, s.UPDATE_COMPUTER, s.UPDATE_WINDOW
        FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL_STICKER s
        OUTER APPLY (SELECT TOP 1 d.TOT_ST tot FROM PARTNER_ERP_TEST3.nx.PR_T_INDI_WELD_SHEET_DTL d
             WHERE d.SHEET_NO=s.SHEET_NO AND d.PROC_SEQ=s.PROC_SEQ AND d.S_WORK_CODE=s.S_WORK_CODE) x
        WHERE {' AND '.join(w)}
        ORDER BY s.PROC_CODE, s.SHEET_NO, s.PROC_SEQ""", *p)
    div = 1.0 if gb == "7" else 60.0
    def _dt(v):
        try: return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""
        except Exception: return str(v or "")
    rows = []
    for r in cur.fetchall():
        qty = float(r[5] or 0); tot = float(r[6] or 0)
        rows.append({
            "part": str(r[0] or "").strip(), "partnm": str(r[1] or "").strip(), "swork": str(r[2] or "").strip(),
            "item": str(r[3] or "").strip(), "tag": str(r[4] or "").strip(),
            "gubun_tag": {'1': '양산', '2': '셀'}.get(str(r[4] or "").strip(), ''),
            "qty": qty, "st": round(tot * qty / div, 2),
            "worker": str(r[7] or "").strip(), "mach": str(r[8] or "").strip(), "machnm": str(r[9] or "").strip(),
            "sta": _dt(r[10]), "fin": _dt(r[11]), "barcode": str(r[12] or "").strip(),
            "sheet": r[13], "proc_seq": r[14],
            "u_user": str(r[15] or "").strip(), "u_dt": _dt(r[16]), "u_ip": str(r[17] or "").strip(),
            "u_comp": str(r[18] or "").strip(), "u_win": str(r[19] or "").strip()})
    return {"mode": gb, "rows": rows, "cnt": len(rows),
            "sum_qty": sum(r["qty"] for r in rows), "sum_st": round(sum(r["st"] for r in rows), 2)}

@router.get("/api/partresult/list")
def partresult_list(from_ymd: str = Query(""), to_ymd: str = Query(""), part: str = Query(""),
                    item: str = Query(""), worker: str = Query(""), gubun: str = Query("1")):
    """파트별 생산실적현황(레거시 w_pr_list_090) — 파트×일자 집계/도번 평면리스트.
       ★실측확정(2026-08-02, 272행/398,897 정확재현): 소스=PR_T_PROD_DTL_PROC(조립/용접, part=PROC_CODE)
       ∪ PR_T_INDI_CUTTING(가공, part=IN_GAGONG_PROC_CODE, PROD_QTY=가공완료). PR_T_PROD_DTL 아님(용접 S5 누락되던 원인).
       필요ST=PARTNER_ERP_TEST.dbo.f_get_item_st_day(레거시 운영DB, S6=5244.1 정확일치)×수량/60. 파트명=PR_M_PROC_GAGONG.
       필터 도번(item)·파트(part)·작업자(PROD_USER_ID). 5/6/7=STICKER 바코드/가간판/스티커."""
    cn = _conn(); cur = cn.cursor()
    try:
        gb = (gubun or "1").strip()
        if gb in ("5", "6", "7"):   # 바코드/가간판/스티커 — PR_T_PROD_DTL_STICKER 공정단위 상세(실측확정)
            return _sticker_result(cur, from_ymd, to_ymd, part, item, worker, gb)
        # 집계/도번 소스 = PROC(조립/용접, part=PROC_CODE) ∪ CUTTING(가공, part=IN_GAGONG_PROC_CODE) — part×일자 합집합
        # ★필요ST = f_st_part_day_live(item, 파트, ymd)×수량: 파트별·날짜별 공정ST(라이브 PARTNER_ERP.pr_m_item_st_day.tot_st /폴백 proc_gagong.TOT_ST).
        #   레거시 f_get_item_st_part_day 로직을 라이브데이터로 복제(TEST3 st_day는 07/16고정) — 조립/용접/가공 자동분리, 07/01 11/11 정확.
        STFN = "PARTNER_ERP_TEST3.dbo.f_st_part_day_live"
        wp = ["a.PROC_CODE>''"]; wc = ["c.IN_GAGONG_PROC_CODE>''", "c.PROD_DATETIME IS NOT NULL"]; pp = []; pc = []
        if from_ymd:
            fd = _d6(from_ymd)
            wp.append("a.PROD_YMD>=?"); pp.append(fd)
            wc.append("CONVERT(varchar(6),c.PROD_DATETIME,12)>=?"); pc.append(fd)
        if to_ymd:
            td = _d6(to_ymd)
            wp.append("a.PROD_YMD<=?"); pp.append(td)
            wc.append("CONVERT(varchar(6),c.PROD_DATETIME,12)<=?"); pc.append(td)
        if part.strip():
            wp.append("a.PROC_CODE=?"); pp.append(part.strip())
            if part.strip() != "P0002":
                wc.append("1=0")   # 가공(P0002=11라인가공) 외 파트 선택시 CUTTING 제외
        if item.strip():
            wp.append("a.ITEM_CODE LIKE ?"); pp.append(f"%{item.strip()}%")
            wc.append("c.ITEM_CODE LIKE ?"); pc.append(f"%{item.strip()}%")
        if worker.strip():
            wp.append("a.PROD_USER_ID LIKE ?"); pp.append(f"%{worker.strip()}%")
            wc.append("c.PROD_USER_ID LIKE ?"); pc.append(f"%{worker.strip()}%")
        union = f"""SELECT a.PROC_CODE part, a.PROD_YMD ymd, a.PROD_QTY qty, a.ITEM_CODE item, ISNULL(a.PROD_TAG,'') tag,
                           {STFN}(a.ITEM_CODE,a.PROC_CODE,a.PROD_YMD)*a.PROD_QTY stq
                      FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL_PROC a WHERE {' AND '.join(wp)}
                    UNION ALL
                    SELECT 'P0002', CONVERT(varchar(6),c.PROD_DATETIME,12), c.PROD_QTY, c.MAT_CODE, '',
                           {STFN}(c.ITEM_CODE,'P0002',CONVERT(varchar(6),c.PROD_DATETIME,12))*c.PROD_QTY
                      FROM PARTNER_ERP_TEST3.nx.PR_T_INDI_CUTTING c WHERE {' AND '.join(wc)}"""
                    # 가공(CUTTING)=P0002(11라인가공): 파트=P0002·품목수=자도번(MAT_CODE)distinct·ST=f(ITEM_CODE,P0002). 레거시 07/29~31 정확일치
        params = pp + pc
        if gb == "2":   # 파트별 생산실적(도번) — 파트×도번×일자
            cur.execute(f"""SELECT z.part, ISNULL((SELECT TOP 1 GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=z.part),'') pnm,
                  z.item, ISNULL((SELECT TOP 1 ITEM_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE=z.item),'') inm, z.ymd, z.tag, z.qty, z.st
                FROM (SELECT u.part, u.item, u.ymd, u.tag, SUM(u.qty) qty, SUM(u.stq)/60.0 st
                      FROM ({union}) u GROUP BY u.part, u.item, u.ymd, u.tag) z
                ORDER BY z.ymd, z.part, z.item""", *params)
            rows = [{"part": str(r[0]).strip(), "pnm": str(r[1]).strip(), "item": str(r[2]).strip(),
                     "inm": str(r[3]).strip(), "ymd": str(r[4]), "tag": str(r[5]).strip(),
                     "gubun": {'1': '양산', '2': '셀'}.get(str(r[5]).strip(), ''),
                     "qty": float(r[6] or 0), "st": round(float(r[7] or 0), 1)} for r in cur.fetchall()]
            return {"mode": "2", "rows": rows, "cnt": len(rows), "sum_qty": sum(r["qty"] for r in rows),
                    "sum_st": round(sum(r["st"] for r in rows) / 60.0, 1)}
        # gb == "1": 파트별 생산실적(집계)
        cur.execute(f"""SELECT z.part, ISNULL((SELECT TOP 1 GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WHERE GAGONG_PROC_CODE=z.part),'') pnm,
              z.ymd, z.qty, z.st, z.items
            FROM (SELECT u.part, u.ymd, SUM(u.qty) qty, SUM(u.stq)/60.0 st, COUNT(DISTINCT u.item) items
                  FROM ({union}) u GROUP BY u.part, u.ymd) z
            ORDER BY z.ymd, z.part""", *params)
        rows = [{"part": str(r[0]).strip(), "pnm": str(r[1]).strip(), "ymd": str(r[2]),
                 "qty": float(r[3] or 0), "st": round(float(r[4] or 0), 1), "items": int(r[5] or 0)} for r in cur.fetchall()]
        return {"mode": "1", "rows": rows, "cnt": len(rows), "sum_qty": sum(r["qty"] for r in rows),
                "sum_st": round(sum(r["st"] for r in rows) / 60.0, 1)}  # footer=Σ(분)/60=시간(레거시 DW group trailer)
    finally:
        cn.close()

@router.get("/api/partresult/filters")
def partresult_filters():
    """파트별 생산실적 필터 드롭다운 소스 — 파트(PR_M_PROC_GAGONG 정본, 레거시 c1 gagong_proc_code)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT GAGONG_PROC_CODE, GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG ORDER BY GAGONG_PROC_CODE")
        parts = [{"code": str(r[0]).strip(), "name": str(r[1]).strip()} for r in cur.fetchall() if str(r[0]).strip()]
        return {"parts": parts}
    finally:
        cn.close()

# ====== 생산 ⑦⑧: 생산파트재고조정(w_pr_stock_470)·생산자재출고(w_pr_stock_150) — PR_T_STOCK_MAINT_MAT ======
# MAINT_TAG '2'=장부수정(재고조정), FROM_PART_CODE 有=창고간 이동/출고, '4'=생산소요.
@router.get("/api/partledger/list")
def partledger_list(kind: str = Query("adj"), from_ymd: str = Query(""), to_ymd: str = Query(""),
                    part: str = Query(""), wc: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        w = []; p = []
        if kind == "adj":     w.append("m.MAINT_TAG='2'")            # 재고조정(장부수정)
        elif kind == "issue": w.append("m.FROM_PART_CODE>'' AND m.FROM_PART_CODE<>m.PART_CODE")  # 창고이동/출고
        else:                 w.append("1=1")
        if from_ymd: w.append("m.MAINT_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("m.MAINT_YMD<=?"); p.append(_d6(to_ymd))
        if part.strip(): w.append("m.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if wc.strip():   w.append("(m.PROD_WORK_CODE=? OR m.WORK_CODE=?)"); p += [wc.strip(), wc.strip()]
        cur.execute(f"""SELECT TOP 2000 m.MAINT_YMD, m.MAINT_SEQ, m.MAINT_TAG, ISNULL(m.PART_CODE,'') part,
              ISNULL(m.FROM_PART_CODE,'') frompart, ISNULL(m.MAT_CODE,'') mat, ISNULL(ii.ITEM_DESC,'') nm,
              m.MAINT_QTY, m.MAINT_COST, m.MAINT_AMT, ISNULL(m.REMARKS,'') remarks, ISNULL(m.ITEM_CODE,'') dobun,
              ISNULL(m.PROD_WORK_CODE,'') pwc, ISNULL(m.INSERT_USER_ID,'') usr, m.INSERT_DATETIME
            FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT m LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM ii ON ii.ITEM_CODE=m.MAT_CODE
            WHERE {' AND '.join(w)} ORDER BY m.MAINT_YMD DESC, m.MAINT_SEQ DESC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["MAINT_QTY"] = float(r["MAINT_QTY"] or 0); r["MAINT_COST"] = float(r["MAINT_COST"] or 0)
            r["MAINT_AMT"] = float(r["MAINT_AMT"] or 0)
            r["INSERT_DATETIME"] = str(r["INSERT_DATETIME"] or "")[:19]
        return {"rows": rows, "cnt": len(rows), "sum_qty": sum(r["MAINT_QTY"] for r in rows)}
    finally:
        cn.close()

# ====== 생산 ⑨: 공정별 생산실적등록 이력(w_pr_input_260) — PR_T_PROD_DTL 상세 ======
@router.get("/api/procresult/dtl")
def procresult_dtl(from_ymd: str = Query(""), to_ymd: str = Query(""), swork: str = Query(""),
                   line: str = Query(""), item: str = Query("")):
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["d.PROD_YMD>''"]; p = []
        if from_ymd: w.append("d.PROD_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("d.PROD_YMD<=?"); p.append(_d6(to_ymd))
        if swork.strip(): w.append("d.S_WORK_CODE=?"); p.append(swork.strip())
        if line.strip():  w.append("d.LINE_NO=?"); p.append(line.strip())
        if item.strip():  w.append("d.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        cur.execute(f"""SELECT TOP 2000 d.PROD_YMD, d.PROD_HMS, ISNULL(d.WORK_ORDER,'') wo, ISNULL(d.ITEM_CODE,'') item,
              ISNULL(ii.ITEM_DESC,'') nm, ISNULL(d.PART_CODE,'') part, d.S_WORK_CODE sw, ISNULL(d.LINE_NO,'') line,
              d.PROD_QTY, ISNULL(d.PROD_USER_ID,'') usr
            FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL d LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM ii ON ii.ITEM_CODE=d.ITEM_CODE
            WHERE {' AND '.join(w)} ORDER BY d.PROD_YMD DESC, d.PROD_HMS DESC""", *p)
        cols = [dd[0] for dd in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["PROD_QTY"] = float(r["PROD_QTY"] or 0); r["sw"] = str(r["sw"] or "")
        return {"rows": rows, "cnt": len(rows), "sum_qty": sum(r["PROD_QTY"] for r in rows)}
    finally:
        cn.close()
