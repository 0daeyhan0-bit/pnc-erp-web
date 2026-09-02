# -*- coding: utf-8 -*-
"""order 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# ================= 생산: 주문UPLOAD(w_pr_plan_010) · 생산계획UPLOAD(w_pr_plan_020) =================
# 소스=LG PU-SCS 2.0 엑셀(Purchase Order / Production Plan Status). 레거시 SP_LGE_RECV_ORDER 매핑을
# 실측검증(품번·단가·워크오더·납기·CR_FLAG 0불일치, 생산계획 WO총량 100%)한 규칙 그대로 적재. 저장=nx(TEST3).
def _d6(s):
    d = ''.join(ch for ch in str(s or '') if ch.isdigit())
    if len(d) == 8: return d[2:8]      # yyyymmdd → yymmdd
    return d[-6:] if len(d) >= 6 else d

def _po_rows(ws, cr):
    """Purchase Order 시트 → recv 튜플. WORK_ORDER=P/S Order '-' 앞부분, ITEM_COST=Unit Price."""
    def y6(v):
        s = str(v); return (s[2:4]+s[5:7]+s[8:10]) if len(s) >= 10 and s[4] == '-' else ''
    out = []
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not r or r[3] is None or str(r[0]) == 'Total Sum': continue
        on = f"{str(r[3]).strip()}-{str(r[4]).strip() if r[4] is not None else ''}"
        ps = str(r[17]).strip() if r[17] else ''
        out.append((on, str(r[1]).strip() if r[1] else '', y6(r[5]), '0000', int(r[9] or 0), int(r[8] or 0),
                    ps[:8], ps, y6(r[33]), cr, str(r[2] or '')[:40], round(float(r[24] or 0), 2)))  # WORK_ORDER=LEFT(P/S,8) 레거시 정본
    return out

def _plan_rows(rows, cr):
    """Production Plan Status 행들 → plan 튜플(WO,일자별). 일별 컬럼(MM/DD) 전개.

    ★반환 = (recs, axis_from) — axis_from 은 **파일 일자축의 첫날**이다(2026-08-28 신설).
      수량 0인 셀은 계획행으로 저장하지 않지만(의미 없는 행 30배 증가), 그날이
      **편성 기준일**이 되어야 한다. 저장된 행의 MIN(PLAN_YMD)로 기준일을 역산하면
      첫날 수량이 전부 0일 때 기준일이 통째로 밀린다.
      실측 2026-08-28: 파일 축은 08/28~ 인데 08/28 열이 전 행 0(3,671행) 이라
      저장분 최소일이 260829 가 됐고, 당일 클램프가 29일로 잡혀 28일 컬럼이 사라졌다.
      (레거시 기준일 = 260828 → 자재소요 12,330건이 28일에 모임)"""
    import re as _re
    def cymd(h):
        m = _re.match(r'(\d\d)/(\d\d)', str(h)); return ('26'+m.group(1)+m.group(2)) if m else None
    hdr = rows[0]; dcol = {i: cymd(hdr[i]) for i in range(len(hdr)) if cymd(hdr[i])}
    axis_from = min(dcol.values()) if dcol else ""
    agg = {}
    for r in rows[1:]:
        if not r or r[3] is None: continue
        wo = str(r[3]).strip(); line = str(r[1]).strip() if r[1] else ''; sg = str(r[2]).strip() if r[2] else ''
        model = str(r[4]).strip() if r[4] else ''; buyer = str(r[5]).strip() if r[5] else ''
        tot = int(float(r[6] or 0)); rem = int(float(r[7] or 0))
        st = str(r[46]) if len(r) > 46 and r[46] else ''
        # ★Start Time 시각 = 'HH:MM' 패턴으로 찾는다(2026-09-02, 고정위치 자르기에서 변경).
        #   결과는 종전 `st[11:13]+st[14:16]` 과 전수 동일하지만(4,622건 대조),
        #   'AM/PM' 이 뒤에 붙거나 초가 없는 등 길이가 달라져도 안전하다.
        #   ※시각이 아예 없으면 종전대로 0800 폴백(레거시 동일).
        #
        # ★2026-09-02 규명 — 0800 29건 중 28건은 **진짜 8시**(레거시 ORG_OUTPUT_HM 도 0800).
        #   남은 1건 6J4M0018 은 웹 업로드 버그가 아니다. 레거시 원본 실측:
        #       UPLOAD_PLAN_YMD 260907 · UPLOAD_OUTPUT_HM 0000   ← 레거시 업로드도 시각 실패
        #       ORG_PLAN_YMD    260904 · ORG_OUTPUT_HM    1728   ← 최종값은 다름
        #       REMARKS1 'C1야간분' · AM_PM 'P'
        #   엑셀 원본이 '2026-09-04 13:48:00 AM'(AM 인데 13시, 우측 수량열도 0/0) 로 깨져
        #   **레거시도 0000 으로 읽었다.** 웹이 받은 260907 은 UPLOAD_PLAN_YMD 와 일치 —
        #   즉 업로드 단계는 양쪽 다 같았고, 레거시만 이후 어딘가에서 값이 바뀌었다.
        #     · 4,425건 중 UPLOAD≠ORG 인 것은 이 1건뿐 (REMARKS1 이 채워진 것도 이 1건뿐).
        #     · 무엇이 바꿨는지는 미규명(업로드 후 보정 경로가 있는 것으로 보이나 확인 못함).
        #   ⟹ 업로드 파싱으로는 재현 불가. 파트별계획 차이 ±14×4 의 원인이 이것이다.
        #
        # ★폴백값 0800 → 1700 (2026-09-02, 사용자 확정).
        #   시각을 **못 읽었을 때만** 적용된다 — 정상 파싱된 08:00 은 그대로 0800 이다
        #   (실측: 0800 29건 중 28건이 진짜 8시. 폴백을 무조건 걸면 그 28건이 망가진다).
        #   0800(주간 시작)보다 1700(야간 투입)이 실제에 가깝다는 판단.
        #   ※레거시 폴백은 0000 이라 값 자체는 여전히 다르다. 총량에는 영향 없음.
        _m = _re.search(r'(\d{1,2}):(\d{2})', st)
        sh = (_m.group(1).zfill(2) + _m.group(2)) if _m else ''
        if not ('0000' <= sh <= '2359'): sh = '1700'   # 무효 Start Time → 1700(야간)
        fs = str(r[47]).strip() if len(r) > 47 and r[47] is not None else ''
        ts = str(r[48]).strip() if len(r) > 48 and r[48] is not None else ''
        tool = str(r[49]).strip() if len(r) > 49 and r[49] else ''
        for ci, ymd in dcol.items():
            if ci < len(r) and r[ci] and float(r[ci]) > 0:
                q = int(float(r[ci])); k = (wo, ymd)
                if k in agg:
                    p = list(agg[k]); p[6] += q; agg[k] = tuple(p)
                else:
                    agg[k] = (ymd, wo, model, buyer, line, sg, q, tot, rem, sh, tool[:40], fs[:20], ts[:20], cr)
    return list(agg.values()), axis_from

def _fname_axis_warn(fname, axis_from, cr):
    """파일명 날짜 ↔ 계획 일자축 대조 → 경고문(없으면 "").

    ★양식 = `lg_<구분>_<MMDD>` 고정 (사용자 확정 2026-09-01)
        lg_rac_0901 생산계획(편집).xlsx
        LG_SAC_0901.xlsx
      → `lg_` 다음 세 번째 토큰의 4자리를 날짜로 읽는다. 파일명 아무 데나 있는
        4자리 숫자를 줍지 않으므로 오탐이 없다(제번·모델명에도 숫자가 많다).
      규칙에 안 맞는 이름이면 판단하지 않고 조용히 통과한다.

    ★왜 필요한가 (2026-09-01 실사고)
      9/1 에 8/28 자 파일을 올려 편성이 통째로 어긋났다.
      웹 계획원본 260829~ / 레거시 260901~ · 업체별 대사 불일치 15쌍 → 1,934쌍.
      화면·로그 어디에도 "옛 파일을 올렸다"는 신호가 없어 원인 찾는 데 오래 걸렸다.

    ★차단하지 않고 경고만 한다 — 과거분 재업로드가 정상 업무일 수 있다.
      파일명에 날짜가 없으면(규칙 밖 이름) 아무 말도 하지 않는다.
    """
    import re as _re
    f = str(fname or "").strip()
    a = "".join(ch for ch in str(axis_from or "") if ch.isdigit())
    if not f or len(a) != 6:
        return ""
    base = f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = _re.sub(r'\.(xlsx|xlsm|xls|csv)$', '', base, flags=_re.I)
    # ★`lg_<구분>_<MMDD>` 의 세 번째 토큰만 본다. 뒤에 무엇이 붙든(공백·한글·괄호) 무관.
    m = _re.match(r'\s*lg[_\-\s]+[A-Za-z]+[_\-\s]+(\d{4})(?!\d)', base, _re.I)
    if not m:
        return ""                       # 규칙 밖 이름 = 판단 불가, 조용히 통과
    fn = m.group(1)
    mm, dd = int(fn[:2]), int(fn[2:])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ""                       # 날짜가 아닌 4자리
    ax_md = a[2:]                       # YYMMDD → MMDD
    if fn == ax_md:
        return ""                       # 일치
    _f = f"{fn[:2]}월 {fn[2:]}일"
    _a = f"{ax_md[:2]}월 {ax_md[2:]}일"
    return (f"업로드 날짜가 상이합니다.\n\n"
            f"    파일명 날짜   {_f}   ({base})\n"
            f"    계획 시작일   {_a}   (파일 안의 일자축 첫날)\n\n"
            f"다른 날짜의 파일을 올리셨을 수 있습니다.\n"
            f"맞는 파일인지 확인하세요 — 옛 파일로 편성하면 계획이 통째로 어긋납니다.")


def _load_xlsx(b64):
    import base64, io as _io, openpyxl
    raw = base64.b64decode(str(b64).split(',')[-1])
    return openpyxl.load_workbook(_io.BytesIO(raw), data_only=True, read_only=True)

@router.get("/api/order/list")
def order_list(from_ymd: str = Query(""), to_ymd: str = Query(""), need_from: str = Query(""),
               need_to: str = Query(""), done: str = Query("all"), item: str = Query(""),
               wo: str = Query(""), cr: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("r.ORDER_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("r.ORDER_YMD<=?"); p.append(_d6(to_ymd))
        if need_from: w.append("r.NEED_BY_YMD>=?"); p.append(_d6(need_from))
        if need_to:   w.append("r.NEED_BY_YMD<=?"); p.append(_d6(need_to))
        if item.strip(): w.append("r.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if wo.strip():   w.append("(r.WORK_ORDER LIKE ? OR r.PS_ORDER LIKE ?)"); p += [f"%{wo.strip()}%"]*2
        if cr in ('C', 'R'): w.append("r.CR_FLAG=?"); p.append(cr)
        if done == 'done':   w.append("r.REMAIN_QTY<=0")
        elif done == 'undone': w.append("r.REMAIN_QTY>0")
        cur.execute(f"""SELECT TOP 5000 r.ORDER_NO,r.ORDER_YMD,r.ITEM_CODE,ISNULL(i.item_name,'') nm,
            r.ORDER_QTY,r.REMAIN_QTY,r.NEED_BY_YMD,r.NEED_BY_HM,r.WORK_ORDER,r.PS_ORDER,r.ITEM_COST,r.CR_FLAG,r.PO_TYPE
          FROM nx.recv_dtl r LEFT JOIN PARTNER_ERP_TEST3.nx.item i ON i.item_code=r.ITEM_CODE
          WHERE {' AND '.join(w)} ORDER BY r.ORDER_YMD DESC, r.ORDER_NO""", *p)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            r["ITEM_COST"] = float(r["ITEM_COST"] or 0)
            r["AMT"] = round(r["ITEM_COST"] * (r["ORDER_QTY"] or 0))
        return {"rows": rows, "count": len(rows),
                "sum_qty": sum(r["ORDER_QTY"] or 0 for r in rows),
                "sum_amt": sum(r["AMT"] for r in rows)}
    finally:
        nx.close()

@router.post("/api/order/upload")
def order_upload(payload: dict = Body(...)):
    cr = (str(payload.get("cr", "C")).strip() or "C")[:1]
    try:
        wb = _load_xlsx(payload.get("b64", ""))
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")
    recs = _po_rows(wb[wb.sheetnames[0]], cr); wb.close()
    if not recs:
        return {"ok": True, "inserted": 0, "updated": 0, "total": 0, "cr": cr}
    nx = _nx(); cur = nx.cursor()
    try:
        # 레거시 방식(temp→일괄): 세트기반 upsert로 고속 처리
        cur.execute("IF OBJECT_ID('tempdb..#s') IS NOT NULL DROP TABLE #s")
        cur.execute("""CREATE TABLE #s(ORDER_NO varchar(24),ITEM_CODE varchar(20),NEED_BY_YMD varchar(6),NEED_BY_HM varchar(4),
            ORDER_QTY int,REMAIN_QTY int,WORK_ORDER varchar(20),PS_ORDER varchar(30),ORDER_YMD varchar(6),
            CR_FLAG varchar(1),PO_TYPE varchar(40),ITEM_COST decimal(18,2))""")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #s VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        upd = cur.execute("SELECT COUNT(*) FROM nx.recv_dtl r JOIN #s s ON r.ORDER_NO=s.ORDER_NO").fetchone()[0]
        cur.execute("DELETE r FROM nx.recv_dtl r JOIN #s s ON r.ORDER_NO=s.ORDER_NO")
        cur.execute("""INSERT INTO nx.recv_dtl(ORDER_NO,ITEM_CODE,NEED_BY_YMD,NEED_BY_HM,ORDER_QTY,REMAIN_QTY,
            WORK_ORDER,PS_ORDER,ORDER_YMD,CR_FLAG,PO_TYPE,ITEM_COST,UPLOAD_DT)
            SELECT ORDER_NO,ITEM_CODE,NEED_BY_YMD,NEED_BY_HM,ORDER_QTY,REMAIN_QTY,WORK_ORDER,PS_ORDER,ORDER_YMD,
                   CR_FLAG,PO_TYPE,ITEM_COST,getdate() FROM #s""")
        return {"ok": True, "inserted": len(recs) - upd, "updated": upd, "total": len(recs), "cr": cr}
    finally:
        nx.close()

