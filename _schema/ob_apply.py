# -*- coding: utf-8 -*-
"""③ 오프닝밸런스 적재 — nx.stock_ledger 에 조정행 INSERT.

  목표잔액 = MAX(레거시 잔량, 0)          (대표 지시 2026-09-06: 음수는 0)
  조정수량 = 목표잔액 − 원장 파생잔액

  · 백업 = nx.bk_stock_ledger_260906_ob (선행 완료)
  · 식별 = INSERT_USER_ID='GOLIVE' + MAINT_TAG='OB'  → 이 두 값으로 전건 원복 가능
  · MAINT_SEQ 는 (MAINT_YMD 내) 기존 최대값 다음부터 부여
  · 트랜잭션 1건. 실패 시 전량 롤백.

  실행: python ob_apply.py            → 드라이런(건수만)
        python ob_apply.py --commit   → 실제 적재
"""
import sys, csv, os
sys.path.insert(0, r"c:\Users\박근민\Desktop\New_ERP")
import db_client

OUT = r"C:\Users\박근민\AppData\Local\Temp\claude\c--Users-----Desktop-NEW-ERP-1--schema\0d811a39-bd77-4b27-83f9-16f3733d6289\scratchpad"
YMD = "260906"
TAG = "OB"
USER = "GOLIVE"
REM = "GOLIVE 기초확정 260906 (레거시 정합, 음수0)"
COMMIT = "--commit" in sys.argv

# point -> (키1이 담길 컬럼, 키2가 담길 컬럼, CUST_CODE 고정값)
COLMAP = {
    "MAT": ("MAT_CODE",  "GAGONG_PROC_CODE", "Z99990"),
    "PRD": ("MAT_CODE",  "GAGONG_PROC_CODE", ""),
    "ASY": ("ITEM_CODE", "",                 ""),
    "RDY": ("ITEM_CODE", "GAGONG_PROC_CODE", "Z99990"),
    "SAG": ("MAT_CODE",  "CUST_CODE",        ""),
}

cn = db_client.get_connection(); cur = cn.cursor()

# 안전장치 ①: 백업 존재 확인
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='bk_stock_ledger_260906_ob'""")
if not cur.fetchone()[0]:
    sys.exit("중단: 백업 nx.bk_stock_ledger_260906_ob 이 없습니다.")

# 안전장치 ②: 이미 적재했는지
cur.execute("""SELECT COUNT(*) FROM nx.stock_ledger WITH(NOLOCK)
               WHERE MAINT_TAG=? AND LTRIM(RTRIM(INSERT_USER_ID))=?""", TAG, USER)
already = cur.fetchone()[0]
if already:
    sys.exit(f"중단: 이미 오프닝밸런스 {already:,}행이 있습니다. 원복 후 재실행하세요.")

# MAINT_SEQ 시작값
cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0) FROM nx.stock_ledger WITH(NOLOCK) WHERE MAINT_YMD=?", YMD)
seq = int(cur.fetchone()[0])
print(f"MAINT_SEQ 시작 = {seq+1}")

batch = []
for pt in ["MAT", "PRD", "ASY", "RDY", "SAG"]:
    c1, c2, cust = COLMAP[pt]
    rows = list(csv.DictReader(open(os.path.join(OUT, f"ob3_{pt}.csv"), encoding="utf-8-sig")))
    ks = list(rows[0].keys()) if rows else []
    n = 0
    for r in rows:
        k1, k2 = r[ks[0]].strip(), r[ks[1]].strip()
        adj = float(r["adjust_qty"])
        if abs(adj) < 0.0001:
            continue
        if not k1:                       # 품목코드 없는 행은 넣지 않는다(추적 불가)
            continue
        seq += 1
        cols = {"MAINT_YMD": YMD, "MAINT_SEQ": seq, "MAINT_TAG": TAG, "STOCK_POINT": pt,
                "MAINT_QTY": adj, "REMARKS": REM, "INSERT_USER_ID": USER,
                "CUST_CODE": cust}
        cols[c1] = k1
        if c2 and k2:
            cols[c2] = k2
        batch.append(cols)
        n += 1
    print(f"  {pt:<5} {n:>6,}행")

print(f"\n총 {len(batch):,}행  ·  조정합 {sum(b['MAINT_QTY'] for b in batch):,.1f}")

if not COMMIT:
    print("\n[드라이런] --commit 을 붙이면 실제 적재합니다.")
    sys.exit(0)

# 실제 적재 — 트랜잭션 1건
allcols = ["MAINT_YMD","MAINT_SEQ","MAINT_TAG","STOCK_POINT","MAINT_QTY","REMARKS",
           "INSERT_USER_ID","CUST_CODE","MAT_CODE","ITEM_CODE","GAGONG_PROC_CODE"]
sql = (f"INSERT INTO nx.stock_ledger ({','.join(allcols)}, INSERT_DATETIME) "
       f"VALUES ({','.join('?' * len(allcols))}, GETDATE())")
try:
    cur.fast_executemany = True
    cur.executemany(sql, [tuple(b.get(c, "") if c not in ("MAINT_SEQ","MAINT_QTY") else b.get(c, 0)
                                for c in allcols) for b in batch])
    cn.commit()
    print(f"\n적재 완료: {len(batch):,}행")
except Exception as e:
    cn.rollback()
    print(f"\n실패 → 전량 롤백: {e}")
    raise
