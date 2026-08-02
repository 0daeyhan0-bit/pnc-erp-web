# -*- coding: utf-8 -*-
"""
[프로그램 이관/합치기] 품질불량관리  QA_T_ERROR(레거시) → nx.qc_error
- 멱등: legacy_seq 기준으로 이미 이관된 행은 건너뜀 (수시 재실행 안전)
- 정제: 전 코드/텍스트 TRIM, 플래그 varchar→bit('1'만 1), BOX_NO int→nvarchar
- 이관 제외(빈/상수 '0'): ERROR_PROC_DESC, MEASURE_DESC, ERROR_POSITION(빈), SAC_REG_INFO, RE_ERROR_FLAG
- 매핑: WATER_CHECK_FLAG→susu_flag, RE_INSP_CHECK→reinsp_flag, WORK_CUST_CODE→partner_code, WEIGHT_QTY→scrap_weight
- 컷오버 후 nx.qc_error 단일 원장. 실행: python sync_qc_error.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()

# 이관 전 현황
c.execute("SELECT COUNT(*) FROM PARTNER_ERP.dbo.QA_T_ERROR"); leg = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM nx.qc_error"); nx_before = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM nx.qc_error WHERE legacy_seq IS NOT NULL"); mig_before = c.fetchone()[0]
print(f"레거시 QA_T_ERROR {leg}건 / nx.qc_error {nx_before}건(이관분 {mig_before}) → 신규분만 삽입")

INS = """
INSERT INTO nx.qc_error
 (error_ymd,error_tag,division,cust_line,pg_reg,item_code,work_code,partner_code,proc_code,mach_code,
  box_no,inspector,error_member,error_item1,error_item2,error_item3,error_desc,color,
  lot_qty,error_qty,real_error_qty,error_cause,measure_info,progress_stats,target_date,charge_name,
  check_result,finish_flag,susu_flag,reinsp_flag,scrap_weight,legacy_seq,upd_user,upd_dt)
SELECT
  LTRIM(RTRIM(e.ERROR_YMD)), LTRIM(RTRIM(e.ERROR_TAG)), LTRIM(RTRIM(e.DIVISION_DESC)),
  LTRIM(RTRIM(e.CUST_LINE)), LTRIM(RTRIM(e.PG_REG_INFO)), LTRIM(RTRIM(e.ITEM_CODE)),
  LTRIM(RTRIM(e.WORK_CODE)), NULLIF(LTRIM(RTRIM(e.WORK_CUST_CODE)),''), LTRIM(RTRIM(e.PROC_CODE)),
  LTRIM(RTRIM(e.MACH_CODE)), CAST(e.BOX_NO AS NVARCHAR(20)), LTRIM(RTRIM(e.INSPECTOR_MEMBER_NAME)),
  LTRIM(RTRIM(e.ERROR_MEMBER_NAME)), LTRIM(RTRIM(e.ERROR_ITEM)), LTRIM(RTRIM(e.ERROR_ITEM2)),
  LTRIM(RTRIM(e.ERROR_ITEM3)), LTRIM(RTRIM(e.ERROR_DESC)), LTRIM(RTRIM(e.ERROR_COLOR)),
  e.LOT_QTY, e.ERROR_QTY, e.REAL_ERROR_QTY, LTRIM(RTRIM(e.ERROR_CAUSE)),
  LTRIM(RTRIM(e.MEASURE_INFO)), LTRIM(RTRIM(e.PROGRESS_STATS)), LTRIM(RTRIM(e.TARGET_DATE)),
  LTRIM(RTRIM(e.CHARGE_NAME)), LTRIM(RTRIM(e.CHECK_RESULT)),
  CASE WHEN LTRIM(RTRIM(e.FINISH_FLAG))='1' THEN 1 ELSE 0 END,
  CASE WHEN LTRIM(RTRIM(e.WATER_CHECK_FLAG))='1' THEN 1 ELSE 0 END,
  CASE WHEN LTRIM(RTRIM(e.RE_INSP_CHECK))='1' THEN 1 ELSE 0 END,
  e.WEIGHT_QTY, CAST(e.SEQ AS INT), 'MIGRATION', GETDATE()
FROM PARTNER_ERP.dbo.QA_T_ERROR e
WHERE CAST(e.SEQ AS INT) NOT IN (SELECT legacy_seq FROM nx.qc_error WHERE legacy_seq IS NOT NULL)
"""
c.execute(INS)
ins = c.rowcount
cn.commit()

# 검증: 건수/합계 대사
c.execute("SELECT COUNT(*) FROM nx.qc_error WHERE legacy_seq IS NOT NULL"); mig_after = c.fetchone()[0]
c.execute("SELECT SUM(CAST(ERROR_QTY AS BIGINT)), SUM(CAST(LOT_QTY AS BIGINT)) FROM PARTNER_ERP.dbo.QA_T_ERROR"); leg_eq, leg_lot = c.fetchone()
c.execute("SELECT SUM(CAST(error_qty AS BIGINT)), SUM(CAST(lot_qty AS BIGINT)) FROM nx.qc_error WHERE legacy_seq IS NOT NULL"); nx_eq, nx_lot = c.fetchone()
print(f"삽입 {ins}건 → 이관분 {mig_before}→{mig_after}")
print(f"검증 불량수량합: 레거시 {leg_eq} vs nx이관 {nx_eq}  {'OK' if leg_eq==nx_eq else '★불일치'}")
print(f"검증 LOT수량합 : 레거시 {leg_lot} vs nx이관 {nx_lot}  {'OK' if leg_lot==nx_lot else '★불일치'}")
print(f"검증 건수      : 레거시 {leg} vs nx이관 {mig_after}  {'OK' if leg==mig_after else '★불일치'}")
