# -*- coding: utf-8 -*-
"""사급(sagub)+매출(saleout/lgsale)+권한(perm) 도메인 라우터 — 사급재고조정/출고/회수·매출마감출고·LG송장·권한.
   app.py에서 분리. 원장/가격 헬퍼(_led_ins·_sagub_move·_pur_price·_sagub_price·_is_free_sagub·
   _sale_close_lookup·_saleout_led·_lgsale_led·_next_yymm)는 이 도메인 로컬(블록내). 공유는 common.py."""
import math
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Body, HTTPException
from common import _conn, _nx, _nx_tx, _b, _d6, _num, _ITEM_WORK, _ym, _closed

router = APIRouter()

# ===================== 사급재고조정 (w_pu_stock_090) — ★Phase4 단일원장 fold: nx.stock_ledger(STOCK_POINT='SAG', tag '2') =====================
# 협력사 보유 사급재고(SAG) 장부조정(±). id="YMD-SEQ"(원장 복합키). tag '2'=장부수정(±). MAT screen은 STOCK_POINT='MAT' 격리(Phase3).
@router.get("/api/sagub/adjust/list")
def sagub_adjust_list(fr: str = Query(""), to: str = Query(""), cust: str = Query(""), mat: str = Query(""), limit: int = Query(500)):
    """사급재고조정 목록 = stock_ledger(STOCK_POINT='SAG', tag='2'). 코드→이름 조인."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["l.STOCK_POINT='SAG'", "l.MAINT_TAG='2'"]; p = []
        if fr: w.append("l.MAINT_YMD>=?"); p.append(fr)
        if to: w.append("l.MAINT_YMD<=?"); p.append(to)
        if cust: w.append("l.CUST_CODE=?"); p.append(cust)
        if mat: w.append("l.MAT_CODE LIKE ?"); p.append(f"%{mat}%")
        cur.execute(f"""SELECT TOP {int(limit)} l.MAINT_YMD maint_ymd, l.MAINT_SEQ maint_seq, l.CUST_CODE cust_code,
              ISNULL(c.CUST_DESC,'') custnm, l.MAT_CODE mat_code, ISNULL(i.ITEM_DESC,'') matnm,
              l.MAINT_QTY maint_qty, ISNULL(l.MAINT_COST,0) maint_cost, ISNULL(l.MAINT_AMT,0) maint_amt,
              ISNULL(l.REMARKS,'') remarks, ISNULL(l.INSERT_USER_ID,'') insert_user_id, l.INSERT_DATETIME insert_datetime
            FROM nx.stock_ledger l LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=l.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=l.MAT_CODE
            WHERE {' AND '.join(w)} ORDER BY l.MAINT_YMD DESC, l.MAINT_SEQ ASC""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["id"] = f'{r["maint_ymd"]}-{r["maint_seq"]}'
            r["maint_qty"] = float(r["maint_qty"] or 0)
            r["insert_datetime"] = str(r["insert_datetime"] or "")[:19]
        cur.execute("""SELECT DISTINCT l.CUST_CODE, ISNULL(c.CUST_DESC,'') nm FROM nx.stock_ledger l
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=l.CUST_CODE
            WHERE l.STOCK_POINT='SAG' AND l.CUST_CODE IS NOT NULL ORDER BY 2""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        return {"rows": rows, "custs": custs}
    finally:
        cn.close()

@router.post("/api/sagub/adjust/save")
def sagub_adjust_save(payload: dict = Body(...)):
    """사급재고조정 등록/수정 → stock_ledger(SAG, tag '2'). 수정수량 음수허용(강제수정). id="YMD-SEQ"면 삭제후 재키."""
    rid = payload.get("id")
    cust = str(payload.get("cust_code", "")).strip()
    mat = str(payload.get("mat_code", "")).strip()
    remarks = str(payload.get("remarks", "")).strip()
    try:
        qty = float(payload.get("maint_qty"))
    except Exception:
        raise HTTPException(400, "수정수량(숫자) 필수")
    if not cust or not mat:
        raise HTTPException(400, "사급업체·자도번 필수")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        ymd = cur.fetchone()[0]
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
        seq = cur.fetchone()[0]
        if rid:  # 수정 = 기존행 삭제 후 신규(재키)
            try:
                oy, osq = str(rid).split("-"); osq = int(osq)
                if _closed(cur, oy):
                    raise HTTPException(400, f"마감월({_ym(oy)}) 편집 불가")
                cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='SAG' AND MAINT_YMD=? AND MAINT_SEQ=?", oy, osq)
            except (ValueError, AttributeError):
                pass
        cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('SAG',?,?,'2',?,?,?,?,'web',getdate())""", ymd, seq, cust, mat, qty, (remarks or None))
        return {"ok": True, "id": f"{ymd}-{seq}"}
    finally:
        cn.close()

