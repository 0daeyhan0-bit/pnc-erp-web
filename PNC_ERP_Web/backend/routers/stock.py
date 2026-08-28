# -*- coding: utf-8 -*-
"""stock 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _mat_avail, _assert_open, _lock_msg, _closed, stock_changed)

router = APIRouter()

# ===================== 자재 재고 (nx.stock_ledger 통합원장) =====================
# 조정/입고/출고 3화면 = 동일 원장, MAINT_TAG 프리셋으로 구분. 출고는 음수저장(양수표시).
STOCK_SCREENS = {
    "adjust":  {"name": "자재개별재고조정", "tags": ["1", "2", "3", "A"], "sign": 0},   # ± 조정
    "receipt": {"name": "자재입고관리",     "tags": ["9", "S", "C", "G", "H"], "sign": 1},  # + 입고
    "issue":   {"name": "자재출고관리",     "tags": ["4"], "sign": -1},                 # - 출고(양수표시)
    "return":  {"name": "자재반품",         "tags": ["RT"], "sign": -1},               # - 반품(≤현재고 가드, 다음공정 이동분은 이미 재고감소=반품불가)
}

def _ym(ymd):  # MAINT_YMD(YYMMDD/YYYYMMDD) → 마감월 YYMM
    y = str(ymd or "").strip()
    return y[:4] if len(y) >= 6 else ""

@router.get("/api/stock/list")
def stock_list(screen: str = Query("adjust"), ymd_from: str = Query(...), ymd_to: str = Query(...),
               q: str = Query(""), cust: str = Query(""), cust_code: str = Query("")):
    """q=자도번(품번) / cust=매입처(코드 또는 거래처명, LIKE) / cust_code=확정된 거래처코드(정확일치).
    2026-08-23 매입처 조건 분리. 화면에서 이름을 정확히 골랐거나 코드를 친 경우 cust_code 가 와서
    그 거래처 한 곳만 조회된다('그린산업' 입력 시 '그린산업(주)김해공장'까지 딸려오던 문제)."""
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    cn = _nx(); cur = cn.cursor()
    try:
        tags = "','".join(sc["tags"])
        like = f"%{q.strip()}%"
        # 매입처 = 코드확정(cust_code)이면 그 거래처만, 아니면 코드/이름 LIKE(빈값이면 조건 무시)
        ccode = cust_code.strip()
        cs = '' if ccode else cust.strip()
        clike = f"%{cs}%"
        sign = "-1" if sc["sign"] == -1 else "1"
        cur.execute(f"""
            SELECT TOP 500 l.MAINT_YMD, l.MAINT_SEQ, l.MAINT_TAG, tg.name AS tag_name,
                   l.CUST_CODE, pc.CUST_DESC AS cust_name, l.GAGONG_PROC_CODE,
                   l.MAT_CODE, i.item_name, i.item_spec, l.ITEM_CODE,
                   (l.MAINT_QTY * {sign}) AS qty, l.MAINT_COST, l.MAINT_AMT, l.REMARKS,
                   l.SHEET_NO, l.INSP_FLAG, l.WORK_CODE, l.TO_GAGONG_PROC_CODE, l.OUT_WH_GUBUN,
                   l.INSERT_USER_ID, l.INSERT_DATETIME
            FROM nx.stock_ledger l
            LEFT JOIN nx.item i ON i.item_code = l.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST pc ON pc.CUST_CODE = l.CUST_CODE
            LEFT JOIN nx.stock_tag tg ON tg.tag = l.MAINT_TAG
            WHERE l.STOCK_POINT='MAT' AND l.MAINT_YMD BETWEEN ? AND ? AND l.MAINT_TAG IN ('{tags}')
              AND (? = '%%' OR l.MAT_CODE LIKE ? OR l.CUST_CODE LIKE ?)
              AND (? = '' OR l.CUST_CODE = ?)
              AND (? = '' OR l.CUST_CODE LIKE ? OR pc.CUST_DESC LIKE ?)
            ORDER BY l.MAINT_YMD DESC, l.MAINT_SEQ DESC""",
            ymd_from.strip(), ymd_to.strip(), like, like, like, ccode, ccode, cs, clike, clike)
        cols = [d[0] for d in cur.description]
        rows = [{c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        return {"screen": screen, "name": sc["name"], "sign": sc["sign"], "rows": rows}
    finally:
        cn.close()

@router.post("/api/stock/save")
def stock_save(payload: dict = Body(...)):
    """재고원장 저장(신규행 insert). 가드: 마감월 잠금·FK·출고 재고부족(음수방지)."""
    screen = str(payload.get("screen", "")).strip()
    rows = payload.get("rows", []) or []
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    cn = _nx(); cur = cn.cursor()
    try:
        # 마감월 집합
        cur.execute("SELECT ym FROM nx.stock_close WHERE close_flag=1")
        closed = {str(r[0]).strip() for r in cur.fetchall()}   # ym=char(6) 패딩 제거(_ym은 4자 → 집합비교 일치)
        errs = []
        for idx, r in enumerate(rows, 1):
            ymd = str(r.get("MAINT_YMD", "")).strip()
            mat = str(r.get("MAT_CODE", "")).strip()
            qty = float(r.get("qty") or 0)
            if not ymd or len(ymd) < 6:
                errs.append(f"{idx}행: 일자 필요"); continue
            # ★마감잠금 = 공용 게이트(nx.period_close: 일마감+월마감+도메인). 구 nx.stock_close 는 폴백으로 유지.
            _lm = _lock_msg(cur, ymd, "MAT")
            if _lm:
                errs.append(f"{idx}행: {_lm}")
            elif _ym(ymd) in closed:
                errs.append(f"{idx}행: 마감월({_ym(ymd)}) 편집 불가")
            if not mat:
                errs.append(f"{idx}행: 자도번 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", mat)
            if not cur.fetchone():
                errs.append(f"{idx}행: 미등록 품목({mat})")
            # 조정=부호입력 허용(불량·개발불출 −, 장부수정 ±), 그 외=양수만
            if screen == "adjust":
                if qty == 0:
                    errs.append(f"{idx}행: 조정수량은 0일 수 없습니다(증가 +, 감소 −)")
            elif qty <= 0:
                errs.append(f"{idx}행: 수량은 0보다 커야 함")
            # 재고 음수방지: 출고·반품(가용 이내) / 조정 감소(결과재고 ≥ 0). 현재고=원장 SUM.
            if mat and screen in ("issue", "return"):
                avail = _mat_avail(cur, mat)   # ★정본=mat_stock_daily(레거시 실재고). nx.stock_ledger(미동기화·테스트오염) 금지 §4-C
                if qty > avail:
                    lbl = "반품" if screen == "return" else "출고"
                    errs.append(f"{idx}행: 재고부족 ({mat} 가용 {avail:g} < {lbl} {qty:g}) — 다음공정 이동분은 반품 불가")
            elif mat and screen == "adjust" and qty < 0:
                avail = _mat_avail(cur, mat)   # ★정본=mat_stock_daily(레거시 실재고). nx.stock_ledger(미동기화·테스트오염) 금지 §4-C
                if avail + qty < 0:
                    errs.append(f"{idx}행: 음수재고 유발 ({mat} 결과재고 {avail+qty:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        # insert (일자별 SEQ 채번, 출고 음수 저장)
        saved = 0
        for r in rows:
            ymd = str(r.get("MAINT_YMD", "")).strip()
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
            seq = cur.fetchone()[0]
            tag = str(r.get("MAINT_TAG") or sc["tags"][0]).strip()
            qty = float(r.get("qty") or 0)
            store_qty = -abs(qty) if sc["sign"] == -1 else qty
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,OUT_WH_GUBUN,
                 MAT_CODE,ITEM_CODE,WORK_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,SHEET_NO,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                ymd, seq, tag, (r.get("CUST_CODE") or None), (r.get("GAGONG_PROC_CODE") or None),
                (r.get("TO_GAGONG_PROC_CODE") or None), (r.get("OUT_WH_GUBUN") or None),
                str(r.get("MAT_CODE", "")).strip(), (r.get("ITEM_CODE") or None), (r.get("WORK_CODE") or None),
                store_qty, float(r.get("MAINT_COST") or 0), float(r.get("MAINT_AMT") or 0),
                (r.get("REMARKS") or None), (r.get("SHEET_NO") or None), "web")
            # ★자재창고 재고에도 반영(2026-08-20) — 레거시와 같은 구조.
            #   기존엔 nx.stock_ledger 에만 쌓여서 화면마다 반영이 갈렸음:
            #     준비등록 팝업 = 스냅샷 + stock_ledger 합산 → 조정분 보임
            #     자재입출고현황 = pu_t_stock_maint 만 조회   → 조정분 안 보임
            #   → 조정/입고/출고 시 nx.PU_T_MAT_STOCK_WH 잔액도 함께 증감시켜
            #     모든 화면이 같은 값을 보게 한다. (원장은 이력용으로 그대로 유지)
            #   ※버킷 키 = (MAT_CODE, CUST_CODE, GAGONG_PROC_CODE).
            #     자재창고 기본 버킷은 CUST_CODE='Z99990' · GAGONG_PROC_CODE='IS0001'
            #     (준비등록 setcheck 가 읽는 버킷과 동일해야 값이 맞음 — ready.py line 101)
            _mc = str(r.get("MAT_CODE", "")).strip()
            _cc = (str(r.get("CUST_CODE") or "").strip() or "Z99990")
            _gp = (str(r.get("GAGONG_PROC_CODE") or "").strip() or "IS0001")
            try:
                cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                  UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='stockadjust'
                                WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                            store_qty, _mc, _cc, _gp)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                                      UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                    VALUES(?,?,?,?,'web',GETDATE(),'stockadjust')""",
                                _mc, _cc, _gp, store_qty)
            except Exception: pass   # 재고 반영 실패해도 원장 기록은 유지(이력 우선)
            # ★자재 입출고이력에도 기록(2026-08-20) — 레거시 w_pu_stock_016 과 동일 형태.
            #   자재입출고현황·자재수불장 등은 nx.PU_T_STOCK_MAINT 를 읽으므로 여기 없으면
            #   잔액은 맞는데 "입출고 내역"에는 안 잡힌다.
            #   ★WH_CUST_CODE·GAGONG_PROC_CODE 필수 — 공백이면 창고 필터에서 빠져 조회 누락됨.
            try:
                cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
                _sq = int(cur.fetchone()[0] or 1)
                cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                        (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                         WH_CUST_CODE,GAGONG_PROC_CODE,
                         INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                         UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES(?,?,?,?,?,?,?,?,?,'web',GETDATE(),'stockadjust','web',GETDATE(),'stockadjust')""",
                    ymd, _sq, ("T" if tag == "RT" else tag), _cc, _mc, store_qty, (r.get("REMARKS") or None), _cc, _gp)
                    # ★F2: MAINT_TAG=CHAR(1) → 반품 'RT'(2글자) 잘림오류로 수불장 누락됐음 → 'T'(자재창고반품) 매핑
            except Exception: pass
            saved += 1
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "count": saved}
    finally:
        cn.close()

@router.get("/api/stock/kanban")
def stock_kanban(q: str = Query("")):
    """자재입고진행현황(읽기전용 집계): 품목별 현재고=원장 SUM. 계획대비는 추후 확장."""
    cn = _nx(); cur = cn.cursor()
    try:
        like = f"%{q.strip()}%"
        cur.execute("""
            SELECT TOP 300 l.MAT_CODE, i.item_name, i.item_spec, MAX(l.GAGONG_PROC_CODE) AS part,
                   SUM(l.MAINT_QTY) AS stock_qty,
                   SUM(CASE WHEN l.MAINT_QTY>0 THEN l.MAINT_QTY ELSE 0 END) AS in_qty,
                   SUM(CASE WHEN l.MAINT_QTY<0 THEN -l.MAINT_QTY ELSE 0 END) AS out_qty
            FROM nx.stock_ledger l LEFT JOIN nx.item i ON i.item_code=l.MAT_CODE
            WHERE l.STOCK_POINT='MAT' AND (? = '%%' OR l.MAT_CODE LIKE ?)
            GROUP BY l.MAT_CODE, i.item_name, i.item_spec
            HAVING SUM(l.MAINT_QTY) <> 0
            ORDER BY SUM(l.MAINT_QTY) DESC""", like, like)
        cols = [d[0] for d in cur.description]
        rows = [{c: v for c, v in zip(cols, r)} for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        cn.close()

# ============ 자재입고: 발주분 입고(057 개별일괄 / 057_1 PO바코드) — 발주잔량 차감·nx.stock_ledger 기록 ============
# 발주잔량 = 발주(PU_T_PURCHASE_DTL.PUR_QTY) − 레거시기입고(IN_QTY) − 취소(CANCEL_QTY) − nx웹입고(발주링크 SUM). [[nextgen-erp-ledger-consistency]] 원장파생.
@router.get("/api/matrecv/po_pending")
def matrecv_po_pending(cust: str = Query(""), item: str = Query(""), sheet: str = Query(""),
                       from_ymd: str = Query(""), to_ymd: str = Query("")):
    """발주분 입고대기(발주잔량>0). 개별일괄/PO바코드 공용. sheet=발주번호(PUR_SEQ, 바코드 PO뒤 숫자)."""
    C = " COLLATE DATABASE_DEFAULT"
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["(p.PUR_QTY - ISNULL(p.IN_QTY,0) - ISNULL(p.CANCEL_QTY,0)) > 0"]; pr = []
        if cust.strip(): w.append("p.CUST_CODE LIKE ?"); pr.append(f"%{cust.strip()}%")
        if item.strip(): w.append("p.ITEM_CODE LIKE ?"); pr.append(f"%{item.strip()}%")
        if sheet.strip(): w.append("p.PUR_SEQ=?"); pr.append(sheet.strip())
        if from_ymd.strip(): w.append("p.PUR_YMD>=?"); pr.append(_d6(from_ymd))
        if to_ymd.strip(): w.append("p.PUR_YMD<=?"); pr.append(_d6(to_ymd))
        cur.execute(f"""SELECT TOP 800 p.PUR_YMD, p.PUR_SEQ, p.PUR_SEQ_ROW, p.CUST_CODE, ISNULL(cu.CUST_DESC,'') cust_nm,
              p.ITEM_CODE, ISNULL(it.item_name,'') nm, ISNULL(it.item_spec,'') spec, ISNULL(it.unit,'') unit, p.DLVY_YMD,
              p.PUR_QTY, ISNULL(p.IN_QTY,0) in_qty, ISNULL(p.CANCEL_QTY,0) cancel_qty, ISNULL(nx.q,0) nx_in,
              ISNULL(p.PUR_COST,0) pur_cost, ISNULL(p.MAT_INSPECTION,'') insp,
              (p.PUR_QTY - ISNULL(p.IN_QTY,0) - ISNULL(p.CANCEL_QTY,0) - ISNULL(nx.q,0)) remain
            FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL p
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cu ON cu.CUST_CODE=p.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.item it ON it.item_code=p.ITEM_CODE
            LEFT JOIN (SELECT PUR_YMD,PUR_SEQ,PUR_SEQ_ROW,SUM(MAINT_QTY) q FROM nx.stock_ledger
                       WHERE MAINT_TAG='9' AND ISNULL(PUR_YMD,'')<>'' GROUP BY PUR_YMD,PUR_SEQ,PUR_SEQ_ROW) nx
              ON nx.PUR_YMD{C}=p.PUR_YMD{C} AND nx.PUR_SEQ{C}=p.PUR_SEQ{C} AND nx.PUR_SEQ_ROW=p.PUR_SEQ_ROW
            WHERE {' AND '.join(w)}
            ORDER BY p.PUR_YMD DESC, p.PUR_SEQ, p.PUR_SEQ_ROW""", *pr)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["remain"] = float(d["remain"] or 0)
            if d["remain"] <= 0:  # nx입고로 이미 충족분 제외
                continue
            for k in ("PUR_QTY", "in_qty", "cancel_qty", "nx_in", "pur_cost"):
                d[k] = float(d[k] or 0)
            d["DLVY_YMD"] = str(d["DLVY_YMD"] or "")
            rows.append(d)
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/matrecv/receive")
def matrecv_receive(payload: dict = Body(...)):
    """발주분 입고 확정 → nx.stock_ledger(MAINT_TAG='9', 발주링크). 마감월/미등록품목/발주잔량초과 가드.
    입고수량이 발주잔량 초과시 차단. 삭제는 /api/stock/delete(원장행 제거=역진행)."""
    ymd = str(payload.get("ymd") or "").strip()      # 입고일자 YYMMDD
    wh = str(payload.get("wh") or "IS0001").strip()   # 입고창고(gagong_proc_code)
    rows = payload.get("rows", []) or []
    if not ymd or len(ymd) < 6:
        raise HTTPException(400, "입고일자 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        if _closed(cur, ymd, "MAT"):
            return {"ok": False, "errors": [f"마감월({_ym(ymd)}) 입고 불가"]}
        errs = []
        # 검증: 품목등록·발주잔량 초과
        for idx, r in enumerate(rows, 1):
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            py = str(r.get("pur_ymd", "")).strip(); ps = str(r.get("pur_seq", "")).strip(); prw = r.get("pur_seq_row")
            if qty <= 0: errs.append(f"{idx}행: 입고수량>0 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", item)
            if not cur.fetchone(): errs.append(f"{idx}행: 미등록품목({item})")
            if py and ps and prw is not None:  # 발주잔량 초과 가드
                cur.execute("""SELECT (p.PUR_QTY-ISNULL(p.IN_QTY,0)-ISNULL(p.CANCEL_QTY,0)
                    -ISNULL((SELECT SUM(MAINT_QTY) FROM nx.stock_ledger WHERE MAINT_TAG='9' AND PUR_YMD=? AND PUR_SEQ=? AND PUR_SEQ_ROW=?),0))
                    FROM PARTNER_ERP_TEST3.nx.PU_T_PURCHASE_DTL p WHERE p.PUR_YMD=? AND p.PUR_SEQ=? AND p.PUR_SEQ_ROW=?""",
                    py, ps, int(prw), py, ps, int(prw))
                rem = cur.fetchone()
                remain = float(rem[0]) if rem and rem[0] is not None else None
                if remain is not None and qty > remain + 0.001:
                    errs.append(f"{idx}행: 발주잔량 초과({item} 잔량 {remain:g} < 입고 {qty:g})")
        if errs:
            return {"ok": False, "errors": errs}
        saved = 0
        for r in rows:
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            if qty <= 0: continue
            cost = float(r.get("cost") or 0); vat = float(r.get("vat") or round(qty * cost * 0.1))
            py = (str(r.get("pur_ymd", "")).strip() or None); ps = (str(r.get("pur_seq", "")).strip() or None)
            prw = r.get("pur_seq_row")
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
            seq = cur.fetchone()[0]
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,MAINT_VAT,
                 PUR_YMD,PUR_SEQ,PUR_SEQ_ROW,INSP_FLAG,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?, '9',?,?,?,?,?,?,?, ?,?,?,?,?, ?, GETDATE())""",
                ymd, seq, (r.get("cust") or None), wh, item, qty, cost, round(qty * cost), vat,
                py, ps, (int(prw) if prw is not None else None), (r.get("insp") or None),
                (r.get("remarks") or "발주입고"), "web")
            saved += 1
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "count": saved}
    finally:
        cn.close()

