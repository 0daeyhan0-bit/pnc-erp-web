# -*- coding: utf-8 -*-
"""
[프로그램 이관/합치기] 거래처MASTER  CM_M_CUST(레거시 w_cm_master_055) → nx.cust
- ★위하고(WEHAGO) 일반거래처 36컬럼 코어 정합 + PNC 확장(거래처구분·역할·사급/세트/열처리·결제조건 등)
- 더존 연동 대비: 코어 컬럼명이 위하고 엑셀 교환포맷과 1:1 매핑 (_schema/WEHAGO_거래처등록_reference.md)
- 멱등: CUST_CODE 신규만 삽입(nx CRUD 추가분 보존). 스키마 불일치 시 재생성.
- 실행: python sync_cust.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client, pyodbc
cn = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)
c = cn.cursor()

DDL = """CREATE TABLE nx.cust (
  cust_code NVARCHAR(10) NOT NULL PRIMARY KEY,
  cust_name NVARCHAR(50), biz_no NVARCHAR(12), resident_no NVARCHAR(13), resident_flag NVARCHAR(1),
  owner_name NVARCHAR(30), biz_type NVARCHAR(50), biz_item NVARCHAR(100),
  post_no NVARCHAR(6), address1 NVARCHAR(100), address2 NVARCHAR(100),
  tel NVARCHAR(50), fax NVARCHAR(20), print_name NVARCHAR(50),
  trade_start NVARCHAR(8), trade_end NVARCHAR(8), use_flag BIT DEFAULT 1,
  dept_name NVARCHAR(30), charge_name NVARCHAR(30), charge_rank NVARCHAR(20),
  charge_tel NVARCHAR(20), charge_hp NVARCHAR(20), charge_email NVARCHAR(40), homepage NVARCHAR(50),
  credit_limit DECIMAL(18,0), collateral_amt DECIMAL(18,0),
  -- PNC 확장
  cust_type NVARCHAR(2), in_flag BIT, out_flag BIT, outside_flag BIT, bank_flag BIT,
  business_tag NVARCHAR(1), charge_user_id NVARCHAR(20), corp_no NVARCHAR(13),
  recv_post_no NVARCHAR(6), recv_address NVARCHAR(100), recv_address_dtl NVARCHAR(100),
  sagub_out_flag BIT, set_in_flag BIT, heat_label_flag BIT, prod_check_flag BIT,
  dlvy_day INT, dlvy_day2 INT, ue_date NVARCHAR(2), ue_week NVARCHAR(2), ue_day NVARCHAR(2),
  gc_gubun NVARCHAR(10), bank_code NVARCHAR(10), bank_bookno NVARCHAR(20), bank_person_name NVARCHAR(30),
  cms_no NVARCHAR(20), remarks NVARCHAR(255), upd_user NVARCHAR(40), upd_dt DATETIME DEFAULT GETDATE()
)"""

# 스키마 확인: cust_name 컬럼 없으면(구 1:1 복제본) 재생성
c.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='cust' AND COLUMN_NAME='cust_name'")
has_new = c.fetchone()[0] > 0
if not has_new:
    c.execute("IF OBJECT_ID('nx.cust') IS NOT NULL DROP TABLE nx.cust")
    c.execute(DDL); cn.commit(); print("nx.cust 위하고정합 스키마 재생성")

def b(col): return f"CASE WHEN LTRIM(RTRIM(CAST({col} AS NVARCHAR(5))))='1' THEN 1 ELSE 0 END"
INS = f"""INSERT INTO nx.cust
 (cust_code,cust_name,biz_no,resident_no,owner_name,biz_type,biz_item,post_no,address1,address2,
  tel,fax,print_name,use_flag,charge_name,charge_rank,charge_tel,charge_hp,charge_email,homepage,
  cust_type,in_flag,out_flag,outside_flag,bank_flag,business_tag,charge_user_id,corp_no,
  recv_post_no,recv_address,recv_address_dtl,sagub_out_flag,set_in_flag,heat_label_flag,prod_check_flag,
  dlvy_day,dlvy_day2,ue_date,ue_week,ue_day,gc_gubun,bank_code,bank_bookno,bank_person_name,cms_no,
  remarks,upd_user)
 SELECT LTRIM(RTRIM(s.CUST_CODE)), LTRIM(RTRIM(s.CUST_DESC)), LTRIM(RTRIM(s.BUSINESS_NO)), LTRIM(RTRIM(s.SSN)),
   LTRIM(RTRIM(s.OWNER_NAME)), LTRIM(RTRIM(s.BUSI_TYPE)), LTRIM(RTRIM(s.BUSI_KIND)), LTRIM(RTRIM(s.POST_NO)),
   LTRIM(RTRIM(s.ADDRESS)), LTRIM(RTRIM(s.ADDRESS_DTL)), LTRIM(RTRIM(s.PHONE_NO)), LTRIM(RTRIM(s.FAX_NO)),
   LTRIM(RTRIM(s.REG_CUST_DESC)), {b('s.USE_FLAG')}, LTRIM(RTRIM(s.CHARGE_NAME)), LTRIM(RTRIM(s.CHARGE_CHIEF_DESC)),
   LTRIM(RTRIM(s.CHARGE_PHONE_NO)), LTRIM(RTRIM(s.CHARGE_CELPHONE_NO)), LTRIM(RTRIM(s.CHARGE_EMAIL)), LTRIM(RTRIM(s.HOMEPAGE)),
   LTRIM(RTRIM(s.CUST_TYPE)), {b('s.IN_FLAG')}, {b('s.OUT_FLAG')}, {b('s.OUTSIDE_FLAG')}, {b('s.BANK_FLAG')},
   LTRIM(RTRIM(s.BUSINESS_TAG)), LTRIM(RTRIM(s.CHARGE_USER_ID)), LTRIM(RTRIM(s.CORP_NO)),
   LTRIM(RTRIM(s.RECV_POST_NO)), LTRIM(RTRIM(s.RECV_ADDRESS)), LTRIM(RTRIM(s.RECV_ADDRESS_DTL)),
   {b('s.SAGUB_OUT_FLAG')}, {b('s.SET_IN_FLAG')}, {b('s.HEAT_LABEL_FLAG')}, {b('s.PROD_CHECK_FLAG')},
   ISNULL(s.DLVY_DAY,0), ISNULL(s.DLVY_DAY2,0), LTRIM(RTRIM(s.UE_DATE)), LTRIM(RTRIM(s.UE_WEEK)), LTRIM(RTRIM(s.UE_DAY)),
   LTRIM(RTRIM(s.GC_GUBUN)), LTRIM(RTRIM(s.BANK_CODE)), LTRIM(RTRIM(s.BANK_BOOKNO)), LTRIM(RTRIM(s.BANK_PERSON_NAME)),
   LTRIM(RTRIM(s.CMS_NO)), LTRIM(RTRIM(s.REMARKS)), 'MIGRATION'
 FROM PARTNER_ERP.dbo.CM_M_CUST s
 WHERE LTRIM(RTRIM(s.CUST_CODE)) NOT IN (SELECT cust_code FROM nx.cust)"""

c.execute("SELECT COUNT(*) FROM nx.cust"); before = c.fetchone()[0]
c.execute(INS); ins = c.rowcount; cn.commit()
c.execute("SELECT COUNT(*) FROM nx.cust"); after = c.fetchone()[0]
c.execute("SELECT COUNT(DISTINCT LTRIM(RTRIM(CUST_CODE))) FROM PARTNER_ERP.dbo.CM_M_CUST"); leg = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='cust'"); ncols = c.fetchone()[0]
print(f"삽입 {ins} → nx.cust {before}→{after} · {ncols}컬럼(위하고코어+PNC확장)")
print(f"검증 코드수: 레거시 {leg} vs nx {after}  {'OK' if leg==after else '★불일치'}")
# 샘플 확인
c.execute("SELECT TOP 3 cust_code,cust_name,biz_no,owner_name,cust_type,in_flag,out_flag,use_flag FROM nx.cust ORDER BY cust_code")
for r in c.fetchall(): print("  ", [str(x) for x in r])
