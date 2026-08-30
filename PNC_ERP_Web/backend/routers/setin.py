# -*- coding: utf-8 -*-
"""협력사 세트입고(setin/setstock) 도메인 라우터 — 세트입고요청·명세·실입고·바코드스캔. _fmtbiz(사업자번호 포맷)는 로컬.
   app.py에서 분리. 공유헬퍼는 common.py."""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
# ★라이브(_conn) 미import — 이 도메인은 nx 단일소스(§1-9-1). 실수로 쓰이지 않게 뺀다.
from common import _nx, _nx_tx, _d6, _assert_open, stock_changed

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
        return {"barcode": bc, "cust": rows[0]["in_cust_code"], "custnm": rows[0]["custnm"], "rows": rows}
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
        return {"rows": rows, "next_no": nextno}
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
       payload: {ymd, cust, rows:[{item_code, qty, remark, direct}], user}
    """
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    cust = str(payload.get("cust") or "").strip()
    user = str(payload.get("user") or "웹")[:20]
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
            jado = []
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
                "sagub_posted": sagub, "rows": made}
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
        cur.execute("""SELECT h.sheet_no, h.item_code, ISNULL(h.deliver_qty,h.input_req_qty) qty, h.in_cust_code,
              ISNULL(h.insp_flag,'0') insp FROM nx.set_input_req h WHERE h.barcode_no=? AND h.status IN ('10','30')""", bc)
        reqs = cur.fetchall()
        if not reqs:
            raise HTTPException(404, "발행 상태의 송장이 없습니다(이미 입고완료?).")
        recv = 0; posted = 0; sagub_src = []
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
                # ★레거시 135(dw_pr_input_135_5) 원문: 세트입고요청 명세(_DTL)를 그대로 읽는다.
                #   146(수동)의 BOM 재귀전개와 달리, 바코드는 이미 확정된 mat_code/use_qty 사용.
                #   단가 = pr_m_item_cost(cost_tag='1', 거래처별, 입고일 이하 최신) — 원문 동일.
                #   입고창고는 원문에서 'IS0001' 하드코딩(계산값 미사용).
                #   ※웹 명세(set_input_req_dtl)가 비어 있으면 미러(_DTL)를 원천으로 쓴다.
                cur.execute("""SELECT d.mat_code, d.use_qty,
                                      ISNULL(s.insp_flag,'N') insp,
                                      ISNULL((SELECT TOP 1 c.item_cost FROM nx.pr_m_item_cost c WITH(NOLOCK)
                                               WHERE c.item_code=d.mat_code AND c.cust_code=?
                                                 AND c.cost_tag='1' AND c.currency='KRW'
                                                 AND c.cost_apply_ymd<=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)
                                               ORDER BY c.cost_apply_ymd DESC),0) cost
                                 FROM nx.set_input_req_dtl d WITH(NOLOCK)
                                 LEFT JOIN nx.pr_m_item_sub s WITH(NOLOCK) ON s.item_code=d.mat_code
                                WHERE d.sheet_no=?""", cust, sheet)
                dtl = cur.fetchall()
                if not dtl:
                    cur.execute("""SELECT d.MAT_CODE, d.USE_QTY,
                                          ISNULL(s.insp_flag,'N') insp,
                                          ISNULL((SELECT TOP 1 c.item_cost FROM nx.pr_m_item_cost c WITH(NOLOCK)
                                                   WHERE c.item_code=d.MAT_CODE AND c.cust_code=?
                                                     AND c.cost_tag='1' AND c.currency='KRW'
                                                     AND c.cost_apply_ymd<=RIGHT(CONVERT(varchar(8),GETDATE(),112),6)
                                                   ORDER BY c.cost_apply_ymd DESC),0) cost
                                     FROM nx.PU_T_SET_INPUT_REQ_DTL d WITH(NOLOCK)
                                     LEFT JOIN nx.pr_m_item_sub s WITH(NOLOCK) ON s.item_code=d.MAT_CODE
                                    WHERE d.SHEET_NO=? AND ISNULL(d.ITEM_GUBUN,'1')='1'""", cust, sheet)
                    dtl = cur.fetchall()
                for mat, uq, _insp, cost in dtl:
                    lseq += 1
                    jqty = qty * float(uq or 1)
                    cst = float(cost or 0)
                    bcn = int(bc) if bc.isdigit() else None
                    cur.execute("""INSERT INTO nx.stock_ledger(STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,SHEET_NO,
                          CUST_CODE,WH_CUST_CODE,GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,
                          ITEM_CODE,SET_MAINT_YMD,SET_MAINT_SEQ,INPUT_YMD,ITEM_GUBUN,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                        VALUES('MAT',RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,'S',?,?,'Z99990','IS0001',?,?,?,?,?,
                               RIGHT(CONVERT(varchar(8),GETDATE(),112),6),?,RIGHT(CONVERT(varchar(8),GETDATE(),112),6),
                               '1','세트입고','web',getdate())""",
                        lseq, bcn, cust, str(mat).strip(), jqty, cst, int(jqty * cst), doban, mseq)
                    posted += 1
                    sagub_src.append((str(mat).strip(), jqty))
                cur.execute("UPDATE nx.set_stock_maint SET derived_flag='1' WHERE maint_ymd=RIGHT(CONVERT(varchar(8),GETDATE(),112),6) AND maint_seq=?", mseq)

        # ── ④⑤ 사급 처리 (레거시 135 원문 — 세트입고분이 쓴 사급품 소진)
        sagub = 0
        try:
            cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
            _t6 = cur.fetchone()[0]
            sagub = _apply_sagub(cur, _t6, str(reqs[0][3] or "").strip(), sagub_src,
                                 "web", "w_pr_input_135", ref="SETBC#%s" % bc)
        except Exception:
            sagub = -1

        cn.commit()
        stock_changed()      # ★재고 변경 → 수불장 캐시 버림(캐시 stale 금지)
        return {"ok": True, "received": recv, "ledger_posted": posted,
                "sagub_posted": sagub, "barcode": "SET" + bc}
    finally:
        cn.close()
