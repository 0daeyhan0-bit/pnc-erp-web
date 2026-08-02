# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client

# price_hist partner 고아 확인 (partner_cd NOT NULL인 것만)
orph = db_client.run_query("""
SELECT COUNT(DISTINCT partner_cd) c FROM CM_ITEM_PRICE_HIST p
WHERE p.partner_cd IS NOT NULL AND NOT EXISTS(SELECT 1 FROM CM_PARTNER m WHERE m.partner_cd=p.partner_cd)
""").iloc[0,0]
print("PRICE_HIST partner 고아 코드수:", orph)

def add_fk(label, sql):
    try:
        db_client.execute_query(sql); print(f"[OK] {label}")
    except Exception as e:
        print(f"[SKIP] {label} -> {e}")

# 공급처 FK (고아 0 확인됨) 활성화
add_fk("FK CM_ITEM_SUPPLIER.partner_cd -> CM_PARTNER",
  "ALTER TABLE CM_ITEM_SUPPLIER WITH CHECK ADD CONSTRAINT FK_SUP_PARTNER FOREIGN KEY(partner_cd) REFERENCES CM_PARTNER(partner_cd)")

# price_hist FK — 고아 없을 때만
if orph == 0:
    add_fk("FK CM_ITEM_PRICE_HIST.partner_cd -> CM_PARTNER",
      "ALTER TABLE CM_ITEM_PRICE_HIST WITH CHECK ADD CONSTRAINT FK_PRICE_PARTNER FOREIGN KEY(partner_cd) REFERENCES CM_PARTNER(partner_cd)")
else:
    print(f"[HOLD] PRICE_HIST FK 보류 (고아 {orph}건 — 거래처 코드 정리 후 활성화)")

# 활성 FK 목록 확인
print("\n[품목↔거래처 활성 FK]")
print(db_client.run_query("""
SELECT fk.name, OBJECT_NAME(fk.parent_object_id) tbl, OBJECT_NAME(fk.referenced_object_id) ref
FROM sys.foreign_keys fk
WHERE OBJECT_NAME(fk.referenced_object_id)='CM_PARTNER'
""").to_string(index=False))
