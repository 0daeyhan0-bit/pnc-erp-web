# -*- coding: utf-8 -*-
"""품목단가 관리(w_tc_master_090) — 매출처별 판매/매입 단가 마스터 CRUD. 데이터 nx.PR_M_ITEM_COST.
   ★단가 편집은 권한자만(프론트 게이트) + 관리화면 예외(거래/조회 화면은 여전히 읽기전용, feedback-material-price-close-only).
   키=(ITEM_CODE,CUST_CODE,COST_TAG,COST_APPLY_YMD). COST_TAG 1=매입·E=수출판매·S=내수판매."""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _custnm_map, _d6

router = APIRouter()
_TAGNM = {"1": "매입", "E": "수출판매", "S": "내수판매"}

@router.get("/api/pricemgmt/items")
def pm_items(q: str = Query(""), lg: str = Query(""), sg: str = Query(""), limit: int = Query(1000)):
    """좌측 품목 리스트(품번·품명·소분류·단가건수). 단가있는 품목 우선 정렬."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if q.strip():  w.append("(i.ITEM_CODE LIKE ? OR i.ITEM_DESC LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        if lg.strip(): w.append("i.ITEM_LGROUP=?"); p.append(lg.strip())
        if sg.strip(): w.append("i.ITEM_SGROUP=?"); p.append(sg.strip())
        n = max(1, min(int(limit), 3000))
        cur.execute(f"""SELECT TOP {n} i.ITEM_CODE, ISNULL(i.ITEM_DESC,''), ISNULL(i.ITEM_SGROUP,''), ISNULL(pc.cnt,0)
            FROM nx.PR_M_ITEM i
            LEFT JOIN (SELECT ITEM_CODE, COUNT(*) cnt FROM nx.PR_M_ITEM_COST GROUP BY ITEM_CODE) pc ON pc.ITEM_CODE=i.ITEM_CODE
            WHERE {' AND '.join(w)} ORDER BY (CASE WHEN ISNULL(pc.cnt,0)>0 THEN 0 ELSE 1 END), i.ITEM_CODE""", *p)
        rows = [{"item": str(r[0]).strip(), "nm": str(r[1]).strip(), "sg": str(r[2]).strip(), "cnt": int(r[3] or 0)}
                for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()

@router.get("/api/pricemgmt/detail")
def pm_detail(item: str = Query(...)):
    """선택 품목의 단가행 전체(거래처별·구분별·적용일별)."""
    item = item.strip()
    cn = _nx(); cur = cn.cursor()
    try:
        cur.execute("""SELECT COST_TAG,CUST_CODE,ISNULL(MAIN_FLAG,'0'),COST_APPLY_YMD,ISNULL(CURRENCY,''),
              ITEM_COST,MAT_COST,PROC_COST,OTHER_COST,ISNULL(MAT_UNIT,''),ISNULL(MKT,''),ISNULL(REMARKS,''),
              ISNULL(UPDATE_USER_ID,ISNULL(INSERT_USER_ID,'')),CONVERT(varchar(19),ISNULL(UPDATE_DATETIME,INSERT_DATETIME),120)
            FROM nx.PR_M_ITEM_COST WHERE ITEM_CODE=? ORDER BY COST_TAG, COST_APPLY_YMD DESC""", item)
        rows = []; cch = set()
        for r in cur.fetchall():
            d = {"tag": str(r[0]).strip(), "tag_nm": _TAGNM.get(str(r[0]).strip(), str(r[0]).strip()),
                 "cust": str(r[1] or '').strip(), "main": str(r[2]).strip(), "ymd": str(r[3] or '').strip(),
                 "cur": str(r[4]).strip(), "cost": float(r[5] or 0), "mat": float(r[6] or 0), "proc": float(r[7] or 0),
                 "other": float(r[8] or 0), "matunit": str(r[9]).strip(), "mkt": str(r[10]).strip(), "remarks": r[11],
                 "usr": r[12], "dt": r[13]}
            cch.add(d["cust"]); rows.append(d)
        nm = _custnm_map(cur, cch)
        for d in rows: d["cust_nm"] = nm.get(d["cust"], d["cust"])
        return {"item": item, "rows": rows}
    finally:
        cn.close()

def _valid(p):
    item = str(p.get("item", "")).strip(); tag = str(p.get("tag", "")).strip()
    cust = str(p.get("cust", "")).strip(); ymd = _d6(str(p.get("ymd", "")).strip())
    if not item or not cust or tag not in ("1", "E", "S") or len(ymd) != 6:
        raise HTTPException(400, "품목·거래처·단가구분(1/E/S)·적용일(YYMMDD) 필수")
    return item, tag, cust, ymd

@router.post("/api/pricemgmt/save")
def pm_save(p: dict = Body(...)):
    """추가/수정. old(원래키) 주면 키변경 처리(삭제후 재삽입). 단가는 수동입력(계산 안 함)."""
    item, tag, cust, ymd = _valid(p)
    cost = float(p.get("cost") or 0); mat = float(p.get("mat") or 0)
    proc = float(p.get("proc") or 0); other = float(p.get("other") or 0)
    cur_ccy = str(p.get("cur", "KRW")).strip() or "KRW"; main = str(p.get("main", "0")).strip() or "0"
    matunit = str(p.get("matunit", "")).strip(); mkt = str(p.get("mkt", "")).strip()
    remarks = str(p.get("remarks", "")).strip(); by = str(p.get("by", "web")).strip() or "web"
    old = p.get("old") if isinstance(p.get("old"), dict) else None
    cn = _nx(); c = cn.cursor()
    try:
        if old:   # 키변경(수정): 원래키 삭제
            c.execute("DELETE FROM nx.PR_M_ITEM_COST WHERE ITEM_CODE=? AND CUST_CODE=? AND COST_TAG=? AND COST_APPLY_YMD=?",
                item, str(old.get("cust", "")).strip(), str(old.get("tag", "")).strip(), _d6(str(old.get("ymd", "")).strip()))
        ex = c.execute("SELECT COUNT(*) FROM nx.PR_M_ITEM_COST WHERE ITEM_CODE=? AND CUST_CODE=? AND COST_TAG=? AND COST_APPLY_YMD=?",
            item, cust, tag, ymd).fetchone()[0]
        if ex:
            c.execute("""UPDATE nx.PR_M_ITEM_COST SET MAIN_FLAG=?,CURRENCY=?,ITEM_COST=?,MAT_COST=?,PROC_COST=?,OTHER_COST=?,
                  MAT_UNIT=?,MKT=?,REMARKS=?,UPDATE_USER_ID=?,UPDATE_DATETIME=getdate()
                WHERE ITEM_CODE=? AND CUST_CODE=? AND COST_TAG=? AND COST_APPLY_YMD=?""",
                main, cur_ccy, cost, mat, proc, other, matunit, mkt, remarks, by, item, cust, tag, ymd)
            mode = "update"
        else:
            c.execute("""INSERT INTO nx.PR_M_ITEM_COST(ITEM_CODE,CUST_CODE,COST_TAG,COST_APPLY_YMD,MAIN_FLAG,CURRENCY,
                  ITEM_COST,MAT_COST,PROC_COST,OTHER_COST,MAT_UNIT,MKT,REMARKS,INSERT_USER_ID,INSERT_DATETIME)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate())""",
                item, cust, tag, ymd, main, cur_ccy, cost, mat, proc, other, matunit, mkt, remarks, by)
            mode = "insert"
        cn.commit(); return {"ok": True, "mode": mode}
    finally:
        cn.close()

@router.post("/api/pricemgmt/delete")
def pm_delete(p: dict = Body(...)):
    item, tag, cust, ymd = _valid(p)
    cn = _nx(); c = cn.cursor()
    try:
        c.execute("DELETE FROM nx.PR_M_ITEM_COST WHERE ITEM_CODE=? AND CUST_CODE=? AND COST_TAG=? AND COST_APPLY_YMD=?",
            item, cust, tag, ymd)
        n = c.rowcount; cn.commit()
        if not n: raise HTTPException(404, "삭제 대상 없음")
        return {"ok": True, "deleted": n}
    finally:
        cn.close()
