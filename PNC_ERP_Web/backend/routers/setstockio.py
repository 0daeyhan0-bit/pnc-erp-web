"""자재세트재고입출고현황 (레거시 w_pu_stock_070) — 조회 전용.

★웹 정본 = nx.set_stock_maint (2026-08-27 라이브 기초이관 후 웹이 쌓는 단일원장).
  라이브 PU_T_SET_MAT_STOCK / PU_T_SET_STOCK_MAINT 는 읽지 않는다(§1-9-1 단일소스).

  잔액   = SUM(maint_qty) GROUP BY cust_code, item_code
  maint_tag : 9=기초이관 · 2=바코드입고(+) · 3=출고(−) · 1=조정
  출고(생산실적) = nx.PR_T_PROD_DTL — 세트도번 단위 차감(레거시 실측: 자도번 분해 아님)

  ※레거시 대사: 잔액 = 입고 − 출고 가 표본 20건 diff 0 으로 성립(2026-08-30 실측).
"""
from fastapi import APIRouter, Query
from common import _nx   # 라이브(_conn) 미사용 — 웹 단일소스

router = APIRouter()


def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


@router.get("/api/setstockio/list")
def setstockio_list(
    cust: str = Query("", description="세트거래처 코드(부분일치)"),
    item: str = Query("", description="도번(부분일치)"),
    gubun: str = Query("all", description="minus|plus|all"),
):
    """좌측 그리드 — 세트거래처×세트도번 잔액."""
    where = []
    args = []
    if cust:
        where.append("m.cust_code LIKE ?")
        args.append("%" + cust + "%")
    if item:
        where.append("m.item_code LIKE ?")
        args.append("%" + item + "%")
    cond = (" WHERE " + " AND ".join(where)) if where else ""

    having = ""
    if gubun == "minus":
        having = " HAVING SUM(m.maint_qty) < 0"
    elif gubun == "plus":
        having = " HAVING SUM(m.maint_qty) > 0"

    sql = f"""
        SELECT m.cust_code, m.item_code,
               SUM(m.maint_qty)               AS stock_qty,
               MAX(m.insert_datetime)         AS last_dt
          FROM nx.set_stock_maint m WITH(NOLOCK)
          {cond}
         GROUP BY m.cust_code, m.item_code
         {having}
    """
    with _nx() as cn:
        cur = cn.cursor()
        cur.execute(sql, *args)
        rows = _rows(cur)

        # 거래처명 · 품명 매핑 (클린본)
        custs = sorted({(r["cust_code"] or "").strip() for r in rows if r["cust_code"]})
        cmap = {}
        for i in range(0, len(custs), 500):
            ch = custs[i:i + 500]
            ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT partner_code, partner_name FROM nx.partner WITH(NOLOCK) "
                        f"WHERE partner_code IN ({ph})", *ch)
            for c, n in cur.fetchall():
                cmap[(c or "").strip()] = (n or "").strip()

        # 담당 = 거래처 담당자(CHARGE_USER_ID). 레거시 070 의 '담당' 컬럼과 동일 원천
        chmap = {}
        for i in range(0, len(custs), 500):
            ch = custs[i:i + 500]
            ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT CUST_CODE, CHARGE_USER_ID FROM nx.CM_M_CUST WITH(NOLOCK) "
                        f"WHERE CUST_CODE IN ({ph})", *ch)
            for c, n in cur.fetchall():
                chmap[(c or "").strip()] = (n or "").strip()

        items = sorted({(r["item_code"] or "").strip() for r in rows if r["item_code"]})
        imap = {}
        for i in range(0, len(items), 500):
            ch = items[i:i + 500]
            ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT item_code, item_name FROM nx.item WITH(NOLOCK) "
                        f"WHERE item_code IN ({ph})", *ch)
            for c, n in cur.fetchall():
                imap[(c or "").strip()] = (n or "").strip()

    out = []
    for r in rows:
        cc = (r["cust_code"] or "").strip()
        ic = (r["item_code"] or "").strip()
        out.append({
            "cust_code": cc,
            "cust_name": cmap.get(cc, cc),
            "item_code": ic,
            "item_name": imap.get(ic, ""),
            "stock_qty": _f(r["stock_qty"]),
            "user_id": chmap.get(cc, ""),
        })
    # 레거시 정렬 = 재고수량 내림차순 → 거래처 → 도번
    out.sort(key=lambda x: (-x["stock_qty"], x["cust_name"], x["item_code"]))
    return {
        "rows": out,
        "cnt": len(out),
        "total": sum(x["stock_qty"] for x in out),
    }


