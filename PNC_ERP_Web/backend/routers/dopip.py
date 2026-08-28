# -*- coding: utf-8 -*-
"""도입-수입입력(w_pu_stock_c_040, MAINT_TAG='P'/DIVISION='P') · 도입-수출입력(w_pu_stock_c_050, 'Q').
   데이터원 = nx.PU_T_STOCK_MAINT_C (해외 수입/수출, 외환·관세·운임·BL·HS·신고번호). 읽기+쓰기 nx.
   금액(KRW) = ROUND(MAINT_AMT×EXCHANGE_RATE,0,1) 버림(레거시 검증). 금액=수량×단가.
   키=(MAINT_YMD,MAINT_SEQ). 채번: sheet_no=max(division)+1, maint_seq=max(ymd)+1."""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _custnm_map, _d6, _lock_msg, _assert_open

router = APIRouter()

def _kd(kind):
    return ("P", "도입-수입입력") if kind == "pur" else ("Q", "도입-수출입력")

def _dopip_rows(tag, from_ymd, to_ymd, cust, mat, insp, bl, wide):
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["MAINT_TAG=?", "MAINT_YMD BETWEEN ? AND ?"]
        p = [tag, _d6(from_ymd), _d6(to_ymd)]
        if cust.strip(): w.append("CUST_CODE=?"); p.append(cust.strip())
        if mat.strip():  w.append("MAT_CODE LIKE ?"); p.append(f"%{mat.strip()}%")
        if insp.strip(): w.append("INSP_SEQ LIKE ?"); p.append(f"%{insp.strip()}%")
        if bl.strip():   w.append("BL_SEQ LIKE ?"); p.append(f"%{bl.strip()}%")
        cur.execute(f"""SELECT MAINT_YMD, MAINT_SEQ, CUST_CODE, MAT_CODE, MAINT_QTY, CURRENCY, MAINT_COST, MAINT_AMT,
              ROUND(MAINT_AMT*EXCHANGE_RATE,0,1) AS KRW, EXCHANGE_RATE, ISNULL(REMARKS,''),
              CUSTOMS_DUTIES, TRANSPORTATION_FATE, TAX_TABLE, ISNULL(INSP_SEQ,''), ISNULL(BL_SEQ,''), ISNULL(HS_CODE,''),
              ISNULL(SHEET_NO,0)
          FROM nx.PU_T_STOCK_MAINT_C
          WHERE {' AND '.join(w)}
          ORDER BY MAINT_YMD, CUST_CODE, INSP_SEQ, MAINT_SEQ""", *p)
        rows = []; cch = set()
        for r in cur.fetchall():
            d = {"ymd": str(r[0]).strip(), "seq": int(r[1] or 0), "cust": str(r[2] or '').strip(), "mat": str(r[3] or '').strip(),
                 "qty": float(r[4] or 0), "cur": str(r[5] or '').strip(), "cost": float(r[6] or 0),
                 "amt": float(r[7] or 0), "krw": float(r[8] or 0), "rate": float(r[9] or 0), "remarks": r[10],
                 "sheet": int(r[17] or 0)}
            if wide:
                d.update({"duty": float(r[11] or 0), "fare": float(r[12] or 0), "tax": float(r[13] or 0),
                          "insp": str(r[14] or '').strip(), "bl": str(r[15] or '').strip(), "hs": str(r[16] or '').strip()})
            cch.add(d["cust"]); rows.append(d)
        nm = _custnm_map(cur, cch)
        for d in rows: d["cust_nm"] = nm.get(d["cust"], d["cust"])
        tot = {"cnt": len(rows), "qty": sum(d["qty"] for d in rows),
               "amt": sum(d["amt"] for d in rows), "krw": sum(d["krw"] for d in rows)}
        return {"rows": rows, "tot": tot}
    finally:
        cn.close()

@router.get("/api/dopip/purchase")
def dopip_purchase(from_ymd: str = Query(""), to_ymd: str = Query(""), cust: str = Query(""),
                   mat: str = Query(""), insp: str = Query(""), bl: str = Query("")):
    return _dopip_rows("P", from_ymd, to_ymd, cust, mat, insp, bl, wide=True)

@router.get("/api/dopip/sale")
def dopip_sale(from_ymd: str = Query(""), to_ymd: str = Query(""), cust: str = Query(""), mat: str = Query("")):
    return _dopip_rows("Q", from_ymd, to_ymd, cust, mat, "", "", wide=False)

