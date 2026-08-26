# -*- coding: utf-8 -*-
"""원가 100%(nx.item 마스터 stale): nx.item의 원가관련 필드를 live PR_M_ITEM와 동기화.
엔진은 nx.item(cg·metal·치수·make_type)으로 재료비·전개 판정. SP는 live 사용 → 낡으면 갭.
동기화 필드: cost_gubun·metal_gubun·make_type·diam·thick·length (객관적 마스터, SP정합).
백업 nx.item_costfld_bak. --commit 없으면 규모만. ※nature/prod_group 등 재설계 필드는 미변경."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY=('--commit' not in sys.argv)
n=pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c=n.cursor()
J="""nx.item i JOIN PARTNER_ERP.dbo.PR_M_ITEM p ON p.ITEM_CODE COLLATE DATABASE_DEFAULT=i.item_code COLLATE DATABASE_DEFAULT"""
where=("""ISNULL(LTRIM(RTRIM(i.cost_gubun)),'')<>ISNULL(LTRIM(RTRIM(p.COST_GUBUN)),'')
 OR ISNULL(LTRIM(RTRIM(i.metal_gubun)),'')<>ISNULL(LTRIM(RTRIM(p.METAL_GUBUN)),'')
 OR ISNULL(LTRIM(RTRIM(i.make_type)),'')<>ISNULL(LTRIM(RTRIM(p.MAKE_TYPE)),'')
 OR ABS(ISNULL(i.diam,0)-ISNULL(p.ITEM_DIAM,0))>0.001
 OR ABS(ISNULL(i.thick,0)-ISNULL(p.ITEM_THICK,0))>0.001
 OR ABS(ISNULL(i.length,0)-ISNULL(p.ITEM_LENGTH,0))>0.001""")
mis=c.execute(f"SELECT COUNT(*) FROM {J} WHERE {where}").fetchone()[0]
# ★신규 항목 = 라이브 PR_M_ITEM엔 있는데 nx.item엔 없는 것(신규품목 자동유입). 코어필드+재설계 기본값.
new_cnt=c.execute("SELECT COUNT(*) FROM PARTNER_ERP.dbo.PR_M_ITEM p WHERE NOT EXISTS(SELECT 1 FROM nx.item i WHERE i.item_code COLLATE DATABASE_DEFAULT=p.ITEM_CODE COLLATE DATABASE_DEFAULT)").fetchone()[0]
print(f"nx.item 원가필드 불일치: {mis}건 / 신규유입(nx.item 없음): {new_cnt}건")
if DRY: print("DRY (--commit 실행)"); n.close(); sys.exit()
if new_cnt:
    c.execute("""INSERT INTO nx.item(item_code,item_name,item_spec,metal_gubun,diam,thick,length,net_weight,unit,
        make_type,in_cust,cost_gubun,lgroup,sgroup,status,item_status,item_type)
      SELECT LTRIM(RTRIM(p.ITEM_CODE)), p.ITEM_DESC, p.ITEM_SPEC, LTRIM(RTRIM(p.METAL_GUBUN)), p.ITEM_DIAM, p.ITEM_THICK,
        p.ITEM_LENGTH, p.ITEM_WEIGHT, ISNULL(NULLIF(LTRIM(RTRIM(p.UNIT)),''),'EA'), LTRIM(RTRIM(p.MAKE_TYPE)),
        LTRIM(RTRIM(p.IN_CUST_CODE)), LTRIM(RTRIM(p.COST_GUBUN)), LTRIM(RTRIM(p.ITEM_LGROUP)), LTRIM(RTRIM(p.ITEM_SGROUP)),
        CASE WHEN LTRIM(RTRIM(ISNULL(p.ITEM_STATUS,'')))='2' THEN '휴면' ELSE '사용' END, LTRIM(RTRIM(p.ITEM_STATUS)), '부품'
      FROM PARTNER_ERP.dbo.PR_M_ITEM p
      WHERE NOT EXISTS(SELECT 1 FROM nx.item i WHERE i.item_code COLLATE DATABASE_DEFAULT=p.ITEM_CODE COLLATE DATABASE_DEFAULT)""")
    print(f"신규 {new_cnt}건 INSERT 완료(코어필드·재설계필드는 CRUD/후속에서 보강).")
c.execute("IF OBJECT_ID('nx.item_costfld_bak','U') IS NOT NULL DROP TABLE nx.item_costfld_bak")
c.execute("SELECT item_code, cost_gubun, metal_gubun, make_type, diam, thick, length INTO nx.item_costfld_bak FROM nx.item")
print("백업 nx.item_costfld_bak:", c.execute("SELECT COUNT(*) FROM nx.item_costfld_bak").fetchone()[0])
c.execute(f"""UPDATE i SET
   cost_gubun=LTRIM(RTRIM(p.COST_GUBUN)), metal_gubun=LTRIM(RTRIM(p.METAL_GUBUN)), make_type=LTRIM(RTRIM(p.MAKE_TYPE)),
   diam=p.ITEM_DIAM, thick=p.ITEM_THICK, length=p.ITEM_LENGTH
   FROM {J} WHERE {where}""")
print("동기화 완료. 되돌리기: nx.item_costfld_bak")

# ── 갭 컬럼(리더가 미러에서 읽던 것) 동기화 — 미러 은퇴 관문. 멱등 ALTER + 항상 최신 backfill.
#    (미러 UPPER→클린 lower 동명·case-insensitive. ITEM_WEIGHT는 의미상이 보류.)
GAP = [("sagub_stock_flag","varchar(1)","SAGUB_STOCK_FLAG"),("std_won_mat_flag","varchar(1)","STD_WON_MAT_FLAG"),
       ("jig_code","varchar(20)","JIG_CODE"),("jig_keep_area","varchar(20)","JIG_KEEP_AREA"),
       ("safe_stock_min","smallint","SAFE_STOCK_MIN"),("safe_stock_max","smallint","SAFE_STOCK_MAX"),
       ("weld_point_in","tinyint","WELD_POINT_IN"),("weld_point_out","tinyint","WELD_POINT_OUT"),
       ("tariff_rate","numeric(18,2)","TARIFF_RATE"),("remarks","varchar(100)","REMARKS"),("item_cost","numeric(18,4)","ITEM_COST"),
       ("item_weight","numeric(18,4)","ITEM_WEIGHT")]  # 레거시 단중(엔진용)·net_weight와 별개축·미러값 복사(diff0)
for cl, ddl, _mir in GAP:
    if c.execute("SELECT COL_LENGTH('nx.item',?)", cl).fetchone()[0] is None:
        c.execute(f"ALTER TABLE nx.item ADD {cl} {ddl} NULL"); print(f"  갭컬럼 ADD {cl}")
c.execute(f"UPDATE i SET {', '.join(f'i.{cl}=p.{mir}' for cl,_d,mir in GAP)} FROM {J}")
print("갭 컬럼 동기화 완료(리더 이관 지원).")

# ── 리더 컬럼(엔진/화면이 읽는 객관 마스터필드) 동기화 — 이관 diff0 관문.
#    ★item_name은 제외(SUB 접미사 [-xxx] 보존 — 접미사 스텝이 별도 관리). 나머지는 live 추종.
c.execute(f"""UPDATE i SET
   i.in_cust=LTRIM(RTRIM(p.IN_CUST_CODE)), i.item_spec=p.ITEM_SPEC, i.work_code=LTRIM(RTRIM(p.WORK_CODE)),
   i.sgroup=LTRIM(RTRIM(p.ITEM_SGROUP)), i.lgroup=LTRIM(RTRIM(p.ITEM_LGROUP)),
   i.item_status=LTRIM(RTRIM(p.ITEM_STATUS)), i.prod_rate=p.PROD_RATE,
   i.unit=ISNULL(LTRIM(RTRIM(p.UNIT)),'')
   FROM {J}""")
print("리더 컬럼 동기화 완료(item_name=접미사 보존 위해 제외).")
n.close()
