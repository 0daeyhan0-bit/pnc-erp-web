# -*- coding: utf-8 -*-
"""파트별 생산계획 — 드래그 실적처리 (2026-08-30 신설).

레거시 w_pr_input_260(공정별 생산실적등록)의 '드래그 → 확인(F12)' 을 웹에 이식.
★실적 단위 = **도번**(바코드실적과 동일). BOM 전개·세트차감도 도번 기준.

★파트마스터(nx.PR_M_PROC_GAGONG) 설정으로 동작이 갈린다
   PROD_RESULT_TYPE  'R' = 생산준비재고 → 녹색(키팅완료) 셀만, 준비된 만큼만
                     'W' = 자재창고출고 → 자재창고(Z99990)에서 BOM만큼 바로 차감
                     ''  = 드래그 실적 불가(바코드만)
   BARCODE_FLAG      바코드실적 허용 여부(이 API 와 무관, 독립)

★차감 대상은 바코드실적(520)과 **동일**하다. 위치만 다르다.
   ① 생산실적    nx.PR_T_PROD_DTL
   ② BOM 자재    W=PU_T_MAT_STOCK(Z99990) / R=PU_T_READY_STOCK(파트별 준비재고)
   ③ 자재세트    nx.set_stock_maint(tag 3) + nx.set_output_dtl
   ④ 가공세트    nx.PU_T_SET_STOCK_MAINT_GAGONG(tag P) + nx.PU_T_SET_GAGONG_STOCK
   ⑤ ASSY재고    nx.SA_T_ITEM_STOCK (+)
"""
from datetime import datetime
from fastapi import APIRouter, Query, Body, HTTPException
from common import _nx, _nx_tx, _assert_open, stock_changed

router = APIRouter()


def _part_conf(cur, part):
    """파트마스터의 실적처리방법."""
    cur.execute("""SELECT ISNULL(BARCODE_FLAG,'1'), ISNULL(PROD_RESULT_TYPE,''),
                          ISNULL(GAGONG_PROC_DESC,'')
                     FROM nx.PR_M_PROC_GAGONG WITH(NOLOCK)
                    WHERE GAGONG_PROC_CODE=?""", part)
    r = cur.fetchone()
    if not r:
        return {"ok": False, "bc": "0", "pt": "", "nm": "", "msg": f"파트 '{part}' 가 마스터에 없습니다."}
    return {"ok": True, "bc": str(r[0] or "1").strip(),
            "pt": str(r[1] or "").strip().upper(), "nm": (r[2] or "").strip()}


@router.get("/api/dragprod/conf")
def dragprod_conf(part: str = Query(..., description="파트(GAGONG_PROC_CODE)")):
    """드래그 실적 가능 여부 — 화면이 조건문 파트 선택 시 호출."""
    cn = _nx(); cur = cn.cursor()
    try:
        c = _part_conf(cur, part.strip())
        if not c["ok"]:
            return {"ok": False, "enabled": False, "msg": c["msg"]}
        pt = c["pt"]
        return {"ok": True, "part": part, "part_nm": c["nm"],
                "barcode": c["bc"] == "1", "type": pt,
                "enabled": pt in ("R", "W"),
                "type_nm": {"R": "생산준비재고", "W": "자재창고출고"}.get(pt, ""),
                "msg": "" if pt in ("R", "W")
                       else f"'{c['nm'] or part}' 는 생산실적 방식이 지정되지 않았습니다."
                            " 파트 마스터에서 준비재고/자재창고출고 중 하나를 선택하세요."}
    finally:
        cn.close()


def _bom(cur, item):
    """도번의 BOM 하위 — 실사용분만(제외플래그 제외)."""
    cur.execute("""SELECT b.MAT_CODE, ISNULL(b.USE_QTY,0),
                          ISNULL(b.GAGONG_PROC_CODE,'')
                     FROM nx.pr_m_item_bom b WITH(NOLOCK)
                    WHERE b.ITEM_CODE=? AND ISNULL(b.EXCEPT_FLAG,'0')<>'1'""", item)
    return [(str(a).strip(), float(q or 0), str(g or "").strip())
            for a, q, g in cur.fetchall() if a and float(q or 0) > 0]


