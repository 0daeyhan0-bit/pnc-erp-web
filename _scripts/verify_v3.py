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

show("완제품 종류(prod_kind) 분포 = LGROUP 제품라인", """
SELECT prod_kind, COUNT(*) c FROM CM_ITEM_PROD GROUP BY prod_kind ORDER BY c DESC
""")
show("310(구 LG사급) 589품목이 이제 어떤 type/category로?", """
SELECT m.item_type, m.category_cd, COUNT(*) c
FROM CM_ITEM_MST m
WHERE m.item_cd IN (SELECT LTRIM(RTRIM(ITEM_CODE)) FROM PR_M_ITEM WHERE LTRIM(RTRIM(ITEM_SGROUP))='310')
GROUP BY m.item_type, m.category_cd
""")
show("분류마스터에 '사급' 카테고리가 없는지 확인 (310 없어야 정상)", """
SELECT category_cd, category_nm, legacy_sgroup FROM CM_ITEM_CATEGORY ORDER BY category_cd
""")
