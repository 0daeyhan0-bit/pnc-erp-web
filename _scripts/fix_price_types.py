# -*- coding: utf-8 -*-
"""단가 재분류: PR_M_ITEM_COST.COST_TAG (1=구매/E=판매수출/S=판매내수) → CM_ITEM_PRICE_HIST
   BOM이 CM_ITEM_MST를 FK참조하므로 단가 테이블만 타겟 재적재."""
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def run(l,q):
    try: db_client.execute_query(q); print("[OK]",l)
    except Exception as e: print("[FAIL]",l,"->",e)
def show(t,q):
    print(f"\n== {t} ==");
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:",e)

# 1) market_gubun 컬럼 추가 (없으면)
run("ADD market_gubun", """
IF COL_LENGTH('CM_ITEM_PRICE_HIST','market_gubun') IS NULL
  ALTER TABLE CM_ITEM_PRICE_HIST ADD market_gubun VARCHAR(10) NULL
""")

# 2) 단가 전체 재적재
run("DELETE price_hist", "DELETE FROM CM_ITEM_PRICE_HIST")
run("INSERT (COST_TAG 기반)", """
INSERT INTO CM_ITEM_PRICE_HIST(item_cd,partner_cd,price_type,market_gubun,currency,price_uom_cd,apply_ymd,
                               mat_cost,proc_cost,other_cost,unit_price,main_flag)
SELECT m.item_cd, NULLIF(LTRIM(RTRIM(c.CUST_CODE)),''),
       CASE WHEN LTRIM(RTRIM(c.COST_TAG))='1' THEN 'BUY' ELSE 'SALE' END,
       CASE LTRIM(RTRIM(c.COST_TAG)) WHEN 'E' THEN 'EXPORT' WHEN 'S' THEN 'DOMESTIC' ELSE NULL END,
       ISNULL(NULLIF(LTRIM(RTRIM(c.CURRENCY)),''),'KRW'), 'EA',
       TRY_CONVERT(DATE,'20'+LTRIM(RTRIM(c.COST_APPLY_YMD))),
       c.MAT_COST, c.PROC_COST, c.OTHER_COST,
       COALESCE(c.ITEM_COST, ISNULL(c.MAT_COST,0)+ISNULL(c.PROC_COST,0)+ISNULL(c.OTHER_COST,0), 0),
       'N'
FROM PR_M_ITEM_COST c JOIN CM_ITEM_MST m ON m.item_cd=LTRIM(RTRIM(c.ITEM_CODE))
WHERE LTRIM(RTRIM(c.COST_TAG)) IN ('1','E','S')
  AND TRY_CONVERT(DATE,'20'+LTRIM(RTRIM(c.COST_APPLY_YMD))) IS NOT NULL
""")
run("main_flag 재계산(현행단가)", """
;WITH cur AS (SELECT price_id, ROW_NUMBER() OVER
   (PARTITION BY item_cd, ISNULL(partner_cd,''), price_type, ISNULL(market_gubun,'') ORDER BY apply_ymd DESC) rn
   FROM CM_ITEM_PRICE_HIST)
UPDATE p SET main_flag='Y' FROM CM_ITEM_PRICE_HIST p JOIN cur ON cur.price_id=p.price_id WHERE cur.rn=1
""")

# 3) 검증
show("price_type x market 분포", """
SELECT price_type, ISNULL(market_gubun,'-') mkt, COUNT(*) c
FROM CM_ITEM_PRICE_HIST GROUP BY price_type, market_gubun ORDER BY c DESC""")
show("검증: 6851A20022W 현행단가 (구매/판매)", """
SELECT price_type, ISNULL(market_gubun,'-') mkt, partner_cd, CONVERT(varchar,apply_ymd,23) ymd, unit_price
FROM CM_ITEM_PRICE_HIST WHERE item_cd='6851A20022W' AND main_flag='Y'
ORDER BY price_type, market_gubun, partner_cd""")
