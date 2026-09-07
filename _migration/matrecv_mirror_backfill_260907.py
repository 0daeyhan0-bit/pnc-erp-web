# -*- coding: utf-8 -*-
"""발주입고 미러 누락 보정 — stock_ledger 에만 있는 tag9 입고를 PU_T_STOCK_MAINT 로 (2026-09-07)

  왜 — 자재입고를 잡았는데 「자재 입출고현황」에 안 나왔다(실사용 오류).
       원인 = /api/matrecv/receive(stock.py matrecv_receive)가 **원장(nx.stock_ledger)에만** 쓰고
              화면이 읽는 미러(nx.PU_T_STOCK_MAINT)와 잔액(nx.PU_T_MAT_STOCK_WH)에 안 썼다.
              같은 파일의 /api/stock/save 는 이미 셋 다 쓰고 있었다 — 이 경로만 빠져 있었다.

  ★코드는 고쳤다(matrecv_receive 에 잔액·미러 기록 추가).
    이 스크립트는 그 전에 원장에만 쌓인 기존 행을 미러·잔액에 반영한다.

  대상 = nx.stock_ledger  STOCK_POINT='MAT' AND MAINT_TAG='9' AND MAINT_QTY>0
         AND 같은 (MAINT_YMD, MAT_CODE, MAINT_QTY) 의 미러행이 없는 것
  ※미러에 이미 있는 행은 건드리지 않는다(이중계상 방지).

  실행
    python _migration/matrecv_mirror_backfill_260907.py            # DRY-RUN
    python _migration/matrecv_mirror_backfill_260907.py --commit   # 실제 반영
"""
import sys, os, io

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common                                   # noqa: E402

COMMIT = "--commit" in sys.argv
FROM = "260901"        # 보정 시작일(그 이전 과거분은 손대지 않는다)

cn = common._nx()
cur = cn.cursor()

print("=" * 78)
print(f"  발주입고 미러 보정 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print("=" * 78)

# 미러에 짝이 없는 원장 tag9 입고
cur.execute("""
    SELECT L.MAINT_YMD, L.MAINT_SEQ, RTRIM(ISNULL(L.CUST_CODE,'')), RTRIM(L.MAT_CODE),
           CAST(L.MAINT_QTY AS float), RTRIM(ISNULL(L.GAGONG_PROC_CODE,'IS0001')),
           RTRIM(ISNULL(L.REMARKS,''))
      FROM nx.stock_ledger L WITH(NOLOCK)
     WHERE L.STOCK_POINT='MAT' AND L.MAINT_TAG='9' AND L.MAINT_QTY>0
       AND L.MAINT_YMD>=?
       AND NOT EXISTS (SELECT 1 FROM nx.PU_T_STOCK_MAINT M WITH(NOLOCK)
                        WHERE M.MAINT_YMD=L.MAINT_YMD AND RTRIM(M.MAT_CODE)=RTRIM(L.MAT_CODE)
                          AND M.MAINT_QTY=L.MAINT_QTY)
     ORDER BY L.MAINT_YMD, L.MAINT_SEQ""", FROM)
rows = [(str(a).strip(), int(b), str(c).strip(), str(d).strip(), float(e or 0),
         (str(f).strip() or "IS0001"), str(g or "").strip()) for a, b, c, d, e, f, g in cur.fetchall()]

if not rows:
    print("\n보정할 행이 없습니다(미러에 모두 있음).")
    cn.close(); sys.exit(0)

print(f"\n■ 미러 누락 {len(rows)}행 · 합계 {sum(r[4] for r in rows):,.0f}\n")
print(f"  {'일자':<8}{'seq':>5}  {'거래처':<7}{'자도번':<16}{'수량':>9}  {'창고':<8}비고")
for ymd, seq, cc, mat, q, gp, rmk in rows:
    print(f"  {ymd:<8}{seq:>5}  {cc:<7}{mat[:15]:<16}{q:>9,.0f}  {gp:<8}{rmk[:20]}")

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 {len(rows)}행이 맞으면")
    print("   python _migration/matrecv_mirror_backfill_260907.py --commit  으로 반영하세요.")
    print("   ※원장은 손대지 않습니다. 미러(입출고 이력)와 잔액만 채웁니다.")
    cn.close(); sys.exit(0)

# 백업 — 반영 전 미러 스냅샷(대상 일자만)
BK = "bk_pustockmaint_260907_backfill"
cur.execute(f"IF OBJECT_ID('nx.{BK}') IS NOT NULL DROP TABLE nx.{BK}")
cur.execute(f"""SELECT * INTO nx.{BK} FROM nx.PU_T_STOCK_MAINT WHERE MAINT_YMD>=?""", FROM)
cn.commit()
print(f"\n✅ 백업 nx.{BK}")

done = 0
try:
    for ymd, seq, cc, mat, q, gp, rmk in rows:
        cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT
                        WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""", ymd)
        sq = int(cur.fetchone()[0] or 20000)
        cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
                (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
                 WH_CUST_CODE,GAGONG_PROC_CODE,
                 INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
                 UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
                VALUES(?,?,'9',?,?,?,?,'Z99990',?,'backfill',GETDATE(),'matrecv_bf',
                       'backfill',GETDATE(),'matrecv_bf')""",
                    ymd, sq, (cc or None), mat, q, (rmk or "발주입고"), gp)
        # ★잔액(PU_T_MAT_STOCK_WH)은 **건드리지 않는다**(2026-09-07 실측 확인).
        #   앞선 버킷 교정(fix_matstock_bucket_260907)으로 잔액은 이미 맞아 있다 —
        #   실측 5품목 전부 원장합 == 410 자재재고 잔액(565/8,034/63/383/1,694).
        #   여기서 또 더하면 **이중가산**이 된다. 미러(입출고 이력)만 채운다.
        done += 1
    cn.commit()
    print(f"✅ 반영 완료 — 미러 {done}행 기록 (잔액은 이미 정확해 손대지 않음)")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:250])
    raise
finally:
    cn.close()
