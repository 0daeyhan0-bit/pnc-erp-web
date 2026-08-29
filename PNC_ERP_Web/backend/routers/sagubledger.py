# -*- coding: utf-8 -*-
"""협력사 사급부품 수불장 (신규) — nx.sagub_parts_ledger(클린 단일원장) 조회.
   모델(SAGUB_PARTS_LEDGER_DESIGN.md): (협력사 × 우리가 보낸 사급부품)
     보낸(+, tag OUT) = 사급출고(PU_T_STOCK_MAINT tag5) · 소진(−, tag SET) = 세트입고 × 소요엔진(§10)
     잔량 = 보낸 − 소진. 기초0 @2026-01(용접 소재 별도 트랙 제외).
   ★조회 전용(RO). 원장 적재는 _migration/sagub_parts_ledger_ingest.py(멱등).
"""
from fastapi import APIRouter, Query, Request
from routers.auth import require_user, scope_cust
from common import _nx

router = APIRouter()


@router.get("/api/sagubledger/list")
def sagubledger_list(request: Request, cust: str = Query(""), mat: str = Query(""), fr: str = Query(""),
                     to: str = Query(""), sign: str = Query(""), scope: str = Query("sent"),
                     limit: int = Query(3000)):
    """좌: (협력사×사급부품) 보낸/소진/잔량. 필터: 협력사·자도번(코드/이름)·기간·잔량부호.
       scope='sent'(기본)=우리가 보낸 부품만(사급출고 有) · 'all'=소진만 있는 것(LG직접공급 등)까지 전체.
       ★소속 강제 — 협력사 계정은 cust 파라미터와 무관하게 자기 거래처만 본다."""
    cust = scope_cust(require_user(request), cust)   # 협력사=자기코드 강제 / 담당자=필터 그대로
    w = ["1=1"]; p = []
    if cust: w.append("l.cust_code=?"); p.append(cust)
    if mat:  w.append("(l.mat_code LIKE ? OR i.item_name LIKE ?)"); p += [f"%{mat}%", f"%{mat}%"]
    if fr:   w.append("l.maint_ymd>=?"); p.append(fr)
    if to:   w.append("l.maint_ymd<=?"); p.append(to)
    hv = []
    if scope != "all":  hv.append("SUM(CASE WHEN l.tag='OUT' THEN 1 ELSE 0 END)>0")  # 우리가 보낸 부품만
    if sign == "1":   hv.append("SUM(l.qty)>0.5")
    elif sign == "-1": hv.append("SUM(l.qty)<-0.5")
    elif sign == "0":  hv.append("ABS(SUM(l.qty))<=0.5")
    hav = ("HAVING " + " AND ".join(hv)) if hv else ""
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT TOP {int(limit)} l.cust_code, ISNULL(c.CUST_DESC,'') custnm, l.mat_code,
              ISNULL(i.item_name,'') matnm,
              SUM(CASE WHEN l.tag='OUT' THEN l.qty ELSE 0 END) sent,
              SUM(CASE WHEN l.tag='SET' THEN -l.qty ELSE 0 END) used,
              SUM(l.qty) bal
            FROM nx.sagub_parts_ledger l
            LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=l.cust_code
            LEFT JOIN nx.item i ON i.item_code=l.mat_code
            WHERE {' AND '.join(w)}
            GROUP BY l.cust_code, c.CUST_DESC, l.mat_code, i.item_name
            {hav} ORDER BY custnm, l.mat_code""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("sent", "used", "bal"): r[k] = round(float(r[k] or 0), 2)
        # 협력사 드롭다운
        cur.execute("""SELECT DISTINCT l.cust_code, ISNULL(c.CUST_DESC,'') nm FROM nx.sagub_parts_ledger l
            LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=l.cust_code ORDER BY 2""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        tot = {"sent": round(sum(r["sent"] for r in rows), 2), "used": round(sum(r["used"] for r in rows), 2),
               "bal": round(sum(r["bal"] for r in rows), 2)}
        return {"rows": rows, "custs": custs, "tot": tot}
    finally:
        cn.close()


@router.get("/api/sagubledger/detail")
def sagubledger_detail(request: Request, cust: str = Query(...), mat: str = Query(...), fr: str = Query(""), to: str = Query("")):
    """우: 선택 (협력사×사급부품) 일자별 수불 + running balance. 보낸(+)·소진(−) 구분.
       ★소속 강제 — 협력사는 남의 cust 를 넣어도 자기 것만 열린다."""
    cust = scope_cust(require_user(request), cust)
    # 협력사 관점: 우리 창고 출고(사급출고)=협력사입고 / 우리 창고 재입고(세트입고)=협력사출고
    tagnm = {"OUT": "협력사입고", "SET": "협력사출고", "ADJ": "조정"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT l.maint_ymd, l.tag,
              SUM(CASE WHEN l.qty>0 THEN l.qty ELSE 0 END) inq,
              SUM(CASE WHEN l.qty<0 THEN -l.qty ELSE 0 END) outq,
              SUM(l.qty) netq
            FROM nx.sagub_parts_ledger l
            WHERE l.cust_code=? AND l.mat_code=?
            GROUP BY l.maint_ymd, l.tag ORDER BY l.maint_ymd, l.tag""", cust, mat)
        bal = 0.0; out = []
        for r in cur.fetchall():
            prev = bal; net = float(r[4] or 0); bal = prev + net
            row = {"maint_ymd": r[0], "tag": r[1], "tagnm": tagnm.get(r[1], r[1]),
                   "in_qty": round(float(r[2] or 0), 2), "out_qty": round(float(r[3] or 0), 2),
                   "prev_qty": round(prev, 2), "stock_qty": round(bal, 2)}
            if fr and r[0] < fr: continue
            if to and r[0] > to: continue
            out.append(row)
        return {"rows": out, "final_qty": round(bal, 2)}
    finally:
        cn.close()
