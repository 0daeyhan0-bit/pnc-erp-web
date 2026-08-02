# -*- coding: utf-8 -*-
"""이중검증: 사용자 dw 로직으로 계산한 가공/용접 재고(PR_ITEM_STOCK) vs 정적 재고테이블(PR_T_MAT_STOCK_WH)"""
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",str(e)[:150])

# 1) 기준월 타당성: PR_T_MONTH_STOCK_WH 에 어떤 월마감이 있나 (2502가 최신인가?)
show("1. PR_T_MONTH_STOCK_WH 보유 월마감(STOCK_YYMM) 상위", """
SELECT TOP 12 STOCK_YYMM, COUNT(*) rows FROM PR_T_MONTH_STOCK_WH GROUP BY STOCK_YYMM ORDER BY STOCK_YYMM DESC
""")

# 2) 계산값(가공+용접) vs 정적 PR_T_MAT_STOCK_WH  — (item, line) 매칭 비교
#    정적: MAT_CODE, PART_CODE, STOCK_QTY   /  계산: item_cd, location(가공은 P0001), stock_qty
show("2. 계산 vs 정적 대조 (item x line)", """
;WITH calc AS (
  SELECT item_cd, CASE WHEN stock_stage='GAGONG' THEN 'P0001' ELSE location_cd END line, stock_qty
  FROM PR_ITEM_STOCK WHERE stock_stage IN ('GAGONG','WELD')
),
stat AS (
  SELECT LTRIM(RTRIM(MAT_CODE)) item_cd, LTRIM(RTRIM(PART_CODE)) line, SUM(STOCK_QTY) stock_qty
  FROM PR_T_MAT_STOCK_WH GROUP BY LTRIM(RTRIM(MAT_CODE)), LTRIM(RTRIM(PART_CODE))
)
SELECT
 SUM(CASE WHEN c.item_cd IS NOT NULL AND s.item_cd IS NOT NULL AND ABS(ISNULL(c.stock_qty,0)-ISNULL(s.stock_qty,0))<0.001 THEN 1 ELSE 0 END) 일치,
 SUM(CASE WHEN c.item_cd IS NOT NULL AND s.item_cd IS NOT NULL AND ABS(ISNULL(c.stock_qty,0)-ISNULL(s.stock_qty,0))>=0.001 THEN 1 ELSE 0 END) 수량불일치,
 SUM(CASE WHEN c.item_cd IS NOT NULL AND s.item_cd IS NULL THEN 1 ELSE 0 END) 계산에만,
 SUM(CASE WHEN c.item_cd IS NULL AND s.item_cd IS NOT NULL THEN 1 ELSE 0 END) 정적에만
FROM calc c FULL OUTER JOIN stat s ON s.item_cd=c.item_cd AND s.line=c.line
""")

# 3) 불일치 샘플 (수량이 다른 것)
show("3. 수량 불일치 샘플 10", """
;WITH calc AS (SELECT item_cd, CASE WHEN stock_stage='GAGONG' THEN 'P0001' ELSE location_cd END line, stock_qty FROM PR_ITEM_STOCK WHERE stock_stage IN ('GAGONG','WELD')),
stat AS (SELECT LTRIM(RTRIM(MAT_CODE)) item_cd, LTRIM(RTRIM(PART_CODE)) line, SUM(STOCK_QTY) stock_qty FROM PR_T_MAT_STOCK_WH GROUP BY LTRIM(RTRIM(MAT_CODE)),LTRIM(RTRIM(PART_CODE)))
SELECT TOP 10 ISNULL(c.item_cd,s.item_cd) item, ISNULL(c.line,s.line) line, c.stock_qty 계산, s.stock_qty 정적
FROM calc c FULL OUTER JOIN stat s ON s.item_cd=c.item_cd AND s.line=c.line
WHERE ABS(ISNULL(c.stock_qty,0)-ISNULL(s.stock_qty,0))>=0.001 AND c.item_cd IS NOT NULL AND s.item_cd IS NOT NULL
ORDER BY ABS(ISNULL(c.stock_qty,0)-ISNULL(s.stock_qty,0)) DESC
""")
