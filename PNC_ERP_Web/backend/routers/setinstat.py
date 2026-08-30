# -*- coding: utf-8 -*-
"""자재세트입고현황 — 레거시 w_pr_input_130_part 이식.

★자재입고진행현황(w_pr_input_010_part / matinput.py)과 **같은 구조**다.
  차이는 두 가지뿐 —
    · 행 단위 : 자도번(010) → **도번(세트)**(130). 자도번은 'LIST' 로 콤마 나열.
    · 재고    : 단품재고 4갈래(010) → **세트재고**(130, nx.set_stock_maint 잔액)
  협력사가 자기 세트 납품계획을 보는 화면이라 자도번작업처로 거는 게 기본.

★구분 3종(레거시 라디오)
   전체 : 집계행 + 그 아래 제번 상세(화면에서 클릭 펼침)
   집계 : 집계행만
   제번 : 제번 상세만

★원천 (전부 nx — 라이브 무접근)
   · 소요     = nx.plan_part_mat  (제번×도번×자도번×일자, part_plan_qty)
   · 자도번작업처 = plan_part_mat.mat_work_center_code   ← 레거시 '자도번작업처'
   · 계획     = nx.plan_part_dtl  (라인 line_no · LG INPUT output_hm · LOT lot_qty)
   · 근무일   = nx.HR_M_CALENDAR  (010 과 동일 규칙)
   · 세트재고 = nx.set_stock_maint 잔액 SUM (도번×거래처)
  ※「자재세트바코드입고」 버튼은 넣지 않는다 — 입고관리 화면에 이미 있음(사용자 지정).
"""
from fastapi import APIRouter, Query
from common import _nx, _d6

router = APIRouter()


def _workdays(cur, base, days):
    """일자축 — 기준일부터 달력일로 이어 붙이되 근무일이 N일 찰 때까지(010 동일)."""
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
    for _ in range(120):
        ymd = d.strftime("%y%m%d")
        is_work = st.get(ymd, "1") in ("1", "2", "5", "6")
        out.append({"ymd": ymd, "work": 1 if is_work else 0})
        if is_work:
            work += 1
        d += timedelta(days=1)
        if work >= n:
            break
    return out


def _base_ymd(cur):
    """★기준일자 기본값 = **계획 마지막 업로드 일자**(오늘 아님).

    오늘로 잡으면 업로드일~오늘 사이 미처리 계획이 첫 칸에 뭉쳐 표시된다
    (실측: 업로드 260828 · 오늘 260830 → 8/28·29 물량이 30일 칸에 합산).
    원천 = nx.plan_upload_axis.axis_from (STEP7 클램프와 같은 기준),
    없으면 계획 최소일, 그것도 없으면 오늘.
    """
    try:
        cur.execute("""SELECT MAX(axis_from) FROM nx.plan_upload_axis WITH(NOLOCK)
                        WHERE ISNULL(axis_from,'')<>''""")
        v = str((cur.fetchone() or [None])[0] or "").strip()
        if v:
            return v
    except Exception:
        pass
    try:
        cur.execute("""SELECT MIN(plan_ymd) FROM nx.plan_part_mat WITH(NOLOCK)
                        WHERE part_plan_qty>0""")
        v = str((cur.fetchone() or [None])[0] or "").strip()
        if v:
            return v
    except Exception:
        pass
    cur.execute("SELECT FORMAT(GETDATE(),'yyMMdd')")
    return cur.fetchone()[0]


