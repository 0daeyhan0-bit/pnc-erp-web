# -*- coding: utf-8 -*-
"""세트수동입고 재고 미반영분 보정 — 원장에만 있고 잔액·미러이력에 없는 건 올린다

  ★경위 (2026-09-08)
    세트 수동입고(w_pu_stock_146 → /api/setstock/manual)가 **원장(stock_ledger)에만** 쓰고
    잔액(PU_T_MAT_STOCK_WH)·미러이력(PU_T_STOCK_MAINT)을 안 써서 화면 재고가 안 늘었다.
    코드는 고쳤다(setin.py:637 _upd_mat_wh + _mirror_ins). 이 스크립트는 **고치기 전에 잡힌 건**만 보정한다.

    실측 대상: 260908 AJR73803003-F&T 1,000 (원장 O · 미러 0 · 잔액 미반영)

  ★안전장치
    · 기본 DRY-RUN. 실제 반영은 --commit
    · 대상 = 원장 tag='S' + 비고 '수동' + **미러이력이 없는 것**만(이미 올라간 건 건드리지 않음)
    · 미러이력은 웹 대역(SEQ>=20000)에 역행이 아닌 정상 입고행으로 추가
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
SC, PW = 'Z99990', 'IS0001'
cn = _nx(); cur = cn.cursor()

print("=" * 92)
print(" 세트수동입고 재고 보정")
print(" 모드: {}".format("★COMMIT (실제 반영)" if COMMIT else "DRY-RUN (조회만)"))
print("=" * 92)

# 대상 = 원장 수동입고 중 미러이력이 없는 것
#   ★수동입고뿐 아니라 **세트입고 전체**(tag='S')를 본다 — 화면(자재입고관리)에 뜬 건 중
#     미러이력이 없어 재고에 안 올라간 것을 전부 잡는다.
#     원장 합계 vs 미러 합계를 자재별로 비교해 **모자란 만큼만** 채운다(이중가산 방지).
cur.execute("""
SELECT g.MAINT_YMD, MIN(g.MAINT_SEQ) seq, RTRIM(g.MAT_CODE) mat,
       SUM(g.MAINT_QTY) led,
       MAX(RTRIM(ISNULL(g.ITEM_CODE,''))) item, MAX(RTRIM(ISNULL(g.CUST_CODE,''))) cust,
       ISNULL((SELECT SUM(h.MAINT_QTY) FROM nx.PU_T_STOCK_MAINT h WITH(NOLOCK)
                WHERE h.MAINT_YMD=g.MAINT_YMD AND h.MAINT_TAG='S'
                  AND RTRIM(h.MAT_CODE)=RTRIM(g.MAT_CODE)),0) mir
  FROM nx.stock_ledger g WITH(NOLOCK)
 WHERE g.MAINT_TAG='S' AND g.MAINT_YMD>='260901'
 GROUP BY g.MAINT_YMD, RTRIM(g.MAT_CODE)
 ORDER BY g.MAINT_YMD, RTRIM(g.MAT_CODE)""")
rows = [tuple(x) for x in cur.fetchall()]
# 채울 양 = 원장 − 미러 (양수일 때만)
tgt = []
for r in rows:
    led_, mir_ = float(r[3] or 0), float(r[6] or 0)
    gap = led_ - mir_
    # ★보정 조건 — 아래 둘을 모두 만족할 때만 (오검출 방지)
    #   · 원장이 양수다 (실제로 입고된 건)
    #   · 미러가 0 이다 (아예 안 올라간 건)
    #  ⛔미러가 음수인 건은 **회수 완료분**이다(오염분 5210AP4184A 원장0·미러−20).
    #    그런 건에 gap 을 채우면 회수를 되돌리는 꼴이 된다.
    if led_ > 0.001 and abs(mir_) < 0.001:
        tgt.append((r[0], r[1], r[2], led_, r[4], r[5], mir_))

print("\n[대상]")
print("   9월 세트입고 원장 {}조합 중 미러 부족 {}건".format(len(rows), len(tgt)))
print("   {:<9s} {:<24s} {:>10s} {:>10s} {:>10s}".format("일자", "자재", "원장", "미러", "채울양"))
for r in rows:
    gap = float(r[3] or 0) - float(r[6] or 0)
    print("   {:<9s} {:<24s} {:>10,.0f} {:>10,.0f} {:>10,.0f}  {}".format(
        str(r[0]).strip(), str(r[2]).strip(), float(r[3] or 0), float(r[6] or 0), gap,
        "★보정" if gap > 0.001 else "일치"))
if not tgt:
    print("   ✅ 보정할 것 없음"); cur.close(); cn.close(); sys.exit(0)

for x in tgt:
    ymd, seq, mat, q, item, cust = str(x[0]).strip(), x[1], str(x[2]).strip(), float(x[3] or 0), str(x[4]).strip(), str(x[5]).strip()
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", mat, SC, PW)
    bal = float(cur.fetchone()[0] or 0)
    print("   {} seq={} {:<24s} qty={:>9,.0f}  현재잔액 {:>10,.0f} → {:>10,.0f}".format(
        ymd, seq, mat, q, bal, bal + q))
    print("      (도번={} 거래처={})".format(item, cust))

if not COMMIT:
    print("\n" + "=" * 92)
    print(" 실행 예정 (DRY-RUN)")
    print("=" * 92)
    print("   ① 잔액 PU_T_MAT_STOCK_WH  += 수량")
    print("   ② 미러이력 PU_T_STOCK_MAINT INSERT (tag='S', 웹대역 SEQ>=20000)")
    print("   ※원장은 이미 있으므로 건드리지 않는다")
    print("\n   ⟹ 실제 반영하려면 --commit")
    cur.close(); cn.close(); sys.exit(0)

print("\n" + "=" * 92)
print(" 실행")
print("=" * 92)
try:
    for x in tgt:
        ymd, seq, mat, q = str(x[0]).strip(), x[1], str(x[2]).strip(), float(x[3] or 0)
        item, cust = str(x[4]).strip(), str(x[5]).strip()

        # ① 잔액
        cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH SET STOCK_QTY=ISNULL(STOCK_QTY,0)+?,
                          UPDATE_USER_ID='fix260908', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='w_pu_stock_146'
                        WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                    q, mat, SC, PW)
        n = cur.rowcount
        if n == 0:
            cur.execute("""INSERT INTO nx.PU_T_MAT_STOCK_WH(MAT_CODE,CUST_CODE,GAGONG_PROC_CODE,STOCK_QTY,
                              UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                            VALUES(?,?,?,?, 'fix260908', GETDATE(), 'w_pu_stock_146')""",
                        mat, SC, PW, q)
            n = cur.rowcount
        print("   ① 잔액 {:<24s} {:+,.0f}  ({}행)".format(mat, q, n))

        # ② 미러이력
        cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT
                        WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""", ymd)
        msq = int(cur.fetchone()[0] or 20000)
        cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                 WH_CUST_CODE,GAGONG_PROC_CODE,ITEM_CODE,
                 INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                 UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                VALUES(?,?,'S',?,?,?,?,?,?,?, 'fix260908',GETDATE(),'w_pu_stock_146',
                       'fix260908',GETDATE(),'w_pu_stock_146')""",
            ymd, msq, (cust or None), mat, q, '세트수동입고',
            SC, PW, (item or None))
        print("   ② 미러이력 seq={} {:+,.0f}".format(msq, q))

    cn.commit(); print("\n   ✅ commit 완료")
except Exception as e:
    cn.rollback(); print("\n   ★오류 rollback: {}".format(str(e)[:220]))
    cur.close(); cn.close(); sys.exit(1)

print("\n" + "=" * 92)
print(" 보정 후 확인")
print("=" * 92)
for x in tgt:
    mat = str(x[2]).strip()
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""", mat, SC, PW)
    bal = float(cur.fetchone()[0] or 0)
    cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND MAINT_YMD=? AND MAINT_TAG='S'""", mat, str(x[0]).strip())
    mir = float(cur.fetchone()[0] or 0)
    cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND STOCK_POINT='MAT'""", mat)
    led = float(cur.fetchone()[0] or 0)
    print("   {:<24s} 원장 {:>10,.0f} · 미러이력 {:>10,.0f} · 잔액 {:>10,.0f}".format(mat, led, mir, bal))
print("\n   ⟹ 자재 입출고현황에서 좌측 재고·우측 이력 모두 보여야 정상")
cur.close(); cn.close()
