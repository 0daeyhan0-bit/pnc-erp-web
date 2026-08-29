# -*- coding: utf-8 -*-
"""협력사 사급부품 수불장 — nx.sagub_maint(협력사 사급재고 단일 원장) 파생.
   협력사 관점: 협력사입고(우리 창고 출고=사급출고, maint_qty>0) − 협력사출고(세트입고로 재입고=세트소진, maint_qty<0) = 잔량.
   ★단일 원장 = nx.sagub_maint (saleout 사급출고 tag5 실시간 + 세트소진 + 7월이관 hist7). 매출=nx.saleout_maint 병행.
   ★기초이관 snapshot(remarks_src='migration')은 제외 = 7월~ movement만(기초0). 용접봉/은납은 별도 트랙 제외.
   ★조회 전용(RO). 이력 이관=_migration/sagub_maint_hist_ingest.py.
"""
from fastapi import APIRouter, Query, Request
from routers.auth import require_user, scope_cust
from common import _nx

router = APIRouter()

# 사급부품(v_pr_bom SAGUB_FLAG=1)이고 용접 소재가 아닌 movement 만 = 이 수불장 대상
_PART = ("ISNULL(l.remarks_src,'')<>'migration'"
         " AND EXISTS(SELECT 1 FROM nx.v_pr_bom v WHERE UPPER(LTRIM(RTRIM(v.MAT_CODE)))=UPPER(LTRIM(RTRIM(l.mat_code))) AND v.SAGUB_FLAG='1')"
         " AND NOT EXISTS(SELECT 1 FROM nx.item wi WHERE wi.item_code=l.mat_code"
         "   AND (wi.item_code LIKE 'RAC%' OR wi.item_code LIKE 'BCUP%' OR wi.item_name LIKE '%용접%'))")


@router.get("/api/sagubledger/list")
def sagubledger_list(request: Request, cust: str = Query(""), mat: str = Query(""), fr: str = Query(""),
                     to: str = Query(""), sign: str = Query(""), scope: str = Query("sent"),
                     limit: int = Query(3000)):
    """좌: (협력사×사급부품) 협력사입고/협력사출고/잔량. 필터: 협력사·자도번·기간·잔량부호.
       scope='sent'(기본)=협력사입고 있는 부품만 · 'all'=출고만 있는 것까지 전체.
       ★소속 강제 — 협력사 계정은 자기 거래처만."""
    cust = scope_cust(require_user(request), cust)
    w = [_PART]; p = []
    if cust: w.append("l.cust_code=?"); p.append(cust)
    if mat:  w.append("(l.mat_code LIKE ? OR i.item_name LIKE ?)"); p += [f"%{mat}%", f"%{mat}%"]
    if fr:   w.append("l.maint_ymd>=?"); p.append(fr)
    if to:   w.append("l.maint_ymd<=?"); p.append(to)
    hv = []
    if scope != "all":  hv.append("SUM(CASE WHEN l.maint_qty>0 THEN 1 ELSE 0 END)>0")  # 협력사입고 있는 것만
    if sign == "1":   hv.append("SUM(l.maint_qty)>0.5")
    elif sign == "-1": hv.append("SUM(l.maint_qty)<-0.5")
    elif sign == "0":  hv.append("ABS(SUM(l.maint_qty))<=0.5")
    hav = ("HAVING " + " AND ".join(hv)) if hv else ""
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT TOP {int(limit)} l.cust_code, ISNULL(c.CUST_DESC,'') custnm, l.mat_code,
              ISNULL(i.item_name,'') matnm,
              SUM(CASE WHEN l.maint_qty>0 THEN l.maint_qty ELSE 0 END) sent,
              SUM(CASE WHEN l.maint_qty<0 THEN -l.maint_qty ELSE 0 END) used,
              SUM(l.maint_qty) bal
            FROM nx.sagub_maint l
            LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=l.cust_code
            LEFT JOIN nx.item i ON i.item_code=l.mat_code
            WHERE {' AND '.join(w)}
            GROUP BY l.cust_code, c.CUST_DESC, l.mat_code, i.item_name
            {hav} ORDER BY custnm, l.mat_code""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            for k in ("sent", "used", "bal"): r[k] = round(float(r[k] or 0), 2)
        # 협력사 목록 = 원장에 거래(movement) 있는 협력사만
        cur.execute(f"""SELECT DISTINCT LTRIM(RTRIM(l.cust_code)), LTRIM(RTRIM(ISNULL(c.CUST_DESC,''))) nm
            FROM nx.sagub_maint l LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=l.cust_code
            WHERE {_PART} ORDER BY nm""")
        custs = [{"code": r[0], "nm": r[1]} for r in cur.fetchall()]
        tot = {"sent": round(sum(r["sent"] for r in rows), 2), "used": round(sum(r["used"] for r in rows), 2),
               "bal": round(sum(r["bal"] for r in rows), 2)}
        return {"rows": rows, "custs": custs, "tot": tot}
    finally:
        cn.close()


@router.get("/api/sagubledger/detail")
def sagubledger_detail(request: Request, cust: str = Query(...), mat: str = Query(...), fr: str = Query(""), to: str = Query("")):
    """우: 선택 (협력사×사급부품) 일자별 수불 + running balance.
       협력사입고(+)=사급출고 tag5 · 협력사출고(−)=세트소진 tag S · 조정 tag B. ★소속 강제."""
    cust = scope_cust(require_user(request), cust)
    tagnm = {"5": "협력사입고", "9": "협력사입고", "S": "협력사출고", "C": "협력사입고", "B": "조정", "2": "조정", "3": "기초"}
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT l.maint_ymd, l.maint_tag,
              SUM(CASE WHEN l.maint_qty>0 THEN l.maint_qty ELSE 0 END) inq,
              SUM(CASE WHEN l.maint_qty<0 THEN -l.maint_qty ELSE 0 END) outq,
              SUM(l.maint_qty) netq
            FROM nx.sagub_maint l
            WHERE ISNULL(l.remarks_src,'')<>'migration' AND l.cust_code=? AND l.mat_code=?
            GROUP BY l.maint_ymd, l.maint_tag ORDER BY l.maint_ymd, l.maint_tag""", cust, mat)
        bal = 0.0; out = []
        for r in cur.fetchall():
            prev = bal; net = float(r[4] or 0); bal = prev + net
            row = {"maint_ymd": r[0], "tag": r[1], "tagnm": tagnm.get(str(r[1]).strip(), str(r[1]).strip()),
                   "in_qty": round(float(r[2] or 0), 2), "out_qty": round(float(r[3] or 0), 2),
                   "prev_qty": round(prev, 2), "stock_qty": round(bal, 2)}
            if fr and r[0] < fr: continue
            if to and r[0] > to: continue
            out.append(row)
        return {"rows": out, "final_qty": round(bal, 2)}
    finally:
        cn.close()
