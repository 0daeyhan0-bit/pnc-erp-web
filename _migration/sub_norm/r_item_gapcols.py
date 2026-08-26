# -*- coding: utf-8 -*-
"""미러 은퇴 관문: nx.item에 갭 컬럼 11개 추가 + live PR_M_ITEM에서 backfill.
리더가 미러에서 읽던 컬럼(nx.item 부재)을 클린 마스터에 실어 이관 가능케 함.
컬럼(미러 UPPER → 클린 lower, 동명·case-insensitive): sagub_stock_flag·std_won_mat_flag·
jig_code·jig_keep_area·safe_stock_min/max·weld_point_in/out·tariff_rate·remarks·item_cost.
※ITEM_WEIGHT는 의미 상이(net_weight≠) → 보류. 멱등(COL_LENGTH 체크). --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()

# (클린컬럼, DDL타입, 미러컬럼)
COLS = [
    ("sagub_stock_flag", "varchar(1)",   "SAGUB_STOCK_FLAG"),
    ("std_won_mat_flag", "varchar(1)",   "STD_WON_MAT_FLAG"),
    ("jig_code",         "varchar(20)",  "JIG_CODE"),
    ("jig_keep_area",    "varchar(20)",  "JIG_KEEP_AREA"),
    ("safe_stock_min",   "smallint",     "SAFE_STOCK_MIN"),
    ("safe_stock_max",   "smallint",     "SAFE_STOCK_MAX"),
    ("weld_point_in",    "tinyint",      "WELD_POINT_IN"),
    ("weld_point_out",   "tinyint",      "WELD_POINT_OUT"),
    ("tariff_rate",      "numeric(18,2)","TARIFF_RATE"),
    ("remarks",          "varchar(100)", "REMARKS"),
    ("item_cost",        "numeric(18,4)","ITEM_COST"),
    # ITEM_WEIGHT = 레거시 단중(엔진이 이 값으로 원가/전개 판정). net_weight(f_get_weight3 우리실측)와 별개축.
    # 미러값 그대로 복사(대문자 ITEM_WEIGHT 읽기가 case-insensitive로 해석) → 원가 diff0 보존. net_weight 미접촉.
    ("item_weight",      "numeric(18,4)","ITEM_WEIGHT"),
]

# 1) 부재 컬럼만 ADD(멱등)
add = []
for cl, ddl, mir in COLS:
    exists = c.execute("SELECT COL_LENGTH('nx.item',?)", cl).fetchone()[0] is not None
    if not exists: add.append((cl, ddl, mir))
print(f"추가 대상: {len(add)}/{len(COLS)}  ({', '.join(x[0] for x in add) or '없음(모두 존재)'})")
if DRY:
    print("DRY — --commit 로 ALTER+backfill 실행"); n.close(); sys.exit()
for cl, ddl, mir in add:
    c.execute(f"ALTER TABLE nx.item ADD {cl} {ddl} NULL")
    print(f"  ADD {cl} {ddl}")

# 2) live dbo.PR_M_ITEM 에서 backfill (전 컬럼 — stale 방지 위해 항상 최신값으로)
J = "nx.item i JOIN PARTNER_ERP.dbo.PR_M_ITEM p ON p.ITEM_CODE COLLATE DATABASE_DEFAULT=i.item_code COLLATE DATABASE_DEFAULT"
setcl = ", ".join(f"i.{cl}=p.{mir}" for cl, _d, mir in COLS)
c.execute(f"UPDATE i SET {setcl} FROM {J}")
print("backfill 완료(live PR_M_ITEM).")
# 검증 표본
row = c.execute("""SELECT
   SUM(CASE WHEN sagub_stock_flag IS NOT NULL THEN 1 ELSE 0 END),
   SUM(CASE WHEN ISNULL(item_cost,0)>0 THEN 1 ELSE 0 END),
   SUM(CASE WHEN ISNULL(jig_keep_area,'')<>'' THEN 1 ELSE 0 END),
   COUNT(*) FROM nx.item""").fetchone()
print(f"채움 표본: sagub_flag非NULL {row[0]} / item_cost>0 {row[1]} / jig_keep_area있음 {row[2]} / 전체 {row[3]}")
n.close()
