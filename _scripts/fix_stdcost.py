# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client

# STD_COST 재적재 (unit_price NULL 방지: COALESCE)
db_client.execute_query("""
INSERT INTO CM_ITEM_PRICE_HIST(item_cd,partner_cd,price_type,currency,price_uom_cd,apply_ymd,
                               mat_cost,proc_cost,other_cost,unit_price,main_flag)
SELECT m.item_cd, NULLIF(LTRIM(RTRIM(c.CUST_CODE)),''), 'STD_COST',
       ISNULL(NULLIF(LTRIM(RTRIM(c.CURRENCY)),''),'KRW'), 'EA',
       TRY_CONVERT(DATE,'20'+LTRIM(RTRIM(c.COST_APPLY_YMD))),
       c.MAT_COST, c.PROC_COST, c.OTHER_COST,
       COALESCE(c.ITEM_COST, ISNULL(c.MAT_COST,0)+ISNULL(c.PROC_COST,0)+ISNULL(c.OTHER_COST,0), 0),
       CASE WHEN c.MAIN_FLAG IN ('1','Y') THEN 'Y' ELSE 'N' END
FROM PR_M_ITEM_COST c JOIN CM_ITEM_MST m ON m.item_cd=LTRIM(RTRIM(c.ITEM_CODE))
WHERE TRY_CONVERT(DATE,'20'+LTRIM(RTRIM(c.COST_APPLY_YMD))) IS NOT NULL
""")
print("STD_COST 적재 완료")

print("\n[price_type 분포]")
print(db_client.run_query("SELECT price_type, COUNT(*) c FROM CM_ITEM_PRICE_HIST GROUP BY price_type ORDER BY c DESC").to_string(index=False))
print(f"\nPRICE_HIST 총건수: {db_client.run_query('SELECT COUNT(*) FROM CM_ITEM_PRICE_HIST').iloc[0,0]}")
# 소급/시계열 검증: 한 품목이 여러 시점 단가를 갖는가
print("\n[한 품목이 다중 시점 단가 보유(시계열 검증)]")
print(db_client.run_query("""
SELECT TOP 3 item_cd, price_type, COUNT(*) versions, MIN(apply_ymd) first_ymd, MAX(apply_ymd) last_ymd
FROM CM_ITEM_PRICE_HIST GROUP BY item_cd, price_type HAVING COUNT(*)>1
ORDER BY COUNT(*) DESC
""").to_string(index=False))
# FK 무결성 위반 0 확인
print("\n[FK 고아행 점검 - 0이어야 정상]")
print(db_client.run_query("""
SELECT
 (SELECT COUNT(*) FROM CM_ITEM_PRICE_HIST p WHERE NOT EXISTS(SELECT 1 FROM CM_ITEM_MST m WHERE m.item_cd=p.item_cd)) price_orphan,
 (SELECT COUNT(*) FROM CM_ITEM_SUPPLIER s WHERE NOT EXISTS(SELECT 1 FROM CM_ITEM_MST m WHERE m.item_cd=s.item_cd)) sup_orphan
""").to_string(index=False))