@router.get("/api/setinstat/opts")
def setinstat_opts():
    """조건부 옵션 — 라인 · 작업처(자도번작업처) · 기준일자 기본값."""
    cn = _nx(); cur = cn.cursor()
    try:
        base = _base_ymd(cur)
        cur.execute("""SELECT DISTINCT line_no FROM nx.plan_part_dtl WITH(NOLOCK)
                        WHERE ISNULL(line_no,'')<>'' ORDER BY line_no""")  # noqa
        lines = [str(r[0]).strip() for r in cur.fetchall()]
        # ★자도번작업처 = 자도번의 매입처(pr_m_item.IN_CUST_CODE) — list 와 동일 기준
        cur.execute("""SELECT mi.IN_CUST_CODE cd, ISNULL(c.CUST_DESC,'') nm
                         FROM nx.plan_part_mat m WITH(NOLOCK)
                         JOIN nx.pr_m_item mi WITH(NOLOCK) ON mi.ITEM_CODE=m.mat_code
                         LEFT JOIN nx.CM_M_CUST c WITH(NOLOCK) ON c.CUST_CODE=mi.IN_CUST_CODE
                        WHERE ISNULL(mi.IN_CUST_CODE,'')<>''
                        GROUP BY mi.IN_CUST_CODE, c.CUST_DESC
                        ORDER BY ISNULL(c.CUST_DESC,'')""")
        custs = [{"code": str(a).strip(), "name": (b or "").strip()} for a, b in cur.fetchall()]
        return {"lines": lines, "custs": custs, "base_ymd": base}
    finally:
        cn.close()