@router.post("/api/dopip/save")
def dopip_save(p: dict = Body(...)):
    """추가(seq=0)/수정(seq>0). 금액=수량×단가 자동. 채번=sheet_no(division)·maint_seq(ymd)."""
    kind = str(p.get("kind", "pur"))
    tag, _ = _kd(kind)
    ymd = _d6(str(p.get("ymd", "")).strip())
    if len(ymd) != 6: raise HTTPException(400, "일자(YYMMDD) 필요")
    cust = str(p.get("cust", "")).strip(); mat = str(p.get("mat", "")).strip()
    if not cust or not mat: raise HTTPException(400, "거래처·품목번호 필수")
    qty = float(p.get("qty") or 0); cost = float(p.get("cost") or 0)
    amt = round(qty * cost, 4)
    cur_ccy = str(p.get("cur", "USD")).strip() or "USD"
    rate = float(p.get("rate") or 0)
    remarks = str(p.get("remarks", "")).strip()
    duty = float(p.get("duty") or 0); fare = float(p.get("fare") or 0); tax = float(p.get("tax") or 0)
    insp = str(p.get("insp", "")).strip(); bl = str(p.get("bl", "")).strip(); hs = str(p.get("hs", "")).strip()
    seq = int(p.get("seq") or 0)
    cn = _nx(); c = cn.cursor()
    try:
        lm = _lock_msg(c, ymd)   # ★공통 마감잠금
        if lm: raise HTTPException(400, lm)
        if seq > 0:   # 수정
            c.execute("""UPDATE nx.PU_T_STOCK_MAINT_C SET CUST_CODE=?, MAT_CODE=?, MAINT_QTY=?, MAINT_AMT=?,
                  CURRENCY=?, MAINT_COST=?, EXCHANGE_RATE=?, REMARKS=?, CUSTOMS_DUTIES=?, TRANSPORTATION_FATE=?,
                  TAX_TABLE=?, INSP_SEQ=?, BL_SEQ=?, HS_CODE=?, UPDATE_DATETIME=getdate(), UPDATE_USER_ID='web'
                WHERE MAINT_YMD=? AND MAINT_SEQ=? AND MAINT_TAG=?""",
                cust, mat, qty, amt, cur_ccy, cost, rate, remarks, duty, fare, tax, insp, bl, hs, ymd, seq, tag)
            if c.rowcount == 0: raise HTTPException(404, "수정 대상 없음")
            cn.commit(); return {"ok": True, "mode": "update", "ymd": ymd, "seq": seq}
        # 추가: 채번
        nseq = int(c.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.PU_T_STOCK_MAINT_C WHERE MAINT_YMD=?", ymd).fetchone()[0])
        sheet = int(c.execute("SELECT ISNULL(MAX(SHEET_NO),0)+1 FROM nx.PU_T_STOCK_MAINT_C WHERE DIVISION=?", tag).fetchone()[0])
        c.execute("""INSERT INTO nx.PU_T_STOCK_MAINT_C
              (MAINT_YMD,MAINT_SEQ,MAINT_TAG,DIVISION,SHEET_NO,CUST_CODE,MAT_CODE,MAINT_QTY,MAINT_AMT,
               CURRENCY,MAINT_COST,EXCHANGE_RATE,REMARKS,CUSTOMS_DUTIES,TRANSPORTATION_FATE,TAX_TABLE,
               INSP_SEQ,BL_SEQ,HS_CODE,INSERT_DATETIME,INSERT_USER_ID)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),'web')""",
            ymd, nseq, tag, tag, sheet, cust, mat, qty, amt, cur_ccy, cost, rate, remarks, duty, fare, tax, insp, bl, hs)
        cn.commit(); return {"ok": True, "mode": "insert", "ymd": ymd, "seq": nseq, "sheet": sheet}
    finally:
        cn.close()

@router.get("/api/dopip/vendors")
def dopip_vendors(kind: str = Query("pur"), q: str = Query("")):
    """도입 거래처 오토컴플리트(해당 division 도입이력에 등장한 거래처만). 거래처 먼저 선택용."""
    tag, _ = _kd(kind); qq = f"%{q.strip()}%"
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT TOP 40 a.CUST_CODE, MAX(ISNULL(c.CUST_DESC,'')) nm, MAX(a.MAINT_YMD) lastymd
              FROM nx.PU_T_STOCK_MAINT_C a LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=a.CUST_CODE
              WHERE a.DIVISION=? AND a.CUST_CODE>'' AND (a.CUST_CODE LIKE ? OR ISNULL(c.CUST_DESC,'') LIKE ?)
              GROUP BY a.CUST_CODE ORDER BY MAX(a.MAINT_YMD) DESC""", tag, qq, qq)
        rows = [{"code": str(r[0]).strip(), "name": (str(r[1]).strip() or str(r[0]).strip())} for r in cur.fetchall()]
        return {"rows": rows}
    finally:
        cn.close()

@router.get("/api/dopip/items")
def dopip_items(kind: str = Query("pur"), cust: str = Query(""), q: str = Query("")):
    """선택 거래처가 도입한 품번 오토컴플리트(+ 최근 단가·통화). 거래처 미선택시 빈 목록."""
    tag, _ = _kd(kind); cust = cust.strip()
    if not cust:
        return {"rows": []}
    qq = f"%{q.strip()}%"
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT mat, nm, cost, cur FROM (
              SELECT a.MAT_CODE mat, ISNULL(i.item_name,'') nm, ISNULL(a.MAINT_COST,0) cost, ISNULL(a.CURRENCY,'') cur,
                ROW_NUMBER() OVER(PARTITION BY a.MAT_CODE ORDER BY a.MAINT_YMD DESC, a.MAINT_SEQ DESC) rn
              FROM nx.PU_T_STOCK_MAINT_C a LEFT JOIN nx.item i ON i.ITEM_CODE=a.MAT_CODE
              WHERE a.DIVISION=? AND a.CUST_CODE=? AND a.MAT_CODE>'' AND (a.MAT_CODE LIKE ? OR ISNULL(i.item_name,'') LIKE ?)
            ) x WHERE rn=1 ORDER BY mat""", tag, cust, qq, qq)
        rows = [{"mat": str(r[0]).strip(), "nm": str(r[1]).strip(), "cost": float(r[2] or 0), "cur": str(r[3] or '').strip()} for r in cur.fetchall()]
        return {"rows": rows[:40]}
    finally:
        cn.close()

