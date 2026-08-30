# -*- coding: utf-8 -*-
"""S1: SUB 출생라벨 스키마(additive·멱등) — nx.sub_registry에 컬럼 추가.
   기존 행 NULL·기존 코드 무영향(읽는 코드가 새 컬럼 모름). forward-only 정본화 §2.
   실행: python r_sub_birthlabel_schema.py [--commit]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'New_ERP'))
import db_client, pyodbc

def _nx():
    return pyodbc.connect(f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}')

COLS = [
    ("birth_label", "NVARCHAR(60)"),   # {ASSY}_R{route}_S{nn} 출생라벨(표시명)
    ("birth_assy",  "NVARCHAR(40)"),   # 태어난 ASSY(route.item_code)
    ("birth_route", "INT"),            # 태어난 route_no
    ("birth_seq",   "INT"),            # (assy,route)별 영속 순번
    ("is_shared",   "BIT"),            # 공용(참조 ASSY>1) 플래그
    ("ref_count",   "INT"),            # 참조 제품 수
]

def main(commit):
    cn = _nx(); cur = cn.cursor()
    for name, typ in COLS:
        cur.execute("SELECT COL_LENGTH('nx.sub_registry', ?)", name)
        exists = cur.fetchone()[0] is not None
        if exists:
            print(f"  {name}: 이미 있음(skip)")
        else:
            print(f"  {name}: 추가 {typ}")
            if commit:
                cur.execute(f"ALTER TABLE nx.sub_registry ADD {name} {typ}")
    if commit:
        cn.commit(); print("COMMITTED")
    else:
        print("DRY(--commit 시 실제 추가)")
    # 확인
    cur.execute("""SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                   WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='sub_registry' ORDER BY ORDINAL_POSITION""")
    print("현재 컬럼:", [r[0] for r in cur.fetchall()])
    cn.close()

if __name__ == "__main__":
    main("--commit" in sys.argv)
