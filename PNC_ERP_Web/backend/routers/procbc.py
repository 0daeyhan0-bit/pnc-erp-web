# -*- coding: utf-8 -*-
"""procbc 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 가공바코드실적처리 (w_pr_input_018) — 스캔조회 + 실적등록/취소 =================
# ★레거시 018 원본 확보(2026-08-20, pr_prod_01.pbl 바이너리 직독) → 재고흐름 4갈래 이식.
#   ① 생산재고   PR_T_MAT_STOCK   (CUST_CODE='Z99990')        +양품
#   ② 가공창고   PR_T_MAT_STOCK_WH(PART_CODE='P0001')         +양품
#   ③ 원소재     PR_T_MAT_STOCK_WH(P0001, 표준원소재) +
#                PR_T_STOCK_MAINT_MAT(TAG='4') UPSERT          -(양품+불량)×단중
#   ④ 하위자재   PU_T_MAT_STOCK / PU_T_MAT_STOCK_WH(Z99990) +
#                PU_T_STOCK_MAINT(TAG='4')                     -BOM소요×양품
#   전표 PR_T_INDI_CUTTING: PROD_QTY 누적 + PROD_FLAG='1', 실적이력 PU_T_CUT_DTL 1건.
#   취소 = 전부 역부호(레거시 동일: 원본 삭제 아닌 음수 역분개 추가).
#   ★쓰기는 전부 nx(PARTNER_ERP_TEST3). 라이브는 조회만(§1 절대규칙).
WH_CUST = 'Z99990'      # 자재창고 거래처버킷
GAGONG_PART = 'P0001'   # 완료후 입고 = 생산 가공창고(레거시 하드코딩)

def _bc_box(barcode):
    """바코드 → box_no. 접두어(CT/GP/가공) 무시, 뒤 숫자 추출."""
    import re
    m = re.search(r'(\d+)\s*$', str(barcode if barcode is not None else '').strip())
    return int(m.group(1)) if m else None

def _bc_ctx(cur, box):
    """전표 1건의 실적처리 컨텍스트(규격·단중·표준원소재·하위BOM) 조회."""
    cur.execute("""SELECT ISNULL(ic.ASSY_ITEM_CODE,''), ISNULL(ic.MAT_CODE,''), ISNULL(ic.ITEM_CODE,''),
                          ISNULL(ic.PLAN_QTY,0), ISNULL(ic.PROD_QTY,0), ISNULL(ic.PROD_FLAG,'0'),
                          ISNULL(ic.WH_GAGONG_PROC_CODE,''), ISNULL(ic.LINE_NO,''),
                          ISNULL(ic.MIX_GAGONG,0), ISNULL(ic.DEL_FLAG,'0')
                     FROM nx.PR_T_INDI_CUTTING ic WHERE ic.BOX_NO=?""", box)
    r = cur.fetchone()
    if not r:
        return None
    c = {"assy": r[0], "mat": r[1], "item": r[2], "plan_qty": int(r[3] or 0),
         "prod_qty": int(r[4] or 0), "prod_flag": r[5], "wh": r[6], "line_no": r[7],
         "mix": int(r[8] or 0), "del_flag": r[9]}
    # 자도번 규격/단중 + 작업처
    cur.execute("""SELECT ISNULL(diam,0), ISNULL(thick,0), ISNULL(ITEM_WEIGHT,0),
                          ISNULL(METAL_GUBUN,''), ISNULL(PIPE_KIND,''), ISNULL(ITEM_PIPE_MATERIAL,''),
                          ISNULL(WORK_CODE,''), ISNULL(in_cust,''), ISNULL(item_name,'')
                     FROM nx.item WHERE ITEM_CODE=?""", c["mat"])
    m = cur.fetchone()
    if m:
        c.update({"diam": float(m[0] or 0), "thick": float(m[1] or 0), "weight": float(m[2] or 0),
                  "metal": m[3], "pipe_kind": m[4], "pipe_mat": m[5],
                  "mat_work": m[6], "mat_cust": m[7], "matnm": m[8]})
    else:
        c.update({"diam": 0, "thick": 0, "weight": 0, "metal": "", "pipe_kind": "",
                  "pipe_mat": "", "mat_work": "", "mat_cust": "", "matnm": ""})
    for k, code in (("item", c["item"]), ("assy", c["assy"])):
        cur.execute("SELECT ISNULL(WORK_CODE,''), ISNULL(in_cust,'') FROM nx.item WHERE ITEM_CODE=?", code)
        w = cur.fetchone()
        c[k + "_work"], c[k + "_cust"] = (w[0], w[1]) if w else ("", "")
    # 표준원소재(규격 동일). 레거시: PIPE_KIND=isnull(B.PIPE_KIND,'1')
    c["won"] = None
    if c["weight"]:
        cur.execute("""SELECT TOP 1 ITEM_CODE FROM nx.item
                        WHERE STD_WON_MAT_FLAG='1' AND diam=? AND thick=?
                          AND METAL_GUBUN=? AND PIPE_KIND=? AND ITEM_PIPE_MATERIAL=?""",
                    c["diam"], c["thick"], c["metal"], (c["pipe_kind"] or '1'), c["pipe_mat"])
        w = cur.fetchone()
        if w:
            c["won"] = w[0]
    c["bom"] = _bc_bom(cur, c["mat"])
    return c

def _bc_bom(cur, parent, mult=1.0, depth=0, acc=None):
    """하위자재 전개(dw_6 = dw_pr_input_028_5) — 실측 규칙:
       · EXCEPT_FLAG='1' / SET_EXCEPT_FLAG='1' 행은 제외
       · VIR_ITEM_FLAG='1'(가상도번)은 자신을 차감하지 않고 그 자식을 USE_QTY 배로 전개
       예) AAA31179501 → ACJ75119301(가상,USE2) → PNC-EL-AA-00-06(USE2) = 4/개
       실측대조: 실적88 → -352(=88*2*2), 나머지 -176(=88*1*2). 일치."""
    if acc is None:
        acc = []
    if depth > 5:
        return acc
    cur.execute("""SELECT b.MAT_CODE, ISNULL(b.USE_QTY,0), ISNULL(b.IN_GAGONG_PROC_CODE,''),
                          ISNULL(b.VIR_ITEM_FLAG,'0')
                     FROM nx.PR_M_ITEM_BOM b
                    WHERE b.ITEM_CODE=? AND ISNULL(b.EXCEPT_FLAG,'0')<>'1'
                      AND ISNULL(b.SET_EXCEPT_FLAG,'0')<>'1'""", parent)
    for mat, use, gpc, vir in cur.fetchall():
        use = float(use or 0)
        if use <= 0:
            continue
        if str(vir) == '1':                       # 가상도번 = 실물 아님 → 한 단계 더
            _bc_bom(cur, mat, mult * use, depth + 1, acc)
        else:
            acc.append((mat, use * mult, gpc or GAGONG_PART))
    return acc

def _upd_stock(cur, table, keys, qty, user, win):
    """재고 UPSERT(+qty). keys=[(컬럼,값)...]. 레거시 f_*_set_mat_stock(_wh) 대응."""
    where = " AND ".join("%s=?" % k for k, _ in keys)
    vals = [v for _, v in keys]
    cur.execute("UPDATE nx.%s SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?, UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(), UPDATE_WINDOW=? WHERE %s"
                % (table, where), qty, user, win, *vals)
    if cur.rowcount == 0:
        cols = ",".join(k for k, _ in keys)
        qs = ",".join("?" for _ in keys)
        cur.execute("INSERT INTO nx.%s(%s,STOCK_QTY,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW) VALUES(%s,?,?,getdate(),?)"
                    % (table, cols, qs), *(vals + [qty, user, win]))

def _stock_of(cur, table, keys):
    where = " AND ".join("%s=?" % k for k, _ in keys)
    cur.execute("SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.%s WITH(NOLOCK) WHERE %s" % (table, where),
                *[v for _, v in keys])
    r = cur.fetchone()
    return float(r[0] or 0) if r else 0.0

@router.get("/api/gagong/barcode/scan")
def gagong_bc_scan(barcode: str = Query("")):
    """바코드 스캔 → 전표(BOX_NO) 정보 조회. 1회=조회, 2회=등록/취소는 프론트가 판단."""
    box = _bc_box(barcode)
    if not box:
        return {"ok": False, "msg": "바코드 형식 오류(숫자 없음)"}
    cn = _nx(); cur = cn.cursor()
    try:
        c = _bc_ctx(cur, box)
        if not c:
            return {"ok": False, "msg": f"전표(바코드 {box})가 존재하지 않습니다."}
        if c["del_flag"] == '1':
            return {"ok": False, "msg": "해당 가공간판은 삭제처리 되었습니다."}
        cur.execute("SELECT ISNULL(SUM(CAST(ISNULL(ERROR_QTY,0) AS int)),0), COUNT(*) FROM nx.QA_T_ERROR WITH(NOLOCK) WHERE BOX_NO=?", box)
        er = cur.fetchone()
        cur.execute("""SELECT ISNULL(SUM(CUT_QTY),0), ISNULL(SUM(ERR_QTY),0)
                         FROM nx.PU_T_CUT_DTL WITH(NOLOCK) WHERE BOX_NO=?""", box)
        cd = cur.fetchone()
        done = c["prod_flag"] == '1'
        # 레거시: 실적있으면 prod_qty, 없으면 plan_qty 를 수량칸 기본값으로
        return {"ok": True, "box_no": box, "assy": c["assy"], "item": c["item"],
                "mat": c["mat"], "matnm": c["matnm"], "plan_qty": c["plan_qty"],
                "prod_qty": c["prod_qty"], "prod_flag": c["prod_flag"], "done": done,
                "wh": c["wh"] or GAGONG_PART, "won": c["won"], "weight": c["weight"],
                "diam": c["diam"], "thick": c["thick"], "bom_cnt": len(c["bom"]),
                "err_qty": int(er[0] or 0), "err_cnt": int(er[1] or 0),
                "cut_qty": int(cd[0] or 0), "cut_err": int(cd[1] or 0),
                "default_qty": (c["prod_qty"] if c["prod_qty"] > 0 else c["plan_qty"]),
                "already": done,
                "msg": ("이미 실적완료 — 재스캔 시 취소" if done else "")}
    finally:
        cn.close()

def _apply(cur, c, box, good, bad, sign, user, ymd, win):
    """재고 4갈래 이동. sign=+1 등록 / -1 취소. 반환=실제 반영내역."""
    moved = []
    qty = good * sign
    wgt = c["weight"] * (good + bad) * sign      # 원소재 소모중량(양품+불량)
    part = GAGONG_PART
    # ① 생산재고
    _upd_stock(cur, "PR_T_MAT_STOCK", [("CUST_CODE", WH_CUST), ("WORK_CODE", ''), ("MAT_CODE", c["mat"])],
               qty, user, win)
    moved.append(("생산재고", c["mat"], qty))
    # ② 가공창고
    _upd_stock(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", c["mat"]), ("PART_CODE", part)], qty, user, win)
    moved.append(("가공창고", c["mat"], qty))
    # ③ 원소재 차감(중량)
    if c["won"] and wgt:
        cur.execute("""SELECT MAINT_SEQ FROM nx.PR_T_STOCK_MAINT_MAT
                        WHERE MAINT_YMD=? AND MAINT_TAG='4' AND PART_CODE=? AND ITEM_CODE=? AND MAT_CODE=?""",
                    ymd, part, c["mat"], c["won"])
        ex = cur.fetchone()
        if ex:
            cur.execute("""UPDATE nx.PR_T_STOCK_MAINT_MAT
                              SET MAINT_QTY=ISNULL(MAINT_QTY,0)+?, UPDATE_USER_ID=?, UPDATE_DATETIME=getdate(),
                                  UPDATE_WINDOW=?
                            WHERE MAINT_YMD=? AND MAINT_SEQ=?""", -wgt, user, win, ymd, ex[0])
        else:
            cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PR_T_STOCK_MAINT_MAT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
            seq = int(cur.fetchone()[0] or 1)
            cur.execute("""INSERT INTO nx.PR_T_STOCK_MAINT_MAT
                           (MAINT_YMD,MAINT_SEQ,MAINT_TAG,PART_CODE,WORK_CODE,PROD_WORK_CODE,ITEM_CODE,MAT_CODE,
                            MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,BOX_NO,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           VALUES(?,?,'4',?,'','',?,?,?,0,0,'',?,?,getdate(),?,?,getdate(),?)""",
                        ymd, seq, part, c["mat"], c["won"], -wgt, box, user, win, user, win)
        _upd_stock(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", c["won"]), ("PART_CODE", part)], -wgt, user, win)
        moved.append(("원소재", c["won"], -wgt))
    # ④ 하위자재 차감
    if c["bom"] and good:
        cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),19999) FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD=? AND MAINT_SEQ>=20000", ymd)
        seq = int(cur.fetchone()[0] or 19999)
        for child, use, cgpc in c["bom"]:
            seq += 1
            d = -(use * good) * sign
            cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                           (MAINT_YMD,MAINT_SEQ,WH_CUST_CODE,CUST_CODE,GAGONG_PROC_CODE,MAINT_TAG,MAT_CODE,
                            MAINT_QTY,REF_MAINT_QTY,MAINT_COST,MAINT_AMT,REMARKS,BOX_NO,ITEM_CODE,
                            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                           VALUES(?,?,?,?,?,'4',?,?,0,0,0,'',?,?,?,getdate(),?,?,getdate(),?)""",
                        ymd, seq, WH_CUST, WH_CUST, cgpc, child, d, box, child, user, win, user, win)
            _upd_stock(cur, "PU_T_MAT_STOCK", [("MAT_CODE", child), ("CUST_CODE", WH_CUST)], d, user, win)
            _upd_stock(cur, "PU_T_MAT_STOCK_WH",
                       [("MAT_CODE", child), ("CUST_CODE", WH_CUST), ("GAGONG_PROC_CODE", cgpc)], d, user, win)
            moved.append(("하위자재", child, d))
    return moved

