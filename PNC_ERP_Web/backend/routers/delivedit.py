# -*- coding: utf-8 -*-
"""거래명세표 수정 — 레거시 w_pr_outside_030_new 이식.

세트납품서(SET+SHEET_NO) 단위 납품내역 조회 + 수량수정·삭제 + 출력 3종 재발행.
★입고완료건(CONFIRM_FLAG='1')은 조회·인쇄만 가능(레거시 동일 메시지).

★레거시 근거(PBD 원문 추출 · PR_OUTSIDE_01.PBD)
  · 판정 : dw_t1 → confirm_flag getitemstring → '1' 이면
           f_messagebox_ok('확인','입고완료건은 조회만 가능합니다.')
  · 원천 : dw_pr_outside_030_new_t1
      SELECT A.INPUT_YMD, A.INPUT_HMS, A.IN_CUST_CODE, A.ITEM_CODE, A.ITEM_GUBUN,
             A.SHEET_NO, A.AM_PM, A.PLAN_YMD,
             MAX(A.CONFIRM_FLAG) confirm_flag, SUM(A.INPUT_REQ_QTY) input_req_qty,
             A.MAT_CODE, MAX(A.USE_QTY) use_qty, SUM(A.MAT_QTY) mat_qty
        FROM PU_T_SET_INPUT_REQ_DTL A
       WHERE A.INPUT_YMD BETWEEN ? AND ? AND A.ITEM_CODE LIKE ?
         AND A.IN_CUST_CODE = ? AND A.MAT_CODE LIKE ?
       GROUP BY ...
  · 출력구분 3종 = 거래명세서 / 입고태그 / 출하검사성적서 (입고완료건도 재인쇄 가능)

★원천 = 웹 자체 nx.set_input_req(헤더) + nx.set_input_req_dtl(자도번 상세). 라이브 무접근.

  ┌─ 2026-08-31 소스 전환 (§1-9-1 단일 소스) ─────────────────────────────
  │ 전에는 미러 nx.PU_T_SET_INPUT_REQ_DTL(8/28 라이브 312,110행 스냅샷)을 읽었다.
  │ 그 결과 「거래명세서 발행」(coopplan → nx.set_input_req)으로 발행한 건이
  │ 이 화면에 **0건**으로 나왔다(실측 8/31: 발행 4건, 화면 0건).
  │ 스냅샷은 갱신되지 않으므로 웹 발행분이 영원히 안 보인다 → 발행이 쓰는 곳을 그대로 읽는다.
  │ UNION 폴백(A 없으면 B)은 두지 않는다 — 컷오버에 죽는 코드가 된다.
  │
  │ 자도번 상세는 발행 시 coopplan 이 dw_6 전개로 함께 넣는다(같은 날 추가).
  │ ※set_profile(도번→자도번 마스터)로 유추하면 안 된다 — 실측 대조 시
  │   ADM73210516→ADM74930508-12-2, AJR30125601→MJU66478501 처럼 마스터엔 없는
  │   실제 납품 조합이 있어 화면이 어긋난다.
  │
  │ 입고완료 판정: 미러 CONFIRM_FLAG='1' ↔ 웹 status '90'(입고완료)·'40'(검사중)·'99'(반품)
  └───────────────────────────────────────────────────────────
"""
from fastapi import APIRouter, Query, Body, HTTPException, Request
from common import _nx, _nx_tx, _d6, _sub_desc_plain
from routers.auth import require_user, scope_cust   # ★협력사 소속강제(방어심층) — 협력사는 자기 거래처만

router = APIRouter()

# 레거시 dw_pr_outside_030_new_t1 원문과 동일 집계 단위.
# ★소스 = 웹 자체(nx.set_input_req + _dtl) — 2026-08-31 전환.
#   전에는 미러 nx.PU_T_SET_INPUT_REQ_DTL 을 읽었는데 그건 8/28 라이브 스냅샷이라
#   웹에서 발행한 건(거래명세서 발행 → nx.set_input_req)이 이 화면에 0건으로 나왔다.
#   §1-9-1(단일 소스) — 발행이 쓰는 곳을 그대로 읽는다. UNION 폴백을 두지 않는다.
#   미러의 CONFIRM_FLAG(입고완료) ↔ 웹의 status: '90'=입고완료 → cf='1'.
_BASE = """
  FROM nx.set_input_req H WITH(NOLOCK)
  LEFT JOIN nx.set_input_req_dtl D WITH(NOLOCK) ON D.sheet_no = H.sheet_no
 WHERE H.input_ymd BETWEEN ? AND ? {more}
 GROUP BY H.input_ymd, H.input_hms, H.in_cust_code, H.item_code,
          H.item_gubun, H.sheet_no, H.am_pm, H.plan_ymd, D.mat_code
"""


