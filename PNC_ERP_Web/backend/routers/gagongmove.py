# -*- coding: utf-8 -*-
"""gagongmove 도메인 라우터 — app.py에서 분리. 공유헬퍼는 common.py."""
import os, math, json, base64, time, hashlib, mimetypes
from datetime import datetime, timedelta
from urllib.parse import quote as _urlquote
from fastapi import APIRouter, Query, Body, HTTPException, Response, UploadFile, File, Form
from common import (_conn, _num, _run_sp, _shape, _nx, _nx_tx, _b, _d6, _ym, _ITEM_WORK, _get_cost_engine, _reset_cost_engine, _COST_LOCK, SP_SIL, SP_NAE, NxCostEngine, _HERE, _closed, _validate_alloc, _ensure_modelbom, _pur_src, _custnm_map, _kindmap, _dig4, _cur_ym, _sale_win, _SALE_MAGAM, DOC_STORAGE_PATH, _hashlib, _mimetypes)

router = APIRouter()

# 생산파트/사급업체 드롭다운 — 레거시 as_pr_part_code(PR_M_PROC_GAGONG)·as_sagub_cust_code(CM_M_CUST) 실측(2026-08-22).
@router.get("/api/gagong/move580/opts")
def gagong_move580_opts():
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("""SELECT GAGONG_PROC_CODE, GAGONG_PROC_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG
                       ORDER BY SORT_KEY, GAGONG_PROC_CODE""")
        parts = [{"code": r[0], "nm": r[1] or r[0]} for r in cur.fetchall()]
        cur.execute("""SELECT DISTINCT c.CUST_CODE, c.CUST_DESC FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM m
                       JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST c ON c.CUST_CODE=m.IN_CUST_CODE
                       WHERE ISNULL(m.IN_CUST_CODE,'')<>'' ORDER BY c.CUST_DESC""")
        sagubs = [{"code": r[0], "nm": r[1] or r[0]} for r in cur.fetchall()]
        return {"parts": parts, "sagubs": sagubs}
    finally:
        cn.close()

# ================= 가공창고 이동계획 (w_pr_input_580) =================
# ★2026-08-22 전환: 역설계 중단 → 레거시 SP 를 그대로 호출한다.
#   SP 본문은 암호화(WITH ENCRYPTION)라 못 읽지만 EXEC 는 되고 174컬럼을 그대로 반환한다(실측 384행).
#   → 계획/완료 자·모, 색상(color_00~31), 자도번LIST(mat_list), 재고 컬럼 전부 레거시 정답을 그대로 받는다.
#   조회 = 라이브(PARTNER_ERP) 읽기전용. 쓰기(이동전표 발행)는 여전히 nx 만(§1 절대규칙).
SP_MOVE580 = "SP_PR_가공창고_이동계획_260213"

# PowerBuilder 색상정수(BGR) → CSS. 실측 분포: 16777215(흰=없음) / 39270(초록=확정) / 65535(노랑) / 9486586(회청)
def _pbcolor(v):
    try:
        n = int(v)
    except Exception:
        return ""
    if n in (16777215, -1, 0):        # 흰색/미지정 = 색 없음
        return ""
    b, g, r = (n >> 16) & 255, (n >> 8) & 255, n & 255
    return "#%02x%02x%02x" % (r, g, b)

def _f(v):
    try: return float(v or 0)
    except Exception: return 0.0

