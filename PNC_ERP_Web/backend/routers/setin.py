# -*- coding: utf-8 -*-
"""협력사 세트입고(setin/setstock) 도메인 라우터 — 세트입고요청·명세·실입고·바코드스캔. _fmtbiz(사업자번호 포맷)는 로컬.
   app.py에서 분리. 공유헬퍼는 common.py."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from fastapi import Request
from routers.auth import (require_user, scope_cust, staff_only,
                          assert_own_barcode)   # ★소속 강제 (2026-08-29)
# ★라이브(_conn) 미import — 이 도메인은 nx 단일소스(§1-9-1). 실수로 쓰이지 않게 뺀다.
#   (_conn·_b·_num 은 이 파일에서 실사용 0회라 병합 시 제외 — 2026-08-30)
from common import _nx, _nx_tx, _d6, _assert_open, stock_changed, _sub_desc_plain

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
            # ★품명은 SUB 접미사 병기('[-12-1] ')를 벗긴 원품명 — 레거시 출력물과 동일하게.
            rows.append({"doban": (doban if doban != lastd else ""), "jado": jado, "nm": _sub_desc_plain(nm), "qty": qty, "insp": insp})
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

@router.get("/api/setin/stat")
def setin_stat(fr: str = Query(""), to: str = Query(""), cust: str = Query(""),
               item: str = Query(""), gubun: str = Query(""), ret: str = Query(""),
               limit: int = Query(3000)):
    """자재세트입고현황 — 레거시 w_pu_stock_140 목록부.

       컬럼: 입고일자·MaintSeq·입고구분·거래처코드/명·도번·입고수량·비고
             ·자도번입고·구분체크·바코드입고NO·수동입고NO·작업일시
       입고구분(maint_tag) 1:수동 / 2:바코드 / 3:장부수정 / 9:기초이관
       ★자도번입고 = 그 세트건이 파생시킨 자재원장(TAG='S') 행수·수량.
         장부수정(3)은 파생이 없다(레거시 실측 확인).
       gubun = 생성구분(maint_tag) · ret = 반품구분(all|in 입고|ret 반품=음수)
    """
    fr = _d6(fr) or ""
    to = _d6(to) or ""
    w = []; p = []
    if fr: w.append("m.maint_ymd>=?"); p.append(fr)
    if to: w.append("m.maint_ymd<=?"); p.append(to)
    if cust: w.append("m.cust_code=?"); p.append(cust)
    if item: w.append("m.item_code LIKE ?"); p.append("%" + item + "%")
    if gubun: w.append("m.maint_tag=?"); p.append(gubun)
    if ret == "in": w.append("m.maint_qty>=0")
    elif ret == "ret": w.append("m.maint_qty<0")
    where = (" WHERE " + " AND ".join(w)) if w else ""

    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute(f"""
            SELECT TOP {int(limit)}
                   m.maint_ymd, m.maint_seq, m.maint_tag, m.cust_code,
                   ISNULL(c.CUST_DESC,'') custnm, m.item_code,
                   ISNULL(i.item_name,'') itemnm, m.maint_qty,
                   ISNULL(m.remarks,'') remarks, ISNULL(m.item_gubun,'') item_gubun,
                   m.sheet_no, m.manual_sheet_no, m.insert_datetime,
                   ISNULL(m.insert_user_id,'') user_id, ISNULL(m.status,'') status,
                   (SELECT COUNT(*) FROM nx.stock_ledger g WITH(NOLOCK)
                     WHERE g.MAINT_TAG='S' AND g.SET_MAINT_YMD=m.maint_ymd
                       AND g.SET_MAINT_SEQ=m.maint_seq) jado_cnt,
                   (SELECT ISNULL(SUM(g.MAINT_QTY),0) FROM nx.stock_ledger g WITH(NOLOCK)
                     WHERE g.MAINT_TAG='S' AND g.SET_MAINT_YMD=m.maint_ymd
                       AND g.SET_MAINT_SEQ=m.maint_seq) jado_qty
              FROM nx.set_stock_maint m WITH(NOLOCK)
              LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=m.cust_code
              LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code=m.item_code
              {where}
             ORDER BY m.maint_ymd DESC, m.maint_seq""", *p)
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            dt = d.get("insert_datetime")
            rows.append({
                "ymd": (d["maint_ymd"] or "").strip(),
                "seq": int(d["maint_seq"] or 0),
                "tag": (d["maint_tag"] or "").strip(),
                "cust_code": (d["cust_code"] or "").strip(),
                "cust_name": (d["custnm"] or "").strip(),
                "item_code": (d["item_code"] or "").strip(),
                "item_name": (d["itemnm"] or "").strip(),
                "qty": float(d["maint_qty"] or 0),
                "remarks": (d["remarks"] or "").strip(),
                "item_gubun": (d["item_gubun"] or "").strip(),
                "sheet_no": d["sheet_no"],
                "manual_no": d["manual_sheet_no"],
                "jado_cnt": int(d["jado_cnt"] or 0),
                "jado_qty": float(d["jado_qty"] or 0),
                "user_id": (d["user_id"] or "").strip(),
                "status": (d["status"] or "").strip(),
                "dt": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "",
            })
        return {"rows": rows, "cnt": len(rows),
                "total": sum(x["qty"] for x in rows)}
    finally:
        cn.close()


# ── 세트입고 자도번 전개 (레거시 dw_pu_stock_146_1) ─────────────────────────
#   PBL 원문(sa_stock_01.pbl) 그대로 이식 — 2026-08-30.
#   ★가상도번 플래그를 쓰지 않는다. 거래처(work_code 우선, 없으면 in_cust_code)가
#     대상 거래처와 같은 노드만 남기므로, 거래처가 다른 가상도번은 자연히 탈락하고
#     재귀가 한 단계 더 내려간 실도번이 남는다. 이것이 '한 단계 더 전개'의 실체.
#   가지치기 3종: except_flag<>'1' · pr_m_mat(원자재)면 컷 · set_except_flag='0'
#   순환방지: 거래처 경로 누적문자열 charindex
#   검증(2026-08-30): AJR30101601/233, AJR77224517×2048·2148·233·2068 5건 전부 일치.
_DW6_SQL = """
WITH CTE_BOM(mat_code, in_cust_code, mat_use_qty, cum_in_cust_code,
             set_except_flag, insp_flag, in_gagong_proc_code) AS (
  SELECT i.item_code,
         CASE WHEN i.work_code > '' THEN i.work_code ELSE i.in_cust_code END,
         1,
         CONVERT(varchar(500),'||' + CASE WHEN i.work_code > '' THEN i.work_code
                                          ELSE i.in_cust_code END + '|'),
         '0',
         (SELECT insp_flag FROM nx.pr_m_item_sub s WHERE i.item_code = s.item_code),
         CONVERT(varchar(10),'')
    FROM nx.pr_m_item i
   WHERE i.item_code = ?
  UNION ALL
  SELECT b1.mat_code,
         CASE WHEN m.work_code > '' THEN m.work_code ELSE m.in_cust_code END,
         CONVERT(int, CASE WHEN cb.mat_use_qty = 0 THEN 0
                      ELSE CONVERT(NUMERIC(18,5), cb.mat_use_qty * b1.use_qty) END),
         CONVERT(varchar(500), cb.cum_in_cust_code + '|'
                 + CASE WHEN m.work_code > '' THEN m.work_code ELSE m.in_cust_code END + '|'),
         ISNULL(b1.set_except_flag,'0'),
         (SELECT insp_flag FROM nx.pr_m_item_sub s WHERE m.item_code = s.item_code),
         b1.in_gagong_proc_code
    FROM CTE_BOM cb
    JOIN nx.pr_m_item_bom b1 ON cb.mat_code = b1.item_code
    JOIN nx.pr_m_item m      ON b1.mat_code = m.item_code
   WHERE ISNULL(b1.except_flag,'0') <> '1'
     AND NOT EXISTS (SELECT '2' FROM nx.pr_m_mat WHERE mat_code = b1.mat_code)
)
SELECT mat_code, MAX(in_cust_code) in_cust_code, SUM(mat_use_qty) mat_use_qty,
       ISNULL(MAX(insp_flag),'N') insp_flag, ISNULL(in_gagong_proc_code,'') in_gpc,
       ISNULL((SELECT TOP 1 item_cost FROM nx.pr_m_item_cost
                WHERE item_code = a.mat_code AND cust_code = MAX(a.in_cust_code)
                  AND cost_tag = '1' AND cost_apply_ymd <= ? AND currency = 'KRW'
                ORDER BY cost_apply_ymd DESC),0) item_cost
  FROM CTE_BOM a
 WHERE a.in_cust_code = ?
   AND CHARINDEX('||' + a.in_cust_code + '||', a.cum_in_cust_code) = 0
   AND a.set_except_flag = '0'
 GROUP BY mat_code, in_gagong_proc_code
