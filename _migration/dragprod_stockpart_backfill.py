# -*- coding: utf-8 -*-
"""드래그 실적 → PR_T_PROD_DTL.STOCK_PART_CODE 백필 (2026-09-07)

  왜 — 「생산입출고현황」(live_api._prodinout:943)은 생산실적 입고를
       **STOCK_PART_CODE 로만** 집계한다:

         SELECT a.STOCK_PART_CODE ... FROM pr_t_prod_dtl a
          WHERE ... AND a.STOCK_PART_CODE > ''

       드래그 실적(dragprod.py)은 이 컬럼을 안 채워서, 잔액테이블에 재고가
       멀쩡히 있어도 **화면이 그 행을 통째로 건너뛰어 "결과 없음"** 이 됐다.
       (실사용 오류 2026-09-07: AJR32883902-은납 S6 10개가 화면에 0)
       코드는 고쳤지만(dragprod.py ⓪+①) 그 전에 잡힌 실적은 여전히 빈값 → 이 스크립트로 채운다.

  ★넣는 값 = **입고처 파트**(_prod_dest 판정), 실적 파트가 **아니다**.
    재고가 실제로 간 곳을 넣어야 잔액테이블과 축이 맞는다.
    실적파트(S10)를 넣으면 재고는 S6 에 있는데 화면은 S10 에 유령재고를 만든다.
      · 판정 PART → 그 파트코드
      · 판정 MAT/ASSY → **비워 둔다**(생산창고가 아니다). 각각 PU_T_STOCK_MAINT·
        SA_T_ITEM_STOCK 로 잡히므로 여기 채우면 이중계상된다.

  ★안전장치 — 판정한 파트에 **실제 잔량이 있는 건만** 채운다.
    잔량이 없는데 채우면 화면에만 재고가 생겨 잔액과 어긋난다.

  실행
    python _migration/dragprod_stockpart_backfill.py            # DRY-RUN(대상만)
    python _migration/dragprod_stockpart_backfill.py --commit   # 실제 반영
"""
import sys, os, io

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client                      # noqa: E402
from routers.prodsheet import _prod_dest      # noqa: E402

COMMIT = "--commit" in sys.argv
WIN = "w_pr_input_410_drag"

cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  드래그 실적 → STOCK_PART_CODE 백필 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print("=" * 78)

# 대상 = 드래그 실적 중 STOCK_PART_CODE 가 비어 있는 것
cur.execute("""
    SELECT PROD_YMD, RTRIM(ISNULL(PART_CODE,'')) pt, RTRIM(ITEM_CODE) it,
           SUM(PROD_QTY) q, COUNT(*) n
      FROM nx.PR_T_PROD_DTL WITH(NOLOCK)
     WHERE ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(STOCK_PART_CODE,'')=''
     GROUP BY PROD_YMD, RTRIM(ISNULL(PART_CODE,'')), RTRIM(ITEM_CODE)
     ORDER BY PROD_YMD, RTRIM(ITEM_CODE)""", WIN)
rows = cur.fetchall()

if not rows:
    print("\n채울 대상이 없습니다.")
    sys.exit(0)

todo, skip = [], []
for r in rows:
    ymd, pt, it, q, n = str(r[0]), str(r[1]), str(r[2]), float(r[3] or 0), int(r[4])
    # 입고처 판정 — dragprod.py 와 같은 기준(BOM 상위 → _prod_dest)
    cur.execute("""SELECT TOP 1 ITEM_CODE FROM nx.pr_m_item_bom WITH(NOLOCK)
                    WHERE MAT_CODE=? AND ISNULL(EXCEPT_FLAG,'0')<>'1'""", it)
    _r = cur.fetchone()
    upper = str(_r[0] or "").strip() if _r else ""
    dk, dp = _prod_dest(cur, it, upper)
    if dk != "PART" or not dp:
        skip.append((ymd, pt, it, q, n, f"입고처가 {dk} — 생산창고 아님(비워둠이 정상)"))
        continue
    # 안전장치: 판정한 파트에 실제 잔량이 있어야 채운다
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PR_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE MAT_CODE=? AND PART_CODE=?""", it, dp)
    bal = float(cur.fetchone()[0] or 0)
    if bal <= 0:
        skip.append((ymd, pt, it, q, n, f"{dp} 잔량 0 — 채우면 화면에만 재고가 생긴다"))
        continue
    todo.append((ymd, pt, it, q, n, dp, bal))

print(f"\n■ 채울 대상 {len(todo)}그룹 · {sum(x[4] for x in todo)}행 · 수량 {sum(x[3] for x in todo):,.0f}\n")
print(f"  {'일자':<8}{'실적파트':<9}{'도번':<26}{'수량':>6}{'행':>4}  {'→STOCK_PART':<12}{'잔량':>9}")
for ymd, pt, it, q, n, dp, bal in todo:
    print(f"  {ymd:<8}{pt:<9}{it[:25]:<26}{q:>6,.0f}{n:>4}  {dp:<12}{bal:>9,.2f}")

if skip:
    print(f"\n■ 건너뜀 {len(skip)}그룹 (채우지 않는 것이 정상)\n")
    print(f"  {'일자':<8}{'실적파트':<9}{'도번':<26}{'수량':>6}{'행':>4}  사유")
    for ymd, pt, it, q, n, why in skip:
        print(f"  {ymd:<8}{pt:<9}{it[:25]:<26}{q:>6,.0f}{n:>4}  {why}")

if not todo:
    print("\n채울 대상이 없습니다.")
    sys.exit(0)

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 {len(todo)}그룹이 맞는지 확인한 뒤")
    print("   python _migration/dragprod_stockpart_backfill.py --commit  으로 반영하세요.")
    sys.exit(0)

n_upd = 0
try:
    for ymd, pt, it, q, n, dp, bal in todo:
        cur.execute("""UPDATE nx.PR_T_PROD_DTL SET STOCK_PART_CODE=?,
                          UPDATE_USER_ID='backfill', UPDATE_DATETIME=GETDATE()
                        WHERE ISNULL(UPDATE_WINDOW,'')=? AND ISNULL(STOCK_PART_CODE,'')=''
                          AND PROD_YMD=? AND ISNULL(PART_CODE,'')=? AND ITEM_CODE=?""",
                    dp, WIN, ymd, pt, it)
        n_upd += cur.rowcount
    cn.commit()
    print(f"\n✅ 반영 완료 — {n_upd}행 갱신")

    # 확인 — 화면이 쓰는 집계식 그대로
    print("\n■ 화면('SUB생산실적' 집계) 확인")
    cur.execute("""SELECT a.STOCK_PART_CODE, UPPER(a.ITEM_CODE), SUM(a.PROD_QTY)
                     FROM nx.PR_T_PROD_DTL a WITH(NOLOCK)
                    WHERE ISNULL(a.UPDATE_WINDOW,'')=? AND a.STOCK_PART_CODE>''
                    GROUP BY a.STOCK_PART_CODE, UPPER(a.ITEM_CODE)
                    ORDER BY a.STOCK_PART_CODE, UPPER(a.ITEM_CODE)""", WIN)
    for x in cur.fetchall():
        print(f"    PART={str(x[0]).strip():<6} {str(x[1]).strip()[:25]:<26}{float(x[2]):>7,.0f}개")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:200])
    raise
finally:
    cn.close()