@router.get("/api/gagong/move580")
def gagong_move580(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query("P2"),
                   pr_part: str = Query("%"), pu_part: str = Query("IS0001"), sagub: str = Query(""),
                   item: str = Query(""), part: str = Query(""), mv: str = Query("전체"), limit: int = Query(2500)):
    """레거시 SP 직접호출. 인자 = (as_from_ymd, as_to_ymd, as_work_code, as_pu_part_code, as_pr_part_code, as_sagub_cust_code).
       도번(item)·자도번(part)·이동필요(mv) 필터는 SP 인자에 없으므로 결과에서 파이썬 필터."""
    d6a = _d6(from_ymd) if from_ymd else ""
    d6b = _d6(to_ymd) if to_ymd else ""
    cn = _conn(); cur = cn.cursor()
    try:
        cur.execute("SET NOCOUNT ON; EXEC [dbo].[" + SP_MOVE580 + "] ?,?,?,?,?,?",
                    d6a, d6b, (wc or "").strip(), (pu_part or "").strip(),
                    (pr_part or "%").strip() or "%", (sagub or "").strip())
        while cur.description is None:
            if not cur.nextset(): break
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        cn.close()

    # 일자컬럼(NN) → 실제 날짜 매핑. SP 는 from_ymd 기준 00=이전, 01..31=경과일.
    from datetime import date as _date
    def _ymd_add(y6, k):
        y, m, d = 2000 + int(y6[0:2]), int(y6[2:4]), int(y6[4:6])
        t = _date(y, m, d) + timedelta(days=k)
        return "%02d%02d%02d" % (t.year % 100, t.month, t.day)
    ndays = 0
    if d6a and d6b:
        ya, ma, da = 2000 + int(d6a[0:2]), int(d6a[2:4]), int(d6a[4:6])
        yb, mb, db = 2000 + int(d6b[0:2]), int(d6b[2:4]), int(d6b[4:6])
        ndays = (_date(yb, mb, db) - _date(ya, ma, da)).days
    # ★_01 = 기준일 "당일"(from_ymd). 이전엔 +1 로 잡아 전체가 하루씩 밀렸다.
    #   실증(2026-08-23): 기준일 260823 조회에서 part_plan_ymd=260824 인 행의 값이 _02 에 있음 → _01=260823.
    #   레거시 화면도 첫 일자컬럼이 기준일(23일)로 시작한다.
    ndays = max(0, min(ndays + 1, 31))
    dates = [_ymd_add(d6a, k) for k in range(ndays)] if d6a else []

    # ★레거시 SP 는 라이브(PARTNER_ERP)만 본다 — 웹이 nx 에 발행한 이동전표는 SP 결과에 안 들어있다.
    #   (§1 규칙상 쓰기는 nx 만 하므로) nx 발행분을 (ASSY,자도번,일자)별로 읽어 SP 값 위에 얹어준다.
    #   발행(IN_CONFIRM_FLAG='0') → jp_print_qty 가산 / 확정('1') → finish 가산.
    #   ★셀 매핑은 발행일(MAINT_YMD)이 아니라 "어느 계획일자 셀에서 발행했는지"(PR_MAINT_YMD)로 한다.
    #     (오늘 발행해도 계획은 며칠 뒤일 수 있어 발행일로 붙이면 셀에 안 걸린다 — 2026-08-23)
    nx_pr = {}   # (assy, 계획ymd) -> 발행수량
    nx_fin = {}  # (assy, 계획ymd) -> 확정수량
    nx_pr_tot = {}   # assy -> 발행합
    # ★가공세트재고관리(w_pu_stock_285_web)에서 조정한 분 — SP 의 jp_print_qty 는 라이브 세트재고
    #   (PU_T_SET_GAGONG_STOCK)를 읽어 계산하므로 웹 조정분을 모른다. 여기서 얹어준다(2026-08-23).
    nx_setadj = {}   # assy -> 세트재고 조정합
    try:
        _sc = _nx(); _scur = _sc.cursor()
        try:
            _scur.execute("""SELECT ITEM_CODE, SUM(CAST(MAINT_QTY AS float))
                  FROM nx.PU_T_SET_STOCK_MAINT_GAGONG
                 WHERE ISNULL(INSERT_WINDOW,'') LIKE 'w_pu_stock_28%_web'
                 GROUP BY ITEM_CODE""")
            for rr in _scur.fetchall():
                nx_setadj[str(rr[0] or "").strip()] = _f(rr[1])
        finally:
            _sc.close()
    except Exception:
        pass
    try:
        _nc = _nx(); _ncur = _nc.cursor()
        try:
            # PR_MAINT_YMD = 발행한 계획일자 셀. 'P' = 당일이전 칸에서 발행(실제 계획일은 조회범위 이전).
            #   PR_MAINT_YMD 가 없는 옛 발행분은 발행일(MAINT_YMD)로 범위를 판정한 뒤 당일이전('P')에 넣는다.
            #   (범위판정 없이 전부 넣으면 작년 확정분까지 당일이전에 딸려온다 — 2026-08-23 실측)
            _ncur.execute("""SELECT ITEM_CODE, ISNULL(PR_MAINT_YMD,''), MAINT_YMD, IN_CONFIRM_FLAG,
                    SUM(CAST(MAINT_QTY AS float))
                  FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE WHERE MAINT_TAG='B'
                  GROUP BY ITEM_CODE, ISNULL(PR_MAINT_YMD,''), MAINT_YMD, IN_CONFIRM_FLAG""")
            for rr in _ncur.fetchall():
                a = str(rr[0] or "").strip()
                pymd = str(rr[1] or "").strip(); mymd = str(rr[2] or "").strip()
                flag = str(rr[3] or "").strip(); v = float(rr[4] or 0)
                if pymd == 'P' or not pymd:
                    # 당일이전 칸(또는 계획일자 미기록) — 발행일 기준으로 조회범위 판정
                    if d6a and mymd and mymd < d6a: continue
                    if d6b and mymd and mymd > d6b: continue
                    ymd = 'P'
                else:
                    ymd = pymd
                    if d6a and ymd < d6a: continue
                    if d6b and ymd > d6b: continue
                if flag == '1': nx_fin[(a, ymd)] = nx_fin.get((a, ymd), 0.0) + v
                else:
                    nx_pr[(a, ymd)] = nx_pr.get((a, ymd), 0.0) + v
                    nx_pr_tot[a] = nx_pr_tot.get(a, 0.0) + v
        finally:
            _nc.close()
    except Exception:
        pass

    rows = []
    _WEBPR = "#66bb6a"   # 웹 발행분(nx, 미확정) 표시색 — SP 초록(#669900)과 구분되는 연한 초록
    for r in raw:
        _assy = (r.get("assy_item_code") or "").strip()
        # ★세트재고 조정분(웹)은 "채워진 양"을 바꾼다 — 당일이전 → 앞 일자 순으로 흡수시킨다.
        #   (세트재고 30을 28로 줄이면 30/30 이던 셀이 28/30 이 되어야 함. 2026-08-23)
        _adj_left = nx_setadj.get(_assy, 0.0)
        days, done, colors, webpr = {}, {}, {}, {}
        # 먼저 당일이전부터 조정분을 흡수(레거시 SP 는 당일이전에 세트재고를 얹어 계산한다)
        _pplan = _f(r.get("plan_qty_00"))
        _pdone = _f(r.get("finish_qty_00")) + nx_fin.get((_assy, 'P'), 0.0)
        _pweb = nx_pr.get((_assy, 'P'), 0.0)
        if _adj_left < 0 and _pdone > 0:
            _take = min(_pdone, -_adj_left)
            _pdone -= _take; _adj_left += _take
        for k in range(1, ndays + 1):
            ii = "%02d" % k
            ymd = dates[k - 1]
            days[ymd] = _f(r.get("plan_qty_" + ii))
            d0 = _f(r.get("finish_qty_" + ii)) + nx_fin.get((_assy, ymd), 0.0)
            if _adj_left < 0 and d0 > 0:          # 남은 감소분을 이 셀에서 마저 흡수
                take = min(d0, -_adj_left)
                d0 -= take; _adj_left += take
            wp = nx_pr.get((_assy, ymd), 0.0)     # 웹이 nx 에 발행한 미확정분
            webpr[ymd] = wp
            # ★셀 분자 = 확정 + 웹발행분(계획 상한). 발행하면 그 셀이 "채워진" 상태로 보여야 한다.
            #   (10개 발행했는데 0/5 로 보이면 안 됨 — 5/5. 2026-08-23)
            done[ymd] = min(d0 + wp, days[ymd]) if days[ymd] > 0 else d0
            cc = _pbcolor(r.get("color_" + ii))
            # 계획을 못 채우게 되면 SP 가 준 색(초록)도 걷어낸다
            if days[ymd] > 0 and (d0 + wp) < days[ymd] - 1e-9:
                cc = ""
            # SP 가 색을 안 준 셀인데 웹 발행분이 계획을 채우면 초록으로 표시(레거시가 nx 를 못 보므로 보완)
            elif not cc and days[ymd] > 0 and (d0 + wp) >= days[ymd] - 1e-9:
                cc = _WEBPR
            colors[ymd] = cc
        plan_qty = _f(r.get("plan_qty"))
        fin_qty = (_f(r.get("finish_qty")) + sum(v for (a, _y), v in nx_fin.items() if a == _assy)
                   + nx_setadj.get(_assy, 0.0))
        # 당일이전 칸 색상 — 계획을 못 채우면 색 제거, 웹 발행분이 채우면 초록
        _prior_color = _pbcolor(r.get("color_00"))
        if _pplan > 0 and (_pdone + _pweb) < _pplan - 1e-9:
            _prior_color = ""
        if not _prior_color and _pplan > 0 and (_pdone + _pweb) >= _pplan - 1e-9: _prior_color = _WEBPR
        g = {
            "assy": (r.get("assy_item_code") or "").strip(),
            "item": (r.get("item_code") or "").strip(),
            "nm": (r.get("ITEM_DESC") or "").strip(),
            "line": (r.get("line_no") or "").strip(),
            # 최종납품처 = 사급업체명 우선, 없으면 조달가공공정명(레거시 dw 컬럼 gole_in_cust_desc)
            "dest": ((r.get("GOLE_IN_CUST_DESC") or "").strip()
                     or (r.get("GOLE_GAGONG_PROC_DESC") or "").strip()
                     or (r.get("MAT_WORK_DESC") or "").strip()),
            "jado": (r.get("mat_list") or "").strip(),
            "matcnt": len([x for x in (r.get("mat_list") or "").split(",") if x.strip()]),
            "part_ymd": (r.get("part_plan_ymd") or "").strip(),
            "hm": (r.get("part_output_hm") or "").strip(),
            "plan_qty": plan_qty,
            "moved": fin_qty,                       # 이동완료(확정)
            # 이동필요 = 계획 − (확정 + 웹발행분). 발행하면 그만큼 필요수가 줄어야 한다.
            "need": max(0.0, plan_qty - fin_qty - nx_pr_tot.get(_assy, 0.0)),
            # 이동전표발행 = SP값(라이브 세트재고 기준) + 웹 발행분 + 웹 세트재고 조정분
            "jp_print": (_f(r.get("jp_print_qty")) + nx_pr_tot.get(_assy, 0.0)
                         + nx_setadj.get(_assy, 0.0)),
            "set_adj": nx_setadj.get(_assy, 0.0),   # 웹 세트재고 조정분(툴팁 표시용)
            "sale": _f(r.get("sale_qty")),
            "assy_stock": _f(r.get("assy_stock_qty")),
            "prior": _pplan,      # 당일이전
            # 분자 = 확정 + 웹발행분(계획 상한). 날짜셀과 동일 규칙.
            "prior_done": (min(_pdone + _pweb, _pplan) if _pplan > 0 else _pdone),
            "prior_webpr": _pweb,   # 당일이전 칸에서 웹이 발행한 미확정분
            "prior_color": _prior_color,
            # 재고 3종(레거시 580 컬럼) = 자재재고 / 생산재고 / 도번고정재고. SP 원값 그대로.
            "stock": _f(r.get("stock_qty")), "pr_stock": _f(r.get("pr_stock_qty")),
            "fix_stock": _f(r.get("fix_stock_qty")),
            "days": days, "doneday": done, "colorday": colors, "webpr": webpr,
            "gagong_proc": (r.get("gagong_proc_code") or "").strip(),
            "gole_proc": (r.get("GOLE_GAGONG_PROC_CODE") or "").strip(),
            "gole_cust": (r.get("GOLE_IN_CUST_CODE") or "").strip(),
            "mat_work": (r.get("mat_work_code") or "").strip(),
            "work_code": (r.get("work_code") or "").strip(),
        }
        # ★납품처 = 생산(라인)과 사급업체가 같은 축이라 하나로 합친다(2026-08-22 사용자요청).
        #   키는 'P:코드'(생산라인) / 'C:코드'(사급업체) 로 구분해 동명이인 충돌을 막는다.
        if g["gole_cust"]:
            g["dest_key"] = "C:" + g["gole_cust"]; g["dest_kind"] = "C"
        elif g["gole_proc"]:
            g["dest_key"] = "P:" + g["gole_proc"]; g["dest_kind"] = "P"
        else:
            g["dest_key"] = ""; g["dest_kind"] = ""
        rows.append(g)

    it = item.strip().upper(); pt = part.strip().upper()
    if it: rows = [r for r in rows if it in (r["assy"] or "").upper()]
    if pt: rows = [r for r in rows if pt in (r["jado"] or "").upper()]
    # ★납품처 목록 = 조회결과에서 중복제거. 생산(라인) 먼저 → 사급업체 순, 각 그룹은 이름순.
    #   (SP 는 as_pr_part_code/as_sagub_cust_code 인자를 무시하므로 필터는 결과에서 한다 = 레거시와 동일 구조)
    seen = {}
    for r in rows:
        k = r["dest_key"]
        if k and k not in seen:
            seen[k] = {"key": k, "nm": r["dest"], "kind": r["dest_kind"]}
    dests = sorted(seen.values(), key=lambda x: (0 if x["kind"] == "P" else 1, x["nm"]))
    dk = (pr_part or "").strip()
    if dk and dk != "%": rows = [r for r in rows if r["dest_key"] == dk]
    m = mv.strip()
    if m == "이동필요": rows = [r for r in rows if r["need"] > 0]
    elif m == "이동완료": rows = [r for r in rows if r["need"] <= 0]
    capped = len(rows) > int(limit)
    rows = rows[:int(limit)]
    note = ("⚠ 상위 %d건만 표시 — 조건으로 좁혀주세요." % limit) if capped else ""
    return {"dates": dates, "rows": rows, "cnt": len(rows), "dests": dests,
            "plan_sum": sum(r["plan_qty"] for r in rows),
            "need_sum": sum(r["need"] for r in rows),
            "moved_sum": sum(r["moved"] for r in rows), "note": note}

