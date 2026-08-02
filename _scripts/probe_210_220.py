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

# 1) 특성 프로파일 비교
show("1. 210(원소재) vs 220(원자재) 특성 비교", """
SELECT ITEM_SGROUP,
 COUNT(*) cnt,
 SUM(CASE WHEN ITEM_LENGTH>0 THEN 1 ELSE 0 END) has_length,
 SUM(CASE WHEN ITEM_DESC LIKE N'%컷팅%' OR ITEM_DESC LIKE N'%소재컷%' THEN 1 ELSE 0 END) nm_cutting,
 SUM(CASE WHEN ITEM_DESC LIKE N'%직관%' THEN 1 ELSE 0 END) nm_straight,
 SUM(CASE WHEN ITEM_DESC LIKE '%[0-9]*[0-9]%' THEN 1 ELSE 0 END) nm_hasdim,
 AVG(CAST(ITEM_LENGTH AS float)) avg_len,
 AVG(CAST(ITEM_WEIGHT AS float)) avg_wt
FROM PR_M_ITEM WHERE ITEM_SGROUP IN ('210','220') GROUP BY ITEM_SGROUP
""")

# 2) 매입처(구매) 유무: 각 그룹이 실제 사오는 물건인가
show("2. 매입처 등록 여부 (품목별_매입처정보2 기준)", """
SELECT p.ITEM_SGROUP, COUNT(DISTINCT p.ITEM_CODE) items,
 COUNT(DISTINCT s.[도번]) with_supplier
FROM PR_M_ITEM p
LEFT JOIN [품목별_매입처정보2] s ON LTRIM(RTRIM(s.[도번]))=LTRIM(RTRIM(p.ITEM_CODE))
WHERE p.ITEM_SGROUP IN ('210','220') GROUP BY p.ITEM_SGROUP
""")

# 3) BOM 관계: 각 그룹이 모품목(만들어짐)인지 자재(소모)인지
show("3. BOM에서 모품목(ITEM_CODE=만듦) vs 자재(MAT_CODE=소모) 등장", """
SELECT g.ITEM_SGROUP,
 SUM(CASE WHEN par.ITEM_CODE IS NOT NULL THEN 1 ELSE 0 END) appears_as_parent,
 SUM(CASE WHEN mat.MAT_CODE IS NOT NULL THEN 1 ELSE 0 END) appears_as_material
FROM PR_M_ITEM g
LEFT JOIN (SELECT DISTINCT ITEM_CODE FROM PR_M_ITEM_BOM) par ON par.ITEM_CODE=g.ITEM_CODE
LEFT JOIN (SELECT DISTINCT MAT_CODE FROM PR_M_ITEM_BOM) mat ON mat.MAT_CODE=g.ITEM_CODE
WHERE g.ITEM_SGROUP IN ('210','220') GROUP BY g.ITEM_SGROUP
""")

# 4) 210 자재를 소모하는 모품목의 SGROUP (210이 무엇으로 가공되나)
show("4. 210(원소재)을 자재로 쓰는 모품목의 SGROUP 분포", """
SELECT par.ITEM_SGROUP parent_sgroup, COUNT(*) c
FROM PR_M_ITEM_BOM b
JOIN PR_M_ITEM mat ON mat.ITEM_CODE=b.MAT_CODE AND mat.ITEM_SGROUP='210'
JOIN PR_M_ITEM par ON par.ITEM_CODE=b.ITEM_CODE
GROUP BY par.ITEM_SGROUP ORDER BY c DESC
""")
show("5. 220(원자재)을 자재로 쓰는 모품목의 SGROUP 분포", """
SELECT par.ITEM_SGROUP parent_sgroup, COUNT(*) c
FROM PR_M_ITEM_BOM b
JOIN PR_M_ITEM mat ON mat.ITEM_CODE=b.MAT_CODE AND mat.ITEM_SGROUP='220'
JOIN PR_M_ITEM par ON par.ITEM_CODE=b.ITEM_CODE
GROUP BY par.ITEM_SGROUP ORDER BY c DESC
""")

for sg in ['210','220']:
    show(f"{sg} 대표 품명 12건 (치수 포함)", f"""
    SELECT TOP 12 ITEM_CODE, ITEM_DESC, ITEM_DIAM diam, ITEM_THICK thick, ITEM_LENGTH len, ITEM_LGROUP lg
    FROM PR_M_ITEM WHERE ITEM_SGROUP='{sg}' ORDER BY ITEM_CODE
    """)
