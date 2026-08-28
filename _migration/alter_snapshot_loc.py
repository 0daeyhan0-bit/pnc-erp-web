# -*- coding: utf-8 -*-
"""nx.stock_snapshot 에 재고위치 축(loc) 추가 — 멱등.

왜 필요한가:
  · 자재(MAT)·완성(SAL) 은 품목 1축이지만 **생산(PRD) 은 2축**이다.
    레거시 w_pr_stock_480(생산재고조회) = (품목 × 라인) 그레인 —
    가공창고(P0001) 와 용접라인(그 외 line code) 이 별개 재고점.
  · 지금 PK(domain,ptype,period,item_code) 로는 같은 품목의 가공/용접이 충돌한다.
  · 따라서 loc 을 PK 에 넣는다. MAT/SAL 은 loc='' 로 기존과 동일.

사용: python _migration/alter_snapshot_loc.py [--commit]
"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

COMMIT = "--commit" in sys.argv
cn = _nx(); cur = cn.cursor()

cur.execute("SELECT OBJECT_ID('nx.stock_snapshot')")
if cur.fetchone()[0] is None:
    print("★ nx.stock_snapshot 이 없습니다. 먼저 create_period_close.py 를 실행하세요.")
    sys.exit(1)

cur.execute("""SELECT 1 FROM sys.columns
               WHERE object_id=OBJECT_ID('nx.stock_snapshot') AND name='loc'""")
has_loc = cur.fetchone() is not None

cur.execute("""SELECT COUNT(*) FROM sys.index_columns ic
               JOIN sys.indexes i ON i.object_id=ic.object_id AND i.index_id=ic.index_id
               JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
              WHERE i.object_id=OBJECT_ID('nx.stock_snapshot') AND i.is_primary_key=1 AND c.name='loc'""")
pk_has_loc = cur.fetchone()[0] > 0

print(f"  loc 컬럼      : {'있음' if has_loc else '없음'}")
print(f"  PK 에 loc 포함: {'예' if pk_has_loc else '아니오'}")

steps = []
if not has_loc:
    steps.append(("loc 컬럼 추가",
                  "ALTER TABLE nx.stock_snapshot ADD loc varchar(20) NOT NULL "
                  "CONSTRAINT DF_snap_loc DEFAULT('')"))
if not pk_has_loc:
    steps.append(("기존 PK 삭제", """
        DECLARE @pk sysname;
        SELECT @pk = name FROM sys.key_constraints
         WHERE parent_object_id=OBJECT_ID('nx.stock_snapshot') AND type='PK';
        IF @pk IS NOT NULL EXEC('ALTER TABLE nx.stock_snapshot DROP CONSTRAINT ' + @pk);"""))
    steps.append(("PK 재생성(loc 포함)",
                  "ALTER TABLE nx.stock_snapshot ADD CONSTRAINT PK_stock_snapshot "
                  "PRIMARY KEY (domain, ptype, period, item_code, loc)"))

if not steps:
    print("\n변경 없음(멱등).")
elif not COMMIT:
    print("\nDRY-RUN — 적용할 단계:")
    for nm, _ in steps:
        print(f"    · {nm}")
    print("  --commit 으로 적용")
else:
    for nm, sql in steps:
        cur.execute(sql)
        print(f"  ✓ {nm}")
    cn.commit()
    cur.execute("SELECT COUNT(*) FROM nx.stock_snapshot")
    print(f"\n적용 완료. 기존 스냅샷 {cur.fetchone()[0]:,}행 보존(loc='').")
cn.close()
