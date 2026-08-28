# -*- coding: utf-8 -*-
"""prodwrite 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes, _lock_msg)

router = APIRouter()

# ================= 생산 쓰기화면 공용 룩업 =================
@router.get("/api/wr/itemsearch")
def wr_itemsearch(q: str = Query("")):
    """품번/품명 부분검색 (자재·도번 입력 도우미)"""
    q = q.strip()
    cn = _conn(); cur = cn.cursor()
    try:
        like = f"%{q}%"
        cur.execute("""SELECT TOP 40 ITEM_CODE, ISNULL(item_name,'') nm, ISNULL(sgroup,'') sg
            FROM PARTNER_ERP_TEST3.nx.item WHERE ITEM_CODE LIKE ? OR item_name LIKE ? ORDER BY ITEM_CODE""", like, like)
        return {"rows": [{"item": r[0], "nm": r[1], "sg": r[2]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/wr/parts")
def wr_parts():
    """파트(생산창고) 목록 — PR_M_PROC_GAGONG.
       ★재고조정 등 쓰기화면의 파트칸은 반드시 이 드롭다운으로(코드 저장·이름 표시).
         자유입력으로 두면 '04라인' 같은 표시명이 PART_CODE 에 들어가
         재고가 없는 파트에 쌓인다(2026-08-25 실사고: SUB6 조정 500개가 S4 대신
         '04라인'에 들어가 520 차감이 재고 0 으로 판정)."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') nm
                         FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG WITH(NOLOCK)
                        WHERE ISNULL(GAGONG_PROC_CODE,'')<>''
                        ORDER BY GAGONG_PROC_CODE""")
        rows = [{"code": str(r[0]).strip(), "nm": str(r[1] or '').strip()} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.get("/api/wr/works")
def wr_works():
    """작업장 목록 (PR_M_WORK)"""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT WORK_CODE, ISNULL(WORK_DESC,'') nm FROM PARTNER_ERP_TEST3.nx.PR_M_WORK ORDER BY WORK_CODE")
        return {"rows": [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/wr/sworks")
def wr_sworks():
    """공정(S_WORK_CODE) 목록 — 실적 상위 사용코드"""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT TOP 40 S_WORK_CODE, COUNT(*) c FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL
            WHERE S_WORK_CODE IS NOT NULL AND S_WORK_CODE>0 GROUP BY S_WORK_CODE ORDER BY c DESC""")
        return {"rows": [{"code": int(r[0])} for r in cur.fetchall()]}
    finally:
        cn.close()


# ================= 470 자재개별재고조정 (w_pr_stock_470) — ★Phase3 단일원장 fold: nx.stock_ledger(STOCK_POINT='PRD') =================
# 생산파트재고조정 = PRD 조정(±). 태그: 불량→'1', 재고조정→'2', 기타→'PE'(레거시 '4', STOCK_POINT로 격리).
# ID = "YMD-SEQ" (원장 복합키). 수정=기존행 삭제 후 신규(일자·부호 변경 안전). 마감월 잠금 가드.
STOCKMAINT_TAGS = {"1": "불량", "2": "재고조정", "4": "기타"}
_SM_UI2LED = {"4": "PE"}   # UI 태그 → 원장 태그
_SM_LED2UI = {"PE": "4"}   # 원장 태그 → UI 태그