"""


def _set_bom_expand(cur, item, cust, ymd):
    """세트도번 → 그 거래처가 대는 자도번 목록. 레거시 dw_6 동일."""
    cur.execute(_DW6_SQL, item, ymd, cust)
    return [{"mat_code": str(r[0]).strip(), "cust": str(r[1] or "").strip(),
             "use_qty": float(r[2] or 0), "insp_flag": str(r[3] or "N").strip(),
             "in_gpc": str(r[4] or "").strip(), "cost": float(r[5] or 0)}
            for r in cur.fetchall()]


def _apply_sagub(cur, ymd, cust, mats, user, win, ref=""):
    """★사급 처리 — 레거시 ue_save_after ④⑤ (146·135 공통, 2026-08-30 이식).

       규칙(대표 확정): 우리가 사급 '판매'하면 협력사 사급재고가 늘고,
       그 협력사가 세트로 납품해 오면 자도번이 쓴 사급품만큼 **소진(−)** 된다.
       레거시 w_pu_stock_080 화면의 '사급출고(+입고칸)' vs '사급사용(−출고칸)'.

       ④ PU_T_SAGUB_STOCK  MERGE  — 잔액 감소. 판정 = pr_m_item_bom_sub.sagub_flag='1'
       ⑤ PU_T_SAGUB_MAINT  INSERT — 사용실적 tag='A'. 판정 = pr_m_item_bom.sagub_flag='1'
         ★④와 ⑤의 판정 테이블이 서로 다르다(원문 그대로. bom_sub 4,811 vs bom 1,557).

       mats = [(자도번, 입고수량)] — 세트입고로 파생된 자도번들.
       반환 = 사급실적 행수.
    """
    if not mats:
        return 0
    made = 0
    for mat_code, qty in mats:
        if not mat_code or not qty:
            continue
        # ④ 사급잔액 감소 (bom_sub 기준)
        cur.execute("""
            MERGE INTO nx.PU_T_SAGUB_STOCK AS T
            USING (SELECT b.mat_code, ? AS cust_code,
                          SUM(b.use_qty * ? * -1) AS MAINT_QTY
                     FROM nx.pr_m_item_bom b WITH(NOLOCK)
                     JOIN nx.pr_m_item_bom_sub c WITH(NOLOCK)
                       ON b.item_code=c.item_code AND b.mat_code=c.mat_code
                     JOIN nx.pr_m_item a WITH(NOLOCK) ON b.mat_code=a.item_code
                    WHERE b.item_code=? AND c.sagub_flag='1'
                    GROUP BY b.mat_code) AS S
               ON (T.MAT_CODE=S.mat_code AND T.CUST_CODE=S.cust_code)
             WHEN MATCHED THEN
                  UPDATE SET STOCK_QTY=ISNULL(T.STOCK_QTY,0)+S.MAINT_QTY,
                             UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
             WHEN NOT MATCHED THEN
                  INSERT (MAT_CODE,CUST_CODE,STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                  VALUES (S.mat_code,S.cust_code,S.MAINT_QTY,?,GETDATE(),?);
        """, cust, qty, mat_code, user, win, user, win)

        # ⑤ 사급 사용실적 (bom 기준)
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.PU_T_SAGUB_MAINT WHERE MAINT_YMD=?", ymd)
        sseq = int((cur.fetchone() or [0])[0] or 0)
        cur.execute("""
            INSERT INTO nx.PU_T_SAGUB_MAINT
                  (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                   ITEM_CODE,SET_MAINT_YMD,SET_MAINT_SEQ,
                   INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                   UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
            SELECT ?, ? + ROW_NUMBER() OVER (ORDER BY b.mat_code), 'A', ?, b.mat_code,
                   b.use_qty * ? * -1, ?, ?, ?, ?,
                   ?, GETDATE(), ?, ?, GETDATE(), ?
              FROM nx.pr_m_item_bom b WITH(NOLOCK)
              JOIN nx.pr_m_item a WITH(NOLOCK) ON b.mat_code=a.item_code
             WHERE b.item_code=? AND b.sagub_flag='1'
        """, ymd, sseq, cust, qty, ref, mat_code, ymd, 0,
             user, win, user, win, mat_code)
        made += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return made


@router.get("/api/setstock/bom")
def setstock_bom(item: str = Query(...), cust: str = Query(...), ymd: str = Query("")):
    """세트입고 시 파생될 자도번 미리보기(수동입고 팝업 확인용)."""
    ymd = _d6(ymd) or datetime.now().strftime("%y%m%d")
    cn = _nx(); cur = cn.cursor()
    try:
        rows = _set_bom_expand(cur, item.strip(), cust.strip(), ymd)
        return {"item": item, "cust": cust, "rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.get("/api/setstock/manual/prep")
def setstock_manual_prep(cust: str = Query(""), item: str = Query("")):
    """수동입고 팝업 보조 — 거래처의 세트도번 후보 + 현재고.
       레거시 w_pu_stock_146 그리드의 '도번 / 재고수량' 열."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = []; p = []
        if cust:
            w.append("m.cust_code=?"); p.append(cust)
        if item:
            w.append("m.item_code LIKE ?"); p.append("%" + item + "%")
        where = (" WHERE " + " AND ".join(w)) if w else ""
        # ★직납품 판정 — 레거시 ue_itemchanged 원문:
        #   pr_m_item.in_cust_code = 화면거래처 AND work_code = '' → '직납품'
        cur.execute(f"""SELECT TOP 500 m.item_code, ISNULL(i.item_name,'') itemnm,
                               SUM(m.maint_qty) stock_qty,
                               MAX(CASE WHEN ISNULL(pi.IN_CUST_CODE,'')=m.cust_code
                                         AND ISNULL(pi.WORK_CODE,'')=''
                                        THEN '1' ELSE '0' END) direct
                          FROM nx.set_stock_maint m WITH(NOLOCK)
                          LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code=m.item_code
                          LEFT JOIN nx.pr_m_item pi WITH(NOLOCK) ON pi.ITEM_CODE=m.item_code
                          {where}
                         GROUP BY m.item_code, i.item_name
                         ORDER BY m.item_code""", *p)
        rows = [{"item_code": str(r[0]).strip(), "itemnm": (r[1] or "").strip(),
                 "stock_qty": float(r[2] or 0),
                 "direct": (str(r[3] or "0").strip() == "1")} for r in cur.fetchall()]
        # 다음 수동입고NO (레거시 MANUAL_SHEET_NO = 날짜무관 연속채번, 1회 저장분은 같은 번호 공유)
        cur.execute("""SELECT ISNULL(MAX(TRY_CONVERT(int, manual_sheet_no)),0)+1
                         FROM nx.set_stock_maint WITH(NOLOCK)
                        WHERE ISNULL(manual_sheet_no,'')<>''""")
        nextno = int((cur.fetchone() or [1])[0] or 1)
        # ★거래처 목록을 함께 준다(2026-09-01) — 종전 화면은 `/api/base/partners` 를
        #   불렀는데 **그 엔드포인트가 없어 404** 였다. custMap 이 통째로 비어
        #   어떤 거래처를 넣어도 "일치하는 거래처가 없습니다"가 떴다(실측: 케이비/2266).
        custs = []
        try:
            cur.execute("""SELECT RTRIM(CUST_CODE), RTRIM(CUST_DESC)
                             FROM nx.CM_M_CUST WITH(NOLOCK)
                            WHERE ISNULL(RTRIM(CUST_DESC),'')<>''
                            ORDER BY CUST_DESC""")
            custs = [{"code": str(r[0]).strip(), "nm": str(r[1]).strip()}
                     for r in cur.fetchall()]
        except Exception:
            custs = []
        return {"rows": rows, "next_no": nextno, "custs": custs}
    finally:
        cn.close()


@router.post("/api/setstock/manual")
def setstock_manual(payload: dict = Body(...)):
    """★수동입고(장부입고) — 레거시 w_pu_stock_146 '자재세트일괄입고'.

       바코드 송장 없이 거래처+도번+수량을 직접 등록한다(MAINT_TAG='1').
       레거시 실측(2026-08-30, 라이브 1,391행):
         · MAINT_TAG='1' · MANUAL_SHEET_NO 채움 · SHEET_NO 는 비움
         · MANUAL_SHEET_NO = 날짜무관 연속채번, **1회 저장분은 같은 번호 공유**
           (예: 260819 no=734 에 3행 / 731~738 연속)
       payload: {ymd, cust, rows:[{item_code, qty, remark, direct}], user, scope}

       ★scope (2026-09-01 신설, 사용자 요청) — 재고 반영 범위
         'set'  세트재고만  : ①세트원장만 기록. 하위 자도번 재고는 **건드리지 않는다**
         'all'  하위재고반영: ①+② 종전 동작(세트 + 자도번 파생). 미지정 기본값
       왜: 세트만 장부로 잡고 하위 단품재고는 그대로 두어야 하는 경우가 있다.
           종전엔 항상 ②까지 돌아 하위 재고가 함께 움직였다.
    """
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    cust = str(payload.get("cust") or "").strip()
    user = str(payload.get("user") or "웹")[:20]
    scope = str(payload.get("scope") or "all").strip().lower()
    if scope not in ("set", "all"):
        scope = "all"
    rows = payload.get("rows") or []
    if not cust:
        raise HTTPException(400, "거래처를 선택하세요.")
    items = []
    for r in rows:
        ic = str(r.get("item_code") or "").strip()
        try:
            q = float(r.get("qty") or 0)
        except Exception:
            q = 0.0
        if not ic or not q:
            continue
        items.append((ic, q, str(r.get("remark") or "")[:250],
                      "1" if r.get("direct") else ""))
    if not items:
        raise HTTPException(400, "입고할 도번·수량을 입력하세요.")

    cn = _nx_tx(); cur = cn.cursor()
    try:
        _assert_open(cur, ymd, "MAT", "세트수동입고")      # ★마감잠금
        # 도번 유효성 — 없는 품번을 넣으면 잔액이 오염된다
        bad = []
        for ic, _q, _r, _d in items:
            cur.execute("SELECT COUNT(*) FROM nx.item WITH(NOLOCK) WHERE item_code=?", ic)
            if int((cur.fetchone() or [0])[0] or 0) == 0:
                bad.append(ic)
        if bad:
            raise HTTPException(400, "품목마스터에 없는 도번: " + ", ".join(bad[:10]))

        # 수동입고NO — 1회 저장분 전체가 공유(레거시 동일)
        cur.execute("""SELECT ISNULL(MAX(TRY_CONVERT(int, manual_sheet_no)),0)+1
                         FROM nx.set_stock_maint WITH(NOLOCK)
                        WHERE ISNULL(manual_sheet_no,'')<>''""")
        manual_no = int((cur.fetchone() or [1])[0] or 1)

        cur.execute("SELECT ISNULL(MAX(maint_seq),0) FROM nx.set_stock_maint WHERE maint_ymd=?", ymd)
        mseq = int((cur.fetchone() or [0])[0] or 0)

        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.stock_ledger WHERE MAINT_YMD=?", ymd)
        lseq = int((cur.fetchone() or [0])[0] or 0)

        made = []; posted = 0; sagub_src = []
        for ic, q, rem, direct in items:
            mseq += 1
            # ── ① 세트원장 (레거시 PU_T_SET_STOCK_MAINT tag='1')
            cur.execute("""INSERT INTO nx.set_stock_maint
                   (maint_ymd,maint_seq,maint_tag,in_tag,cust_code,item_code,maint_qty,
                    sheet_no,manual_sheet_no,item_gubun,status,derived_flag,remarks,
                    insert_user_id,insert_datetime)
                   VALUES(?,?,'1',?,?,?,?,NULL,?,'1','90','1',?,?,getdate())""",
                        ymd, mseq, ('2' if q < 0 else '1'), cust, ic, q,
                        str(manual_no), rem, user)

            # ── ② 자도번 파생 (레거시 dw_6 루프 → PU_T_STOCK_MAINT tag='S')
            #    거래처가 대는 자도번만 · qty×use_qty · Z99990/IS0001 하드코딩(원문 동일)
            #    ※검사품(insp S/F) 게이트는 이번 범위에서 제외(사용자 지시 2026-08-30) —
            #      원문은 재고반영을 건너뛰지만 지금은 전량 즉시 반영한다.
            #    ★scope='set' 이면 자도번 파생을 통째로 건너뛴다(하위 단품재고 무영향).
            jado = []
            if scope != "set":
                try:
                    jado = _set_bom_expand(cur, ic, cust, ymd)
                except Exception:
                    jado = []
            for b in jado:
                lseq += 1
                jq = q * (b["use_qty"] or 0)
                if not jq:
                    continue
                cur.execute("""INSERT INTO nx.stock_ledger
                       (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,WH_CUST_CODE,
                        GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,
                        ITEM_CODE,SET_MAINT_YMD,SET_MAINT_SEQ,INPUT_YMD,ITEM_GUBUN,
                        INSP_YMD,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                       VALUES('MAT',?,?,'S',?,'Z99990','IS0001',?,?,?,?,?,?,?,?,'1',
                              NULL,'세트수동입고',?,getdate())""",
                            ymd, lseq, cust, b["mat_code"], jq, b["cost"],
                            int(jq * b["cost"]), ic, ymd, mseq, ymd, user)
                posted += 1
                sagub_src.append((b["mat_code"], jq))
            made.append({"seq": mseq, "item_code": ic, "qty": q,
                         "direct": direct, "jado": len(jado)})

        # ── ④⑤ 사급 처리 (레거시 원문 — 세트입고로 들어온 자도번이 쓴 사급품 소진)
        #    ★scope='set' 이면 sagub_src 가 비어 있어 자연히 아무것도 안 한다.
        sagub = 0
        try:
            sagub = _apply_sagub(cur, ymd, cust, sagub_src, user, "w_pu_stock_146",
                                 ref="MANUAL#%s" % manual_no)
        except Exception:
            sagub = -1      # 사급 실패가 입고 자체를 막지 않는다

        cn.commit()
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "manual_no": manual_no, "ymd": ymd,
                "cust": cust, "count": len(made), "ledger_posted": posted,
                "sagub_posted": sagub, "scope": scope, "rows": made}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        raise HTTPException(500, str(e)[:300])
    finally:
        cn.close()


@router.post("/api/setstock/manual/delete")
def setstock_manual_delete(payload: dict = Body(...)):
    """수동입고 취소 — 수동입고NO 단위 삭제(근거키 스코프, §1-3 준수)."""
    no = str(payload.get("manual_no") or "").strip()
    if not no:
        raise HTTPException(400, "수동입고NO가 필요합니다.")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT COUNT(*), ISNULL(SUM(maint_qty),0), MIN(maint_ymd)
                         FROM nx.set_stock_maint WITH(NOLOCK)
                        WHERE manual_sheet_no=? AND maint_tag='1'""", no)
        r = cur.fetchone()
        cnt = int(r[0] or 0)
        if not cnt:
            raise HTTPException(404, f"수동입고NO {no} 를 찾을 수 없습니다.")
        _assert_open(cur, str(r[2] or ''), "MAT", "세트수동입고취소")
        # ★자도번 파생행(tag='S')도 함께 — 세트만 지우면 단품재고가 남는다.
        #   근거키 = 그 수동입고NO 가 만든 (SET_MAINT_YMD, SET_MAINT_SEQ) 쌍뿐(§1-3).
        cur.execute("""DELETE g FROM nx.stock_ledger g
                        WHERE g.MAINT_TAG='S'
                          AND EXISTS(SELECT 1 FROM nx.set_stock_maint m WITH(NOLOCK)
                                      WHERE m.manual_sheet_no=? AND m.maint_tag='1'
                                        AND m.maint_ymd=g.SET_MAINT_YMD
                                        AND m.maint_seq=g.SET_MAINT_SEQ)""", no)
        led = cur.rowcount
        # ★사급도 되돌린다 — 근거키 = REMARKS 에 심은 수동입고NO(§1-3 스코프 삭제)
        #   실적행의 부호를 반대로 잔액에 가산해 원복한 뒤 실적행을 지운다.
        sag = 0
        try:
            _tagno = "MANUAL#%s" % no
            cur.execute("""SELECT MAT_CODE, CUST_CODE, ISNULL(SUM(MAINT_QTY),0)
                             FROM nx.PU_T_SAGUB_MAINT WITH(NOLOCK)
                            WHERE MAINT_TAG='A' AND REMARKS=?
                            GROUP BY MAT_CODE, CUST_CODE""", _tagno)
            for mc, cc, qy in cur.fetchall():
                cur.execute("""UPDATE nx.PU_T_SAGUB_STOCK
                                  SET STOCK_QTY=ISNULL(STOCK_QTY,0)-?,
                                      UPDATE_DATETIME=GETDATE(),
                                      UPDATE_WINDOW='w_pu_stock_146(취소)'
                                WHERE MAT_CODE=? AND CUST_CODE=?""", float(qy or 0), mc, cc)
            cur.execute("DELETE FROM nx.PU_T_SAGUB_MAINT WHERE MAINT_TAG='A' AND REMARKS=?", _tagno)
            sag = cur.rowcount
        except Exception:
            sag = -1

        cur.execute("""DELETE FROM nx.set_stock_maint
                        WHERE manual_sheet_no=? AND maint_tag='1'""", no)
        cn.commit()
        stock_changed()
        return {"ok": True, "manual_no": no, "deleted": cnt,
                "ledger_deleted": led, "sagub_deleted": sag, "qty": float(r[1] or 0)}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    finally:
        cn.close()


# ===================== 자재세트재고조정 (레거시 w_pu_stock_135) =====================
@router.get("/api/setadj/list")
def setadj_list(fr: str = Query(""), to: str = Query(""), cust: str = Query(""),
                item: str = Query(""), limit: int = Query(1000)):
    """조정 이력(maint_tag='3')."""
    fr = _d6(fr) or ""; to = _d6(to) or ""
    w = ["m.maint_tag='3'"]; p = []
    if fr: w.append("m.maint_ymd>=?"); p.append(fr)
    if to: w.append("m.maint_ymd<=?"); p.append(to)
    if cust: w.append("m.cust_code=?"); p.append(cust)
    if item: w.append("m.item_code LIKE ?"); p.append("%" + item + "%")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT TOP {int(limit)} m.maint_ymd, m.maint_seq, m.cust_code,
                   ISNULL(c.CUST_DESC,'') custnm, m.item_code, ISNULL(i.item_name,'') itemnm,
                   m.maint_qty, ISNULL(m.remarks,'') remarks,
                   ISNULL(m.insert_user_id,'') user_id, m.insert_datetime
              FROM nx.set_stock_maint m WITH(NOLOCK)
              LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=m.cust_code
              LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code=m.item_code
             WHERE {' AND '.join(w)}
             ORDER BY m.maint_ymd DESC, m.maint_seq DESC""", *p)
        rows = []
        for r in cur.fetchall():
            rows.append({"ymd": (r[0] or "").strip(), "seq": int(r[1] or 0),
                         "cust_code": (r[2] or "").strip(), "cust_name": (r[3] or "").strip(),
                         "item_code": (r[4] or "").strip(), "item_name": (r[5] or "").strip(),
                         "qty": float(r[6] or 0), "remarks": (r[7] or "").strip(),
                         "user_id": (r[8] or "").strip(),
                         "dt": r[9].strftime("%Y-%m-%d %H:%M:%S") if r[9] else ""})
        return {"rows": rows, "cnt": len(rows), "total": sum(x["qty"] for x in rows)}
    finally:
        cn.close()


