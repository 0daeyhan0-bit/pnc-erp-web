# -*- coding: utf-8 -*-
"""영업계획현황(w_pr_plan_050) — SA_T_PLAN_DTL 기반 일별 크로스탭. 레거시 dw_pr_plan_050_t1 SQL 그대로 실행.
   구분: 1=상세(원행) · 2=집계(연속 line·output_hm·work_order 병합+일별 overwrite+도번 concat) · 3=도번집계.
   ★집계 알고리즘은 레거시 srw 379~412 PowerScript 후처리 충실이식(검증: 2607/260814 7일 = 2,028행·일별합계 완전일치).
   조회 우선(라이브 PARTNER_ERP RO). 필터 오토컴플리트는 프론트."""
import os, datetime
from fastapi import APIRouter, Query, HTTPException
from common import _conn

router = APIRouter()
with open(os.path.join(os.path.dirname(__file__), 'sql_plan050.txt'), encoding='utf-8') as _f:
    _BASE_SQL = _f.read()

def _d6(s): return ''.join(ch for ch in str(s or '') if ch.isdigit())[:6]
def _like(s):
    s = str(s or '').strip()
    if not s or s in ('%', '전체', 'XX 전체'): return '%'
    return s.replace("'", "''").replace(";", "")   # 인젝션 방지(내부 RO지만 방어)
def _rel(ymd, n):
    d = datetime.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])) + datetime.timedelta(days=n)
    return d.strftime('%y%m%d')
def _label(ymd):
    d = datetime.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    return ymd[4:6] + '월화수목금토일'[d.weekday()]

@router.get("/api/salesplan")
def salesplan(from_ymd: str = Query(...), days: int = Query(7), gubun: str = Query("2"),
              cust: str = Query(""), line: str = Query(""), model: str = Query(""),
              wo: str = Query(""), item: str = Query("")):
    fr = _d6(from_ymd)
    if len(fr) != 6: raise HTTPException(400, "기준일자(YYMMDD) 필요")
    days = max(1, min(int(days or 7), 31))
    to = _rel(fr, days - 1)
    sub = {':as_from_ymd': "'%s'" % fr, ':as_to_ymd': "'%s'" % to,
           ':as_cust_code': "'%s'" % _like(cust), ':as_line_no': "'%s'" % _like(line),
           ':as_model_no': "'%s'" % _like(model), ':as_work_order': "'%s'" % _like(wo),
           ':as_item_code': "'%s'" % _like(item)}
    sql = _BASE_SQL
    for k, v in sub.items(): sql = sql.replace(k, v)
    dcols = ",".join("plan_qty_%02d" % i for i in range(1, days + 1))
    selcols = ("line_no,plan_ymd,output_hm,work_order,ISNULL(model_no,''),ISNULL(tools_desc,''),"
               "c_item_code,ISNULL(work_center,''),ISNULL(work_center_code,''),ISNULL(lot_qty,0),"
               "ISNULL(prod_rate,0),ISNULL(remarks2,''),") + dcols
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SELECT " + selcols + " FROM (" + sql + ") q ORDER BY line_no,plan_ymd,output_hm,work_order,c_item_code")
        raw = cur.fetchall()
    finally:
        cn.close()
    def mk(r):
        return {"line": str(r[0] or '').strip(), "ymd": str(r[1] or '').strip(), "ohm": str(r[2] or '').strip(),
                "wo": str(r[3] or '').strip(), "model": str(r[4] or '').strip(), "tool": str(r[5] or '').strip(),
                "item": str(r[6] or '').strip(), "wc": str(r[7] or '').strip(), "lot": float(r[9] or 0),
                "rate": float(r[10] or 0), "remarks": str(r[11] or '').strip(),
                "d": [float(x or 0) for x in r[12:12 + days]]}
    rows = [mk(r) for r in raw]
    # 라인명(CM_M_MASTER_DETAIL PR003 생산라인)
    lnm = {}
    try:
        cn2 = _conn(); c2 = cn2.cursor()
        try:
            c2.execute("SELECT DETAIL_CODE, ISNULL(DETAIL_DESC,'') FROM PARTNER_ERP.dbo.CM_M_MASTER_DETAIL WHERE KIND_CODE='PR003'")
            for a, b in c2.fetchall(): lnm[str(a).strip()] = str(b).strip()
        finally: cn2.close()
    except Exception: pass
    for x in rows: x["line_nm"] = lnm.get(x["line"], "")

    if gubun == "2":       # 집계 (레거시 379~412)
        out = []
        for x in rows:
            p = out[-1] if out else None
            if p and p["line"] == x["line"] and p["ohm"] == x["ohm"] and p["wo"] == x["wo"]:
                for i in range(days):
                    if x["d"][i] > 0: p["d"][i] = x["d"][i]     # overwrite(비-0)
                if x["item"] and x["item"] not in p["item"]:
                    p["item"] = (p["item"] + " " + x["item"]).strip(); p["wc"] = ""; p["rate"] = 0
            else:
                out.append(x)
        rows = out
    elif gubun == "3":     # 도번집계 (도번별 합산)
        agg = {}
        for x in rows:
            k = x["item"]
            a = agg.get(k)
            if not a:
                a = agg[k] = {"line": x["line"], "ohm": "", "wo": "", "model": "", "tool": "",
                              "item": k, "wc": x["wc"], "lot": 0.0, "rate": 0.0, "remarks": "", "d": [0.0] * days}
            for i in range(days): a["d"][i] += x["d"][i]
            a["lot"] += x["lot"]
        rows = list(agg.values())

    for x in rows: x["total"] = sum(x["d"])
    tot = {"cnt": len(rows), "lot": sum(x["lot"] for x in rows), "total": sum(x["total"] for x in rows),
           "d": [sum(x["d"][i] for x in rows) for i in range(days)]}
    labels = [_label(_rel(fr, i)) for i in range(days)]
    return {"from": fr, "to": to, "days": days, "labels": labels, "gubun": gubun, "rows": rows, "tot": tot}
