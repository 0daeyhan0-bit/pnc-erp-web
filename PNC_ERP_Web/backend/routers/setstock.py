# -*- coding: utf-8 -*-
"""setstock 도메인 라우터 — 가공세트재고관리 (w_pu_stock_280 + 조정팝업 w_pu_stock_285).

★레거시 원천(2026-08-23 소스/실측 확인)
  · 현재고   = PU_T_SET_GAGONG_STOCK        (키 = ITEM_CODE + IN_CUST_CODE, 컬럼 STOCK_QTY)
               ★레거시 dw_pu_stock_280 조회쿼리 실물 확인(2026-08-23). 이름이 비슷한
                 PU_T_SET_MAT_STOCK(자재세트재고)와 다른 테이블이니 혼동 주의.
  · 조정이력 = PU_T_SET_STOCK_MAINT_GAGONG (MAINT_YMD+MAINT_SEQ 키, MAINT_TAG/CUST_CODE/ITEM_CODE/MAINT_QTY)
  · 조회조건 = 세트거래처(mat_cust_code) · 도번(item_code) · 구분(gubun: 1=(-)재고 / 0=(+)재고 / %=전체)
  · 조정저장(285 ue_save_after):
      MAINT_TAG='3' 이고 reset_flag='1' 이면  등록수량 = 입력수량 − 현재고 (장부수정: 결과가 입력값이 되게)
      그 외는 등록수량 = 입력수량 그대로(가감)
      INSERT 후 실시간 세트재고 반영(f_pu_set_set_gagong_stock) = 현재고 테이블 UPSERT

★조회는 라이브(PARTNER_ERP) 읽기전용 + nx 조정분 합산, 쓰기는 nx 만(§1 절대규칙).
"""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import _conn, _nx, _d6

router = APIRouter()

LIVE = "PARTNER_ERP.dbo"
NX = "PARTNER_ERP_TEST3.nx"

# 조정구분 — 레거시 dw_pu_stock_285_c1 의 maint_tag 선택지
MAINT_TAGS = [
    {"code": "1", "nm": "1:입고"},
    {"code": "2", "nm": "2:출고"},
    {"code": "3", "nm": "3:장부수정"},
    {"code": "4", "nm": "4:기타"},
]


def _f(v):
    try: return float(v or 0)
    except Exception: return 0.0


