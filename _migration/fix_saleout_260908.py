# -*- coding: utf-8 -*-
"""판매출고 재고 미차감분 보정 — 원장에만 있고 잔액·미러이력에 없는 건 반영

  ★경위 (2026-09-08)
    판매및출고등록(w_pu_output_010 → /api/saleout/save)이 **원장(stock_ledger tag='5')에만** 쓰고
    잔액(PU_T_MAT_STOCK_WH)·미러이력(PU_T_STOCK_MAINT)을 안 써서 화면 재고가 안 깎였다.
    코드는 고쳤다(sales.py:_saleout_led_post 에 _so_upd_wh + _so_mirror 추가).
    이 스크립트는 **고치기 전에 잡힌 건**만 보정한다.

  ★안전장치
    · 기본 DRY-RUN. 실제 반영은 --commit
    · 대상 = 원장 tag='5' 중 **같은 일자·자재의 미러이력 tag='5' 가 없는 것**만
    · 이미 반영된 건은 건드리지 않는다(이중차감 방지)
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
SC, PW = 'Z99990', 'IS0001'
cn = _nx(); cur = cn.cursor()

print("=" * 96)
print(" 판매출고 재고 미차감 보정   모드: {}".format("★COMMIT" if COMMIT else "DRY-RUN"))
print("=" * 96)

cur.execute("""
SELECT g.MAINT_YMD, RTRIM(g.MAT_CODE) mat, SUM(g.MAINT_QTY) led,
       MAX(RTRIM(ISNULL(g.CUST_CODE,''))) cust,
       ISNULL((SELECT SUM(h.MAINT_QTY) FROM nx.PU_T_STOCK_MAINT h WITH(NOLOCK)
                WHERE h.MAINT_YMD=g.MAINT_YMD AND h.MAINT_TAG='5'
                  AND RTRIM(h.MAT_CODE)=RTRIM(g.MAT_CODE)),0) mir
  FROM nx.stock_ledger g WITH(NOLOCK)
 WHERE g.STOCK_POINT='MAT' AND g.MAINT_TAG='5' AND g.MAINT_YMD>='260901'
 GROUP BY g.MAINT_YMD, RTRIM(g.MAT_CODE)
 ORDER BY g.MAINT_YMD, RTRIM(g.MAT_CODE)""")
rows = [tuple(x) for x in cur.fetchall()]
print("\n   9월 판매출고 원장 {}조합".format(len(rows)))
print("   {:<9s} {:<24s} {:>10s} {:>10s}  {}".format("일자", "자재", "원장", "미러", "판정"))
tgt = []
for x in rows:
    ymd, mat, led, cust, mir = str(x[0]).strip(), str(x[1]).strip(), float(x[2] or 0), str(x[3]).strip(), float(x[4] or 0)
    # 원장이 음수(출고)인데 미러가 0 = 미반영
    v = "★미반영" if (led < -0.001 and abs(mir) < 0.001) else "반영됨"
    if led < -0.001 and abs(mir) < 0.001:
        tgt.append((ymd, mat, led, cust))
    print("   {:<9s} {:<24s} {:>10,.0f} {:>10,.0f}  {}".format(ymd, mat, led, mir, v))

if not tgt:
    print("\n   ✅ 보정할 것 없음"); cur.close(); cn.close(); sys.exit(0)

print("\n[보정 대상 {}건]".format(len(tgt)))
for ymd, mat, q, cust in tgt:
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", mat, SC, PW)
    bal = float(cur.fetchone()[0] or 0)
    print("   {} {:<24s} {:>9,.0f}  잔액 {:>10,.0f} → {:>10,.0f}".format(ymd, mat, q, bal, bal + q))

if not COMMIT:
    print("\n   ① 잔액 −수량  ② 미러이력 tag='5' INSERT")
    print("   ⟹ 실제 반영하려면 --commit")
    cur.close(); cn.close(); sys.exit(0)

print("\n" + "=" * 96); print(" 실행"); print("=" * 96)
try:
    for ymd, mat, q, cust in tgt:
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                          UPDATE_USER_ID='fix260908', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='w_pu_output_010'
                        WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                    q, mat, SC, PW)
        print("   ① 잔액 {:<24s} {:+,.0f} ({}행)".format(mat, q, cur.rowcount))
        cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT
                        WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""", ymd)
        sq = int(cur.fetchone()[0] or 20000)
        cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                 WH_CUST_CODE,GAGONG_PROC_CODE,
                 INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                 UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                VALUES(?,?,'5',?,?,?, N'유상사급 매출출고', ?,?,
                       'fix260908',GETDATE(),'w_pu_output_010','fix260908',GETDATE(),'w_pu_output_010')""",
            ymd, sq, (cust or None), mat, q, SC, PW)
        print("   ② 미러이력 seq={} {:+,.0f}".format(sq, q))
    cn.commit(); print("\n   ✅ commit")
except Exception as e:
    cn.rollback(); print("\n   ★오류 rollback: {}".format(str(e)[:200]))
    cur.close(); cn.close(); sys.exit(1)

print("\n" + "=" * 96); print(" 보정 후"); print("=" * 96)
for ymd, mat, q, cust in tgt:
    cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WITH(NOLOCK) WHERE STOCK_POINT='MAT' AND RTRIM(MAT_CODE)=?", mat)
    a = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK) WHERE RTRIM(MAT_CODE)=?", mat)
    b = float(cur.fetchone()[0] or 0)
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", mat, SC, PW)
    c = float(cur.fetchone()[0] or 0)
    print("   {:<24s} 원장 {:>10,.0f} · 미러이력 {:>10,.0f} · 잔액 {:>10,.0f}".format(mat, a, b, c))
cur.close(); cn.close()
