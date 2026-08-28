# -*- coding: utf-8 -*-
"""자재입고진행현황 — 레거시 w_pr_input_010_part 이식 (1차: 핵심 컬럼).

기준일부터 N근무일 동안, 자재(자도번)별 소요계획과 진행상태를 보여준다.

★구분 4종 (레거시 라디오) — IN/OUT 은 INPUT 만(사용자 지정)
   전체   : 자도번 집계행 + 그 아래 제번 상세  (화면에서 클릭 펼침/접힘)
   집계   : 자도번 집계행만
   제번   : 제번 상세만
   도번별 : 도번 단위 + 도번 소계 (도번재고 3종 함께)

★원천 (전부 nx — 라이브 무접근)
   · 소요   = nx.plan_part_mat   (제번×자도번×일자, part_plan_qty)
   · 계획   = nx.plan_part_dtl   (라인·LG INPUT(output_hm)·LOT수량)
   · 근무일 = nx.HR_M_CALENDAR   (레거시와 동일: work_team='A', time_type='A',
                                  work_stats IN ('1','2','5','6'))
   · 재고   = nx.PU_T_MAT_STOCK_WH(자재창고) / nx.PR_T_MAT_STOCK_WH(생산파트)
   실측 대조(그린산업 2005 · 기준일 260828): 레거시 첫 행 ADM72950717/EBE60659006/
   라인 CM/LOT 4/31월 4-4  =  웹 6I1M0BB8(CM, 260831, lot 4, qty 4).

★1차 범위 = 식별·일자·수량·재고. 모델/지름/두께/길이/중량/단가/재고금액은 2차.
"""
from fastapi import APIRouter, Query, HTTPException
from common import _nx, _d6

router = APIRouter()


def _workdays(cur, base, days):
    """일자축 — ★기준일부터 '달력일'로 이어 붙이되 근무일이 N일 찰 때까지.

    레거시 실측(기준일 260828 · 4일): 화면 헤더가 28금·29토·30일·31월·01화·02수 6칸.
    8/28(금)은 HR_M_CALENDAR work_stats=4 → 휴무, 29토·30일도 휴무라 값이 0/0 으로
    비어 있고, 근무일은 31·01·02·03 4일이다. 즉 휴무일도 칸으로는 나오고
    '4일'은 근무일 기준으로 센다. 근무일만 뽑으면 기준일이 통째로 사라진다.
    """
    from datetime import datetime, timedelta
    n = max(1, min(int(days or 4), 31))
    cur.execute("""SELECT SUBSTRING(calendar_yymd,3,6), work_stats
                     FROM nx.HR_M_CALENDAR WITH(NOLOCK)
                    WHERE work_team='A' AND time_type='A'
                      AND calendar_yymd BETWEEN '20'+? AND '20'+?
                    ORDER BY calendar_yymd""",
                base, (datetime.strptime("20" + base, "%Y%m%d")
                       + timedelta(days=90)).strftime("%y%m%d"))
    st = {str(a).strip(): str(b).strip() for a, b in cur.fetchall()}
    out = []; work = 0
    d = datetime.strptime("20" + base, "%Y%m%d")
    for _ in range(120):             # 안전 상한
        ymd = d.strftime("%y%m%d")
        is_work = st.get(ymd, "1") in ("1", "2", "5", "6")   # 달력 미등록=근무 취급
        out.append({"ymd": ymd, "work": 1 if is_work else 0})
        if is_work:
            work += 1
        d += timedelta(days=1)
        if work >= n:
            break
    return out


