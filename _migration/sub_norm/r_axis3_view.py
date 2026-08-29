# -*- coding: utf-8 -*-
"""품목 3축(조달/생산/판매) 유도 파생뷰 nx.v_item_axis3.
   ITEM_MASTER_CLASSIFY_DESIGN §5 step3. 조달/생산=sgroup(배타·CASE stable), 판매=lgroup(PR005 명칭).
   ★표시·집계용 = 원가/소요 엔진 미참여(§0 안전선). 뷰=읽기전용·데이터 무변경. 멱등(CREATE OR ALTER).
   커버리지(2026-08-29·25,367품목): 조달4556·생산19309·판매17976·미분류1501. sgroup커버 94.1%.
   실행: python r_axis3_view.py (멱등·즉시 적용)."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
DDL = """CREATE OR ALTER VIEW nx.v_item_axis3 AS
SELECT i.item_code, i.item_name, i.sgroup, i.lgroup,
  CASE i.sgroup WHEN '210' THEN N'원소재' WHEN '220' THEN N'원자재' WHEN '230' THEN N'용접링'
    WHEN '240' THEN N'용접봉' WHEN '310' THEN N'LG사급' WHEN '910' THEN N'부자재'
    WHEN '991' THEN N'제조소모품' WHEN '992' THEN N'일반소모품' WHEN '993' THEN N'판매소모품'
    ELSE NULL END AS axis_procure,
  CASE i.sgroup WHEN '110' THEN N'완제품ASSY' WHEN '120' THEN N'SUB-ASSY' WHEN '130' THEN N'가공품'
    ELSE NULL END AS axis_produce,
  -- 현행조달 표기(C블록·참조) — make_type. ★route가 진실이나 route에 make_type 없음 → 마스터값 표기만(§1 C·§3-1 신뢰주의).
  CASE i.make_type WHEN '1' THEN N'제작' WHEN '2' THEN N'외주' WHEN '3' THEN N'구매'
    WHEN '4' THEN N'LG사급' WHEN '5' THEN N'외주완성' ELSE NULL END AS procure_method,
  CASE WHEN i.lgroup IS NOT NULL AND LTRIM(RTRIM(i.lgroup)) <> '' THEN i.lgroup ELSE NULL END AS axis_sales_code,
  lg.DETAIL_DESC AS axis_sales,
  CASE WHEN i.sgroup IS NULL OR LTRIM(RTRIM(i.sgroup)) = '' THEN 1 ELSE 0 END AS unclassified
FROM nx.item i
LEFT JOIN (SELECT DETAIL_CODE, MAX(DETAIL_DESC) DETAIL_DESC FROM nx.CM_M_MASTER_DETAIL
           WHERE KIND_CODE = 'PR005' GROUP BY DETAIL_CODE) lg
  ON lg.DETAIL_CODE = LTRIM(RTRIM(i.lgroup))"""
c.execute(DDL)
print("뷰 nx.v_item_axis3 생성/갱신 완료")
c.execute("SELECT COUNT(*), SUM(IIF(axis_procure IS NOT NULL,1,0)), SUM(IIF(axis_produce IS NOT NULL,1,0)), SUM(IIF(axis_sales_code IS NOT NULL,1,0)), SUM(unclassified) FROM nx.v_item_axis3")
r = c.fetchone(); print(f"검증: 총 {r[0]} | 조달 {r[1]} | 생산 {r[2]} | 판매 {r[3]} | 미분류 {r[4]}")
n.close()