# ============ 자재입고: 가공이동전표 입고(057_2 바코드) — PU_T_STOCK_MAINT_GAGONG_MOVE → nx.stock_ledger(tag C) ============
@router.get("/api/matrecv/gagong_pending")
def matrecv_gagong_pending(sheet: str = Query(""), item: str = Query("")):
    """가공이동전표 미입고분. sheet=바코드(MV+MAINT_GROUP_SEQ). 미입고=IN_CONFIRM_FLAG≠1 & nx웹입고 미충족."""
    C = " COLLATE DATABASE_DEFAULT"
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["ISNULL(g.IN_CONFIRM_FLAG,'0')<>'1'"]; pr = []
        if sheet.strip():
            gs = "".join(ch for ch in sheet.strip() if ch.isdigit())
            w.append("g.MAINT_GROUP_SEQ=?"); pr.append(int(gs) if gs else -1)
        if item.strip(): w.append("g.MAT_CODE LIKE ?"); pr.append(f"%{item.strip()}%")
        cur.execute(f"""SELECT TOP 500 g.MAINT_GROUP_SEQ, g.MAT_CODE, ISNULL(it.item_name,'') nm, ISNULL(it.item_spec,'') spec,
              ISNULL(it.unit,'') unit, g.ITEM_CODE upper_code, g.MAINT_QTY, g.GAGONG_PROC_CODE, g.TO_GAGONG_PROC_CODE,
              g.MAINT_YMD, ISNULL(nx.q,0) nx_in
            FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE g
            LEFT JOIN PARTNER_ERP_TEST3.nx.item it ON it.item_code{C}=g.MAT_CODE{C}
            LEFT JOIN (SELECT MAINT_GROUP_SEQ, SUM(MAINT_QTY) q FROM nx.stock_ledger WHERE MAINT_TAG='C' AND MAINT_GROUP_SEQ IS NOT NULL GROUP BY MAINT_GROUP_SEQ) nx
              ON nx.MAINT_GROUP_SEQ=g.MAINT_GROUP_SEQ
            WHERE {' AND '.join(w)}
            ORDER BY g.MAINT_YMD DESC, g.MAINT_GROUP_SEQ DESC""", *pr)
        cols = [d[0] for d in cur.description]; rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["MAINT_QTY"] = float(d["MAINT_QTY"] or 0); d["nx_in"] = float(d["nx_in"] or 0)
            d["remain"] = d["MAINT_QTY"] - d["nx_in"]
            d["MAINT_YMD"] = str(d["MAINT_YMD"] or "")
            if d["remain"] <= 0: continue
            rows.append(d)
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.post("/api/matrecv/gagong_receive")
def matrecv_gagong_receive(payload: dict = Body(...)):
    """가공이동전표 입고 확정 → nx.stock_ledger(MAINT_TAG='C', MAINT_GROUP_SEQ 링크, 입고창고=TO_GAGONG_PROC_CODE). 마감 가드."""
    ymd = str(payload.get("ymd") or "").strip()
    rows = payload.get("rows", []) or []
    if not ymd or len(ymd) < 6:
        raise HTTPException(400, "입고일자 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        if _closed(cur, ymd, "MAT"):
            return {"ok": False, "errors": [f"마감월({_ym(ymd)}) 입고 불가"]}
        errs = []; saved = 0
        for idx, r in enumerate(rows, 1):
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            if qty <= 0: errs.append(f"{idx}행: 입고수량>0 필요"); continue
            cur.execute("SELECT 1 FROM nx.item WHERE item_code=?", item)
            if not cur.fetchone(): errs.append(f"{idx}행: 미등록품목({item})")
        if errs:
            return {"ok": False, "errors": errs}
        for r in rows:
            item = str(r.get("item", "")).strip(); qty = float(r.get("qty") or 0)
            if qty <= 0: continue
            gseq = r.get("group_seq"); wh = str(r.get("to_gagong") or r.get("wh") or "IS0001").strip()
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
            seq = cur.fetchone()[0]
            cur.execute("""INSERT INTO nx.stock_ledger
                (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,GAGONG_PROC_CODE,TO_GAGONG_PROC_CODE,MAT_CODE,ITEM_CODE,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES('MAT',?,?,?, 'C', ?,?,?,?,?, ?, ?, GETDATE())""",
                ymd, seq, (int(gseq) if gseq is not None else None), wh, (r.get("gagong") or None),
                item, (r.get("upper") or None), qty, (r.get("remarks") or "가공이동입고"), "web")
            saved += 1
        stock_changed("stock_save")           # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "count": saved}
    finally:
        cn.close()

# ★로컬 _closed 제거(2026-08-28) — 구 stock_close 만 보던 사본이 common 의 공용 게이트를 가렸다.
#   이제 common._closed(=_lock_msg 위임)를 그대로 쓴다.

# ===================== ★Phase5: nx 재고 월마감 스냅샷 (STOCK_POINT별 기초→기말=기초+ΣMAINT) =====================
# 기말 스냅샷=다음달 기초 연속성·마감후 파생 고정. 잠금=기존 nx.stock_close(ym) 플래그 재사용(옵션).
# ★사고 재발방지: stock_ledger 무삭제. 재계산은 자기생성 근거키(ym+point)의 stock_close_snap만 갱신.
@router.post("/api/stockclose/run")
def stockclose_run(payload: dict = Body(...)):
    """월마감 실행: (ym, point) 기말 스냅샷 산출·저장(set-based, 고속). 기초=단일원장 누적(<ym01, =직전월기말 동치). 기말=기초+입−출.
    lock=true면 nx.stock_close(ym) 잠금 플래그 set(기존 가드 발동=이전 원장 쓰기잠금). 멱등(같은 ym+point 재실행=재계산).
    ★사고 재발방지: stock_ledger 무삭제. 정리는 자기생성 근거키(ym+point)의 stock_close_snap만."""
    ym = str(payload.get("ym", "")).strip()
    point = str(payload.get("point", "")).strip().upper()
    lock = bool(payload.get("lock", False))
    user = (str(payload.get("user", "")).strip() or "web")[:30]
    if len(ym) != 4 or point not in ("MAT", "PRD", "ASY", "RDY", "SAG"):
        raise HTTPException(400, "ym=YYMM(4자)·point=MAT/PRD/ASY/RDY/SAG 필수")
    # ★C4(2026-08-27) 사용중단 — 마감관리(/api/close/*)로 일원화.
    #   MAT/PRD/ASY 는 새 마감이 정본이며, 이 API 는 (a)MAT 을 stock_ledger 로 계산해 45.88% 부정확
    #   (b)nx.stock_close 를 세워 새 잠금(nx.period_close)과 이중 잠금원이 된다 → 차단.
    #   RDY/SAG 는 아직 대체 스냅샷이 없어 스냅샷 산출만 남겨두되 잠금(lock)은 금지한다.
    if point in ("MAT", "PRD", "ASY"):
        raise HTTPException(410, f"사용중단된 API 입니다({point}) — 마감관리 /api/close/run 을 사용하세요"
                                 f" (domain MAT=자재 · PRD=생산 · SAL=영업).")
    if lock:
        raise HTTPException(400, "잠금(lock)은 마감관리 /api/close/run 으로 일원화되었습니다"
                                 " — 여기서는 스냅샷 산출만 가능합니다.")
    y01, y99 = ym + "01", ym + "99"
    cn = _nx(); cur = cn.cursor()
    try:
        # 자기생성 근거키(ym+point) 재계산분만 제거(멱등 — 이 마감의 스냅샷만)
        cur.execute("DELETE FROM nx.stock_close_snap WHERE ym=? AND stock_point=?", ym, point)
        # set-based: RTRIM 정규화 GROUP BY(후행공백 PK중복 방지), 기초=Σ(<y01)·입출=당월. 기말=기초+입−출.
        cur.execute("""INSERT INTO nx.stock_close_snap(ym,stock_point,item_key,gpc,cust,base_qty,in_qty,out_qty,end_qty,close_user,close_dt)
            SELECT ?, ?, LEFT(t.k,40), LEFT(t.g,20), LEFT(t.c,10), t.base, t.inq, t.outq, t.base+t.inq-t.outq, ?, GETDATE()
            FROM (
              SELECT COALESCE(NULLIF(RTRIM(L.MAT_CODE),''),RTRIM(L.ITEM_CODE)) k,
                     RTRIM(ISNULL(L.GAGONG_PROC_CODE,'')) g, RTRIM(ISNULL(L.CUST_CODE,'')) c,
                     SUM(CASE WHEN L.MAINT_YMD<? THEN L.MAINT_QTY ELSE 0 END) base,
                     SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY>0 THEN L.MAINT_QTY ELSE 0 END) inq,
                     SUM(CASE WHEN L.MAINT_YMD BETWEEN ? AND ? AND L.MAINT_QTY<0 THEN -L.MAINT_QTY ELSE 0 END) outq
              FROM nx.stock_ledger L WHERE L.STOCK_POINT=?
              GROUP BY COALESCE(NULLIF(RTRIM(L.MAT_CODE),''),RTRIM(L.ITEM_CODE)), RTRIM(ISNULL(L.GAGONG_PROC_CODE,'')), RTRIM(ISNULL(L.CUST_CODE,''))
            ) t
            WHERE (t.base<>0 OR t.inq<>0 OR t.outq<>0) AND t.k IS NOT NULL AND t.k<>''""",
            ym, point, user, y01, y01, y99, y01, y99, point)
        n = cur.rowcount
        if lock:  # 기존 nx.stock_close(ym) 플래그 재사용(신설 아님) — 이전 원장 쓰기잠금 발동
            cur.execute("IF EXISTS(SELECT 1 FROM nx.stock_close WHERE ym=?) UPDATE nx.stock_close SET close_flag=1,close_user=?,close_dt=GETDATE() WHERE ym=? ELSE INSERT INTO nx.stock_close(ym,close_flag,close_user,close_dt) VALUES(?,1,?,GETDATE())", ym, user, ym, ym, user)
        cur.execute("SELECT ISNULL(SUM(end_qty),0) FROM nx.stock_close_snap WHERE ym=? AND stock_point=?", ym, point)
        endsum = float(cur.fetchone()[0] or 0)
        stock_changed("stockclose")           # ★스냅샷 확정 → 수불장 캐시 버림
        return {"ok": True, "ym": ym, "point": point, "rows": n, "end_total": round(endsum, 3),
                "base_from": "단일원장 누적(<ym01 = 직전월기말 동치)", "locked": lock}
    finally:
        cn.close()

@router.get("/api/stockclose/status")
def stockclose_status(ym: str = Query(""), point: str = Query("")):
    """마감 현황: 스냅샷 요약(ym·point별 행수·기말합) + 잠금 플래그."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = []; p = []
        if ym.strip(): w.append("ym=?"); p.append(ym.strip())
        if point.strip(): w.append("stock_point=?"); p.append(point.strip().upper())
        wh = ("WHERE " + " AND ".join(w)) if w else ""
        cur.execute(f"""SELECT ym, stock_point, COUNT(*) rows, ISNULL(SUM(end_qty),0) end_total, MAX(close_dt) close_dt
            FROM nx.stock_close_snap {wh} GROUP BY ym, stock_point ORDER BY ym DESC, stock_point""", *p)
        snaps = [{"ym": r[0], "point": r[1], "rows": int(r[2]), "end_total": round(float(r[3] or 0), 3),
                  "close_dt": str(r[4] or "")[:19]} for r in cur.fetchall()]
        cur.execute("SELECT ym, close_flag, close_user, close_dt FROM nx.stock_close ORDER BY ym DESC")
        locks = [{"ym": str(r[0]).strip(), "locked": bool(r[1]), "user": r[2], "dt": str(r[3] or "")[:19]} for r in cur.fetchall()]
        return {"snapshots": snaps, "locks": locks}
    finally:
        cn.close()

def _mat_mirror_edit(cur, ymd, mat, cc, gp, tag, old_q, new_q, window):
    """★F1: 자재 원장(stock_ledger MAT) 수정/삭제 시 조회정본(자재재고 PU_T_MAT_STOCK_WH·자재수불장 PU_T_STOCK_MAINT)도 동반 반영.
       save는 3곳 반영하나 update/delete는 원장만 고쳐 수불장·재고가 stale(F1)였음. old_q→new_q(삭제=new_q=0).
       ★F2: PU_T_STOCK_MAINT.MAINT_TAG=CHAR(1) → 반품 'RT'(2글자)는 'T'(자재창고반품)로 매핑(truncation 방지)."""
    mat = str(mat or "").strip()
    if not mat: return
    cc = (str(cc or "").strip() or "Z99990")
    gp = (str(gp or "").strip() or "IS0001")
    mtag = "T" if str(tag).strip() == "RT" else (str(tag or "").strip()[:1] or "2")
    dq = new_q - old_q
    # 1) 자재재고 잔액(버킷=MAT_CODE·CUST_CODE·GAGONG_PROC_CODE) 델타 반영
    try:
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
              UPDATE_USER_ID='web',UPDATE_DATETIME=GETDATE(),UPDATE_WINDOW=?
              WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", dq, window, mat, cc, gp)
        if cur.rowcount == 0 and abs(dq) > 1e-9:
            cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                  UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW) VALUES(?,?,?,?,'web',GETDATE(),?)""", mat, cc, gp, dq, window)
    except Exception: pass
    # 2) 자재수불장: save가 남긴 web행(INSERT_WINDOW='stockadjust') 찾으면 in-place 수정/삭제, 못찾으면 보정행 insert
    try:
        cur.execute("""SELECT TOP 1 MAINT_YMD,MAINT_SEQ FROM nx.PU_T_STOCK_MAINT
              WHERE MAINT_YMD=? AND MAT_CODE=? AND ABS(MAINT_QTY-?)<0.0001 AND MAINT_TAG=?
                AND ISNULL(WH_CUST_CODE,'')=? AND ISNULL(GAGONG_PROC_CODE,'')=? AND INSERT_WINDOW='stockadjust'
              ORDER BY MAINT_SEQ DESC""", ymd, mat, old_q, mtag, cc, gp)
        hit = cur.fetchone()
        if hit and abs(new_q) < 1e-9:            # 삭제 → 그 web행 삭제(내역서 사라짐)
            cur.execute("DELETE FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ=?", hit[0], hit[1])
        elif hit:                                 # 수정 → 그 web행 수량 갱신
            cur.execute("""UPDATE nx.PU_T_STOCK_MAINT SET MAINT_QTY=?,UPDATE_USER_ID='web',UPDATE_DATETIME=GETDATE(),UPDATE_WINDOW=?
                  WHERE MAINT_YMD=? AND MAINT_SEQ=?""", new_q, window, hit[0], hit[1])
        elif abs(dq) > 1e-9:                       # 원본 못찾음 → 보정(델타)행 기록(잔액·수불합 정합 유지)
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
            nsq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                  WH_CUST_CODE,GAGONG_PROC_CODE,INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                  VALUES(?,?,?,?,?,?,?,?,?,'web',GETDATE(),?,'web',GETDATE(),?)""",
                ymd, nsq, mtag, cc, mat, dq, "원장수정보정", cc, gp, window, window)
    except Exception: pass

@router.post("/api/stock/update")
def stock_update(payload: dict = Body(...)):
    """기존 원장행 수정(값 필드만). 키(MAINT_YMD,MAINT_SEQ)·자도번 불변, 저장부호 보존.
    가드: 대상존재·마감월 잠금·수량>0·음수재고 유발 차단."""
    screen = str(payload.get("screen", "")).strip()
    sc = STOCK_SCREENS.get(screen)
    if not sc:
        raise HTTPException(400, "screen 오류")
    ymd = str(payload.get("MAINT_YMD", "")).strip()
    try:
        seq = int(payload.get("MAINT_SEQ"))
    except (TypeError, ValueError):
        raise HTTPException(400, "MAINT_SEQ 오류")
    qty = float(payload.get("qty") or 0)
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT MAT_CODE, MAINT_QTY, ISNULL(CUST_CODE,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(MAINT_TAG,'') FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        row = cur.fetchone()
        if not row:
            return {"ok": False, "errors": [f"대상 없음 ({ymd}/{seq})"]}
        mat = str(row[0] or "").strip()
        old_stored = float(row[1] or 0)
        old_cc = str(row[2] or "").strip(); old_gp = str(row[3] or "").strip(); old_tag = str(row[4] or "").strip()
        errs = []
        if _closed(cur, ymd, "MAT"):
            errs.append(f"마감월({_ym(ymd)}) 편집 불가")
        if screen == "adjust":
            # 조정=부호 그대로(불량·개발불출 −, 장부수정 ±). 음수재고는 아래 new_sum 검증에서 차단.
            if qty == 0:
                errs.append("조정수량은 0일 수 없습니다(증가 +, 감소 −)")
            new_stored = qty
        else:
            if qty <= 0:
                errs.append("수량은 0보다 커야 함")
            # 저장부호 보존(기존 음수→음수, 0이면 화면부호)
            neg = old_stored < 0 or (old_stored == 0 and sc["sign"] == -1)
            new_stored = -abs(qty) if neg else abs(qty)
        # 음수재고 유발 차단(악화 시에만)
        cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE MAT_CODE=?", mat)
        cur_sum = float(cur.fetchone()[0] or 0)
        new_sum = cur_sum - old_stored + new_stored
        if new_sum < 0 and new_sum < cur_sum:
            errs.append(f"음수재고 유발 ({mat} 결과재고 {new_sum:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        cur.execute("""UPDATE nx.stock_ledger
            SET MAINT_QTY=?, MAINT_TAG=?, CUST_CODE=?, GAGONG_PROC_CODE=?, REMARKS=?,
                UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE()
            WHERE MAINT_YMD=? AND MAINT_SEQ=?""",
            new_stored, (str(payload.get("MAINT_TAG") or sc["tags"][0]).strip()),
            (str(payload.get("CUST_CODE") or "").strip() or None),
            (str(payload.get("GAGONG_PROC_CODE") or "").strip() or None),
            (str(payload.get("REMARKS") or "").strip() or None),
            "web", ymd, seq)
        # ★F1: 원장만 고치면 자재수불장·자재재고(조회정본) stale → 미러 동반 반영
        _mat_mirror_edit(cur, ymd, mat, old_cc, old_gp, old_tag, old_stored, new_stored, "stockupdate")
        stock_changed("stock_update")         # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "stored_qty": new_stored, "stock": new_sum}
    finally:
        cn.close()

@router.post("/api/stock/delete")
def stock_delete(payload: dict = Body(...)):
    """기존 원장행 삭제. 가드: 대상존재·마감월 잠금·삭제 시 음수재고 유발 차단(입고행 삭제로 재고<0 방지)."""
    ymd = str(payload.get("MAINT_YMD", "")).strip()
    try:
        seq = int(payload.get("MAINT_SEQ"))
    except (TypeError, ValueError):
        raise HTTPException(400, "MAINT_SEQ 오류")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT MAT_CODE, MAINT_QTY, ISNULL(CUST_CODE,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(MAINT_TAG,'') FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        row = cur.fetchone()
        if not row:
            return {"ok": False, "errors": [f"대상 없음 ({ymd}/{seq})"]}
        mat = str(row[0] or "").strip()
        old_stored = float(row[1] or 0)
        old_cc = str(row[2] or "").strip(); old_gp = str(row[3] or "").strip(); old_tag = str(row[4] or "").strip()
        errs = []
        if _closed(cur, ymd, "MAT"):
            errs.append(f"마감월({_ym(ymd)}) 삭제 불가")
        cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE MAT_CODE=?", mat)
        cur_sum = float(cur.fetchone()[0] or 0)
        new_sum = cur_sum - old_stored
        if new_sum < 0 and new_sum < cur_sum:
            errs.append(f"음수재고 유발 ({mat} 삭제 후 재고 {new_sum:g} < 0)")
        if errs:
            return {"ok": False, "errors": errs}
        cur.execute("DELETE FROM nx.stock_ledger WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
        # ★F1: 삭제도 자재수불장·자재재고(조회정본) 동반 반영(save가 남긴 web행 삭제 + 잔액 되돌림)
        _mat_mirror_edit(cur, ymd, mat, old_cc, old_gp, old_tag, old_stored, 0.0, "stockdelete")
        stock_changed("stock_delete")         # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        cn.close()