@router.get("/api/gagongset/opts")
def setstock_opts():
    """세트거래처 드롭다운 — 세트재고가 잡혀 있는 거래처만."""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT DISTINCT s.IN_CUST_CODE, ISNULL(c.CUST_DESC,''), ISNULL(c.CHARGE_USER_ID,'')
              FROM {LIVE}.PU_T_SET_GAGONG_STOCK s
              LEFT JOIN {NX}.CM_M_CUST c ON c.CUST_CODE=s.IN_CUST_CODE
             WHERE ISNULL(s.IN_CUST_CODE,'')<>''
             ORDER BY ISNULL(c.CUST_DESC,''), s.IN_CUST_CODE""")
        custs = [{"code": r[0], "nm": r[1] or r[0], "charge": r[2]} for r in cur.fetchall()]
        return {"custs": custs, "tags": MAINT_TAGS}
    finally:
        cn.close()


@router.get("/api/gagongset/list")
def setstock_list(cust: str = Query(""), item: str = Query(""), gubun: str = Query("%"),
                  zero: str = Query("숨김"), limit: int = Query(3000)):
    """가공세트재고 현황. 라이브 현재고 + nx 조정분 합산.
       gubun: '1'=(-)재고만 / '0'=(+)재고만 / '%'=전체.  zero='숨김'이면 재고 0 제외."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["1=1"]; p = []
        if cust.strip(): w.append("s.IN_CUST_CODE=?"); p.append(cust.strip())
        if item.strip(): w.append("s.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 20000))}
              s.IN_CUST_CODE, ISNULL(c.CUST_DESC,''), ISNULL(c.CHARGE_USER_ID,''),
              s.ITEM_CODE, ISNULL(i.ITEM_DESC,''), s.STOCK_QTY,
              ISNULL(s.UPDATE_USER_ID,''), s.UPDATE_DATETIME
            FROM {LIVE}.PU_T_SET_GAGONG_STOCK s
            LEFT JOIN {NX}.CM_M_CUST c ON c.CUST_CODE=s.IN_CUST_CODE
            LEFT JOIN {NX}.PR_M_ITEM i ON i.ITEM_CODE=s.ITEM_CODE
            WHERE {' AND '.join(w)}
            ORDER BY ISNULL(c.CUST_DESC,''), s.ITEM_CODE""", *p)
        rows = []
        for r in cur.fetchall():
            rows.append({"cust": r[0], "cust_nm": r[1], "charge": r[2],
                         "item": r[3], "item_nm": r[4], "qty": _f(r[5]),
                         "upd_user": r[6], "upd_dt": str(r[7] or "")[:19],
                         "nx_adj": 0.0})
        # ★nx 조정분(웹에서 조정한 것) 합산 — 라이브 현재고는 레거시만 갱신하므로 웹 조정분을 얹어준다.
        adj = {}
        try:
            nc = _nx(); ncur = nc.cursor()
            try:
                ncur.execute("""SELECT ITEM_CODE, CUST_CODE, SUM(CAST(MAINT_QTY AS float))
                      FROM nx.PU_T_SET_STOCK_MAINT_GAGONG
                     WHERE ISNULL(INSERT_WINDOW,'') LIKE 'w_pu_stock_28%_web'
                     GROUP BY ITEM_CODE, CUST_CODE""")
                for rr in ncur.fetchall():
                    adj[(str(rr[0] or "").strip(), str(rr[1] or "").strip())] = _f(rr[2])
            finally:
                nc.close()
        except Exception:
            pass
        for g in rows:
            a = adj.get((g["item"], g["cust"]), 0.0)
            if a:
                g["nx_adj"] = a
                g["qty"] += a
        # 구분/0재고 필터 — 합산 후 판정
        gb = (gubun or "%").strip()
        if gb == "1": rows = [r for r in rows if r["qty"] < 0]
        elif gb == "0": rows = [r for r in rows if r["qty"] > 0]
        if (zero or "").strip() == "숨김": rows = [r for r in rows if r["qty"] != 0]
        return {"rows": rows, "cnt": len(rows),
                "qty_sum": sum(r["qty"] for r in rows)}
    finally:
        cn.close()


@router.get("/api/gagongset/hist")
def setstock_hist(item: str = Query(""), cust: str = Query(""),
                  from_ymd: str = Query(""), to_ymd: str = Query(""), limit: int = Query(500)):
    """세트재고 조정이력 — 라이브(레거시 조정분) + nx(웹 조정분) 합산 조회."""
    d6a = _d6(from_ymd) if from_ymd else ""
    d6b = _d6(to_ymd) if to_ymd else ""
    w = ["1=1"]; p = []
    if item.strip(): w.append("m.ITEM_CODE=?"); p.append(item.strip())
    if cust.strip(): w.append("m.CUST_CODE=?"); p.append(cust.strip())
    if d6a: w.append("m.MAINT_YMD>=?"); p.append(d6a)
    if d6b: w.append("m.MAINT_YMD<=?"); p.append(d6b)
    wsql = " AND ".join(w)
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 3000))}
              u.MAINT_YMD, u.MAINT_SEQ, u.MAINT_TAG, u.CUST_CODE, u.ITEM_CODE,
              u.MAINT_QTY, ISNULL(u.REMARKS,''), ISNULL(u.INSERT_USER_ID,''), u.INSERT_DATETIME, u.SRC
            FROM (
              SELECT m.MAINT_YMD,m.MAINT_SEQ,m.MAINT_TAG,m.CUST_CODE,m.ITEM_CODE,m.MAINT_QTY,
                     m.REMARKS,m.INSERT_USER_ID,m.INSERT_DATETIME,'라이브' SRC
                FROM {LIVE}.PU_T_SET_STOCK_MAINT_GAGONG m WHERE {wsql}
              UNION ALL
              SELECT m.MAINT_YMD,m.MAINT_SEQ,m.MAINT_TAG,m.CUST_CODE,m.ITEM_CODE,m.MAINT_QTY,
                     m.REMARKS,m.INSERT_USER_ID,m.INSERT_DATETIME,'nx' SRC
                FROM {NX}.PU_T_SET_STOCK_MAINT_GAGONG m WHERE {wsql}
            ) u
            ORDER BY u.MAINT_YMD DESC, u.MAINT_SEQ DESC""", *(p + p))
        rows = [{"ymd": r[0], "seq": r[1], "tag": r[2], "cust": r[3], "item": r[4],
                 "qty": _f(r[5]), "remarks": r[6], "user": r[7],
                 "dt": str(r[8] or "")[:19], "src": r[9]} for r in cur.fetchall()]
        return {"rows": rows, "cnt": len(rows)}
    finally:
        cn.close()


