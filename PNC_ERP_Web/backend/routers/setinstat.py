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
    """일자축 — 기준일부터 **근무일이 N일 찰 때까지** 달력일로 이어 붙인다.

    ★거래명세서발행(420)의 _wd_horizon() 과 같은 규칙이다(coopplan.py:1172).
      레거시 w_pr_outside_420 실측 산식 = "종료일 = 기준일 초과 (N-1)번째 근무일".
      휴무가 끼면 그만큼 조회 범위가 늘어난다("휴무만큼 +해서 조회된다" — 사용자 설명).
        실측 260902 기준 4일 : 02(근)·03(근)·04(근)·05(휴)·06(휴)·07(근) → 6칸
      ⚠2026-09-02 에 잠깐 "달력 N일"로 바꿨다가 되돌렸다 —
        그러면 420 과 조회범위가 달라져 같은 업체·기간인데 계획이 어긋난다.
        두 화면은 같은 계획을 보여야 한다(사용자 확정).
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

        # ★★★주 테이블 = nx.plan_part_dtl (**파트별 생산계획**) — 2026-09-02 확정.
        #   이 화면은 "파트별 생산계획을 푼 것 + 직납품 계획"이다(사용자 정의).
        #   종전엔 nx.plan_part_mat(자재소요)을 주 테이블로 썼는데, 그건 자재 단위라
        #   같은 도번의 제번 대부분이 빠진다.
        #     실측 AJR30012101 · 미래정밀 · 02수 :
        #       plan_part_mat  → 제번 1개(6I1M0BK3) → 웹 1     ❌
        #       plan_part_dtl  → 제번 49개          → 85       ✅ 레거시와 동일
        #     레거시 8일 화면 02수 20도번 전수 대조 : **20/20 일치**(불일치 0).
        #
        #   ▸ 수량   = SUM(part_plan_qty) WHERE **proc_seq=1**
        #   ▸ 일자   = part_plan_ymd (파트 소요일) · 기준일 이전은 첫 칸에 합산
        #   ▸ 협력사 = 그 (제번,도번)의 plan_part_mat 에 해당 업체 자재가 있는가
        #              (mat_work_center_code)
        #   ▸ 직납품 = 파트공정이 없어 plan_part_dtl 에 없다 → 아래 UNION 으로 따로 붙인다.
        #
        # ★★★proc_seq=1 = 레거시 원본 조건이다(2026-09-02, 축을 데이터가 아니라 원본에서 확정).
        #   근거 = 자매화면 거래명세서발행(420)의 DW 원본 SQL
        #          `_legacy_analysis/GAGONG_4PROGRAMS_ANALYSIS.md:30-80`
        #          (원본 src_extracted/pr_prod_06/dw_pr_input_420_t1.srd:123~285)
        #     · FROM PR_T_PLAN_PART_DTL a          ← 주 테이블 (= nx.plan_part_dtl)
        #     · sum(... a.part_plan_qty ...)        ← 수량은 **SUM**
        #     · and A.PROC_SEQ = 1                  ← ★다공정 중복 제거
        #     · a.part_plan_ymd 로 일자 셀을 가름
        #   두 화면은 같은 계획을 보여야 하므로(사용자 확인) 같은 축을 쓴다.
        #
        #   proc_seq 를 안 걸면 2공정 도번이 그대로 더해져 **정확히 배수**가 된다.
        #     실측 AJR73965505 · 미래정밀 · 02수 :
        #       proc_seq=1 : 37행 544   ← 레거시 화면값과 일치
        #       proc_seq=2 : 14행 387
        #       전체       :      931   ❌ (레거시 544)
        #     레거시 8일 화면 02수 33도번 전수 대조 : proc_seq=1 적용 후 **32/32 일치**
        #     (나머지 1건 MJU66478801 은 세트제외품이라 파트공정이 없어 ②갈래로 나온다).
        #   ※종전엔 이 배수를 MAX 로 덮으려 했으나 그건 보정이지 레거시 산식이 아니다.
        #
        # ※s_work_code 는 협력사코드가 아니라 **작업장**(454/385/386…)이다 — 협력사 판정에
        #   쓸 수 없다(실측: 2096 으로 걸면 33도번 전멸). 레거시 420 의 `a.work_code` 에
        #   해당하는 컬럼이 nx.plan_part_dtl 에 없으므로 협력사는 소요(mat_work_center_code)로 본다.
        # ※gc_gubun 도 nx 에는 P/Q 두 값뿐이라 레거시의 `g.gc_gubun<>'P'`
        #   (PR_M_PROC_GAGONG 조인분)와 다른 값이다 — 걸면 전멸하므로 적용하지 않는다.
        w = ["pd.part_plan_ymd <= ?", "pd.proc_seq = 1"]; p = [d_to]
        if jcust:
            w.append("""EXISTS(SELECT 1 FROM nx.plan_part_mat z WITH(NOLOCK)
                                WHERE z.work_order=pd.work_order
                                  AND ISNULL(NULLIF(z.assy_item_code,''),z.item_code)=pd.item_code
                                  AND RTRIM(ISNULL(z.mat_work_center_code,''))=?)""")
            p.append(jcust)
        if wo:    w.append("pd.work_order LIKE ?");          p.append("%" + wo + "%")
        if line:  w.append("ISNULL(pd.line_no,'')=?");        p.append(line)
        # ★도번칸 — 도번(item_code)이 우선이지만 자도번을 넣어도 잡히게 한다.
        if doban:
            w.append("""(pd.item_code LIKE ?
                         OR EXISTS(SELECT 1 FROM nx.plan_part_mat z WITH(NOLOCK)
                                    WHERE z.work_order=pd.work_order
                                      AND ISNULL(NULLIF(z.assy_item_code,''),z.item_code)=pd.item_code
                                      AND z.mat_code LIKE ?))""")
            p.append("%" + doban + "%"); p.append("%" + doban + "%")
        if jadoban:
            w.append("""EXISTS(SELECT 1 FROM nx.plan_part_mat z WITH(NOLOCK)
                                WHERE z.work_order=pd.work_order
                                  AND ISNULL(NULLIF(z.assy_item_code,''),z.item_code)=pd.item_code
                                  AND z.mat_code LIKE ?)""")
            p.append("%" + jadoban + "%")

        # ★★plan_part_dtl EXISTS 조건을 **제거한다**(2026-09-02).
        #   종전엔 "계획(plan_part_dtl)에 있는 (제번×도번)만" 으로 걸렀다. 그런데
        #   거래명세서발행(420)에는 그 조건이 없어 **같은 업체·기간인데 계획이 달랐다**
        #   (사용자 지적 — 두 화면은 같은 계획을 보여야 한다).
        #     실측 미래정밀 260902~260905 :
        #       AJJ30041802 : part_plan_ymd 조건으로 18행 잡히는데
        #                     plan_part_dtl EXISTS 를 걸면 **0행** → 화면에서 도번이 통째로 사라짐
        #       이런 도번이 20개(420 에만 있던 것). 계획차 −1,483 의 주원인.
        #     직납품(item_code=mat_code)은 파트공정이 없어 애초에 dtl 에 안 들어가고,
        #     세트품도 파생도번(-은납) 아래 달리면 dtl 매칭이 안 되는 경우가 있다.
        #   ⟹ 소요(plan_part_mat)에 있으면 협력사가 만들어야 하는 것이다 — 그대로 보여준다.
        #   ※line 필터만 dtl 로 건다(라인 정보가 거기에만 있으므로). 직납은 예외 통과.
        if line:
            w.append("""(RTRIM(m.item_code)=RTRIM(m.mat_code)
                         OR EXISTS(SELECT 1 FROM nx.plan_part_dtl pd WITH(NOLOCK)
                                    WHERE pd.work_order=m.work_order AND pd.item_code=m.item_code
                                      AND ISNULL(pd.line_no,'')=?))""")
            p.append(line)

        # ★수량은 **도번 기준**이다(자도번 축은 안 편다).
        #   plan_part_dtl 을 (제번×도번×일자)로 GROUP BY 하고 proc_seq=1 로 걸러 SUM 한다
        #   — 레거시 420 원본과 같은 처리다(위 주석의 근거 참고).
        #
        # ★★자재수량 = plan_item_dtl 의 PLAN_QTY×USE_QTY×PROD_RATE/100 이다(2026-09-02 수정).
        #   종전엔 plan_part_mat.part_plan_qty 를 썼는데 그 값은 **한 번 더 전개된 것**이라
        #   레거시 화면의 3배가 나왔다.
        #     실측 6I3M0006 × MJU63357501 :
        #       plan_part_mat.part_plan_qty = 315   (웹·레거시 원천 동일)
        #       plan_item_dtl 계산          = 105   (LOT 35 × USE_QTY 3)  ← 레거시 130·420 화면값
        #     레거시 130 은 「LOT수량 35 · 자재수량 105」로 표시한다(사용자 화면 확인).
        #     use_qty 가 모델별로 1·2·3 이라 배수가 제각각인 것도 이 산식과 맞는다.
        #   ⟹ 소요 존재 판정만 plan_part_mat 로 하고, 수량은 plan_item_dtl 에서 가져온다.
        # ★★행 그레인 = (제번 × **모도번 assy_item_code**) — item_code 아님(2026-09-02).
        #   파생도번(-은납·-SUB)에 달린 자도번도 모도번 한 행으로 묶인다(레거시 130 동일).
        #   ★거래명세서발행(420)이 쓰는 축과 같다 — 두 화면은 같은 계획을 보여야 한다
        #     (420: coopplan._fulfillment 도 assy_item_code 로 묶고 plan_item_dtl 수량을 쓴다).
        # ── ② 직납품 갈래 필터 (plan_part_mat 기준) ──
        #   직납품은 파트공정이 없어 plan_part_dtl 에 안 들어간다 → 별도 UNION.
        #   판정 = item_code = mat_code (자기가 곧 도번).
        w2 = ["m.part_plan_ymd <= ?", "RTRIM(m.item_code)=RTRIM(m.mat_code)"]; p2 = [d_to]
        if jcust:   w2.append("RTRIM(ISNULL(m.mat_work_center_code,''))=?"); p2.append(jcust)
        if wo:      w2.append("m.work_order LIKE ?");  p2.append("%" + wo + "%")
        if doban:   w2.append("m.item_code LIKE ?");   p2.append("%" + doban + "%")
        if jadoban: w2.append("m.mat_code LIKE ?");    p2.append("%" + jadoban + "%")
        # line 은 직납에 파트공정이 없어 걸 수 없다(레거시도 라인 공란) — 조건 생략.

        # ── ③ 세트입고제외품 갈래 (★조건 미확정 — 기본 OFF) ─────────────────────
        # 세트 = 최상위 도번 + 그 하위품을 하나로 묶은 품번. 세트입고제외품은
        # 하위→상위품에 속하는 품번을 **단품화**시켜 세트재고가 아니라 단품재고로 관리한다
        # (사용자 설명). BOM 에서 설정한다(nx.bom_line.set_except / PR_M_ITEM_BOM.SET_EXCEPT_FLAG).
        #
        # ★화면에서 확인한 사실(2026-09-02, 레거시 130 자도번=MJU66478801 조회 실측):
        #   같은 자재라도 **세트제외인 경로와 아닌 경로가 섞여 있다**(사용자 지적).
        #     · 어떤 제번은 상위도번 행으로 나온다(도번=상위, 자도번LIST=이 자재)
        #         AJR30125601 소계 323 · AJR30125602 소계 63 — 둘 다 웹과 일치(①갈래)
        #     · 어떤 제번은 자재가 **자기 이름으로 도번 행**이 된다(자도번LIST 빈칸)
        #         자기행 = 13제번 · 소계 126 (화면 SEQ 48~60)
        #   ⟹ 합쳐서 한 행으로 만들지 않는다. **제번 단위 행**이다.
        #     (420 은 자재 한 행으로 합친다 — coopplan._setexc_rows. 그건 업체별 집계라 그렇고
        #      130 은 상세라 제번별로 편다. 두 화면의 축이 다르다.)
        #
        # ⚠★두 집합을 가르는 조건은 **아직 확정되지 않았다**(2026-09-02).
        #   소요(plan_part_mat)상 두 집합은 모양이 완전히 같다 — 확인한 것:
        #     · item_code 전부 '-S1-2' 파생  (13/13, 11/11)
        #     · bom_level 전부 1 · assy=up 동일 · part_plan_ymd 전부 260902
        #     · 상위도번의 plan_part_dtl 존재여부도 양쪽 다 1 (이걸로 안 갈린다)
        #   유일하게 갈리는 값 = plan_ymd (자기행 13건은 전부 260904 /
        #                                 나머지 11건은 260902·260903)
        #   근거 없이 조건을 만들면 다른 자재에서 틀린다 → **확정 전까지 이 갈래는 끈다.**
        #   확정되면 _SETEXC_ON 을 켜고 아래 조건을 그 규칙으로 교체한다.
        #
        # ※NOT EXISTS 안에도 같은 기간 제한을 건다. 안 걸면 기간 밖(과거) 상위계획까지
        #   매칭돼 조건이 전건을 지운다(실측: 안 걸면 60행 → 0행).
        _SETEXC_ON = False        # ★판별조건 확정 전까지 OFF
        w3 = ["m.part_plan_ymd <= ?",
              "1=0" if not _SETEXC_ON else "1=1",
              "RTRIM(m.item_code)<>RTRIM(m.mat_code)",   # 직납(②)과 겹치지 않게
              # 상위도번이 파트별계획에 없을 것 = 단품화 조건
              """NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WITH(NOLOCK)
                             WHERE d.work_order=m.work_order
                               AND RTRIM(d.item_code)=RTRIM(m.upper_item_code)
                               AND d.proc_seq=1 AND d.part_plan_ymd<=?)""",
              # 자재 자신도 파트별계획에 없을 것(있으면 ①에서 이미 나온다)
              """NOT EXISTS(SELECT 1 FROM nx.plan_part_dtl d WITH(NOLOCK)
                             WHERE d.work_order=m.work_order
                               AND RTRIM(d.item_code)=RTRIM(m.mat_code)
                               AND d.proc_seq=1 AND d.part_plan_ymd<=?)"""]
        p3 = [d_to, d_to, d_to]
        if jcust:   w3.append("RTRIM(ISNULL(m.mat_work_center_code,''))=?"); p3.append(jcust)
        if wo:      w3.append("m.work_order LIKE ?");  p3.append("%" + wo + "%")
        if doban:   w3.append("m.mat_code LIKE ?");    p3.append("%" + doban + "%")
        if jadoban: w3.append("m.mat_code LIKE ?");    p3.append("%" + jadoban + "%")

        cur.execute(f"""
            -- ① 파트별 생산계획을 푼 것
            SELECT pd.work_order, pd.item_code doban, x.mat_code, pd.part_plan_ymd ymd,
                   pd.q qty, x.jcust, pd.item_code assy
              FROM (SELECT work_order, item_code, part_plan_ymd,
                           SUM(CAST(part_plan_qty AS float)) q   -- ★레거시 420 과 동일: proc_seq=1 로 거르고 SUM
                      FROM nx.plan_part_dtl pd WITH(NOLOCK)
                     WHERE {' AND '.join(w)}
                     GROUP BY work_order, item_code, part_plan_ymd) pd
              CROSS APPLY (SELECT MAX(RTRIM(z.mat_code)) mat_code,
                                  MAX(RTRIM(ISNULL(z.mat_work_center_code,''))) jcust
                             FROM nx.plan_part_mat z WITH(NOLOCK)
                            WHERE z.work_order=pd.work_order
                              AND ISNULL(NULLIF(z.assy_item_code,''),z.item_code)=pd.item_code
                              {"AND RTRIM(ISNULL(z.mat_work_center_code,''))=?" if jcust else ""}) x
             WHERE x.mat_code IS NOT NULL
            UNION ALL
            -- ② 직납품 계획 (파트공정 없음)
            SELECT m.work_order, m.item_code doban, m.mat_code, m.part_plan_ymd ymd,
                   MAX(ISNULL(i.q, m.part_plan_qty)) qty,
                   MAX(RTRIM(ISNULL(m.mat_work_center_code,''))) jcust,
                   MAX(ISNULL(m.assy_item_code,'')) assy
              FROM nx.plan_part_mat m WITH(NOLOCK)
              OUTER APPLY (SELECT MAX(CEILING(CONVERT(float,d.PLAN_QTY)
                                    *ISNULL(d.USE_QTY,1)*ISNULL(d.PROD_RATE,100)/100.0)) q
                             FROM nx.plan_item_dtl d WITH(NOLOCK)
                            WHERE d.WORK_ORDER=m.work_order
                              AND d.C_ITEM_CODE=m.item_code) i
             WHERE {' AND '.join(w2)}
             GROUP BY m.work_order, m.item_code, m.mat_code, m.part_plan_ymd
            UNION ALL
            -- ③ 세트입고제외품 (상위가 파트별계획에 없어 단품화된 것)
            --    도번 = 자재 자신 · 자도번LIST 는 빈칸(레거시 화면과 동일)
            SELECT m.work_order, m.mat_code doban, '' mat_code, m.part_plan_ymd ymd,
                   SUM(CAST(m.part_plan_qty AS float)) qty,
                   MAX(RTRIM(ISNULL(m.mat_work_center_code,''))) jcust,
                   MAX(RTRIM(ISNULL(m.upper_item_code,''))) assy
              FROM nx.plan_part_mat m WITH(NOLOCK)
             WHERE {' AND '.join(w3)}
             GROUP BY m.work_order, m.mat_code, m.part_plan_ymd""",
                    *(p + ([jcust] if jcust else []) + p2 + p3))
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
                              -- ★LG INPUT = **part_output_hm**(파트 투입시각)이다(2026-09-02).
                              --   output_hm 은 상위 계획시각이라 A/S 제번에서 어긋난다.
                              --     실측 WO1094468AR × AJR37039701 :
                              --       output_hm 2100 / part_output_hm 1700 → 레거시 화면 17:00
                              --       (6I2M03L6 은 둘 다 0909 라 종전엔 안 드러났다)
                              FROM (SELECT work_order, item_code, line_no,
                                           ISNULL(NULLIF(part_output_hm,''), output_hm) output_hm,
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

        # ★직납품 폴백 — plan_part_dtl 에 없는 (제번×도번)은 STEP5(nx.plan_item_dtl)에서 채운다.
        #   직납은 파트공정이 없어 plan_part_dtl 에 안 들어가므로(위 _DIRECT 주석 참고)
        #   라인·LG INPUT·LOT·계획일자가 전부 빈칸이 된다.
        #     레거시 130 은 MJU63357501 을 라인 C1 · LG INPUT 07:50 · LOT 149 로 보여준다.
        #   plan_item_dtl 은 도번(C_ITEM_CODE) 단위라 직납품도 들어 있다(420 에서 확인).
        miss = [k for k in keys if k not in plan]
        for i in range(0, len(miss), 400):
            ch = miss[i:i + 400]
            cond = " OR ".join(["(WORK_ORDER=? AND C_ITEM_CODE=?)"] * len(ch))
            args = [v for k in ch for v in k]
            cur.execute(f"""SELECT WORK_ORDER, C_ITEM_CODE,
                                   MAX(ISNULL(LINE_NO,'')) line_no,
                                   MAX(ISNULL(OUTPUT_HM,'')) output_hm,
                                   MAX(ISNULL(LOT_QTY,0)) lot_qty,
                                   MAX(ISNULL(PLAN_YMD,'')) plan_ymd
                              FROM nx.plan_item_dtl WITH(NOLOCK)
                             WHERE {cond}
                             GROUP BY WORK_ORDER, C_ITEM_CODE""", *args)
            for r in cur.fetchall():
                plan[(str(r[0]).strip(), str(r[1]).strip())] = {
                    "line": (r[2] or "").strip(), "hm": (r[3] or "").strip(),
                    "lot": int(r[4] or 0), "pymd": (r[5] or "").strip(),
                    "gpc": "", "pull": 0}

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
            #   ※세트입고제외품(UNION ③)은 정의상 단품재고로 관리하지만, 레거시 화면도
            #     단품재고 칸을 채우지 않는다(실측: 자기행 13제번 전부 공란) — 동일하게 0.
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
