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

# ★성능: 사급부품 universe(v_pr_bom SAGUB_FLAG=1)와 용접 제외집합을 in-process 캐시(행마다 상관 EXISTS 제거).
#   BOM 구조 변경은 드묾 + 재기동시 재로드. (Phase3 동적정확성: 필요시 /reset 결선.)
_PART_SET = None; _WELD_SET = None
def _sets():
    global _PART_SET, _WELD_SET
    if _PART_SET is None:
        cn = _nx(); cur = cn.cursor()
        try:
            cur.execute("SELECT DISTINCT UPPER(LTRIM(RTRIM(MAT_CODE))) FROM nx.v_pr_bom WHERE SAGUB_FLAG='1' AND ISNULL(MAT_CODE,'')<>''")
            _PART_SET = set(r[0].strip() for r in cur.fetchall())
            cur.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item WHERE item_code LIKE 'RAC%' OR item_code LIKE 'BCUP%' OR item_name LIKE '%용접%'")
            _WELD_SET = set(r[0].strip() for r in cur.fetchall())
        finally:
            cn.close()
    return _PART_SET, _WELD_SET
def _is_part(mat):
    p, w = _sets(); m = str(mat or "").strip().upper()
    return m in p and m not in w

# ★기동 시 백그라운드 프리워밍(첫 요청 지연 제거). 실패해도 lazy 폴백.
def _warm_bg():
    try: _sets()
    except Exception: pass
import threading as _th
_th.Thread(target=_warm_bg, daemon=True).start()


@router.get("/api/sagubledger/list")
def sagubledger_list(request: Request, cust: str = Query(""), mat: str = Query(""), fr: str = Query(""),
                     to: str = Query(""), sign: str = Query(""), scope: str = Query("sent"),
                     limit: int = Query(3000)):
    """좌: (협력사×사급부품) 협력사입고/협력사출고/잔량. 필터: 협력사·자도번·기간·잔량부호.
       scope='sent'(기본)=협력사입고 있는 부품만 · 'all'=출고만 있는 것까지 전체.
       ★소속 강제 — 협력사 계정은 자기 거래처만."""
    cust = scope_cust(require_user(request), cust)
    # ★성능: 상관 EXISTS 제거 — GROUP BY(작은 sagub_maint)만 SQL, 부품/scope/sign/cust 는 Python 필터.
    w = ["ISNULL(l.remarks_src,'')<>'migration'"]; p = []
    if mat: w.append("(l.mat_code LIKE ? OR i.item_name LIKE ?)"); p += [f"%{mat}%", f"%{mat}%"]
    if fr:  w.append("l.maint_ymd>=?"); p.append(fr)
    if to:  w.append("l.maint_ymd<=?"); p.append(to)
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT l.cust_code, ISNULL(c.CUST_DESC,'') custnm, l.mat_code, ISNULL(i.item_name,'') matnm,
              SUM(CASE WHEN l.maint_qty>0 THEN l.maint_qty ELSE 0 END) sent,
              SUM(CASE WHEN l.maint_qty<0 THEN -l.maint_qty ELSE 0 END) used, SUM(l.maint_qty) bal
            FROM nx.sagub_maint l
            LEFT JOIN nx.CM_M_CUST c ON c.CUST_CODE=l.cust_code
            LEFT JOIN nx.item i ON i.item_code=l.mat_code
            WHERE {' AND '.join(w)}
            GROUP BY l.cust_code, c.CUST_DESC, l.mat_code, i.item_name""", *p)
        cols = [d[0] for d in cur.description]
        allrows = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            if not _is_part(d["mat_code"]):
                continue
            for k in ("sent", "used", "bal"): d[k] = round(float(d[k] or 0), 2)
            d["cust_code"] = str(d["cust_code"]).strip()
            allrows.append(d)
        custs = sorted({(r["cust_code"], (r["custnm"] or r["cust_code"]).strip()) for r in allrows}, key=lambda x: x[1])
        rows = []
        for r in allrows:
            if cust and r["cust_code"] != cust: continue
            if scope != "all" and not r["sent"] > 0: continue
            if sign == "1" and not r["bal"] > 0.5: continue
            if sign == "-1" and not r["bal"] < -0.5: continue
            if sign == "0" and abs(r["bal"]) > 0.5: continue
            rows.append(r)
        rows.sort(key=lambda r: ((r["custnm"] or "").strip(), r["mat_code"]))
        rows = rows[:int(limit)]
        tot = {"sent": round(sum(r["sent"] for r in rows), 2), "used": round(sum(r["used"] for r in rows), 2),
               "bal": round(sum(r["bal"] for r in rows), 2)}
        return {"rows": rows, "custs": [{"code": c, "nm": n} for c, n in custs], "tot": tot}
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
