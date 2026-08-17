# -*- coding: utf-8 -*-
"""nx 복제본 성능 인덱스(콜드 첫조회 지연 해소). r_bulk_copy(SELECT INTO)는 힙만 만들어 조인/필터가 풀스캔.
 자재수불장 등 조회 프로그램 첫 조회 지연의 근본원인. 인덱스는 읽기전용 최적화(데이터 무변경).
 ★컷오버 데이터 재동기(SELECT INTO) 후 재실행 필요(인덱스 유실됨).
 --commit 없으면 계획만."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import pyodbc, db_client
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
DRY = ('--commit' not in sys.argv)
n = pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=True)
c = n.cursor()
# (테이블, 인덱스명, 키컬럼, 유니크여부, 포함컬럼)
IDX = [
  ('pr_m_item', 'ix_nx_prmitem_code', 'item_code', True, ''),
  ('cm_m_cust', 'ix_nx_cmcust_code', 'cust_code', True, ''),
  ('pr_m_proc_gagong', 'ix_nx_prgagong_code', 'gagong_proc_code', True, ''),
  ('pr_m_mat', 'ix_nx_prmat_code', 'mat_code', True, ''),
  ('PU_T_MONTH_STOCK_WH_DAILY', 'ix_nx_pustkday', 'cust_code,STOCK_YMD,mat_code', False, ''),
  ('PU_T_MONTH_STOCK_WH', 'ix_nx_pustkmon', 'cust_code,STOCK_YYMM,mat_code', False, ''),
]
def has_dup(tbl, col):
    return c.execute(f"SELECT COUNT(*) FROM (SELECT {col} FROM nx.{tbl} GROUP BY {col} HAVING COUNT(*)>1) q").fetchone()[0] > 0
for tbl, name, keys, uniq, incl in IDX:
    exists = c.execute("SELECT COUNT(*) FROM sys.indexes WHERE name=? AND object_id=OBJECT_ID('nx.'+?)", name, tbl).fetchone()[0]
    if exists:
        print(f"  {tbl}.{name}: 이미 존재(스킵)"); continue
    u = uniq
    if uniq and has_dup(tbl, keys.split(',')[0]):
        u = False; print(f"  ! {tbl}.{keys}: 중복존재 → 비유니크로 생성")
    ddl = f"CREATE {'UNIQUE ' if u else ''}NONCLUSTERED INDEX {name} ON nx.{tbl}({keys})" + (f" INCLUDE ({incl})" if incl else "")
    print(f"  {'[DRY] ' if DRY else ''}{ddl}")
    if not DRY:
        c.execute(ddl)
if not DRY:
    print("인덱스 생성 완료. (컷오버 데이터 재동기 후 재실행)")
n.close()