# ================= 가공자재 이동처리 (w_pr_input_586 "자재개별일괄출고") =================
# ★레거시 로직 이식(w_pr_input_586.srw ue_save_after, 2026-08-22 소스 확보):
#   자재구분 3분기 — work_code='P2'(가공)=자기자신 등록 / gole_in_cust_code 있음(사급)=BOM전개 / 그외(사내생산)=BOM전개.
#   저장 = PU_T_STOCK_MAINT_GAGONG_MOVE INSERT(MAINT_TAG='B', IN_CONFIRM_FLAG='0') — "발행"이지 확정 아님.
#   ★확정('1')은 이 화면이 아니라 자재종류별 다른 화면(가공=바코드실적처리, 사급=자재입고확인, 직납품=출하)이 트리거.
#   maint_group_seq/check_list_seq = 레거시와 동일 패턴(최댓값+10, 끝자리 랜덤)으로 그룹 구분만 유지(중복 방지 목적, 값 자체 의미없음).
@router.post("/api/gagong/move580/issue")
def gagong_move580_issue(payload: dict = Body(...)):
    """선택셀(또는 수동입력) 자도번 목록을 받아 이동전표(미확정) 발행. rows=[{item_code,mat_code,item_desc,set_qty,use_qty,maint_qty,remarks}]."""
    ymd = _d6(payload.get("ymd") or "") or datetime.now().strftime("%y%m%d")
    out_wh = str(payload.get("out_wh") or "P0001").strip()
    rows_in = payload.get("rows") or []
    user = str(payload.get("user") or "web").strip()
    if not rows_in:
        raise HTTPException(400, "발행할 자도번이 없습니다.")
    # 자재구분(work_code) 판정. ★PR_M_ITEM 에는 GAGONG_PROC_CODE 컬럼이 없다(2026-08-23 실측: WORK_CODE·IN_CUST_CODE만).
    #   조달가공공정/사급업체는 화면(SP결과)이 gole_proc·gole_cust 로 함께 넘겨주므로 그 값을 우선 사용한다.
    cn = _conn(); cur = cn.cursor()
    itemset = list({str(r.get("item_code") or "").strip() for r in rows_in if r.get("item_code")})
    wkinfo = {}   # item_code -> {work_code, in_cust}
    try:
        for i in range(0, len(itemset), 900):
            ck = itemset[i:i + 900]; ph = ",".join("?" * len(ck))
            cur.execute(f"""SELECT ITEM_CODE, ISNULL(WORK_CODE,''), ISNULL(IN_CUST_CODE,'')
                FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})""", *ck)
            for r in cur.fetchall():
                wkinfo[str(r[0]).strip()] = {"work_code": r[1], "in_cust": r[2]}
    finally:
        cn.close()
    # 자재구분별 최종 전표행 조립. P2(가공)는 프론트가 넘긴 값 그대로(자기자신), 사급/사내생산은 BOM 1단계 전개.
    out_rows = []   # {item_code, mat_code, item_desc, set_qty, use_qty, maint_qty, remarks, pr_part_code, sagub_cust_code, to_gagong_proc_code}
    nxcn = _nx(); nxcur = nxcn.cursor()
    try:
        for r in rows_in:
            item_code = str(r.get("item_code") or "").strip()
            mat_code = str(r.get("mat_code") or "").strip()
            if not item_code or not mat_code:
                continue
            set_qty = float(r.get("set_qty") or 0); use_qty = float(r.get("use_qty") or 1)
            maint_qty = float(r.get("maint_qty") or (set_qty * use_qty))
            if maint_qty <= 0:
                continue
            info = wkinfo.get(item_code, {})
            # 화면이 SP 결과로 넘겨준 값 우선(gole_proc=조달가공공정, gole_cust=사급업체)
            row_proc = str(r.get("gole_proc") or "").strip()
            row_cust = str(r.get("gole_cust") or "").strip() or info.get("in_cust", "")
            # ★계획일자 — 어느 날짜셀에서 발행했는지. 조회 때 그 셀에 색을 칠하는 근거(PR_MAINT_YMD 에 저장).
            #   레거시는 이 컬럼을 안 쓴다(실측 34,441건 전부 공란)라 웹 전용으로 안전하게 쓸 수 있다.
            plan_ymd = _d6(str(r.get("plan_ymd") or "").strip()) or ""
            if info.get("work_code") == "P2":
                # 가공직납품 — 자기자신 등록(BOM전개 없음)
                out_rows.append({"item_code": item_code, "mat_code": item_code, "item_desc": r.get("item_desc") or "",
                                  "set_qty": maint_qty, "use_qty": 1, "maint_qty": maint_qty, "plan_ymd": plan_ymd,
                                  "remarks": r.get("remarks") or "", "pr_part_code": row_proc, "sagub_cust_code": ""})
            else:
                # 사급/사내생산 — mat_code(자도번) 자체가 이미 선택 대상이면 그대로, BOM 하위전개가 필요하면 1단계 조회.
                pr_part = "" if row_cust else row_proc
                sagub = row_cust
                out_rows.append({"item_code": item_code, "mat_code": mat_code, "item_desc": r.get("item_desc") or "",
                                  "set_qty": set_qty, "use_qty": use_qty, "maint_qty": maint_qty, "plan_ymd": plan_ymd,
                                  "remarks": r.get("remarks") or "", "pr_part_code": pr_part, "sagub_cust_code": sagub})
        if not out_rows:
            raise HTTPException(400, "발행할 유효한 자도번이 없습니다.")
        # maint_group_seq/check_list_seq 채번 (레거시: 최댓값+10, 끝자리 랜덤)
        import random
        nxcur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE WHERE MAINT_YMD=?", ymd)
        maint_seq = int((nxcur.fetchone() or [0])[0] or 0)
        nxcur.execute("SELECT ISNULL(MAX(MAINT_GROUP_SEQ),0) FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE")
        group_seq = int((nxcur.fetchone() or [0])[0] or 0)
        nxcur.execute("SELECT ISNULL(MAX(CHECK_LIST_SEQ),0) FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE")
        check_seq = int((nxcur.fetchone() or [0])[0] or 0)
        check_seq = (check_seq + 10) // 10 * 10 + random.randint(0, 9)
        last_item = None
        group_seq_from = None
        for r in out_rows:
            if r["item_code"] != last_item:
                group_seq = (group_seq + 10) // 10 * 10 + random.randint(0, 9)
                last_item = r["item_code"]
                if group_seq_from is None: group_seq_from = group_seq
            maint_seq += 1
            nxcur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT_GAGONG_MOVE
                (MAINT_YMD, MAINT_SEQ, MAINT_GROUP_SEQ, CHECK_LIST_SEQ, MAINT_TAG, GAGONG_PROC_CODE,
                 ITEM_CODE, MAT_CODE, SET_QTY, MAINT_QTY, REMARKS, OUT_WH_GUBUN, TO_GAGONG_PROC_CODE,
                 PR_PART_CODE, SAGUB_CUST_CODE, IN_CONFIRM_FLAG, PR_MAINT_YMD,
                 INSERT_USER_ID, INSERT_DATETIME, INSERT_IP, INSERT_COMPUTER, INSERT_WINDOW,
                 UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_IP, UPDATE_COMPUTER, UPDATE_WINDOW)
                VALUES (?,?,?,?,'B',?,?,?,?,?,?,'',?,?,?,'0',?,?,GETDATE(),'','','w_pr_input_580_web',?,GETDATE(),'','','w_pr_input_580_web')""",
                ymd, maint_seq, group_seq, check_seq, out_wh,
                r["item_code"], r["mat_code"], r["set_qty"], r["maint_qty"], r["remarks"],
                r["pr_part_code"], r["pr_part_code"], r["sagub_cust_code"], r.get("plan_ymd") or "",
                user, user)
        nxcn.commit()
        return {"ok": True, "cnt": len(out_rows), "msg": f"이동전표 {len(out_rows)}건 발행(미확정)",
                "group_seq_from": group_seq_from, "group_seq_to": group_seq}
    except HTTPException:
        nxcn.rollback(); raise
    except Exception as e:
        nxcn.rollback()
        raise HTTPException(500, f"등록 실패: {e}")
    finally:
        nxcn.close()

# ================= 이동전표 조회/인쇄 (부품납품표·부품확인납품표) =================
# ★바코드번호 = "MV"+MAINT_GROUP_SEQ(8자리 0패딩) 확정(2026-08-22, 실측: 화면 이동전표번호 195245 = 인쇄물 바코드 MV00195245).
#   레거시 dw_pr_input_586_p1(개별 카드)·p2(그룹묶음, 8행/페이지) 재현.
@router.get("/api/gagong/move580/sheets")
def gagong_move580_sheets(from_ymd: str = Query(""), to_ymd: str = Query(""),
                          item: str = Query(""), part: str = Query(""), confirm: str = Query("전체"), limit: int = Query(2500)):
    """구분=이동전표 모드 — MAINT_GROUP_SEQ 단위로 발행된 전표 목록(확정여부 포함).
       ★라이브(레거시 발행분) + nx(웹 발행분) 합산 조회. 쓰기는 nx만(§1)."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["m.MAINT_TAG='B'"]; p = []
        if from_ymd: w.append("m.MAINT_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("m.MAINT_YMD<=?"); p.append(_d6(to_ymd))
        if item.strip(): w.append("m.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if part.strip(): w.append("m.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if confirm.strip() == "미확정": w.append("m.IN_CONFIRM_FLAG='0'")
        elif confirm.strip() == "확정": w.append("m.IN_CONFIRM_FLAG='1'")
        wsql = ' AND '.join(w)
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))}
              u.MAINT_YMD, u.MAINT_SEQ, u.MAINT_GROUP_SEQ, u.CHECK_LIST_SEQ,
              COALESCE(pg.GAGONG_PROC_DESC, u.PR_PART_CODE, cc.CUST_DESC, '') dest,
              u.ITEM_CODE, u.MAT_CODE, ISNULL(mi.ITEM_DESC,'') nm, ISNULL(su.RACK_NO,'') rack,
              u.MAINT_QTY, u.IN_CONFIRM_FLAG, ISNULL(u.IN_CONFIRM_DATETIME,'') confirm_dt,
              ISNULL(u.IN_CONFIRM_USER_ID,'') confirm_user
            FROM (
              SELECT m.MAINT_YMD,m.MAINT_SEQ,m.MAINT_GROUP_SEQ,m.CHECK_LIST_SEQ,m.PR_PART_CODE,m.SAGUB_CUST_CODE,
                     m.ITEM_CODE,m.MAT_CODE,m.MAINT_QTY,m.IN_CONFIRM_FLAG,m.IN_CONFIRM_DATETIME,m.IN_CONFIRM_USER_ID
                FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_GAGONG_MOVE m WHERE {wsql}
              UNION ALL
              SELECT m.MAINT_YMD,m.MAINT_SEQ,m.MAINT_GROUP_SEQ,m.CHECK_LIST_SEQ,m.PR_PART_CODE,m.SAGUB_CUST_CODE,
                     m.ITEM_CODE,m.MAT_CODE,m.MAINT_QTY,m.IN_CONFIRM_FLAG,m.IN_CONFIRM_DATETIME,m.IN_CONFIRM_USER_ID
                FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE m WHERE {wsql}
            ) u
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM mi ON mi.ITEM_CODE=u.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB su ON su.ITEM_CODE=u.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=u.PR_PART_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=u.SAGUB_CUST_CODE
            ORDER BY u.MAINT_GROUP_SEQ DESC, u.MAINT_SEQ""", *(p + p))
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            g = dict(zip(cols, r))
            rows.append({"ymd": g["MAINT_YMD"], "seq": g["MAINT_SEQ"], "group_seq": g["MAINT_GROUP_SEQ"],
                         "check_seq": g["CHECK_LIST_SEQ"], "dest": g["dest"] or "",
                         "assy": g["ITEM_CODE"], "mat": g["MAT_CODE"], "nm": g["nm"], "rack": g["rack"],
                         "qty": float(g["MAINT_QTY"] or 0), "confirmed": g["IN_CONFIRM_FLAG"] == "1",
                         "confirm_dt": str(g["confirm_dt"] or ""), "confirm_user": g["confirm_user"],
                         "sheet_no": "MV" + str(g["MAINT_GROUP_SEQ"]).zfill(8)})
        return {"rows": rows, "cnt": len(rows)}
    finally:
        nx.close()

@router.get("/api/gagong/move580/print")
def gagong_move580_print(group_from: int = Query(...), group_to: int = Query(None)):
    """부품납품표(개별카드)+부품확인/납품표(그룹묶음) 인쇄용 데이터. group_to 없으면 group_from 단건."""
    gt = group_to if group_to is not None else group_from
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT u.MAINT_YMD, u.MAINT_GROUP_SEQ, u.MAINT_SEQ,
              -- ★2026-08-24 외주(사급) 출고분 라인칸 빈값 수정.
              --   PR_PART_CODE 가 NULL 이 아니라 ''(빈문자열)이라 COALESCE 가 거기서 멈춰
              --   뒤의 거래처명까지 못 갔다. NULLIF 로 빈문자열을 NULL 로 바꿔 건너뛰게 한다.
              --   (실측 MJU66763703: PR_PART_CODE='' / SAGUB_CUST_CODE=2148 → 대원산업)
              COALESCE(NULLIF(LTRIM(RTRIM(pg.GAGONG_PROC_DESC)),''),
                       NULLIF(LTRIM(RTRIM(u.PR_PART_CODE)),''),
                       NULLIF(LTRIM(RTRIM(cc.CUST_DESC)),''), '') line,
              u.ITEM_CODE, u.MAT_CODE, ISNULL(su.RACK_NO,'') rack, u.MAINT_QTY
            FROM (
              SELECT m.MAINT_YMD,m.MAINT_GROUP_SEQ,m.MAINT_SEQ,m.PR_PART_CODE,m.SAGUB_CUST_CODE,m.ITEM_CODE,m.MAT_CODE,m.MAINT_QTY
                FROM PARTNER_ERP.dbo.PU_T_STOCK_MAINT_GAGONG_MOVE m
               WHERE m.MAINT_GROUP_SEQ BETWEEN ? AND ? AND m.MAINT_TAG='B'
              UNION ALL
              SELECT m.MAINT_YMD,m.MAINT_GROUP_SEQ,m.MAINT_SEQ,m.PR_PART_CODE,m.SAGUB_CUST_CODE,m.ITEM_CODE,m.MAT_CODE,m.MAINT_QTY
                FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE m
               WHERE m.MAINT_GROUP_SEQ BETWEEN ? AND ? AND m.MAINT_TAG='B'
            ) u
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB su ON su.ITEM_CODE=u.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=u.PR_PART_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=u.SAGUB_CUST_CODE
            ORDER BY u.MAINT_GROUP_SEQ, u.MAINT_SEQ""", group_from, gt, group_from, gt)
        cols = [d[0] for d in cur.description]
        raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        groups = {}
        for r in raw:
            gs = r["MAINT_GROUP_SEQ"]
            grp = groups.setdefault(gs, {"group_seq": gs, "sheet_no": "MV" + str(gs).zfill(8),
                                          "ymd": r["MAINT_YMD"], "line": r["line"] or "", "items": []})
            grp["items"].append({"assy": r["ITEM_CODE"], "mat": r["MAT_CODE"], "rack": r["rack"] or "",
                                  "qty": float(r["MAINT_QTY"] or 0)})
        return {"groups": list(groups.values())}
    finally:
        nx.close()