@router.get("/api/plan/list")
def plan_list(from_ymd: str = Query(""), to_ymd: str = Query(""), line: str = Query(""),
              sched: str = Query(""), wo: str = Query(""), model: str = Query(""), cr: str = Query("")):
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["1=1"]; p = []
        if from_ymd: w.append("PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if line.strip():  w.append("LINE_NO=?"); p.append(line.strip())
        if sched.strip(): w.append("SCHED_GROUP=?"); p.append(sched.strip())
        if wo.strip():    w.append("WORK_ORDER LIKE ?"); p.append(f"%{wo.strip()}%")
        if model.strip(): w.append("MODEL_NO LIKE ?"); p.append(f"%{model.strip()}%")
        if cr in ('C', 'R'): w.append("CR_FLAG=?"); p.append(cr)
        cur.execute(f"""SELECT PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,
            TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG
          FROM nx.plan_dtl WHERE {' AND '.join(w)}""", *p)
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, row)) for row in cur.fetchall()]
        dates = sorted({r["PLAN_YMD"] for r in raw})
        wos = {}
        for r in raw:
            k = r["WORK_ORDER"]
            g = wos.get(k)
            if not g:
                g = {"wo": k, "model": r["MODEL_NO"], "buyer": r["BUYER_MODEL"], "line": r["LINE_NO"],
                     "sched": r["SCHED_GROUP"], "total": r["TOTAL_QTY"], "remain": r["REMAIN_QTY"],
                     "tool": r["TOOL"], "cr": r["CR_FLAG"], "days": {}}
                wos[k] = g
            g["days"][r["PLAN_YMD"]] = (g["days"].get(r["PLAN_YMD"], 0) + (r["PLAN_QTY"] or 0))
        rows = sorted(wos.values(), key=lambda x: (x["line"] or "", x["wo"]))
        return {"dates": dates, "rows": rows, "wo_count": len(rows),
                "sum_qty": sum(r["PLAN_QTY"] or 0 for r in raw)}
    finally:
        nx.close()

