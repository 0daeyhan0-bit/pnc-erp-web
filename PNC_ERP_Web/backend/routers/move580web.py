# -*- coding: utf-8 -*-
"""가공창고 이동계획(580) 조회 — SP 재구현 웹버전.

  ★목적 (CLAUDE.md §1-9-1 클린 단일화)
    현행 조회엔진 nx.SP_PR_가공창고_이동계획_WEBPLAN(1,238줄 T-SQL)이
    레거시 미러 5종(PR_M_ITEM_BOM·PR_M_PROC_GAGONG·PR_M_ITEM_SUB·PR_M_WORK·CM_M_MASTER_DETAIL)을
    읽는다. 컷오버로 레거시가 은퇴하면 얼어붙으므로 조회를 우리 코드로 옮긴다.
    (발행·인쇄·삭제·전표조회는 이미 gagongmove.py 의 우리 코드다 — 여기선 조회만 다룬다.)

  ★대표 확정 (2026-09-08)
    ① 값은 **지금 SP와 100% 같아야 한다** — "웹버전으로 해도 계획이 비슷해야 해"
    ② SP 안의 **버그성 동작도 그대로 복제**한다(고치면 diff 발생)
    ③ 범위는 **조회만**

  ★설계 — SP 파이프라인을 순서 그대로 옮긴다
    데이터 적재는 SQL(집합연산)로, **재고 충당 커서 5개만** Python 루프로 옮긴다.
    커서는 상태(재고 이월)를 들고 정렬순으로 도는 절차적 로직이라 집합연산으로 안 풀린다.

      ① load_plan          4개 뷰 UNION            → rows
      ② sale  커서          TAG 90
      ③ assy  커서          TAG 70
      ④ mat_stock          생산파트+사급+자재창고 + BOM 하향전파 FIX_STOCK_QTY
      ⑤ bom_assy           BOM 재귀 2벌(사내생산·사급) → mat_list
      ⑥ fix   커서          TAG 70
      ⑦ jae   커서          TAG 70
      ⑧ move_plan + jp     → part 커서  TAG 50
      ⑨ 7키 GROUP BY + 32칸 피벗 × 4종

  ★그대로 복제하는 SP 버그 4개 — 각 지점에 [SP버그] 주석과 원문 줄번호를 남겼다.
    B1 ASSY커서 ORDER BY 에 BOM_LEVEL 이 없는데 키 비교엔 있다(sp 253 vs 260~264,
       올바른 정렬이 254행에 주석처리) → 재고가 반복 리셋되어 과다충당
    B2 도번고정커서 WHERE 가 STOCK_QTY+PR_STOCK_QTY+FIX_STOCK_QTY>0 인데(sp 588)
       앞 둘은 646행에서야 채워진다 → 실질 조건 = FIX_STOCK_QTY>0
    B3 커서 그룹키 ≠ UPDATE 8키. UPDATE 가 여러 행을 한꺼번에 갱신하는데 커서는
       그 행들을 각각 다시 방문한다(fetch 시점 FINISH_QTY 는 옛값) → 중복 가산
    B4 use_qty 곱셈이 커서마다 다르다 — 출하○ ASSY○ 도번고정✕ 자재✕ 파트✕

  ★파라미터 함정(SP 실측)
    · from_ymd  = 필터가 **아니다**. 32칸 피벗 앵커일 뿐(_00=미만 전부, _01=+0일 … _31=+30일)
    · to_ymd    = 유일한 실제 필터. **하한 없음**(between '' and to_ymd)
    · pr_part_code·sagub_cust_code = **죽은 파라미터**(sp 450~453, 534~537 전부 주석)
    · pu_part_code = 필터 아님. 출력 상수(wh_gagong_proc_code)

  ★쓰기 없음(조회 전용). 라이브 PARTNER_ERP 무변경.
"""
from datetime import datetime, timedelta

# SP 가 읽는 스키마. SP 본문이 무수식으로 참조하는 이름들은 nx 스키마로 해석된다
# (SP 소유자가 nx). 재현도 같은 곳을 읽어야 diff0 이 된다.
S = "PARTNER_ERP_TEST3.nx"


