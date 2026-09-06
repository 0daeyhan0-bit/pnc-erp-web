# -*- coding: utf-8 -*-
"""① 백업 — nx.stock_ledger 전체 스냅샷. 오프닝밸런스 적재 전 필수 (CLAUDE.md §1-3)."""
import sys
sys.path.insert(0, r"c:\Users\박근민\Desktop\New_ERP")
import db_client

BK = "bk_stock_ledger_260906_ob"
cn = db_client.get_connection(); cur = cn.cursor()

cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='nx' AND TABLE_NAME=?""", BK)
if cur.fetchone()[0]:
    print(f"이미 존재: nx.{BK} — 중복 생성 안 함")
else:
    cur.execute(f"SELECT * INTO PARTNER_ERP_TEST3.nx.{BK} FROM PARTNER_ERP_TEST3.nx.stock_ledger")
    cn.commit()
    print(f"백업 생성: nx.{BK}")

cur.execute(f"SELECT COUNT(*), ISNULL(SUM(MAINT_QTY),0) FROM PARTNER_ERP_TEST3.nx.{BK}")
b = cur.fetchone()
cur.execute("SELECT COUNT(*), ISNULL(SUM(MAINT_QTY),0) FROM PARTNER_ERP_TEST3.nx.stock_ledger")
o = cur.fetchone()
print(f"  원본 {o[0]:,}행 / {float(o[1]):,.1f}")
print(f"  백업 {b[0]:,}행 / {float(b[1]):,.1f}")
print("  검증:", "OK 일치" if (b[0] == o[0] and abs(float(b[1]) - float(o[1])) < 0.001) else "!! 불일치")