@router.post("/api/plan/upload")
def plan_upload(payload: dict = Body(...)):
    cr = (str(payload.get("cr", "C")).strip() or "C")[:1]
    try:
        wb = _load_xlsx(payload.get("b64", ""))
    except Exception as e:
        raise HTTPException(400, f"엑셀 파싱 실패: {e}")
    ws = wb[wb.sheetnames[0]]; rows = list(ws.iter_rows(values_only=True)); wb.close()
    recs, axis_from = _plan_rows(rows, cr)
    if not recs:
        return {"ok": True, "inserted": 0, "updated": 0, "total": 0, "cr": cr}
    # ★★날짜 대조는 **저장 전에** 한다 — 경고만 띄우면 이미 덮어쓴 뒤라 되돌릴 수 없다.
    #   (2026-09-01 사용자 지적: "오류가 나도 업로드가 되어버리네")
    #   기존 계획을 CR별로 전량 삭제·재적재하므로, 잘못 올리면 직전 계획이 사라진다.
    #   ⟹ 불일치면 **저장하지 않고 409**. 사용자가 확인 후 force=true 로 다시 올리면 진행.
    _w = _fname_axis_warn(str(payload.get("fname") or ""), axis_from, cr)
    if _w and not bool(payload.get("force")):
        raise HTTPException(409, _w + "\n\n※ 이 파일이 맞다면 [확인]을 눌러 그대로 업로드할 수 있습니다.")
    nx = _nx(); cur = nx.cursor()
    try:  # recs t=(PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG)
        cur.execute("IF OBJECT_ID('tempdb..#p') IS NOT NULL DROP TABLE #p")
        cur.execute("""CREATE TABLE #p(PLAN_YMD varchar(6),WORK_ORDER varchar(20),MODEL_NO varchar(30),BUYER_MODEL varchar(30),
            LINE_NO varchar(10),SCHED_GROUP varchar(6),PLAN_QTY int,TOTAL_QTY int,REMAIN_QTY int,START_HM varchar(4),
            TOOL varchar(40),FROM_SEQ varchar(20),TO_SEQ varchar(20),CR_FLAG varchar(1))""")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #p VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", recs)
        # 레거시 STEP0: "cr별 삭제 후 재적재"(full replace). 업로드 파일 = 해당 CR의 완전한 현재 계획.
        # ★해당 CR 전체 삭제(과거일자 포함) → 재적재. 계획일자 이동/재업로드 시 stale행 누적(2배)·
        #   과거일자 잔재(compose_mat 부풀림) 방지. 과거 이력은 별도 _daily 백업 대상(현 미구현).
        fmin = min(r[0] for r in recs)
        upd = cur.execute("SELECT COUNT(*) FROM nx.plan_dtl WHERE CR_FLAG=?", cr).fetchone()[0]
        cur.execute("DELETE FROM nx.plan_dtl WHERE CR_FLAG=?", cr)
        cur.execute("""INSERT INTO nx.plan_dtl(PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,
            TOTAL_QTY,REMAIN_QTY,START_HM,TOOL,FROM_SEQ,TO_SEQ,CR_FLAG,UPLOAD_DT)
            SELECT PLAN_YMD,WORK_ORDER,MODEL_NO,BUYER_MODEL,LINE_NO,SCHED_GROUP,PLAN_QTY,TOTAL_QTY,REMAIN_QTY,START_HM,
                   TOOL,FROM_SEQ,TO_SEQ,CR_FLAG,getdate() FROM #p""")
        # ★파일 일자축의 첫날을 기록한다 — 편성의 **당일 클램프 기준일**(planrev._step7_sql).
        #   그날 수량이 전부 0이면 계획행이 없어 MIN(PLAN_YMD)로는 알 수 없다(2026-08-28).
        cur.execute("""IF OBJECT_ID('nx.plan_upload_axis') IS NULL
                       CREATE TABLE nx.plan_upload_axis(
                         cr_flag varchar(1) NOT NULL PRIMARY KEY,
                         axis_from varchar(6) NULL,
                         upload_dt datetime NOT NULL DEFAULT getdate())""")
        if axis_from:
            cur.execute("UPDATE nx.plan_upload_axis SET axis_from=?, upload_dt=getdate() WHERE cr_flag=?",
                        axis_from, cr)
            if cur.rowcount == 0:
                cur.execute("INSERT INTO nx.plan_upload_axis(cr_flag,axis_from) VALUES(?,?)", cr, axis_from)
        # full-replace(cr별): 기존 upd행 삭제 후 recs행 재적재
        #   ※날짜 대조는 이 위(저장 전)에서 이미 끝났다 — 여기 오면 통과했거나 force 다.
        return {"ok": True, "inserted": len(recs), "replaced": upd, "total": len(recs), "cr": cr,
                "from_ymd": fmin, "axis_from": axis_from,
                "forced": bool(payload.get("force"))}
    finally:
        nx.close()


