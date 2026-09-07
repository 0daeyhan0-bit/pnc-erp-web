# -*- coding: utf-8 -*-
"""거래처 단일데이터셋 호환 뷰 — nx.v_cm_m_cust (2026-09-08)

왜
  단일데이터셋 원칙(CUTOVER_RETRY_REQUIREMENTS §0): 거래처는 nx.cust 단일 소스.
  기존 코드 147곳이 미러 nx.CM_M_CUST(레거시 복사·컷오버후 write-dead)를 직독했다.
  컬럼명이 달라(CUST_DESC≠cust_name) 147곳 직접 재매핑은 오종 위험 → nx.cust 위에
  레거시 컬럼명을 노출하는 **호환 뷰**를 두고, 코드는 테이블명만 nx.v_cm_m_cust 로 교체.
  ⟹ 데이터 소스는 nx.cust 단일. 미러 CM_M_CUST 는 컷오버 시 은퇴(drop) 대상.

  ※CM_M_CUST_MAGAM(거래처 마감일)은 별개 테이블 — 이 뷰와 무관, 코드도 그대로 둔다.

멱등: 재실행 안전(DROP+CREATE). 재컷오버 배포 시 DB(nx=PARTNER_ERP_TEST3)에 1회 실행.
사용: python _migration/create_v_cm_m_cust.py
"""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

DDL = """
CREATE VIEW nx.v_cm_m_cust AS
SELECT
  cust_code AS CUST_CODE, cust_name AS CUST_DESC, cust_name AS REG_CUST_DESC,
  CAST(NULL AS varchar(100)) AS CUST_DESCE, CAST(NULL AS varchar(100)) AS CUST_DESCH,
  biz_no AS BUSINESS_NO, corp_no AS CORP_NO, owner_name AS OWNER_NAME,
  CAST(NULL AS varchar(50)) AS OWNER_NAMEE, CAST(NULL AS varchar(50)) AS OWNER_NAMEH,
  resident_no AS SSN, business_tag AS BUSINESS_TAG, biz_type AS BUSI_TYPE, biz_item AS BUSI_KIND,
  CAST(NULL AS varchar(10)) AS DEPT_CODE, charge_user_id AS CHARGE_USER_ID,
  post_no AS POST_NO, address1 AS ADDRESS, address2 AS ADDRESS_DTL,
  recv_post_no AS RECV_POST_NO, recv_address AS RECV_ADDRESS, recv_address_dtl AS RECV_ADDRESS_DTL,
  tel AS PHONE_NO, fax AS FAX_NO, CAST(NULL AS varchar(100)) AS EMAIL, homepage AS HOMEPAGE,
  charge_name AS CHARGE_NAME, charge_tel AS CHARGE_PHONE_NO, CAST(NULL AS varchar(30)) AS CHARGE_FAX_NO,
  charge_hp AS CHARGE_CELPHONE_NO, charge_email AS CHARGE_EMAIL, charge_rank AS CHARGE_CHIEF_DESC,
  cust_type AS CUST_TYPE, in_flag AS IN_FLAG, out_flag AS OUT_FLAG, outside_flag AS OUTSIDE_FLAG,
  bank_flag AS BANK_FLAG, bank_code AS BANK_CODE, bank_bookno AS BANK_BOOKNO, bank_person_name AS BANK_PERSON_NAME,
  cms_no AS CMS_NO, prod_check_flag AS PROD_CHECK_FLAG, dlvy_day AS DLVY_DAY, dlvy_day2 AS DLVY_DAY2,
  set_in_flag AS SET_IN_FLAG, sagub_out_flag AS SAGUB_OUT_FLAG, heat_label_flag AS HEAT_LABEL_FLAG,
  use_flag AS USE_FLAG, remarks AS REMARKS,
  CAST(NULL AS varchar(30)) AS INSERT_USER_ID, CAST(NULL AS datetime) AS INSERT_DATETIME,
  CAST(NULL AS varchar(30)) AS INSERT_IP, CAST(NULL AS varchar(50)) AS INSERT_COMPUTER, CAST(NULL AS varchar(50)) AS INSERT_WINDOW,
  upd_user AS UPDATE_USER_ID, upd_dt AS UPDATE_DATETIME,
  CAST(NULL AS varchar(30)) AS UPDATE_IP, CAST(NULL AS varchar(50)) AS UPDATE_COMPUTER, CAST(NULL AS varchar(50)) AS UPDATE_WINDOW,
  ue_date AS UE_DATE, ue_week AS UE_WEEK, ue_day AS UE_DAY, gc_gubun AS GC_GUBUN
FROM nx.cust
"""


def main():
    cn = _nx(); c = cn.cursor()
    c.execute("IF OBJECT_ID('nx.v_cm_m_cust','V') IS NOT NULL DROP VIEW nx.v_cm_m_cust")
    cn.commit()
    c.execute(DDL); cn.commit()
    c.execute("SELECT COUNT(*) FROM nx.v_cm_m_cust")
    print("nx.v_cm_m_cust 생성 완료 · 행수:", c.fetchone()[0])
    cn.close()


if __name__ == "__main__":
    main()
