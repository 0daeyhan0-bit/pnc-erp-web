# -*- coding: utf-8 -*-
"""품목단가 관리(w_tc_master_090) — 매출처별 판매/매입 단가 마스터 CRUD.

★2026-08-29 데이터 소스 이관: 미러 `nx.PR_M_ITEM_COST` → **정본 `nx.price_item`** (DO_NOT_USE §18).
  컷오버 후 미러는 죽는다. 이 화면이 그때 갈 곳이 없어서 `nx.price_item` 을 마스터로 승격했다
  (키 1:1 · main_flag 등 11컬럼 추가·라이브 백필 99.23% — `_schema/CUTOVER_CHECKLIST.md` "(A)안 검증").
  ★`_migration/sub_norm/r_price_vendor_match.py` 는 이 테이블의 '매입'을 통째로 지운다 —
    실행 거부 가드를 걸어 뒀다. 절대 풀지 말 것(웹 업로드 사급가 855행이 날아간다).

★단가 편집은 권한자만(프론트 게이트) + 관리화면 예외(거래/조회 화면은 여전히 읽기전용, feedback-material-price-close-only).
  키=(item_code, vendor_code, price_type, apply_ymd). price_type 매입 / TAGE=수출판매 / TAGS=내수판매.
  ※화면·API 의 tag 코드(1/E/S)는 그대로 두고 **DB 값만 매핑**한다(프론트 무변경).
"""
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _custnm_map, _d6

router = APIRouter()
_TAGNM = {"1": "매입", "E": "수출판매", "S": "내수판매"}

# 화면 tag(1/E/S) ↔ 정본 price_type(매입/TAGE/TAGS). §9 의 매핑 그대로.
_T2P = {"1": "매입", "E": "TAGE", "S": "TAGS"}
_P2T = {v: k for k, v in _T2P.items()}
_PTCASE = "CASE price_type WHEN 'TAGS' THEN 'S' WHEN 'TAGE' THEN 'E' ELSE '1' END"

@router.get("/api/pricemgmt/items")
def pm_items(q: str = Query(""), lg: str = Query(""), sg: str = Query(""), limit: int = Query(1000)):
    """좌측 품목 리스트(품번·품명·소분류·단가건수). 단가있는 품목 우선 정렬."""
    cn = _nx(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if q.strip():  w.append("(i.ITEM_CODE LIKE ? OR i.item_name LIKE ?)"); p += [f"%{q.strip()}%", f"%{q.strip()}%"]
        if lg.strip(): w.append("i.lgroup=?"); p.append(lg.strip())
        if sg.strip(): w.append("i.sgroup=?"); p.append(sg.strip())
        n = max(1, min(int(limit), 3000))
        cur.execute(f"""SELECT TOP {n} i.ITEM_CODE, ISNULL(i.item_name,''), ISNULL(i.sgroup,''), ISNULL(pc.cnt,0)
            FROM nx.item i
            LEFT JOIN (SELECT item_code, COUNT(*) cnt FROM nx.price_item GROUP BY item_code) pc ON pc.item_code=i.ITEM_CODE
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
        cur.execute(f"""SELECT {_PTCASE},vendor_code,ISNULL(main_flag,'0'),apply_ymd,ISNULL(currency,''),
              price,mat_cost,proc_cost,other_cost,ISNULL(mat_unit,''),ISNULL(mkt,''),ISNULL(remarks,''),
              ISNULL(upd_user,ISNULL(ins_user,'')),CONVERT(varchar(19),ISNULL(upd_dt,ins_dt),120)
            FROM nx.price_item WHERE item_code=? ORDER BY {_PTCASE}, apply_ymd DESC""", item)
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
        if old:   # 키가 실제 바뀐 경우에만 원래키 삭제(같은키 수정은 UPDATE로 감·INSERT_DATETIME 보존)
            okey = (str(old.get("cust", "")).strip(), str(old.get("tag", "")).strip(), _d6(str(old.get("ymd", "")).strip()))
            if okey != (cust, tag, ymd):
                c.execute("DELETE FROM nx.price_item WHERE item_code=? AND vendor_code=? AND price_type=? AND apply_ymd=?",
                    item, okey[0], _T2P.get(okey[1], okey[1]), okey[2])
        pt = _T2P.get(tag, tag)
        ex = c.execute("SELECT COUNT(*) FROM nx.price_item WHERE item_code=? AND vendor_code=? AND price_type=? AND apply_ymd=?",
            item, cust, pt, ymd).fetchone()[0]
        if ex:
            c.execute("""UPDATE nx.price_item SET main_flag=?,currency=?,price=?,mat_cost=?,proc_cost=?,other_cost=?,
                  mat_unit=?,mkt=?,remarks=?,upd_user=?,upd_dt=getdate()
                WHERE item_code=? AND vendor_code=? AND price_type=? AND apply_ymd=?""",
                main, cur_ccy, cost, mat, proc, other, matunit, mkt, remarks, by, item, cust, pt, ymd)
            mode = "update"
        else:
            c.execute("""INSERT INTO nx.price_item(item_code,vendor_code,price_type,apply_ymd,main_flag,currency,
                  price,mat_cost,proc_cost,other_cost,mat_unit,mkt,remarks,ins_user,ins_dt)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate())""",
                item, cust, pt, ymd, main, cur_ccy, cost, mat, proc, other, matunit, mkt, remarks, by)
            mode = "insert"
        cn.commit(); return {"ok": True, "mode": mode}
    finally:
        cn.close()

@router.post("/api/pricemgmt/delete")
def pm_delete(p: dict = Body(...)):
    item, tag, cust, ymd = _valid(p)
    cn = _nx(); c = cn.cursor()
    try:
        c.execute("DELETE FROM nx.price_item WHERE item_code=? AND vendor_code=? AND price_type=? AND apply_ymd=?",
            item, cust, _T2P.get(tag, tag), ymd)
        n = c.rowcount; cn.commit()
        if not n: raise HTTPException(404, "삭제 대상 없음")
        return {"ok": True, "deleted": n}
    finally:
        cn.close()
