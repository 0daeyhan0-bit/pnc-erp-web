# -*- coding: utf-8 -*-
"""제품재고조정 (레거시 w_sa_stock_010) — 제품수불원장(SA_T_STOCK_MAINT) 조회 + 수동 재고조정 CRUD.
★컷오버 원칙(saleout과 동일): 조회 = nx.SA_T_STOCK_MAINT 미러(기존이력 J/P/2, 읽기전용) ∪ nx.prod_stock_adjust(웹조정, 편집).
쓰기(추가/수정/삭제) = 신규 nx.prod_stock_adjust (미러 delta-sync clobber 방지). 채번 MAINT_SEQ = 일자별 max+1(미러+웹 통합).
수정구분(MAINT_TAG): J=출하등록(w_pr_input_040 자동·음수) / P=생산입고(w_pr_input_260/520 자동·양수) / 2=재고조정(수동) / R=반품 / 1=불량."""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _nx_tx

router = APIRouter()

_TAGS = {"J": "출하등록", "P": "생산입고", "2": "재고조정", "R": "반품", "1": "불량"}


@router.get("/api/prodstockadj/list")
def prodstockadj_list(fr: str = Query(""), to: str = Query(""), tag: str = Query(""),
                      item: str = Query(""), limit: int = Query(1500)):
    """제품재고조정 목록 = nx.SA_T_STOCK_MAINT 미러(이력·읽기전용) ∪ nx.prod_stock_adjust(웹조정·편집).
    tag: 빈값/%=전체, 그외 해당 수정구분만. item=도번 LIKE. 수량/부호 원본유지(J출하=음수)."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["1=1"]; pf = []
        if fr: w.append("m.maint_ymd>=?"); pf.append(fr)
        if to: w.append("m.maint_ymd<=?"); pf.append(to)
        if tag and tag != "%": w.append("m.maint_tag=?"); pf.append(tag)
        if item: w.append("m.item_code LIKE ?"); pf.append(f"%{item}%")
        where = " AND ".join(w)
        SEL = """SELECT {idcol} id, '{src}' src, m.maint_ymd, m.maint_seq, m.maint_tag,
              m.item_code, ISNULL(i.ITEM_DESC,'') itemnm, m.cust_code,
              ISNULL(m.maint_qty,0) maint_qty, ISNULL(m.maint_cost,0) maint_cost, ISNULL(m.maint_amt,0) maint_amt,
              ISNULL(m.remarks,'') remarks, m.work_order, m.split_work_order,
              m.insert_user_id reg_user, {upd} upd_user, ISNULL(m.update_datetime,m.insert_datetime) work_dt
            FROM {tbl} m LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM i ON i.ITEM_CODE=m.item_code
            WHERE {where}"""
        leg_sel = SEL.format(idcol="NULL", src="legacy", upd="m.update_user_id",
                             tbl="PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT", where=where)
        web_sel = SEL.format(idcol="m.id", src="web", upd="m.upd_user",
                             tbl="nx.prod_stock_adjust", where=where)
        cur.execute(f"""SELECT TOP {int(limit)} * FROM ({web_sel} UNION ALL {leg_sel}) u
            ORDER BY maint_ymd DESC, maint_seq DESC""", *(pf + pf))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["tagnm"] = _TAGS.get(str(r.get("maint_tag") or "").strip(), str(r.get("maint_tag") or ""))
            r["editable"] = 1 if (r.get("src") == "web" and r.get("id") is not None) else 0
        totqty = sum(float(r["maint_qty"] or 0) for r in rows)
        totamt = sum(float(r["maint_amt"] or 0) for r in rows)
        return {"rows": rows, "tags": _TAGS, "totqty": totqty, "totamt": totamt}
    finally:
        cn.close()


def _next_seq(cur, ymd):
    """채번: MAINT_SEQ = 해당 일자 미러+웹 통합 max+1."""
    cur.execute("""SELECT ISNULL(MAX(s),0)+1 FROM (
          SELECT MAX(maint_seq) s FROM PARTNER_ERP_TEST3.nx.SA_T_STOCK_MAINT WHERE maint_ymd=?
          UNION ALL SELECT MAX(maint_seq) s FROM nx.prod_stock_adjust WHERE maint_ymd=?) t""", ymd, ymd)
    return int(cur.fetchone()[0] or 1)


def _pa_mirror_ins(cur, ymd, seq, tag, cust, item, qty, cost, amt, vat, wo, swo, rmk):
    """★제품재고조회(w_pr_stock_040, _salesstock)는 SA_T_STOCK_MAINT를 읽음 → 제품재고조정이 여기에도 써야 조회 반영.
       링크=(MAINT_YMD,MAINT_SEQ)=prod_stock_adjust와 동일 seq(_next_seq가 미러+웹 통합 max+1이라 충돌없음). INSERT_WINDOW='prodstockadj'로 웹행 식별."""
    try:
        cur.execute("""INSERT INTO nx.SA_T_STOCK_MAINT
              (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,MAINT_QTY,MAINT_COST,MAINT_VAT,MAINT_AMT,
               WORK_ORDER,SPLIT_WORK_ORDER,REMARKS,INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'web',GETDATE(),'prodstockadj')""",
            ymd, seq, str(tag or '2').strip()[:1] or '2', cust, item, qty, cost, vat, amt, wo, swo, rmk)
    except Exception: pass
def _pa_mirror_del(cur, ymd, seq):
    try:
        cur.execute("DELETE FROM nx.SA_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ=? AND INSERT_WINDOW='prodstockadj'", ymd, int(seq))
    except Exception: pass

@router.post("/api/prodstockadj/save")
def prodstockadj_save(payload: dict = Body(...)):
    """추가/수정 — nx.prod_stock_adjust. id 있으면 수정, 없으면 추가(채번). 금액=trunc(수량×단가)."""
    ymd = str(payload.get("maint_ymd") or "").strip().replace("-", "")[:8]
    if len(ymd) == 8:  # YYYYMMDD → YYMMDD
        ymd = ymd[2:]
    ymd = ymd[:6]
    item = str(payload.get("item_code") or "").strip()
    if len(ymd) != 6 or not item:
        raise HTTPException(400, "수정일자·도번은 필수입니다.")
    tag = str(payload.get("maint_tag") or "2").strip() or "2"
    cust = str(payload.get("cust_code") or "").strip() or None
    try:
        qty = float(payload.get("maint_qty") or 0)
    except Exception:
        raise HTTPException(400, "수정수량은 숫자여야 합니다.")
    try:
        cost = float(payload.get("maint_cost") or 0)
    except Exception:
        cost = 0.0
    amt = int(qty * cost)   # 절사(정수 금액)
    vat = 0
    wo = str(payload.get("work_order") or "").strip() or None
    swo = str(payload.get("split_work_order") or "").strip() or None
    rmk = str(payload.get("remarks") or "").strip() or None
    user = str(payload.get("user") or "web").strip() or "web"
    rid = payload.get("id")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        if rid:  # 수정
            # ★기존 미러행 제거용 옛 (ymd,seq) 읽기
            cur.execute("SELECT maint_ymd, maint_seq FROM nx.prod_stock_adjust WHERE id=?", int(rid))
            _o = cur.fetchone()
            cur.execute("""UPDATE nx.prod_stock_adjust SET maint_ymd=?, maint_tag=?, cust_code=?, item_code=?,
                  maint_qty=?, maint_cost=?, maint_amt=?, maint_vat=?, work_order=?, split_work_order=?, remarks=?,
                  upd_user=?, update_datetime=GETDATE() WHERE id=?""",
                ymd, tag, cust, item, qty, cost, amt, vat, wo, swo, rmk, user, int(rid))
            if cur.rowcount == 0:
                cn.rollback(); raise HTTPException(404, "수정 대상이 없습니다.")
            if _o:  # 옛 미러 제거 후 새 미러(같은 seq, 새 ymd/값)
                _pa_mirror_del(cur, str(_o[0]).strip(), _o[1]); seq = int(_o[1])
                _pa_mirror_ins(cur, ymd, seq, tag, cust, item, qty, cost, amt, vat, wo, swo, rmk)
        else:    # 추가
            seq = _next_seq(cur, ymd)
            cur.execute("""INSERT INTO nx.prod_stock_adjust
                  (maint_ymd, maint_seq, maint_tag, cust_code, item_code, maint_qty, maint_cost, maint_amt, maint_vat,
                   work_order, split_work_order, remarks, insert_user_id, insert_datetime)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,GETDATE())""",
                ymd, seq, tag, cust, item, qty, cost, amt, vat, wo, swo, rmk, user)
            # ★F-영업: 조회원천(SA_T_STOCK_MAINT)에도 반영 → 제품재고조회에 보이게
            _pa_mirror_ins(cur, ymd, seq, tag, cust, item, qty, cost, amt, vat, wo, swo, rmk)
        cn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"저장 실패: {e}")
    finally:
        cn.close()


@router.post("/api/prodstockadj/delete")
def prodstockadj_delete(payload: dict = Body(...)):
    """삭제 — nx.prod_stock_adjust(웹조정분만). 미러 이력은 삭제 불가(id 없음)."""
    ids = payload.get("ids") or ([payload.get("id")] if payload.get("id") is not None else [])
    ids = [int(x) for x in ids if x is not None]
    if not ids:
        raise HTTPException(400, "삭제할 행을 선택해 주세요.")
    cn = _nx_tx(); cur = cn.cursor()
    try:
        # ★삭제 전 (ymd,seq) 읽어 조회원천 미러행도 제거
        q = ",".join("?" * len(ids))
        cur.execute(f"SELECT maint_ymd, maint_seq FROM nx.prod_stock_adjust WHERE id IN ({q})", *ids)
        _rows = [(str(r[0]).strip(), r[1]) for r in cur.fetchall()]
        cur.execute(f"DELETE FROM nx.prod_stock_adjust WHERE id IN ({q})", *ids)
        for _y, _s in _rows: _pa_mirror_del(cur, _y, _s)
        n = cur.rowcount; cn.commit()
        return {"ok": True, "deleted": n}
    except Exception as e:
        cn.rollback(); raise HTTPException(500, f"삭제 실패: {e}")
    finally:
        cn.close()
