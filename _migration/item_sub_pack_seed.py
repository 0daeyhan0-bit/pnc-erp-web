# -*- coding: utf-8 -*-
"""미러 nx.PR_M_ITEM_SUB → 클린 nx.item_sub 적재 (포장종류·포장수량·용접자·검사자 4종).

왜
--
생산정보등록(w_pr_master_090)에서 이 4종을 편집하기로 확정(2026-09-08 대표).
저장·조회 소스를 **클린 nx.item_sub 단일**로 통일했는데(CLAUDE.md §1-9-1),
클린에는 값이 일부만 있어 그대로 전환하면 기존 값이 화면·라벨에서 빈칸이 된다.
  실측: 용접자 2,109 · 검사자 2,110 · 포장종류 3,031 · 포장수량 3,811 품목이 미러에만 있음.
        그중 **라벨 발행 이력이 있는 품목 202건** → 이관 없이 전환하면 라벨 이름이 사라진다.

원칙
----
★덮어쓰지 않는다. **클린이 비어 있을 때만** 채운다(컬럼 단위).
  클린에 이미 값이 있으면 그게 최신이다(웹에서 누군가 고친 값).
  양쪽 다 값이 있고 서로 다른 53건은 **손대지 않는다** — 실측으로 확인한 수치이며,
  덮어쓰면 웹에서 고친 최신값이 옛 미러값으로 되돌아간다.
★쓰기 대상은 nx(PARTNER_ERP_TEST3) 뿐. 라이브 PARTNER_ERP 는 읽지도 쓰지도 않는다(§1-1).

사용법
------
  python item_sub_pack_seed.py            # 조회만(dry-run) — 무엇을 바꿀지 출력, 쓰기 없음
  python item_sub_pack_seed.py --apply    # 실제 적재
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', '..', 'New_ERP'))
from db_client import get_connection

APPLY = "--apply" in sys.argv
M = "PARTNER_ERP_TEST3.nx.PR_M_ITEM_SUB"
C = "PARTNER_ERP_TEST3.nx.item_sub"

# (미러컬럼, 클린컬럼, 표시명, 빈값판정)
COLS = [("PACK_KIND",   "pack_kind",   "포장종류", "str"),
        ("PACK_QTY",    "pack_qty",    "포장수량", "num"),
        ("PROD_WORKER", "prod_worker", "용접자",   "str"),
        ("INSP_WORKER", "insp_worker", "검사자",   "str")]


def main():
    cn = get_connection(); cur = cn.cursor()
    print("=" * 66)
    print("미러 → 클린 적재 (포장·작업자 4종)   모드 =", "★APPLY(실제 쓰기)" if APPLY else "DRY-RUN(조회만)")
    print("=" * 66)

    # ── 1) 클린에 행이 없는 품목 → INSERT
    cur.execute(f"""SELECT M.ITEM_CODE, ISNULL(M.PACK_KIND,''), ISNULL(M.PACK_QTY,0),
                           ISNULL(M.PROD_WORKER,''), ISNULL(M.INSP_WORKER,'')
                      FROM {M} M WITH(NOLOCK)
                     WHERE NOT EXISTS(SELECT 1 FROM {C} C WITH(NOLOCK) WHERE C.item_code=M.ITEM_CODE)
                       AND (RTRIM(ISNULL(M.PACK_KIND,''))<>'' OR ISNULL(M.PACK_QTY,0)<>0
                            OR RTRIM(ISNULL(M.PROD_WORKER,''))<>'' OR RTRIM(ISNULL(M.INSP_WORKER,''))<>'')""")
    ins = cur.fetchall()
    print(f"\n[1] 클린에 행 없음 → INSERT 대상 : {len(ins):,}건")
    for r in ins[:5]:
        print(f"      {str(r[0]).strip():20} 포장[{str(r[1]).strip()}] {int(r[2] or 0):>4} "
              f"용접[{str(r[3]).strip()}] 검사[{str(r[4]).strip()}]")
    if len(ins) > 5:
        print(f"      … 외 {len(ins)-5:,}건")

    # ── 2) 행은 있고 해당 컬럼만 비어 있는 경우 → 컬럼별 UPDATE
    print("\n[2] 행은 있으나 컬럼이 빈 경우 → 컬럼별 UPDATE 대상")
    upd_plan = []
    for cm, cc, nm, kind in COLS:
        empty_c = f"RTRIM(ISNULL(C.{cc},''))=''" if kind == "str" else f"ISNULL(C.{cc},0)=0"
        has_m = f"RTRIM(ISNULL(M.{cm},''))<>''" if kind == "str" else f"ISNULL(M.{cm},0)<>0"
        cur.execute(f"""SELECT COUNT(*) FROM {M} M WITH(NOLOCK)
                        JOIN {C} C WITH(NOLOCK) ON C.item_code=M.ITEM_CODE
                        WHERE {has_m} AND {empty_c}""")
        n = cur.fetchone()[0]
        upd_plan.append((cm, cc, nm, kind, empty_c, has_m, n))
        print(f"      {nm:6} : {n:,}건")

    # ── 3) 충돌(양쪽 다 값 있고 다름) — 건드리지 않음을 명시
    cur.execute(f"""SELECT COUNT(*) FROM {M} M WITH(NOLOCK)
                    JOIN {C} C WITH(NOLOCK) ON C.item_code=M.ITEM_CODE
                    WHERE (RTRIM(ISNULL(M.PROD_WORKER,''))<>'' AND RTRIM(ISNULL(C.prod_worker,''))<>''
                           AND RTRIM(M.PROD_WORKER)<>RTRIM(C.prod_worker))
                       OR (RTRIM(ISNULL(M.INSP_WORKER,''))<>'' AND RTRIM(ISNULL(C.insp_worker,''))<>''
                           AND RTRIM(M.INSP_WORKER)<>RTRIM(C.insp_worker))""")
    print(f"\n[3] 양쪽 값이 다른 품목 : {cur.fetchone()[0]:,}건 → ★건드리지 않음(클린이 최신)")

    if not APPLY:
        print("\n" + "=" * 66)
        print("DRY-RUN 이라 아무것도 쓰지 않았습니다. 실제 적재는 --apply 를 붙이세요.")
        print("=" * 66)
        cn.close(); return

    # ── 실제 적재 ──
    print("\n적재 시작…")
    n_ins = 0
    for r in ins:
        cur.execute(f"""INSERT INTO {C}(item_code,pack_kind,pack_qty,prod_worker,insp_worker)
                        VALUES(?,?,?,?,?)""",
                    str(r[0]).strip(), str(r[1]).strip()[:50], int(r[2] or 0),
                    str(r[3]).strip()[:50], str(r[4]).strip()[:50])
        n_ins += 1
    print(f"  INSERT {n_ins:,}건")

    tot_upd = 0
    for cm, cc, nm, kind, empty_c, has_m, n in upd_plan:
        if not n:
            continue
        cur.execute(f"""UPDATE C SET C.{cc} = M.{cm}
                          FROM {C} C JOIN {M} M WITH(NOLOCK) ON M.ITEM_CODE=C.item_code
                         WHERE {has_m} AND {empty_c}""")
        print(f"  UPDATE {nm:6} {cur.rowcount:,}건")
        tot_upd += cur.rowcount
    cn.commit()
    print(f"\n완료 — INSERT {n_ins:,} · UPDATE {tot_upd:,}")

    # ── 검증 ──
    print("\n=== 검증: 라벨 발행 이력 품목 중 클린에 용접자 없는 건 ===")
    cur.execute(f"""SELECT COUNT(DISTINCT s.ITEM_CODE)
                    FROM PARTNER_ERP_TEST3.nx.PR_T_PRINT_STICKER s WITH(NOLOCK)
                    JOIN {M} M WITH(NOLOCK) ON M.ITEM_CODE=s.ITEM_CODE
                    LEFT JOIN {C} C WITH(NOLOCK) ON C.item_code=s.ITEM_CODE
                    WHERE RTRIM(ISNULL(M.PROD_WORKER,''))<>''
                      AND RTRIM(ISNULL(C.prod_worker,''))=''""")
    left = cur.fetchone()[0]
    print(f"  {left}건", "  ✅ 0 이면 라벨 이름 유실 없음" if left == 0 else "  ★남아있음 — 확인 필요")
    cn.close()


if __name__ == "__main__":
    main()
