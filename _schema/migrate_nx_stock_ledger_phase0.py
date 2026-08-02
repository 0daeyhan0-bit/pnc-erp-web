"""
NX 재고이동 엔진 Phase0 DDL (블루프린트 B1) — 멱등 마이그레이션.
★nx(PARTNER_ERP_TEST3)에만 적용. 라이브 PARTNER_ERP 절대 무변경.
재실행 안전(IF NOT EXISTS / 컬럼·행 존재체크). 가법적·회귀안전.
실행: python migrate_nx_stock_ledger_phase0.py
"""
import sys
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc

cs = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(cs, autocommit=True); cur = cn.cursor()
log = []

# (1) STOCK_POINT 컬럼 + 백필 'MAT'
cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='stock_ledger' AND COLUMN_NAME='STOCK_POINT'")
if cur.fetchone()[0] == 0:
    cur.execute("ALTER TABLE nx.stock_ledger ADD STOCK_POINT varchar(4) NULL")
    log.append("ADD COLUMN nx.stock_ledger.STOCK_POINT")
else:
    log.append("skip: STOCK_POINT 이미 존재")
cur.execute("UPDATE nx.stock_ledger SET STOCK_POINT='MAT' WHERE STOCK_POINT IS NULL")
log.append(f"backfill STOCK_POINT='MAT' rows={cur.rowcount}")

# (2) 잔량파생 인덱스
cur.execute("SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID('nx.stock_ledger') AND name='IX_stock_ledger_bal'")
if cur.fetchone()[0] == 0:
    cur.execute("""CREATE INDEX IX_stock_ledger_bal ON nx.stock_ledger(STOCK_POINT, ITEM_CODE, MAT_CODE)
                   INCLUDE(MAINT_QTY, GAGONG_PROC_CODE, WORK_ORDER)""")
    log.append("CREATE INDEX IX_stock_ledger_bal")
else:
    log.append("skip: IX_stock_ledger_bal 이미 존재")

# (3) 신규 태그 (존재확인 후 INSERT — 기존 5/9/C 재사용, 중복금지)
newtags = [('K1','키팅','키팅확인(준비등록)','+'), ('K2','키팅','키팅취소','-'),
           ('P4','생산','생산소비(백플러시)','-'), ('P7','생산','생산입고(백플러시)','+'),
           ('G1','사급','무상사급 이동출고','-'), ('G2','사급','무상사급 이동복귀','+'),
           ('MV','이동','창고간 이동','+-')]
added = []
for tag, cat, name, sign in newtags:
    cur.execute("SELECT COUNT(*) FROM nx.stock_tag WHERE tag=?", tag)
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO nx.stock_tag(tag,category,name,sign) VALUES(?,?,?,?)", tag, cat, name, sign)
        added.append(tag)
log.append(f"stock_tag INSERT: {added or '없음(전부 기존)'}")

# (4) nx.sagub_free_vendor + 초기 2행
cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='sagub_free_vendor'")
if cur.fetchone()[0] == 0:
    cur.execute("""CREATE TABLE nx.sagub_free_vendor(
        cust_code varchar(10) NOT NULL PRIMARY KEY, apply_from_ymd varchar(6) NULL,
        remarks nvarchar(100) NULL, active bit NOT NULL DEFAULT 1,
        ins_datetime datetime NOT NULL DEFAULT getdate())""")
    log.append("CREATE TABLE nx.sagub_free_vendor")
else:
    log.append("skip: nx.sagub_free_vendor 이미 존재")
for cc, ay, rm in [('2014','260226','문영산업 무상'), ('2350', None, '경성정밀 무상 적용일 담당확인')]:
    cur.execute("SELECT COUNT(*) FROM nx.sagub_free_vendor WHERE cust_code=?", cc)
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO nx.sagub_free_vendor(cust_code,apply_from_ymd,remarks,active) VALUES(?,?,?,1)", cc, ay, rm)
        log.append(f"free_vendor INSERT {cc}")

# 검증 출력
cur.execute("SELECT COUNT(*), SUM(CASE WHEN STOCK_POINT='MAT' THEN 1 ELSE 0 END), SUM(CASE WHEN STOCK_POINT IS NULL THEN 1 ELSE 0 END) FROM nx.stock_ledger")
r = cur.fetchone()
log.append(f"검증 stock_ledger: 총{r[0]} · MAT={r[1]} · NULL={r[2]}")
cur.execute("SELECT tag FROM nx.stock_tag ORDER BY tag")
log.append("stock_tag 전체: " + ",".join(x[0] for x in cur.fetchall()))
cur.execute("SELECT cust_code, apply_from_ymd, remarks FROM nx.sagub_free_vendor ORDER BY cust_code")
log.append("free_vendor: " + str([(x[0], x[1], x[2]) for x in cur.fetchall()]))
cn.close()
print("\n".join("  " + l for l in log))
print("PHASE0_DONE")
