# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
print("DB:", db_client.DB_DATABASE)
# 우리 명명 제약이 이미 어디에 있나
print("\n[우리 FK/제약 이름이 이미 존재하는 곳]")
print(db_client.run_query("""
SELECT o.name AS constraint_name, OBJECT_NAME(fk.parent_object_id) AS on_table, o.type_desc
FROM sys.objects o
LEFT JOIN sys.foreign_keys fk ON fk.object_id=o.object_id
WHERE o.name IN ('FK_PRICE_ITEM','FK_PRICE_UOM','FK_PRICE_PARTNER','FK_SUP_ITEM','FK_SUP_PARTNER',
                 'FK_COMP_BOM','FK_COMP_CHILD','FK_BOM_PARENT','FK_ROLE_PARTNER')
""").to_string(index=False))
# 우리 next-gen 테이블 중 TEST3에 이미 있는 것
print("\n[TEST3에 이미 존재하는 우리 스키마 테이블]")
print(db_client.run_query("""
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'
AND TABLE_NAME IN ('CM_ITEM_MST','CM_ITEM_RAW','CM_ITEM_SUB','CM_ITEM_CON','CM_ITEM_SASSY','CM_ITEM_PROD',
 'CM_ITEM_SUPPLIER','CM_ITEM_PRICE_HIST','CM_ITEM_CATEGORY','CM_UOM','CM_UOM_CONV',
 'CM_PARTNER','CM_PARTNER_ROLE','CM_PARTNER_CLASS','CM_PROCESS','PR_BOM','PR_BOM_COMP',
 'PR_ROUTING','PR_ROUTING_OP','PR_ITEM_SOURCING','PR_PROD_ROUTE','PR_ROUTE_COST',
 'CM_ITEM_RAW_MAT','CM_ITEM_SUB_MAT','CM_ITEM_S_ASSY')
ORDER BY TABLE_NAME
""").to_string(index=False))
