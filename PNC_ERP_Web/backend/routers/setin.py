# -*- coding: utf-8 -*-
"""협력사 세트입고(setin/setstock) 도메인 라우터 — 세트입고요청·명세·실입고·바코드스캔. _fmtbiz(사업자번호 포맷)는 로컬.
   app.py에서 분리. 공유헬퍼는 common.py."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import _conn, _nx, _nx_tx, _b, _d6, _num

router = APIRouter()

# ===================== 세트입고요청 (nx.set_input_req, 협력사) =====================
@router.get("/api/setin/list")
def setin_list(cust: str = Query(""), fr: str = Query(""), to: str = Query(""), status: str = Query(""), limit: int = Query(800)):
    """세트입고요청 송장 목록(nx.set_input_req, 계획편성분). 협력사명·자도번수 조인."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["h.remarks='PLAN_COMPOSE'"]; p = []
        if cust: w.append("h.in_cust_code=?"); p.append(cust)
        if fr: w.append("h.input_ymd>=?"); p.append(fr)
        if to: w.append("h.input_ymd<=?"); p.append(to)
        if status: w.append("h.status=?"); p.append(status)
        where = " AND ".join(w)
        cur.execute(f"""SELECT TOP {int(limit)} h.sheet_no, h.input_ymd, h.in_cust_code,
              ISNULL(c.CUST_DESC,'') custnm, h.item_code, ISNULL(i.ITEM_DESC,'') itemnm,
              h.input_req_qty, h.status, ISNULL(h.insp_flag,'0') insp_flag,
              (SELECT COUNT(*) FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no) jcnt,
              ISNULL(h.deliver_qty,0) deliver_qty,
              STUFF((SELECT ','+d.mat_code FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no FOR XML PATH('')),1,1,'') jadolist
            FROM nx.set_input_req h
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.in_cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=h.item_code
            WHERE {where} ORDER BY h.in_cust_code, h.input_ymd, h.sheet_no""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.execute("""SELECT h.in_cust_code, MAX(ISNULL(c.CUST_DESC,'')) nm, COUNT(*) n
            FROM nx.set_input_req h LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.in_cust_code
            WHERE h.remarks='PLAN_COMPOSE' GROUP BY h.in_cust_code ORDER BY COUNT(*) DESC""")
        custs = [{"code": r[0], "nm": r[1], "n": r[2]} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows), "custs": custs}
    finally:
        cn.close()

@router.get("/api/setin/detail")
def setin_detail(sheet: str = Query(...)):
    """세트입고요청 자도번 명세(nx.set_input_req_dtl)."""
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT d.line_no, d.mat_code, ISNULL(i.ITEM_DESC,'') matnm, d.use_qty, d.mat_qty, ISNULL(d.insp_flag,'0') insp_flag
            FROM nx.set_input_req_dtl d LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=d.mat_code
            WHERE d.sheet_no=? ORDER BY d.line_no""", sheet)
        cols = [d[0] for d in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        cn.close()

@router.post("/api/setin/issue")
def setin_issue(payload: dict = Body(...)):
    """거래명세서(송장) 발행 — 협력사가 납품수량 입력·완성분 체크 후 발행.
       체크한 여러 도번을 ★하나의 SET바코드(barcode_no)로 묶음. 상태 00요청→10발행. cancel=1이면 되돌림.
       items=[{sheet, qty}]."""
    items = payload.get("items", []) or []
    cancel = bool(payload.get("cancel"))
    if not items:
        raise HTTPException(400, "발행할 송장이 없습니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        if cancel:
            ok = 0
            for it in items:
                sh = str(it.get("sheet", "")).strip()
                if sh:
                    cur.execute("UPDATE nx.set_input_req SET status='00', deliver_qty=NULL, barcode_no=NULL, issue_ymd=NULL WHERE sheet_no=? AND remarks='PLAN_COMPOSE' AND status='10'", sh)
                    ok += cur.rowcount
            cn.commit(); return {"ok": True, "count": ok, "action": "취소"}
        # 배치 SET바코드 채번(하나로 묶음)
        cur.execute("SELECT ISNULL(MAX(CAST(barcode_no AS int)),500000)+1 FROM nx.set_input_req WHERE barcode_no IS NOT NULL AND ISNUMERIC(barcode_no)=1")
        batch = str(cur.fetchone()[0]); ok = 0
        for it in items:
            sh = str(it.get("sheet", "")).strip()
            if not sh:
                continue
            q = float(it.get("qty", 0) or 0)
            cur.execute("""UPDATE nx.set_input_req SET status='10', deliver_qty=?, barcode_no=?,
                issue_ymd=RIGHT(CONVERT(varchar(8),GETDATE(),112),6), status_dt=GETDATE()
                WHERE sheet_no=? AND remarks='PLAN_COMPOSE' AND status IN ('00','10')""", q, batch, sh)
            ok += cur.rowcount
        cn.commit()
        return {"ok": True, "count": ok, "barcode": batch, "action": "발행"}
    finally:
        cn.close()

def _fmtbiz(b):
    b = "".join(ch for ch in str(b or "") if ch.isdigit())
    return f"{b[:3]}-{b[3:5]}-{b[5:]}" if len(b) == 10 else (str(b) or "")

@router.get("/api/setin/invoice")
def setin_invoice(barcode: str = Query(...)):
    """거래명세표(송장) 데이터 — 하나의 SET바코드에 묶인 도번→자도번 명세 + 공급자(협력사)/공급받는자(당사)."""
    import datetime
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("SELECT TOP 1 in_cust_code FROM nx.set_input_req WHERE barcode_no=?", barcode)
        rc = cur.fetchone()
        if not rc:
            raise HTTPException(404, "해당 SET바코드 송장 없음")
        cust = rc[0]
        cur.execute("""SELECT ISNULL(BUSINESS_NO,''),ISNULL(CUST_DESC,''),ISNULL(OWNER_NAME,''),
            LTRIM(ISNULL(ADDRESS,'')+' '+ISNULL(ADDRESS_DTL,'')),ISNULL(PHONE_NO,''),ISNULL(FAX_NO,'')
            FROM PARTNER_ERP_TEST3.nx.CM_M_CUST WHERE CUST_CODE=?""", cust)
        s = cur.fetchone() or ('',)*6
        supplier = {"biz": _fmtbiz(s[0]), "nm": (s[1] or '').strip(), "owner": (s[2] or '').strip(), "addr": (s[3] or '').strip(), "tel": (s[4] or '').strip(), "fax": (s[5] or '').strip()}
        cur.execute("""SELECT TOP 1 ISNULL(BUSINESS_NO,''),ISNULL(COMPANY_DESCK,''),ISNULL(OWNER_NAME,''),
            LTRIM(ISNULL(ADDRESS,'')+' '+ISNULL(ADDRESS_DTL,'')),ISNULL(PHONE_NO,''),ISNULL(FAX_NO,'') FROM PARTNER_ERP_TEST3.nx.CM_M_COMPANY""")
        b = cur.fetchone() or ('',)*6
        buyer = {"biz": _fmtbiz(b[0]), "nm": (b[1] or '').strip(), "owner": (b[2] or '').strip(), "addr": (b[3] or '').strip(), "tel": (b[4] or '').strip(), "fax": (b[5] or '').strip()}
        cur.execute("""SELECT h.item_code doban, ISNULL(h.deliver_qty,h.input_req_qty) setqty,
              d.mat_code jado, ISNULL(i.ITEM_DESC,'') nm, d.use_qty, ISNULL(d.insp_flag,'0') insp
            FROM nx.set_input_req h JOIN nx.set_input_req_dtl d ON d.sheet_no=h.sheet_no
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=d.mat_code
            WHERE h.barcode_no=? ORDER BY h.item_code, d.line_no""", barcode)
        rows = []; tot = 0.0; lastd = None
        for doban, setq, jado, nm, uq, insp in cur.fetchall():
            qty = float(setq or 0) * float(uq or 1); tot += qty
            rows.append({"doban": (doban if doban != lastd else ""), "jado": jado, "nm": (nm or '').strip(), "qty": qty, "insp": insp})
            lastd = doban
        return {"barcode": "SET" + barcode, "raw": barcode, "ymd": datetime.date.today().strftime('%Y-%m-%d'),
                "supplier": supplier, "buyer": buyer, "rows": rows, "total": tot}
    finally:
        cn.close()

# ===================== 자재세트입고관리 (입고처리, w_pu_stock_140) =====================
@router.get("/api/setstock/list")
def setstock_list(fr: str = Query(""), to: str = Query(""), cust: str = Query(""), item: str = Query(""), tag: str = Query(""), limit: int = Query(600)):
    """세트입고 실적 목록(nx.set_stock_maint). 반품=maint_qty<0."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if fr: w.append("m.maint_ymd>=?"); p.append(fr)
        if to: w.append("m.maint_ymd<=?"); p.append(to)
        if cust: w.append("m.cust_code=?"); p.append(cust)
        if item: w.append("m.item_code LIKE ?"); p.append(f"%{item}%")
        if tag: w.append("m.maint_tag=?"); p.append(tag)
        cur.execute(f"""SELECT TOP {int(limit)} m.maint_ymd, m.maint_seq, m.maint_tag, m.in_tag, m.cust_code,
              ISNULL(c.CUST_DESC,'') custnm, m.item_code, ISNULL(i.ITEM_DESC,'') itemnm, m.maint_qty, m.sheet_no,
              m.manual_sheet_no, m.status, ISNULL(m.derived_flag,'0') derived_flag, m.insert_datetime
            FROM nx.set_stock_maint m
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=m.item_code
            WHERE {' AND '.join(w)} ORDER BY m.maint_ymd DESC, m.maint_seq DESC""", *p)
        cols = [d[0] for d in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        cn.close()

@router.get("/api/setstock/scan")
def setstock_scan(barcode: str = Query(...)):
    """SET바코드(발행 송장) 조회 → 입고 확인용 정보(협력사·도번들·자도번수). barcode=숫자 또는 SETnnn."""
    bc = "".join(ch for ch in str(barcode) if ch.isdigit())
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT h.item_code, ISNULL(i.ITEM_DESC,'') itemnm, ISNULL(h.deliver_qty,h.input_req_qty) qty,
              h.in_cust_code, ISNULL(c.CUST_DESC,'') custnm, h.status, ISNULL(h.insp_flag,'0') insp,
              (SELECT COUNT(*) FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no) jcnt
            FROM nx.set_input_req h LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.in_cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=h.item_code
            WHERE h.barcode_no=? ORDER BY h.item_code""", bc)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not rows:
            raise HTTPException(404, f"SET바코드 {barcode} 송장을 찾을 수 없습니다.")
        return {"barcode": bc, "cust": rows[0]["in_cust_code"], "custnm": rows[0]["custnm"], "rows": rows}
    finally:
        cn.close()

@router.post("/api/setstock/receive")
def setstock_receive(payload: dict = Body(...)):
    """입고처리 — SET바코드 스캔/장부입고. set_stock_maint 기록 + status(일반=입고완료90/검사=입고대기30)
       + 입고완료분 자도번 재고파생(stock_ledger, MAINT_TAG='S'). tag: 2바코드/3장부. manual: 수동입고NO."""
    bc = "".join(ch for ch in str(payload.get("barcode", "")) if ch.isdigit())
    tag = str(payload.get("tag", "2")).strip() or "2"
    manual = str(payload.get("manual", "")).strip() or None
    if not bc:
        raise HTTPException(400, "SET바코드가 필요합니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT h.sheet_no, h.item_code, ISNULL(h.deliver_qty,h.input_req_qty) qty, h.in_cust_code,
              ISNULL(h.insp_flag,'0') insp FROM nx.set_input_req h WHERE h.barcode_no=? AND h.status IN ('10','30')""", bc)
        reqs = cur.fetchall()
        if not reqs:
            raise HTTPException(404, "발행 상태의 송장이 없습니다(이미 입고완료?).")
        recv = 0; posted = 0
        cur.execute("SELECT ISNULL(MAX(maint_seq),0) FROM nx.set_stock_maint WHERE maint_ymd=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        mseq = int(cur.fetchone()[0])
        for sheet, doban, qty, cust, insp in reqs:
            qty = float(qty or 0); mseq += 1
            newstat = "30" if insp == "1" else "90"   # 검사품=입고대기, 일반=입고완료
            cur.execute("""INSERT INTO nx.set_stock_maint(maint_ymd,maint_seq,maint_tag,in_tag,cust_code,item_code,maint_qty,
                  sheet_no,manual_sheet_no,item_gubun,status,derived_flag,insert_user_id,insert_datetime)
                VALUES(RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,?,'1',?,?,?,?,?,'1',?,'0','web',getdate())""",
                mseq, tag, cust, doban, qty, bc, manual, newstat)
            cur.execute("UPDATE nx.set_input_req SET status=?, status_dt=GETDATE() WHERE sheet_no=? AND barcode_no=?", newstat, sheet, bc)
            recv += 1
            if newstat == "90":  # 입고완료 → 자도번 재고파생
                cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.stock_ledger WHERE MAINT_YMD=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
                lseq = int(cur.fetchone()[0])
                cur.execute("SELECT mat_code, use_qty FROM nx.set_input_req_dtl WHERE sheet_no=?", sheet)
                for mat, uq in cur.fetchall():
                    lseq += 1; jqty = qty * float(uq or 1)
                    bcn = int(bc) if bc.isdigit() else None
                    cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,SHEET_NO,CUST_CODE,MAT_CODE,MAINT_QTY,
                          ITEM_CODE,SET_MAINT_YMD,SET_MAINT_SEQ,INPUT_YMD,ITEM_GUBUN,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                        VALUES('MAT',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,'S',?,?,?,?,?,RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,RIGHT(CONVERT(varchar(8),GETDATE(),112),6),'1','세트입고','web',getdate())""",
                        lseq, bcn, cust, str(mat).strip(), jqty, doban, mseq)
                    posted += 1
                cur.execute("UPDATE nx.set_stock_maint SET derived_flag='1' WHERE maint_ymd=RIGHT(CONVERT(varchar(8),GETDATE(),112),6) AND maint_seq=?", mseq)
        cn.commit()
        return {"ok": True, "received": recv, "ledger_posted": posted, "barcode": "SET" + bc}
    finally:
        cn.close()