@router.get("/api/setinstat/list")
def setinstat_list(base_ymd: str = Query(""), days: int = Query(4),
                   jcust: str = Query("", description="자도번작업처(mat_work_center_code)"),
                   dcust: str = Query("", description="도번작업처"),
                   line: str = Query(""), wo: str = Query(""),
                   doban: str = Query(""), jadoban: str = Query("")):
    """제번×도번 단위 상세 + 일자별 소요. 집계는 프론트가 묶는다(010 동일 방식)."""
    cn = _nx(); cur = cn.cursor()
    try:
        base = _d6(base_ymd) or _base_ymd(cur)   # ★기본 = 계획 마지막 업로드 일자
        axis = _workdays(cur, base, days)
        d_from, d_to = axis[0]["ymd"], axis[-1]["ymd"]

        # ★일자축 = plan_ymd(생산계획일). part_plan_ymd(소요일) 아님 —
        #   레거시 실측: WO1094193AR 이 31월 칸 23 → plan_ymd=260831 (소요일은 260828).
        # ★자도번작업처 = 자도번의 pr_m_item.IN_CUST_CODE.
        #   plan_part_mat.mat_work_center_code 는 '자재 구매처'라 전혀 다른 업체가 잡힌다
        #   (AJR30027704-12-1 → in_cust 2148 대원산업 / mwc 는 2111·2246·2203…).
        # ★도번 = ASSY 자신(bom_level=0)만. -SUB1·-S1-2·-은납 같은 파생(lv≥1)은
        #   레거시 130 집계에 나오지 않는다(실측 대사: lv=1 전건이 웹에만 존재).
        # ★기준일 이전 계획도 포함해 **첫 칸에 합산**한다(레거시 동일).
        #   실측: 기준 260830 인데 레거시 30일 칸 1158 ≈ 웹 260829(1011)+260830(0).
        #   AJR30027708(계획 260829) 같은 건이 축에서 통째로 빠지던 원인.
        w = ["m.plan_ymd <= ?", "ISNULL(m.bom_level,0)=0"]; p = [d_to]
        if jcust: w.append("ISNULL(mi.IN_CUST_CODE,'')=?"); p.append(jcust)
        if wo:    w.append("m.work_order LIKE ?");          p.append("%" + wo + "%")
        # ★도번칸 — 도번(item_code)이 우선이지만 자도번을 넣어도 잡히게 한다.
        #   레거시도 도번/자도번을 섞어 치는 운용이라(AJR30125601 은 자도번),
        #   도번으로 0건이면 그 자도번을 쓰는 도번 전체가 나와야 한다.
        if doban:
            w.append("(m.item_code LIKE ? OR EXISTS(SELECT 1 FROM nx.plan_part_mat z WITH(NOLOCK)"
                     "   WHERE z.work_order=m.work_order AND z.item_code=m.item_code"
                     "     AND z.mat_code LIKE ?))")
            p.append("%" + doban + "%"); p.append("%" + doban + "%")
        if jadoban: w.append("m.mat_code LIKE ?");          p.append("%" + jadoban + "%")

        # ★계획(plan_part_dtl)에 있는 (제번×도번)만 — 레거시 130 은 계획행 기준이다.
        #   plan_part_mat 단독이면 계획 없는 조합까지 나온다(실측: 258행 중 82조합이
        #   dtl 미매칭, AJJ76418701·AJJ30041801 계열처럼 라인·작업처가 통째로 빈 행).
        if line:
            w.append("""EXISTS(SELECT 1 FROM nx.plan_part_dtl pd WITH(NOLOCK)
                                WHERE pd.work_order=m.work_order AND pd.item_code=m.item_code
                                  AND ISNULL(pd.line_no,'')=?)""")
            p.append(line)
        else:
            w.append("""EXISTS(SELECT 1 FROM nx.plan_part_dtl pd WITH(NOLOCK)
                                WHERE pd.work_order=m.work_order AND pd.item_code=m.item_code)""")

        # ★수량은 **도번 기준**이다. 자도번이 여러 개여도 소요는 한 번만 센다.
        #   자도번별 SUM 을 하면 자도번 수만큼 배수가 된다
        #   (실측: AJR30083102 자도번 2개 → 웹 6/6, 레거시 3/3).
        #   → 일자별로 MAX(part_plan_qty) 를 취한다(자도번마다 같은 도번 소요가 반복됨).
        cur.execute(f"""
            SELECT m.work_order, m.item_code, m.mat_code, m.plan_ymd,
                   MAX(m.part_plan_qty) qty,
                   MAX(ISNULL(mi.IN_CUST_CODE,'')) jcust,
                   MAX(ISNULL(m.assy_item_code,'')) assy
              FROM nx.plan_part_mat m WITH(NOLOCK)
              LEFT JOIN nx.pr_m_item mi WITH(NOLOCK) ON mi.ITEM_CODE=m.mat_code
             WHERE {' AND '.join(w)}
             GROUP BY m.work_order, m.item_code, m.mat_code, m.plan_ymd""", *p)
        raw = [{"wo": str(r[0]).strip(), "doban": str(r[1]).strip(),
                "jado": str(r[2] or "").strip(), "ymd": str(r[3]).strip(),
                "qty": float(r[4] or 0), "jcust": str(r[5] or "").strip(),
                "assy": str(r[6] or "").strip()} for r in cur.fetchall()]
        if not raw:
            return {"axis": axis, "rows": [], "base": base}

        # ── 계획(라인·LG INPUT·LOT·작업처) — 제번×도번
        keys = sorted({(x["wo"], x["doban"]) for x in raw})
        plan = {}
        for i in range(0, len(keys), 400):
            ch = keys[i:i + 400]
            cond = " OR ".join(["(work_order=? AND item_code=?)"] * len(ch))
            args = [v for k in ch for v in k]
            # ★작업처 = **첫 공정**(proc_seq 최소). MAX 로 뽑으면 마지막 공정이 나온다.
            #   실측: AJR30078601 = seq1 S5(01용접) / seq2 S5-2(01라인 조립)
            #   → 화면엔 첫 공정 S5 가 나와야 한다.
            cur.execute(f"""SELECT work_order, item_code,
                                   MAX(ISNULL(line_no,'')) line_no,
                                   MAX(ISNULL(output_hm,'')) output_hm,
                                   MAX(ISNULL(lot_qty,0)) lot_qty,
                                   MAX(ISNULL(plan_ymd,'')) plan_ymd,
                                   MAX(CASE WHEN rn=1 THEN gpc END) gpc,
                                   MAX(ISNULL(pull_day,0)) pull_day
                              FROM (SELECT work_order, item_code, line_no, output_hm,
                                           lot_qty, plan_ymd, pull_day,
                                           ISNULL(gagong_proc_code,'') gpc,
                                           ROW_NUMBER() OVER (PARTITION BY work_order, item_code
                                             ORDER BY ISNULL(proc_seq,0),
                                                      ISNULL(gagong_proc_seq,0),
                                                      ISNULL(gagong_proc_code,'')) rn
                                      FROM nx.plan_part_dtl WITH(NOLOCK)
                                     WHERE {cond}) z
                             GROUP BY work_order, item_code""", *args)
            for r in cur.fetchall():
                plan[(str(r[0]).strip(), str(r[1]).strip())] = {
                    "line": (r[2] or "").strip(), "hm": (r[3] or "").strip(),
                    "lot": int(r[4] or 0), "pymd": (r[5] or "").strip(),
                    "gpc": (r[6] or "").strip(), "pull": int(r[7] or 0)}

        # ── 일자 뒤 컬럼들 (레거시 화면 순서, matinput 과 동일 원천)
        #    LOT수량·자재수량·자재입고·요청수량·생산준비·생산실적·검사실적·출하실적
        #    ·세트재고·단품재고·ASSY재고·모델 …
        dobans = sorted({x["doban"] for x in raw if x["doban"]})
        jados = sorted({x["jado"] for x in raw if x["jado"]})

        def _fill(codes, sql, into, *pre):
            cl = [x for x in codes if x]
            for i in range(0, len(cl), 900):
                ch = cl[i:i + 900]; ph = ",".join("?" * len(ch))
                try:
                    cur.execute(sql.format(ph=ph), *(list(pre) + ch))
                    for a, b in cur.fetchall():
                        into[str(a).strip()] = float(b or 0)
                except Exception:
                    pass

        stock = {}      # 세트재고 — 도번 × 자도번작업처
        if jcust:
            _fill(dobans, """SELECT item_code, ISNULL(SUM(maint_qty),0)
                               FROM nx.set_stock_maint WITH(NOLOCK)
                              WHERE cust_code=? AND item_code IN ({ph})
                              GROUP BY item_code""", stock, jcust)
        else:
            _fill(dobans, """SELECT item_code, ISNULL(SUM(maint_qty),0)
                               FROM nx.set_stock_maint WITH(NOLOCK)
                              WHERE item_code IN ({ph}) GROUP BY item_code""", stock)

        st_dan = {}     # 단품재고 — 자도번(자재창고)
        _fill(jados, """SELECT MAT_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.PU_T_MAT_STOCK_WH
                         WITH(NOLOCK) WHERE MAT_CODE IN ({ph}) GROUP BY MAT_CODE""", st_dan)

        st_assy = {}    # ASSY재고 — 도번(영업창고)
        _fill(dobans, """SELECT ITEM_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.SA_T_ITEM_STOCK
                          WITH(NOLOCK) WHERE ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE""", st_assy)

        req = {}        # 요청수량 — 미확정 세트입고요청(자도번 기준)
        _fill(jados, f"""SELECT MAT_CODE, SUM(ISNULL(MAT_QTY,0))
                           FROM nx.PU_T_SET_INPUT_REQ_DTL WITH(NOLOCK)
                          WHERE MAT_CODE IN ({{ph}})
                            AND INPUT_YMD BETWEEN '{d_from}' AND '{d_to}'
                            AND ISNULL(CONFIRM_FLAG,'0')<>'1'
                          GROUP BY MAT_CODE""", req)

        jin = {}        # 자재입고 — 확정된 세트입고(자도번 기준)
        _fill(jados, f"""SELECT MAT_CODE, SUM(ISNULL(MAT_QTY,0))
                           FROM nx.PU_T_SET_INPUT_REQ_DTL WITH(NOLOCK)
                          WHERE MAT_CODE IN ({{ph}})
                            AND INPUT_YMD BETWEEN '{d_from}' AND '{d_to}'
                            AND ISNULL(CONFIRM_FLAG,'0')='1'
                          GROUP BY MAT_CODE""", jin)

        # 생산준비 — 레거시 130 의 ready_qty + item_move_qty (색상 ⑤단계에 쓰임)
        rdy = {}
        _fill(dobans, """SELECT ITEM_CODE, SUM(ISNULL(STOCK_QTY,0)) FROM nx.PU_T_READY_STOCK
                          WITH(NOLOCK) WHERE ITEM_CODE IN ({ph}) GROUP BY ITEM_CODE""", rdy)

        prd = {}        # 생산실적 — 도번
        _fill(dobans, f"""SELECT ITEM_CODE, SUM(ISNULL(PROD_QTY,0))
                            FROM nx.PR_T_PROD_DTL WITH(NOLOCK)
                           WHERE ITEM_CODE IN ({{ph}})
                             AND PROD_YMD BETWEEN '{d_from}' AND '{d_to}'
                           GROUP BY ITEM_CODE""", prd)

        # 출하실적 — ★제번+도번 (품번 누적이면 모든 행에 같은 값이 반복된다)
        sal = {}
        for i in range(0, len(keys), 400):
            ch = keys[i:i + 400]
            cond = " OR ".join(["(work_order=? AND item_code=?)"] * len(ch))
            args = [v for k in ch for v in k]
            try:
                cur.execute(f"""SELECT work_order, item_code, SUM(ISNULL(sale_qty,0))
                                  FROM nx.sale_dtl WITH(NOLOCK)
                                 WHERE ISNULL(finish_flag,'0')='0' AND ({cond})
                                 GROUP BY work_order, item_code""", *args)
                for a, b, q in cur.fetchall():
                    sal[(str(a).strip(), str(b).strip())] = float(q or 0)
            except Exception:
                pass

        # 사급 — 그 자도번이 쓰는 사급품 수량(레거시 '사급' 컬럼)
        sagub = {}
        _fill(jados, """SELECT b.item_code, ISNULL(SUM(b.use_qty),0)
                          FROM nx.pr_m_item_bom b WITH(NOLOCK)
                          JOIN nx.pr_m_item_bom_sub c WITH(NOLOCK)
                            ON c.item_code=b.item_code AND c.mat_code=b.mat_code
                         WHERE b.item_code IN ({ph}) AND c.sagub_flag='1'
                         GROUP BY b.item_code""", sagub)

        # ★작업처 명칭 — 코드(S4)보다 명칭(04라인)이 읽힌다(§3 코드는 이름으로 표시)
        gmap = {}
        try:
            cur.execute("""SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'')
                             FROM nx.PR_M_PROC_GAGONG WITH(NOLOCK)""")
            gmap = {str(a).strip(): (b or "").strip() for a, b in cur.fetchall()}
        except Exception:
            pass

        # 모델 — 도번
        model = {}
        for i in range(0, len(dobans), 400):
            ch = dobans[i:i + 400]; ph = ",".join("?" * len(ch))
            try:
                cur.execute(f"""SELECT item_code, ISNULL(model_no,'') FROM nx.item WITH(NOLOCK)
                                 WHERE item_code IN ({ph})""", *ch)
                for a, b in cur.fetchall():
                    model[str(a).strip()] = (b or "").strip()
            except Exception:
                pass

        # ── 이름 매핑
        custs = sorted({x["jcust"] for x in raw if x["jcust"]})
        cmap = {}
        if custs:
            ph = ",".join("?" * len(custs))
            cur.execute(f"""SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM nx.CM_M_CUST WITH(NOLOCK)
                             WHERE CUST_CODE IN ({ph})""", *custs)
            cmap = {str(a).strip(): (b or "").strip() for a, b in cur.fetchall()}

        imap = {}
        for i in range(0, len(dobans), 400):
            ch = dobans[i:i + 400]
            ph = ",".join("?" * len(ch))
            cur.execute(f"""SELECT item_code, ISNULL(item_name,'') FROM nx.item WITH(NOLOCK)
                             WHERE item_code IN ({ph})""", *ch)
            for a, b in cur.fetchall():
                imap[str(a).strip()] = (b or "").strip()

    finally:
        cn.close()

    # ── 제번×도번 으로 접어 일자별 소요를 붙인다
    det = {}
    for x in raw:
        k = (x["wo"], x["doban"])
        d = det.setdefault(k, {
            "wo": x["wo"], "doban": x["doban"], "assy": x["assy"],
            "jcust": x["jcust"], "jados": set(), "day": {},
        })
        if x["jado"]:
            d["jados"].add(x["jado"])
        # ★기준일 이전 계획(미처리분)은 첫 칸에 합산 — 레거시 동일
        ymd = x["ymd"] if x["ymd"] >= d_from else d_from
        # ★도번 기준 — 같은 (제번·도번·일자)면 자도번이 여럿이어도 한 번만.
        #   원자료가 자도번별로 같은 소요를 반복하므로 MAX 로 잡는다.
        prev = d["day"].get(ymd, 0.0)
        if x["ymd"] >= d_from:
            d["day"][ymd] = max(prev, x["qty"])
        else:
            # 기준일 이전분은 일자가 뭉개지므로 '그 일자별 최대'를 누적
            k2 = d.setdefault("_pre", {})
            k2[x["ymd"]] = max(k2.get(x["ymd"], 0.0), x["qty"])

    # ★기준일 이전분 — 일자별 최대치를 모아 첫 칸에 더한다(도번 기준 유지)
    for d in det.values():
        pre = d.pop("_pre", None)
        if pre:
            d["day"][d_from] = d["day"].get(d_from, 0.0) + sum(pre.values())

    rows = []
    for (wo, doban), d in det.items():
        pl = plan.get((wo, doban), {})
        jl = sorted(d["jados"])
        # 자재수량 = 그 제번×도번의 자도번 소요 합(일자축 내)
        matq = sum(d["day"].values())
        rows.append({
            "wo": wo, "doban": doban, "doban_nm": imap.get(doban, ""),
            "assy": d["assy"],
            "jcust": d["jcust"], "jcust_nm": cmap.get(d["jcust"], d["jcust"]),
            "jadolist": ",".join(jl), "jado_cnt": len(jl),
            "line": pl.get("line", ""), "hm": pl.get("hm", ""),
            "lot": pl.get("lot", 0), "pymd": pl.get("pymd", ""),
            "gpc": pl.get("gpc", ""),                          # 작업처 코드(툴팁·필터용)
            "gpc_nm": gmap.get(pl.get("gpc", ""), pl.get("gpc", "")),   # ★작업처 명칭
            "pull": pl.get("pull", 0),                         # 당김,변경
            "sagub": sum(sagub.get(j, 0.0) for j in jl),       # 사급
            # ── 일자 뒤 컬럼 (레거시 순서)
            "mat_qty": matq,                                   # 자재수량
            "mat_in": sum(jin.get(j, 0.0) for j in jl),        # 자재입고
            "req": sum(req.get(j, 0.0) for j in jl),           # 요청수량
            "ready": rdy.get(doban, 0.0),                      # 생산준비
            "prod": prd.get(doban, 0.0),                       # 생산실적
            "insp": 0.0,                                       # 검사실적(2차)
            "sale": sal.get((wo, doban), 0.0),                 # 출하실적
            "set_stock": stock.get(doban, 0.0),                # ★세트재고
            # ★단품재고 = 0 고정 (대표 확정 2026-08-30).
            #   이 화면은 **세트재고 기준**이라 단품(자재창고) 재고를 끌어오지 않는다.
            #   ASSY 도번이면 하위가 하나여도 단품재고가 오면 안 된다.
            #   ※세트 제외품 등 별도 제외조건은 후속 과제.
            "dan_stock": 0.0,
            "assy_stock": st_assy.get(doban, 0.0),             # ASSY재고
            "model": model.get(doban, ""),                     # 모델
            "day": d["day"],
            "total": matq,
        })

    # ★정렬 — 작업처 → 라인 → 도번 → **생산계획일 → LG INPUT 시각** → 제번.
    #   제번 문자열로 정렬하면 시각이 뒤섞인다(실측: 1053→0915→0933→1042).
    #   같은 도번 안에서는 계획일·투입시각 순이어야 현장 흐름과 맞는다.
    def _firstday(r):
        d = [k for k, v in (r.get("day") or {}).items() if v]
        return min(d) if d else "999999"

    rows.sort(key=lambda r: (r["jcust_nm"], r["line"], r["doban"],
                             r.get("pymd") or _firstday(r),
                             (r.get("hm") or "9999"), r["wo"]))
    tot_day = {a["ymd"]: round(sum(r["day"].get(a["ymd"], 0.0) for r in rows), 2)
               for a in axis}
    return {"axis": axis, "rows": rows, "base": base, "cnt": len(rows),
            "tot_day": tot_day,
            "tot_lot": round(sum(r["lot"] for r in rows), 2),
            "tot_mat": round(sum(r["mat_qty"] for r in rows), 2),
            "tot_prod": round(sum(r["prod"] for r in rows), 2),
            "tot_sale": round(sum(r["sale"] for r in rows), 2)}
