# -*- coding: utf-8 -*-
import sys, io, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client
def show(t,q):
    print(f"\n== {t} ==")
    try: print(db_client.run_query(q).to_string(index=False))
    except Exception as e: print("ERR:", str(e)[:150])

# 1) cm_m_cust 컬럼 (CHARGE_USER_ID / cust_type 확인)
show("cm_m_cust 관련 컬럼", "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='cm_m_cust' AND (COLUMN_NAME LIKE '%CHARGE%' OR COLUMN_NAME LIKE '%TYPE%' OR COLUMN_NAME LIKE '%USER%')")

# 2) cust_type 분포
show("cust_type 분포", "SELECT ISNULL(cust_type,'') ctype, COUNT(*) cnt FROM cm_m_cust GROUP BY cust_type ORDER BY ctype")

# 3) 거래처분류 코드→이름 (마스터 상세에서 유상사급/절삭 검색)
show("거래처분류 후보(마스터상세 유상사급/절삭)", "SELECT KIND_CODE, DETAIL_CODE, DETAIL_DESC FROM CM_M_MASTER_DETAIL WHERE DETAIL_DESC LIKE '%유상사급%' OR DETAIL_DESC LIKE '%절삭%' ORDER BY KIND_CODE, DETAIL_CODE")

# 4) charge_user_id 샘플 + 사용자 마스터 후보 테이블
show("사용자 마스터 후보", "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND (TABLE_NAME LIKE '%USER%' OR TABLE_NAME LIKE '%EMP%' OR TABLE_NAME LIKE '%사원%' OR TABLE_NAME LIKE '%직원%') ORDER BY TABLE_NAME")

# 5) 월수불 테이블 컬럼 (last_in_ymd 유무)
show("PU_T_MONTH_STOCK_WH 컬럼", "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='PU_T_MONTH_STOCK_WH' ORDER BY ORDINAL_POSITION")
