# -*- coding: utf-8 -*-
"""도입-수입입력(w_pu_stock_c_040, MAINT_TAG='P') · 도입-수출입력(w_pu_stock_c_050, MAINT_TAG='Q').
   데이터원 = PU_T_STOCK_MAINT_C (해외 수입/수출, 외환·관세·운임·BL·HS·신고번호).
   조회 우선(라이브 PARTNER_ERP RO 직독, 레거시 화면과 대조). 컷오버 시 nx 소스 전환.
   금액(KRW) = ROUND(MAINT_AMT × EXCHANGE_RATE, 0) (레거시 화면 검증)."""
from fastapi import APIRouter, Query
from common import _conn, _custnm_map, _d6

router = APIRouter()

def _dopip_rows(tag, from_ymd, to_ymd, cust, mat, insp, bl, wide):
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["MAINT_TAG=?", "MAINT_YMD BETWEEN ? AND ?"]
        p = [tag, _d6(from_ymd), _d6(to_ymd)]
        if cust.strip(): w.append("CUST_CODE=?"); p.append(cust.strip())
        if mat.strip():  w.append("MAT_CODE LIKE ?"); p.append(f"%{mat.strip()}%")
        if insp.strip(): w.append("INSP_SEQ LIKE ?"); p.append(f"%{insp.strip()}%")
        if bl.strip():   w.append("BL_SEQ LIKE ?"); p.append(f"%{bl.strip()}%")
        cur.execute(f"""SELECT MAINT_YMD, CUST_CODE, MAT_CODE, MAINT_QTY, CURRENCY, MAINT_COST, MAINT_AMT,
              ROUND(MAINT_AMT*EXCHANGE_RATE,0,1) AS KRW, EXCHANGE_RATE, ISNULL(REMARKS,''),
              CUSTOMS_DUTIES, TRANSPORTATION_FATE, TAX_TABLE, ISNULL(INSP_SEQ,''), ISNULL(BL_SEQ,''), ISNULL(HS_CODE,''),
              MAINT_SEQ
          FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_C
          WHERE {' AND '.join(w)}
          ORDER BY MAINT_YMD, CUST_CODE, INSP_SEQ, MAINT_SEQ""", *p)
        rows = []
        cch = set()
        for r in cur.fetchall():
            d = {"ymd": str(r[0]).strip(), "cust": str(r[1] or '').strip(), "mat": str(r[2] or '').strip(),
                 "qty": float(r[3] or 0), "cur": str(r[4] or '').strip(), "cost": float(r[5] or 0),
                 "amt": float(r[6] or 0), "krw": float(r[7] or 0), "rate": float(r[8] or 0), "remarks": r[9]}
            if wide:
                d.update({"duty": float(r[10] or 0), "fare": float(r[11] or 0), "tax": float(r[12] or 0),
                          "insp": str(r[13] or '').strip(), "bl": str(r[14] or '').strip(), "hs": str(r[15] or '').strip()})
            cch.add(d["cust"]); rows.append(d)
        nm = _custnm_map(cur, cch)
        for d in rows: d["cust_nm"] = nm.get(d["cust"], d["cust"])
        tot = {"cnt": len(rows), "qty": sum(d["qty"] for d in rows),
               "amt": sum(d["amt"] for d in rows), "krw": sum(d["krw"] for d in rows)}
        return {"rows": rows, "tot": tot}
    finally:
        cn.close()

@router.get("/api/dopip/purchase")
def dopip_purchase(from_ymd: str = Query(""), to_ymd: str = Query(""), cust: str = Query(""),
                   mat: str = Query(""), insp: str = Query(""), bl: str = Query("")):
    """도입-수입입력(040, tag=P). 전 컬럼(관세·운임·부가세과표·신고번호·BL·HS)."""
    return _dopip_rows("P", from_ymd, to_ymd, cust, mat, insp, bl, wide=True)

@router.get("/api/dopip/sale")
def dopip_sale(from_ymd: str = Query(""), to_ymd: str = Query(""), cust: str = Query(""), mat: str = Query("")):
    """도입-수출입력(050, tag=Q). 축소 컬럼(출고일자·거래처·품목·수량·통화·단가·금액·KRW·환율·비고)."""
    return _dopip_rows("Q", from_ymd, to_ymd, cust, mat, "", "", wide=False)