@router.post("/api/dragprod/check")
def dragprod_check(payload: dict = Body(...)):
    """실적 가능 여부 사전점검 — 확인 누르기 전 부족분을 보여준다.
       rows: [{part, item, qty}]"""
    rows = payload.get("rows") or []
    if not rows:
        raise HTTPException(400, "선택된 행이 없습니다.")
    cn = _nx(); cur = cn.cursor()
    try:
        out = []
        for r in rows:
            part = str(r.get("part") or "").strip()
            item = str(r.get("item") or "").strip()
            try:
                qty = float(r.get("qty") or 0)
            except Exception:
                qty = 0.0
            if not part or not item or qty <= 0:
                continue
            c = _part_conf(cur, part)
            pt = c["pt"]
            if pt not in ("R", "W"):
                out.append({"item": item, "part": part, "qty": qty, "ok": False,
                            "reason": "생산실적 방식 미지정"})
                continue

            lack = []
            can = qty
            if pt == "R":
                # 준비재고 — 그 파트의 준비된 수량까지만(부분 실적 허용)
                cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_READY_STOCK WITH(NOLOCK)
                                WHERE ITEM_CODE=? AND PROC_GUBUN=?""", item, part)
                rdy = float((cur.fetchone() or [0])[0] or 0)
                if rdy < qty:
                    can = max(rdy, 0.0)
                    lack.append({"mat": "(준비재고)", "need": qty, "have": rdy,
                                 "lack": qty - rdy})
            # BOM 자재 — 두 방식 공통. 없으면 실적 불가
            for mat, use, _g in _bom(cur, item):
                need = use * can
                if need <= 0:
                    continue
                if pt == "W":
                    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK WITH(NOLOCK)
                                    WHERE MAT_CODE=? AND CUST_CODE='Z99990'""", mat)
                else:
                    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PR_T_MAT_STOCK_WH WITH(NOLOCK)
                                    WHERE MAT_CODE=? AND PART_CODE=?""", mat, part)
                have = float((cur.fetchone() or [0])[0] or 0)
                if have < need:
                    lack.append({"mat": mat, "need": need, "have": have,
                                 "lack": need - have})
            out.append({"item": item, "part": part, "qty": qty, "can": can,
                        "type": pt, "ok": (can > 0 and not any(
                            x["mat"] != "(준비재고)" for x in lack)),
                        "lack": lack})
        return {"ok": True, "rows": out}
    finally:
        cn.close()


def _upd(cur, tbl, keys, qty, user, win):
    """재고 UPSERT — 있으면 가산, 없으면 신규."""
    wh = " AND ".join(f"{k}=?" for k, _ in keys)
    vals = [v for _, v in keys]
    cur.execute(f"""UPDATE nx.{tbl} SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                    WHERE {wh}""", qty, user, win, *vals)
    if cur.rowcount == 0:
        cols = ",".join(k for k, _ in keys)
        ph = ",".join("?" * len(keys))
        cur.execute(f"""INSERT INTO nx.{tbl}({cols},STOCK_QTY,
                          UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                        VALUES({ph},?,?,GETDATE(),?)""", *vals, qty, user, win)


@router.post("/api/dragprod/save")
def dragprod_save(payload: dict = Body(...)):
    """★드래그 실적처리 — 도번 단위. 바코드실적(520)과 같은 계정을 태운다.

       payload: {ymd, rows:[{part, item, qty, wo, line}], user}
    """
    # ★실적일자 = 오늘(작업일) 고정. 화면의 기준일자는 계획을 보는 축일 뿐이라
    #   그 값으로 실적을 잡으면 지난 일자에 기록되고, 마감된 일자면 거부된다
    #   (2026-08-30 실측: 기준일 260828 이 넘어와 "일마감된 일자" 실패).
    #   바코드실적(520)도 datetime.now() 기준이라 동일하게 맞춘다.
    ymd = datetime.now().strftime("%y%m%d")
    user = str(payload.get("user") or "웹")[:20]
    win = "w_pr_input_410_drag"
    rows = payload.get("rows") or []
    if not rows:
        raise HTTPException(400, "선택된 행이 없습니다.")

    # prodsheet 의 검증된 로직 재사용 — 세트차감 + 입고처 판정(바코드실적과 동일 규칙)
    try:
        from routers.prodsheet import _apply_set_stock
    except Exception:
        _apply_set_stock = None
    try:
        from routers.prodsheet import _prod_dest
    except Exception:
        _prod_dest = None

    cn = _nx_tx(); cur = cn.cursor()
    try:
        _assert_open(cur, ymd, "MAT", "드래그 생산실적")
        hms = datetime.now().strftime("%H%M%S")
        done = []; skipped = []

        for r in rows:
            part = str(r.get("part") or "").strip()
            item = str(r.get("item") or "").strip()
            wo = str(r.get("wo") or "").strip()
            line = str(r.get("line") or "").strip()
            try:
                qty = float(r.get("qty") or 0)
            except Exception:
                qty = 0.0
            if not part or not item or qty <= 0:
                continue

            c = _part_conf(cur, part)
            pt = c["pt"]
            if pt not in ("R", "W"):
                skipped.append({"item": item, "part": part,
                                "reason": "생산실적 방식 미지정"})
                continue

            # ── 준비재고 방식이면 준비된 만큼으로 clamp(부분 실적 허용)
            if pt == "R":
                cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_READY_STOCK WITH(NOLOCK)
                                WHERE ITEM_CODE=? AND PROC_GUBUN=?""", item, part)
                rdy = float((cur.fetchone() or [0])[0] or 0)
                if rdy <= 0:
                    skipped.append({"item": item, "part": part, "reason": "준비재고 없음"})
                    continue
                if qty > rdy:
                    qty = rdy

            # ── BOM 자재 확인 — 부족하면 그 행은 실적 불가
            boms = _bom(cur, item)
            short = []
            for mat, use, _g in boms:
                need = use * qty
                if pt == "W":
                    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK WITH(NOLOCK)
                                    WHERE MAT_CODE=? AND CUST_CODE='Z99990'""", mat)
                else:
                    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PR_T_MAT_STOCK_WH WITH(NOLOCK)
                                    WHERE MAT_CODE=? AND PART_CODE=?""", mat, part)
                if float((cur.fetchone() or [0])[0] or 0) < need:
                    short.append(mat)
            if short:
                skipped.append({"item": item, "part": part,
                                "reason": "자재 부족: " + ", ".join(short[:4])})
                continue

            # ── ⓪ 입고처 판정 — ★①보다 먼저 한다(2026-09-07).
            #   PR_T_PROD_DTL.STOCK_PART_CODE 에 **재고가 실제로 간 파트**를 적어야 하는데
            #   그 값은 ④의 판정 결과라, 판정을 ① INSERT 앞으로 끌어올렸다.
            #   (종전엔 ④가 ① 뒤에 있어 STOCK_PART_CODE 를 채울 수가 없었다.)
            dk, dp = ("ASSY", None)
            if _prod_dest:
                # 상위품번 = BOM 상위(화면 '상위도번'과 같은 기준)
                cur.execute("""SELECT TOP 1 ITEM_CODE FROM nx.pr_m_item_bom WITH(NOLOCK)
                                WHERE MAT_CODE=? AND ISNULL(EXCEPT_FLAG,'0')<>'1'""", item)
                _r = cur.fetchone()
                upper = str(_r[0] or "").strip() if _r else ""
                dk, dp = _prod_dest(cur, item, upper)

            # ── ① 생산실적
            #   ★STOCK_PART_CODE = 입고처 파트(dp). 실적 파트(PART_CODE)가 아니다.
            #     「생산입출고현황」(live_api._prodinout:943)은 생산실적 입고를 **이 컬럼으로만**
            #     집계한다 — 비어 있으면 그 행은 통째로 빠져 잔량에 재고가 있어도 화면이 0이 된다
            #     (실사용 오류 2026-09-07: AJR32883902-은납 S6 10개가 "결과 없음").
            #     그리고 넣을 값은 **재고가 간 곳**이어야 잔액테이블과 축이 맞는다.
            #     실적 파트(S10)를 넣으면 재고는 S6 에 있는데 화면은 S10 에 유령재고를 만든다.
            #     ※ASSY/자재창고 입고는 생산창고가 아니므로 비워 둔다 — 각각 SA_T_ITEM_STOCK,
            #       PU_T_STOCK_MAINT 로 잡히고, 여기 채우면 이중계상된다.
            _spc = dp if (dk == "PART" and dp) else None
            cur.execute("""INSERT INTO nx.PR_T_PROD_DTL
                   (WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,PROD_YMD,PROD_HMS,LINE_NO,
                    PROD_QTY,PROD_USER_ID,WORK_CODE,PART_CODE,STOCK_PART_CODE,
                    PROD_TAG,FINISH_FLAG,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                   VALUES(?,'',?,?,?,?,?,?,'',?,?,'','0',?,GETDATE(),?)""",
                        wo, item, ymd, hms, line, int(qty), user, part, _spc, user, win)
            # ── ①-b 공정별 생산실적 (PR_T_PROD_DTL_PROC) ★2026-09-07 신설
            #   왜 — 「파트별 생산실적현황」(prod.py:154)은 **_PROC 을 읽는다**(PROD_DTL 아님.
            #   PROD_DTL 로 읽으면 용접 S5 가 누락된다 — prod.py:121 경위).
            #   레거시 520 은 두 테이블에 다 쓰는데 드래그 실적은 PROD_DTL 에만 써서
            #   **실적을 잡아도 실적현황이 0건**이었다(실사용 오류 2026-09-07).
            #   ★PROC_CODE = 파트코드 — 드래그 실적은 파트 단위로 잡는 기능이고
            #     실적현황도 파트별 집계 화면이라 축이 맞는다(공정 세분은 520 이 한다).
            #   ★PK(WO+SWO+ITEM+YMD+HMS+WORK_CODE+PROC_CODE+S_WORK_CODE) 충돌 시 **누적**한다 —
            #     바코드 실적(prodsheet.py:1341-1355)과 같은 방식. 무시하면 같은 초에 두 건이
            #     들어올 때 수량이 통째로 빠진다.
            _pk = (wo, item, ymd, hms, part)
            cur.execute("""SELECT COUNT(*) FROM nx.PR_T_PROD_DTL_PROC
                            WHERE WORK_ORDER=? AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                              AND PROD_YMD=? AND PROD_HMS=? AND ISNULL(WORK_CODE,'')=''
                              AND ISNULL(PROC_CODE,'')=? AND ISNULL(S_WORK_CODE,0)=0""", *_pk)
            if int(cur.fetchone()[0] or 0) == 0:
                cur.execute("""INSERT INTO nx.PR_T_PROD_DTL_PROC
                                 (WORK_ORDER,SPLIT_WORK_ORDER,ITEM_CODE,PROD_YMD,PROD_HMS,
                                  WORK_CODE,PROC_CODE,S_WORK_CODE,LINE_NO,PROD_QTY,PROD_USER_ID,
                                  PROD_TAG,FINISH_FLAG,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                               VALUES(?,'',?,?,?,'',?,0,?,?,?,'','0',?,GETDATE(),?)""",
                            wo, item, ymd, hms, part, line, int(qty), user, user, win)
            else:
                cur.execute("""UPDATE nx.PR_T_PROD_DTL_PROC SET PROD_QTY=ISNULL(PROD_QTY,0)+?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                WHERE WORK_ORDER=? AND SPLIT_WORK_ORDER='' AND ITEM_CODE=?
                                  AND PROD_YMD=? AND PROD_HMS=? AND ISNULL(WORK_CODE,'')=''
                                  AND ISNULL(PROC_CODE,'')=? AND ISNULL(S_WORK_CODE,0)=0""",
                            int(qty), user, win, *_pk)

            # ── ② BOM 자재 차감 (위치만 다름)
            for mat, use, gpc in boms:
                d = -(use * qty)
                if pt == "W":
                    _upd(cur, "PU_T_MAT_STOCK",
                         [("MAT_CODE", mat), ("CUST_CODE", "Z99990")], d, user, win)
                    _upd(cur, "PU_T_MAT_STOCK_WH",
                         [("MAT_CODE", mat), ("CUST_CODE", "Z99990"),
                          ("GAGONG_PROC_CODE", gpc or "IS0001")], d, user, win)
                else:
                    _upd(cur, "PR_T_MAT_STOCK_WH",
                         [("MAT_CODE", mat), ("PART_CODE", part)], d, user, win)
                cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT
                       (MAINT_YMD,MAINT_SEQ,MAINT_TAG,PART_CODE,MAT_CODE,ITEM_CODE,
                        MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                        UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                       SELECT ?,ISNULL(MAX(MAINT_SEQ),29999)+1,'4',?,?,?,?,0,0,?,
                              ?,GETDATE(),?,?,GETDATE(),?
                         FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=30000""",
                            ymd, part, mat, item, d,
                            ("드래그실적(%s)" % ("자재창고" if pt == "W" else "준비재고")),
                            user, win, user, win, ymd)

            # ── ③ 준비재고 차감(R 방식)
            if pt == "R":
                _upd(cur, "PU_T_READY_STOCK",
                     [("ITEM_CODE", item), ("CUST_CODE", "Z99990"),
                      ("PROC_GUBUN", part)], -qty, user, win)
                cur.execute("""INSERT INTO nx.PU_T_READY_STOCK_MAINT
                       (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,PROC_GUBUN,
                        WORK_ORDER,SPLIT_WORK_ORDER,PLAN_YMD,MAINT_QTY,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                        UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                       SELECT ?,ISNULL(MAX(MAINT_SEQ),0)+1,'A','Z99990',?,?,?,'','',?,
                              ?,GETDATE(),?,?,GETDATE(),?
                         FROM nx.PU_T_READY_STOCK_MAINT WHERE MAINT_YMD=?""",
                            ymd, item, part, wo, -qty, user, win, user, win, ymd)

            # ── ④ 완성품 입고 — ★입고처는 바코드실적(520)과 **동일한 판정**을 쓴다.
            #   무조건 영업창고(ASSY)에 넣으면 안 된다. -SUB 서브품이 ASSY로 새어나가
            #   화면의 ASSY재고만 늘고 정작 상위 실적 때 차감할 재고가 없다
            #   (2026-08-30 실측: AJJ76559005-SUB 3개가 SA_T_ITEM_STOCK 으로 잘못 들어감).
            #     상위가 업체   → 자재창고 Z99990   (화면 '자재재고')
            #     상위가 사내   → 상위 파트 생산창고 (화면 '생산재고')
            #     상위 없음/자기자신 → 영업창고 ASSY (화면 'ASSY재고')
            #   ★판정은 ⓪에서 이미 끝났다(dk·dp 재사용) — 여기서 다시 조회하지 않는다.
            dest = "ASSY"
            if _prod_dest:
                if dk == "PART" and dp:
                    # ★잔액만 갱신하고 PR_T_STOCK_MAINT_MAT 원장행은 넣지 않는다.
                    #   이력은 ①의 PR_T_PROD_DTL(STOCK_PART_CODE)로 남는다 —
                    #   원장행을 또 넣으면 「생산입출고현황」이 이중계상하고,
                    #   그 화면은 tag='4' 를 '생산사용(출고)'로 보아 부호를 뒤집으므로
                    #   입고를 tag='4' 로 넣으면 재고가 되레 늘어난다
                    #   (prodsheet.py:1456-1462 와 같은 규칙·같은 사고이력).
                    _upd(cur, "PR_T_MAT_STOCK_WH",
                         [("MAT_CODE", item), ("PART_CODE", dp)], qty, user, win)
                    dest = "생산창고(%s)" % dp
                elif dk == "MAT":
                    # 자재창고 — 잔액 2종 + 원장(PU_T_STOCK_MAINT tag='P') 520 동일.
                    # ★파트코드 = IS0001 고정. 실적 파트(S8 등)를 넣으면 안 된다.
                    #   자재창고에도 파트코드가 둘 있지만(IS0001 자재창고 / IS0002 부자재창고),
                    #   생산실적 입고는 IS0001 뿐이다 — 원장 실측 tag='P' 10,261건 전부 IS0001,
                    #   IS0002 는 총 4건이고 전부 수동조정(w_pu_stock_057)·준비재고 창구로
                    #   소모성 부자재(미니호스·압력계)용이라 생산실적 경로와 무관.
                    #   (파트별 재고를 나눠 갖는 것은 생산창고 PR_T_MAT_STOCK_WH 쪽이다)
                    #   520 은 전표 STOCK_GPC 를 쓰고 없으면 IS0001 인데, 드래그 실적은
                    #   전표가 없으므로 항상 IS0001. 이후 사급출고(w_pu_output_015)가 이 버킷에서 뺀다.
                    gpc_in = "IS0001"
                    _upd(cur, "PU_T_MAT_STOCK",
                         [("MAT_CODE", item), ("CUST_CODE", "Z99990")], qty, user, win)
                    _upd(cur, "PU_T_MAT_STOCK_WH",
                         [("MAT_CODE", item), ("CUST_CODE", "Z99990"),
                          ("GAGONG_PROC_CODE", gpc_in)], qty, user, win)
                    cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                           (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,WORK_CODE,MAT_CODE,
                            MAINT_QTY,REF_MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,
                            ITEM_CODE,OUT_WH_GUBUN,GAGONG_PROC_CODE,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                            UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           SELECT ?,ISNULL(MAX(MAINT_SEQ),19999)+1,'P','','',?,?,0,0,0,
                                  '생산완료 후 자재창고 입고','','',?,?,GETDATE(),?,?,GETDATE(),?
                             FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""",
                                ymd, item, int(qty), gpc_in, user, win, user, win, ymd)
                    dest = "자재창고"
                else:
                    _upd(cur, "SA_T_ITEM_STOCK", [("ITEM_CODE", item)], qty, user, win)
                    dest = "ASSY"
            else:
                _upd(cur, "SA_T_ITEM_STOCK", [("ITEM_CODE", item)], qty, user, win)
                dest = "ASSY"

            # ── ⑤ 세트재고 2종 — 바코드실적(520)과 동일
            sets = []
            if _apply_set_stock:
                try:
                    sets = _apply_set_stock(cur, item, qty, wo or "DRAG",
                                            user, win, ymd, hms)
                except Exception:
                    sets = []

            # ★key = 화면 셀 식별자(gpc|item|wo|ymd). 화면이 이걸로 그 셀만 부분갱신한다
            #   (전체 재조회하면 8,500행을 다시 그려 스크롤·툴바가 리셋된다).
            done.append({"key": str(r.get("key") or ""),
                         "item": item, "part": part, "qty": qty, "type": pt,
                         "bom": len(boms), "sets": len(sets), "dest": dest})

        cn.commit()
        stock_changed()
        return {"ok": True, "ymd": ymd, "done": len(done),
                "skipped": len(skipped), "rows": done, "skips": skipped}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        raise HTTPException(500, str(e)[:300])
    finally:
        cn.close()


# ============ 드래그 실적 취소(원복) — 2026-09-07 신설 ============
@router.post("/api/dragprod/cancel")
def dragprod_cancel(payload: dict = Body(...)):
    """드래그 실적 취소 — save 가 한 일을 **부호 반대로** 되돌린다.

       body {rows:[{item, part, ymd?, qty?}], user?}
         · ymd 생략 = 오늘 · qty 생략 = 그 날 그 파트에 잡힌 전량

       ★save 와 짝이 맞아야 한다(6곳). 하나라도 빠지면 재고가 어긋난다 —
         ① PR_T_PROD_DTL          실적행 삭제
         ①-b PR_T_PROD_DTL_PROC   공정별 실적 차감(0 이면 삭제) ← 실적현황이 읽는 곳
         ② BOM 자재               W=PU_T_MAT_STOCK / R=PR_T_MAT_STOCK_WH 복원(+)
         ③ 준비재고(R)            PU_T_READY_STOCK 복원(+)
         ④ 완성품 입고            입고처에서 차감(−) — save 와 같은 _prod_dest 판정
         ⑤ 세트재고               (자동복원 대상 아님 — 아래 주석)

       ★세트재고(⑤)는 되돌리지 않는다. _apply_set_stock 이 만든 파생은 역함수가 없고
         (세트출고 이력·가공세트가 얽힌다) 잘못 되돌리면 이중차감이 난다.
         세트가 걸린 실적은 세트입고 취소(/api/setstock/cancel)로 별도 처리한다.
    """
    rows = payload.get("rows", []) or []
    user = (str(payload.get("user") or "웹")).strip()[:20]
    win = "w_pr_input_410_drag"
    if not rows:
        return {"ok": False, "detail": "취소할 행이 없습니다."}

    # ★save 와 **같은 판정**을 써야 엉뚱한 창고에서 빠지지 않는다 —
    #   save 는 함수 안에서 import 하는데 취소는 빠뜨려 NameError 로 500 이 났다
    #   (2026-09-07 롤백 테스트에서 검출. 실사용이었으면 취소가 통째로 실패).
    try:
        from routers.prodsheet import _prod_dest
    except Exception:
        _prod_dest = None

    cn = _nx_tx(); cur = cn.cursor()
    done, skipped = [], []
    try:
        for r in rows:
            item = str(r.get("item") or "").strip()
            part = str(r.get("part") or "").strip()
            # 일자 = YYMMDD 6자리. 화면이 YYYY-MM-DD 로 줄 수도 있어 숫자만 추려 뒤 6자리를 쓴다.
            _y = "".join(ch for ch in str(r.get("ymd") or "") if ch.isdigit())
            ymd = (_y[-6:] if len(_y) >= 6 else "") or datetime.now().strftime("%y%m%d")
            if not item or not part:
                skipped.append({"item": item, "part": part, "reason": "도번·파트 필요"}); continue
            _assert_open(cur, ymd, "PRD", "드래그 실적 취소")

            # 취소할 수량 = 지정값 또는 그 날 그 파트에 잡힌 전량(드래그 실적분만)
            cur.execute("""SELECT ISNULL(SUM(PROD_QTY),0) FROM nx.PR_T_PROD_DTL
                            WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PART_CODE,'')=?
                              AND ISNULL(UPDATE_WINDOW,'')=?""", item, ymd, part, win)
            have = float(cur.fetchone()[0] or 0)
            qty = float(r.get("qty") or 0) or have
            if have <= 0:
                skipped.append({"item": item, "part": part, "reason": "취소할 드래그 실적이 없습니다"}); continue
            if qty > have:
                skipped.append({"item": item, "part": part,
                                "reason": f"취소수량 {qty:g} > 실적 {have:g}"}); continue

            # ① 실적행 — 전량이면 삭제, 부분이면 최신 행부터 차례로 깎는다.
            #   ★종전 UPDATE TOP(1) ... AND PROD_QTY>=qty 는 부분취소에 구멍이 있었다:
            #     행이 여러 개고 각 행 수량이 취소량보다 작으면(2+2 에서 3 취소)
            #     조건에 걸리는 행이 없어 **아무것도 안 빠진다**(자재·재고만 되돌아가 어긋남).
            #   ①-b 와 같은 방식으로 통일한다.
            if abs(qty - have) < 1e-9:
                cur.execute("""DELETE FROM nx.PR_T_PROD_DTL
                                WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PART_CODE,'')=?
                                  AND ISNULL(UPDATE_WINDOW,'')=?""", item, ymd, part, win)
            else:
                _left = int(qty)
                cur.execute("""SELECT WORK_ORDER, SPLIT_WORK_ORDER, PROD_HMS, ISNULL(PROD_QTY,0)
                                 FROM nx.PR_T_PROD_DTL
                                WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PART_CODE,'')=?
                                  AND ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(PROD_QTY,0)>0
                                ORDER BY PROD_HMS DESC""", item, ymd, part, win)
                for _wo, _swo, _hms, _q in cur.fetchall():
                    if _left <= 0:
                        break
                    _cut = min(_left, int(_q or 0))
                    cur.execute("""UPDATE nx.PR_T_PROD_DTL SET PROD_QTY=ISNULL(PROD_QTY,0)-?,
                                      UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE()
                                    WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PART_CODE,'')=?
                                      AND ISNULL(UPDATE_WINDOW,'')=?
                                      AND ISNULL(WORK_ORDER,'')=ISNULL(?,'')
                                      AND ISNULL(SPLIT_WORK_ORDER,'')=ISNULL(?,'')
                                      AND PROD_HMS=?""",
                                _cut, user, item, ymd, part, win, _wo, _swo, _hms)
                    _left -= _cut
                cur.execute("""DELETE FROM nx.PR_T_PROD_DTL
                                WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PART_CODE,'')=?
                                  AND ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(PROD_QTY,0)<=0""",
                            item, ymd, part, win)

            # ①-b 공정별 실적(실적현황 원천) — 총량에서 정확히 qty 만 뺀다.
            #   ★행마다 빼면 안 된다(2026-09-07 롤백 테스트에서 검출):
            #     같은 (도번·일자·파트)에 행이 2개면(백필분 + 신규분) 조건에 둘 다 걸려
            #     각각 qty 를 빼 **2배가 차감**됐다(실측 13 → 7, 정답 10).
            #     ①은 UPDATE TOP(1) 로 막혀 있는데 ①-b 만 빠져 있었다.
            #   → 최신 행부터 차례로 깎아 합계가 qty 만큼만 줄게 한다.
            _left = int(qty)
            cur.execute("""SELECT WORK_ORDER, SPLIT_WORK_ORDER, PROD_HMS, S_WORK_CODE,
                                  ISNULL(PROD_QTY,0)
                             FROM nx.PR_T_PROD_DTL_PROC
                            WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PROC_CODE,'')=?
                              AND ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(PROD_QTY,0)>0
                            ORDER BY PROD_HMS DESC""", item, ymd, part, win)
            for _wo, _swo, _hms, _sw, _q in cur.fetchall():
                if _left <= 0:
                    break
                _cut = min(_left, int(_q or 0))
                cur.execute("""UPDATE nx.PR_T_PROD_DTL_PROC SET PROD_QTY=ISNULL(PROD_QTY,0)-?,
                                  UPDATE_USER_ID=?, UPDATE_DATETIME=GETDATE(), UPDATE_WINDOW=?
                                WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PROC_CODE,'')=?
                                  AND ISNULL(WORK_ORDER,'')=ISNULL(?,'')
                                  AND ISNULL(SPLIT_WORK_ORDER,'')=ISNULL(?,'')
                                  AND PROD_HMS=? AND ISNULL(S_WORK_CODE,0)=ISNULL(?,0)""",
                            _cut, user, win, item, ymd, part, _wo, _swo, _hms, _sw)
                _left -= _cut
            cur.execute("""DELETE FROM nx.PR_T_PROD_DTL_PROC
                            WHERE ITEM_CODE=? AND PROD_YMD=? AND ISNULL(PROC_CODE,'')=?
                              AND ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(PROD_QTY,0)<=0""",
                        item, ymd, part, win)

            # 실적처리방법(W/R) — ★save 와 **같은 함수**를 쓴다.
            #   직접 SELECT 하면 _part_conf 의 .upper() 가 빠져 소문자 'r' 일 때
            #   준비재고 복원(③)이 통째로 건너뛰어진다. 취소는 등록의 정확한 역이어야 한다.
            pt = _part_conf(cur, part)["pt"]

            # ② BOM 자재 복원(+)
            # ★save 와 같은 _bom() 을 쓴다 — 없는 이름(_bom_of)이라 NameError 였다.
            #   BOM 소스가 다르면 되돌리는 자재가 달라져 재고가 어긋난다.
            boms = _bom(cur, item)
            for mat, use, gpc in boms:
                d = use * qty
                if pt == "W":
                    _upd(cur, "PU_T_MAT_STOCK", [("MAT_CODE", mat), ("CUST_CODE", "Z99990")], d, user, win)
                    _upd(cur, "PU_T_MAT_STOCK_WH",
                         [("MAT_CODE", mat), ("CUST_CODE", "Z99990"),
                          ("GAGONG_PROC_CODE", gpc or "IS0001")], d, user, win)
                else:
                    _upd(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", mat), ("PART_CODE", part)], d, user, win)
                cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT
                       (MAINT_YMD,MAINT_SEQ,MAINT_TAG,PART_CODE,MAT_CODE,ITEM_CODE,
                        MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                        UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                       SELECT ?,ISNULL(MAX(MAINT_SEQ),29999)+1,'4',?,?,?,?,0,0,?,
                              ?,GETDATE(),?,?,GETDATE(),?
                         FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=30000""",
                            ymd, part, mat, item, d, "드래그실적 취소(복원)",
                            user, win, user, win, ymd)

            # ③ 준비재고 복원(R) — 잔액 + ★원장행까지 save 와 대칭으로 되돌린다.
            #   save 는 PU_T_READY_STOCK_MAINT 에 −qty 를 남기므로, 취소는 +qty 를 남긴다.
            #   잔액만 되돌리면 준비재고 이력이 "빠진 적만 있고 돌아온 적은 없는" 상태가 된다.
            if pt == "R":
                _upd(cur, "PU_T_READY_STOCK",
                     [("ITEM_CODE", item), ("CUST_CODE", "Z99990"), ("PROC_GUBUN", part)],
                     qty, user, win)
                cur.execute("""INSERT INTO nx.PU_T_READY_STOCK_MAINT
                       (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,ITEM_CODE,PROC_GUBUN,
                        WORK_ORDER,SPLIT_WORK_ORDER,PLAN_YMD,MAINT_QTY,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                        UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                       SELECT ?,ISNULL(MAX(MAINT_SEQ),0)+1,'A','Z99990',?,?,'','','',?,
                              ?,GETDATE(),?,?,GETDATE(),?
                         FROM nx.PU_T_READY_STOCK_MAINT WHERE MAINT_YMD=?""",
                            ymd, item, part, qty, user, win, user, win, ymd)

            # ④ 완성품 입고 취소(−) — save 와 **같은 판정**이어야 엉뚱한 창고에서 빠지지 않는다
            dest = "ASSY"
            if _prod_dest:
                cur.execute("""SELECT TOP 1 ITEM_CODE FROM nx.pr_m_item_bom WITH(NOLOCK)
                                WHERE MAT_CODE=? AND ISNULL(EXCEPT_FLAG,'0')<>'1'""", item)
                _r2 = cur.fetchone()
                upper = str(_r2[0] or "").strip() if _r2 else ""
                dk, dp = _prod_dest(cur, item, upper)
                if dk == "PART" and dp:
                    _upd(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", item), ("PART_CODE", dp)],
                         -qty, user, win)
                    dest = "생산창고(%s)" % dp
                elif dk == "MAT":
                    _upd(cur, "PU_T_MAT_STOCK", [("MAT_CODE", item), ("CUST_CODE", "Z99990")],
                         -qty, user, win)
                    _upd(cur, "PU_T_MAT_STOCK_WH",
                         [("MAT_CODE", item), ("CUST_CODE", "Z99990"),
                          ("GAGONG_PROC_CODE", "IS0001")], -qty, user, win)
                    dest = "자재창고"
                else:
                    _upd(cur, "SA_T_ITEM_STOCK", [("ITEM_CODE", item)], -qty, user, win)
            else:
                _upd(cur, "SA_T_ITEM_STOCK", [("ITEM_CODE", item)], -qty, user, win)

            done.append({"item": item, "part": part, "qty": qty, "type": pt,
                         "bom": len(boms), "dest": dest})
        cn.commit()
        stock_changed()
        return {"ok": True, "done": len(done), "skipped": len(skipped),
                "rows": done, "skips": skipped}
    except HTTPException:
        try: cn.rollback()
        except Exception: pass
        raise
    except Exception as e:
        try: cn.rollback()
        except Exception: pass
        raise HTTPException(500, str(e)[:300])
    finally:
        cn.close()