@router.post("/api/setadj/save")
def setadj_save(payload: dict = Body(...)):
    """★자재세트재고조정 — 레거시 w_pu_stock_135(장부수정, maint_tag='3').

       ★저장 대상은 **세트 계정 2곳뿐**이다 — PBL 원문 확정(sa_stock_01.pbl, 2026-08-30):
         ① PU_T_SET_STOCK_MAINT INSERT   ② f_pu_set_set_mat_stock 로 잔액 가산
       ⛔자도번 파생 **없음** — 창 소스 8,206자에 dw_6·PU_T_STOCK_MAINT·set_maint_seq 전부 0회.
         (입고 146/135 는 dw_6 루프로 파생하지만 조정 135 는 하지 않는다.
          라이브 실측도 tag='3' 전건 파생 0행으로 코드와 일치.)
       ⛔사급 처리 **없음** — SAGUB 문자열 0회(대표 확정과 일치. 사급은 별도 점검 대상).

       수정방법(레거시 dw_c1.reset_flag):
         '0' 가감  → 입력수량 그대로.        78 → +78 / -78 → -78
         '1' 변경  → maint_qty - stock_qty.  현재고 20 에 30 입력 → +10 만 기록
         ※차액 계산은 프론트가 하고 여기로는 이미 계산된 변동량이 온다.

       · (+)증가·(−)감소 둘 다 허용 (라이브 실측 7,545 / 2,312)
       · SHEET_NO·MANUAL_SHEET_NO 비움 · item_gubun 은 '' (원문 리터럴)
       payload: {ymd, rows:[{cust, item_code, qty, remark}], user}
    """
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    user = str(payload.get("user") or "웹")[:20]
    items = []
    for r in (payload.get("rows") or []):
        ic = str(r.get("item_code") or "").strip()
        cc = str(r.get("cust") or r.get("cust_code") or "").strip()
        try:
            q = float(r.get("qty") or 0)
        except Exception:
            q = 0.0
        if not ic or not cc or not q:
            continue
        items.append((cc, ic, q, str(r.get("remark") or "")[:250]))
    if not items:
        raise HTTPException(400, "조정할 거래처·도번·수량을 입력하세요.")

    cn = _nx_tx(); cur = cn.cursor()
    try:
        _assert_open(cur, ymd, "MAT", "세트재고조정")      # ★마감잠금
        bad = []
        for _cc, ic, _q, _r in items:
            cur.execute("SELECT COUNT(*) FROM nx.item WITH(NOLOCK) WHERE item_code=?", ic)
            if int((cur.fetchone() or [0])[0] or 0) == 0:
                bad.append(ic)
        if bad:
            raise HTTPException(400, "품목마스터에 없는 도번: " + ", ".join(bad[:10]))

        cur.execute("SELECT ISNULL(MAX(maint_seq),0) FROM nx.set_stock_maint WHERE maint_ymd=?", ymd)
        mseq = int((cur.fetchone() or [0])[0] or 0)
        made = []
        for cc, ic, q, rem in items:
            mseq += 1
            # ★세트원장 INSERT 하나가 전부. 잔액은 이 원장의 SUM 으로 도출된다
            #   (레거시 f_pu_set_set_mat_stock = PU_T_SET_MAT_STOCK 가산에 대응).
            #   자도번 파생·사급 없음 — PBL 원문 확정.
            cur.execute("""INSERT INTO nx.set_stock_maint
                   (maint_ymd,maint_seq,maint_tag,in_tag,cust_code,item_code,maint_qty,
                    sheet_no,manual_sheet_no,item_gubun,status,derived_flag,remarks,
                    insert_user_id,insert_datetime)
                   VALUES(?,?,'3',?,?,?,?,NULL,NULL,'','90','0',?,?,getdate())""",
                        ymd, mseq, ('2' if q < 0 else '1'), cc, ic, q, rem, user)
            made.append({"seq": mseq, "cust": cc, "item_code": ic, "qty": q})

        cn.commit()
        stock_changed()
        return {"ok": True, "ymd": ymd, "count": len(made), "rows": made}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        raise HTTPException(500, str(e)[:300])
    finally:
        cn.close()