@router.get("/api/plan/basedate")
def plan_basedate():
    """★계획 계열 화면의 공통 기준일 = **마지막 업로드 파일의 일자축 첫날**(2026-08-28 신설).

    왜 오늘(GETDATE)이 아니라 업로드 일자인가 — 사용자 확정:
      27일 기준으로 보던 계획을 28일 업로드 후에 다시 보면, 27일 미출하분이 28일로
      재편성되면서 재고가 그쪽에 충당된다. 즉 27일 기준 화면은 이미 '그때의 재고반영'이
      아니게 되어 재고가 실제보다 많이 채워져 보인다. 28일(업로드 일자)로 조회하면
      그 재편성분에 재고가 채워지므로 정합이 맞는다.
      (출하가 다 끝난 날은 무관하지만, 미출하가 남으면 반드시 어긋난다)

    쓰는 화면: 파트별계획 · 자재소요 · 영업계획 · 가공계획 · 가공이동계획 · 협력사계획.
    폴백 순서: plan_upload_axis(파일 축) → MIN(PLAN_YMD)(구 업로드분) → 오늘."""
    nx = _nx(); cur = nx.cursor()
    try:
        base = ""
        try:
            cur.execute("""SELECT MIN(axis_from) FROM nx.plan_upload_axis
                            WHERE ISNULL(axis_from,'')<>''""")
            base = str((cur.fetchone() or [None])[0] or "").strip()
        except Exception:
            pass
        src = "upload_axis"
        if not base:
            cur.execute("SELECT MIN(PLAN_YMD) FROM nx.plan_dtl WHERE PLAN_QTY>0")
            base = str((cur.fetchone() or [None])[0] or "").strip(); src = "min_plan_ymd"
        if not base:
            from datetime import datetime as _d
            base = _d.now().strftime("%y%m%d"); src = "today"
        up = None
        try:
            cur.execute("SELECT MAX(upload_dt) FROM nx.plan_upload_axis")
            up = cur.fetchone()[0]
        except Exception:
            pass
        return {"base_ymd": base, "base_iso": (f"20{base[:2]}-{base[2:4]}-{base[4:6]}" if len(base) >= 6 else ""),
                "src": src, "upload_dt": (str(up)[:19] if up else None)}
    finally:
        nx.close()