def _f(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _s(v):
    return str(v or "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# ① 계획 적재 — SP 91~135행 4개 UNION ALL 그대로
# ─────────────────────────────────────────────────────────────────────────────
_PLAN_SQL = f"""
SELECT PLAN_YMD, WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, BOM_LEVEL, UPPER_ITEM_CODE,
       ITEM_CODE, PROC_SEQ, GC_GUBUN, OUTPUT_HM, LINE_NO, USE_QTY, PLAN_QTY, WORK_CODE,
       GAGONG_PROC_CODE, GAGONG_PROC_SEQ, JP_PROC_METHOD, LT_HR, CUM_LT_HR,
       PART_PLAN_YMD, PART_OUTPUT_HM, PART_PLAN_QTY
  FROM {S}.v_plan_part_copy_new WITH (NOLOCK)
 WHERE WORK_CODE = 'P1' AND GAGONG_PROC_SEQ = 1
UNION ALL
SELECT A.PLAN_YMD, A.WORK_ORDER, A.SPLIT_WORK_ORDER, A.C_ITEM_CODE, 0, A.C_ITEM_CODE,
       A.C_ITEM_CODE, 0, M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1, A.PLAN_QTY * A.USE_QTY, '',
       '', 0, '', 0, 0,
       A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_QTY * A.USE_QTY
  FROM {S}.v_plan_item_dtl_new A WITH (NOLOCK)
  JOIN {S}.PR_M_ITEM M ON A.C_ITEM_CODE = M.ITEM_CODE
 WHERE M.IN_CUST_CODE > '' AND A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
UNION ALL
SELECT A.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, 0, A.ITEM_CODE,
       A.ITEM_CODE, 0, M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1, A.PLAN_QTY, '',
       '', 0, '', 0, 0,
       A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_QTY
  FROM {S}.v_prod_plan_input_new A WITH (NOLOCK)
  JOIN {S}.PR_M_ITEM M ON A.ITEM_CODE = M.ITEM_CODE
 WHERE M.IN_CUST_CODE > '' AND A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
UNION ALL
SELECT A.PLAN_YMD, A.WORK_ORDER, A.WORK_ORDER, A.ITEM_CODE, 0, A.ITEM_CODE,
       A.ITEM_CODE, 0, M.GC_GUBUN, A.OUTPUT_HM, A.LINE_NO, 1, A.PLAN_QTY, M.WORK_CODE,
       '', 0, '', 0, 0,
       A.PLAN_YMD, A.OUTPUT_HM, A.PLAN_QTY
  FROM {S}.v_prod_plan_input_new A WITH (NOLOCK)
  JOIN {S}.PR_M_ITEM M ON A.ITEM_CODE = M.ITEM_CODE
 WHERE M.WORK_CODE = 'P2' AND A.PLAN_YMD >= CONVERT(VARCHAR, GETDATE(), 12)
"""

_PCOLS = ["plan_ymd", "work_order", "split_work_order", "assy_item_code", "bom_level",
          "upper_item_code", "item_code", "proc_seq", "gc_gubun", "output_hm", "line_no",
          "use_qty", "plan_qty", "work_code", "gagong_proc_code", "gagong_proc_seq",
          "jp_proc_method", "lt_hr", "cum_lt_hr", "part_plan_ymd", "part_output_hm",
          "part_plan_qty"]

_NUMC = {"bom_level", "proc_seq", "use_qty", "plan_qty", "gagong_proc_seq",
         "lt_hr", "cum_lt_hr", "part_plan_qty"}


def load_plan(cur):
    """#TEMP_PART_DTL 재현. 계산컬럼은 0/초기값으로 붙인다(SP 96~98행)."""
    cur.execute(_PLAN_SQL)
    rows = []
    for r in cur.fetchall():
        d = {}
        for i, c in enumerate(_PCOLS):
            d[c] = _f(r[i]) if c in _NUMC else _s(r[i])
        d.update(finish_tag=0, color=16777215, finish_qty=0.0, sale_qty=0.0,
                 assy_stock_qty=0.0, fix_stock_qty=0.0, set_stock_qty=0.0,
                 pr_stock_qty=0.0, stock_qty=0.0, part_stock_qty=0.0,
                 ready_stock_qty=0.0, jp_print_qty=0.0, ready_qty=0.0)
        rows.append(d)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ★커서 공통 골격 — SP 커서 5개가 전부 같은 형태다.
# ─────────────────────────────────────────────────────────────────────────────
def _idx8(rows, with_gole=False):
    """UPDATE 의 WHERE 8키 → 행 목록. [SP버그 B3] 커서 그룹키와 다른 이 키로
       여러 행이 한꺼번에 갱신된다(SP 293~300 등)."""
    ix = {}
    for r in rows:
        k = (r["plan_ymd"], r["work_order"], r["split_work_order"], r["assy_item_code"],
             r["bom_level"], r["upper_item_code"], r["item_code"], r["proc_seq"])
        if with_gole:
            k = k + (r.get("gole_code", ""),)
        ix.setdefault(k, []).append(r)
    return ix


def _run_cursor(rows, *, order, group, stock_of, tag, to_ymd,
                mul_use=False, where=None, assign=False, upd_gole=False):
    """SP 커서 1개 = 정렬순 순회하며 재고를 이월 소진.

       order    : 정렬 키 함수 (SP order by 그대로 — ★고치면 diff 발생)
       group    : 그룹 판정 키 함수 (SP 의 if @ls_xx <> @db_xx 비교 그대로)
       stock_of : 그룹이 바뀔 때 채울 재고
       mul_use  : 재고에 use_qty 를 곱하는가 [SP버그 B4] 커서마다 다르다
       assign   : True 면 FINISH_QTY = fin (출하 커서만), False 면 +=
       where    : 커서 SELECT 의 WHERE (None 이면 to_ymd 만)
    """
    ix = _idx8(rows, with_gole=upd_gole)
    cand = [r for r in rows if r["part_plan_ymd"] <= to_ymd and (where is None or where(r))]
    cand.sort(key=order)

    last, stock = None, 0.0
    for r in cand:
        g = group(r)
        if g != last:
            last = g
            stock = stock_of(r) * (r["use_qty"] if mul_use else 1.0)
        if stock <= 0:
            continue
        # ★fetch 시점의 finish_qty 를 쓴다 — UPDATE 로 이미 갱신됐어도 커서 값은 옛것.
        #   [SP버그 B3] 이 성질이 중복 가산을 만든다. 그대로 복제한다.
        jan = r["part_plan_qty"] - r["_fin_at_fetch"]
        if jan <= 0:
            continue
        if jan > stock:
            newtag, fin, stock = None, stock, 0.0
        else:
            newtag, fin, stock = tag, jan, stock - jan
        k = (r["plan_ymd"], r["work_order"], r["split_work_order"], r["assy_item_code"],
             r["bom_level"], r["upper_item_code"], r["item_code"], r["proc_seq"])
        if upd_gole:
            k = k + (r.get("gole_code", ""),)
        for t in ix.get(k, ()):
            t["finish_qty"] = fin if assign else t["finish_qty"] + fin
            if newtag is not None:
                t["finish_tag"] = newtag
    return rows


def _snap_fetch(rows):
    """커서가 SELECT 하는 시점의 FINISH_QTY 스냅. 커서 1개마다 시작 전에 찍는다.

       ★실측 확인(2026-09-08) — T-SQL 커서는 **연 시점 스냅**을 본다.
         같은 표를 루프 안에서 UPDATE 해도 커서가 읽는 값은 안 바뀐다.
           CREATE #T(3행 finish=0) → 커서 돌며 매회 전행 +1 → fetch 값 0,0,0
         (갱신값을 봤다면 0,1,2 가 나왔을 것)
         [SP버그 B3] 의 중복 가산이 여기서 나온다. 그대로 복제해야 diff0 이다."""
    for r in rows:
        r["_fin_at_fetch"] = r["finish_qty"]
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ② 출하실적 — SP 147~200행. TAG 90. ★유일하게 FINISH_QTY 를 **대입**한다.
# ─────────────────────────────────────────────────────────────────────────────
def step_sale(cur, rows, to_ymd):
    cur.execute(f"""SELECT work_order, split_work_order, item_code, ISNULL(SUM(sale_qty),0)
                      FROM {S}.sa_t_sale_dtl WITH (NOLOCK)
                     WHERE finish_flag='0'
                     GROUP BY work_order, split_work_order, item_code""")
    sm = {}
    for r in cur.fetchall():
        sm[(_s(r[0]), _s(r[1]), _s(r[2]))] = _f(r[3])
    for r in rows:
        r["sale_qty"] = sm.get((r["work_order"], r["split_work_order"], r["assy_item_code"]), 0.0)

    _snap_fetch(rows)
    _run_cursor(
        rows, to_ymd=to_ymd, tag=90, mul_use=True, assign=True,
        # SP 162: order by wo, swo, assy, bl, upper, item, seq, plan_ymd
        order=lambda r: (r["work_order"], r["split_work_order"], r["assy_item_code"],
                         r["bom_level"], r["upper_item_code"], r["item_code"],
                         r["proc_seq"], r["plan_ymd"]),
        # SP 그룹키 = 위 7개(plan_ymd 제외)
        group=lambda r: (r["work_order"], r["split_work_order"], r["assy_item_code"],
                         r["bom_level"], r["upper_item_code"], r["item_code"], r["proc_seq"]),
        stock_of=lambda r: r["sale_qty"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ③ ASSY재고 — SP 244~307행. TAG 70.
# ─────────────────────────────────────────────────────────────────────────────
def step_assy(cur, rows, to_ymd):
    cur.execute(f"""SELECT item_code, ISNULL(SUM(stock_qty),0)
                      FROM {S}.sa_t_item_stock WITH (NOLOCK) GROUP BY item_code""")
    am = {_s(r[0]): _f(r[1]) for r in cur.fetchall()}
    for r in rows:
        r["assy_stock_qty"] = am.get(r["assy_item_code"], 0.0)

    _snap_fetch(rows)
    _run_cursor(
        rows, to_ymd=to_ymd, tag=70, mul_use=True,
        # ★[SP버그 B1] SP 253 order by 에 BOM_LEVEL 이 **없다**.
        #   올바른 정렬(BOM_LEVEL 포함)은 254행에 주석처리돼 있다.
        #   그런데 아래 group 은 BOM_LEVEL 을 본다(SP 260~264) → 재고 반복 리셋.
        #   고치면 값이 달라진다. 그대로 둔다.
        order=lambda r: (r["assy_item_code"], r["upper_item_code"], r["item_code"],
                         r["proc_seq"], r["gagong_proc_code"], r["part_plan_ymd"],
                         r["part_output_hm"], r["plan_ymd"], r["output_hm"],
                         r["work_order"], r["split_work_order"]),
        group=lambda r: (r["assy_item_code"], r["bom_level"], r["upper_item_code"],
                         r["item_code"], r["proc_seq"]),
        stock_of=lambda r: r["assy_stock_qty"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ④ 재고풀 + BOM 하향전파 — SP 313~362행 (#TEMP_MAT_STOCK)
#
#   ★BOM 재귀는 SQL 재귀 CTE 를 **그대로 실행**해 결과만 받는다.
#     SOYO_ENGINE_RULE §0 은 "라우터에서 BOM 을 ad-hoc 전개하지 말 것"인데,
#     여기 목적은 **SP 와 diff0** 이고 SP 의 종료조건(A/B/C 3벌이 서로 다르다)을
#     엔진 walker 로 재현하면 미묘한 차이가 값 차이로 직결된다.
#     ⟹ 전개식 자체는 SP 원문을 그대로 쓰고, Python 은 커서(상태 로직)만 맡는다.
#     ※컷오버 관점에서 이 CTE 가 읽는 pr_m_item_bom 은 나중에 nx.bom_line 으로
#       옮겨야 한다. diff0 게이트를 통과시킨 뒤 별도 단계로 진행한다.
# ─────────────────────────────────────────────────────────────────────────────
#   ★조회 커넥션(_conn)은 RO 가드라 임시표 DDL 도 막힌다(common.py:84).
#     그래서 #TEMP_PART_DTL 대신 **품목목록을 VALUES 인라인**으로 넘긴다.
#     SP 가 쓰는 건 `SELECT DISTINCT ITEM_CODE FROM #TEMP_PART_DTL` 뿐이라 동치다.
_MATSTOCK_SQL = """
;WITH PL(ITEM_CODE) AS ( SELECT v.c FROM ( {vals} ) v(c) ),
T_SUB_CTE(item_code, mat_code, stock_qty, pr_stock_qty, set_stock_qty, FIX_STOCK_QTY) AS (
    SELECT s.mat_code, s.mat_code,
           CONVERT(int, ISNULL(SUM(s.stock_qty),0)),
           CONVERT(int, ISNULL(SUM(s.pr_stock_qty),0)),
           CONVERT(int, ISNULL(SUM(s.set_stock_qty),0)),
           0
      FROM (
            /*생산파트재고*/
            SELECT A.mat_code, 0 AS stock_qty, A.STOCK_QTY AS PR_STOCK_QTY, 0 AS SET_STOCK_QTY, 0 AS FIX_STOCK_QTY
              FROM PL T
              JOIN {S}.pr_t_mat_stock_wh A WITH (NOLOCK) ON T.ITEM_CODE = A.MAT_CODE
             WHERE A.stock_qty <> 0 AND A.part_code NOT IN ('P0001','P0002')
            UNION ALL
            /*사급재고 — ★계획과 조인 없음(SP 332~335 그대로). 전체 사급재고를 싣는다*/
            SELECT a.mat_code, 0, A.STOCK_QTY, 0, 0
              FROM {S}.PU_T_SAGUB_STOCK A WITH (NOLOCK)
              JOIN {S}.pr_m_item M WITH (NOLOCK) ON A.MAT_CODE = M.ITEM_CODE
             WHERE M.SAGUB_STOCK_FLAG = '1'
            UNION ALL
            /*자재창고재고*/
            SELECT A.mat_code, A.stock_qty, 0, 0, 0
              FROM PL T
              JOIN {S}.pu_t_mat_stock_wh A WITH (NOLOCK) ON T.ITEM_CODE = A.MAT_CODE
             WHERE A.cust_code = 'Z99990' AND A.stock_qty <> 0
           ) S
     GROUP BY s.mat_code
    HAVING SUM(s.stock_qty) <> 0 OR SUM(s.PR_STOCK_QTY) <> 0 OR SUM(s.SET_STOCK_QTY) <> 0
    UNION ALL
    /*재귀 — 보유재고를 하위 자재 소요로 환산 전파(SP 348~356)*/
    SELECT cb.item_code, b.mat_code, 0, 0, 0,
           CONVERT(int, CASE WHEN cb.FIX_STOCK_QTY <> 0 THEN cb.FIX_STOCK_QTY
                             ELSE (cb.pr_stock_qty + cb.stock_qty) END * b.use_qty)
      FROM T_SUB_CTE cb
      JOIN {S}.pr_m_item_bom b WITH (NOLOCK) ON cb.mat_code = b.item_code
     WHERE ISNULL(b.except_flag,'0') <> '1'
)
SELECT s.item_code, s.mat_code,
       ISNULL(SUM(s.stock_qty),0), ISNULL(SUM(s.pr_stock_qty),0),
       ISNULL(SUM(s.set_stock_qty),0), ISNULL(SUM(s.FIX_STOCK_QTY),0)
  FROM T_SUB_CTE S
 GROUP BY s.item_code, s.mat_code
OPTION (MAXRECURSION 100)
"""


def _lit(s):
    """SQL 문자열 리터럴. 작은따옴표만 이스케이프하면 안전하다.

       ★품번에는 괄호·＃ 등이 들어간다(실측 MJU65551101-SUB(4)).
         화이트리스트로 문자를 고르면 그런 품번이 **조용히 빠져** 재고가 0이 된다
         (첫 diff 에서 pr_stock_qty 17→0 으로 드러났다). 문자 제한을 두지 않는다."""
    return "'" + _s(s).replace("'", "''") + "'"


def _vals_cte(items):
    """VALUES 인라인 CTE — 파라미터 2,100개 한계를 피해 리터럴로 만든다."""
    safe = [f"({_lit(t)})" for t in items if _s(t)]
    return "VALUES " + ",".join(safe or ["('')"])


def load_mat_stock(cur, rows):
    """#TEMP_MAT_STOCK → {(item,mat): (stock, pr, set, fix)}"""
    items = sorted({r["item_code"] for r in rows if r["item_code"]})
    sql = _MATSTOCK_SQL.format(vals=_vals_cte(items), S=S)
    cur.execute(sql)
    out = {}
    for r in cur.fetchall():
        out[(_s(r[0]), _s(r[1]))] = (_f(r[2]), _f(r[3]), _f(r[4]), _f(r[5]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ BOM 전개 2벌 → #TEMP_BOM_MAT / #TEMP_BOM_ASSY (mat_list)
#   SP 381~546행. 사내생산(GOLE_GAGONG_PROC_CODE) + 사급(GOLE_IN_CUST_CODE) 두 갈래를
#   #TEMP_BOM_MAT 에 UNION 한 뒤 도번별로 MAT_LIST 를 만든다.
#
#   ★두 CTE 의 종료조건이 서로 다르다(그대로 복제):
#     #1(사내생산) except_flag='0' AND (vir='1' OR in_cust>'' OR work='P2' OR 공정마스터없음)
#     #2(사급)     except_flag='0' 만 — 정지조건 없음 → MAXRECURSION 100 으로 끊긴다
# ─────────────────────────────────────────────────────────────────────────────
_BOM_SQL = """
;WITH PL(ITEM_CODE, GAGONG_PROC_CODE, ASSY_ITEM_CODE, PROC_SEQ) AS (
    SELECT CAST(v.a AS varchar(20)), CAST(v.b AS varchar(10)),
           CAST(v.c AS varchar(20)), CAST(v.d AS smallint)
      FROM ( {vals} ) v(a,b,c,d)
),
CTE1(item_code, item_gagong_proc_code, mat_code, cum_use_qty, sagub_flag, SET_EXCEPT_FLAG,
     WH_GAGONG_PROC_CODE, vir_item_flag, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, WORK_CODE, ITEM_CLASS) AS (
    /*앵커 — 자기자신(SP 387~402)*/
    SELECT DISTINCT
           CAST(T.item_code AS varchar(20)), CAST(T.GAGONG_PROC_CODE AS varchar(10)),
           CAST(T.ITEM_CODE AS varchar(20)),
           CONVERT(NUMERIC(18,5),1),
           CAST('0' AS varchar(1)), CAST('0' AS varchar(1)),
           CAST('IS0001' AS varchar(10)), CAST('0' AS varchar(1)),
           CAST(AM.IN_CUST_CODE AS varchar(10)),
           CAST(IIF(AM.IN_CUST_CODE>'','',IIF(AM.WORK_CODE='P2','IS0001',
               (SELECT TOP 1 GAGONG_PROC_CODE FROM {S}.PR_M_ITEM_PROC_GAGONG WITH (NOLOCK)
                 WHERE ITEM_CODE = T.ITEM_CODE AND PROC_SEQ = 1))) AS varchar(10)),
           CAST(AM.WORK_CODE AS varchar(10)), CAST(AM.ITEM_CLASS AS varchar(30))
      FROM PL T
      JOIN {S}.pr_m_item AM WITH (NOLOCK) ON T.item_code = AM.item_code
     WHERE T.proc_seq <= 1
    UNION ALL
    /*재귀(SP 405~422) — 하위품이 사내생산이 아닌 것까지만*/
    SELECT CAST(cb.item_code AS varchar(20)), CAST(cb.item_gagong_proc_code AS varchar(10)),
           CAST(b.mat_code AS varchar(20)),
           CONVERT(NUMERIC(18,5), cb.cum_use_qty * b.use_qty),
           CAST(b.sagub_flag AS varchar(1)), CAST(ISNULL(b.SET_EXCEPT_FLAG,'0') AS varchar(1)),
           CAST(b.WH_GAGONG_PROC_CODE AS varchar(10)), CAST(b.vir_item_flag AS varchar(1)),
           CAST(IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_IN_CUST_CODE, AM.IN_CUST_CODE) AS varchar(10)),
           CAST(IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_GAGONG_PROC_CODE,
               IIF(AM.IN_CUST_CODE>'','',
                   (SELECT GAGONG_PROC_CODE FROM {S}.PR_M_ITEM_PROC_GAGONG WITH (NOLOCK)
                     WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1))) AS varchar(10)),
           CAST(M.WORK_CODE AS varchar(10)), CAST(M.ITEM_CLASS AS varchar(30))
      FROM CTE1 cb
      JOIN {S}.pr_m_item_bom b  WITH (NOLOCK) ON cb.mat_code = b.item_code
      JOIN {S}.pr_m_item      AM WITH (NOLOCK) ON b.item_code = AM.item_code
      JOIN {S}.pr_m_item      M  WITH (NOLOCK) ON b.mat_code  = M.item_code
     WHERE ISNULL(b.except_flag,'0')='0'
       AND (B.VIR_ITEM_FLAG='1' OR M.IN_CUST_CODE>'' OR M.WORK_CODE='P2'
            OR NOT EXISTS (SELECT * FROM {S}.PR_M_ITEM_PROC_GAGONG WITH (NOLOCK) WHERE ITEM_CODE = B.MAT_CODE))
),
CTE2(item_code, item_gagong_proc_code, mat_code, cum_use_qty, sagub_flag, SET_EXCEPT_FLAG,
     WH_GAGONG_PROC_CODE, vir_item_flag, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, WORK_CODE, ITEM_CLASS) AS (
    /*앵커 — 한 레벨 미리 내려감(SP 468~487)*/
    SELECT DISTINCT
           CAST(T.item_code AS varchar(20)), CAST(T.GAGONG_PROC_CODE AS varchar(10)),
           CAST(b.mat_code AS varchar(20)),
           CONVERT(NUMERIC(18,5), b.use_qty),
           CAST(b.sagub_flag AS varchar(1)), CAST(ISNULL(b.SET_EXCEPT_FLAG,'0') AS varchar(1)),
           CAST(IIF(b.WH_GAGONG_PROC_CODE>'', b.WH_GAGONG_PROC_CODE, 'IS0001') AS varchar(10)),
           CAST(b.vir_item_flag AS varchar(1)),
           CAST(AM.IN_CUST_CODE AS varchar(10)),
           CAST(IIF(AM.IN_CUST_CODE>'','',
               (SELECT TOP 1 GAGONG_PROC_CODE FROM {S}.PR_M_ITEM_PROC_GAGONG WITH (NOLOCK)
                 WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1)) AS varchar(10)),
           CAST(M.WORK_CODE AS varchar(10)), CAST(M.ITEM_CLASS AS varchar(30))
      FROM PL T
      JOIN {S}.pr_m_item_bom b  WITH (NOLOCK) ON T.ITEM_CODE = b.item_code
      JOIN {S}.pr_m_item      AM WITH (NOLOCK) ON b.item_code = AM.item_code
      JOIN {S}.pr_m_item      M  WITH (NOLOCK) ON b.mat_code  = M.item_code
     WHERE ISNULL(b.except_flag,'0')='0'
       AND T.ASSY_ITEM_CODE = T.ITEM_CODE
       AND T.proc_seq <= 1
    UNION ALL
    /*재귀(SP 490~506) — ★정지조건 없음*/
    SELECT CAST(cb.item_code AS varchar(20)), CAST(cb.item_gagong_proc_code AS varchar(10)),
           CAST(b.mat_code AS varchar(20)),
           CONVERT(NUMERIC(18,5), cb.cum_use_qty * b.use_qty),
           CAST(b.sagub_flag AS varchar(1)), CAST(ISNULL(b.SET_EXCEPT_FLAG,'0') AS varchar(1)),
           CAST(b.WH_GAGONG_PROC_CODE AS varchar(10)), CAST(b.vir_item_flag AS varchar(1)),
           CAST(IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_IN_CUST_CODE, AM.IN_CUST_CODE) AS varchar(10)),
           CAST(IIF(CB.VIR_ITEM_FLAG='1', CB.GOLE_GAGONG_PROC_CODE,
               IIF(AM.IN_CUST_CODE>'','',
                   (SELECT GAGONG_PROC_CODE FROM {S}.PR_M_ITEM_PROC_GAGONG WITH (NOLOCK)
                     WHERE ITEM_CODE = B.ITEM_CODE AND PROC_SEQ = 1))) AS varchar(10)),
           CAST(M.WORK_CODE AS varchar(10)), CAST(M.ITEM_CLASS AS varchar(30))
      FROM CTE2 cb
      JOIN {S}.pr_m_item_bom b  WITH (NOLOCK) ON cb.mat_code = b.item_code
      JOIN {S}.pr_m_item      AM WITH (NOLOCK) ON b.item_code = AM.item_code
      JOIN {S}.pr_m_item      M  WITH (NOLOCK) ON b.mat_code  = M.item_code
     WHERE ISNULL(b.except_flag,'0')='0'
),
STK(MAT_CODE, STOCK_QTY, PR_STOCK_QTY) AS (
    SELECT v.m, v.s, v.p FROM ( {stk} ) v(m,s,p)
),
BM AS (
    /*사내생산(SP 428~440)*/
    SELECT A.item_code, A.item_gagong_proc_code, A.GOLE_IN_CUST_CODE, A.GOLE_GAGONG_PROC_CODE,
           A.MAT_CODE, SUM(A.CUM_USE_QTY) AS USE_QTY,
           MAX(A.WORK_CODE) AS WORK_CODE, MAX(A.item_class) AS item_class,
           MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0)) AS STOCK_QTY
      FROM CTE1 A
      LEFT JOIN STK B ON A.MAT_CODE = B.MAT_CODE
     WHERE A.WORK_CODE = ? AND A.SET_EXCEPT_FLAG <> '1'
       AND A.GOLE_GAGONG_PROC_CODE > '' AND ISNULL(A.vir_item_flag,'0') <> '1'
     GROUP BY A.item_code, A.item_gagong_proc_code, A.GOLE_IN_CUST_CODE, A.GOLE_GAGONG_PROC_CODE, A.MAT_CODE
    UNION ALL
    /*사급(SP 513~524)*/
    SELECT A.item_code, A.item_gagong_proc_code, A.GOLE_IN_CUST_CODE, A.GOLE_GAGONG_PROC_CODE,
           A.MAT_CODE, SUM(A.CUM_USE_QTY),
           MAX(A.WORK_CODE), MAX(A.item_class),
           MAX(ISNULL(B.STOCK_QTY,0) + ISNULL(B.PR_STOCK_QTY,0))
      FROM CTE2 A
      LEFT JOIN STK B ON A.MAT_CODE = B.MAT_CODE
     WHERE A.WORK_CODE = ? AND A.SET_EXCEPT_FLAG = '0'
       AND A.GOLE_IN_CUST_CODE > '' AND ISNULL(A.vir_item_flag,'0') <> '1'
     GROUP BY A.item_code, A.item_gagong_proc_code, A.GOLE_IN_CUST_CODE, A.GOLE_GAGONG_PROC_CODE, A.MAT_CODE
)
SELECT item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE,
       MAX(WORK_CODE), MAX(item_class), STRING_AGG(MAT_CODE, ',')
         WITHIN GROUP (ORDER BY MAT_CODE)
  FROM BM
 GROUP BY item_code, item_gagong_proc_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE
OPTION (MAXRECURSION 100)
"""


def load_bom_assy(cur, rows, mat_stock, work_code):
    """#TEMP_BOM_ASSY → {(item, gpc, gole_cust, gole_proc): (work_code, item_class, mat_list)}

       ※SP 는 #TEMP_BOM_MAT 를 (item,gpc,gole_cust,gole_proc,MAT_CODE) 로 GROUP BY 하므로
         MAT_CODE 중복이 이미 제거된다 → STRING_AGG 도 중복 없다. 정렬은 SP 544~545
         (item_code, GOLE_IN_CUST_CODE, GOLE_GAGONG_PROC_CODE, MAT_CODE) 의 마지막 키와 동치."""
    seen, buf = set(), []
    for r in rows:
        k = (r["item_code"], r["gagong_proc_code"], r["assy_item_code"], int(r["proc_seq"]))
        if k not in seen:
            seen.add(k); buf.append(k)
    vals = ("VALUES " + ",".join(
        f"({_lit(a)},{_lit(b)},{_lit(c)},{d})" for a, b, c, d in buf)) if buf else "VALUES ('','','',0)"

    agg = {}
    for (_it, mt), v in mat_stock.items():
        s, p = agg.get(mt, (0.0, 0.0))
        agg[mt] = (s + v[0], p + v[1])
    stk = ("VALUES " + ",".join(
        f"({_lit(m)},{s},{p})" for m, (s, p) in agg.items())) if agg else "VALUES ('',0,0)"

    cur.execute(_BOM_SQL.format(vals=vals, stk=stk, S=S), work_code, work_code)
    out = {}
    for r in cur.fetchall():
        out[(_s(r[0]), _s(r[1]), _s(r[2]), _s(r[3]))] = (_s(r[4]), _s(r[5]), _s(r[6]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ 도번고정재고 — SP 562~642행. TAG 70.
# ─────────────────────────────────────────────────────────────────────────────
def step_fix(rows, mat_stock, to_ymd):
    # 세팅 ①(SP 564~570): UPPER<>ITEM 이면 (upper,item) 키로 **대입**
    # 세팅 ②(SP 572~578): UPPER=ITEM  이면 (assy,item) 키로 **누적**
    #   두 WHERE 가 배타적이라 실제로는 행마다 하나만 적용된다.
    agg = {}
    for (it, mt), v in mat_stock.items():
        agg[(it, mt)] = agg.get((it, mt), 0.0) + v[3]
    for r in rows:
        if r["upper_item_code"] != r["item_code"]:
            r["fix_stock_qty"] = agg.get((r["upper_item_code"], r["item_code"]), 0.0)
    for r in rows:
        if r["upper_item_code"] == r["item_code"]:
            r["fix_stock_qty"] = r["fix_stock_qty"] + agg.get((r["assy_item_code"], r["item_code"]), 0.0)

    _snap_fetch(rows)
    _run_cursor(
        rows, to_ymd=to_ymd, tag=70, mul_use=False,
        # ★[SP버그 B2] SP 588 WHERE 는 STOCK_QTY+PR_STOCK_QTY+FIX_STOCK_QTY>0 인데
        #   앞 두 컬럼은 SP 646(자재재고 세팅)에서야 채워진다. 이 커서 시점엔 0이므로
        #   실질 조건은 fix_stock_qty>0 이다. 그대로 복제한다.
        where=lambda r: r["fix_stock_qty"] > 0,
        # SP 589
        order=lambda r: (r["upper_item_code"], r["item_code"], r["gagong_proc_code"],
                         r["part_plan_ymd"], r["part_output_hm"], r["plan_ymd"],
                         r["output_hm"], r["work_order"], r["split_work_order"]),
        # SP 597~603
        group=lambda r: (r["upper_item_code"], r["item_code"], r["proc_seq"]),
        stock_of=lambda r: r["fix_stock_qty"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ 자재재고 — SP 644~713행. TAG 70.
# ─────────────────────────────────────────────────────────────────────────────
def step_jae(rows, mat_stock, to_ymd):
    # 세팅(SP 646~652): MAT_CODE 로 묶어 ITEM_CODE 에 대입
    agg = {}
    for (_it, mt), v in mat_stock.items():
        s, p = agg.get(mt, (0.0, 0.0))
        agg[mt] = (s + v[0], p + v[1])
    for r in rows:
        s, p = agg.get(r["item_code"], (0.0, 0.0))
        r["stock_qty"], r["pr_stock_qty"] = s, p

    _snap_fetch(rows)
    _run_cursor(
        rows, to_ymd=to_ymd, tag=70, mul_use=False,
        # SP 661 — 이번엔 앞 두 컬럼이 채워져 있으므로 조건이 그대로 산다
        where=lambda r: (r["stock_qty"] + r["pr_stock_qty"] + r["fix_stock_qty"]) > 0,
        # SP 662
        order=lambda r: (r["item_code"], r["proc_seq"], r["gagong_proc_code"],
                         r["part_plan_ymd"], r["part_output_hm"], r["plan_ymd"],
                         r["output_hm"], r["work_order"], r["split_work_order"]),
        # SP 670~675 — ★UPPER 없음(도번고정보다 넓은 그룹)
        group=lambda r: (r["item_code"], r["proc_seq"]),
        stock_of=lambda r: r["stock_qty"] + r["pr_stock_qty"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# ⑧ #TEMP_MAT_MOVE_PLAN + JP_PRINT_QTY → 파트재고 커서 — SP 718~800행. TAG 50.
# ─────────────────────────────────────────────────────────────────────────────
def build_move_plan(cur, rows, bom_assy, to_ymd, pu_part, item_desc, prod_rate):
    """SP 719~759 — #TEMP_PART_DTL ⋈ #TEMP_BOM_ASSY(INNER). DISTINCT.
       ★조인키 = (item_code, gagong_proc_code) 두 개뿐. bom_assy 는 그 위에
         (gole_cust, gole_proc) 까지 쪼개져 있으므로 **한 계획행이 여러 GOLE 로 퍼진다**."""
    by_ig = {}
    for (it, gpc, gc, gp), v in bom_assy.items():
        by_ig.setdefault((it, gpc), []).append((gc, gp, v))

    out, seen = [], set()
    for a in rows:
        if a["part_plan_ymd"] > to_ymd:
            continue
        for gc, gp, v in by_ig.get((a["item_code"], a["gagong_proc_code"]), ()):
            m = {
                "gagong_proc_code": a["gagong_proc_code"], "part_group_code": "",
                "work_order": a["work_order"], "split_work_order": a["split_work_order"],
                "assy_item_code": a["assy_item_code"], "upper_item_code": a["upper_item_code"],
                "item_code": a["item_code"],
                "item_desc": item_desc.get(a["assy_item_code"], ""),
                "gole_code": (gc if gc else "Z99990"),
                "gole_gagong_proc_code": gp, "gole_in_cust_code": gc,
                "mat_work_code": v[0], "work_code": a["work_code"],
                "proc_seq": a["proc_seq"], "use_qty": a["use_qty"],
                "part_plan_ymd": a["part_plan_ymd"], "part_output_hm": a["part_output_hm"],
                "plan_ymd": a["plan_ymd"], "output_hm": a["output_hm"], "line_no": a["line_no"],
                "part_plan_qty": a["part_plan_qty"], "finish_qty": a["finish_qty"],
                "finish_tag": a["finish_tag"], "sale_qty": a["sale_qty"],
                "assy_stock_qty": a["assy_stock_qty"], "stock_qty": a["stock_qty"],
                "pr_stock_qty": a["pr_stock_qty"], "fix_stock_qty": a["fix_stock_qty"],
                "jp_print_qty": 0.0,
                "prod_rate": prod_rate.get(a["gagong_proc_code"], 0.0),
                "wh_gagong_proc_code": pu_part, "item_class": v[1], "mat_list": v[2],
                # bom_level 은 #TEMP_MAT_MOVE_PLAN 에 없다(파트 커서 UPDATE 키에서 빠짐)
                "bom_level": 0,
            }
            k = tuple(sorted((kk, str(vv)) for kk, vv in m.items()))
            if k in seen:      # SP 719 SELECT DISTINCT
                continue
            seen.add(k)
            out.append(m)
    return out


def step_part(cur, mrows, to_ymd):
    """가공세트재고 + 이동전표발행분 → JP_PRINT_QTY, 그 뒤 파트재고 커서(TAG 50)."""
    # 세팅 ①(SP 764~767) 가공세트재고 = 대입
    cur.execute(f"""SELECT ITEM_CODE, ISNULL(IN_CUST_CODE,''), SUM(STOCK_QTY)
                      FROM {S}.PU_T_SET_GAGONG_STOCK WITH (NOLOCK)
                     GROUP BY ITEM_CODE, ISNULL(IN_CUST_CODE,'')""")
    setm = {(_s(r[0]), _s(r[1])): _f(r[2]) for r in cur.fetchall()}
    # 세팅 ②(SP 769~777) 이동전표 미확정 = 2단 집계 후 누적
    cur.execute(f"""SELECT ITEM_CODE, GOLE_CODE, SUM(SET_QTY) FROM (
                        SELECT ITEM_CODE, MAINT_GROUP_SEQ,
                               MAX(IIF(SAGUB_CUST_CODE>'',SAGUB_CUST_CODE,'Z99990')) AS GOLE_CODE,
                               MAX(SET_QTY) AS SET_QTY
                          FROM {S}.PU_T_STOCK_MAINT_GAGONG_MOVE WITH (NOLOCK)
                         WHERE IN_CONFIRM_FLAG='0'
                         GROUP BY ITEM_CODE, MAINT_GROUP_SEQ) T
                     GROUP BY ITEM_CODE, GOLE_CODE""")
    mvm = {(_s(r[0]), _s(r[1])): _f(r[2]) for r in cur.fetchall()}

    for r in mrows:
        k = (r["item_code"], r["gole_code"])
        if k in setm:
            r["jp_print_qty"] = setm[k]
        if k in mvm:
            r["jp_print_qty"] = r["jp_print_qty"] + mvm[k]

    _snap_fetch(mrows)
    _run_cursor(
        mrows, to_ymd=to_ymd, tag=50, mul_use=False, upd_gole=True,
        where=lambda r: r["jp_print_qty"] > 0,          # SP 788
        # SP 789
        order=lambda r: (r["gole_code"], r["item_code"], r["proc_seq"],
                         r["part_plan_ymd"], r["part_output_hm"], r["plan_ymd"],
                         r["output_hm"], r["work_order"], r["split_work_order"]),
        group=lambda r: (r["gole_code"], r["item_code"], r["proc_seq"]),
        stock_of=lambda r: r["jp_print_qty"])
    return mrows


# ─────────────────────────────────────────────────────────────────────────────
# ⑨ 7키 GROUP BY + 32칸 피벗 × 4종 — SP 719~(최종 SELECT)
#    _00 = from_ymd 미만 전부 · _01 = +0일 · _NN = +(NN-1)일 · _31 = +30일
#    finish_tag 는 **MIN + ISNULL(...,0)** (SUM/MAX 아님)
# ─────────────────────────────────────────────────────────────────────────────
_TAGCLR = {90: 9486586, 70: 65535, 50: 39270, 30: 12632256, 10: 39270}


def _ymd_add(y6, k):
    from datetime import date as _date
    y, m, d = 2000 + int(y6[0:2]), int(y6[2:4]), int(y6[4:6])
    t = _date(y, m, d) + timedelta(days=k)
    return "%02d%02d%02d" % (t.year % 100, t.month, t.day)


def aggregate(mrows, from_ymd, wh_desc, gole_proc_desc, gole_cust_desc,
              mat_work_desc, item_class_desc, pu_part):
    """SP 최종 SELECT 재현 → 174컬럼 dict 목록."""
    slots = [None] * 32
    for n in range(1, 32):
        slots[n] = _ymd_add(from_ymd, n - 1)

    G = {}
    for a in mrows:
        k = (a["gagong_proc_code"], a["assy_item_code"], a["upper_item_code"],
             a["item_code"], a["item_class"], a["gole_gagong_proc_code"],
             a["gole_in_cust_code"])
        g = G.get(k)
        if g is None:
            g = G[k] = {"_max": {}, "_min": {}, "plan": 0.0, "fin": 0.0,
                        "pq": [0.0] * 32, "fq": [0.0] * 32, "ft": [None] * 32}
        for c in ("part_group_code", "item_desc", "mat_work_code", "work_code", "use_qty",
                  "sale_qty", "assy_stock_qty", "stock_qty", "pr_stock_qty",
                  "fix_stock_qty", "jp_print_qty", "mat_list", "prod_rate"):
            v = a.get(c)
            if c not in g["_max"] or (v is not None and v > g["_max"][c]):
                g["_max"][c] = v
        for c in ("proc_seq", "part_plan_ymd", "part_output_hm", "plan_ymd",
                  "output_hm", "line_no"):
            v = a.get(c)
            if c not in g["_min"] or (v is not None and v < g["_min"][c]):
                g["_min"][c] = v
        g["plan"] += a["part_plan_qty"]
        g["fin"] += a["finish_qty"]
        ppy = a["part_plan_ymd"]
        idx = 0 if ppy < from_ymd else next((n for n in range(1, 32) if slots[n] == ppy), None)
        if idx is not None:
            g["pq"][idx] += a["part_plan_qty"]
            g["fq"][idx] += a["finish_qty"]
            t = a["finish_tag"]
            g["ft"][idx] = t if g["ft"][idx] is None else min(g["ft"][idx], t)

    out = []
    for k, g in G.items():
        gpc, assy, upper, item, icls, gproc, gcust = k
        d = {"gagong_proc_code": gpc, "part_group_code": g["_max"].get("part_group_code") or "",
             "work_order": "", "split_work_order": "",
             "assy_item_code": assy, "upper_item_code": upper, "item_code": item,
             "MAT_CODE": "", "ITEM_DESC": g["_max"].get("item_desc") or "",
             "GOLE_GAGONG_PROC_CODE": gproc, "GOLE_IN_CUST_CODE": gcust,
             "mat_work_code": g["_max"].get("mat_work_code") or "",
             "work_code": g["_max"].get("work_code") or "",
             "proc_seq": g["_min"].get("proc_seq"), "use_qty": g["_max"].get("use_qty"),
             "mat_use_qty": 0,
             "part_plan_ymd": g["_min"].get("part_plan_ymd") or "",
             "part_output_hm": g["_min"].get("part_output_hm") or "",
             "plan_ymd": g["_min"].get("plan_ymd") or "",
             "output_hm": g["_min"].get("output_hm") or "",
             "line_no": g["_min"].get("line_no") or "",
             "plan_qty": g["plan"], "finish_qty": g["fin"],
             "sale_qty": g["_max"].get("sale_qty") or 0,
             "assy_stock_qty": g["_max"].get("assy_stock_qty") or 0,
             "stock_qty": g["_max"].get("stock_qty") or 0,
             "pr_stock_qty": g["_max"].get("pr_stock_qty") or 0,
             "fix_stock_qty": g["_max"].get("fix_stock_qty") or 0,
             "jp_print_qty": g["_max"].get("jp_print_qty") or 0,
             "min_part_plan_ymd_hm": "",
             "KIT_WH_STOCK_QTY": 0, "WH_STOCK_QTY": 0,
             "STACKER_STOCK_QTY": 0, "OTHER_STOCK_QTY": 0,
             "item_class": icls, "mat_list": g["_max"].get("mat_list") or "",
             "item_st": 0, "prod_rate": g["_max"].get("prod_rate") or 0,
             "prod_calc_flag": "0",
             "wh_gagong_proc_code": pu_part,
             "WH_GAGONG_PROC_DESC": wh_desc,
             "GOLE_GAGONG_PROC_DESC": gole_proc_desc.get(gproc, ""),
             "GOLE_IN_CUST_DESC": gole_cust_desc.get(gcust, ""),
             "MAT_WORK_DESC": mat_work_desc.get(g["_max"].get("mat_work_code") or "", ""),
             "c_height": 0, "item_class_desc": item_class_desc.get(icls, "")}
        for n in range(32):
            ii = "%02d" % n
            d["plan_qty_" + ii] = g["pq"][n]
            d["finish_qty_" + ii] = g["fq"][n]
            t = g["ft"][n] if g["ft"][n] is not None else 0
            d["finish_tag_" + ii] = t
            d["color_" + ii] = _TAGCLR.get(t, 16777215)
        out.append(d)
    return out


def _codemaps(cur, pu_part):
    """코드명 조회 — SP 최종 SELECT 의 상관 서브쿼리들."""
    cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(GAGONG_PROC_DESC,'') FROM {S}.PR_M_PROC_GAGONG WITH (NOLOCK)")
    gp = {_s(r[0]): _s(r[1]) for r in cur.fetchall()}
    cur.execute(f"SELECT CUST_CODE, ISNULL(CUST_DESC,'') FROM {S}.CM_M_CUST WITH (NOLOCK)")
    gc = {_s(r[0]): _s(r[1]) for r in cur.fetchall()}
    cur.execute(f"SELECT WORK_CODE, ISNULL(WORK_DESC,'') FROM {S}.PR_M_WORK WITH (NOLOCK)")
    mw = {_s(r[0]): _s(r[1]) for r in cur.fetchall()}
    cur.execute(f"""SELECT DETAIL_CODE, ISNULL(DETAIL_DESC,'') FROM {S}.CM_M_MASTER_DETAIL
                     WITH (NOLOCK) WHERE KIND_CODE='PR008'""")
    ic = {_s(r[0]): _s(r[1]) for r in cur.fetchall()}
    return gp, gc, mw, ic, gp.get(_s(pu_part), "")


def compute(cur, from_ymd, to_ymd, work_code, pu_part="IS0001"):
    """★진입점 — SP 와 같은 174컬럼 목록을 낸다.

       pr_part_code·sagub_cust_code 는 SP 에서 죽은 파라미터라 받지 않는다."""
    rows = load_plan(cur)
    step_sale(cur, rows, to_ymd)
    step_assy(cur, rows, to_ymd)
    ms = load_mat_stock(cur, rows)
    ba = load_bom_assy(cur, rows, ms, work_code)
    step_fix(rows, ms, to_ymd)
    step_jae(rows, ms, to_ymd)

    assys = sorted({r["assy_item_code"] for r in rows if r["assy_item_code"]})
    idesc = {}
    for i in range(0, len(assys), 900):
        ck = assys[i:i + 900]; ph = ",".join("?" * len(ck))
        cur.execute(f"SELECT ITEM_CODE, ISNULL(ITEM_DESC,'') FROM {S}.pr_m_item WITH (NOLOCK) WHERE ITEM_CODE IN ({ph})", *ck)
        for r in cur.fetchall():
            idesc[_s(r[0])] = _s(r[1])
    cur.execute(f"SELECT GAGONG_PROC_CODE, ISNULL(PROD_RATE,0) FROM {S}.PR_M_PROC_GAGONG WITH (NOLOCK)")
    prate = {_s(r[0]): _f(r[1]) for r in cur.fetchall()}

    mrows = build_move_plan(cur, rows, ba, to_ymd, pu_part, idesc, prate)
    step_part(cur, mrows, to_ymd)

    gp, gc, mw, ic, whd = _codemaps(cur, pu_part)
    return aggregate(mrows, from_ymd, whd, gp, gc, mw, ic, pu_part)