@router.get("/api/stockmaint/list")
def stockmaint_list(from_ymd: str = Query(""), to_ymd: str = Query(""), tag: str = Query(""),
                    mat: str = Query(""), wc: str = Query("")):
    """생산파트재고조정 조회 = 웹(nx.stock_ledger PRD, editable) ∪ 미러이력(nx.PR_T_STOCK_MAINT_MAT tag2 재고조정, 읽기전용).
       컷오버: 레거시 라이브 없음. 미러=델타싱크가 채운 nx, src='legacy' editable=0."""
    nx = _nx(); cur = nx.cursor()
    try:
        rows = []
        # --- 웹행 (nx.stock_ledger PRD, 편집가능) ---
        if not tag.strip() or _SM_UI2LED.get(tag.strip()[:1], tag.strip()[:1]) in ('1','2','PE'):
            w = ["l.STOCK_POINT='PRD'", "l.MAINT_TAG IN ('1','2','PE')"]; p = []
            if from_ymd: w.append("l.MAINT_YMD>=?"); p.append(_d6(from_ymd))
            if to_ymd:   w.append("l.MAINT_YMD<=?"); p.append(_d6(to_ymd))
            if tag.strip():
                ui = tag.strip()[:1]; w.append("l.MAINT_TAG=?"); p.append(_SM_UI2LED.get(ui, ui))
            if mat.strip():  w.append("(l.MAT_CODE LIKE ? OR l.ITEM_CODE LIKE ?)"); p += [f"%{mat.strip()}%"]*2
            if wc.strip():   w.append("(l.WORK_CODE=? OR l.TO_GAGONG_PROC_CODE=?)"); p += [wc.strip(), wc.strip()]
            cur.execute(f"""SELECT TOP 3000 l.MAINT_YMD, l.MAINT_SEQ, ISNULL(l.MAINT_TAG,'') tag,
                  ISNULL(l.WORK_CODE,'') work_code, ISNULL(l.GAGONG_PROC_CODE,'') part_code,
                  ISNULL(l.MAT_CODE,'') mat_code, ISNULL(im.item_name,'') mat_nm,
                  ISNULL(l.ITEM_CODE,'') item_code, ISNULL(ii.item_name,'') item_nm,
                  l.MAINT_QTY, l.MAINT_COST, l.MAINT_AMT, ISNULL(l.REMARKS,'') remarks,
                  ISNULL(l.TO_GAGONG_PROC_CODE,'') prod_work_code, ISNULL(l.INSERT_USER_ID,'') usr, l.INSERT_DATETIME
                FROM nx.stock_ledger l
                LEFT JOIN PARTNER_ERP_TEST3.nx.item im ON im.ITEM_CODE=l.MAT_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.item ii ON ii.ITEM_CODE=l.ITEM_CODE
                WHERE {' AND '.join(w)} ORDER BY l.MAINT_YMD DESC, l.MAINT_SEQ DESC""", *p)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                d = dict(zip(cols, r)); ui = _SM_LED2UI.get(d["tag"], d["tag"])
                d["ID"] = f'{d["MAINT_YMD"]}-{d["MAINT_SEQ"]}'; d["tag"] = ui; d["src"] = "web"; d["editable"] = 1
                d["MAINT_QTY"] = float(d["MAINT_QTY"] or 0); d["MAINT_COST"] = float(d["MAINT_COST"] or 0); d["MAINT_AMT"] = float(d["MAINT_AMT"] or 0)
                d["tag_nm"] = STOCKMAINT_TAGS.get(ui, ui); d["INSERT_DATETIME"] = str(d["INSERT_DATETIME"] or "")[:19]
                rows.append(d)
        # --- 미러 이력행 (nx.PR_T_STOCK_MAINT_MAT tag2 재고조정, 읽기전용) ---
        if not tag.strip() or tag.strip()[:1] == '2':
            wm = ["m.MAINT_TAG='2'"]; pm = []
            if from_ymd: wm.append("m.MAINT_YMD>=?"); pm.append(_d6(from_ymd))
            if to_ymd:   wm.append("m.MAINT_YMD<=?"); pm.append(_d6(to_ymd))
            if mat.strip():  wm.append("(m.MAT_CODE LIKE ? OR m.ITEM_CODE LIKE ?)"); pm += [f"%{mat.strip()}%"]*2
            if wc.strip():   wm.append("(m.WORK_CODE=? OR m.PROD_WORK_CODE=?)"); pm += [wc.strip(), wc.strip()]
            cur.execute(f"""SELECT TOP 3000 m.MAINT_YMD, m.MAINT_SEQ, ISNULL(m.WORK_CODE,'') work_code,
                  ISNULL(m.PART_CODE,'') part_code, ISNULL(m.MAT_CODE,'') mat_code, ISNULL(im.item_name,'') mat_nm,
                  ISNULL(m.ITEM_CODE,'') item_code, ISNULL(ii.item_name,'') item_nm,
                  m.MAINT_QTY, m.MAINT_COST, m.MAINT_AMT, ISNULL(m.REMARKS,'') remarks,
                  ISNULL(m.PROD_WORK_CODE,'') prod_work_code, ISNULL(m.INSERT_USER_ID,'') usr, m.INSERT_DATETIME
                FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT m
                LEFT JOIN PARTNER_ERP_TEST3.nx.item im ON im.ITEM_CODE=m.MAT_CODE
                LEFT JOIN PARTNER_ERP_TEST3.nx.item ii ON ii.ITEM_CODE=m.ITEM_CODE
                WHERE {' AND '.join(wm)} ORDER BY m.MAINT_YMD DESC, m.MAINT_SEQ DESC""", *pm)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                d = dict(zip(cols, r)); d["tag"] = "2"; d["src"] = "legacy"; d["editable"] = 0
                d["ID"] = None   # 미러 이력=읽기전용(wrCrud가 ID없으면 체크박스·수정 숨김)
                d["MAINT_QTY"] = float(d["MAINT_QTY"] or 0); d["MAINT_COST"] = float(d["MAINT_COST"] or 0); d["MAINT_AMT"] = float(d["MAINT_AMT"] or 0)
                d["tag_nm"] = STOCKMAINT_TAGS.get("2", "재고조정"); d["INSERT_DATETIME"] = str(d["INSERT_DATETIME"] or "")[:19]
                rows.append(d)
        rows.sort(key=lambda r: (str(r["MAINT_YMD"]), 1 if r["src"] == "web" else 0, r["MAINT_SEQ"]), reverse=True)
        return {"rows": rows, "cnt": len(rows), "sum_qty": sum(r["MAINT_QTY"] for r in rows),
                "sum_amt": sum(r["MAINT_AMT"] for r in rows)}
    finally:
        nx.close()

