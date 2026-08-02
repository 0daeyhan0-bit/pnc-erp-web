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

show("0. 총 거래처 수 / 사용여부", """
SELECT COUNT(*) total, SUM(CASE WHEN USE_FLAG='Y' THEN 1 ELSE 0 END) use_y FROM CM_M_CUST
""")

# 역할 플래그 분포
show("1. 역할 플래그 분포 (IN=매입/OUT=매출/OUTSIDE=외주/SAGUB_OUT=사급출고/SET_IN)", """
SELECT
 SUM(CASE WHEN IN_FLAG='Y' THEN 1 ELSE 0 END) in_maeip,
 SUM(CASE WHEN OUT_FLAG='Y' THEN 1 ELSE 0 END) out_maechul,
 SUM(CASE WHEN OUTSIDE_FLAG='Y' THEN 1 ELSE 0 END) outside_oeju,
 SUM(CASE WHEN SAGUB_OUT_FLAG='Y' THEN 1 ELSE 0 END) sagub_out,
 SUM(CASE WHEN SET_IN_FLAG='Y' THEN 1 ELSE 0 END) set_in
FROM CM_M_CUST
""")

# 역할 조합 (한 거래처가 여러 역할?)
show("2. 매입&매출 겸용 등 역할 조합", """
SELECT ISNULL(IN_FLAG,'') in_f, ISNULL(OUT_FLAG,'') out_f, ISNULL(OUTSIDE_FLAG,'') oj_f,
       ISNULL(SAGUB_OUT_FLAG,'') sg_f, COUNT(*) c
FROM CM_M_CUST GROUP BY ISNULL(IN_FLAG,''),ISNULL(OUT_FLAG,''),ISNULL(OUTSIDE_FLAG,''),ISNULL(SAGUB_OUT_FLAG,'')
ORDER BY c DESC
""")

# CUST_TYPE 값 + 코드마스터 의미 (PR011 거래처분류)
show("3. CUST_TYPE 분포", "SELECT ISNULL(CUST_TYPE,'(null)') CUST_TYPE, COUNT(*) c FROM CM_M_CUST GROUP BY CUST_TYPE ORDER BY c DESC")
show("3b. 코드마스터 PR011(거래처분류) 정의", """
SELECT DETAIL_CODE, DETAIL_DESC FROM CM_M_MASTER_DETAIL WHERE KIND_CODE='PR011' ORDER BY DETAIL_CODE
""")

# 핵심 협력사/고객 찾기
show("4. 핵심 거래처 (LG/미래정밀/대원/FONE)", """
SELECT CUST_CODE, CUST_DESC, IN_FLAG, OUT_FLAG, OUTSIDE_FLAG, SAGUB_OUT_FLAG, CUST_TYPE, USE_FLAG
FROM CM_M_CUST
WHERE CUST_DESC LIKE N'%미래정밀%' OR CUST_DESC LIKE N'%대원%' OR CUST_DESC LIKE '%FONE%'
   OR CUST_DESC LIKE N'%엘지%' OR CUST_DESC LIKE '%LG%' OR CUST_DESC LIKE N'%LG전자%'
ORDER BY CUST_DESC
""")

# GC_GUBUN, BUSINESS_TAG 의미 파악
show("5. GC_GUBUN / BUSINESS_TAG 분포", """
SELECT ISNULL(GC_GUBUN,'(null)') gc, ISNULL(BUSINESS_TAG,'(null)') biz_tag, COUNT(*) c
FROM CM_M_CUST GROUP BY GC_GUBUN, BUSINESS_TAG ORDER BY c DESC
""")