@router.post("/api/gagong/barcode/register")
def gagong_bc_register(payload: dict = Body(...)):
    """실적등록 — 재고 4갈래 이동 + 전표갱신 + PU_T_CUT_DTL 이력(레거시 018 동일)."""
    box = _bc_box(payload.get("box_no") or payload.get("scan1"))
    good = int(float(payload.get("good_qty") or 0))
    bad = int(float(payload.get("bad_qty") or 0))
    user = str(payload.get("user") or "웹")[:20]
    if not box:
        return {"ok": False, "msg": "바코드 오류"}
    if good <= 0 and bad <= 0:
        return {"ok": False, "msg": "양품/불량 수량을 입력하세요."}
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    win = 'w_pr_input_018'
    cn = _nx_tx(); cur = cn.cursor()
    try:
        c = _bc_ctx(cur, box)
        if not c:
            cn.rollback(); return {"ok": False, "msg": f"전표(바코드 {box}) 없음"}
        if c["del_flag"] == '1':
            cn.rollback(); return {"ok": False, "msg": "삭제된 가공간판입니다."}
        if c["prod_flag"] == '1':
            cn.rollback()
            return {"ok": False, "done": True,
                    "msg": f"이미 실적완료된 전표입니다(수량 {c['prod_qty']}). 취소 후 재등록하세요."}
        # ★음수재고 방지(§1-8). 레거시엔 없으나 원장 음수는 금지.
        short = []
        if c["won"] and c["weight"]:
            need = c["weight"] * (good + bad)
            have = _stock_of(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", c["won"]), ("PART_CODE", GAGONG_PART)])
            if have < need:
                short.append({"kind": "원소재", "code": c["won"], "need": round(need, 4), "have": round(have, 4)})
        for child, use, cgpc in c["bom"]:
            need = use * good
            have = _stock_of(cur, "PU_T_MAT_STOCK_WH",
                             [("MAT_CODE", child), ("CUST_CODE", WH_CUST), ("GAGONG_PROC_CODE", cgpc)])
            if have < need:
                short.append({"kind": "하위자재", "code": child, "need": round(need, 4), "have": round(have, 4)})
        if short:
            cn.rollback()
            msg = "재고부족: " + ", ".join("%s %s(필요 %g/보유 %g)" % (s["kind"], s["code"], s["need"], s["have"]) for s in short)
            return {"ok": False, "shortage": short, "msg": msg}

        moved = _apply(cur, c, box, good, bad, +1, user, ymd, win)
        cur.execute("""UPDATE nx.PR_T_INDI_CUTTING
                          SET PROD_QTY=ISNULL(PROD_QTY,0)+?, PROD_FLAG='1',
                              PROD_USER_ID=?, PROD_DATETIME=getdate()
                        WHERE BOX_NO=?""", good, user, box)
        hms = datetime.now().strftime("%H%M%S")
        cur.execute("""INSERT INTO nx.PU_T_CUT_DTL
                       (LINE_NO,ITEM_CODE,MAT_CODE,CUT_YMD,CUT_HMS,WH_CUST_CODE,GAGONG_PROC_CODE,
                        CUT_QTY,ERR_QTY,CUT_USER_ID,BOX_NO,ITEM_DIAM,ITEM_THICK,ITEM_WEIGHT,CUT_WEIGHT,
                        ITEM_WORK_CODE,ITEM_IN_CUST_CODE,MAT_WORK_CODE,MAT_IN_CUST_CODE,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,mix_gagong)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),?,?)""",
                    c["line_no"], c["item"], c["mat"], ymd, hms, WH_CUST, GAGONG_PART,
                    good, bad, user, box, c["diam"], c["thick"], c["weight"],
                    c["weight"] * (good + bad), c["item_work"], c["item_cust"],
                    c["mat_work"], c["mat_cust"], user, win, c["mix"])
        cn.commit()
        return {"ok": True, "box_no": box, "good_qty": good, "bad_qty": bad,
                "moved": [{"kind": k, "code": m, "qty": round(q, 4)} for k, m, q in moved],
                "msg": f"실적등록 완료 — 가공창고 +{good}"}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()

@router.post("/api/gagong/barcode/cancel")
def gagong_bc_cancel(payload: dict = Body(...)):
    """실적취소 — 재고 4갈래 역이동 + 전표원복 + PU_T_CUT_DTL 음수 역분개(레거시 동일)."""
    box = _bc_box(payload.get("box_no"))
    user = str(payload.get("user") or "웹")[:20]
    if not box:
        return {"ok": False, "msg": "바코드 오류"}
    ymd = _d6(str(payload.get("ymd") or "")) or datetime.now().strftime("%y%m%d")
    win = 'w_pr_input_018'
    cn = _nx_tx(); cur = cn.cursor()
    try:
        c = _bc_ctx(cur, box)
        if not c:
            cn.rollback(); return {"ok": False, "msg": f"전표(바코드 {box}) 없음"}
        if c["prod_flag"] != '1':
            cn.rollback(); return {"ok": False, "msg": "실적이 등록되지 않은 전표입니다."}
        # 취소대상 수량 = 마지막 실적(누계 PU_T_CUT_DTL 합)
        cur.execute("""SELECT ISNULL(SUM(CUT_QTY),0), ISNULL(SUM(ERR_QTY),0)
                         FROM nx.PU_T_CUT_DTL WITH(NOLOCK) WHERE BOX_NO=?""", box)
        cd = cur.fetchone()
        good = int(cd[0] or 0) or c["prod_qty"]
        bad = int(cd[1] or 0)
        if good <= 0:
            cn.rollback(); return {"ok": False, "msg": "취소할 실적수량이 없습니다."}
        # ★음수재고 방지: 이미 다음공정으로 빠진 분은 취소불가
        have = _stock_of(cur, "PR_T_MAT_STOCK_WH", [("MAT_CODE", c["mat"]), ("PART_CODE", GAGONG_PART)])
        if have < good:
            cn.rollback()
            return {"ok": False, "msg": f"가공창고 재고부족으로 취소불가({c['mat']} 보유 {have:g} < 취소 {good})"}

        moved = _apply(cur, c, box, good, bad, -1, user, ymd, win)
        cur.execute("""UPDATE nx.PR_T_INDI_CUTTING
                          SET PROD_QTY=ISNULL(PROD_QTY,0)-?, PROD_FLAG='0',
                              PROD_USER_ID='', PROD_DATETIME=NULL
                        WHERE BOX_NO=?""", good, box)
        hms = datetime.now().strftime("%H%M%S")
        cur.execute("""INSERT INTO nx.PU_T_CUT_DTL
                       (LINE_NO,ITEM_CODE,MAT_CODE,CUT_YMD,CUT_HMS,WH_CUST_CODE,GAGONG_PROC_CODE,
                        CUT_QTY,ERR_QTY,CUT_USER_ID,BOX_NO,ITEM_DIAM,ITEM_THICK,ITEM_WEIGHT,CUT_WEIGHT,
                        ITEM_WORK_CODE,ITEM_IN_CUST_CODE,MAT_WORK_CODE,MAT_IN_CUST_CODE,
                        INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,mix_gagong)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,getdate(),?,?)""",
                    c["line_no"], c["item"], c["mat"], ymd, hms, WH_CUST, GAGONG_PART,
                    -good, -bad, user, box, c["diam"], c["thick"], c["weight"],
                    -(c["weight"] * (good + bad)), c["item_work"], c["item_cust"],
                    c["mat_work"], c["mat_cust"], user, win, c["mix"])
        cn.commit()
        return {"ok": True, "box_no": box, "good_qty": good, "bad_qty": bad,
                "moved": [{"kind": k, "code": m, "qty": round(q, 4)} for k, m, q in moved],
                "msg": f"실적취소 완료 — 가공창고 -{good}"}
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()