@router.get("/api/matinput/list")
def matinput_list(base_ymd: str = Query(""), days: int = Query(4),
                  gubun: str = Query("all"), cust: str = Query(""),
                  line: str = Query(""), wo: str = Query(""),
                  doban: str = Query(""), jadoban: str = Query(""),
                  limit: int = Query(4000)):
    """gubun: all=전체 / sum=집계 / wo=제번 / doban=도번별."""
    b6 = _d6(base_ymd)
    if len(b6) != 6:
        raise HTTPException(400, "기준일자가 필요합니다.")
    if gubun not in ("all", "sum", "wo", "doban"):
        raise HTTPException(400, "구분이 올바르지 않습니다.")
    nx = _nx(); cur = nx.cursor()
    try:
        cal = _workdays(cur, b6, days)          # [{ymd, work}] — 휴무일 칸 포함
        dl = [x["ymd"] for x in cal]
        d_from, d_to = dl[0], dl[-1]
        w = ["m.part_plan_ymd BETWEEN ? AND ?"]; p = [d_from, d_to]
        # ★자도번작업처 = 코드 정확일치 우선(레거시 동일).
        #   이름 LIKE 로 받으면 '산업' 같은 부분일치로 다른 업체가 섞인다(사용자 지적).
        #   코드가 아닌 값이 들어오면 그때만 이름 정확일치로 폴백.
        cc = str(cust or "").strip()
        if cc:
            w.append("""(RTRIM(m.mat_work_center_code)=? OR EXISTS(
                          SELECT 1 FROM nx.CM_M_CUST c2 WITH(NOLOCK)
                           WHERE c2.CUST_CODE=RTRIM(m.mat_work_center_code)
                             AND RTRIM(c2.CUST_DESC)=?))""")
            p += [cc, cc]
        if wo.strip():
            w.append("m.work_order LIKE ?"); p.append(f"%{wo.strip()}%")
        if doban.strip():
            w.append("m.assy_item_code LIKE ?"); p.append(f"%{doban.strip()}%")
        if jadoban.strip():
            w.append("m.mat_code LIKE ?"); p.append(f"%{jadoban.strip()}%")
        if line.strip() and line.strip() != "%":
            w.append("RTRIM(ISNULL(d.line_no,''))=?"); p.append(line.strip())

        # 제번 상세 — 소요(plan_part_mat) ⋈ 계획(plan_part_dtl, 라인·시각·LOT)
        cur.execute(f"""SELECT TOP {max(1, min(int(limit), 20000))}
              m.work_order, m.split_work_order, m.assy_item_code, m.item_code,
              m.mat_code, RTRIM(ISNULL(m.mat_work_center_code,'')) cc,
              m.part_plan_ymd, ISNULL(m.part_output_hm,'') hm,
              ISNULL(m.plan_ymd,'') plan_ymd,
              CAST(ISNULL(m.part_plan_qty,0) AS float) qty,
              RTRIM(ISNULL(d.line_no,'')) line_no, ISNULL(d.output_hm,'') lg_hm,
              CAST(ISNULL(d.lot_qty,0) AS float) lot_qty,
              ISNULL(i1.item_name,'') dnm, ISNULL(i2.item_name,'') jnm,
              ISNULL(c.CUST_DESC,'') cnm, ISNULL(m.bom_level,'') lv,
              -- ★2차 컬럼: 모델 / 치수·중량 / 단가  (자도번 기준, 없으면 bom_dim 폴백)
              ISNULL(pd.MODEL_NO,'') model,
              CAST(ISNULL(NULLIF(i2.diam,0),   ISNULL(bd.fin_diam,0))   AS float) dia,
              CAST(ISNULL(NULLIF(i2.thick,0),  ISNULL(bd.fin_thick,0))  AS float) thk,
              CAST(ISNULL(NULLIF(i2.length,0), ISNULL(bd.fin_length,0)) AS float) len,
              CAST(ISNULL(NULLIF(i2.item_weight,0),
                   ISNULL(NULLIF(i2.net_weight,0), ISNULL(bd.fin_weight,0))) AS float) wgt,
              -- ★단가 = nx.price_item(웹 정본). nx.item.item_cost 는 전체 0건이라 못 쓴다.
              --   작업처(vendor)별 매입단가 중 소요일 이하 최신 1건.
              CAST(ISNULL((SELECT TOP 1 pi.price FROM nx.price_item pi WITH(NOLOCK)
                            WHERE pi.item_code=m.mat_code
                              AND pi.vendor_code=RTRIM(m.mat_work_center_code)
                              AND pi.price_type=N'매입'
                              AND pi.apply_ymd<=m.part_plan_ymd
                            ORDER BY pi.apply_ymd DESC),0) AS float) cost
            FROM nx.plan_part_mat m WITH(NOLOCK)
            LEFT JOIN nx.plan_dtl pd WITH(NOLOCK) ON pd.WORK_ORDER=m.work_order
            LEFT JOIN nx.bom_dim bd WITH(NOLOCK) ON bd.item_code=m.mat_code
            LEFT JOIN nx.plan_part_dtl d WITH(NOLOCK)
              ON d.work_order=m.work_order AND d.split_work_order=m.split_work_order
             AND d.assy_item_code=m.assy_item_code AND d.item_code=m.item_code
            LEFT JOIN nx.item i1 WITH(NOLOCK) ON i1.item_code=m.assy_item_code
            LEFT JOIN nx.item i2 WITH(NOLOCK) ON i2.item_code=m.mat_code
            LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=RTRIM(m.mat_work_center_code)
           WHERE {' AND '.join(w)}
           ORDER BY m.mat_code, m.assy_item_code, m.part_plan_ymd, m.work_order""", *p)
        raw = []
        for r in cur.fetchall():
            g = lambda i: str(r[i] if r[i] is not None else "").strip()
            raw.append({"wo": g(0), "swo": g(1), "doban": g(2), "item": g(3),
                        "jadoban": g(4), "cc": g(5), "ymd": g(6), "hm": g(7),
                        "pymd": g(8),                       # ★생산계획일 = 레거시 정렬 1순위
                        "qty": float(r[9] or 0), "line": g(10), "lg_hm": g(11),
                        "lot_qty": float(r[12] or 0), "dnm": g(13), "jnm": g(14),
                        "cnm": g(15), "lv": g(16),
                        "model": g(17),
                        "dia": float(r[18] or 0), "thk": float(r[19] or 0),
                        "len": float(r[20] or 0), "wgt": float(r[21] or 0),
                        "cost": float(r[22] or 0)})
        # 재고 — 자도번(자재창고) · 생산(파트합계) · 도번고정
        jset = {x["jadoban"] for x in raw if x["jadoban"]}
        dset = {x["doban"] for x in raw if x["doban"]}
        st_j = {}; st_p = {}; st_d = {}
        def _fill(codes, sql, into):
            cl = [x for x in codes if x]
            for i in range(0, len(cl), 900):
                ch = cl[i:i + 900]; ph = ",".join("?" * len(ch))
                try:
                    cur.execute(sql.format(ph=ph), *ch)
                    for a, b in cur.fetchall():
                        into[str(a).strip()] = float(b or 0)
                except Exception:
                    pass
        _fill(jset, """SELECT MAT_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.PU_T_MAT_STOCK_WH
                        WITH(NOLOCK) WHERE MAT_CODE IN ({ph}) GROUP BY MAT_CODE""", st_j)
        _fill(jset, """SELECT MAT_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.PR_T_MAT_STOCK_WH
                        WITH(NOLOCK) WHERE MAT_CODE IN ({ph}) GROUP BY MAT_CODE""", st_p)
        _fill(dset, """SELECT MAT_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.PU_T_MAT_STOCK_WH
                        WITH(NOLOCK) WHERE MAT_CODE IN ({ph}) GROUP BY MAT_CODE""", st_d)
        # ★2차: ASSY재고(도번=완제품) · 요청수량(세트입고요청) · 생산실적
        st_a = {}; req = {}; prd = {}
        _fill(dset, """SELECT ITEM_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.SA_T_ITEM_STOCK
                        WITH(NOLOCK) WHERE ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE""", st_a)
        # ★요청수량 = 미확정 세트입고요청, **자도번(MAT_CODE) 기준**(사용자 확인).
        _fill(jset, f"""SELECT MAT_CODE, SUM(ISNULL(MAT_QTY,0))
                          FROM nx.PU_T_SET_INPUT_REQ_DTL WITH(NOLOCK)
                         WHERE MAT_CODE IN ({{ph}}) AND INPUT_YMD BETWEEN '{d_from}' AND '{d_to}'
                           AND ISNULL(CONFIRM_FLAG,'0')<>'1'
                         GROUP BY MAT_CODE""", req)
        _fill(dset, f"""SELECT ITEM_CODE, SUM(ISNULL(PROD_QTY,0))
                          FROM nx.PR_T_PROD_DTL WITH(NOLOCK)
                         WHERE ITEM_CODE IN ({{ph}}) AND PROD_YMD BETWEEN '{d_from}' AND '{d_to}'
                         GROUP BY ITEM_CODE""", prd)
        # ★출하실적 — **제번(LOT) + 도번** 기준(사용자 확인).
        #   품번 누적이면 같은 자도번의 모든 행에 같은 값이 반복되고,
        #   제번만으로 잡으면 그 제번의 다른 도번 출하까지 섞인다.
        #   실측: 레거시 24 = 제번 6I1M09AJ + 도번 AJR77224524 의 출하.
        #   원천 = 웹 자체 nx.sale_dtl (미러 SA_T_SALE_DTL 아님), 미완결분.
        sal = {}
        pairs = sorted({(x["wo"], x["doban"]) for x in raw if x["wo"] and x["doban"]})
        for i in range(0, len(pairs), 400):
            ch = pairs[i:i + 400]
            cond = " OR ".join(["(work_order=? AND item_code=?)"] * len(ch))
            args = [v for pr in ch for v in pr]
            cur.execute(f"""SELECT work_order, item_code, SUM(ISNULL(sale_qty,0))
                              FROM nx.sale_dtl WITH(NOLOCK)
                             WHERE ISNULL(finish_flag,'0')='0' AND ({cond})
                             GROUP BY work_order, item_code""", *args)
            for a, b, q in cur.fetchall():
                sal[(str(a).strip(), str(b).strip())] = float(q or 0)

        # 제번 상세행 — 일자별 칸 채우기
        det = {}
        for x in raw:
            k = (x["jadoban"], x["doban"], x["wo"], x["swo"])
            it = det.setdefault(k, {
                "jadoban": x["jadoban"], "jnm": x["jnm"], "doban": x["doban"], "dnm": x["dnm"],
                "wo": x["wo"], "swo": x["swo"], "cc": x["cc"], "cnm": x["cnm"],
                "line": x["line"], "lg_hm": x["lg_hm"], "lot_qty": x["lot_qty"],
                "pymd": x.get("pymd", ""),      # 생산계획일(정렬 1순위)
                "byday": {}, "qty": 0.0,
                "st_j": st_j.get(x["jadoban"], 0.0), "st_p": st_p.get(x["jadoban"], 0.0),
                "st_d": st_d.get(x["doban"], 0.0),
                # ★2차 컬럼
                "st_a": st_a.get(x["doban"], 0.0),        # ASSY재고(도번)
                "req": req.get(x["jadoban"], 0.0),        # 요청수량(자도번 기준)
                "prod": prd.get(x["doban"], 0.0),         # 생산실적
                "sale": sal.get((x["wo"], x["doban"]), 0.0),   # 출하실적(제번+도번)
                "model": x.get("model", ""),
                "dia": x.get("dia", 0.0), "thk": x.get("thk", 0.0),
                "len": x.get("len", 0.0), "wgt": x.get("wgt", 0.0),
                "cost": x.get("cost", 0.0)})
            it["byday"][x["ymd"]] = it["byday"].get(x["ymd"], 0.0) + x["qty"]
            it["qty"] += x["qty"]
            if not it["line"] and x["line"]:
                it["line"] = x["line"]; it["lg_hm"] = x["lg_hm"]; it["lot_qty"] = x["lot_qty"]
        dets = sorted(det.values(), key=lambda z: (z["jadoban"], z["doban"], z["wo"]))

        # ★서버는 '제번 상세'(가장 세밀한 단위)만 내려준다 — 구분(전체/집계/제번/도번별)
        #   전환은 프론트에서 즉시 집계한다(레거시처럼 재조회 없이 라디오만 눌러 전환).
        #   2026-08-28 사용자요청: "전체 데이터 조회 후 라디오 클릭할 때마다 바뀌게".
        rows = [dict(x, kind="wo") for x in dets]
        tot_day = {d: round(sum((x["byday"].get(d, 0) for x in dets), 0.0), 2) for d in dl}
        return {"base_ymd": b6, "days": dl, "cal": cal, "gubun": gubun,
                "rows": rows, "cnt": len(rows), "det_cnt": len(dets),
                "tot_qty": round(sum(x["qty"] for x in dets), 2),
                "tot_lot": round(sum(x["lot_qty"] for x in dets), 2),
                "tot_day": tot_day}
    finally:
        nx.close()


