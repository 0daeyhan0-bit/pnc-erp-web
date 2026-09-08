# -*- coding: utf-8 -*-
"""bom_flat.raw_lg_kg 제거 — 백업 후 DROP COLUMN. 실사용 0 확인됨(코드/SQL/JS 참조 없음, 문서만). --commit 없으면 DRY."""
import sys, io
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\NEW_ERP_1\PNC_ERP_Web\backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
import common
DRY = ('--commit' not in sys.argv)
cn = common._nx(); cn.autocommit = True; c = cn.cursor()
# 컬럼 존재·값 현황
c.execute("SELECT COUNT(*), SUM(CASE WHEN ISNULL(raw_lg_kg,0)<>0 THEN 1 ELSE 0 END) FROM nx.bom_flat")
tot, nz = c.fetchone(); print("bom_flat 행 %d · raw_lg_kg 비영 %d"%(tot, nz))
if DRY:
    print("DRY — --commit 로 백업+드롭 실행"); cn.close(); sys.exit()
# 1) 백업 (멱등)
c.execute("""IF OBJECT_ID('nx.bom_flat_raw_lg_kg_bak_260908','U') IS NULL
             SELECT item_code, leaf_code, raw_lg_kg INTO nx.bom_flat_raw_lg_kg_bak_260908 FROM nx.bom_flat""")
c.execute("SELECT COUNT(*) FROM nx.bom_flat_raw_lg_kg_bak_260908"); print("백업 nx.bom_flat_raw_lg_kg_bak_260908 행:", c.fetchone()[0])
# 2) DROP COLUMN
c.execute("ALTER TABLE nx.bom_flat DROP COLUMN raw_lg_kg")
print("DROP COLUMN raw_lg_kg 완료")
# 3) 검증
c.execute("SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('nx.bom_flat') AND name='raw_lg_kg'")
print("raw_lg_kg 컬럼 잔존:", c.fetchone()[0], "(0=제거확인)")
c.execute("SELECT COUNT(*) FROM nx.bom_flat"); print("bom_flat 행수(불변확인):", c.fetchone()[0])
c.execute("SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID('nx.bom_flat')"); print("bom_flat 컬럼수:", c.fetchone()[0])
cn.close()
