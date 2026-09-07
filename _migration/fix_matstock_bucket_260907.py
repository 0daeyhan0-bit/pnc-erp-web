# -*- coding: utf-8 -*-
"""자재창고 잔량 버킷 교정 — 매입처코드로 쌓인 재고를 Z99990 으로 (2026-09-07)

  왜 — 자재입고를 100개 잡았는데 「자재 입출고현황」에 재고가 안 보였다(실사용 오류).
       원인 = stock.py 저장이 화면에서 온 CUST_CODE(=매입처 2023)를 **재고 버킷 키**로 써서,
              자재창고(Z99990) 가 아니라 매입처 버킷에 쌓였다.
       레거시(w_pu_stock_057·156)는 재고처리에 항상 'Z99990' 고정을 쓴다:
          f_pu_set_mat_stock_wh(..., ls_mat_code, 'Z99990', ls_gagong_proc_code, ld_qty,'')
       CUST_CODE 는 **원장 기록용 거래처**이지 창고가 아니다.
       실측: 라이브 PU_T_MAT_STOCK_WH 는 Z99990 단일(7,771행) — 거래처 버킷이 아예 없다.

  ★코드는 이미 고쳤다(stock.py: 화면·경로와 무관하게 _cc='Z99990').
    이 스크립트는 그 전에 잘못 쌓인 기존 행을 정리한다.

  하는 일
    CUST_CODE 가 Z99990 도 빈값도 아닌 행을 찾아, 같은 (MAT_CODE, GAGONG_PROC_CODE) 의
    Z99990 버킷으로 수량을 합치고 원래 행은 지운다. 총 수량은 보존된다.

  실행
    python _migration/fix_matstock_bucket_260907.py            # DRY-RUN
    python _migration/fix_matstock_bucket_260907.py --commit   # 실제 반영
"""
import sys, os, io

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client                      # noqa: E402

COMMIT = "--commit" in sys.argv

cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  자재창고 버킷 교정 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print("=" * 78)

cur.execute("""SELECT RTRIM(MAT_CODE), RTRIM(ISNULL(CUST_CODE,'')), RTRIM(ISNULL(GAGONG_PROC_CODE,'')),
                      CAST(STOCK_QTY AS float)
                 FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                WHERE ISNULL(CUST_CODE,'') NOT IN ('Z99990','')
                ORDER BY RTRIM(MAT_CODE)""")
rows = [(str(a).strip(), str(b).strip(), str(c).strip(), float(d or 0)) for a, b, c, d in cur.fetchall()]

if not rows:
    print("\n교정할 행이 없습니다(전부 Z99990).")
    sys.exit(0)

print(f"\n■ 잘못된 버킷 {len(rows)}행 · 합계 {sum(r[3] for r in rows):,.0f}\n")
print(f"  {'자도번':<22}{'현재 CUST':<10}{'공정':<9}{'수량':>10}   → Z99990 합산 후")
for mat, cc, gp, q in rows:
    cur.execute("""SELECT ISNULL(SUM(CAST(STOCK_QTY AS float)),0) FROM nx.PU_T_MAT_STOCK_WH
                    WHERE MAT_CODE=? AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                mat, gp)
    cur_z = float(cur.fetchone()[0] or 0)
    print(f"  {mat[:21]:<22}{cc:<10}{gp:<9}{q:>10,.0f}   {cur_z:,.0f} → {cur_z + q:,.0f}")

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 {len(rows)}행이 맞으면")
    print("   python _migration/fix_matstock_bucket_260907.py --commit  으로 반영하세요.")
    print("   ※총 수량은 보존됩니다(옮기는 것뿐, 늘거나 줄지 않습니다).")
    sys.exit(0)

# 백업
BK = "bk_matstockwh_260907_bucket"
cur.execute(f"IF OBJECT_ID('nx.{BK}') IS NOT NULL DROP TABLE nx.{BK}")
cur.execute(f"""SELECT * INTO nx.{BK} FROM nx.PU_T_MAT_STOCK_WH
                 WHERE ISNULL(CUST_CODE,'') NOT IN ('Z99990','')""")
cn.commit()
print(f"\n✅ 백업 nx.{BK}")

moved = 0
try:
    for mat, cc, gp, q in rows:
        # Z99990 버킷에 합산(없으면 생성)
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                          UPDATE_USER_ID='fixbucket', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='fix_bucket_260907'
                        WHERE MAT_CODE=? AND CUST_CODE='Z99990' AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                    q, mat, gp)
        if cur.rowcount == 0:
            cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES(?,'Z99990',?,?,'fixbucket',GETDATE(),'fix_bucket_260907')""",
                        mat, gp, q)
        # 잘못된 버킷 제거
        cur.execute("""DELETE FROM nx.PU_T_MAT_STOCK_WH
                        WHERE MAT_CODE=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                    mat, cc, gp)
        moved += 1
    cn.commit()
    print(f"✅ 반영 완료 — {moved}행을 Z99990 으로 이동")

    cur.execute("""SELECT COUNT(*) FROM nx.PU_T_MAT_STOCK_WH
                    WHERE ISNULL(CUST_CODE,'') NOT IN ('Z99990','')""")
    print(f"   남은 잘못된 버킷: {int(cur.fetchone()[0])}행 (0이어야 정상)")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:250])
    raise
finally:
    cn.close()
