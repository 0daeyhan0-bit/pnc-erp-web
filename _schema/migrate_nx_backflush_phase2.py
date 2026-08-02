"""
NX 재고엔진 Phase2 — 백플러시 멱등성 로그 테이블(nx.backflush_log).
★nx(PARTNER_ERP_TEST3)에만. 라이브 무변경. 재실행 안전.
(WORK_ORDER, ITEM_CODE, PROD_YMD, SEQ) 단위 1회 posting 보증 · reverse 추적.
"""
import sys
sys.path.insert(0, r"D:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import db_client, pyodbc
cs = (f"DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};"
      f"DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}")
cn = pyodbc.connect(cs, autocommit=True); cur = cn.cursor()
log = []
cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='backflush_log'")
if cur.fetchone()[0] == 0:
    cur.execute("""CREATE TABLE nx.backflush_log(
        bf_id bigint IDENTITY PRIMARY KEY,
        prod_ymd varchar(6) NOT NULL, work_order varchar(20) NULL, item_code varchar(20) NOT NULL,
        gpc varchar(10) NULL, prod_qty decimal(18,3) NOT NULL, ref_key varchar(60) NULL,
        state varchar(10) NOT NULL DEFAULT 'posted',   -- posted / reversed
        maint_ymd varchar(6) NULL, seq_from int NULL, seq_to int NULL,
        ins_user varchar(20) NULL, ins_datetime datetime NOT NULL DEFAULT getdate())""")
    cur.execute("CREATE INDEX IX_backflush_key ON nx.backflush_log(work_order, item_code, prod_ymd, state)")
    log.append("CREATE TABLE nx.backflush_log + IX_backflush_key")
else:
    log.append("skip: nx.backflush_log 이미 존재")
cur.execute("SELECT COUNT(*) FROM nx.backflush_log")
log.append(f"backflush_log 행수={cur.fetchone()[0]}")
cn.close()
print("\n".join("  " + l for l in log)); print("PHASE2_MIG_DONE")