@router.post("/api/setadj/delete")
def setadj_delete(payload: dict = Body(...)):
    """조정 취소 — (maint_ymd, maint_seq) 단건 삭제(근거키 스코프, §1-3)."""
    ymd = _d6(str(payload.get("ymd") or ""))
    try:
        seq = int(payload.get("seq") or 0)
    except Exception:
        seq = 0
    if not ymd or not seq:
        raise HTTPException(400, "조정일자·SEQ 가 필요합니다.")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT item_code, cust_code, maint_qty FROM nx.set_stock_maint WITH(NOLOCK)
                        WHERE maint_ymd=? AND maint_seq=? AND maint_tag='3'""", ymd, seq)
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, f"조정건({ymd}/{seq})을 찾을 수 없습니다.")
        _assert_open(cur, ymd, "MAT", "세트재고조정취소")
        cur.execute("""DELETE FROM nx.set_stock_maint
                        WHERE maint_ymd=? AND maint_seq=? AND maint_tag='3'""", ymd, seq)
        cn.commit()
        stock_changed()
        return {"ok": True, "ymd": ymd, "seq": seq,
                "item_code": str(r[0]).strip(), "qty": float(r[2] or 0)}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    finally:
        cn.close()


def _upd_mat_wh(cur, mat, dq, cc="Z99990", gp="IS0001"):
    """자재창고 재고 증감 — nx.PU_T_MAT_STOCK_WH + nx.PU_T_MAT_STOCK.

    레거시 `f_pu_set_mat_stock_wh` / `f_pu_set_mat_stock` 대응.
    ★버킷키 = 창고 소유주 'Z99990' 고정 + 가공처 'IS0001'(입고창고) — 원장과 동일.
      매입처를 버킷키에 쓰면 같은 창고에 유령 버킷이 생긴다(2026-09-01 기존 사고).
    ★없으면 INSERT, 있으면 누적 UPDATE. 실패해도 원장은 남긴다(이력 우선, stock.py:427 동일).
    """
    if not mat or not dq:
        return
    for wh in (True, False):          # True=창고별(WH) · False=자재합계
        try:
            if wh:
                cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                  UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='setinsp'
                                WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                            dq, mat, cc, gp)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,
                                      STOCK_QTY,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                    VALUES(?,?,?,?,'web',GETDATE(),'setinsp')""", mat, cc, gp, dq)
            else:
                cur.execute("""UPDATE nx.PU_T_MAT_STOCK SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                                  UPDATE_USER_ID='web', UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='setinsp'
                                WHERE MAT_CODE=? AND CUST_CODE=?""", dq, mat, cc)
                if cur.rowcount == 0:
                    cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK(MAT_CODE,CUST_CODE,STOCK_QTY,
                                      UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                                    VALUES(?,?,?,'web',GETDATE(),'setinsp')""", mat, cc, dq)
        except Exception:
            pass


def _derive_set_stock(cur, cust, doban, qty, sheet, bc, mseq, today):
    """세트입고 '입고완료(90)' 시 자도번 재고파생 + 협력사 사급소진.

    ★입고 시점(setstock_receive)과 검사완료 시점(setinsp_complete)이 **같은 처리**를 해야 한다.
      그래서 블록을 함수로 뺐다 — 한쪽만 고치면 검사품과 무검사품의 재고가 갈린다.
      (2026-09-01 자재입고검사관리 신설 시 분리. 로직은 종전 원문 그대로.)

    반환 = 원장에 넣은 행수.
    """
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.stock_ledger WHERE MAINT_YMD=?", today)
    lseq = int(cur.fetchone()[0])
    # ★레거시 135(dw_pr_input_135_5) 원문: 세트입고요청 명세(_DTL)를 그대로 읽는다.
    #   단가 = pr_m_item_cost(cost_tag='1', 거래처별, 입고일 이하 최신). 입고창고 'IS0001' 하드코딩.
    #   ※웹 명세(set_input_req_dtl)가 비어 있으면 미러(_DTL)를 원천으로 쓴다.
    cur.execute("""SELECT d.mat_code, d.use_qty,
                          ISNULL((SELECT TOP 1 c.item_cost FROM nx.pr_m_item_cost c WITH(NOLOCK)
                                   WHERE c.item_code=d.mat_code AND c.cust_code=?
                                     AND c.cost_tag='1' AND c.currency='KRW'
                                     AND c.cost_apply_ymd<=? ORDER BY c.cost_apply_ymd DESC),0) cost
                     FROM nx.set_input_req_dtl d WITH(NOLOCK)
                    WHERE d.sheet_no=?""", cust, today, sheet)
    dtl = cur.fetchall()
    if not dtl:
        cur.execute("""SELECT d.MAT_CODE, d.USE_QTY,
                              ISNULL((SELECT TOP 1 c.item_cost FROM nx.pr_m_item_cost c WITH(NOLOCK)
                                       WHERE c.item_code=d.MAT_CODE AND c.cust_code=?
                                         AND c.cost_tag='1' AND c.currency='KRW'
                                         AND c.cost_apply_ymd<=? ORDER BY c.cost_apply_ymd DESC),0) cost
                         FROM nx.PU_T_SET_INPUT_REQ_DTL d WITH(NOLOCK)
                        WHERE d.SHEET_NO=? AND ISNULL(d.ITEM_GUBUN,'1')='1'""", cust, today, sheet)
        dtl = cur.fetchall()
    posted = 0
    bcn = int(bc) if str(bc).isdigit() else None
    for mat, uq, cost in dtl:
        lseq += 1
        jqty = float(qty) * float(uq or 1)
        cst = float(cost or 0)
        cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,SHEET_NO,
              CUST_CODE,WH_CUST_CODE,GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,
              ITEM_CODE,SET_MAINT_YMD,SET_MAINT_SEQ,INPUT_YMD,ITEM_GUBUN,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
            VALUES('MAT',?,?,'S',?,?,'Z99990','IS0001',?,?,?,?,?,?,?,?,'1','세트입고','web',getdate())""",
            today, lseq, bcn, cust, str(mat).strip(), jqty, cst, int(jqty * cst),
            doban, today, mseq, today)
        # ★★자재창고 재고 반영 (2026-09-01 추가) — 원장만 넣으면 「자재 입출고현황」에 안 잡힌다.
        #   레거시 w_qa_input_160 `ue_save` 가 f_pu_set_mat_stock / f_pu_set_mat_stock_wh 를
        #   부르는 자리다. 실측: 검사완료 후 원장 +6 인데 PU_T_MAT_STOCK_WH 는 0 그대로였다.
        #   ⟹ 세트재고(set_stock_maint)만 늘고 자재재고가 안 늘어 두 화면이 어긋났다.
        #   버킷키 = 창고 소유주 'Z99990' + 입고창고 'IS0001' (원장과 동일, stock.py:417-427 패턴).
        _upd_mat_wh(cur, str(mat).strip(), jqty)
        posted += 1
    cur.execute("UPDATE nx.set_stock_maint SET derived_flag='1' WHERE maint_ymd=? AND maint_seq=?",
                today, mseq)
    # ★협력사출고(사급소진) — 완제품 doban×qty 만큼 협력사 사급재고 차감(nx.sagub_maint tag S, −). 소요엔진(§10).
    #   _apply_sagub(수동입고 146 경로)와 나란히 두지 말 것 — 같은 소진이 두 번 잡힌다.
    _post_sagub_out(cur, cust, doban, qty, today, mseq)
    return posted


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
            if newstat == "90":  # 입고완료 → 자도번 재고파생 + 사급소진
                # ★2026-09-01 블록을 _derive_set_stock 으로 분리(로직 무변경).
                #   검사완료(자재입고검사관리)에서 **같은 함수**를 부른다 —
                #   한쪽만 고치면 검사품과 무검사품의 재고 결과가 갈린다.
                posted += _derive_set_stock(cur, cust, doban, qty, sheet, bc, mseq, _today)
        cn.commit()
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림(캐시 stale 금지)
        return {"ok": True, "received": recv, "ledger_posted": posted,
                "barcode": "SET" + bc}
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