@router.get("/api/setstockio/detail")
def setstockio_detail(
    item: str = Query(..., description="세트도번"),
    cust: str = Query("", description="세트거래처 코드"),
    frm: str = Query("", description="YYMMDD"),
    to: str = Query("", description="YYMMDD"),
):
    """우측 그리드 — 일자별 전일재고/입고/출고/재고."""
    item = (item or "").strip()
    cust = (cust or "").strip()
    frm = (frm or "").strip()
    to = (to or "").strip()

    cc = " AND m.cust_code=?" if cust else ""

    with _nx() as cn:
        cur = cn.cursor()

        # ── 입고·조정 (웹 정본 원장). tag 9=기초이관은 '전일재고'로만 반영
        a = [item] + ([cust] if cust else [])
        cur.execute(f"""
            SELECT m.maint_ymd AS ymd, m.maint_tag AS tag,
                   SUM(m.maint_qty) AS qty,
                   MAX(m.insert_user_id) AS user_id
              FROM nx.set_stock_maint m WITH(NOLOCK)
             WHERE m.item_code=?{cc}
             GROUP BY m.maint_ymd, m.maint_tag
        """, *a)
        maint = _rows(cur)

        # ── 출고 = 생산실적. 레거시(w_pr_input_220/520)는 마지막 공정 실적 시
        #    스캔 도번(=세트도번) 그대로 -실적수량 차감(use_qty 곱셈 없음).
        #    ★차감 대상 거래처 = dw_7 이 리턴하는 '그 도번의 세트 거래처 전부'.
        #      같은 BOM 조합을 여러 업체가 공급하면 그 업체들 모두 전량 차감된다
        #      (라이브 실측 2026-08-30: 3개월 5,756건 중 2,496건 43%가 복수 거래처,
        #       최대 7곳. AHQ73469301 = 2067·2096·2266 3곳 동시차감 33행 전부).
        #      ★단 '지금 그 세트를 대는 업체'만이다 — 거래가 끊긴 옛 업체는 빠진다.
        #        판별식 = 최근(90일) 세트입고 이력 유무. 라이브 26/08 실측:
        #          차감O 832조합 중 611(73%)이 최근입고 보유
        #          차감X 615조합 중   7( 1%)만 보유          → 판별력 확인
        #        (A업체가 대던 BOM 을 D업체가 대면 D 가 차감된다 = 대표 확인 규칙)
        #      ⛔nx.set_vendor_map(현재매핑 1:1)은 복수업체를 못 담아 정합 42% → 미사용.
        prod = []
        if cust:
            cur.execute("""SELECT COUNT(*) FROM nx.PU_T_SET_INPUT_REQ WITH(NOLOCK)
                            WHERE ITEM_CODE=? AND IN_CUST_CODE=?
                              AND INPUT_YMD >= CONVERT(varchar(6), DATEADD(day,-90,GETDATE()), 12)""",
                        item, cust)
            is_target = (cur.fetchone() or [0])[0] > 0
            if not is_target:      # 웹 신규 세트입고(nx.set_input_req)도 인정
                cur.execute("""SELECT COUNT(*) FROM nx.set_input_req WITH(NOLOCK)
                                WHERE item_code=? AND in_cust_code=?""", item, cust)
                is_target = (cur.fetchone() or [0])[0] > 0
        else:
            is_target = True      # 거래처 미지정 = 도번 전체 관점

        if is_target:
            cur.execute("""
                SELECT p.PROD_YMD AS ymd, SUM(p.PROD_QTY) AS qty,
                       MAX(p.PROD_USER_ID) AS user_id
                  FROM nx.PR_T_PROD_DTL p WITH(NOLOCK)
                 WHERE p.ITEM_CODE=?
                 GROUP BY p.PROD_YMD
            """, item)
            prod = _rows(cur)

        # ★기초이관(tag 9)일 = 잔액 확정 시점. 그 이전 생산실적은 이미 잔액에 반영돼
        #   있으므로 다시 빼면 이중차감이 된다. 이관일 '이후' 실적만 출고로 잡는다.
        cur.execute("""SELECT MAX(maint_ymd) FROM nx.set_stock_maint WITH(NOLOCK)
                        WHERE maint_tag='9'""")
        r = cur.fetchone()
        mig = (r[0] or "").strip() if r and r[0] else ""

        cur.execute("SELECT TOP 1 item_name FROM nx.item WITH(NOLOCK) WHERE item_code=?", item)
        r = cur.fetchone()
        item_name = (r[0] or "").strip() if r else ""

    # ── 일자축 병합
    day = {}

    def slot(y):
        return day.setdefault(y, {"ymd": y, "in_qty": 0.0, "out_qty": 0.0,
                                  "note": "", "user_id": ""})

    base = 0.0            # 조회기간 이전 누계 = 전일재고
    for m in maint:
        y = (m["ymd"] or "").strip()
        q = _f(m["qty"])
        tag = (m["tag"] or "").strip()
        if tag == "9":            # 기초이관분은 항상 기초잔액
            base += q
            continue
        if mig and y <= mig:      # 이관일 이전 입출고는 이관 잔액에 이미 포함
            continue
        if frm and y < frm:
            base += q
            continue
        if to and y > to:
            continue
        s = slot(y)
        if q >= 0:
            s["in_qty"] += q
            s["note"] = "바코드입고" if tag == "2" else "재고조정"
        else:
            s["out_qty"] += -q
            s["note"] = "재고조정"
        s["user_id"] = (m["user_id"] or "").strip()

    for p in prod:
        y = (p["ymd"] or "").strip()
        q = _f(p["qty"])
        if mig and y <= mig:      # 기초이관 잔액에 이미 반영됨 → 스킵
            continue
        if frm and y < frm:
            base -= q
            continue
        if to and y > to:
            continue
        s = slot(y)
        s["out_qty"] += q
        if not s["note"]:
            s["note"] = "생산실적출고"
            s["user_id"] = (p["user_id"] or "").strip()

    rows = []
    bal = base
    for y in sorted(day):
        d = day[y]
        prev = bal
        bal = bal + d["in_qty"] - d["out_qty"]
        note = d["note"]
        if note and d["user_id"]:
            note = f"{note} => 작업자 : {d['user_id']}"
        rows.append({
            "ymd": y, "prev_qty": prev,
            "in_qty": d["in_qty"], "out_qty": d["out_qty"],
            "stock_qty": bal, "note": note,
        })

    return {
        "item_code": item, "item_name": item_name,
        "base": base,
        "rows": rows,
        "sum_in": sum(r["in_qty"] for r in rows),
        "sum_out": sum(r["out_qty"] for r in rows),
        "last": bal,
    }
