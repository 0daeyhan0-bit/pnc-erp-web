# -*- coding: utf-8 -*-
"""협력사 세트입고(setin/setstock) 도메인 라우터 — 세트입고요청·명세·실입고·바코드스캔. _fmtbiz(사업자번호 포맷)는 로컬.
   app.py에서 분리. 공유헬퍼는 common.py."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from fastapi import Request
from routers.auth import (require_user, scope_cust, staff_only,
                          assert_own_barcode)   # ★소속 강제 (2026-08-29)
from common import _conn, _nx, _nx_tx, _b, _d6, _num, _assert_open, stock_changed

router = APIRouter()

# ── 협력사출고(사급소진) posting: 세트입고 완제품 × 사급부품 소요 → nx.sagub_maint(tag 'S', −) ──
#    협력사 사급재고 단일 원장(SAGUB_PARTS_LEDGER_DESIGN). 소요는 통일 소요엔진(§10)만.
#    사급출고(saleout)=협력사입고(+)의 역방향. 수불장·협력사사급재고관리가 이 원장에서 파생.
_SAG_ENG = None; _SAG_STOP = None; _SAG_WELD = None; _SAG_MEMO = {}
def _sag_eng():
    global _SAG_ENG, _SAG_STOP, _SAG_WELD
    if _SAG_ENG is None:
        import nx_soyo_engine as _soyo
        from nx_cost_engine import NxCostEngine
        _SAG_ENG = NxCostEngine(); c = _SAG_ENG.cur
        c.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item WHERE item_code LIKE 'RAC%' OR item_code LIKE 'BCUP%' OR item_name LIKE '%용접%'")
        _SAG_WELD = set(r[0].strip() for r in c.fetchall())
        c.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.v_pr_bom WHERE SAGUB_FLAG='1' AND ISNULL(MAT_CODE,'')<>''")
        _SAG_STOP = set(r[0].strip() for r in c.fetchall())
        _soyo.warm_vpr(_SAG_ENG)
    return _SAG_ENG

def _post_sagub_out(cur, cust, doban, qty, ymd, ref):
    """세트입고 완제품 doban×qty → 사급부품 소요만큼 협력사 사급재고 차감(tag 'S', −qty). 용접 제외. 소요엔진(§10)."""
    if not cust or not doban or not qty:
        return 0
    import nx_soyo_engine as _soyo
    eng = _sag_eng()
    n = 0
    for part, per in _soyo.sagub_parts_soyo(eng, str(doban).strip().upper(), _SAG_STOP, _SAG_MEMO).items():
        if part in _SAG_WELD or per <= 0:
            continue
        cur.execute("SELECT ISNULL(MAX(maint_seq),0)+1 FROM nx.sagub_maint WHERE maint_ymd=?", ymd)
        s = int(cur.fetchone()[0] or 1)
        cur.execute("""INSERT INTO nx.sagub_maint(maint_ymd,maint_seq,maint_tag,cust_code,mat_code,maint_qty,remarks,remarks_src,insert_user_id,insert_datetime)
            VALUES(?,?,'S',?,?,?,N'세트입고 협력사출고(사급소진)',?,'web',getdate())""",
            ymd, s, cust, part, -float(per) * float(qty), f"setstock:{ref}")
        n += 1
    return n

# ===================== 세트입고요청 (nx.set_input_req, 협력사) =====================
@router.get("/api/setin/list")
def setin_list(request: Request, cust: str = Query(""), fr: str = Query(""), to: str = Query(""), status: str = Query(""), limit: int = Query(800)):
    """세트입고요청 송장 목록(nx.set_input_req, 계획편성분). 협력사명·자도번수 조인.
       ★소속 강제 — 협력사 계정은 cust 파라미터와 무관하게 자기 것만 본다."""
    cust = scope_cust(require_user(request), cust)
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
def setin_detail(request: Request, sheet: str = Query(...)):
    """세트입고요청 자도번 명세(nx.set_input_req_dtl).
       ★소속 강제 - 협력사는 자기 송장의 명세만 본다(송장번호를 바꿔 넣어도 열리지 않는다)."""
    _u = require_user(request)
    cn = _nx(); cur = cn.cursor()
    try:
        assert_own_barcode(cur, _u, sheet, col="sheet_no")
        cur.execute("""SELECT d.line_no, d.mat_code, ISNULL(i.item_name,'') matnm, d.use_qty, d.mat_qty, ISNULL(d.insp_flag,'0') insp_flag
            FROM nx.set_input_req_dtl d LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=d.mat_code
            WHERE d.sheet_no=? ORDER BY d.line_no""", sheet)
        cols = [d[0] for d in cur.description]
        return {"rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    finally:
        cn.close()

@router.post("/api/setin/issue")
def setin_issue(request: Request, payload: dict = Body(...)):
    """거래명세서(송장) 발행 — 협력사가 납품수량 입력·완성분 체크 후 발행.
       체크한 여러 도번을 ★하나의 SET바코드(barcode_no)로 묶음. 상태 00요청→10발행. cancel=1이면 되돌림.
       items=[{sheet, qty}]."""
    _u = require_user(request)
    items = payload.get("items", []) or []
    cancel = bool(payload.get("cancel"))
    if not items:
        raise HTTPException(400, "발행할 송장이 없습니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        # ★소속 강제 - 협력사는 **자기 계획으로 만들어진 송장만** 발행한다.
        #   (대표 확정: "계획서에서 지정된 것만 발행하도록 제한해")
        if _u.get("utype") == "협력사":
            mine = _u.get("partner_code") or "__NONE__"
            for _it in items:
                _sh = str(_it.get("sheet", "")).strip()
                if not _sh:
                    continue
                cur.execute("""SELECT COUNT(*) FROM nx.set_input_req
                                WHERE sheet_no=? AND in_cust_code=?""", _sh, mine)
                if not cur.fetchone()[0]:
                    raise HTTPException(403, f"다른 협력사의 송장입니다({_sh}).")
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
def setin_invoice(request: Request, barcode: str = Query(...)):
    """거래명세표(송장) 데이터 — 하나의 SET바코드에 묶인 도번→자도번 명세 + 공급자(협력사)/공급받는자(당사)."""
    import datetime
    cn = _nx(); cur = cn.cursor()
    try:
        assert_own_barcode(cur, require_user(request), barcode)      # ★남의 명세서 차단
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
def setstock_list(request: Request, fr: str = Query(""), to: str = Query(""), cust: str = Query(""), item: str = Query(""), tag: str = Query(""), limit: int = Query(600)):
    """세트입고 실적 목록(nx.set_stock_maint). 반품=maint_qty<0.
       ★소속 강제 — 협력사는 자기 입고분만."""
    cust = scope_cust(require_user(request), cust)
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
def setstock_scan(request: Request, barcode: str = Query(...)):
    """SET바코드(발행 송장) 조회 → 입고 확인용 정보(협력사·도번들·자도번수). barcode=숫자 또는 SETnnn.
       ★입고 스캔은 우리가 받는 행위다 — 담당자 전용."""
    staff_only(request, "입고 스캔")
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
def setstock_receive(request: Request, payload: dict = Body(...)):
    _u = staff_only(request, "세트입고")   # ★협력사 계정 거부 - 우리가 받는 행위다
    """입고처리 — SET바코드 스캔/장부입고. set_stock_maint 기록 + status(일반=입고완료90/검사=입고대기30)
       + 입고완료분 자도번 재고파생(stock_ledger, MAINT_TAG='S'). tag: 2바코드/3장부. manual: 수동입고NO.
       ★입고 가능 상태 = 10발행 · 20출발 · 30입고대기.
         20(출발)은 협력사가 차에 실었다는 표시다(2026-08-29 신설) — 실제로 도착한 것이므로
         **입고 대상에 반드시 포함**해야 한다. 빠뜨리면 출발 처리한 송장이 입고되지 않는다."""
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
              ISNULL(h.insp_flag,'0') insp FROM nx.set_input_req h WHERE h.barcode_no=? AND h.status IN ('10','20','30')""", bc)
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
                f"발행(10)·출발(20)·입고대기(30) 상태만 입고됩니다.")
        recv = 0; posted = 0
        cur.execute("SELECT RIGHT(CONVERT(varchar(8),GETDATE(),112),6)"); _today = cur.fetchone()[0]
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
                # ★협력사출고(사급소진) — 완제품 doban×qty 만큼 협력사 사급재고 차감(nx.sagub_maint tag S, −). 소요엔진(§10).
                _post_sagub_out(cur, cust, doban, qty, _today, mseq)
        cn.commit()
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림(캐시 stale 금지)
        return {"ok": True, "received": recv, "ledger_posted": posted, "barcode": "SET" + bc}
    finally:
        cn.close()