# ═══════════════════════════════════════════════════════════════════════
# 자재입고검사관리 (IQC) — 레거시 w_qa_input_160  ★2026-09-01 신설
#
# 업무흐름 (레거시 PBL `ue_save` 원문 + 실측으로 확정)
#   바코드 입고 → 검사품(insp_flag='1')은 **입고대기(30)** 로 멈춘다.
#                 이때 재고파생도 사급소진도 **하지 않는다**(setin.py 의 90 분기 밖).
#   IQC 검사완료 → 30→90 + 재고파생 + 사급소진   = 무검사품이 입고 즉시 하던 것과 동일
#
#   ★레거시는 원장(PU_T_STOCK_MAINT) 한 테이블에서 insp_proc_flag 로만 갈리지만,
#     웹 세트입고는 status(30/90) 로 갈린다. 개념은 같다(행은 있고 재고만 보류).
#     실측 2026-09-01: status 30 = 15건 derived 0 · 사급 0 / status 90 = 52건 derived 52 · 사급 8/8
#
#   ★재고 반영은 **_derive_set_stock 한 함수**로 통일한다(입고 시점과 동일 처리).
#     레거시가 f_pu_set_mat_stock / f_pu_set_mat_stock_wh 를 부르는 자리에 해당한다.
#
# 범위: 세트입고(TAG 'S')만. 개별 자재입고(TAG '9')는 사용자 지시로 이번 제외.
# 분석 정본 = _legacy_analysis/QA_INPUT_160_IQC_ANALYSIS.md
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/setinsp/list")
def setinsp_list(request: Request, frm: str = Query(""), to: str = Query(""),
                 cust: str = Query(""), item: str = Query(""),
                 stat: str = Query("30"), limit: int = Query(500)):
    """검사대상 목록. stat: 30=입고대기(기본) · 90=검사완료 · ''=전체.

    레거시 160 대응 컬럼(입고일자·입고SEQ·입고구분·거래처·자도번·입고수량·검사구분·상태)을 채운다.
    ★거래처·품명은 LEFT JOIN — 레거시는 cm_m_cust INNER 라 미등록 거래처가 통째로 누락된다(§1-7 결함).
    """
    staff_only(request, "자재입고검사")
    f6, t6 = _d6(frm), _d6(to)
    w, p = ["m.in_tag='1'"], []
    if f6: w.append("m.maint_ymd>=?"); p.append(f6)
    if t6: w.append("m.maint_ymd<=?"); p.append(t6)
    s = str(stat or "").strip()
    if s: w.append("RTRIM(ISNULL(m.status,''))=?"); p.append(s)
    if cust.strip():
        w.append("(RTRIM(ISNULL(m.cust_code,'')) LIKE ? OR ISNULL(c.CUST_DESC,'') LIKE ?)")
        p += ["%" + cust.strip() + "%"] * 2
    if item.strip():
        w.append("RTRIM(ISNULL(m.item_code,'')) LIKE ?"); p.append("%" + item.strip() + "%")
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT TOP {} m.maint_ymd, m.maint_seq, RTRIM(ISNULL(m.maint_tag,'')),
                  RTRIM(ISNULL(m.cust_code,'')), ISNULL(RTRIM(c.CUST_DESC),''),
                  RTRIM(ISNULL(m.item_code,'')), ISNULL(RTRIM(i.ITEM_DESC),''),
                  CAST(ISNULL(m.maint_qty,0) AS float), RTRIM(ISNULL(m.sheet_no,'')),
                  RTRIM(ISNULL(m.status,'')), RTRIM(ISNULL(m.derived_flag,'0')),
                  CONVERT(varchar(19), m.insert_datetime, 120),
                  ISNULL(RTRIM(q.insp_flag),'0'), RTRIM(ISNULL(q.sheet_no,'')),
                  CONVERT(varchar(19), q.status_dt, 120), ISNULL(RTRIM(q.status_user),'')
             FROM nx.set_stock_maint m WITH(NOLOCK)
             LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON RTRIM(c.CUST_CODE)=RTRIM(m.cust_code)
             LEFT JOIN nx.PR_M_ITEM i WITH(NOLOCK) ON RTRIM(i.ITEM_CODE)=RTRIM(m.item_code)
             LEFT JOIN nx.set_input_req q WITH(NOLOCK)
                    ON RTRIM(ISNULL(q.barcode_no,''))=RTRIM(ISNULL(m.sheet_no,''))
                   AND RTRIM(ISNULL(q.item_code,''))=RTRIM(ISNULL(m.item_code,''))
            WHERE {} ORDER BY m.maint_ymd DESC, m.maint_seq DESC""".format(
            max(1, min(int(limit or 500), 3000)), " AND ".join(w)), *p)
        rows = [{"ymd": str(r[0]).strip(), "seq": int(r[1] or 0), "tag": r[2],
                 "cust": r[3], "cust_nm": r[4], "item": r[5], "item_nm": r[6],
                 "qty": float(r[7] or 0), "sheet": r[8], "stat": r[9],
                 "derived": r[10], "in_dt": r[11], "insp": r[12], "req_sheet": r[13],
                 "insp_dt": r[14], "insp_user": r[15]} for r in cur.fetchall()]
        return {"ok": True, "rows": rows, "cnt": len(rows),
                "qty": sum(x["qty"] for x in rows)}
    finally:
        cn.close()


@router.post("/api/setinsp/complete")
def setinsp_complete(request: Request, payload: dict = Body(...)):
    """★검사완료 — 선택건 30→90 + 재고파생 + 사급소진.

    레거시 `ue_save` case 'I' 대응. 입고 시점의 90 분기와 **같은 함수**(_derive_set_stock)를 쓴다.
    ★이미 90 이면 건너뛴다 — 레거시도 `if insp_proc_flag='1' then (아무것도 안 함)` 이다.
      이 가드가 곧 이중 재고파생 방지 장치다(멱등이 아니므로 반드시 유지).
    """
    u = staff_only(request, "검사완료")
    items = payload.get("items") or []
    if not items:
        raise HTTPException(400, "검사완료할 항목을 선택하세요.")
    who = str((u or {}).get("nm") or (u or {}).get("id") or "web")[:20]
    cn = _nx(); cur = cn.cursor()
    try:
        done = 0; posted = 0; skipped = []
        for it in items:
            ymd = str(it.get("ymd", "") or "").strip()
            seq = int(it.get("seq") or 0)
            if not ymd or not seq:
                continue
            cur.execute("""SELECT RTRIM(ISNULL(status,'')), RTRIM(ISNULL(cust_code,'')),
                                  RTRIM(ISNULL(item_code,'')), CAST(ISNULL(maint_qty,0) AS float),
                                  RTRIM(ISNULL(sheet_no,''))
                             FROM nx.set_stock_maint WHERE maint_ymd=? AND maint_seq=?""", ymd, seq)
            r = cur.fetchone()
            if not r:
                skipped.append(f"{ymd}-{seq}: 입고내역 없음"); continue
            st, cust, doban, qty, bc = r[0], r[1], r[2], float(r[3] or 0), r[4]
            if st == "90":
                skipped.append(f"{ymd}-{seq} {doban}: 이미 검사완료"); continue
            if st != "30":
                skipped.append(f"{ymd}-{seq} {doban}: 입고대기(30) 아님(현재 {st})"); continue
            # ★★sheet_no 와 barcode_no 는 다르다 (2026-09-01 실측으로 확인)
            #     set_stock_maint.sheet_no  = SET바코드   (setin.py 입고 시 bc 를 넣는다)
            #     set_input_req.sheet_no    = 송장번호     ← 명세(set_input_req_dtl)의 키
            #     set_input_req.barcode_no  = SET바코드
            #   _derive_set_stock 은 **송장번호**를 받아야 명세를 찾는다.
            #   바코드를 그대로 넘기면 명세 0행 → 재고가 한 행도 안 생긴다(실측으로 잡음).
            cur.execute("""SELECT TOP 1 RTRIM(ISNULL(sheet_no,'')) FROM nx.set_input_req
                            WHERE RTRIM(ISNULL(barcode_no,''))=? AND RTRIM(ISNULL(item_code,''))=?
                            ORDER BY CASE WHEN RTRIM(ISNULL(status,''))='30' THEN 0 ELSE 1 END, id DESC""",
                        bc, doban)
            _s = cur.fetchone()
            sheet = str(_s[0]).strip() if _s else ""
            if not sheet:
                skipped.append(f"{ymd}-{seq} {doban}: 송장(set_input_req)을 찾을 수 없음 — 바코드 {bc}")
                continue
            _assert_open(cur, ymd, "MAT", "검사완료")      # ★마감잠금
            # ① 상태 전환
            cur.execute("""UPDATE nx.set_stock_maint SET status='90'
                            WHERE maint_ymd=? AND maint_seq=?""", ymd, seq)
            cur.execute("""UPDATE nx.set_input_req SET status='90', status_dt=GETDATE(), status_user=?
                            WHERE RTRIM(ISNULL(sheet_no,''))=? AND RTRIM(ISNULL(status,''))='30'""",
                        who, sheet)
            # ② 재고파생 + 사급소진 (입고 시점과 동일 함수)
            #    ★원장 일자는 **입고일(ymd)** 로 맞춘다 — 검사일로 넣으면 입고와 재고가 다른 날에 잡힌다.
            posted += _derive_set_stock(cur, cust, doban, qty, sheet, bc, seq, ymd)
            done += 1
        cn.commit()
        stock_changed()          # ★재고 변경 → 수불장 캐시 버림
        return {"ok": True, "done": done, "ledger_posted": posted,
                "skipped": skipped, "by": who}
    finally:
        cn.close()


@router.post("/api/setinsp/cancel")
def setinsp_cancel(request: Request, payload: dict = Body(...)):
    """검사취소 — 90→30 + 재고파생/사급 되돌림. 레거시 `ue_save` case 'D' 대응.

    ★되돌림은 **행 삭제**가 아니라 근거키 스코프 삭제다(§1-3):
      원장은 (MAINT_YMD, MAINT_TAG='S', SET_MAINT_SEQ=해당 입고seq) 로만 지운다.
      사급은 remarks_src='setstock:<seq>' 로만 지운다. 태그 기반 대량삭제 금지.
    """
    u = staff_only(request, "검사취소")
    items = payload.get("items") or []
    if not items:
        raise HTTPException(400, "검사취소할 항목을 선택하세요.")
    who = str((u or {}).get("nm") or (u or {}).get("id") or "web")[:20]
    cn = _nx(); cur = cn.cursor()
    try:
        done = 0; removed = 0; skipped = []
        for it in items:
            ymd = str(it.get("ymd", "") or "").strip()
            seq = int(it.get("seq") or 0)
            if not ymd or not seq:
                continue
            cur.execute("""SELECT RTRIM(ISNULL(status,'')), RTRIM(ISNULL(item_code,'')),
                                  RTRIM(ISNULL(sheet_no,''))
                             FROM nx.set_stock_maint WHERE maint_ymd=? AND maint_seq=?""", ymd, seq)
            r = cur.fetchone()
            if not r:
                skipped.append(f"{ymd}-{seq}: 입고내역 없음"); continue
            st, doban, bc = r[0], r[1], r[2]
            if st != "90":
                skipped.append(f"{ymd}-{seq} {doban}: 검사완료 상태가 아님(현재 {st})"); continue
            _assert_open(cur, ymd, "MAT", "검사취소")
            # ★창고재고도 되돌린다 — 원장만 지우면 「자재 입출고현황」에 수량이 남는다.
            #   지울 행의 수량을 먼저 읽어 반대부호로 창고에 반영한 뒤 원장을 지운다.
            cur.execute("""SELECT RTRIM(MAT_CODE), CAST(MAINT_QTY AS float) FROM nx.stock_ledger
                            WHERE MAINT_YMD=? AND MAINT_TAG='S' AND SET_MAINT_SEQ=?""", ymd, seq)
            for _m, _q in cur.fetchall():
                _upd_mat_wh(cur, str(_m).strip(), -float(_q or 0))
            cur.execute("""DELETE FROM nx.stock_ledger
                            WHERE MAINT_YMD=? AND MAINT_TAG='S' AND SET_MAINT_SEQ=?""", ymd, seq)
            removed += int(cur.rowcount or 0)
            cur.execute("""DELETE FROM nx.sagub_maint
                            WHERE RTRIM(maint_ymd)=? AND RTRIM(ISNULL(remarks_src,''))=?""",
                        ymd, "setstock:" + str(seq))
            cur.execute("""UPDATE nx.set_stock_maint SET status='30', derived_flag='0'
                            WHERE maint_ymd=? AND maint_seq=?""", ymd, seq)
            cur.execute("""UPDATE nx.set_input_req SET status='30', status_dt=GETDATE(), status_user=?
                            WHERE RTRIM(ISNULL(barcode_no,''))=? AND RTRIM(ISNULL(item_code,''))=?
                              AND RTRIM(ISNULL(status,''))='90'""", who, bc, doban)
            done += 1
        cn.commit()
        stock_changed()
        return {"ok": True, "done": done, "ledger_removed": removed,
                "skipped": skipped, "by": who}
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
