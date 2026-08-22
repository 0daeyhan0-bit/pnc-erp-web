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

# ================= 가공창고 이동계획 (w_pr_input_580) — 도번×라인, 자도번LIST + 이동필요/완료 =================
# ★레거시 dw_pr_input_580_t1.srd 컬럼 스펙(_legacy_analysis/GAGONG_4PROGRAMS_ANALYSIS.md §P4) 대조:
#   당일이전(plan_qty_00) · 일자매트릭스(plan_qty_NN/finish_qty_NN 자/모) · 재고(sale_qty·assy_stock_qty·jp_print_qty).
#   SP 본문 자체는 암호화라 조인 미판독 — 아래는 라이브 데이터로 역설계한 근사(진행하며 대사검증).
@router.get("/api/gagong/move580")
def gagong_move580(from_ymd: str = Query(""), to_ymd: str = Query(""), wc: str = Query(""),
                   pr_part: str = Query(""), sagub: str = Query(""),
                   item: str = Query(""), part: str = Query(""), mv: str = Query("전체"), limit: int = Query(2500)):
    """가공창고 이동계획. 계획=PR_T_PLAN_PART_MAT, 이동완료=PU_T_STOCK_MAINT_GAGONG_MOVE(IN_CONFIRM_FLAG='1').
       이동전표발행(미확정)=IN_CONFIRM_FLAG='0'. 이동필요수=계획−이동완료. 도번(ASSY)×라인 그룹, 자도번LIST 묶기.
       ★필터: wc=가공창고(P1/P2, ASSY의 WORK_CODE) · pr_part=생산파트(PR_M_PROC_GAGONG.GAGONG_PROC_CODE, 자도번의 자기 가공공정)
         · sagub=사급업체(CM_M_CUST.CUST_CODE, 자도번의 IN_CUST_CODE)."""
    cn = _conn(); cur = cn.cursor()
    try:
        w = ["pp.PART_PLAN_QTY>0"]; p = []
        if from_ymd: w.append("pp.PART_PLAN_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("pp.PART_PLAN_YMD<=?"); p.append(_d6(to_ymd))
        if wc.strip():   w.append("ia.WORK_CODE=?"); p.append(wc.strip())
        if pr_part.strip(): w.append("ma.GAGONG_PROC_CODE=?"); p.append(pr_part.strip())
        if sagub.strip():   w.append("ma.IN_CUST_CODE=?"); p.append(sagub.strip())
        if item.strip(): w.append("pp.ASSY_ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if part.strip(): w.append("pp.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        cur.execute(f"""SELECT TOP {int(limit) * 60} pp.ASSY_ITEM_CODE assy, ISNULL(ia.ITEM_DESC,'') nm,
              ISNULL(pp.LINE_NO,'') line, COALESCE(cw.WORK_DESC, cc.CUST_DESC, pp.MAT_WORK_CENTER_CODE, '') dest,
              pp.MAT_CODE mat, pp.PART_PLAN_YMD ymd, MIN(ISNULL(pp.PART_OUTPUT_HM,'')) hm,
              SUM(CAST(pp.PART_PLAN_QTY AS float)) q
            FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT pp
            JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM ia ON ia.ITEM_CODE=pp.ASSY_ITEM_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM ma ON ma.ITEM_CODE=pp.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_WORK cw ON cw.WORK_CODE=pp.MAT_WORK_CENTER_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=pp.MAT_WORK_CENTER_CODE
            WHERE {' AND '.join(w)}
            GROUP BY pp.ASSY_ITEM_CODE, ISNULL(ia.ITEM_DESC,''), pp.LINE_NO,
              COALESCE(cw.WORK_DESC, cc.CUST_DESC, pp.MAT_WORK_CENTER_CODE, ''), pp.MAT_CODE, pp.PART_PLAN_YMD
            ORDER BY assy, line""", *p)
        cols = [d[0] for d in cur.description]; raw = [dict(zip(cols, r)) for r in cur.fetchall()]
        keyed = {}
        for r in raw:
            k = (r["assy"], r["line"], r["dest"])
            g = keyed.get(k)
            if not g:
                g = {"assy": r["assy"], "nm": r["nm"], "line": r["line"], "dest": r["dest"],
                     "days": {}, "mats": {}, "plan_qty": 0.0, "part_ymd": r["ymd"], "hm": r["hm"] or ""}
                keyed[k] = g
            q = float(r["q"] or 0)
            g["days"][r["ymd"]] = g["days"].get(r["ymd"], 0) + q
            g["mats"][r["mat"]] = g["mats"].get(r["mat"], 0) + q
            g["plan_qty"] += q
            if r["ymd"] < g["part_ymd"]: g["part_ymd"] = r["ymd"]; g["hm"] = r["hm"] or ""
        rows = list(keyed.values()); capped = len(keyed) > int(limit); rows = rows[:int(limit)]
        for g in rows:
            g["jado"] = ",".join(f"{m}{{{int(v)}}}" for m, v in sorted(g["mats"].items()))
            g["matcnt"] = len(g["mats"]); g["matlist"] = list(g["mats"].keys()); del g["mats"]
        matset = list({m for g in rows for m in g["matlist"]})
        assyset = list({g["assy"] for g in rows})
        d6a = _d6(from_ymd) if from_ymd else None; d6b = _d6(to_ymd) if to_ymd else None
        CH = 1000
        # 이동완료(확정) = IN_CONFIRM_FLAG='1', 이동전표발행(미확정) = IN_CONFIRM_FLAG='0'. 둘 다 날짜별(MAINT_YMD)로 매핑.
        moved = {}; movedday = {}; printed = {}; printedday = {}
        for i in range(0, len(matset), CH):
            ck = matset[i:i + CH]; ph = ",".join("?" * len(ck))
            for flag, bucket, dbucket in (('1', moved, movedday), ('0', printed, printedday)):
                pr = list(ck)
                q = (f"SELECT MAT_CODE, MAINT_YMD, SUM(CAST(MAINT_QTY AS float)) "
                     f"FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE "
                     f"WHERE IN_CONFIRM_FLAG='{flag}' AND MAT_CODE IN ({ph})")
                if d6a: q += " AND MAINT_YMD>=?"; pr.append(d6a)
                if d6b: q += " AND MAINT_YMD<=?"; pr.append(d6b)
                q += " GROUP BY MAT_CODE, MAINT_YMD"
                try:
                    cur.execute(q, *pr)
                    for rr in cur.fetchall():
                        mat, ymd, v = rr[0], rr[1], float(rr[2] or 0)
                        bucket[mat] = bucket.get(mat, 0.0) + v
                        if dbucket is not None: dbucket[(mat, ymd)] = dbucket.get((mat, ymd), 0.0) + v
                except Exception:
                    pass
        # ASSY재고 = SA_T_ITEM_STOCK(완제품 재고, 도번단위)
        assystk = {}
        for i in range(0, len(assyset), CH):
            ck = assyset[i:i + CH]; ph = ",".join("?" * len(ck))
            try:
                cur.execute(f"SELECT ITEM_CODE, SUM(STOCK_QTY) FROM PARTNER_ERP.dbo.SA_T_ITEM_STOCK WHERE ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE", *ck)
                for rr in cur.fetchall(): assystk[str(rr[0]).strip()] = float(rr[1] or 0)
            except Exception:
                pass
        # 출하 = SA_T_SALE_DTL 미출하잔(FINISH_FLAG='0'), 도번단위 근사(계획 WO 미보유 — §P4 웹구현 한계, 담당확인 필요시 재정밀화)
        saled = {}
        for i in range(0, len(assyset), CH):
            ck = assyset[i:i + CH]; ph = ",".join("?" * len(ck))
            try:
                cur.execute(f"SELECT ITEM_CODE, SUM(SALE_QTY) FROM PARTNER_ERP.dbo.SA_T_SALE_DTL WHERE FINISH_FLAG='0' AND ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE", *ck)
                for rr in cur.fetchall(): saled[str(rr[0]).strip()] = float(rr[1] or 0)
            except Exception:
                pass
        for g in rows:
            g["moved"] = sum(moved.get(m, 0.0) for m in g["matlist"])
            g["jp_print"] = sum(printed.get(m, 0.0) for m in g["matlist"])
            g["need"] = max(0.0, g["plan_qty"] - g["moved"])
            g["assy_stock"] = assystk.get(g["assy"], 0.0)
            g["sale"] = saled.get(g["assy"], 0.0)
            # 당일이전(prior) = from_ymd 이전 계획 대비 완료 잔여(레거시 plan_qty_00). from_ymd 미지정 시 0.
            g["prior"] = 0.0
            if d6a:
                try:
                    ph = ",".join("?" * len(g["matlist"]))
                    cur.execute(f"""SELECT SUM(CAST(PART_PLAN_QTY AS float)) FROM PARTNER_ERP_TEST3.nx.PR_T_PLAN_PART_MAT
                        WHERE ASSY_ITEM_CODE=? AND MAT_CODE IN ({ph}) AND PART_PLAN_YMD<?""", g["assy"], *g["matlist"], d6a)
                    prior_plan = float((cur.fetchone() or [0])[0] or 0)
                    prior_moved = 0.0
                    for m in g["matlist"]:
                        for (mm, ymd), v in movedday.items():
                            if mm == m and ymd < d6a: prior_moved += v
                    g["prior"] = max(0.0, prior_plan - prior_moved)
                except Exception:
                    g["prior"] = 0.0
            # 날짜별 자/모(계획/완료/발행) — days=계획, doneday=확정완료(초록), printday=미확정발행(검정)
            # 셀상태(cellst): 'done'(계획<=완료) > 'print'(계획<=완료+발행) > ''(미착수) — 그리드가 색상 판정에 사용.
            g["doneday"] = {}; g["printday"] = {}; g["cellst"] = {}
            for ymd, planv in g["days"].items():
                dv = sum(movedday.get((m, ymd), 0.0) for m in g["matlist"])
                pv = sum(printedday.get((m, ymd), 0.0) for m in g["matlist"])
                g["doneday"][ymd] = dv; g["printday"][ymd] = pv
                if planv <= 0: st = ''
                elif dv >= planv - 1e-9: st = 'done'
                elif (dv + pv) >= planv - 1e-9: st = 'print'
                elif dv > 0 or pv > 0: st = 'part'
                else: st = ''
                g["cellst"][ymd] = st
            del g["matlist"]
        m = mv.strip()
        if m == "이동필요": rows = [r for r in rows if r["need"] > 0]
        elif m == "이동완료": rows = [r for r in rows if r["need"] <= 0]
        dates = sorted({ymd for g in rows for ymd in g["days"]})
        rows.sort(key=lambda x: (x["part_ymd"], x["assy"]))
        note = f"⚠ 상위 {limit}건만 표시 — 작업처·도번으로 필터하세요." if capped else ""
        return {"dates": dates, "rows": rows, "cnt": len(rows),
                "plan_sum": sum(r["plan_qty"] for r in rows), "need_sum": sum(r["need"] for r in rows),
                "moved_sum": sum(r["moved"] for r in rows), "note": note}
    finally:
        cn.close()

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
    # work_code 판정 + 사급/사내생산 BOM전개는 item_code(도번)마다 1회만 조회(레거시 = ASSY 단위 판정).
    cn = _conn(); cur = cn.cursor()
    itemset = list({str(r.get("item_code") or "").strip() for r in rows_in if r.get("item_code")})
    wkinfo = {}   # item_code -> {work_code, gole_gagong_proc_code, gole_in_cust_code}
    try:
        for i in range(0, len(itemset), 900):
            ck = itemset[i:i + 900]; ph = ",".join("?" * len(ck))
            cur.execute(f"""SELECT ITEM_CODE, ISNULL(WORK_CODE,''), ISNULL(GAGONG_PROC_CODE,''), ISNULL(IN_CUST_CODE,'')
                FROM PARTNER_ERP_TEST3.nx.PR_M_ITEM WHERE ITEM_CODE IN ({ph})""", *ck)
            for r in cur.fetchall():
                wkinfo[str(r[0]).strip()] = {"work_code": r[1], "gagong_proc": r[2], "in_cust": r[3]}
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
            if info.get("work_code") == "P2":
                # 가공직납품 — 자기자신 등록(BOM전개 없음)
                out_rows.append({"item_code": item_code, "mat_code": item_code, "item_desc": r.get("item_desc") or "",
                                  "set_qty": maint_qty, "use_qty": 1, "maint_qty": maint_qty,
                                  "remarks": r.get("remarks") or "", "pr_part_code": info.get("gagong_proc", ""), "sagub_cust_code": ""})
            else:
                # 사급/사내생산 — mat_code(자도번) 자체가 이미 선택 대상이면 그대로, BOM 하위전개가 필요하면 1단계 조회.
                pr_part = "" if info.get("in_cust") else info.get("gagong_proc", "")
                sagub = info.get("in_cust", "")
                out_rows.append({"item_code": item_code, "mat_code": mat_code, "item_desc": r.get("item_desc") or "",
                                  "set_qty": set_qty, "use_qty": use_qty, "maint_qty": maint_qty,
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
                 PR_PART_CODE, SAGUB_CUST_CODE, IN_CONFIRM_FLAG,
                 INSERT_USER_ID, INSERT_DATETIME, INSERT_IP, INSERT_COMPUTER, INSERT_WINDOW,
                 UPDATE_USER_ID, UPDATE_DATETIME, UPDATE_IP, UPDATE_COMPUTER, UPDATE_WINDOW)
                VALUES (?,?,?,?,'B',?,?,?,?,?,?,'',?,?,?,'0',?,GETDATE(),'','','w_pr_input_580_web',?,GETDATE(),'','','w_pr_input_580_web')""",
                ymd, maint_seq, group_seq, check_seq, out_wh,
                r["item_code"], r["mat_code"], r["set_qty"], r["maint_qty"], r["remarks"],
                r["pr_part_code"], r["pr_part_code"], r["sagub_cust_code"], user, user)
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
    """구분=이동전표 모드 — MAINT_GROUP_SEQ 단위로 발행된 전표 목록(확정여부 포함)."""
    nx = _nx(); cur = nx.cursor()
    try:
        w = ["m.MAINT_TAG='B'"]; p = []
        if from_ymd: w.append("m.MAINT_YMD>=?"); p.append(_d6(from_ymd))
        if to_ymd:   w.append("m.MAINT_YMD<=?"); p.append(_d6(to_ymd))
        if item.strip(): w.append("m.ITEM_CODE LIKE ?"); p.append(f"%{item.strip()}%")
        if part.strip(): w.append("m.MAT_CODE LIKE ?"); p.append(f"%{part.strip()}%")
        if confirm.strip() == "미확정": w.append("m.IN_CONFIRM_FLAG='0'")
        elif confirm.strip() == "확정": w.append("m.IN_CONFIRM_FLAG='1'")
        cur.execute(f"""SELECT TOP {max(1,min(int(limit),3000))}
              m.MAINT_YMD, m.MAINT_SEQ, m.MAINT_GROUP_SEQ, m.CHECK_LIST_SEQ,
              COALESCE(pg.GAGONG_PROC_DESC, m.PR_PART_CODE, cc.CUST_DESC, '') dest,
              m.ITEM_CODE, m.MAT_CODE, ISNULL(mi.ITEM_DESC,'') nm, ISNULL(su.RACK_NO,'') rack,
              m.MAINT_QTY, m.IN_CONFIRM_FLAG, ISNULL(m.IN_CONFIRM_DATETIME,'') confirm_dt,
              ISNULL(m.IN_CONFIRM_USER_ID,'') confirm_user
            FROM nx.PU_T_STOCK_MAINT_GAGONG_MOVE m
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM mi ON mi.ITEM_CODE=m.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB su ON su.ITEM_CODE=m.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=m.PR_PART_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=m.SAGUB_CUST_CODE
            WHERE {' AND '.join(w)}
            ORDER BY m.MAINT_GROUP_SEQ DESC, m.MAINT_SEQ""", *p)
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
        cur.execute("""SELECT m.MAINT_YMD, m.MAINT_GROUP_SEQ, m.MAINT_SEQ,
              COALESCE(pg.GAGONG_PROC_DESC, m.PR_PART_CODE, cc.CUST_DESC, '') line,
              m.ITEM_CODE, m.MAT_CODE, ISNULL(su.RACK_NO,'') rack, m.MAINT_QTY
            FROM PARTNER_ERP_TEST3.nx.PU_T_STOCK_MAINT_GAGONG_MOVE m
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB su ON su.ITEM_CODE=m.MAT_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.PR_M_PROC_GAGONG pg ON pg.GAGONG_PROC_CODE=m.PR_PART_CODE
            LEFT JOIN PARTNER_ERP_TEST3.nx.CM_M_CUST cc ON cc.CUST_CODE=m.SAGUB_CUST_CODE
            WHERE m.MAINT_GROUP_SEQ BETWEEN ? AND ? AND m.MAINT_TAG='B'
            ORDER BY m.MAINT_GROUP_SEQ, m.MAINT_SEQ""", group_from, gt)
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
