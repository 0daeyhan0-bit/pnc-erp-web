# -*- coding: utf-8 -*-
"""S5 보조: 기존 SUB의 is_shared/ref_count backfill(공용 배지 표시용).
   ref_count = 이 sub_code의 raw들을 직속자식으로 갖는 distinct 부모(제품) 수. is_shared = ref_count>1.
   ★신규 컬럼만 채움 = 라이브 무영향(아무 기존 코드도 이 컬럼 안 읽음·dedup 무관·bom_line 무수정).
   기본 DRY. --commit 시 반영. 실행: python r_sub_shared_backfill.py [--commit]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
import db_client, pyodbc

def _nx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}', autocommit=False)

CALC = """SELECT m.sub_code, COUNT(DISTINCT h.item_code) AS n
          FROM nx.sub_code_map m
          JOIN nx.bom_line bl ON bl.child_item = m.raw_item
          JOIN nx.bom_header h ON h.bom_id = bl.bom_id
          GROUP BY m.sub_code"""

def main(commit):
    cn = _nx(); cur = cn.cursor()
    cur.execute(CALC)
    rows = [((r[0] or '').strip(), int(r[1] or 0)) for r in cur.fetchall()]
    shared = sum(1 for _, n in rows if n > 1)
    print(f"집계된 sub_code: {len(rows)} · 공용(부모>1): {shared}")
    if commit:
        cur.execute(f"""UPDATE r SET ref_count=x.n, is_shared=CASE WHEN x.n>1 THEN 1 ELSE 0 END
                        FROM nx.sub_registry r JOIN ({CALC}) x ON x.sub_code=r.sub_code""")
        # 집계 안 된 코드(참조 0)=ref_count 0·is_shared 0
        cur.execute("UPDATE nx.sub_registry SET ref_count=ISNULL(ref_count,0), is_shared=ISNULL(is_shared,0) WHERE is_shared IS NULL")
        cn.commit(); print("COMMITTED")
        cur.execute("SELECT COUNT(*) FROM nx.sub_registry WHERE is_shared=1"); print("is_shared=1:", cur.fetchone()[0])
    else:
        cn.rollback(); print("DRY(--commit 시 반영)")
    cn.close()

if __name__ == "__main__":
    main("--commit" in sys.argv)