@router.get("/api/delivedit/list")
def delivedit_list(request: Request, from_ymd: str = Query(""), to_ymd: str = Query(""),
                   cust: str = Query(""), doban: str = Query(""),
                   jadoban: str = Query(""), limit: int = Query(3000)):
    """납품내역 조회 — 좌측(납품일자·일시·세트납품서·도번·세트수량·입고완료·당일) +
       우측(자도번·사용수량·자재수량). 기간 = 납품일자(INPUT_YMD)."""
    f6, t6 = _d6(from_ymd), _d6(to_ymd)
    if not (len(f6) == 6 and len(t6) == 6):
        raise HTTPException(400, "납품기간(from_ymd/to_ymd)이 필요합니다.")
    if f6 > t6:
        f6, t6 = t6, f6
    cust = scope_cust(require_user(request), cust)     # ★협력사=자기 거래처 강제(내부=passthrough)
    if cust == "__NONE__":
        raise HTTPException(403, "거래처코드가 없는 협력사 계정입니다.")
    more = []; p = [f6, t6]
    cc = str(cust or "").strip()
    if cc:
        # 코드 또는 거래처명 — 레거시는 코드지만 웹은 §3(이름 우선) 규칙상 둘 다 받는다
        more.append("""AND (H.in_cust_code=? OR EXISTS(SELECT 1 FROM nx.CM_M_CUST c2 WITH(NOLOCK)
                             WHERE c2.CUST_CODE=H.in_cust_code AND c2.CUST_DESC LIKE ?))""")
        p += [cc, f"%{cc}%"]
    if doban.strip():
        more.append("AND H.item_code LIKE ?"); p.append(f"%{doban.strip()}%")
    if jadoban.strip():
        more.append("AND D.mat_code LIKE ?"); p.append(f"%{jadoban.strip()}%")
    nx = _nx(); cur = nx.cursor()
    try:
        # ★세트수량 = 헤더값(MAX) — 자도번 조인으로 행이 늘어나므로 SUM 하면 배수가 된다.
        #   입고완료 cf = status '90' → '1'(레거시 CONFIRM_FLAG 대응).
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 8000))}
              H.input_ymd, H.input_hms, H.sheet_no, H.in_cust_code, H.item_code,
              H.item_gubun, H.am_pm, H.plan_ymd,
              MAX(CASE WHEN ISNULL(H.status,'')='90' THEN '1' ELSE '0' END) cf,
              MAX(ISNULL(H.deliver_qty, H.input_req_qty)) req,
              D.mat_code, MAX(ISNULL(D.use_qty,0)) uq, SUM(ISNULL(D.mat_qty,0)) mq,
              -- ★바코드번호(2026-08-31) — 화면·인쇄가 이걸로 통일한다.
              --   sheet_no(납품서번호)와 barcode_no 는 다른 번호다: 한 번 발행에 도번이 여러 개면
              --   sheet 는 도번마다 하나씩 늘고 barcode 는 하나다(실측 901204·901205 ↔ 700007).
              --   둘 다 'SET' 을 붙여 보여주던 탓에 같은 번호로 오해됐다.
              MAX(ISNULL(H.barcode_no,'')) bc
            {_BASE.format(more=' '.join(more))}
            ORDER BY H.input_ymd DESC, H.input_hms DESC, H.sheet_no, H.item_code, D.mat_code""", *p)
        raw = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            raw.append({"ymd": g(0), "hms": g(1), "sheet_no": g(2), "cc": g(3),
                        "doban": g(4), "gubun": g(5), "am_pm": g(6), "plan_ymd": g(7),
                        "cf": g(8), "set_qty": float(r[9] or 0), "jadoban": g(10),
                        "use_qty": float(r[11] or 0), "mat_qty": float(r[12] or 0),
                        "barcode": g(13)})
        # 거래처명·품명 디코드
        ccs = {x["cc"] for x in raw if x["cc"]}
        its = {x["doban"] for x in raw if x["doban"]} | {x["jadoban"] for x in raw if x["jadoban"]}
        cnm = {}; inm = {}
        if ccs:
            ph = ",".join("?" * len(ccs)); lst = list(ccs)
            cur.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM nx.CM_M_CUST WHERE CUST_CODE IN ({ph})", *lst)
            for a, b in cur.fetchall(): cnm[str(a).strip()] = str(b).strip()
        il = [x for x in its if x]
        for i in range(0, len(il), 900):
            ch = il[i:i + 900]; ph = ",".join("?" * len(ch))
            cur.execute(f"SELECT item_code, ISNULL(item_name,'') FROM nx.item WHERE item_code IN ({ph})", *ch)
            for a, b in cur.fetchall(): inm[str(a).strip()] = str(b).strip()
        # 도번 단위로 묶어 좌측 셀 병합용 first/span 부여(레거시 화면 형태)
        rows = []; i = 0
        while i < len(raw):
            k = (raw[i]["sheet_no"], raw[i]["cc"], raw[i]["doban"], raw[i]["hms"])
            blk = []
            while i < len(raw) and (raw[i]["sheet_no"], raw[i]["cc"], raw[i]["doban"], raw[i]["hms"]) == k:
                blk.append(raw[i]); i += 1
            for n, x in enumerate(blk):
                rows.append(dict(x, cnm=cnm.get(x["cc"], ""),
                                 dnm=inm.get(x["doban"], ""), jnm=inm.get(x["jadoban"], ""),
                                 first=1 if n == 0 else 0, span=len(blk)))
        heads = [x for x in rows if x["first"]]
        return {"rows": rows, "cnt": len(rows), "heads": len(heads),
                "sheets": len({(x["sheet_no"], x["cc"]) for x in rows}),
                "editable": sum(1 for x in heads if x["cf"] != "1"),
                "sum_set": round(sum(x["set_qty"] for x in heads), 2)}
    finally:
        nx.close()


def _guard(cur, sn, cc, doban, hms):
    """입고완료 판정 — 입고된 건은 수정·삭제 거부(레거시 CONFIRM_FLAG='1' 대응).
       ★웹 소스(nx.set_input_req)의 status 로 판정(2026-08-31):
           00 요청 · 10 발행 · 20 출발 · 30 입고대기 → 수정·삭제 가능
           40 검사중 · 90 입고완료 · 99 반품        → 거부(재고가 이미 움직였다)
       반환 = (현재 세트수량, barcode_no) — 삭제 시 발행이력 정리에 쓴다."""
    cur.execute("""SELECT ISNULL(status,''), ISNULL(deliver_qty, input_req_qty),
                          ISNULL(barcode_no,'')
                     FROM nx.set_input_req WITH(NOLOCK)
                    WHERE sheet_no=? AND in_cust_code=? AND item_code=? AND input_hms=?""",
                sn, cc, doban, hms)
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, f"납품내역을 찾을 수 없습니다. (SET{sn} / {doban})")
    st = str(r[0] or "").strip()
    if st in ('40', '90', '99'):
        _nm = {'40': '검사중', '90': '입고완료', '99': '반품'}.get(st, st)
        raise HTTPException(409, f"{_nm} 건은 조회만 가능합니다. (SET{sn} / {doban})")
    return float(r[1] or 0), str(r[2] or "").strip()


@router.post("/api/delivedit/update")
def delivedit_update(request: Request, payload: dict = Body(...)):
    """납품수량(세트수량) 수정. 자재수량은 사용수량×세트수량으로 함께 갱신.
       ★입고완료건 거부. 헤더(nx.set_input_req)·상세(_dtl)·발행이력(nx.deliv_issue)을
         한 트랜잭션에서 같이 맞춘다 — 하나만 고치면 인쇄·입고·잔량이 어긋난다."""
    sn = str(payload.get("sheet_no", "")).strip()
    cc = str(payload.get("cc", "")).strip()
    cc = scope_cust(require_user(request), cc)          # ★협력사=자기 거래처 강제(남의 명세표 수정 차단)
    if cc == "__NONE__":
        raise HTTPException(403, "거래처코드가 없는 협력사 계정입니다.")
    doban = str(payload.get("doban", "")).strip()
    hms = str(payload.get("hms", "")).strip()
    if not (sn and cc and doban and hms):
        raise HTTPException(400, "세트납품서번호/거래처/도번/납품일시가 필요합니다.")
    try:
        qty = int(float(payload.get("qty")))
    except (TypeError, ValueError):
        raise HTTPException(400, "납품수량이 올바르지 않습니다.")
    if qty <= 0:
        raise HTTPException(400, "납품수량은 0보다 커야 합니다.")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        old, bc = _guard(cur, sn, cc, doban, hms)
        # ★수정은 세 곳을 함께 맞춘다(2026-08-31) — 하나만 고치면 인쇄·입고·발행이력이 어긋난다.
        #   ① 헤더 nx.set_input_req   : 세트수량
        #   ② 상세 nx.set_input_req_dtl: 자재수량 = 세트수량 × 사용수량(재계산)
        #   ③ 발행이력 nx.deliv_issue  : 같은 바코드·도번의 납품수량
        cur.execute("""UPDATE nx.set_input_req
                          SET deliver_qty=?, input_req_qty=?,
                              update_user_id='web', update_datetime=getdate()
                        WHERE sheet_no=? AND in_cust_code=? AND item_code=? AND input_hms=?""",
                    qty, qty, sn, cc, doban, hms)
        nh = cur.rowcount
        cur.execute("""UPDATE nx.set_input_req_dtl
                          SET mat_qty = ? * ISNULL(use_qty,1)
                        WHERE sheet_no=?""", qty, sn)
        n = cur.rowcount
        ni = 0
        if bc:
            cur.execute("""UPDATE nx.deliv_issue SET deliver_qty=?
                            WHERE barcode_no=? AND cust_code=? AND item_code=?
                              AND ISNULL(status,'') NOT IN ('90','99')""", qty, bc, cc, doban)
            ni = cur.rowcount
        nx.commit()
        return {"ok": True, "updated": n, "head_updated": nh, "issue_updated": ni,
                "old_qty": old, "new_qty": qty}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()


@router.post("/api/delivedit/delete")
def delivedit_delete(request: Request, payload: dict = Body(...)):
    """납품내역 삭제(도번 단위) — ★입고완료건 거부."""
    sn = str(payload.get("sheet_no", "")).strip()
    cc = str(payload.get("cc", "")).strip()
    doban = str(payload.get("doban", "")).strip()
    hms = str(payload.get("hms", "")).strip()
    cc = scope_cust(require_user(request), cc)          # ★협력사=자기 거래처 강제(남의 명세표 삭제 차단)
    if cc == "__NONE__":
        raise HTTPException(403, "거래처코드가 없는 협력사 계정입니다.")
    if not (sn and cc and doban and hms):
        raise HTTPException(400, "세트납품서번호/거래처/도번/납품일시가 필요합니다.")
    nx = _nx_tx(); cur = nx.cursor()
    try:
        _old, bc = _guard(cur, sn, cc, doban, hms)   # 입고된 건이면 여기서 409
        # ★삭제도 세 곳(2026-08-31, 대표 확정: "입고처리 안 됐으면 발행이력도 삭제").
        #   입고완료(90)·검사중(40)·반품(99)은 _guard 가 이미 막았으므로 여기 오는 건
        #   전부 미입고분이다 → 발행이력까지 지워 흔적을 남기지 않는다.
        cur.execute("DELETE FROM nx.set_input_req_dtl WHERE sheet_no=?", sn)
        n = cur.rowcount
        cur.execute("""DELETE FROM nx.set_input_req
                        WHERE sheet_no=? AND in_cust_code=? AND item_code=? AND input_hms=?""",
                    sn, cc, doban, hms)
        nh = cur.rowcount
        ni = 0
        if bc:
            # 같은 바코드에 다른 도번이 남아 있으면 그 발행이력은 건드리지 않는다(도번 단위 삭제).
            cur.execute("""DELETE FROM nx.deliv_issue
                            WHERE barcode_no=? AND cust_code=? AND item_code=?
                              AND ISNULL(status,'') NOT IN ('90','99')""", bc, cc, doban)
            ni = cur.rowcount
        nx.commit()
        return {"ok": True, "deleted": n, "head_deleted": nh, "issue_deleted": ni}
    except Exception:
        nx.rollback(); raise
    finally:
        nx.close()


@router.get("/api/delivedit/print")
def delivedit_print(request: Request, sheet_no: str = Query(...), cc: str = Query(""), hms: str = Query(""),
                    kind: str = Query("stmt")):
    """출력용 데이터 — kind: stmt=거래명세서 / tag=입고태그 / insp=출하검사성적서.
       ★입고완료건도 재인쇄 가능(레거시 동일)."""
    sn = str(sheet_no or "").strip()
    cc = scope_cust(require_user(request), cc)          # ★협력사=자기 거래처 강제
    if cc == "__NONE__":
        raise HTTPException(403, "거래처코드가 없는 협력사 계정입니다.")
    if not sn:
        raise HTTPException(400, "세트납품서번호가 필요합니다.")
    if kind not in ("stmt", "tag", "insp"):
        raise HTTPException(400, "출력구분이 올바르지 않습니다.")
    nx = _nx(); cur = nx.cursor()
    try:
        # ★소스 = 웹 자체(set_input_req + _dtl) — 2026-08-31 전환(list 와 동일 기준)
        w = ["H.sheet_no=?"]; p = [sn]
        if cc.strip():  w.append("H.in_cust_code=?"); p.append(cc.strip())
        if hms.strip(): w.append("H.input_hms=?"); p.append(hms.strip())
        cur.execute(f"""SELECT H.input_ymd, H.input_hms, H.sheet_no, H.in_cust_code,
              ISNULL(c.CUST_DESC,''), H.item_code, ISNULL(i1.item_name,''),
              ISNULL(i1.item_spec,''), D.mat_code, ISNULL(i2.item_name,''),
              MAX(ISNULL(H.deliver_qty, H.input_req_qty)), MAX(ISNULL(D.use_qty,0)), SUM(ISNULL(D.mat_qty,0)),
              MAX(CASE WHEN ISNULL(H.status,'')='90' THEN '1' ELSE '0' END), MAX(ISNULL(H.insp_flag,'')),
              MAX(ISNULL(H.plan_ymd,'')),
              MAX(ISNULL(H.barcode_no,''))   -- ★인쇄물에 바코드번호 표기(2026-08-31)
            FROM nx.set_input_req H WITH(NOLOCK)
            LEFT JOIN nx.set_input_req_dtl D WITH(NOLOCK) ON D.sheet_no=H.sheet_no
            LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=H.in_cust_code
            LEFT JOIN nx.item i1 WITH(NOLOCK) ON i1.item_code=H.item_code
            LEFT JOIN nx.item i2 WITH(NOLOCK) ON i2.item_code=D.mat_code
           WHERE {' AND '.join(w)}
           GROUP BY H.input_ymd, H.input_hms, H.sheet_no, H.in_cust_code, c.CUST_DESC,
                    H.item_code, i1.item_name, i1.item_spec, D.mat_code, i2.item_name
           ORDER BY H.item_code, D.mat_code""", *p)
        rows = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            # ★품명은 SUB 접미사 병기('[-12-1] ')를 벗긴 원품명 — 레거시 출력물과 동일하게.
            #   병기값은 화면 조회용으로 마스터에 박아둔 것이고, 출력물은 원품명이 정답.
            rows.append({"ymd": g(0), "hms": g(1), "sheet_no": g(2), "cc": g(3), "cnm": g(4),
                         "doban": g(5), "dnm": _sub_desc_plain(g(6)), "dspec": g(7),
                         "jadoban": g(8), "jnm": _sub_desc_plain(g(9)),
                         "set_qty": float(r[10] or 0), "use_qty": float(r[11] or 0),
                         "mat_qty": float(r[12] or 0), "cf": g(13),
                         "insp": g(14), "plan_ymd": g(15), "barcode": g(16)})
        if not rows:
            raise HTTPException(404, f"출력할 내역이 없습니다. (납품서 {sn})")
        h = rows[0]
        title = {"stmt": "거 래 명 세 서", "tag": "입 고 태 그", "insp": "출하검사성적서"}[kind]
        return {"ok": True, "kind": kind, "title": title,
                "sheet_no": h["sheet_no"], "barcode": h["barcode"],
                "ymd": h["ymd"], "hms": h["hms"],
                "cc": h["cc"], "cnm": h["cnm"], "rows": rows, "cnt": len(rows),
                "sum_set": round(sum(x["set_qty"] for x in rows), 2),
                "sum_mat": round(sum(x["mat_qty"] for x in rows), 2)}
    finally:
        nx.close()


@router.get("/api/delivedit/items")
def delivedit_items(request: Request, kind: str = Query("doban"), q: str = Query(""),
                    cust: str = Query(""), from_ymd: str = Query(""), to_ymd: str = Query("")):
    """도번/자도번 오토컴플리트 — 실제 납품내역에 있는 것만(§3 오토컴플리트 규칙).
       kind: doban=도번(ITEM_CODE) / jadoban=자도번(MAT_CODE).
       거래처·기간이 주어지면 그 범위로 좁힌다(화면 조회조건과 연동)."""
    cust = scope_cust(require_user(request), cust)      # ★협력사=자기 거래처 강제
    if cust == "__NONE__":
        raise HTTPException(403, "거래처코드가 없는 협력사 계정입니다.")
    # ★소스 = 웹 자체(2026-08-31). 자도번=상세(D.mat_code) · 도번=헤더(H.item_code)
    col = "D.mat_code" if kind == "jadoban" else "H.item_code"
    w = ["1=1"]; p = []
    f6, t6 = _d6(from_ymd), _d6(to_ymd)
    if len(f6) == 6 and len(t6) == 6:
        if f6 > t6: f6, t6 = t6, f6
        w.append("H.input_ymd BETWEEN ? AND ?"); p += [f6, t6]
    cc = str(cust or "").strip()
    if cc:
        w.append("""(H.in_cust_code=? OR EXISTS(SELECT 1 FROM nx.CM_M_CUST c2 WITH(NOLOCK)
                      WHERE c2.CUST_CODE=H.in_cust_code AND c2.CUST_DESC LIKE ?))""")
        p += [cc, f"%{cc}%"]
    if q.strip():
        w.append(f"({col} LIKE ? OR EXISTS(SELECT 1 FROM nx.item i2 WITH(NOLOCK)"
                 f" WHERE i2.item_code={col} AND i2.item_name LIKE ?))")
        p += [f"%{q.strip()}%", f"%{q.strip()}%"]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"""SELECT TOP 400 {col} code, MAX(ISNULL(i.item_name,'')) nm
                          FROM nx.set_input_req H WITH(NOLOCK)
                          LEFT JOIN nx.set_input_req_dtl D WITH(NOLOCK) ON D.sheet_no=H.sheet_no
                          LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code={col}
                         WHERE {' AND '.join(w)} AND ISNULL({col},'')<>''
                         GROUP BY {col} ORDER BY {col}""", *p)
        return {"kind": kind,
                "rows": [{"code": str(a).strip(), "nm": str(b).strip()} for a, b in cur.fetchall()]}
    finally:
        nx.close()


@router.get("/api/delivedit/custs")
def delivedit_custs(request: Request, q: str = Query("")):
    """납품처 오토컴플리트 — 실제 납품내역이 있는 거래처만. ★협력사는 자기 거래처만."""
    mine = scope_cust(require_user(request), None)      # 협력사면 자기코드, 내부면 None
    if mine == "__NONE__":
        return {"rows": []}                              # ★코드없는 협력사=빈목록(전체노출 차단)
    nx = _nx(); cur = nx.cursor()
    try:
        w = ""; p = []
        if mine:
            w = "AND c.CUST_CODE=?"; p = [mine]          # ★협력사=자기 거래처만 노출
        elif q.strip():
            w = "AND (c.CUST_CODE LIKE ? OR c.CUST_DESC LIKE ?)"
            p = [f"%{q.strip()}%", f"%{q.strip()}%"]
        cur.execute(f"""SELECT TOP 300 c.CUST_CODE, ISNULL(c.CUST_DESC,'')
                          FROM nx.CM_M_CUST c WITH(NOLOCK)
                         WHERE EXISTS(SELECT 1 FROM nx.set_input_req h WITH(NOLOCK)
                                       WHERE h.in_cust_code=c.CUST_CODE) {w}
                         ORDER BY c.CUST_DESC""", *p)
        return {"rows": [{"cc": str(a).strip(), "nm": str(b).strip()} for a, b in cur.fetchall()]}
    finally:
        nx.close()
