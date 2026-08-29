# -*- coding: utf-8 -*-
"""협력사 세트입고(setin/setstock) 도메인 라우터 — 세트입고요청·명세·실입고·바코드스캔. _fmtbiz(사업자번호 포맷)는 로컬.
   app.py에서 분리. 공유헬퍼는 common.py."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import _conn, _nx, _nx_tx, _b, _d6, _num, _assert_open, stock_changed

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
              ISNULL(c.CUST_DESC,'') custnm, h.item_code, ISNULL(i.item_name,'') itemnm,
              h.input_req_qty, h.status, ISNULL(h.insp_flag,'0') insp_flag,
              (SELECT COUNT(*) FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no) jcnt,
              ISNULL(h.deliver_qty,0) deliver_qty,
              STUFF((SELECT ','+d.mat_code FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no FOR XML PATH('')),1,1,'') jadolist
            FROM nx.set_input_req h
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.in_cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=h.item_code
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
        cur.execute("""SELECT d.line_no, d.mat_code, ISNULL(i.item_name,'') matnm, d.use_qty, d.mat_qty, ISNULL(d.insp_flag,'0') insp_flag
            FROM nx.set_input_req_dtl d LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=d.mat_code
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
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림(캐시 stale 금지)
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
              d.mat_code jado, ISNULL(i.item_name,'') nm, d.use_qty, ISNULL(d.insp_flag,'0') insp
            FROM nx.set_input_req h JOIN nx.set_input_req_dtl d ON d.sheet_no=h.sheet_no
            LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=d.mat_code
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
              ISNULL(c.CUST_DESC,'') custnm, m.item_code, ISNULL(i.item_name,'') itemnm, m.maint_qty, m.sheet_no,
              m.manual_sheet_no, m.status, ISNULL(m.derived_flag,'0') derived_flag, m.insert_datetime
            FROM nx.set_stock_maint m
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=m.item_code
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
        cur.execute("""SELECT h.item_code, ISNULL(i.item_name,'') itemnm, ISNULL(h.deliver_qty,h.input_req_qty) qty,
              h.in_cust_code, ISNULL(c.CUST_DESC,'') custnm, h.status, ISNULL(h.insp_flag,'0') insp,
              (SELECT COUNT(*) FROM nx.set_input_req_dtl d WHERE d.sheet_no=h.sheet_no) jcnt
            FROM nx.set_input_req h LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=h.in_cust_code
            LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=h.item_code
            WHERE h.barcode_no=? ORDER BY h.item_code""", bc)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not rows:
            raise HTTPException(404, f"SET바코드 {barcode} 송장을 찾을 수 없습니다.")

        # ★중복 스캔 사전 경고 (대표 확정 2026-08-29: "같은 송장 2번 입고는 치명적 오류")
        #   찍는 순간 화면에 뜨게 한다 — 입고 버튼을 누르기 전에 알아야 한다.
        cur.execute("""SELECT COUNT(*), MIN(maint_ymd), MAX(LTRIM(RTRIM(ISNULL(insert_user_id,'')))),
                              SUM(CAST(maint_qty AS float))
                         FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'""", bc)
        dn, dymd, duser, dqty = cur.fetchone()
        done = [r for r in rows if str(r.get("status") or "").strip() in ("90", "30", "40")]
        warn = None
        if dn and int(dn) > 0:
            warn = (f"★이미 입고된 SET바코드입니다 — {dymd} · {duser or '?'} · {float(dqty or 0):,.0f}개 ({int(dn)}건). "
                    f"중복 입고하면 재고가 실제보다 늘어납니다.")
        elif done:
            warn = (f"★이미 처리된 송장이 {len(done)}건 있습니다(상태 "
                    f"{', '.join(sorted({str(r.get('status') or '').strip() for r in done}))}).")
        return {"barcode": bc, "cust": rows[0]["in_cust_code"], "custnm": rows[0]["custnm"],
                "rows": rows, "already": int(dn or 0), "warn": warn}
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
        cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
        _assert_open(cur, cur.fetchone()[0], "MAT", "세트입고")   # ★마감잠금(입고일=오늘)
        # ★★중복 입고 차단 (대표 확정 2026-08-29)
        #   "같은 송장이 2번 찍혀서 들어오는 건 치명적 오류" — 막고, 왜 안 되는지 알린다.
        #   믿고 받는 구조(세지 않고 송장대로 입고)에서 중복 스캔은 **재고를 그대로 두 배로** 만든다.
        #   실측: 같은 (송장,도번) 2회 이상 = 99건 · 전부 같은 날 · 전부 바코드(tag 2).
        #        레거시는 상태를 안 보고 찍을 때마다 한 줄씩 넣어 막지 못했다(레거시 결함, CLAUDE.md §1-7).
        force = bool(payload.get("force"))          # 관리자가 사유를 알고 추가할 때만
        cur.execute("""SELECT COUNT(*), MIN(maint_ymd), MAX(LTRIM(RTRIM(ISNULL(insert_user_id,'')))),
                              SUM(CAST(maint_qty AS float))
                         FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'""", bc)
        dn, dymd, duser, dqty = cur.fetchone()
        if dn and int(dn) > 0 and not force:
            raise HTTPException(409,
                f"중복 입고 차단 — SET바코드 {bc} 는 이미 입고되었습니다. "
                f"({dymd} · {duser or '?'} · {float(dqty or 0):,.0f}개 · {int(dn)}건) "
                f"다시 넣으면 재고가 실제보다 늘어납니다. "
                f"추가 납품분이면 [장부수정]으로, 잘못 입고했으면 [입고취소]로 처리하세요.")

        cur.execute("""SELECT h.sheet_no, h.item_code, ISNULL(h.deliver_qty,h.input_req_qty) qty, h.in_cust_code,
              ISNULL(h.insp_flag,'0') insp FROM nx.set_input_req h WHERE h.barcode_no=? AND h.status IN ('10','30')""", bc)
        reqs = cur.fetchall()
        if not reqs:
            # 발행 상태가 아니다 — 왜인지 밝힌다(막연한 404 금지)
            cur.execute("""SELECT status, COUNT(*) FROM nx.set_input_req WHERE barcode_no=?
                           GROUP BY status""", bc)
            st = cur.fetchall()
            if not st:
                raise HTTPException(404, f"SET바코드 {bc} 송장을 찾을 수 없습니다. 바코드를 확인하세요.")
            ST = {"00": "요청(미발행)", "10": "발행", "20": "출발", "30": "입고대기",
                  "40": "검사중", "90": "입고완료", "99": "반품"}
            desc = " · ".join(f"{ST.get(str(a).strip(), a)} {b}건" for a, b in st)
            raise HTTPException(409,
                f"입고할 수 없는 상태입니다 — SET바코드 {bc}: {desc}. "
                f"발행(10) 또는 입고대기(30) 상태만 입고됩니다.")
        recv = 0; posted = 0
        cur.execute("SELECT ISNULL(MAX(maint_seq),0) FROM nx.set_stock_maint WHERE maint_ymd=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)")
        mseq = int(cur.fetchone()[0])
        for sheet, doban, qty, cust, insp in reqs:
            qty = float(qty or 0); mseq += 1
            # ★★이 분기를 지우지 말 것 (대표 확정 2026-08-29 "수입검사는 추후 추가").
            #   지금은 insp_flag 가 전부 '0' 이라 **항상 90(즉시 입고완료)** 으로만 흐른다.
            #   "안 쓰니까 단순화하자" 며 없애면, 나중에 검사를 도입할 때 입고 로직을 다시 뜯어야 한다.
            #   ⟹ 나중에 insp_flag 를 '1' 로 채우는 것만으로 검사 경로가 살아난다(코드 수정 불필요).
            #   상태 30(입고대기)·40(검사중) 도 같은 이유로 보존한다.
            #   설계 = _schema/PARTNER_PORTAL_DESIGN.md §4-1
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
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림(캐시 stale 금지)
        return {"ok": True, "received": recv, "ledger_posted": posted, "barcode": "SET" + bc}
    finally:
        cn.close()
