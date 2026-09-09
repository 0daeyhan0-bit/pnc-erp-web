# -*- coding: utf-8 -*-
"""품목 호환뷰 nx.v_pr_m_item 생성 — 미러 PR_M_ITEM 모양으로 nx.item 노출 (2026-09-09)

■ 왜 뷰인가
  미러 107컬럼 vs 클린 60컬럼(겹침 36). 컬럼명이 다르고(IN_CUST_CODE→in_cust)
  일부는 클린에 아예 없다. 뷰로 미러 모양을 그대로 내주면
  **코드는 테이블명 한 단어만** 바꾸면 되고 롤백도 쉽다(거래처 v_cm_m_cust 와 같은 방식).

■ 실측 근거 (2026-09-09)
  nx.item 25,403행 · 미러 24,154행 · **미러에만 있는 품목 0건**(결손 없음)
  코드가 실제로 쓰는 컬럼은 6종뿐 —
     ITEM_CODE · IN_CUST_CODE · WORK_CODE · ITEM_CLASS · SAGUB_STOCK_FLAG · GC_GUBUN

  전수 대조:
     IN_CUST_CODE → in_cust           24,154/24,154 (100%)
     WORK_CODE    → work_code         24,154/24,154 (100%)
     SAGUB_STOCK_FLAG                 24,154/24,154 (100%)
     ITEM_CLASS   → item_class        결손 12건 → fix_item_class_260909.py 로 선행 보정 완료

  ★GC_GUBUN 은 미러·라이브 모두 24,154행 **전부 빈 값**(죽은 컬럼).
    move580web.py 는 이를 출력 컬럼으로만 흘려보내고 필터에 쓰지 않는다(L76·84·92).
    → 뷰에서 '' 로 고정한다. 값이 없던 것을 없는 채로 두는 것이라 동작 동일.

■ 뷰에 담는 것
  코드가 쓰는 6종 + 화면·조인에 흔한 것들(품명·규격·중량 등)을 미러 이름으로.
  ★없는 것을 지어내지 않는다 — 클린에 근거가 없으면 NULL/'' 로 두고 주석에 남긴다(§1-9-1).
"""
import sys, os, io, argparse
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
A = ap.parse_args()

DDL = """
CREATE VIEW nx.v_pr_m_item AS
SELECT
  item_code                         AS ITEM_CODE,
  item_name                         AS ITEM_DESC,
  item_spec                         AS ITEM_SIZE,
  item_type                         AS ITEM_TYPE,
  sgroup                            AS ITEM_SGROUP,
  lgroup                            AS ITEM_LGROUP,
  item_group                        AS ITEM_GROUP,
  item_class                        AS ITEM_CLASS,
  item_status                       AS ITEM_STATUS,
  metal_gubun                       AS METAL_GUBUN,
  use_gubun                         AS USE_GUBUN,
  diam                              AS ITEM_DIAM,
  thick                             AS ITEM_THICK,
  length                            AS ITEM_LENGTH,
  net_weight                        AS NET_WEIGHT,
  item_weight                       AS ITEM_WEIGHT,
  unit                              AS UNIT,
  make_type                         AS MAKE_TYPE,
  in_cust                           AS IN_CUST_CODE,
  sale_cust                         AS SALE_CUST_CODE,
  work_code                         AS WORK_CODE,
  proc_gubun                        AS PROC_GUBUN,
  prod_tag                          AS PROD_TAG,
  prod_rate                         AS PROD_RATE,
  pur_gubun                         AS PUR_GUBUN,
  obtain_gubun                      AS OBTAIN_GUBUN,
  cost_gubun                        AS COST_GUBUN,
  has_gagong                        AS HAS_GAGONG,
  silver_flag                       AS SILVER_FLAG,
  sagub_stock_flag                  AS SAGUB_STOCK_FLAG,
  sub_mat_flag                      AS SUB_MAT_FLAG,
  sub_mat_wh                        AS SUB_MAT_WH_CODE,
  std_won_mat_flag                  AS STD_WON_MAT_FLAG,
  kitting_min                       AS KITTING_MIN,
  dlvy_except_flag                  AS DLVY_EXCEPT_FLAG,
  set_except_day                    AS SET_EXCEPT_DAY,
  safe_stock_min                    AS SAFE_STOCK_MIN,
  safe_stock_max                    AS SAFE_STOCK_MAX,
  weld_point_in                     AS WELD_POINT_IN,
  weld_point_out                    AS WELD_POINT_OUT,
  jig_code                          AS JIG_CODE,
  cut_gubun                         AS CUT_GUBUN,
  pipe_kind                         AS PIPE_KIND,
  item_pipe_type                    AS ITEM_PIPE_TYPE,
  item_pipe_material                AS ITEM_PIPE_MATERIAL,
  item_pipe_id                      AS ITEM_PIPE_ID,
  item_radius                       AS ITEM_RADIUS,
  item_cost                         AS ITEM_COST,
  tariff_rate                       AS TARIFF_RATE,
  use_flag                          AS USE_FLAG,
  remarks                           AS ITEM_REMARK,
  -- ★미러·라이브 모두 전 행 빈 값인 죽은 컬럼. move580web 은 출력에만 쓴다(필터 아님).
  --   클린에 근거가 없으므로 지어내지 않고 빈 값 그대로 노출한다(§1-9-1).
  CAST('' AS varchar(1))            AS GC_GUBUN
FROM nx.item
"""

nx = _nx(); cur = nx.cursor()

print("=" * 92)
print(" nx.v_pr_m_item — {}".format("생성" if A.apply else "DRY-RUN"))
print("=" * 92)

if not A.apply:
    print(DDL)
    print("   --apply 를 붙이면 생성한다.")
    nx.close(); sys.exit(0)

cur.execute("IF OBJECT_ID('nx.v_pr_m_item') IS NOT NULL DROP VIEW nx.v_pr_m_item")
nx.commit()
cur.execute(DDL)
nx.commit()
print("   ✔ 생성 완료")

cur.execute("SELECT COUNT(*) FROM nx.v_pr_m_item")
print("   행수 {:,}".format(cur.fetchone()[0]))

print()
print(" 검증 — 코드가 쓰는 6컬럼, 미러 대비")
for c in ('ITEM_CODE', 'IN_CUST_CODE', 'WORK_CODE', 'ITEM_CLASS', 'SAGUB_STOCK_FLAG', 'GC_GUBUN'):
    cur.execute("""SELECT COUNT(*),
          SUM(CASE WHEN RTRIM(ISNULL(CAST(v.[{0}] AS nvarchar(60)),''))
                    = RTRIM(ISNULL(CAST(m.[{0}] AS nvarchar(60)),'')) THEN 1 ELSE 0 END)
       FROM nx.v_pr_m_item v JOIN nx.PR_M_ITEM m ON RTRIM(m.ITEM_CODE)=RTRIM(v.ITEM_CODE)""".format(c))
    t, s = cur.fetchone()
    print("   {} {:<20s} {:,}/{:,}".format("✔" if s == t else "★", c, s or 0, t))
nx.close()