@router.get("/api/setstock/cancel_preview")
def setstock_cancel_preview(request: Request, barcode: str = Query(...)):
    staff_only(request, "입고취소 미리보기")
    """입고취소 전 미리보기 — 무엇이 되돌아가는지 보여준다(되돌리기 전에 눈으로 확인)."""
    bc = "".join(ch for ch in str(barcode) if ch.isdigit())
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT maint_ymd, maint_seq, item_code, CAST(maint_qty AS float),
                              LTRIM(RTRIM(ISNULL(insert_user_id,''))), status
                         FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'
                        ORDER BY maint_ymd, maint_seq""", bc)
        cols = [d[0] for d in cur.description]
        recv = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not recv:
            raise HTTPException(404, f"SET바코드 {bc} 의 입고 내역이 없습니다.")
        cur.execute("""SELECT MAINT_YMD, MAINT_SEQ, MAT_CODE, CAST(MAINT_QTY AS float)
                         FROM nx.stock_ledger WHERE SHEET_NO=? AND MAINT_TAG='S'
                        ORDER BY MAINT_YMD, MAINT_SEQ""", int(bc) if bc.isdigit() else None)
        led = [{"ymd": a, "seq": b, "mat": str(c2).strip(), "qty": float(d or 0)}
               for a, b, c2, d in cur.fetchall()]
        return {"barcode": bc, "recv": recv, "recv_cnt": len(recv),
                "ledger": led, "ledger_cnt": len(led),
                "ledger_qty": sum(x["qty"] for x in led)}
    finally:
        cn.close()


@router.post("/api/setstock/cancel")
def setstock_cancel(request: Request, payload: dict = Body(...)):
    _u = staff_only(request, "입고취소")   # ★협력사 계정 거부 - 우리가 받는 행위다
    """★입고취소 — 잘못 스캔한 입고를 되돌린다 (대표 확정 2026-08-29).

       믿고 받는 구조(세지 않고 송장대로 입고)에서는 **되돌리는 길이 반드시 있어야 한다.**
       스캔 1회로 도번 최대 35종이 들어가므로, 잘못 찍으면 통째로 잘못 들어간다.

       되돌리는 것 = 입고가 만든 것 **넷 전부**
         ① nx.set_stock_maint      입고 거래행 삭제
         ② nx.set_input_req.status 90/30 → 10(발행)으로 복귀 + deliver 유지
         ③ nx.stock_ledger         자도번 재고 파생분(MAINT_TAG='S') 삭제
         ④ nx.sagub_maint          협력사출고(사급소진) posting(remarks_src='setstock:mseq') 삭제
       ★넷 중 하나만 지우면 장부가 어긋난다. 한 트랜잭션으로 묶는다.

       ★마감 잠금: 마감된 기간의 입고는 취소할 수 없다(재고가 움직이므로 규칙B).
    """
    bc = "".join(ch for ch in str(payload.get("barcode", "")) if ch.isdigit())
    user = (str(payload.get("user") or "web")[:20])
    reason = str(payload.get("reason", "")).strip()
    if not bc:
        raise HTTPException(400, "SET바코드가 필요합니다.")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT maint_ymd, maint_seq, sheet_no, item_code, CAST(maint_qty AS float)
                         FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'""", bc)
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(404, f"SET바코드 {bc} 의 입고 내역이 없습니다. 취소할 것이 없습니다.")

        # ★마감 잠금 — 입고일자 기준. 마감된 달의 재고는 되돌릴 수 없다.
        for ymd, _seq, _sh, _it, _q in {(r[0], r[1], r[2], r[3], r[4]) for r in rows}:
            _assert_open(cur, str(ymd).strip(), "MAT", "세트입고 취소")

        # ③ 재고 파생분 먼저 제거 (원장 → 거래 → 상태 순서로 되돌린다)
        led = 0
        try:
            cur.execute("DELETE FROM nx.stock_ledger WHERE SHEET_NO=? AND MAINT_TAG='S'",
                        int(bc) if bc.isdigit() else None)
            led = cur.rowcount
        except Exception:
            led = 0

        # ④ 협력사출고(사급소진) posting 제거 — 입고 mseq 기준(remarks_src='setstock:mseq'). 근거키 스코프.
        sag = 0
        try:
            seqs = {int(r[1]) for r in rows}
            if seqs:
                srcs = [f"setstock:{s}" for s in seqs]
                ph = ",".join("?" for _ in srcs)
                cur.execute(f"DELETE FROM nx.sagub_maint WHERE maint_tag='S' AND remarks_src IN ({ph})", *srcs)
                sag = cur.rowcount
        except Exception:
            sag = 0

        # ① 입고 거래행 제거
        cur.execute("DELETE FROM nx.set_stock_maint WHERE sheet_no=? AND in_tag='1'", bc)
        recv = cur.rowcount

        # ② 송장 상태를 발행(10)으로 되돌린다 — 다시 스캔할 수 있게
        cur.execute("""UPDATE nx.set_input_req SET status='10', status_dt=GETDATE(), status_user=?
                        WHERE barcode_no=? AND status IN ('30','40','90')""", user, bc)
        req = cur.rowcount

        cn.commit()
        stock_changed()      # ★재고 변경 → 파생 캐시 무효화
        return {"ok": True, "barcode": bc, "recv_deleted": recv,
                "ledger_deleted": led, "sagub_deleted": sag, "req_reverted": req,
                "msg": f"입고취소 완료 — 입고 {recv}건 · 재고파생 {led}행 · 협력사출고 {sag}행 되돌림. "
                       f"송장 {req}건이 발행(10) 상태로 돌아가 다시 스캔할 수 있습니다."}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()