@router.post("/api/sagub/adjust/delete")
def sagub_adjust_delete(payload: dict = Body(...)):
    """사급재고조정 삭제(SAG)."""
    rid = payload.get("id")
    if not rid:
        raise HTTPException(400, "id 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        try:
            y, sq = str(rid).split("-"); sq = int(sq)
        except ValueError:
            raise HTTPException(400, "id 형식 오류")
        if _closed(cur, y):
            raise HTTPException(400, f"마감월({_ym(y)}) 삭제 불가")
        cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='SAG' AND MAINT_TAG='2' AND MAINT_YMD=? AND MAINT_SEQ=?", y, sq)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        cn.close()

# ===================== 협력사 보유 사급재고 현황 (★작업3 메인, 정본=레거시 PU_T_SAGUB_STOCK RO) =====================
@router.get("/api/sagub/holding/list")
def sagub_holding_list(cust: str = Query(""), mat: str = Query(""), sign: str = Query(""), limit: int = Query(3000)):
    """★작업3 '협력사가 보유중이어야 할 사급재고 리스트' = 레거시 PU_T_SAGUB_STOCK(자도번×사급업체) 라이브 RO 정본.
    STOCK_QTY = 협력사 보유 사급 잔량. 레거시 사급출고 프로그램(w_pu_output_010/011/015)이 트리거로 net 유지:
      잔량 = Σ사급출고(원자재 d) − Σ(완성/세트 입고 × 상위품 BOM상 d 소요량) − 조정.
    ★코드레벨 정합: 사급출고=원자재레벨, 회수=완성/세트=상위레벨 → 코드가 안 맞아 단순 netting 불가하나,
      레거시가 상위품 BOM전개 소요량으로 이미 net한 결과가 PU_T_SAGUB_STOCK.STOCK_QTY (오늘도 갱신되는 살아있는 정본).
    REF_STOCK_QTY=관리품(중량관리 item_class J) 참조수량. sign: 1양수/-1음수/0=제로/공백전체."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = []; p = []
        if cust: w.append("s.CUST_CODE=?"); p.append(cust)
        if mat: w.append("(s.MAT_CODE LIKE ? OR i.ITEM_DESC LIKE ?)"); p += [f"%{mat}%", f"%{mat}%"]
        if sign == "1": w.append("s.STOCK_QTY>0")
        elif sign == "-1": w.append("s.STOCK_QTY<0")
        elif sign == "0": w.append("s.STOCK_QTY=0")
        cur.execute(f"""SELECT TOP {int(limit)} s.CUST_CODE, ISNULL(c.CUST_DESC,'') custnm, s.MAT_CODE,
              ISNULL(i.ITEM_DESC,'') matnm, ISNULL(i.ITEM_CLASS,'') item_class, s.STOCK_QTY, s.REF_STOCK_QTY,
              ISNULL(s.UPDATE_USER_ID,'') upd_user, s.UPDATE_DATETIME upd_dt, ISNULL(s.UPDATE_WINDOW,'') upd_win
            FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK s
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=s.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=s.MAT_CODE
            {('WHERE '+' AND '.join(w)) if w else ''}
            ORDER BY custnm, s.MAT_CODE""", *p)
        cols = [d[0] for d in cur.description]
        rows = [{k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in zip(cols, r)} for r in cur.fetchall()]
        cur.execute("""SELECT s.CUST_CODE, ISNULL(c.CUST_DESC,'') nm FROM PARTNER_ERP_TEST3.nx.PU_T_SAGUB_STOCK s
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=s.CUST_CODE GROUP BY s.CUST_CODE, c.CUST_DESC ORDER BY 2""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        totq = sum(float(r["STOCK_QTY"] or 0) for r in rows)
        return {"rows": rows, "custs": custs, "totqty": totq}
    finally:
        cn.close()

# ===================== 사급재고입출고현황 (w_pu_stock_080) — ★Phase4 fold: stock_ledger(STOCK_POINT='SAG') 파생 =====================
@router.get("/api/sagub/stock/list")
def sagub_stock_list(cust: str = Query(""), mat: str = Query(""), sign: str = Query(""), cls: str = Query(""), limit: int = Query(1000)):
    """사급 현재고(좌): stock_ledger(STOCK_POINT='SAG') SUM 파생. 재고=SUM(MAINT_QTY) per (사급업체,자도번). sign: 1양수/-1음수/공백전체."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["l.STOCK_POINT='SAG'"]; p = []
        if cust: w.append("l.CUST_CODE=?"); p.append(cust)
        if mat: w.append("l.MAT_CODE LIKE ?"); p.append(f"%{mat}%")
        hav = ""
        if sign == "1": hav = "HAVING SUM(l.MAINT_QTY)>0"
        elif sign == "-1": hav = "HAVING SUM(l.MAINT_QTY)<0"
        cur.execute(f"""SELECT TOP {int(limit)} l.CUST_CODE cust_code, ISNULL(c.CUST_DESC,'') custnm, l.MAT_CODE mat_code,
              ISNULL(i.ITEM_DESC,'') matnm, SUM(l.MAINT_QTY) stock_qty, ISNULL(MAX(i.ITEM_CLASS),'A') item_class
            FROM nx.stock_ledger l LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=l.CUST_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=l.MAT_CODE
            WHERE {' AND '.join(w)}
            GROUP BY l.CUST_CODE, c.CUST_DESC, l.MAT_CODE, i.ITEM_DESC
            {hav} ORDER BY custnm, l.MAT_CODE""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["stock_qty"] = float(r["stock_qty"] or 0)
        if cls:  # J관리/A일반 필터(품목 ITEM_CLASS 기준)
            rows = [r for r in rows if (r.get("item_class") or "A") == cls]
        cur.execute("""SELECT DISTINCT l.CUST_CODE, ISNULL(c.CUST_DESC,'') nm FROM nx.stock_ledger l
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=l.CUST_CODE
            WHERE l.STOCK_POINT='SAG' AND l.CUST_CODE IS NOT NULL ORDER BY 2""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        return {"rows": rows, "custs": custs}
    finally:
        cn.close()

@router.get("/api/sagub/stock/ledger")
def sagub_stock_ledger(cust: str = Query(...), mat: str = Query(...), fr: str = Query(""), to: str = Query("")):
    """사급 수불(우): 선택 (사급업체×자도번)의 입출고 이력(stock_ledger SAG). running balance. 입고=+, 출고=−. 구분=태그."""
    tagnm = {"9": "매입입고", "S": "세트입고", "C": "가공입고", "3": "기초재고", "2": "재고조정",
             "G1": "무상이동출고", "G2": "무상이동복귀", "5": "매출출고"}
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["l.STOCK_POINT='SAG'", "l.CUST_CODE=?", "l.MAT_CODE=?"]; p = [cust, mat]
        cur.execute(f"""SELECT l.MAINT_YMD, l.MAINT_SEQ, l.MAINT_TAG, l.MAINT_QTY, ISNULL(l.REMARKS,''), ISNULL(l.INSERT_USER_ID,''), l.INSERT_DATETIME
            FROM nx.stock_ledger l WHERE {' AND '.join(w)} ORDER BY l.MAINT_YMD, l.MAINT_SEQ""", *p)
        bal = 0.0; out = []
        for r in cur.fetchall():
            prev = bal; q = float(r[3] or 0)
            inq = q if q > 0 else 0; outq = -q if q < 0 else 0
            bal = prev + q
            row = {"maint_ymd": r[0], "maint_seq": r[1], "tag": r[2], "tagnm": tagnm.get(r[2], r[2]),
                   "prev_qty": prev, "in_qty": inq, "out_qty": outq, "stock_qty": bal,
                   "remarks": r[4], "user": r[5], "dt": str(r[6])[:19] if r[6] else ""}
            if fr and r[0] < fr: continue
            if to and r[0] > to: continue
            out.append(row)
        return {"rows": out, "final_qty": bal}
    finally:
        cn.close()

# ===================== 사급출고관리 (w_pu_output_050, nx.sagub_output_req) =====================
@router.get("/api/sagub/output/list")
def sagub_output_list(cust: str = Query(""), mat: str = Query(""), fin: str = Query(""), limit: int = Query(800)):
    """사급 출고요청 목록. 사급재고(nx.sagub_maint SUM 파생) 조인. fin: 0미출고/1완료/공백전체."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = []; p = []
        if cust: w.append("r.cust_code=?"); p.append(cust)
        if mat: w.append("r.mat_code LIKE ?"); p.append(f"%{mat}%")
        if fin: w.append("ISNULL(r.finish_flag,'0')=?"); p.append(fin)
        cur.execute(f"""SELECT TOP {int(limit)} r.id, r.req_ymd, r.req_seq, r.cust_code, ISNULL(c.CUST_DESC,'') custnm,
              r.item_code, ISNULL(pi.ITEM_DESC,'') itemnm, r.mat_code, ISNULL(mi.ITEM_DESC,'') matnm,
              r.req_qty, r.out_qty, ISNULL(r.finish_flag,'0') finish_flag, ISNULL(r.remarks,'') remarks,
              ISNULL(sg.stock_qty,0) sagub_stock, r.insert_user_id, r.insert_datetime
            FROM nx.sagub_output_req r
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=r.cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM pi ON pi.ITEM_CODE=r.item_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM mi ON mi.ITEM_CODE=r.mat_code
            LEFT JOIN (SELECT cust_code, mat_code, SUM(maint_qty) stock_qty FROM nx.sagub_maint GROUP BY cust_code, mat_code) sg
              ON sg.cust_code=r.cust_code AND sg.mat_code=r.mat_code
            {('WHERE '+' AND '.join(w)) if w else ''} ORDER BY r.req_ymd DESC, r.req_seq, r.mat_code""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute("""SELECT DISTINCT r.cust_code, ISNULL(c.CUST_DESC,'') nm FROM nx.sagub_output_req r
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=r.cust_code WHERE r.cust_code IS NOT NULL ORDER BY 2""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        return {"rows": rows, "custs": custs}
    finally:
        cn.close()

@router.post("/api/sagub/output/save")
def sagub_output_save(payload: dict = Body(...)):
    """출고요청 등록/수정(req_qty). id 있으면 UPDATE, 없으면 INSERT(채번)."""
    rid = payload.get("id")
    cust = str(payload.get("cust_code", "")).strip()
    mat = str(payload.get("mat_code", "")).strip()
    item = str(payload.get("item_code", "")).strip()
    remarks = str(payload.get("remarks", "")).strip()
    try:
        req = float(payload.get("req_qty"))
    except Exception:
        raise HTTPException(400, "출고요청수량(숫자) 필수")
    if not cust or not mat:
        raise HTTPException(400, "사급업체·자도번 필수")
    cn = _nx(); cur = cn.cursor()
    try:
        if rid:
            cur.execute("UPDATE nx.sagub_output_req SET cust_code=?,mat_code=?,item_code=?,req_qty=?,remarks=? WHERE id=? AND ISNULL(finish_flag,'0')='0'",
                        cust, mat, item, req, remarks, int(rid))
            if cur.rowcount == 0:
                raise HTTPException(409, "출고완료 건은 수정 불가")
        else:
            cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
            ymd = cur.fetchone()[0]
            cur.execute("SELECT ISNULL(MAX(req_seq),0)+1 FROM nx.sagub_output_req WHERE req_ymd=?", ymd)
            seq = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO nx.sagub_output_req(req_ymd,req_seq,cust_code,mat_code,item_code,req_qty,out_qty,finish_flag,remarks,insert_user_id,insert_datetime)
                VALUES(?,?,?,?,?,?,0,'0',?,'web',getdate())""", ymd, seq, cust, mat, item, req, remarks)
        cn.commit()
        return {"ok": True}
    finally:
        cn.close()

# ---- ★Phase4 사급 이동/회수 stock_ledger posting 헬퍼 ----
def _led_ins(cur, point, ymd, tag, gseq, cust, mat, qty, wh, remarks, cost=0.0, amt=0.0):
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
    seq = cur.fetchone()[0]
    cur.execute("""INSERT INTO nx.stock_ledger
        (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,CUST_CODE,GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,
         MAINT_COST,MAINT_AMT,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'web',GETDATE())""",
        point, ymd, seq, gseq, tag, (cust or None), (wh or None), mat, qty, float(cost), float(amt), remarks)
    return seq

def _sagub_move(cur, ymd, cust, mat, qty, wh, direction, remarks):
    """무상사급 창고이동 2행(그룹). direction='out'=출고(−MAT@우리/+SAG@사급처, G1),
    'back'=회수복귀(−SAG@사급처/+PRD@우리, G2). net=소유권 유지(재고총량 불변, 재고점만 이동)."""
    tag = "G1" if direction == "out" else "G2"
    cur.execute("SELECT ISNULL(MAX(MAINT_GROUP_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_TAG=?", tag)
    gseq = cur.fetchone()[0]
    q = abs(float(qty))
    if direction == "out":
        _led_ins(cur, "MAT", ymd, tag, gseq, None, mat, -q, wh, remarks)          # −우리창고
        _led_ins(cur, "SAG", ymd, tag, gseq, cust, mat, q, cust, remarks)         # +사급처(SAG)
    else:
        _led_ins(cur, "SAG", ymd, tag, gseq, cust, mat, -q, cust, remarks)        # −사급처(SAG)
        _led_ins(cur, "PRD", ymd, tag, gseq, None, mat, q, wh, remarks)           # +생산(PRD)
    return gseq

def _pur_price(cur, item, cust, ymd):
    """구매단가 = PR_M_ITEM_COST 최신유효(cost_tag='1', 매입처). 유상 회수=매입입고 단가."""
    cur.execute("""SELECT TOP 1 item_cost FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_COST
        WHERE item_code=? AND cust_code=? AND cost_tag='1' AND cost_apply_ymd<=? ORDER BY cost_apply_ymd DESC""",
        item, cust, ymd)
    r = cur.fetchone()
    return float(r[0]) if r and r[0] is not None else 0.0

@router.post("/api/sagub/output/confirm")
def sagub_output_confirm(payload: dict = Body(...)):
    """출고확정. ★Phase4 자동판정: 무상=창고이동 출고(−MAT@우리/+SAG@사급처, tag G1) posting + finish.
    유상=요청완료만(재고·매출은 판매출고 saleout에서 확정=이중계상 방지)."""
    rid = payload.get("id")
    if not rid:
        raise HTTPException(400, "id 필요")
    wh = str(payload.get("wh") or "IS0001").strip()   # 우리 출고창고(default IS0001)
    try:
        outq = float(payload.get("out_qty"))
    except Exception:
        raise HTTPException(400, "출고수량 필수")
    if outq <= 0:
        raise HTTPException(400, "출고수량>0 필요")
    cn = _nx_tx(); cur = cn.cursor()   # ★원자성: 무상이동 2행(G1) + finish 플래그 그룹
    try:
        cur.execute("SELECT cust_code, mat_code, ISNULL(finish_flag,'0') FROM nx.sagub_output_req WHERE id=?", int(rid))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "요청 없음")
        if row[2] == '1':
            raise HTTPException(409, "이미 출고완료")
        cust, mat = row[0], row[1]
        cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        ymd = cur.fetchone()[0]
        free = _is_free_sagub(cur, cust, ymd)
        if free:
            _sagub_move(cur, ymd, cust, mat, outq, wh, "out", f"무상사급출고(req#{rid})")
            note = f"무상 창고이동 출고 완료(−MAT@{wh} / +SAG@{cust}, 소유권 유지)"
        else:
            note = "유상 요청완료 — 재고·매출은 판매출고(saleout)에서 확정하세요(이중계상 방지)."
        cur.execute("UPDATE nx.sagub_output_req SET out_qty=?, finish_flag='1' WHERE id=?", outq, int(rid))
        cn.commit()   # ★이동 2행+finish 원자 커밋
        return {"ok": True, "gubun": ("무상사급" if free else "유상사급"), "note": note}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/sagub/recover")
def sagub_recover(payload: dict = Body(...)):
    """사급 회수. ★Phase4 자동판정: 유상=매입입고(+PRD, tag '9', 구매단가) / 무상=이동복귀(−SAG@사급처 / +PRD@우리, tag G2).
    무상 복귀는 SAG 잔량 이내 가드. 유상 단가=override 또는 PR_M_ITEM_COST(cost_tag='1')."""
    cust = str(payload.get("cust_code", "")).strip()
    mat = str(payload.get("mat_code", "")).strip()
    item = str(payload.get("item_code", "")).strip() or mat
    wh = str(payload.get("wh") or "IS0001").strip()
    remarks = str(payload.get("remarks", "")).strip()
    cost_override = payload.get("cost")
    try:
        qty = abs(float(payload.get("qty")))
    except Exception:
        raise HTTPException(400, "회수수량(숫자) 필수")
    if not cust or not mat or qty <= 0:
        raise HTTPException(400, "사급업체·자도번·수량(>0) 필수")
    cn = _nx_tx(); cur = cn.cursor()   # ★원자성: 무상 회수 2행(G2) / 유상 매입입고 1행 그룹
    try:
        cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        ymd = cur.fetchone()[0]
        if _closed(cur, ymd):
            raise HTTPException(400, f"마감월({_ym(ymd)}) 회수 불가")
        free = _is_free_sagub(cur, cust, ymd)
        if free:  # 무상 = 이동복귀(−SAG / +PRD). SAG 잔량 가드.
            cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WHERE STOCK_POINT='SAG' AND CUST_CODE=? AND MAT_CODE=?", cust, mat)
            avail = float(cur.fetchone()[0] or 0)
            if qty > avail:
                raise HTTPException(400, f"SAG 잔량부족 ({mat}@{cust} 가용 {avail:g} < 회수 {qty:g})")
            gseq = _sagub_move(cur, ymd, cust, mat, qty, wh, "back", (remarks or f"무상사급회수복귀"))
            cn.commit()   # ★2행(−SAG/+PRD) 원자 커밋
            return {"ok": True, "gubun": "무상사급", "id": f"{ymd}-{gseq}",
                    "note": f"무상 이동복귀 완료(−SAG@{cust} / +PRD@{wh})"}
        # 유상 = 매입입고(+PRD, tag '9'). 구매단가.
        cost = float(cost_override) if (cost_override not in (None, "")) else _pur_price(cur, item, cust, ymd)
        amt = float(int(qty * cost))
        seq = _led_ins(cur, "PRD", ymd, "9", None, cust, item, qty, wh, (remarks or "유상사급회수 매입입고"), cost, amt)
        cn.commit()
        return {"ok": True, "gubun": "유상사급", "id": f"{ymd}-{seq}", "cost": cost, "amt": amt,
                "note": f"유상 매입입고 완료(+PRD@{wh}, 구매단가 {cost:g})"}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/sagub/move/delete")
def sagub_move_delete(payload: dict = Body(...)):
    """무상사급 이동/회수 그룹 취소(id='YMD-GROUP', tag G1 또는 G2). 2행 동반삭제(net 원복)."""
    rid = str(payload.get("id", "")).strip()
    tag = str(payload.get("tag", "")).strip()   # 'G1'(출고) 또는 'G2'(회수)
    if not rid or tag not in ("G1", "G2"):
        raise HTTPException(400, "id(YMD-GROUP)·tag(G1/G2) 필요")
    try:
        y, g = rid.split("-"); g = int(g)
    except ValueError:
        raise HTTPException(400, "id 형식 오류")
    cn = _nx(); cur = cn.cursor()
    try:
        if _closed(cur, y):
            raise HTTPException(400, f"마감월({_ym(y)}) 삭제 불가")
        cur.execute("DELETE FROM nx.stock_ledger WHERE MAINT_TAG=? AND MAINT_YMD=? AND MAINT_GROUP_SEQ=?", tag, y, g)
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        cn.close()

@router.post("/api/sagub/output/delete")
def sagub_output_delete(payload: dict = Body(...)):
    rid = payload.get("id")
    if not rid:
        raise HTTPException(400, "id 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.sagub_output_req WHERE id=? AND ISNULL(finish_flag,'0')='0'", int(rid))
        cn.commit()
        return {"ok": True, "deleted": cur.rowcount}
    finally:
        cn.close()

# ===================== 사용자 권한 서버저장 (nx.user_perm) — 브라우저 localStorage 대체 =====================
@router.get("/api/perm/all")
def perm_all():
    """전 사용자 권한 로드(로그인/앱시작 시). {user_id:{sid:{view,edit}}}. 관리자 저장분이 전 PC 공통 적용."""
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT user_id, sid, can_view, can_edit FROM nx.user_perm")
        out = {}
        for uid, sid, v, e in cur.fetchall():
            out.setdefault(uid, {})[sid] = {"view": bool(v), "edit": bool(e)}
        return {"perms": out}
    finally:
        cn.close()

@router.post("/api/perm/save")
def perm_save(payload: dict = Body(...)):
    """권한 저장(전체 스냅샷 교체). body {perms:{user_id:{sid:{view,edit}}}, by?}. 관리자 UI가 PERM.perms 전체 전송."""
    perms = payload.get("perms") or {}
    by = str(payload.get("by", "web")).strip() or "web"
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.user_perm")   # perms=전체 스냅샷 → 통째 교체
        cnt = 0
        for uid, m in perms.items():
            for sid, pe in (m or {}).items():
                cur.execute("""INSERT INTO nx.user_perm(user_id,sid,can_view,can_edit,upd_user,upd_dt)
                    VALUES(?,?,?,?,?,getdate())""", str(uid), str(sid),
                    1 if (pe or {}).get("view") else 0, 1 if (pe or {}).get("edit") else 0, by)
                cnt += 1
        cn.commit()
        return {"ok": True, "users": len(perms), "rows": cnt}
    finally:
        cn.close()

# ===================== 웹 사용자 계정(전 PC 공통) — nx.web_user 스냅샷 =====================
@router.get("/api/perm/users")
def perm_users_get():
    """웹 로그인 계정목록(전 PC 공통) — 관리자 저장분. 없으면 users=null(프론트가 시드 사용)."""
    cn = _nx(); cur = cn.cursor()
    try:
        users = None
        try:
            cur.execute("SELECT udata FROM nx.web_user WHERE user_id='__ALL__'")
            r = cur.fetchone()
            if r and r[0]:
                import json as _json
                users = _json.loads(r[0])
        except Exception:
            users = None
        return {"users": users}
    finally:
        cn.close()

@router.post("/api/perm/users")
def perm_users_save(payload: dict = Body(...)):
    """웹 로그인 계정목록 저장(전체 스냅샷, 전 PC 공통). body {users:[...], by?}. 사용자관리 저장 시 호출."""
    users = payload.get("users") or []
    by = (str(payload.get("by", "web")).strip() or "web")[:40]
    import json as _json
    blob = _json.dumps(users, ensure_ascii=False)
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("IF OBJECT_ID('nx.web_user') IS NULL CREATE TABLE nx.web_user(user_id NVARCHAR(20) NOT NULL PRIMARY KEY, udata NVARCHAR(MAX), upd_user NVARCHAR(40), upd_dt DATETIME)")
        cur.execute("""MERGE nx.web_user AS t USING (SELECT '__ALL__' uid) s ON t.user_id=s.uid
            WHEN MATCHED THEN UPDATE SET udata=?, upd_user=?, upd_dt=getdate()
            WHEN NOT MATCHED THEN INSERT(user_id,udata,upd_user,upd_dt) VALUES('__ALL__',?,?,getdate());""",
            blob, by, blob, by)
        cn.commit()
        return {"ok": True, "count": len(users)}
    finally:
        cn.close()

# ===================== 판매및출고등록 (w_pu_output_010/015, nx.stock_maint tag='5') — 구매→협력사 판매출고 =====================
# ★역분석 확정(2026-07-28, dw_pu_input_140_t2 retrieve + 라이브대사 98%): 판매출고 정본 = PU_T_STOCK_MAINT(자재수불) MAINT_TAG='5'.
#   maint_cost=사급단가(f_get_item_cost 'S'=PR_M_ITEM_COST cost_tag='S' 유효일자최신), amt=trunc(qty×cost), vat=trunc(amt×0.1)=매출/부가세.
#   ★부호: 판매/불출=음수 저장(집계 SUM(-AMT) 부호반전=사급매출). nx.stock_maint(자재수불 원장)→사급매출집계·수불장 파생.
_SALEOUT_GUBUN = {"5": "협력업체판매", "0": "일반", "9": "완성품"}

def _next_yymm(yymm):
    y = int(yymm[:2]); m = int(yymm[2:4]) + 1
    if m > 12: m = 1; y += 1
    return f"{y:02d}{m:02d}"

def _sale_close_lookup(cur):
    """사급출고=매출 → 매출마감(nx.sale_close) 잠금 판정기 반환. fn(cust,out_ymd)->bool.
    마감월=업체 마감일(CM_M_CUST_MAGAM 최신 MAGAM_DAY)기준: 일자<=마감일→당월, 초과→익월. 마감(close_flag=1)이면 잠금.
    ★작업1: 웹등록분(nx.saleout_maint tag5) 수정/삭제 잠금용. 마감데이터 없으면 전부 미잠금(비침습)."""
    closed = set()
    try:
        cur.execute("SELECT ym, cust_code FROM nx.sale_close WHERE close_flag=1")
        closed = {(str(r[0]).strip(), str(r[1]).strip()) for r in cur.fetchall()}
    except Exception:
        pass
    magam = {}
    try:
        cur.execute("""SELECT CUST_CODE, MAGAM_DAY FROM (
              SELECT CUST_CODE, MAGAM_DAY, ROW_NUMBER() OVER(PARTITION BY CUST_CODE ORDER BY APPLY_YYMM DESC) rn
              FROM PARTNER_ERP_TEST3.nx.CM_M_CUST_MAGAM) t WHERE rn=1""")
        for r in cur.fetchall():
            magam[str(r[0]).strip()] = (str(r[1] or '31').strip() or '31')
    except Exception:
        pass
    def is_closed(cust, out_ymd):
        if not closed: return False
        y = str(out_ymd or '').strip()
        if len(y) < 6: return False
        yymm, dd = y[:4], y[4:6]
        md = magam.get(str(cust or '').strip(), '31')
        try:
            cm = yymm if int(dd) <= int(md) else _next_yymm(yymm)
        except Exception:
            cm = yymm
        return (cm, str(cust or '').strip()) in closed
    return is_closed

def _sagub_price(cur, item, cust, ymd):
    """사급단가 = f_get_item_cost(item,cust,'S',ymd) 정확이식: PR_M_ITEM_COST 최신유효(cost_tag='S')."""
    cur.execute("""SELECT TOP 1 item_cost FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM_COST
        WHERE item_code=? AND cust_code=? AND cost_tag='S' AND cost_apply_ymd<=? ORDER BY cost_apply_ymd DESC""",
        item, cust, ymd)
    r = cur.fetchone()
    return float(r[0]) if r and r[0] is not None else 0.0

# ===================== ★Phase4: 사급 유상/무상 자동판정 (§11) =====================
def _is_free_sagub(cur, cust, ymd):
    """무상사급 판정. nx.sagub_free_vendor(active=1) 등재 AND (적용일 미설정 OR 거래일>=적용일) → 무상.
    미등재=유상(기본). 적용일 미설정(예 경성 담당확인 전)=등재취지상 무상 적용(전체기간). 문영=260226부터."""
    c = str(cust or "").strip()
    if not c:
        return False
    cur.execute("SELECT apply_from_ymd FROM nx.sagub_free_vendor WHERE cust_code=? AND active=1", c)
    r = cur.fetchone()
    if not r:
        return False
    af = str(r[0] or "").strip()
    if not af:
        return True   # 적용일 미설정 → 무상(등재취지). 담당 적용일 설정 시 날짜게이트 발동
    return str(ymd or "").strip() >= af

@router.get("/api/sagub/judge")
def sagub_judge(cust: str = Query(...), ymd: str = Query("")):
    """유무상 자동판정(검증·화면표시). 무상=free_vendor 등재+적용일 조건 충족, else 유상(기본)."""
    cn = _nx(); cur = cn.cursor()
    try:
        if not ymd.strip():
            cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)"); ymd = cur.fetchone()[0]
        cur.execute("SELECT apply_from_ymd, ISNULL(remarks,'') FROM nx.sagub_free_vendor WHERE cust_code=? AND active=1", cust.strip())
        r = cur.fetchone()
        free = _is_free_sagub(cur, cust, ymd)
        if r and not str(r[0] or "").strip():
            note = "적용일 미설정(담당확인) — 전체기간 무상 적용중"
        elif r:
            note = f"적용일 {r[0]} 부터 무상 (이전 거래는 유상, 소급 안 함)"
        else:
            note = "무상거래처 미등재 → 유상"
        return {"cust": cust.strip(), "ymd": ymd, "free": free,
                "gubun": "무상사급" if free else "유상사급", "registered": bool(r),
                "apply_from": (r[0] if r else None), "note": note}
    finally:
        cn.close()

@router.get("/api/saleout/price")
def saleout_price(item: str = Query(...), cust: str = Query(...), ymd: str = Query("")):
    """판매출고 사급단가 자동조회(폼 입력시)."""
    cn = _nx(); cur = cn.cursor()
    try:
        if not ymd:
            cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)"); ymd = cur.fetchone()[0]
        return {"cost": _sagub_price(cur, item, cust, ymd)}
    finally:
        cn.close()

@router.get("/api/saleout/list")
def saleout_list(fr: str = Query(""), to: str = Query(""), sheet: str = Query(""), cust: str = Query(""), cust_code: str = Query(""), item: str = Query(""), gubun: str = Query(""), limit: int = Query(1500)):
    """판매출고 목록 = ★nx미러(nx.PU_T_STOCK_MAINT tag5, 기존이력·읽기전용) ∪ nx.saleout_maint(웹등록·편집가능).
    미러도 nx라 레거시 의존 없음(컷오버 원칙). 출고수량/금액=|값|(음수저장 불출→양수표시). src='legacy'|'web'. 코드→이름."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["m.maint_tag='5'"]; pf = []
        if fr: w.append("m.maint_ymd>=?"); pf.append(fr)
        if to: w.append("m.maint_ymd<=?"); pf.append(to)
        if sheet: w.append("CAST(m.sheet_no AS varchar) LIKE ?"); pf.append(f"%{sheet}%")
        # ★2026-08-23 외주처 = 드롭다운 → 입력칸.
        #   cust_code(화면에서 확정된 코드) 오면 그 거래처만. 아니면 코드/이름 LIKE.
        if cust_code.strip():
            w.append("m.cust_code=?"); pf.append(cust_code.strip())
        elif cust:
            w.append("(m.cust_code=? OR ISNULL(c.CUST_DESC,'') LIKE ?)"); pf += [cust, f"%{cust}%"]
        if item: w.append("m.mat_code LIKE ?"); pf.append(f"%{item}%")
        where = " AND ".join(w)
        SEL = """SELECT {idcol} id, '{src}' src, m.maint_ymd out_ymd, m.cust_code out_cust, ISNULL(c.CUST_DESC,'') custnm,
              CAST(m.sheet_no AS varchar) sheet_no, m.maint_seq out_seq, m.mat_code item_code, ISNULL(i.ITEM_DESC,'') itemnm,
              ABS(ISNULL(m.maint_qty,0)) out_qty, ISNULL(m.maint_cost,0) cost, ABS(ISNULL(m.maint_amt,0)) amt, ABS(ISNULL(m.maint_vat,0)) vat,
              ISNULL(m.remarks,'') remarks, m.insert_user_id reg_user, {upd} upd_user, ISNULL(m.update_datetime,m.insert_datetime) work_dt,
              m.work_order, m.split_work_order, NULL sale_ymd, NULL sale_hms, {pf_col} print_flag
            FROM {tbl} m LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=m.mat_code
            WHERE {where}"""
        web_sel = SEL.format(idcol="m.id", src="web", upd="m.upd_user", pf_col="ISNULL(m.print_flag,'0')",
                             tbl="nx.saleout_maint", where=where)
        leg_sel = SEL.format(idcol="NULL", src="legacy", upd="m.update_user_id", pf_col="'0'",
                             tbl="PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT", where=where)
        cur.execute(f"""SELECT TOP {int(limit)} * FROM ({web_sel} UNION ALL {leg_sel}) u
            ORDER BY out_ymd DESC, sheet_no, out_seq""", *(pf + pf))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        is_closed = _sale_close_lookup(cur)   # ★작업1: 매출마감된 자료 잠금 플래그(웹편집 차단용)
        for r in rows:
            r["gubun"] = "5"; r["gubunnm"] = _SALEOUT_GUBUN["5"]
            r["closed"] = 1 if is_closed(r.get("out_cust"), r.get("out_ymd")) else 0
            # 편집가능 = 웹등록분(src=web, id 있음) AND 미마감. 미러(이력)행은 읽기전용.
            r["editable"] = 1 if (r.get("src") == "web" and r.get("id") is not None and not r["closed"]) else 0
        cur.execute("""SELECT DISTINCT cust_code, nm FROM (
              SELECT m.cust_code, ISNULL(c.CUST_DESC,'') nm FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT m
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.cust_code WHERE m.MAINT_TAG='5' AND m.cust_code IS NOT NULL
              UNION SELECT m.cust_code, ISNULL(c.CUST_DESC,'') FROM nx.saleout_maint m
                LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.cust_code WHERE m.maint_tag='5' AND m.cust_code IS NOT NULL) u
            ORDER BY nm""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        totqty = sum(float(r["out_qty"] or 0) for r in rows)
        totamt = sum(float(r["amt"] or 0) for r in rows); totvat = sum(float(r["vat"] or 0) for r in rows)
        return {"rows": rows, "custs": custs, "gubuns": _SALEOUT_GUBUN, "totqty": totqty, "totamt": totamt, "totvat": totvat,
                "sheetcnt": len(set(r["sheet_no"] for r in rows if r["sheet_no"]))}
    finally:
        cn.close()

# ★Phase4: 유상사급 출고 = 매출out → stock_ledger −MAT(tag '5') 재고 완전제거. 링크 MAINT_GROUP_SEQ=saleout id.
#   매출 amt/vat 정본=nx.saleout_maint(유지), 재고 −정본=stock_ledger(단일). 이중계상 방지=재고 posting은 여기 1곳뿐.
def _saleout_led_del(cur, sid):
    cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='MAT' AND MAINT_TAG='5' AND MAINT_GROUP_SEQ=?", int(sid))

def _saleout_led_post(cur, sid, ymd, cust, item, qty, cost, amt, vat, sheet, wo):
    _saleout_led_del(cur, sid)   # 재게시(수정/복사 시 기존 링크행 제거 후 1행 재생성)
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
    seq = cur.fetchone()[0]
    cur.execute("""INSERT INTO nx.stock_ledger
        (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,
         MAINT_COST,MAINT_AMT,MAINT_VAT,SHEET_NO,WORK_ORDER,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
        VALUES('MAT',?,?,?, '5', ?,?,?, ?,?,?, ?,?, ?, 'web', GETDATE())""",
        ymd, seq, int(sid), cust, item, -abs(float(qty)), float(cost), float(amt), float(vat),
        (sheet or None), (wo or None), "유상사급 매출출고")

@router.post("/api/saleout/save")
def saleout_save(payload: dict = Body(...)):
    """판매출고 등록/수정 → nx.saleout_maint(tag='5', 매출 amt/vat) + ★Phase4 stock_ledger −MAT(tag5) 재고제거.
    ★무상거래처(문영/경성)는 매출 아님 → 차단(무상사급이동 /api/sagub/move 사용). 사급단가 자동(override 가능).
    출고SEQ(maint_seq)=출고증번호별 max+1. 불출=−수량. 외주처·품번·수량 필수."""
    rid = payload.get("id")
    cust = str(payload.get("out_cust", "")).strip()
    item = str(payload.get("item_code", "")).strip()
    sheet = str(payload.get("sheet_no", "")).strip()
    remarks = str(payload.get("remarks", "")).strip()
    wo = str(payload.get("work_order", "")).strip()
    split = str(payload.get("split_work_order", "")).strip()
    out_ymd = str(payload.get("out_ymd", "")).strip()
    cost_override = payload.get("cost")
    try:
        qty = abs(float(payload.get("out_qty")))
    except Exception:
        raise HTTPException(400, "출고수량(숫자) 필수")
    if not cust or not item:
        raise HTTPException(400, "외주처·품번 필수")
    cn = _nx(); cur = cn.cursor()
    try:
        if not out_ymd:
            cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)"); out_ymd = cur.fetchone()[0]
        # ★Phase4 무상 차단: 무상거래처(문영/경성)는 매출 아님(창고이동) → 사급이동으로 처리
        if _is_free_sagub(cur, cust, out_ymd):
            raise HTTPException(400, "무상사급 거래처는 매출출고가 아닙니다 — 무상사급이동(/api/sagub/move)으로 처리하세요.")
        # 사급단가: override 있으면 사용, 없으면 자동조회
        cost = float(cost_override) if (cost_override not in (None, "")) else _sagub_price(cur, item, cust, out_ymd)
        amt = float(int(qty * cost))          # truncate(qty*cost) — 레거시 산식
        vat = float(int(amt * 0.1))           # truncate(amt*0.1)
        ledger_qty = -qty                      # 판매출고=재고 감소(소비)
        if rid:
            is_closed = _sale_close_lookup(cur)   # ★작업1 마감잠금: 기존/신규 기간 모두 매출마감이면 수정불가
            cur.execute("SELECT cust_code, maint_ymd FROM nx.saleout_maint WHERE id=? AND maint_tag='5'", int(rid))
            ex = cur.fetchone()
            if ex and is_closed(ex[0], ex[1]):
                raise HTTPException(409, "매출마감된 자료는 수정할 수 없습니다.")
            if is_closed(cust, out_ymd):
                raise HTTPException(409, f"매출마감된 기간({out_ymd})으로는 수정할 수 없습니다.")
            cur.execute("""UPDATE nx.saleout_maint SET maint_ymd=?,cust_code=?,sheet_no=?,mat_code=?,maint_qty=?,
                  maint_cost=?,maint_amt=?,maint_vat=?,remarks=?,work_order=?,split_work_order=?,upd_user='web',update_datetime=getdate()
                WHERE id=? AND maint_tag='5'""", out_ymd, cust, sheet, item, ledger_qty, cost, amt, vat, remarks, wo, split, int(rid))
            _saleout_led_post(cur, int(rid), out_ymd, cust, item, qty, cost, amt, vat, sheet, wo)  # ★재고 −MAT 재게시
        else:
            if sheet:
                cur.execute("SELECT ISNULL(MAX(maint_seq),0)+1 FROM nx.saleout_maint WHERE sheet_no=?", sheet)
            else:
                cur.execute("SELECT ISNULL(MAX(maint_seq),0)+1 FROM nx.saleout_maint WHERE maint_ymd=?", out_ymd)
            seq = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO nx.saleout_maint(maint_ymd,maint_seq,maint_tag,cust_code,sheet_no,mat_code,maint_qty,
                  maint_cost,maint_amt,maint_vat,remarks,work_order,split_work_order,print_flag,insert_user_id,insert_datetime)
                OUTPUT INSERTED.id VALUES(?,?,'5',?,?,?,?,?,?,?,?,?,?,'0','web',getdate())""",
                out_ymd, seq, cust, sheet, item, ledger_qty, cost, amt, vat, remarks, wo, split)
            newid = int(cur.fetchone()[0])
            _saleout_led_post(cur, newid, out_ymd, cust, item, qty, cost, amt, vat, sheet, wo)  # ★재고 −MAT 게시
        cn.commit()
        return {"ok": True, "cost": cost, "amt": amt, "vat": vat}
    finally:
        cn.close()

@router.post("/api/saleout/delete")
def saleout_delete(payload: dict = Body(...)):
    """판매출고 삭제(단건/복수 ids). tag='5'만."""
    ids = payload.get("ids") or ([payload["id"]] if payload.get("id") else [])
    if not ids:
        raise HTTPException(400, "id/ids 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        ph = ",".join("?" * len(ids))
        is_closed = _sale_close_lookup(cur)   # ★작업1 마감잠금: 매출마감건 삭제차단
        cur.execute(f"SELECT id, cust_code, maint_ymd FROM nx.saleout_maint WHERE maint_tag='5' AND id IN ({ph})", *[int(x) for x in ids])
        locked = [str(r[0]) for r in cur.fetchall() if is_closed(r[1], r[2])]
        if locked:
            raise HTTPException(409, f"매출마감된 자료는 삭제할 수 없습니다(id: {','.join(locked)}).")
        cur.execute(f"DELETE FROM nx.saleout_maint WHERE maint_tag='5' AND id IN ({ph})", *[int(x) for x in ids])
        n = cur.rowcount
        for x in ids:
            _saleout_led_del(cur, int(x))   # ★Phase4: 링크된 재고 −MAT 원장행 동반삭제
        cn.commit()
        return {"ok": True, "deleted": n}
    finally:
        cn.close()

@router.post("/api/saleout/copy")
def saleout_copy(payload: dict = Body(...)):
    """복사: 선택 건 복제(출고SEQ 재채번)."""
    rid = payload.get("id")
    if not rid:
        raise HTTPException(400, "id 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT maint_ymd,cust_code,sheet_no,mat_code,maint_qty,maint_cost,maint_amt,maint_vat,remarks,work_order,split_work_order
            FROM nx.saleout_maint WHERE id=? AND maint_tag='5'""", int(rid))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "원본 없음")
        is_closed = _sale_close_lookup(cur)   # ★마감잠금(규칙B): 마감된 기간으로 복사 차단
        if is_closed(r[1], r[0]):
            raise HTTPException(409, f"매출마감된 기간({r[0]})으로는 복사할 수 없습니다.")
        cur.execute("SELECT ISNULL(MAX(maint_seq),0)+1 FROM nx.saleout_maint WHERE sheet_no=?", r[2])
        seq = int(cur.fetchone()[0])
        cur.execute("""INSERT INTO nx.saleout_maint(maint_ymd,maint_seq,maint_tag,cust_code,sheet_no,mat_code,maint_qty,
              maint_cost,maint_amt,maint_vat,remarks,work_order,split_work_order,print_flag,insert_user_id,insert_datetime)
            OUTPUT INSERTED.id VALUES(?,?,'5',?,?,?,?,?,?,?,?,?,?,'0','web',getdate())""",
            r[0], seq, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10])
        newid = int(cur.fetchone()[0])
        _saleout_led_post(cur, newid, r[0], r[1], r[3], abs(float(r[4] or 0)), r[5], r[6], r[7], r[2], r[9])  # ★재고 −MAT 게시
        cn.commit()
        return {"ok": True}
    finally:
        cn.close()

@router.post("/api/saleout/carryover")
def saleout_carryover(payload: dict = Body(...)):
    """이월처리: 선택 건 출고일자→이월일자 이동 + carryover_ymd 기록."""
    ids = payload.get("ids") or []
    ymd = str(payload.get("carryover_ymd", "")).strip()
    if not ids or not ymd:
        raise HTTPException(400, "선택 건(ids)·이월일자 필요")
    cn = _nx(); cur = cn.cursor()
    try:
        ph = ",".join("?" * len(ids))
        is_closed = _sale_close_lookup(cur)   # ★마감잠금(규칙B): 원본기간·이월대상기간 어느쪽이든 마감이면 이월 차단
        cur.execute(f"SELECT id, cust_code, maint_ymd FROM nx.saleout_maint WHERE maint_tag='5' AND id IN ({ph})", *[int(x) for x in ids])
        locked = [str(r[0]) for r in cur.fetchall() if is_closed(r[1], r[2]) or is_closed(r[1], ymd)]
        if locked:
            raise HTTPException(409, f"매출마감된 기간이 포함되어 이월할 수 없습니다(id: {','.join(locked)}).")
        cur.execute(f"""UPDATE nx.saleout_maint SET carryover_ymd=maint_ymd, maint_ymd=?, upd_user='web', update_datetime=getdate()
            WHERE maint_tag='5' AND id IN ({ph})""", ymd, *[int(x) for x in ids])
        n = cur.rowcount
        for x in ids:  # ★Phase4: 링크된 재고 −MAT 원장 출고일자 동반이월
            cur.execute("UPDATE nx.stock_ledger SET MAINT_YMD=? WHERE STOCK_POINT='MAT' AND MAINT_TAG='5' AND MAINT_GROUP_SEQ=?", ymd, int(x))
        cn.commit()
        return {"ok": True, "carried": n, "to": ymd}
    finally:
        cn.close()

# ===================== 출하실적등록/LG송장 (w_pr_input_040 복원, nx.sale_dtl + nx.lg_songjang_dtl) =====================
@router.get("/api/lgsale/list")
def lgsale_list(fr: str = Query(""), to: str = Query(""), wo: str = Query(""), item: str = Query(""), fin: str = Query(""), limit: int = Query(800)):
    """출하실적 목록 + LG송장 발행상태. fin: 0미발행/1발행/공백전체. 제번(work_order)·품번 필터."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if fr: w.append("s.sale_ymd>=?"); p.append(fr)
        if to: w.append("s.sale_ymd<=?"); p.append(to)
        if wo: w.append("s.work_order LIKE ?"); p.append(f"%{wo}%")
        if item: w.append("s.item_code LIKE ?"); p.append(f"%{item}%")
        if fin: w.append("ISNULL(s.songjang_print_flag,'0')=?"); p.append(fin)
        cur.execute(f"""SELECT TOP {int(limit)} s.id, s.work_order, s.split_work_order, s.item_code,
              ISNULL(i.ITEM_DESC,'') itemnm, s.sale_ymd, s.sale_hms, s.sale_qty,
              ISNULL(s.songjang_print_flag,'0') print_flag, s.songjang_maint_ymd, s.songjang_maint_seq, s.sheet_no,
              ISNULL(s.remarks,'') remarks, s.insert_user_id, s.insert_datetime
            FROM nx.sale_dtl s LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=s.item_code
            WHERE {' AND '.join(w)} ORDER BY s.sale_ymd DESC, s.sale_hms DESC, s.id DESC""", *p)
        cols = [d[0] for d in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        cn.close()

# ★출하(−ASY) 결선: 출하실적(nx.sale_dtl) → stock_ledger −ASY(tag 'J', MAINT_GROUP_SEQ=sale_dtl id 링크). 완성(+ASY)과 정합.
def _lgsale_led_del(cur, sid):
    cur.execute("DELETE FROM nx.stock_ledger WHERE STOCK_POINT='ASY' AND MAINT_TAG='J' AND MAINT_GROUP_SEQ=?", int(sid))
    # ★제품재고조회(_salesstock)는 SA_T_STOCK_MAINT를 읽음 → 출하분 미러행도 함께 제거(링크=REMARKS 토큰)
    try: cur.execute("DELETE FROM nx.SA_T_STOCK_MAINT WHERE MAINT_TAG='J' AND INSERT_WINDOW='lgsale' AND REMARKS=?", f"출하#{int(sid)}")
    except Exception: pass

def _lgsale_led_post(cur, sid, ymd, item, qty, wo):
    _lgsale_led_del(cur, sid)   # 수정 시 기존 링크행 제거 후 재게시(1행)
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
    seq = cur.fetchone()[0]
    cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_GROUP_SEQ,MAINT_TAG,ITEM_CODE,WORK_ORDER,MAINT_QTY,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
        VALUES('ASY',?,?,?, 'J', ?,?,?, '출하(−ASY)','web',GETDATE())""",
        ymd, seq, int(sid), item, (wo or None), -abs(float(qty)))
    # ★F-출하: 제품재고조회 원천(SA_T_STOCK_MAINT tag J, −)에도 동반쓰기 → 출하실적 등록시 제품재고 차감 반영(사용자 확정 (a))
    #   sid 링크=REMARKS '출하#{sid}'로 멱등(수정/삭제시 위 _del이 제거). nx.sale_dtl 기반이라 sale040(SA_T_SALE_DTL)과 이중계상 없음.
    try:
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
        msq = int(cur.fetchone()[0] or 1)
        cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT(MAINT_YMD,MAINT_SEQ,MAINT_TAG,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_VAT,MAINT_AMT,
              WORK_ORDER,REMARKS,INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW)
              VALUES(?,?, 'J', ?,?,0,0,0,?,?,'web',GETDATE(),'lgsale')""",
            ymd, msq, item, -abs(float(qty)), (wo or None), f"출하#{int(sid)}")
    except Exception: pass

@router.post("/api/lgsale/save")
def lgsale_save(payload: dict = Body(...)):
    """출하실적 등록/수정. 발행완료 건은 수정불가. ★출하=stock_ledger −ASY(tag 'J') 동반(완성 +ASY과 정합). _nx_tx 원자성."""
    rid = payload.get("id")
    wo = str(payload.get("work_order", "")).strip()
    split = str(payload.get("split_work_order", "")).strip()
    item = str(payload.get("item_code", "")).strip()
    remarks = str(payload.get("remarks", "")).strip()
    try:
        qty = float(payload.get("sale_qty"))
    except Exception:
        raise HTTPException(400, "출하수량(숫자) 필수")
    if not wo or not item:
        raise HTTPException(400, "제번·품번 필수")
    cn = _nx_tx(); cur = cn.cursor()   # ★원자성: sale_dtl + −ASY 원장 동일 트랜잭션
    try:
        if rid:
            cur.execute("""UPDATE nx.sale_dtl SET work_order=?,split_work_order=?,item_code=?,sale_qty=?,remarks=?
                WHERE id=? AND ISNULL(songjang_print_flag,'0')='0'""", wo, split, item, qty, remarks, int(rid))
            if cur.rowcount == 0:
                raise HTTPException(409, "LG송장 발행완료 건은 수정 불가(먼저 송장취소)")
            cur.execute("SELECT sale_ymd FROM nx.sale_dtl WHERE id=?", int(rid))
            sy = str(cur.fetchone()[0] or "").strip()
            _lgsale_led_post(cur, int(rid), sy, item, qty, wo)   # ★재고 −ASY 재게시
        else:
            cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6), RIGHT(CONVERT(varchar(14),GETDATE(),120),6)")
            ymd, hms = cur.fetchone()
            cur.execute("""INSERT INTO nx.sale_dtl(work_order,split_work_order,item_code,sale_ymd,sale_hms,sale_qty,songjang_print_flag,remarks,insert_user_id,insert_datetime)
                OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,'0',?,'web',getdate())""", wo, split, item, ymd, hms, qty, remarks)
            newid = int(cur.fetchone()[0])
            _lgsale_led_post(cur, newid, ymd, item, qty, wo)     # ★재고 −ASY 게시
        cn.commit()
        return {"ok": True}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/lgsale/delete")
def lgsale_delete(payload: dict = Body(...)):
    """출하실적 삭제(미발행만). 발행건은 송장취소 먼저. ★링크된 −ASY 원장 동반삭제."""
    rid = payload.get("id")
    if not rid:
        raise HTTPException(400, "id 필요")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        cur.execute("DELETE FROM nx.sale_dtl WHERE id=? AND ISNULL(songjang_print_flag,'0')='0'", int(rid))
        n = cur.rowcount
        if n == 0:
            cn.rollback()
            raise HTTPException(409, "발행완료 건은 삭제 불가(송장취소 먼저)")
        _lgsale_led_del(cur, int(rid))   # ★링크 −ASY 동반삭제
        cn.commit()
        return {"ok": True, "deleted": n}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/lgsale/issue")
def lgsale_issue(payload: dict = Body(...)):
    """LG송장 발행(복원 세만틱): 선택 출하실적(미발행) → ①sale_dtl 4컬럼 세팅('1'/발행일/채번/송장번호) ②lg_songjang_dtl INSERT.
    송장번호=발행일+채번. 채번=당일 max(songjang_maint_seq)+1 (우리방식). 여러건=동일 송장번호로 묶음."""
    ids = payload.get("ids") or []
    if not ids:
        raise HTTPException(400, "발행할 출하실적을 선택하세요.")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        ymd = cur.fetchone()[0]
        cur.execute("SELECT ISNULL(MAX(songjang_maint_seq),0)+1 FROM nx.sale_dtl WHERE songjang_maint_ymd=?", ymd)
        seq = int(cur.fetchone()[0])
        sheet = f"{ymd}{seq:04d}"   # 송장번호
        issued = 0
        for rid in ids:
            cur.execute("""SELECT work_order, split_work_order, item_code, sale_qty
                FROM nx.sale_dtl WHERE id=? AND ISNULL(songjang_print_flag,'0')='0'""", int(rid))
            row = cur.fetchone()
            if not row:
                continue  # 이미 발행/없음 skip
            wo, split, item, qty = row
            cur.execute("""UPDATE nx.sale_dtl SET songjang_print_flag='1', songjang_maint_ymd=?, songjang_maint_seq=?, sheet_no=? WHERE id=?""",
                        ymd, seq, sheet, int(rid))
            cur.execute("""INSERT INTO nx.lg_songjang_dtl(maint_ymd,maint_seq,sheet_no,work_order,split_work_order,item_code,sale_qty,sale_dtl_id,insert_user_id,insert_datetime)
                VALUES(?,?,?,?,?,?,?,?,'web',getdate())""", ymd, seq, sheet, wo, split or "", item, float(qty or 0), int(rid))
            issued += 1
        if issued == 0:
            raise HTTPException(409, "발행 가능한(미발행) 건이 없습니다.")
        cn.commit()
        return {"ok": True, "issued": issued, "sheet_no": sheet}
    finally:
        cn.close()

@router.post("/api/lgsale/cancel")
def lgsale_cancel(payload: dict = Body(...)):
    """LG송장 취소(복원 세만틱, w_pu_output_015 역로직): sale_dtl 4컬럼 clear + lg_songjang_dtl DELETE.
    sheet(송장번호) 단위 일괄취소 또는 id 단위."""
    sheet = str(payload.get("sheet_no", "")).strip()
    rid = payload.get("id")
    cn = _nx(); cur = cn.cursor()
    try:
        if sheet:
            cur.execute("UPDATE nx.sale_dtl SET songjang_print_flag='0', songjang_maint_ymd=null, songjang_maint_seq=null, sheet_no=null WHERE sheet_no=?", sheet)
            n = cur.rowcount
            cur.execute("DELETE FROM nx.lg_songjang_dtl WHERE sheet_no=?", sheet)
        elif rid:
            cur.execute("UPDATE nx.sale_dtl SET songjang_print_flag='0', songjang_maint_ymd=null, songjang_maint_seq=null, sheet_no=null WHERE id=?", int(rid))
            n = cur.rowcount
            cur.execute("DELETE FROM nx.lg_songjang_dtl WHERE sale_dtl_id=?", int(rid))
        else:
            raise HTTPException(400, "sheet_no 또는 id 필요")
        cn.commit()
        return {"ok": True, "canceled": n}
    finally:
        cn.close()


# ===================== 출하실적등록 (레거시 w_pr_input_040) =====================
# 제번단위 출하실적. 드래그 선택 → 확인(F12) = 완제품(ASSY)재고 있는 만큼만 출하처리.
#   그리드: PR_T_PLAN_ITEM_DTL(계획) + 실적 4종(생산/검사/출하/이동) + ASSY재고
#   확인:   SA_T_SALE_DTL(+) · SA_T_STOCK_MAINT(TAG='J', 음수) · SA_T_ITEM_STOCK(차감)
#   ★쓰기는 nx 만(§1-1). 음수재고 발생시 롤백(레거시 동일).
S040 = "PARTNER_ERP_TEST3.nx"

@router.get("/api/sale040/lines")
def sale040_lines(src: str = Query("nx")):
    """라인 드롭다운 = CM_M_MASTER_DETAIL(KIND_CODE='PR003') + 계획에 실제 쓰인 코드."""
    SCH = "PARTNER_ERP.dbo" if str(src).strip() == "live" else "PARTNER_ERP_TEST3.nx"
    cn = _conn() if str(src).strip() == "live" else _nx()
    cur = cn.cursor()
    try:
        cur.execute(f"""SELECT DETAIL_CODE, REPLACE(REPLACE(ISNULL(DETAIL_DESC,''),CHAR(13),''),CHAR(10),'')
                         FROM {SCH}.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR003' ORDER BY DETAIL_CODE""")
        nm = {str(a).strip(): str(b).strip() for a, b in cur.fetchall()}
        cur.execute(f"""SELECT DISTINCT LINE_NO FROM {SCH}.PR_T_PLAN_ITEM_DTL
                        WHERE ISNULL(LINE_NO,'')<>'' AND PLAN_YMD>=CONVERT(varchar(6),DATEADD(month,-3,getdate()),12)""")
        for r in cur.fetchall():
            c = str(r[0]).strip()
            nm.setdefault(c, c)
        return {"rows": [{"code": c, "nm": (nm[c] or c)} for c in sorted(nm)]}
    finally:
        cn.close()

def _s040_dates(from_ymd, gigan):
    d0 = datetime.strptime(_d6(from_ymd) or datetime.now().strftime("%y%m%d"), "%y%m%d")
    return [(d0 + timedelta(days=i)).strftime("%y%m%d") for i in range(max(1, int(gigan or 1)))]

def _s040_shift(ymd, n):
    """YYMMDD 를 n 일 이동. 레거시 convert(varchar,convert(datetime,<ymd>,12)+n,12) 와 동일."""
    return (datetime.strptime(ymd, "%y%m%d") + timedelta(days=int(n))).strftime("%y%m%d")

@router.get("/api/sale040/grid")
def sale040_grid(from_ymd: str = Query(""), gigan: int = Query(4), line: str = Query(""),
                 wo: str = Query(""), item: str = Query(""), src: str = Query("nx"),
                 limit: int = Query(4000)):
    """출하실적등록 그리드. 그레인=(제번, 분할제번, 도번)."""
    dates = _s040_dates(from_ymd, gigan)
    d1, d2 = dates[0], dates[-1]
    # ★소스 토글(키팅·410 과 동일): nx=우리 재현 / live=레거시 라이브 직독(대사용, 읽기전용)
    SCH = "PARTNER_ERP.dbo" if str(src).strip() == "live" else "PARTNER_ERP_TEST3.nx"
    cn = _conn() if str(src).strip() == "live" else _nx()
    cur = cn.cursor()
    try:
        # ── 계획원천 = 레거시 dw_pr_input_040_t1 3-UNION ──────────────────
        #   b1 엘지계획   sa_t_plan_item_dtl              (data_gubun=1)
        #   b2 예외생산   pr_t_plan_input                 (분할제번 없음 → work_order 로 대체)
        #   b3 전일계획잔여 sa_t_plan_dtl_daily × pr_m_model_bom (del_flag=1)
        #   계획수량 = ceiling(plan_qty × use_qty × prod_rate/100)
        #   대상 = (work_code LIKE 'A%' OR in_cust_code 존재) AND pr_m_mat 에 없음
        # ※ nx 에는 SA_T_PLAN_DTL_DAILY 가 없어 b3 는 live 에서만 적용.
        has_daily = str(src).strip() == "live"

        f_item = "%%%s%%" % item.strip() if item.strip() else None
        f_wo = "%%%s%%" % wo.strip() if wo.strip() else None
        f_line = line.strip() if (line.strip() and line.strip() != '%') else None

        def _flt(alias_item, alias_wo, alias_swo, alias_line):
            """공통 화면필터(품목/제번/라인) — 브랜치별 컬럼명이 달라 별칭을 받는다."""
            cc, pp = [], []
            if f_item: cc.append("%s LIKE ?" % alias_item); pp.append(f_item)
            if f_wo:
                cc.append("(%s LIKE ? OR %s LIKE ?)" % (alias_wo, alias_swo)); pp += [f_wo, f_wo]
            if f_line: cc.append("ISNULL(%s,'')=?" % alias_line); pp.append(f_line)
            return ("".join(" AND " + c for c in cc), pp)

        # 대상품목 필터(레거시 동일) — pr_m_mat 제외
        # ※ 'A%' 의 % 때문에 %-포맷 금지. 함수로 조립한다.
        def TGT(col):
            # ★레거시 dw_pr_input_040_t1 원문 조건 그대로:
            #     ((work_code like 'A%') or (in_cust_code like '%%'))  ← in_cust_code 는 NULL 만 배제
            #   and isnull((select '2' from pr_m_mat where mat_code=col),'1') like '1'   ← 자재 제외
            # ★2026-08-24 SQL 의 like '%%' 는 NULL 만 걸러내고 빈문자열('')은 통과시킨다.
            #   ISNULL(...)>'' 로 쓰면 빈문자열까지 배제 → 사내 P1(in_cust_code='') 1,284건이
            #   통째로 누락되어 계획수량이 레거시보다 적게 나왔다. IS NOT NULL 이 정답.
            return ("(c.WORK_CODE LIKE 'A" + "%" + "' OR c.IN_CUST_CODE IS NOT NULL)"
                    " AND NOT EXISTS(SELECT 1 FROM {SCH}.PR_M_MAT m WITH(NOLOCK)"
                    " WHERE m.MAT_CODE=" + col + ")")
        # ★2026-08-24 작업처(work_center) — 레거시 dw_pr_input_040_t1 3단 fallback 이식.
        #   ① in_cust_code 있으면 거래처명  ② work_code(단 'P1' 제외)의 작업명
        #   ③ 둘 다 없으면(=사내 P1) 첫 공정(PROC_SEQ 최소)의 GAGONG_PROC_DESC → '03라인' 등
        #   화면 '작업처' 컬럼이 05라인/MTS/이젠터/대원산업 으로 나오는 근거.
        def WCTR(itemcol):
            return ("ISNULL((CASE WHEN c.IN_CUST_CODE>'' THEN"
                    " (SELECT cust_desc FROM {SCH}.CM_M_CUST WHERE cust_code=c.IN_CUST_CODE)"
                    " ELSE (SELECT work_desc FROM {SCH}.PR_M_WORK"
                    " WHERE work_code=c.WORK_CODE AND c.WORK_CODE<>'P1') END),"
                    " (SELECT TOP 1 B1.GAGONG_PROC_DESC"
                    " FROM {SCH}.PR_M_ITEM_PROC_GAGONG A1"
                    " JOIN {SCH}.PR_M_PROC_GAGONG B1 ON A1.GAGONG_PROC_CODE=B1.GAGONG_PROC_CODE"
                    " WHERE A1.ITEM_CODE=" + itemcol + " ORDER BY A1.PROC_SEQ ASC))")
        # 계획수량식(레거시 ceiling)
        def QEXP(q, u):
            return ("CEILING(CONVERT(float," + q + ") * ISNULL(" + u + ",1)"
                    " * ISNULL(c.PROD_RATE,100) / 100)")

        parts, prm = [], []

        # ---- b1 엘지계획 ----
        w1, p1 = _flt("a.C_ITEM_CODE", "a.WORK_ORDER", "ISNULL(a.SPLIT_WORK_ORDER,'')", "a.LINE_NO")
        parts.append(f"""
            SELECT '0' del_flag, '1' data_gubun,
                   a.WORK_ORDER wo, ISNULL(a.SPLIT_WORK_ORDER,a.WORK_ORDER) swo, a.C_ITEM_CODE item,
                   ISNULL(a.LINE_NO,'') line_no, ISNULL(a.MODEL_NO,'') model_no,
                   ISNULL(a.TOOLS_DESC,'') tools, ISNULL(c.WORK_CODE,'') work_code,
                   {WCTR('a.C_ITEM_CODE')} work_center,
                   ISNULL(a.REMARKS2,'') rmk1, ISNULL(a.FROM_SEQ,0) fseq, ISNULL(a.TO_SEQ,0) tseq,
                   ISNULL(a.OUTPUT_HM,'') ohm, a.PLAN_YMD ymd,
                   ISNULL(a.LOT_QTY,0) lot,
                   ISNULL(a.USE_QTY,1) use_qty, ISNULL(c.PROD_RATE,100) prod_rate,
                   ISNULL(a.CHANGE_DAY,'') change_day,
                   {QEXP('a.PLAN_QTY','a.USE_QTY')} planq
              FROM {{SCH}}.SA_T_PLAN_ITEM_DTL a WITH(NOLOCK)
              JOIN {{SCH}}.PR_M_ITEM c WITH(NOLOCK) ON a.C_ITEM_CODE=c.ITEM_CODE
             WHERE a.PLAN_YMD BETWEEN ? AND ?
               AND {TGT('a.C_ITEM_CODE')}{w1}""")
        # ★2026-08-24 레거시 dw_pr_input_040_t1 원문:
        #     where plan_ymd between <기준일> and <컷+10>
        #     plan_qty = sum(case when plan_ymd > <컷> then 0 else ceiling(...) end)
        #   즉 컷 뒤 10일까지 읽되 계획수량엔 안 넣는다(마지막 where plan_qty>0 로 탈락).
        #   컷 = 화면 마지막일자(d2). 화면 일자칸은 d1..d2 만 쓰므로 뒤 10일은 집계에 영향 없음.
        prm += [d1, _s040_shift(d2, 10)] + p1

        # ---- b2 예외생산 (분할제번 컬럼 없음 → work_order) ----
        w2, p2 = _flt("a.ITEM_CODE", "a.WORK_ORDER", "a.WORK_ORDER", "a.LINE_NO")
        parts.append(f"""
            SELECT '0' del_flag,
                   CASE WHEN ISNULL(a.PROD_TAG,'')='PO' THEN '3' ELSE '2' END data_gubun,
                   a.WORK_ORDER wo, a.WORK_ORDER swo, a.ITEM_CODE item,
                   ISNULL(a.LINE_NO,'') line_no, '' model_no,
                   '' tools, ISNULL(c.WORK_CODE,'') work_code,
                   {WCTR('a.ITEM_CODE')} work_center,
                   ISNULL(a.REMARKS,'') rmk1, 0 fseq, 0 tseq,
                   ISNULL(a.OUTPUT_HM,'') ohm, a.PLAN_YMD ymd,
                   ISNULL(a.PLAN_QTY,0) lot,
                   1 use_qty, 100 prod_rate,
                   '' change_day,
                   ISNULL(a.PLAN_QTY,0) planq
              FROM {{SCH}}.PR_T_PLAN_INPUT a WITH(NOLOCK)
              JOIN {{SCH}}.PR_M_ITEM c WITH(NOLOCK) ON a.ITEM_CODE=c.ITEM_CODE
             WHERE a.PLAN_YMD BETWEEN ? AND ?
               AND {TGT('a.ITEM_CODE')}{w2}""")
        prm += [d1, d2] + p2

        # ---- b3 전일계획 잔여(삭제된계획) — live 전용 ----
        if has_daily:
            yst = (datetime.strptime(d1, "%y%m%d") - timedelta(days=1)).strftime("%y%m%d")
            w3, p3 = _flt("b.C_ITEM_CODE", "a.WORK_ORDER", "ISNULL(a.SPLIT_WORK_ORDER,'')", "a.LINE_NO")
            parts.append(f"""
            SELECT '1' del_flag, '1' data_gubun,
                   a.WORK_ORDER wo, ISNULL(a.SPLIT_WORK_ORDER,a.WORK_ORDER) swo, b.C_ITEM_CODE item,
                   ISNULL(a.LINE_NO,'') line_no, ISNULL(a.MODEL_NO,'') model_no,
                   '' tools, ISNULL(c.WORK_CODE,'') work_code,
                   {WCTR('b.C_ITEM_CODE')} work_center,
                   ISNULL(a.REMARKS2,'') rmk1, 0 fseq, 0 tseq,
                   ISNULL(a.OUTPUT_HM,'') ohm, a.PLAN_YMD ymd,
                   ISNULL(a.LOT_QTY,0) lot,
                   ISNULL(b.USE_QTY,1) use_qty, ISNULL(c.PROD_RATE,100) prod_rate,
                   ISNULL(a.CHANGE_DAY,'') change_day,
                   {QEXP('a.PLAN_QTY','b.USE_QTY')} planq
              FROM {{SCH}}.SA_T_PLAN_DTL_DAILY a WITH(NOLOCK)
              JOIN {{SCH}}.PR_M_MODEL_BOM b WITH(NOLOCK)
                   ON a.MODEL_NO=b.MODEL_NO AND a.PLAN_YMD BETWEEN b.MAKE_YMD AND b.TO_APPLY_YMD
              JOIN {{SCH}}.PR_M_ITEM c WITH(NOLOCK) ON b.C_ITEM_CODE=c.ITEM_CODE
             WHERE a.WORK_YMD=? AND a.PLAN_YMD BETWEEN ? AND ?
               AND {TGT('b.C_ITEM_CODE')}{w3}
               AND EXISTS(SELECT 1 FROM {{SCH}}.SA_T_PLAN_DTL_DAILY x WITH(NOLOCK)
                           WHERE x.WORK_YMD=? AND x.WORK_ORDER=a.WORK_ORDER
                             AND ISNULL(x.SPLIT_WORK_ORDER,'')=ISNULL(a.SPLIT_WORK_ORDER,'')
                             AND x.PLAN_YMD>?)
               AND NOT EXISTS(SELECT 1 FROM {{SCH}}.SA_T_PLAN_DTL_DAILY y WITH(NOLOCK)
                           WHERE y.WORK_YMD=CONVERT(varchar,getdate(),12) AND y.WORK_ORDER=a.WORK_ORDER
                             AND ISNULL(y.SPLIT_WORK_ORDER,'')=ISNULL(a.SPLIT_WORK_ORDER,''))""")
            prm += [yst, yst, d2] + p3 + [yst, yst]

        # ★2026-08-24 정렬 = 레거시 dw_pr_input_040_t1 sort 그대로:
        #   plan_ymd, line_no, output_hm, split_work_order, c_item_code (전부 오름차순)
        sql = ("SELECT TOP %d * FROM (\n%s\n) u WHERE u.planq > 0 "
               "ORDER BY u.ymd, u.line_no, u.ohm, u.swo, u.item") % (int(limit) * 8, "\n            UNION ALL\n".join(parts))
        cur.execute(sql.format(SCH=SCH), *prm)
        cols = [d[0] for d in cur.description]
        keyed = {}
        for rr in cur.fetchall():
            r = dict(zip(cols, rr))
            # ★del_flag 는 행 정체성의 일부(레거시 동일): 0=현재계획 / 1=전일 삭제계획.
            #   같은 (제번,도번)이 양쪽에 다 나올 수 있어 키에서 빼면 수량이 2배가 된다.
            k = (r["del_flag"], r["wo"], r["swo"], r["item"])
            g = keyed.get(k)
            if not g:
                g = {"wo": r["wo"], "swo": r["swo"], "item": r["item"], "line_no": r["line_no"],
                     "model_no": r["model_no"], "tools": r["tools"], "work_code": r["work_code"],
                     "work_center": (r.get("work_center") or ""),   # ★작업처(레거시 3단 fallback)
                     "rmk1": r["rmk1"], "fseq": r["fseq"], "tseq": r["tseq"], "ohm": r["ohm"],
                     "org_ymd": r["ymd"], "org_hm": r["ohm"], "del_flag": r["del_flag"],
                     "data_gubun": r["data_gubun"],
                     "use_qty": float(r["use_qty"] or 1), "prod_rate": float(r["prod_rate"] or 100),
                     "change_day": r["change_day"] or '',
                     "lot": 0.0, "days": {}}
                keyed[k] = g
            g["lot"] = max(g["lot"], float(r["lot"] or 0))
            g["days"][r["ymd"]] = g["days"].get(r["ymd"], 0.0) + float(r["planq"] or 0)
        rows = list(keyed.values())
        # 화면 일자칸(d1..d2) — b1 을 컷+10 까지 읽으므로 계획합/표시는 이 범위로 자른다.
        _dset = set(dates)
        if not rows:
            return {"dates": dates, "rows": [], "cnt": 0}

        # ---- 실적 4종 + ASSY재고 (제번·도번 단위) ----
        keys = [(g["wo"], g["swo"], g["item"]) for g in rows]
        items = sorted({g["item"] for g in rows})
        prod = {}; insp = {}; sale = {}; mvin = {}; mvout = {}
        def _chunk(seq, n=600):
            for i in range(0, len(seq), n):
                yield seq[i:i + n]
        for ck in _chunk(items):
            ph = ",".join("?" * len(ck))
            cur.execute(f"""SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(ISNULL(PROD_QTY,0))
                              FROM {SCH}.PR_T_PROD_DTL WITH(NOLOCK)
                             WHERE ITEM_CODE IN ({ph}) AND ISNULL(FINISH_FLAG,'0')='0'
                             GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE""", *ck)
            for a, b, c, v in cur.fetchall(): prod[(a, b, c)] = float(v or 0)
            # 검사수량(QA_T_INSP_DTL)은 이 화면에서 미사용
            pass
            
            cur.execute(f"""SELECT WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(ISNULL(SALE_QTY,0))
                              FROM {SCH}.SA_T_SALE_DTL WITH(NOLOCK)
                             WHERE ITEM_CODE IN ({ph}) AND ISNULL(FINISH_FLAG,'0')='0'
                             GROUP BY WORK_ORDER, ISNULL(SPLIT_WORK_ORDER,''), ITEM_CODE""", *ck)
            for a, b, c, v in cur.fetchall(): sale[(a, b, c)] = float(v or 0)
            # 출하반품(move_tag='3') 은 출하에서 뺀다(레거시 동일)
            cur.execute(f"""SELECT FR_WORK_ORDER, ISNULL(FR_SPLIT_WORK_ORDER,''), ITEM_CODE, SUM(ISNULL(MOVE_QTY,0))
                              FROM {SCH}.SA_T_ITEM_MOVE WITH(NOLOCK)
                             WHERE ITEM_CODE IN ({ph}) AND ISNULL(FR_FINISH_FLAG,'0')='0' AND MOVE_TAG='3'
                             GROUP BY FR_WORK_ORDER, ISNULL(FR_SPLIT_WORK_ORDER,''), ITEM_CODE""", *ck)
            for a, b, c, v in cur.fetchall(): mvout[(a, b, c)] = float(v or 0)
            # ※ 일자별 출하(SALE_YMD)는 쓰지 않는다 — 레거시 dw 에도 sale_ymd 가 없다.
            #   셀 출하수량은 ue_set_dd_color 가 제번 총출하를 계획셀에 배분해 만든다(아래).
        # ★2026-08-25 ASSY재고 = 라이브·nx 잔액 중 '더 최근 갱신본'.
        #   원장 델타 가산은 쓰지 않는다 — 웹은 잔액도 함께 갱신하므로 이중계상이 된다
        #   (실측 SUB1: 라이브잔액 0 + 원장델타 -2 = -2, 정답 0).
        #   웹이 건드린 품목은 nx 가 최신이라 nx 값, 아니면 라이브 값이 잡힌다.
        astk = {}
        for ck in _chunk(items):
            ph = ",".join("?" * len(ck))
            cur.execute(f"""SELECT ITEM_CODE, SUM(STOCK_QTY) FROM (
                              SELECT ISNULL(n.ITEM_CODE,l.ITEM_CODE) ITEM_CODE,
                                     CASE WHEN n.ITEM_CODE IS NULL THEN l.STOCK_QTY
                                          ELSE n.STOCK_QTY END STOCK_QTY
                                FROM (SELECT * FROM PARTNER_ERP_TEST3.nx.SA_T_ITEM_STOCK WITH(NOLOCK) WHERE ITEM_CODE IN ({ph})) n
                                FULL JOIN (SELECT * FROM PARTNER_ERP.dbo.SA_T_ITEM_STOCK WITH(NOLOCK) WHERE ITEM_CODE IN ({ph})) l
                                  ON l.ITEM_CODE=n.ITEM_CODE) u
                            GROUP BY ITEM_CODE""", *(list(ck) + list(ck)))
            for a, v in cur.fetchall(): astk[str(a).strip()] = float(v or 0)
        nm = {}
        for ck in _chunk(items):
            ph = ",".join("?" * len(ck))
            cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM {SCH}.PR_M_ITEM WHERE ITEM_CODE IN ({ph})", *ck)
            for a, b in cur.fetchall(): nm[str(a).strip()] = b

        # 제번 전체계획(조회기간 밖 포함) — 살구색(제번 전량출하) 판정용.
        # ※ 화면 기간만 보면 부분출하도 완료로 보이므로 반드시 제번 전체로 비교한다.
        woplan = {}
        wolist = sorted({(g["wo"], g["swo"], g["item"]) for g in rows})
        for ck in _chunk(wolist, 300):
            oc = " OR ".join(["(a.WORK_ORDER=? AND a.C_ITEM_CODE=?)"] * len(ck))
            pv = []
            for w_, s_, i_ in ck: pv += [w_, i_]
            cur.execute(f"""SELECT a.WORK_ORDER, ISNULL(a.SPLIT_WORK_ORDER,a.WORK_ORDER), a.C_ITEM_CODE,
                                   SUM(CEILING(CONVERT(float,a.PLAN_QTY)*ISNULL(a.USE_QTY,1)
                                               *ISNULL(c.PROD_RATE,100)/100))
                              FROM {SCH}.SA_T_PLAN_ITEM_DTL a WITH(NOLOCK)
                              JOIN {SCH}.PR_M_ITEM c WITH(NOLOCK) ON a.C_ITEM_CODE=c.ITEM_CODE
                             WHERE ({oc})
                             GROUP BY a.WORK_ORDER, ISNULL(a.SPLIT_WORK_ORDER,a.WORK_ORDER),
                                      a.C_ITEM_CODE""", *pv)
            for a_, b_, c_, v in cur.fetchall():
                kk = (str(a_).strip(), str(b_).strip(), str(c_).strip())
                woplan[kk] = woplan.get(kk, 0.0) + float(v or 0)

        out = []
        for g in rows:
            k = (g["wo"], g["swo"], g["item"])
            sq = sale.get(k, 0.0) - mvout.get(k, 0.0)
            # ★2026-08-24 레거시 컷: plan_qty 는 화면일자(d1..d2) 안쪽만 합산한다.
            #   b1 을 컷+10 까지 읽으므로 여기서 안 걸러내면 창 밖 계획까지 더해진다.
            plan_tot = round(sum(v for y, v in g["days"].items() if y in _dset), 0)
            # ── 셀 출하수량 = 레거시 ue_set_dd_color '출하수량 적용' 그대로 ──────────
            #   ll_lot_qty = ceiling(lot_qty × use_qty × prod_rate/100)
            #   ll_qty = sale_qty − (ll_lot_qty − plan_qty)   ← "지난 계획을 차감한 후 적용"
            #   → 조회기간 밖(과거) 계획분만큼을 총출하에서 먼저 빼므로,
            #     과거에 출하된 분은 화면 셀에 나타나지 않는다(레거시 동일 동작).
            #   그 뒤 앞 일자부터: 계획셀 이상이면 계획만큼 채우고(=출하완료), 모자라면 남은 만큼.
            lotq = math.ceil(float(g["lot"] or 0) * float(g.get("use_qty") or 1)
                             * float(g.get("prod_rate") or 100) / 100.0)
            if lotq < plan_tot:
                lotq = plan_tot
            rest = sq - (lotq - plan_tot)
            sd = {}
            for y in dates:
                if rest <= 0:
                    break
                pq = g["days"].get(y, 0.0)
                if pq <= 0:
                    continue
                if rest >= pq:
                    sd[y] = round(pq, 0)     # 그 셀 전량출하 → 살구
                    rest -= pq
                else:
                    sd[y] = round(rest, 0)   # 부분출하
                    rest = 0
            g.update({
                "itemnm": nm.get(g["item"], ''),
                "prod_qty": 0.0,   # ★아래에서 ASSY재고 충당으로 채운다(레거시 동일)
                "sale_qty": round(sq, 0),
                "stock_qty": round(astk.get(g["item"], 0.0), 0),
                "lot": round(g["lot"], 0),
                "plan_qty": plan_tot,
                "wo_plan": round(woplan.get(k, plan_tot), 0),   # 제번 전체계획(살구 판정 기준)
                "sday": sd,
                "days": {y: round(v, 0) for y, v in g["days"].items() if y in _dset},
            })
            # 레거시 마지막 절 where t.plan_qty > 0 — 창 밖 계획만 있는 행은 화면에 안 나온다.
            if plan_tot <= 0:
                continue
            out.append(g)

        # ── 생산실적 = ASSY재고 충당 (레거시 w_pr_input_040 화면스크립트) ──────────
        #   레거시 SQL 의 prod_qty 는 상수 0 이고, 화면에서 ASSY재고를 정렬순서대로
        #   앞 행부터 '미출하계획(계획−출하)' 만큼 채워 넣는다. 그 채워진 값이 생산실적.
        #   → 준비실적처리(키팅)·파트별생산계획(410) 의 재고충당과 같은 방식.
        #   ※ 도번 단위 재고풀을 공유하므로 반드시 화면 정렬순서로 순회해야 한다.
        #     (레거시 sort: plan_ymd, line_no, output_hm, split_work_order, c_item_code)
        _S = lambda v: "" if v is None else str(v)
        out.sort(key=lambda g: (_S(g.get("org_ymd")), _S(g.get("line_no")), _S(g.get("ohm")),
                                _S(g.get("swo") or g.get("wo")), _S(g.get("item"))))
        _pool = {}
        for g in out:
            _pool.setdefault(g["item"], float(g.get("stock_qty") or 0))
        for g in out:
            need = float(g.get("plan_qty") or 0) - float(g.get("sale_qty") or 0)
            if need <= 0:
                continue
            av = _pool.get(g["item"], 0.0)
            if av <= 0:
                continue
            take = min(av, need)
            _pool[g["item"]] = av - take
            g["prod_qty"] = round(take, 0)

        return {"dates": dates, "rows": out, "cnt": len(out)}
    finally:
        cn.close()

@router.post("/api/sale040/confirm")
def sale040_confirm(payload: dict = Body(...)):
    """확인(F12) — 선택 셀을 출하처리. 레거시 w_pr_input_040 ue_save 이식.
       · 출하량 = 계획셀 − 기출하량, 재고 초과분은 재고만큼으로 절삭
       · SA_T_SALE_DTL / SA_T_STOCK_MAINT(TAG='J') / SA_T_ITEM_STOCK 차감
       · 음수재고 발생시 전체 롤백"""
    cells = payload.get("cells") or []
    user = str(payload.get("user") or "웹")[:20]
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    hms = datetime.now().strftime("%H%M%S")
    if not cells:
        return {"ok": False, "msg": "출하처리할 셀을 선택하세요."}
    cn = _nx_tx(); cur = cn.cursor()
    win = 'w_pr_input_040'
    try:
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999) FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
        seq = int(cur.fetchone()[0] or 19999)
        done = []; skipped = []
        # 도번별 재고 캐시(같은 도번 여러 제번 → 순서대로 소진)
        stk = {}
        want_tot = 0      # 요청 총량(재고절삭 전) — 부분출하 안내용
        for c in cells:
            wo = str(c.get("wo") or "").strip()
            swo = str(c.get("swo") or "").strip()
            it = str(c.get("item") or "").strip()
            want = int(float(c.get("qty") or 0))
            if not (wo and it) or want <= 0:
                continue
            want_tot += want
            if it not in stk:
                cur.execute("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", it)
                stk[it] = float(cur.fetchone()[0] or 0)
            avail = stk[it]
            if avail <= 0:
                skipped.append({"wo": swo or wo, "item": it, "why": "영업창고 재고없음"})
                continue
            qty = int(min(want, avail))       # ★재고만큼만 출하
            if qty <= 0:
                skipped.append({"wo": swo or wo, "item": it, "why": "재고부족"})
                continue
            cur.execute("""SELECT TOP 1 ISNULL(ITEM_COST,0) FROM nx.PR_M_ITEM_COST
                            WHERE ITEM_CODE=? AND CUST_CODE IN ('1010','1020')
                              AND COST_TAG IN ('S','E') AND COST_APPLY_YMD<=?
                            ORDER BY COST_APPLY_YMD DESC, CUST_CODE ASC, COST_TAG DESC""", it, ymd)
            cr = cur.fetchone()
            cost = float(cr[0] or 0) if cr else 0.0
            cur.execute("""INSERT INTO nx.SA_T_SALE_DTL
                           (WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,SALE_YMD,SALE_HMS,SALE_QTY,
                            SALE_COST,SALE_AMT,SALE_USER_ID,FINISH_FLAG,LINE_NO,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                            UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           VALUES(?,?,?,?,?,?,?,?,?,'0',?,?,getdate(),?,?,getdate(),?)""",
                        wo, swo, it, ymd, hms, qty, cost, round(cost * qty, 2), user,
                        str(c.get("line_no") or "")[:10], user, win, user, win)
            seq += 1
            cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT
                           (MAINT_YMD,MAINT_SEQ,MAINT_TAG,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,
                            WORK_ORDER,SPLIT_WORK_ORDER,REMARKS,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                            UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           VALUES(?,?,'J',?,?,0,0,?,?,'',?,getdate(),?,?,getdate(),?)""",
                        ymd, seq, it, -qty, wo, swo, user, win, user, win)
            cur.execute("""UPDATE nx.SA_T_ITEM_STOCK
                              SET STOCK_QTY=ISNULL(STOCK_QTY,0)-?, UPDATE_USER_ID=?,
                                  UPDATE_DATETIME=getdate(), UPDATE_WINDOW=?
                            WHERE ITEM_CODE=?""", qty, user, win, it)
            if cur.rowcount == 0:
                cn.rollback()
                return {"ok": False, "msg": "영업창고 재고행이 없습니다(%s)" % it}
            cur.execute("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", it)
            left = float(cur.fetchone()[0] or 0)
            if left < 0:
                cn.rollback()
                return {"ok": False, "msg": "영업창고재고를 차감하는 중 (-)재고 발생 — 제번 %s / 도번 %s" % (swo or wo, it)}
            stk[it] = left
            done.append({"wo": wo, "swo": swo, "item": it, "qty": qty,
                         "cell_ymd": str(c.get("ymd") or ""), "left": left})
        if not done:
            cn.rollback()
            msg = "출하처리된 건이 없습니다."
            if skipped:
                msg += " (" + ", ".join("%s %s:%s" % (x["wo"], x["item"], x["why"]) for x in skipped[:4]) + ")"
            return {"ok": False, "skipped": skipped, "msg": msg}
        cn.commit()
        tot = sum(x["qty"] for x in done)
        msg = "출하처리 %d건 · 수량 %d" % (len(done), tot)
        # 재고가 모자라 일부만 잡힌 경우(6개 계획 → 재고 3개 = 3개만)도 명시한다.
        if want_tot > tot:
            msg += " (요청 %d 중 %d — ASSY재고 부족으로 %d 미처리)" % (want_tot, tot, want_tot - tot)
        if skipped:
            msg += " · 제외 %d건(재고부족)" % len(skipped)
        return {"ok": True, "done": done, "skipped": skipped,
                "want": want_tot, "short": max(0, want_tot - tot), "msg": msg}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/sale040/cancel")
def sale040_cancel(payload: dict = Body(...)):
    """출하취소 — 그 제번·도번·일자의 출하분을 되돌린다(재고 복원)."""
    cells = payload.get("cells") or []
    user = str(payload.get("user") or "웹")[:20]
    if not cells:
        return {"ok": False, "msg": "취소할 셀을 선택하세요."}
    cn = _nx_tx(); cur = cn.cursor()
    win = 'w_pr_input_040'
    try:
        done = []
        for c in cells:
            wo = str(c.get("wo") or "").strip()
            swo = str(c.get("swo") or "").strip()
            it = str(c.get("item") or "").strip()
            y = _d6(str(c.get("ymd") or ""))
            if not (wo and it and y):
                continue
            cur.execute("""SELECT ISNULL(SUM(SALE_QTY),0) FROM nx.SA_T_SALE_DTL
                            WHERE WORK_ORDER=? AND ISNULL(SPLIT_WORK_ORDER,'')=? AND ITEM_CODE=?
                              AND SALE_YMD=? AND ISNULL(FINISH_FLAG,'0')='0'""", wo, swo, it, y)
            q = int(float(cur.fetchone()[0] or 0))
            if q <= 0:
                continue
            cur.execute("""DELETE FROM nx.SA_T_SALE_DTL
                            WHERE WORK_ORDER=? AND ISNULL(SPLIT_WORK_ORDER,'')=? AND ITEM_CODE=?
                              AND SALE_YMD=? AND ISNULL(FINISH_FLAG,'0')='0'""", wo, swo, it, y)
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", y)
            sq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT
                           (MAINT_YMD,MAINT_SEQ,MAINT_TAG,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,
                            WORK_ORDER,SPLIT_WORK_ORDER,REMARKS,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                            UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           VALUES(?,?,'J',?,?,0,0,?,?,'출하취소',?,getdate(),?,?,getdate(),?)""",
                        y, sq, it, q, wo, swo, user, win, user, win)
            cur.execute("""UPDATE nx.SA_T_ITEM_STOCK
                              SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?, UPDATE_USER_ID=?,
                                  UPDATE_DATETIME=getdate(), UPDATE_WINDOW=?
                            WHERE ITEM_CODE=?""", q, user, win, it)
            cur.execute("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.SA_T_ITEM_STOCK WHERE ITEM_CODE=?", it)
            _lf = float(cur.fetchone()[0] or 0)
            done.append({"wo": wo, "swo": swo, "item": it, "ymd": y, "qty": q, "left": _lf})
        if not done:
            cn.rollback()
            return {"ok": False, "msg": "취소할 출하실적이 없습니다."}
        cn.commit()
        return {"ok": True, "done": done,
                "msg": "출하취소 %d건 · 수량 %d" % (len(done), sum(x["qty"] for x in done))}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()


# ===================== 출하실적현황 — 출하단가 수정 (dw_sa_list_010) =====================
# ※CLAUDE.md §1-2 는 "단가는 마감 때만 수정, 그 외 화면은 읽기전용" 이지만,
#   사용자 요청으로 이 화면에서 직접 수정 허용(2026-08-21). 대신 안전장치를 둔다.
#     · 마감된 월(_closed)의 출하건은 거부 — 마감 후 금액 변동 방지
#     · 수정자/수정시각(UPDATE_*)을 남겨 감사추적 가능
#     · 쓰기는 nx 만(§1-1)
#   SA_T_SALE_DTL 에 PK 가 없어 5키로 식별한다
#   (WORK_ORDER+SPLIT_WORK_ORDER+ITEM_CODE+SALE_YMD+SALE_HMS — 실측 중복 0건).
@router.post("/api/shipment/cost")
def shipment_cost(payload: dict = Body(...)):
    """출하단가 수정 → 출하금액(SALE_AMT) 자동 재계산."""
    wo  = str(payload.get("wo") or "").strip()
    swo = str(payload.get("swo") or "").strip()
    it  = str(payload.get("item") or "").strip()
    ymd = _d6(str(payload.get("ymd") or ""))
    hms = str(payload.get("hms") or "").strip().zfill(6)
    user = str(payload.get("user") or "웹")[:20]
    if not (wo and it and ymd and hms):
        return {"ok": False, "msg": "행 식별정보가 부족합니다(제번/도번/일자/시각)."}
    try:
        cost = float(payload.get("cost"))
    except Exception:
        return {"ok": False, "msg": "단가는 숫자로 입력하세요."}
    if cost < 0:
        return {"ok": False, "msg": "단가는 0 이상이어야 합니다."}
    cn = _nx_tx(); cur = cn.cursor()
    try:
        # 마감월 보호 — 마감 후 금액이 바뀌면 원가/매출 집계가 어긋난다
        try:
            if _closed(cur, ymd):
                cn.rollback()
                return {"ok": False,
                        "msg": "마감된 월(20%s-%s)의 출하건은 수정할 수 없습니다." % (ymd[:2], ymd[2:4])}
        except Exception:
            pass
        cur.execute("""SELECT SALE_QTY, SALE_COST, SALE_AMT FROM nx.SA_T_SALE_DTL
                        WHERE WORK_ORDER=? AND ISNULL(SPLIT_WORK_ORDER,'')=? AND ITEM_CODE=?
                          AND SALE_YMD=? AND SALE_HMS=?""", wo, swo, it, ymd, hms)
        r = cur.fetchone()
        if not r:
            cn.rollback()
            return {"ok": False, "msg": "대상 출하건을 찾을 수 없습니다(이미 삭제/변경됨). 새로고침 후 다시 시도하세요."}
        qty = float(r[0] or 0); old = float(r[1] or 0)
        amt = round(cost * qty, 2)
        cur.execute("""UPDATE nx.SA_T_SALE_DTL
                          SET SALE_COST=?, SALE_AMT=?,
                              UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW='dw_sa_list_010'
                        WHERE WORK_ORDER=? AND ISNULL(SPLIT_WORK_ORDER,'')=? AND ITEM_CODE=?
                          AND SALE_YMD=? AND SALE_HMS=?""",
                    cost, amt, user, wo, swo, it, ymd, hms)
        if cur.rowcount != 1:
            cn.rollback()
            return {"ok": False, "msg": "수정 대상이 %d건 — 중단했습니다." % cur.rowcount}
        cn.commit()
        return {"ok": True, "qty": qty, "cost": cost, "amt": amt, "old_cost": old,
                "msg": "출하단가 {:,.2f} → {:,.2f} · 금액 {:,.0f}".format(old, cost, amt)}
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        return {"ok": False, "msg": "수정 실패: %s" % str(e)[:200]}
    finally:
        cn.close()