@router.get("/api/matinput/opts")
def matinput_opts():
    """라인·자도번작업처 드롭다운 — 실제 계획에 쓰인 값만."""
    nx = _nx(); cur = nx.cursor()
    try:
        cur.execute("""SELECT DISTINCT RTRIM(ISNULL(line_no,'')) FROM nx.plan_part_dtl
                        WITH(NOLOCK) WHERE ISNULL(line_no,'')<>'' ORDER BY 1""")
        lines = [str(r[0]).strip() for r in cur.fetchall()]
        # 거래처명이 없는 코드는 제외 — datalist 값이 이름이라 빈 항목이 섞이면 못 고른다
        cur.execute("""SELECT DISTINCT RTRIM(ISNULL(m.mat_work_center_code,'')) cc,
                              ISNULL(c.CUST_DESC,'') nm
                         FROM nx.plan_part_mat m WITH(NOLOCK)
                         JOIN nx.CM_M_CUST c WITH(NOLOCK)
                           ON c.CUST_CODE=RTRIM(m.mat_work_center_code)
                        WHERE ISNULL(m.mat_work_center_code,'')<>''
                          AND ISNULL(c.CUST_DESC,'')<>'' ORDER BY 2""")
        custs = [{"cc": str(a).strip(), "nm": str(b).strip()} for a, b in cur.fetchall()]
        # 도번·자도번 오토컴플리트 후보(§3) — 실제 계획에 쓰인 것만
        def _codes(col):
            cur.execute(f"""SELECT TOP 500 m.{col} code, MAX(ISNULL(i.item_name,'')) nm
                              FROM nx.plan_part_mat m WITH(NOLOCK)
                              LEFT JOIN nx.item i WITH(NOLOCK) ON i.item_code=m.{col}
                             WHERE ISNULL(m.{col},'')<>''
                             GROUP BY m.{col} ORDER BY m.{col}""")
            return [{"code": str(a).strip(), "nm": str(b).strip()} for a, b in cur.fetchall()]
        return {"lines": lines, "custs": custs,
                "dobans": _codes("assy_item_code"), "jados": _codes("mat_code")}
    finally:
        nx.close()