# ================= 이동전표 삭제(발행취소) =================
# ★nx 에 웹이 발행한 전표만 지운다. 라이브(레거시 발행분)는 건드리지 않는다(§1 절대규칙).
#   입고확인(IN_CONFIRM_FLAG='1')된 전표는 이미 재고가 움직였으므로 삭제 불가.
@router.post("/api/gagong/move580/delete")
def gagong_move580_delete(payload: dict = Body(...)):
    """선택한 이동전표(MAINT_YMD+MAINT_SEQ 키) 삭제. keys=[{ymd,seq}, ...]"""
    keys = payload.get("keys") or []
    if not keys:
        raise HTTPException(400, "삭제할 전표를 선택하세요.")
    nxcn = _nx(); cur = nxcn.cursor()
    try:
        done = 0; locked = []
        for k in keys:
            ymd = _d6(str(k.get("ymd") or "").strip())
            try: seq = int(k.get("seq"))
            except Exception: continue
            if not ymd: continue
            cur.execute("""SELECT ISNULL(IN_CONFIRM_FLAG,'0'), MAINT_GROUP_SEQ
                FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE WHERE MAINT_YMD=? AND MAINT_SEQ=?""", ymd, seq)
            row = cur.fetchone()
            if not row:
                continue                      # nx 에 없음 = 레거시 발행분(삭제 대상 아님)
            if row[0] == '1':
                locked.append(int(row[1] or 0)); continue
            cur.execute("DELETE FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE WHERE MAINT_YMD=? AND MAINT_SEQ=?", ymd, seq)
            done += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 1
        nxcn.commit()
        msg = "%d건 삭제" % done
        if locked: msg += " · 입고확인된 %d건은 제외" % len(locked)
        if done == 0 and locked: msg = "입고확인된 전표는 삭제할 수 없습니다."
        if done == 0 and not locked: msg = "삭제 가능한 전표가 없습니다(레거시 발행분은 웹에서 지울 수 없습니다)."
        return {"ok": done > 0, "deleted": done, "locked": len(locked), "msg": msg}
    except HTTPException:
        nxcn.rollback(); raise
    except Exception as e:
        nxcn.rollback()
        raise HTTPException(500, "삭제 실패: %s" % e)
    finally:
        nxcn.close()