@router.post("/api/gagongset/adjust")
def setstock_adjust(payload: dict = Body(...)):
    """세트재고 조정 등록(레거시 w_pu_stock_285 ue_save_after 이식). 쓰기는 nx 만.
       payload = {ymd, cust, maint_tag, reset_flag, user, rows:[{item, qty, remarks}]}
       ★reset_flag='1' + maint_tag='3'(장부수정) → 등록수량 = 입력수량 − 현재고 (결과가 입력값이 되도록)"""
    ymd = _d6(str(payload.get("ymd") or "").strip()) or datetime.now().strftime("%y%m%d")
    cust = str(payload.get("cust") or "").strip()
    tag = str(payload.get("maint_tag") or "3").strip()
    reset_flag = str(payload.get("reset_flag") or "0").strip()
    user = str(payload.get("user") or "web").strip()
    rows_in = [r for r in (payload.get("rows") or []) if str(r.get("item") or "").strip()]
    if not cust:
        raise HTTPException(400, "세트거래처를 선택하세요.")
    if not rows_in:
        raise HTTPException(400, "조정할 도번을 한 건 이상 입력하세요.")

    # 현재고(라이브+nx 조정분) — 장부수정 계산용
    cn = _conn(); cur = cn.cursor()
    cur_stock = {}
    try:
        items = list({str(r.get("item") or "").strip() for r in rows_in})
        for i in range(0, len(items), 900):
            ck = items[i:i + 900]; ph = ",".join("?" * len(ck))
            cur.execute(f"""SELECT ITEM_CODE, STOCK_QTY FROM {LIVE}.PU_T_SET_GAGONG_STOCK
                WHERE IN_CUST_CODE=? AND ITEM_CODE IN ({ph})""", cust, *ck)
            for rr in cur.fetchall():
                cur_stock[str(rr[0]).strip()] = _f(rr[1])
    finally:
        cn.close()

    nxcn = _nx(); nxcur = nxcn.cursor()
    try:
        # 웹 조정분도 현재고에 반영해서 장부수정 기준을 맞춘다
        for it in list(cur_stock.keys()) or []:
            pass
        nxcur.execute("""SELECT ITEM_CODE, SUM(CAST(MAINT_QTY AS float))
              FROM nx.PU_T_SET_STOCK_MAINT_GAGONG
             WHERE CUST_CODE=? AND ISNULL(INSERT_WINDOW,'') LIKE 'w_pu_stock_28%_web'
             GROUP BY ITEM_CODE""", cust)
        for rr in nxcur.fetchall():
            k = str(rr[0] or "").strip()
            cur_stock[k] = cur_stock.get(k, 0.0) + _f(rr[1])

        nxcur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.PU_T_SET_STOCK_MAINT_GAGONG WHERE MAINT_YMD=?", ymd)
        seq = int((nxcur.fetchone() or [0])[0] or 0)

        saved = []
        for r in rows_in:
            item = str(r.get("item") or "").strip()
            inq = _f(r.get("qty"))
            remarks = str(r.get("remarks") or "")[:255]
            # ★장부수정(3)+재설정 = 결과가 입력값이 되도록 차액만 등록
            qty = (inq - cur_stock.get(item, 0.0)) if (tag == "3" and reset_flag == "1") else inq
            if qty == 0:
                continue
            seq += 1
            nxcur.execute("""INSERT INTO nx.PU_T_SET_STOCK_MAINT_GAGONG
                (MAINT_YMD, MAINT_SEQ, MAINT_TAG, CUST_CODE, ITEM_CODE, MAINT_QTY, REMARKS,
                 INSERT_USER_ID, INSERT_DATETIME, INSERT_IP, INSERT_COMPUTER, INSERT_WINDOW,
                 UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_IP, UPDATE_COMPUTER, UPDATE_WINDOW)
                VALUES (?,?,?,?,?,?,?,?,GETDATE(),'','','w_pu_stock_285_web',?,GETDATE(),'','','w_pu_stock_285_web')""",
                ymd, seq, tag, cust, item, qty, remarks, user, user)
            saved.append({"item": item, "qty": qty, "before": cur_stock.get(item, 0.0),
                          "after": cur_stock.get(item, 0.0) + qty})
            cur_stock[item] = cur_stock.get(item, 0.0) + qty
        nxcn.commit()
        if not saved:
            return {"ok": False, "cnt": 0, "msg": "변동수량이 0이라 등록할 내용이 없습니다."}
        return {"ok": True, "cnt": len(saved), "rows": saved,
                "msg": f"세트재고 조정 {len(saved)}건 등록"}
    except HTTPException:
        nxcn.rollback(); raise
    except Exception as e:
        nxcn.rollback()
        raise HTTPException(500, f"등록 실패: {e}")
    finally:
        nxcn.close()
