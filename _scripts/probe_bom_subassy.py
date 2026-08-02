# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n===== {t} =====")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# 부모별 구성요소 수 + 그중 반제품(S_ASSY) 자식 수  (버전 중복 제거: distinct 자식)
# 부모/자식 성격은 CM_ITEM_MST.item_type 사용
show("1. 부모(완제품/반제품)별 총자식수 · SUB-ASSY(반제품)자식수 분포", """
;WITH bom AS (
  SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) parent, LTRIM(RTRIM(MAT_CODE)) child
  FROM PR_M_ITEM_BOM
),
agg AS (
  SELECT b.parent,
         COUNT(*) total_child,
         SUM(CASE WHEN cm.item_type='S_ASSY' THEN 1 ELSE 0 END) subassy_child
  FROM bom b
  LEFT JOIN CM_ITEM_MST cm ON cm.item_cd=b.child
  GROUP BY b.parent
)
SELECT subassy_child AS [SUB_ASSY_자식수], COUNT(*) AS [해당_부모수]
FROM agg GROUP BY subassy_child ORDER BY subassy_child
""")

# 2. 부모의 성격별로 (완제품 PROD가 실제 SUB-ASSY를 몇개 갖나)
show("2. 부모 item_type별 평균/최대 SUB-ASSY 자식수", """
;WITH bom AS (SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) parent, LTRIM(RTRIM(MAT_CODE)) child FROM PR_M_ITEM_BOM),
agg AS (
  SELECT b.parent, SUM(CASE WHEN cm.item_type='S_ASSY' THEN 1 ELSE 0 END) sa
  FROM bom b LEFT JOIN CM_ITEM_MST cm ON cm.item_cd=b.child GROUP BY b.parent
)
SELECT pm.item_type AS 부모유형, COUNT(*) 부모수,
       AVG(CAST(a.sa AS float)) 평균SUBASSY, MAX(a.sa) 최대SUBASSY
FROM agg a JOIN CM_ITEM_MST pm ON pm.item_cd=a.parent
GROUP BY pm.item_type ORDER BY 부모수 DESC
""")

# 3. BOM 최대 레벨 (bomLLC = low level code)
show("3. BOM 레벨(bomLLC) 분포 = 다단계 깊이", """
SELECT ISNULL(bomLLC,'(null)') bomLLC, COUNT(DISTINCT ITEM_CODE) parents
FROM PR_M_ITEM_BOM GROUP BY bomLLC ORDER BY bomLLC
""")

# 4. SUB-ASSY를 많이 가진 완제품 상위 예시
show("4. SUB-ASSY 많은 부모 상위 10", """
;WITH bom AS (SELECT DISTINCT LTRIM(RTRIM(ITEM_CODE)) parent, LTRIM(RTRIM(MAT_CODE)) child FROM PR_M_ITEM_BOM),
agg AS (
  SELECT b.parent, COUNT(*) tot, SUM(CASE WHEN cm.item_type='S_ASSY' THEN 1 ELSE 0 END) sa
  FROM bom b LEFT JOIN CM_ITEM_MST cm ON cm.item_cd=b.child GROUP BY b.parent
)
SELECT TOP 10 a.parent, pm.item_nm, pm.item_type, a.tot 총자식, a.sa SUBASSY수
FROM agg a JOIN CM_ITEM_MST pm ON pm.item_cd=a.parent
ORDER BY a.sa DESC
""")