@router.post("/api/dopip/save_batch")
def dopip_save_batch(p: dict = Body(...)):
    """다건 입력(레거시 w_pu_stock_c_045 그리드): 헤더(일자·거래처·통화·환율) 공유 + 행별(품번·수량·단가·관세·운임·신고·BL·HS).
       한 번 = 한 SHEET_NO, 행마다 MAINT_SEQ 증가. 금액=수량×단가."""
    kind = str(p.get("kind", "pur")); tag, _ = _kd(kind)
    ymd = _d6(str(p.get("ymd", "")).strip())
    if len(ymd) != 6: raise HTTPException(400, "일자(YYMMDD) 필요")
    cust = str(p.get("cust", "")).strip()
    if not cust: raise HTTPException(400, "거래처 필수")
    cur_ccy = str(p.get("cur", "USD")).strip() or "USD"
    rate = float(p.get("rate") or 0)
    rows = p.get("rows") or []
    valid = [r for r in rows if str(r.get("mat", "")).strip() and float(r.get("qty") or 0) != 0]
    if not valid: raise HTTPException(400, "품목 행 1개 이상(품번·수량) 필요")
    cn = _nx(); c = cn.cursor()
    try:
        _assert_open(c, ymd, "MAT", "도입 일괄입력")   # ★마감잠금
        nseq = int(c.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.PU_T_STOCK_MAINT_C WHERE MAINT_YMD=?", ymd).fetchone()[0])
        sheet = int(c.execute("SELECT ISNULL(MAX(SHEET_NO),0)+1 FROM nx.PU_T_STOCK_MAINT_C WHERE DIVISION=?", tag).fetchone()[0])
        ins = 0; seqs = []
        for r in valid:
            nseq += 1
            mat = str(r.get("mat", "")).strip(); qty = float(r.get("qty") or 0); cost = float(r.get("cost") or 0)
            amt = round(qty * cost, 4)
            duty = float(r.get("duty") or 0); fare = float(r.get("fare") or 0); tax = float(r.get("tax") or 0)
            insp = str(r.get("insp", "")).strip(); bl = str(r.get("bl", "")).strip(); hs = str(r.get("hs", "")).strip()
            remarks = str(r.get("remarks", "")).strip()
            c.execute("""INSERT INTO nx.PU_T_STOCK_MAINT_C
                  (MAINT_YMD,MAINT_SEQ,MAINT_TAG,DIVISION,SHEET_NO,CUST_CODE,MAT_CODE,MAINT_QTY,MAINT_AMT,
                   CURRENCY,MAINT_COST,EXCHANGE_RATE,REMARKS,CUSTOMS_DUTIES,TRANSPORTATION_FATE,TAX_TABLE,
                   INSP_SEQ,BL_SEQ,HS_CODE,INSERT_DATETIME,INSERT_USER_ID)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),'web')""",
                ymd, nseq, tag, tag, sheet, cust, mat, qty, amt, cur_ccy, cost, rate, remarks, duty, fare, tax, insp, bl, hs)
            ins += 1; seqs.append(nseq)
        cn.commit()
        return {"ok": True, "inserted": ins, "ymd": ymd, "sheet": sheet, "seqs": seqs}
    finally:
        cn.close()

@router.post("/api/dopip/delete")
def dopip_delete(p: dict = Body(...)):
    kind = str(p.get("kind", "pur")); tag, _ = _kd(kind)
    ymd = _d6(str(p.get("ymd", "")).strip()); seq = int(p.get("seq") or 0)
    if len(ymd) != 6 or seq <= 0: raise HTTPException(400, "일자·순번 필요")
    cn = _nx(); c = cn.cursor()
    try:
        _assert_open(c, ymd, "MAT", "도입 삭제")   # ★마감잠금
        c.execute("DELETE FROM nx.PU_T_STOCK_MAINT_C WHERE MAINT_YMD=? AND MAINT_SEQ=? AND MAINT_TAG=?", ymd, seq, tag)
        n = c.rowcount; cn.commit()
        if n == 0: raise HTTPException(404, "삭제 대상 없음")
        return {"ok": True, "deleted": n}
    finally:
        cn.close()