def _prd_mirror_ins(cur, ymd, part, mat, item, tag, qty, cost, amt, rem):
    """★생산재고조회(w_pr_stock_480, _prodstock)는 PR_T_STOCK_MAINT_MAT를 읽음 → 생산파트조정이 여기에도 써야 조회 반영.
       tag: 조정='2'/불량='1'(조회에서 조정 etc열), 자체 SEQ 채번(당일 MAX+1). INSERT_WINDOW='stockmaint'로 웹행 식별(수정/삭제 매칭용)."""
    try:
        mtag = str(tag or '2').strip()[:1] or '2'
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
        msq = int(cur.fetchone()[0] or 1)
        cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT
              (MAINT_YMD,MAINT_SEQ,MAINT_TAG,PART_CODE,MAT_CODE,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,
               INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW)
              VALUES(?,?,?,?,?,?,?,?,?,?,'web',GETDATE(),'stockmaint')""",
            ymd, msq, mtag, (part or None), mat, (item or None), qty, cost, amt, (rem or None))
    except Exception: pass
def _prd_mirror_del(cur, ymd, part, mat, tag, qty):
    """생산파트조정 수정/삭제 시 대응 미러행(웹생성) 제거 — 시그니처 매칭 TOP 1."""
    try:
        mtag = str(tag or '2').strip()[:1] or '2'
        cur.execute("""SELECT TOP 1 MAINT_YMD,MAINT_SEQ FROM nx.PR_T_STOCK_MAINT_MAT
              WHERE MAINT_YMD=? AND MAT_CODE=? AND ISNULL(PART_CODE,'')=? AND MAINT_TAG=? AND ABS(MAINT_QTY-?)<0.0001
                AND INSERT_WINDOW='stockmaint' ORDER BY MAINT_SEQ DESC""", ymd, mat, (part or ''), mtag, qty)
        h = cur.fetchone()
        if h: cur.execute("DELETE FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ=?", h[0], h[1])
    except Exception: pass

@router.post("/api/stockmaint/save")
def stockmaint_save(payload: dict = Body(...)):
    p = payload
    ymd = _d6(str(p.get("maint_ymd", "")))
    mat = str(p.get("mat_code", "")).strip()[:20]
    if not ymd or not mat:
        raise HTTPException(400, "조정일자·자재코드는 필수입니다.")
    ui_tag = (str(p.get("maint_tag", "2")).strip() or "2")[:1]
    led_tag = _SM_UI2LED.get(ui_tag, ui_tag)
    work = str(p.get("work_code", "")).strip()[:10]
    part = str(p.get("part_code", "")).strip()[:10]
    item = str(p.get("item_code", "")).strip()[:20]
    qty = float(p.get("maint_qty") or 0)
    cost = float(p.get("maint_cost") or 0)
    amt = round(qty * cost, 2)
    rem = str(p.get("remarks", "")).strip()[:255]
    pwc = str(p.get("prod_work_code", "")).strip()[:10]
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    if qty == 0:
        raise HTTPException(400, "조정수량은 0일 수 없습니다(증가 +, 감소 −).")
    mid = p.get("id")
    nx = _nx(); cur = nx.cursor()
    try:
        if _closed(cur, ymd):
            raise HTTPException(400, f"마감월({_ym(ymd)}) 편집 불가")
        # ★파트는 반드시 코드여야 한다 — 표시명('04라인')이 들어가면 그 파트에 재고가
        #   쌓여 실제 파트(S4)에서 안 보인다(2026-08-25 실사고).
        if part:
            cur.execute("""SELECT TOP 1 GAGONG_PROC_CODE FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
                            WITH(NOLOCK) WHERE GAGONG_PROC_CODE=?""", part)
            if not cur.fetchone():
                cur.execute("""SELECT TOP 1 GAGONG_PROC_CODE FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
                                WITH(NOLOCK) WHERE ISNULL(GAGONG_PROC_DESC,'')=?""", part)
                _alt = cur.fetchone()
                raise HTTPException(400,
                    f"파트코드 '{part}' 가 없습니다."
                    + (f" 파트명 대신 코드 '{str(_alt[0]).strip()}' 를 선택하세요." if _alt
                       else " 파트 드롭다운에서 선택하세요."))
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
        seq = cur.fetchone()[0]   # 삭제 전 채번 → 수정 시 신규 SEQ(기존과 상이)
        if mid:  # 수정 = 기존행 삭제 후 신규(재키)
            try:
                oy, osq = str(mid).split("-"); osq = int(osq)
                if _closed(cur, oy):
                    raise HTTPException(400, f"마감월({_ym(oy)}) 편집 불가")
                # ★기존 미러행 제거용 옛값 읽기(삭제 전)
                cur.execute("SELECT ISNULL(GAGONG_PROC_CODE,''),ISNULL(MAT_CODE,''),ISNULL(MAINT_TAG,''),MAINT_QTY FROM nx.stock_ledger WHERE STOCK_POINT='PRD' AND MAINT_YMD=? AND MAINT_SEQ=?", oy, osq)
                _o = cur.fetchone()
                cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='PRD' AND MAINT_YMD=? AND MAINT_SEQ=?", oy, osq)
                if _o: _prd_mirror_del(cur, oy, str(_o[0]).strip(), str(_o[1]).strip(), str(_o[2]).strip(), float(_o[3] or 0))
            except (ValueError, AttributeError):
                pass
        cur.execute("""INSERT INTO nx.stock_ledger
            (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,GAGONG_PROC_CODE,WORK_CODE,TO_GAGONG_PROC_CODE,
             MAT_CODE,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('PRD',?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
            ymd, seq, led_tag, (part or None), (work or None), (pwc or None),
            mat, (item or None), qty, cost, amt, (rem or None), usr)
        # ★F-생산: 조회원천(PR_T_STOCK_MAINT_MAT)에도 반영 → 생산재고조회에 보이게
        _prd_mirror_ins(cur, ymd, part, mat, item, led_tag, qty, cost, amt, rem)
        return {"ok": True, "id": f"{ymd}-{seq}", "mode": ("update" if mid else "insert")}
    finally:
        nx.close()

@router.post("/api/stockmaint/delete")
def stockmaint_delete(payload: dict = Body(...)):
    ids = [str(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        dl = 0
        for x in ids:
            try:
                y, sq = x.split("-"); sq = int(sq)
            except ValueError:
                continue
            if _closed(cur, y):
                raise HTTPException(400, f"마감월({_ym(y)}) 삭제 불가")
            # ★삭제 전 옛값 읽어 조회원천 미러행도 제거
            cur.execute("SELECT ISNULL(GAGONG_PROC_CODE,''),ISNULL(MAT_CODE,''),ISNULL(MAINT_TAG,''),MAINT_QTY FROM nx.stock_ledger WHERE STOCK_POINT='PRD' AND MAINT_YMD=? AND MAINT_SEQ=?", y, sq)
            _o = cur.fetchone()
            cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='PRD' AND MAINT_YMD=? AND MAINT_SEQ=?", y, sq)
            dl += cur.rowcount
            if _o: _prd_mirror_del(cur, y, str(_o[0]).strip(), str(_o[1]).strip(), str(_o[2]).strip(), float(_o[3] or 0))
        return {"ok": True, "deleted": dl}
    finally:
        nx.close()


# ================= 260 공정별 생산실적등록 (w_pr_input_260, PR_T_PROD_DTL) — nx.proc_result =================
@router.get("/api/procreg/list")
def procreg_list(from_ymd: str = Query(""), to_ymd: str = Query(""), swork: str = Query(""),
                 line: str = Query(""), item: str = Query(""), wo: str = Query("")):
    # 공정별 생산실적 조회 = 웹(nx.proc_result, editable) ∪ 미러이력(nx.PR_T_PROD_DTL, 읽기전용). 레거시 라이브 없음(컷오버).
    nx = _nx(); cur = nx.cursor()
    try:
        rows = []
        # --- 웹행 (nx.proc_result, 편집가능) ---
        w = ["1=1"]; p = []
        if from_ymd: w.append("d.PROD_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("d.PROD_YMD<=?"); p.append(_d6(to_ymd))
        if swork.strip(): w.append("d.S_WORK_CODE=?"); p.append(int(swork.strip()))
        if line.strip():  w.append("d.LINE_NO=?"); p.append(line.strip())
        if item.strip():  w.append("d.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if wo.strip():    w.append("d.WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        cur.execute(f"""SELECT TOP 3000 d.ID, d.PROD_YMD, d.PROD_HMS, ISNULL(d.WORK_ORDER,'') wo,
              ISNULL(d.SPLIT_WORK_ORDER,'') swo, ISNULL(d.ITEM_CODE,'') item, ISNULL(ii.item_name,'') nm,
              ISNULL(d.LINE_NO,'') line, ISNULL(d.PART_CODE,'') part, d.S_WORK_CODE sw, d.PROD_QTY,
              ISNULL(d.WORK_CODE,'') work_code, ISNULL(d.FINISH_FLAG,'') fin, ISNULL(d.PROD_USER_ID,'') usr,
              d.INSERT_DATETIME
            FROM nx.proc_result d LEFT JOIN PARTNER_ERP_TEST3.nx.item ii ON ii.ITEM_CODE=d.ITEM_CODE
            WHERE {' AND '.join(w)} ORDER BY d.PROD_YMD DESC, d.PROD_HMS DESC, d.ID DESC""", *p)
        cols = [dd[0] for dd in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r)); d["src"] = "web"; d["editable"] = 1
            d["PROD_QTY"] = float(d["PROD_QTY"] or 0); d["sw"] = str(d["sw"] if d["sw"] is not None else "")
            d["INSERT_DATETIME"] = str(d["INSERT_DATETIME"] or "")[:19]
            rows.append(d)
        # --- 미러 이력행 (nx.PR_T_PROD_DTL, 읽기전용) ---
        wm = ["1=1"]; pm = []
        if from_ymd: wm.append("d.PROD_YMD>=?"); pm.append(_d6(from_ymd))
        if to_ymd:   wm.append("d.PROD_YMD<=?"); pm.append(_d6(to_ymd))
        if swork.strip(): wm.append("d.S_WORK_CODE=?"); pm.append(int(swork.strip()))
        if line.strip():  wm.append("d.LINE_NO=?"); pm.append(line.strip())
        if item.strip():  wm.append("d.ITEM_CODE LIKE ?"); pm.append(f"%{item.strip()}%")
        if wo.strip():    wm.append("d.WORK_ORDER LIKE ?"); pm.append(f"%{wo.strip()}%")
        cur.execute(f"""SELECT TOP 3000 d.PROD_YMD, d.PROD_HMS, ISNULL(d.WORK_ORDER,'') wo,
              ISNULL(d.SPLIT_WORK_ORDER,'') swo, ISNULL(d.ITEM_CODE,'') item, ISNULL(ii.item_name,'') nm,
              ISNULL(d.LINE_NO,'') line, ISNULL(d.PART_CODE,'') part, d.S_WORK_CODE sw, d.PROD_QTY,
              ISNULL(d.WORK_CODE,'') work_code, ISNULL(d.FINISH_FLAG,'') fin, ISNULL(d.PROD_USER_ID,'') usr
            FROM PARTNER_ERP_TEST3.nx.PR_T_PROD_DTL d LEFT JOIN PARTNER_ERP_TEST3.nx.item ii ON ii.ITEM_CODE=d.ITEM_CODE
            WHERE {' AND '.join(wm)} ORDER BY d.PROD_YMD DESC, d.PROD_HMS DESC""", *pm)
        cols = [dd[0] for dd in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r)); d["src"] = "legacy"; d["editable"] = 0; d["ID"] = None
            d["PROD_QTY"] = float(d["PROD_QTY"] or 0); d["sw"] = str(d["sw"] if d["sw"] is not None else "")
            d["INSERT_DATETIME"] = f'{str(d["PROD_YMD"] or "")} {str(d["PROD_HMS"] or "")}'.strip()
            rows.append(d)
        rows.sort(key=lambda r: (str(r["PROD_YMD"]), str(r["PROD_HMS"]), 1 if r["src"] == "web" else 0), reverse=True)
        return {"rows": rows, "cnt": len(rows), "sum_qty": sum(r["PROD_QTY"] for r in rows)}
    finally:
        nx.close()

@router.post("/api/procreg/save")
def procreg_save(payload: dict = Body(...)):
    from datetime import datetime as _dt
    p = payload
    ymd = _d6(str(p.get("prod_ymd", "")))
    item = str(p.get("item_code", "")).strip()[:20]
    if not ymd or not item:
        raise HTTPException(400, "실적일자·품번은 필수입니다.")
    hms = str(p.get("prod_hms", "")).strip()[:6] or _dt.now().strftime("%H%M%S")
    wo = str(p.get("work_order", "")).strip()[:20]
    swo = str(p.get("split_work_order", "")).strip()[:30]
    line = str(p.get("line_no", "")).strip()[:10]
    part = str(p.get("part_code", "")).strip()[:10]
    sw = p.get("s_work_code"); sw = int(sw) if str(sw).strip() not in ("", "None", "null") else 0
    qty = int(float(p.get("prod_qty") or 0))
    work = str(p.get("work_code", "")).strip()[:10]
    fin = (str(p.get("finish_flag", "0")).strip() or "0")[:1]
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    mid = p.get("id")
    nx = _nx(); cur = nx.cursor()
    try:
        # ★생산실적 재고 게이트 — 예외 없음(정본 STOCK_GATING_CLOSE_LOCK_RULES.md §0-★).
        #   이 화면은 종전에 게이트가 **아예 없었다**(nx.proc_result INSERT 만).
        #   실적을 잡는다 = 그 수량만큼 만들었다 = BOM 자재를 썼다 → 자재가 없으면 실적 불가.
        #   수정 시엔 **늘어난 수량분**만 판정한다(같은 실적을 두 번 요구하지 않기 위해).
        #   차단 시 사유(어느 자재가 얼마 부족한지·어디에 있는지)를 그대로 돌려준다.
        need_qty = qty
        if mid:
            cur.execute("SELECT CAST(ISNULL(PROD_QTY,0) AS float) FROM nx.proc_result WHERE ID=?", int(mid))
            _r = cur.fetchone()
            need_qty = max(0.0, qty - float(_r[0] or 0)) if _r else qty
        if need_qty > 0:
            _lm = _lock_msg(cur, ymd)                     # 마감 잠금도 함께(규칙 B)
            if _lm:
                raise HTTPException(409, _lm)
            # ★_is_inner_prod 로 대상을 거르지 않는다 — 그 함수는 라이브 커넥션에서
            #   nx.item 을 읽다 실패하면 **예외를 삼키고 False** 를 돌려주어(=게이트 스킵)
            #   또 하나의 숨은 예외가 된다(2026-08-28 하네스로 실측). §0-★ 규칙 A-0 위반.
            #   대신 BOM 을 전개해 **소비할 것이 있으면 무조건 판정**한다.
            #   BOM 이 비면 소비 자체가 없는 것이므로 게이트 대상이 아니다(예외가 아니라 해당 없음).
            from routers.backflush import _backflush_bom, _prod_shortages
            _comps, _weld = _backflush_bom(nx, item, nx)   # ★cro 도 nx — 라이브엔 nx 스키마가 없다
            _short = _prod_shortages(nx, _comps, _weld, need_qty)
            if _short:
                _more = f" 외 {len(_short)-8}건" if len(_short) > 8 else ""
                raise HTTPException(400, "자재부족으로 생산실적 등록 불가 — "
                                    + "; ".join(_short[:8]) + _more)
        if mid:
            cur.execute("""UPDATE nx.proc_result SET PROD_YMD=?, PROD_HMS=?, WORK_ORDER=?, SPLIT_WORK_ORDER=?,
                ITEM_CODE=?, LINE_NO=?, PART_CODE=?, S_WORK_CODE=?, PROD_QTY=?, WORK_CODE=?, FINISH_FLAG=?,
                PROD_USER_ID=?, UPDATE_USER_ID=?, UPDATE_DATETIME=getdate() WHERE ID=?""",
                ymd, hms, wo, swo, item, line, part, sw, qty, work, fin, usr, usr, int(mid))
            return {"ok": True, "id": int(mid), "mode": "update"}
        cur.execute("""INSERT INTO nx.proc_result(PROD_YMD,PROD_HMS,WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,
            LINE_NO,PART_CODE,S_WORK_CODE,PROD_QTY,WORK_CODE,FINISH_FLAG,PROD_USER_ID,UPDATE_USER_ID)
            OUTPUT INSERTED.ID VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ymd, hms, wo, swo, item, line, part, sw, qty, work, fin, usr, usr)
        nid = cur.fetchone()[0]
        return {"ok": True, "id": int(nid), "mode": "insert"}
    finally:
        nx.close()

@router.post("/api/procreg/delete")
def procreg_delete(payload: dict = Body(...)):
    ids = [int(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        ph = ",".join("?" * len(ids))
        cur.execute(f"DELETE FROM nx.proc_result WHERE ID IN ({ph})", *ids)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        nx.close()


# ================= 150 자재출고(창고간 출고이동) — ★Phase3 단일원장 fold: nx.stock_ledger(STOCK_POINT='MAT', MV) =================
# 파트창고간 이동 = MAT 이동(net 0). 그룹당 2행(−FROM/+TO, MAINT_GROUP_SEQ 링크, tag='MV').
# ★이중차감 경계(결정 I): 이동은 net-0 relocation → 자재소비 아님 → 백플러시(−MAT 소비)와 구조적으로 겹치지 않음.
#   생산소비는 백플러시(Phase2)가 담당하며 이 화면은 소비 경로가 아님. ID = "YMD-GROUP".
@router.get("/api/matissue/list")
def matissue_list(from_ymd: str = Query(""), to_ymd: str = Query(""), mat: str = Query(""),
                  frompart: str = Query(""), topart: str = Query("")):
    # 자재출고(창고이동) 조회 = 웹(nx.stock_ledger MAT/MV, editable) ∪ 미러이력(PR_T_STOCK_MAINT_MAT 창고이동, 읽기전용). 레거시 라이브 없음.
    nx = _nx(); cur = nx.cursor()
    try:
        rows = []
        # --- 웹행 (nx.stock_ledger MAT/MV −출고행, 편집가능) ---
        w = ["l.STOCK_POINT='MAT'", "l.MAINT_TAG='MV'", "l.MAINT_QTY<0", "l.MAINT_GROUP_SEQ IS NOT NULL"]; p = []
        if from_ymd: w.append("l.MAINT_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("l.MAINT_YMD<=?"); p.append(_d6(to_ymd))
        if mat.strip():  w.append("(l.MAT_CODE LIKE ? OR l.ITEM_CODE LIKE ?)"); p += [f"%{mat.strip()}%"]*2
        if frompart.strip(): w.append("l.GAGONG_PROC_CODE=?"); p.append(frompart.strip())
        if topart.strip():   w.append("l.TO_GAGONG_PROC_CODE=?"); p.append(topart.strip())
        cur.execute(f"""SELECT TOP 3000 l.MAINT_YMD ISSUE_YMD, l.MAINT_GROUP_SEQ,
              ISNULL(l.GAGONG_PROC_CODE,'') frompart, ISNULL(l.TO_GAGONG_PROC_CODE,'') topart,
              ISNULL(l.WORK_CODE,'') work_code, ISNULL(l.MAT_CODE,'') mat_code, ISNULL(im.item_name,'') mat_nm,
              ISNULL(l.ITEM_CODE,'') item_code, ABS(l.MAINT_QTY) ISSUE_QTY, ISNULL(l.REMARKS,'') remarks,
              ISNULL(l.INSERT_USER_ID,'') usr, l.INSERT_DATETIME
            FROM nx.stock_ledger l LEFT JOIN PARTNER_ERP_TEST3.nx.item im ON im.ITEM_CODE=l.MAT_CODE
            WHERE {' AND '.join(w)} ORDER BY l.MAINT_YMD DESC, l.MAINT_GROUP_SEQ DESC""", *p)
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r)); d["src"] = "web"; d["editable"] = 1
            d["ID"] = f'{d["ISSUE_YMD"]}-{d["MAINT_GROUP_SEQ"]}'
            d["ISSUE_QTY"] = float(d["ISSUE_QTY"] or 0); d["INSERT_DATETIME"] = str(d["INSERT_DATETIME"] or "")[:19]
            rows.append(d)
        # --- 미러 이력행 (PR_T_STOCK_MAINT_MAT 창고이동=FROM_PART_CODE≠PART_CODE, 읽기전용) ---
        wm = ["ISNULL(m.FROM_PART_CODE,'')>''", "m.FROM_PART_CODE<>m.PART_CODE"]; pm = []
        if from_ymd: wm.append("m.MAINT_YMD>=?"); pm.append(_d6(from_ymd))
        if to_ymd:   wm.append("m.MAINT_YMD<=?"); pm.append(_d6(to_ymd))
        if mat.strip():  wm.append("(m.MAT_CODE LIKE ? OR m.ITEM_CODE LIKE ?)"); pm += [f"%{mat.strip()}%"]*2
        if frompart.strip(): wm.append("m.FROM_PART_CODE=?"); pm.append(frompart.strip())
        if topart.strip():   wm.append("m.PART_CODE=?"); pm.append(topart.strip())
        cur.execute(f"""SELECT TOP 3000 m.MAINT_YMD ISSUE_YMD, m.MAINT_SEQ,
              ISNULL(m.FROM_PART_CODE,'') frompart, ISNULL(m.PART_CODE,'') topart,
              ISNULL(m.WORK_CODE,'') work_code, ISNULL(m.MAT_CODE,'') mat_code, ISNULL(im.item_name,'') mat_nm,
              ISNULL(m.ITEM_CODE,'') item_code, ABS(m.MAINT_QTY) ISSUE_QTY, ISNULL(m.REMARKS,'') remarks,
              ISNULL(m.INSERT_USER_ID,'') usr, m.INSERT_DATETIME
            FROM PARTNER_ERP_TEST3.nx.PR_T_STOCK_MAINT_MAT m LEFT JOIN PARTNER_ERP_TEST3.nx.item im ON im.ITEM_CODE=m.MAT_CODE
            WHERE {' AND '.join(wm)} ORDER BY m.MAINT_YMD DESC, m.MAINT_SEQ DESC""", *pm)
        cols = [d[0] for d in cur.description]
        for r in cur.fetchall():
            d = dict(zip(cols, r)); d["src"] = "legacy"; d["editable"] = 0; d["ID"] = None
            d["ISSUE_QTY"] = float(d["ISSUE_QTY"] or 0); d["INSERT_DATETIME"] = str(d["INSERT_DATETIME"] or "")[:19]
            rows.append(d)
        rows.sort(key=lambda r: (str(r["ISSUE_YMD"]), 1 if r["src"] == "web" else 0), reverse=True)
        return {"rows": rows, "cnt": len(rows), "sum_qty": sum(r["ISSUE_QTY"] for r in rows)}
    finally:
        nx.close()

@router.post("/api/matissue/save")
def matissue_save(payload: dict = Body(...)):
    p = payload
    ymd = _d6(str(p.get("issue_ymd", "")))
    mat = str(p.get("mat_code", "")).strip()[:20]
    if not ymd or not mat:
        raise HTTPException(400, "출고일자·자재코드는 필수입니다.")
    frompart = str(p.get("from_part_code", "")).strip()[:10]
    topart = str(p.get("part_code", "")).strip()[:10]
    work = str(p.get("work_code", "")).strip()[:10]
    item = str(p.get("item_code", "")).strip()[:20]
    qty = float(p.get("issue_qty") or 0)
    rem = str(p.get("remarks", "")).strip()[:255]
    usr = (str(p.get("user", "")).strip() or "웹사용자")[:30]
    mid = p.get("id")
    if qty <= 0:
        raise HTTPException(400, "출고수량은 0보다 커야 합니다.")
    if not frompart or not topart:
        raise HTTPException(400, "FROM파트·TO파트는 필수입니다(창고간 이동).")
    if frompart == topart:
        raise HTTPException(400, "FROM파트와 TO파트가 같습니다.")
    nx = _nx_tx(); cur = nx.cursor()   # ★원자성: MV 이동 2행(±) 그룹 트랜잭션
    try:
        if _closed(cur, ymd):
            raise HTTPException(400, f"마감월({_ym(ymd)}) 편집 불가")
        cur.execute("SELECT ISNULL(MAX(MAINT_GROUP_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_TAG='MV'")
        gseq = cur.fetchone()[0]   # 삭제 전 채번 → 수정 시 신규 그룹번호(기존과 상이)
        if mid:  # 수정 = 기존 그룹(2행) 삭제 후 재생성
            try:
                oy, og = str(mid).split("-"); og = int(og)
                if _closed(cur, oy):
                    raise HTTPException(400, f"마감월({_ym(oy)}) 편집 불가")
                cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND MAINT_TAG='MV' AND MAINT_YMD=? AND MAINT_GROUP_SEQ=?", oy, og)
            except (ValueError, AttributeError):
                pass
        # FROM파트 가용재고 이내(음수재고 방지). 현재고 = 원장 SUM(MAT·해당 파트).
        cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger
            WHERE STOCK_POINT='MAT' AND MAT_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", mat, frompart)
        avail = float(cur.fetchone()[0] or 0)
        if qty > avail:
            raise HTTPException(400, f"FROM파트 재고부족 ({mat}@{frompart} 가용 {avail:g} < 이동 {qty:g})")
        for gpc, to_gpc, sq in ((frompart, topart, -qty), (topart, frompart, qty)):  # −FROM, +TO
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
            seq = cur.fetchone()[0]
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,
                 WORK_CODE,MAT_CODE,ITEM_CODE,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?,?, 'MV', ?,?,?,?,?,?,?,?,GETDATE())""",
                ymd, seq, gseq, gpc, to_gpc, (work or None), mat, (item or None), sq, (rem or None), usr)
        nx.commit()   # ★2행(−FROM/+TO) 원자 커밋
        return {"ok": True, "id": f"{ymd}-{gseq}", "mode": ("update" if mid else "insert")}
    except Exception:
        nx.rollback(); raise   # 부분실패 시 net-0 불변식 보존(전체 롤백)
    finally:
        nx.close()

@router.post("/api/matissue/delete")
def matissue_delete(payload: dict = Body(...)):
    ids = [str(x) for x in (payload.get("ids", []) or []) if str(x).strip()]
    if not ids:
        return {"ok": True, "deleted": 0}
    nx = _nx(); cur = nx.cursor()
    try:
        dl = 0
        for x in ids:
            try:
                y, g = x.split("-"); g = int(g)
            except ValueError:
                continue
            if _closed(cur, y):
                raise HTTPException(400, f"마감월({_ym(y)}) 삭제 불가")
            cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND MAINT_TAG='MV' AND MAINT_YMD=? AND MAINT_GROUP_SEQ=?", y, g)
            dl += cur.rowcount
        return {"ok": True, "deleted": dl}
    finally:
        nx.close()
