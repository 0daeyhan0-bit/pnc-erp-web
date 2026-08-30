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

★원천은 전부 nx (라이브 무접근).
  nx.PU_T_SET_INPUT_REQ_DTL 은 2026-08-28 라이브에서 312,110행 복사해 신설.
  자도번(MAT_CODE)·사용수량(USE_QTY)·자재수량(MAT_QTY)이 이 테이블에 실려 있다.
  ※set_profile(도번→자도번 마스터)로 유추하면 안 된다 — 실측 대조 시
    ADM73210516→ADM74930508-12-2, AJR30125601→MJU66478501 처럼 마스터엔 없는
    실제 납품 조합이 있어 화면이 어긋난다.
"""
from fastapi import APIRouter, Query, Body, HTTPException, Request
from common import _nx, _nx_tx, _d6
from routers.auth import require_user, scope_cust   # ★협력사 소속강제(방어심층) — 협력사는 자기 거래처만

router = APIRouter()

# 레거시 dw_pr_outside_030_new_t1 원문과 동일 집계 단위
_BASE = """
  FROM nx.PU_T_SET_INPUT_REQ_DTL A WITH(NOLOCK)
 WHERE A.INPUT_YMD BETWEEN ? AND ? {more}
 GROUP BY A.INPUT_YMD, A.INPUT_HMS, A.IN_CUST_CODE, A.ITEM_CODE,
          A.ITEM_GUBUN, A.SHEET_NO, A.AM_PM, A.PLAN_YMD, A.MAT_CODE
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
        more.append("""AND (A.IN_CUST_CODE=? OR EXISTS(SELECT 1 FROM nx.CM_M_CUST c2 WITH(NOLOCK)
                             WHERE c2.CUST_CODE=A.IN_CUST_CODE AND c2.CUST_DESC LIKE ?))""")
        p += [cc, f"%{cc}%"]
    if doban.strip():
        more.append("AND A.ITEM_CODE LIKE ?"); p.append(f"%{doban.strip()}%")
    if jadoban.strip():
        more.append("AND A.MAT_CODE LIKE ?"); p.append(f"%{jadoban.strip()}%")
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 8000))}
              A.INPUT_YMD, A.INPUT_HMS, A.SHEET_NO, A.IN_CUST_CODE, A.ITEM_CODE,
              A.ITEM_GUBUN, A.AM_PM, A.PLAN_YMD,
              MAX(A.CONFIRM_FLAG) cf, SUM(A.INPUT_REQ_QTY) req,
              A.MAT_CODE, MAX(A.USE_QTY) uq, SUM(A.MAT_QTY) mq
            {_BASE.format(more=' '.join(more))}
            ORDER BY A.INPUT_YMD DESC, A.INPUT_HMS DESC, A.SHEET_NO, A.ITEM_CODE, A.MAT_CODE""", *p)
        raw = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            raw.append({"ymd": g(0), "hms": g(1), "sheet_no": g(2), "cc": g(3),
                        "doban": g(4), "gubun": g(5), "am_pm": g(6), "plan_ymd": g(7),
                        "cf": g(8), "set_qty": float(r[9] or 0), "jadoban": g(10),
                        "use_qty": float(r[11] or 0), "mat_qty": float(r[12] or 0)})
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
    """입고완료 판정 — 레거시와 동일하게 CONFIRM_FLAG='1' 이면 거부."""
    cur.execute("""SELECT MAX(ISNULL(CONFIRM_FLAG,'0')), SUM(INPUT_REQ_QTY), COUNT(*)
                     FROM nx.PU_T_SET_INPUT_REQ_DTL
                    WHERE SHEET_NO=? AND IN_CUST_CODE=? AND ITEM_CODE=? AND INPUT_HMS=?""",
                sn, cc, doban, hms)
    r = cur.fetchone()
    if not r or not r[2]:
        raise HTTPException(404, f"납품내역을 찾을 수 없습니다. (SET{sn} / {doban})")
    if str(r[0] or "").strip() == "1":
        raise HTTPException(409, "입고완료건은 조회만 가능합니다.")
    return float(r[1] or 0)


@router.post("/api/delivedit/update")
def delivedit_update(request: Request, payload: dict = Body(...)):
    """납품수량(세트수량) 수정. 자재수량은 사용수량×세트수량으로 함께 갱신.
       ★입고완료건 거부. 헤더(PU_T_SET_INPUT_REQ)도 같이 맞춘다."""
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
        old = _guard(cur, sn, cc, doban, hms)
        cur.execute("""UPDATE nx.PU_T_SET_INPUT_REQ_DTL
                          SET OLD_INPUT_REQ_QTY=INPUT_REQ_QTY,
                              INPUT_REQ_QTY=?, MAT_QTY=? * ISNULL(USE_QTY,1),
                              UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='w_pr_outside_030(web)'
                        WHERE SHEET_NO=? AND IN_CUST_CODE=? AND ITEM_CODE=? AND INPUT_HMS=?
                          AND ISNULL(CONFIRM_FLAG,'0')<>'1'""", qty, qty, sn, cc, doban, hms)
        n = cur.rowcount
        # 헤더도 동일 수량으로(있을 때만) — 두 테이블이 어긋나면 인쇄·입고가 틀어진다
        cur.execute("""UPDATE nx.PU_T_SET_INPUT_REQ
                          SET OLD_INPUT_REQ_QTY=INPUT_REQ_QTY, INPUT_REQ_QTY=?,
                              UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW='w_pr_outside_030(web)'
                        WHERE SHEET_NO=? AND IN_CUST_CODE=? AND ITEM_CODE=? AND INPUT_HMS=?
                          AND ISNULL(CONFIRM_FLAG,'0')<>'1'""", qty, sn, cc, doban, hms)
        nh = cur.rowcount
        nx.commit()
        return {"ok": True, "updated": n, "head_updated": nh, "old_qty": old, "new_qty": qty}
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
        _guard(cur, sn, cc, doban, hms)
        cur.execute("""DELETE FROM nx.PU_T_SET_INPUT_REQ_DTL
                        WHERE SHEET_NO=? AND IN_CUST_CODE=? AND ITEM_CODE=? AND INPUT_HMS=?
                          AND ISNULL(CONFIRM_FLAG,'0')<>'1'""", sn, cc, doban, hms)
        n = cur.rowcount
        cur.execute("""DELETE FROM nx.PU_T_SET_INPUT_REQ
                        WHERE SHEET_NO=? AND IN_CUST_CODE=? AND ITEM_CODE=? AND INPUT_HMS=?
                          AND ISNULL(CONFIRM_FLAG,'0')<>'1'""", sn, cc, doban, hms)
        nh = cur.rowcount
        nx.commit()
        return {"ok": True, "deleted": n, "head_deleted": nh}
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
        w = ["A.SHEET_NO=?"]; p = [sn]
        if cc.strip():  w.append("A.IN_CUST_CODE=?"); p.append(cc.strip())
        if hms.strip(): w.append("A.INPUT_HMS=?"); p.append(hms.strip())
        cur.execute(f"""SELECT A.INPUT_YMD, A.INPUT_HMS, A.SHEET_NO, A.IN_CUST_CODE,
              ISNULL(c.CUST_DESC,''), A.ITEM_CODE, ISNULL(i1.item_name,''),
              ISNULL(i1.item_spec,''), A.MAT_CODE, ISNULL(i2.item_name,''),
              SUM(A.INPUT_REQ_QTY), MAX(A.USE_QTY), SUM(A.MAT_QTY),
              MAX(ISNULL(A.CONFIRM_FLAG,'0')), MAX(ISNULL(A.INSP_FLAG,'')),
              MAX(ISNULL(A.PLAN_YMD,''))
            FROM nx.PU_T_SET_INPUT_REQ_DTL A WITH(NOLOCK)
            LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=A.IN_CUST_CODE
            LEFT JOIN nx.item i1 WITH(NOLOCK) ON i1.item_code=A.ITEM_CODE
            LEFT JOIN nx.item i2 WITH(NOLOCK) ON i2.item_code=A.MAT_CODE
           WHERE {' AND '.join(w)}
           GROUP BY A.INPUT_YMD, A.INPUT_HMS, A.SHEET_NO, A.IN_CUST_CODE, c.CUST_DESC,
                    A.ITEM_CODE, i1.item_name, i1.item_spec, A.MAT_CODE, i2.item_name
           ORDER BY A.ITEM_CODE, A.MAT_CODE""", *p)
        rows = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            rows.append({"ymd": g(0), "hms": g(1), "sheet_no": g(2), "cc": g(3), "cnm": g(4),
                         "doban": g(5), "dnm": g(6), "dspec": g(7),
                         "jadoban": g(8), "jnm": g(9),
                         "set_qty": float(r[10] or 0), "use_qty": float(r[11] or 0),
                         "mat_qty": float(r[12] or 0), "cf": g(13),
                         "insp": g(14), "plan_ymd": g(15)})
        if not rows:
            raise HTTPException(404, f"출력할 내역이 없습니다. (SET{sn})")
        h = rows[0]
        title = {"stmt": "거 래 명 세 서", "tag": "입 고 태 그", "insp": "출하검사성적서"}[kind]
        return {"ok": True, "kind": kind, "title": title,
                "sheet_no": h["sheet_no"], "ymd": h["ymd"], "hms": h["hms"],
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
    col = "MAT_CODE" if kind == "jadoban" else "ITEM_CODE"
    w = ["1=1"]; p = []
    f6, t6 = _d6(from_ymd), _d6(to_ymd)
    if len(f6) == 6 and len(t6) == 6:
        if f6 > t6: f6, t6 = t6, f6
        w.append("A.INPUT_YMD BETWEEN ? AND ?"); p += [f6, t6]
    cc = str(cust or "").strip()
    if cc:
        w.append("""(A.IN_CUST_CODE=? OR EXISTS(SELECT 1 FROM nx.CM_M_CUST c2 WITH(NOLOCK)
                      WHERE c2.CUST_CODE=A.IN_CUST_CODE AND c2.CUST_DESC LIKE ?))""")
        p += [cc, f"%{cc}%"]
    if q.strip():
        w.append(f"(A.{col} LIKE ? OR EXISTS(SELECT 1 FROM nx.item i2 WITH(NOLOCK)"
                 f" WHERE i2.item_code=A.{col} AND i2.item_name LIKE ?))")
        p += [f"%{q.strip()}%", f"%{q.strip()}%"]
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute(f"""SELECT TOP 400 A.{col} code, MAX(ISNULL(i.item_name,'')) nm
                          FROM nx.PU_T_SET_INPUT_REQ_DTL A WITH(NOLOCK)
                          LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code=A.{col}
                         WHERE {' AND '.join(w)} AND ISNULL(A.{col},'')<>''
                         GROUP BY A.{col} ORDER BY A.{col}""", *p)
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
                         WHERE EXISTS(SELECT 1 FROM nx.PU_T_SET_INPUT_REQ_DTL h WITH(NOLOCK)
                                       WHERE h.IN_CUST_CODE=c.CUST_CODE) {w}
                         ORDER BY c.CUST_DESC""", *p)
        return {"rows": [{"cc": str(a).strip(), "nm": str(b).strip()} for a, b in cur.fetchall()]}
    finally:
        nx.close()
