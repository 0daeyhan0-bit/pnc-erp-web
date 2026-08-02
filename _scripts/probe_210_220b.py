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

# 재질 구분 (동/알루미늄/STS)
show("재질(METAL_GUBUN)·파이프종류(PIPE_KIND) 분포", """
SELECT ITEM_SGROUP, ISNULL(NULLIF(LTRIM(RTRIM(METAL_GUBUN)),''),'(blank)') metal,
       ISNULL(NULLIF(LTRIM(RTRIM(PIPE_KIND)),''),'(blank)') pipe_kind, COUNT(*) c
FROM PR_M_ITEM WHERE ITEM_SGROUP IN ('210','220')
GROUP BY ITEM_SGROUP, ISNULL(NULLIF(LTRIM(RTRIM(METAL_GUBUN)),''),'(blank)'),
         ISNULL(NULLIF(LTRIM(RTRIM(PIPE_KIND)),''),'(blank)')
ORDER BY ITEM_SGROUP, c DESC
""")

# 220이 210을 자재로 쓰나 / 210이 220을 자재로 쓰나 (절단 관계)
show("210<->220 직접 BOM 관계 (누가 누구로 만들어지나)", """
SELECT par.ITEM_SGROUP parent, mat.ITEM_SGROUP material, COUNT(*) c
FROM PR_M_ITEM_BOM b
JOIN PR_M_ITEM par ON par.ITEM_CODE=b.ITEM_CODE AND par.ITEM_SGROUP IN ('210','220')
JOIN PR_M_ITEM mat ON mat.ITEM_CODE=b.MAT_CODE AND mat.ITEM_SGROUP IN ('210','220')
GROUP BY par.ITEM_SGROUP, mat.ITEM_SGROUP
""")

# DIAM_GUBUN (외경/내경 구분?) 과 길이구간
show("길이 구간 분포 (210=장척 직관 가설 검증)", """
SELECT ITEM_SGROUP,
 SUM(CASE WHEN ITEM_LENGTH>=1000 THEN 1 ELSE 0 END) len_ge_1000mm,
 SUM(CASE WHEN ITEM_LENGTH>0 AND ITEM_LENGTH<1000 THEN 1 ELSE 0 END) len_lt_1000mm,
 SUM(CASE WHEN ITEM_LENGTH IS NULL OR ITEM_LENGTH=0 THEN 1 ELSE 0 END) len_zero
FROM PR_M_ITEM WHERE ITEM_SGROUP IN ('210','220') GROUP BY ITEM_SGROUP
""")
