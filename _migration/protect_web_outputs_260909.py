# -*- coding: utf-8 -*-
"""★컷오버 직전 보호 — 레거시명 테이블에 든 '웹 산출물' 백업 + 가드 보강 (2026-09-09)

★왜 급한가 — 오늘 컷오버다. `r_bulk_copy.py` 는 대상 테이블을
   **DROP TABLE + SELECT * INTO** 로 통째 갈아엎는다(L77-79).
   행수가 같으면 건너뛰지만, 아래 둘은 **행수가 달라 반드시 갈아엎힌다**.

   | 테이블 | nx 초과분 | 정체 |
   |---|---|---|
   | PU_T_MONTH_STOCK_WH | 2608 3,692행 | **8월 월마감 산출물**(한대윤 2026-09-08 10:16) |
   | CS_M_PROC           | 21행         | 웹 등록 체결공정 FS01~FS21(assywork.py:38) |

   `r_bulk_copy.PROTECTED` 에는 소문자 클린 테이블(period_close·stock_snapshot…)만 있고
   **대문자 레거시명은 빠져 있다.** 그래서 마감 '상태'(period_close)는 확정으로 남고
   그 마감이 만든 '값'(PU_T_MONTH_STOCK_WH)만 사라지는 최악의 형태가 된다.
   L36-39 주석이 경고한 그 사고가 보호 목록에서 빠진 채 남아 있었다.

★이 스크립트가 하는 일
   ① 두 테이블의 **웹 초과분만** 별도 백업 테이블로 보존(전량 아님 — 필요분만)
   ② 복구 스크립트 동시 생성(백업 → 원표 재삽입)
   ③ r_bulk_copy.py 의 PROTECTED 에 두 이름 추가(그 파일은 수동 확인 후 반영)

★안전 — 원표는 건드리지 않는다(읽기 + 백업 생성만). --apply 없으면 조회만.

사용: python _migration\\protect_web_outputs_260909.py [--apply]
"""
import sys, os, io, re, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
MIG = r"c:\Users\박근민\Desktop\NEW_ERP_1\_migration"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
S = "PARTNER_ERP_TEST3.nx"
L = "PARTNER_ERP.dbo"

# (테이블, 초과분 판정 키)
CASES = [("PU_T_MONTH_STOCK_WH", ["STOCK_YYMM", "CUST_CODE", "GAGONG_PROC_CODE", "MAT_CODE"]),
         ("CS_M_PROC", ["PROC_CODE"])]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" ★컷오버 보호 — 레거시명 테이블 속 웹 산출물 백업")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

made = []
for t, keys in CASES:
    on = " AND ".join("RTRIM(ISNULL(CAST(n.[{c}] AS varchar(60)),''))="
                      "RTRIM(ISNULL(CAST(l.[{c}] AS varchar(60)),''))".format(c=c) for c in keys)
    cur.execute("""SELECT COUNT(*) FROM {S}.[{t}] n
                    WHERE NOT EXISTS(SELECT 1 FROM {L}.[{t}] l WHERE {on})""".format(S=S, L=L, t=t, on=on))
    n_only = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM {S}.[{t}]".format(S=S, t=t)); n_all = cur.fetchone()[0]
    bk = "bk_webout_{}_{}".format(t.lower(), STAMP)
    print("\n■ {:<24s} 전체 {:,}행 · ★웹 초과분 {:,}행".format(t, n_all, n_only))
    if not n_only:
        print("   초과분 없음 — 백업 불필요"); continue
    # 무엇인지 한 번 더 보여준다
    uid = "UPDATE_USER_ID"
    try:
        cur.execute("""SELECT TOP 3 ISNULL(n.[{u}],''), COUNT(*) FROM {S}.[{t}] n
                        WHERE NOT EXISTS(SELECT 1 FROM {L}.[{t}] l WHERE {on})
                        GROUP BY n.[{u}] ORDER BY COUNT(*) DESC""".format(u=uid, S=S, L=L, t=t, on=on))
        for r in cur.fetchall():
            print("     등록자 {:<12s} {:,}행".format(str(r[0]).strip() or "-", r[1]))
    except Exception:
        pass
    made.append((t, bk, keys, n_only))
    if not APPLY:
        print("     → 백업 예정: {}.{}".format(S, bk)); continue
    cur.execute("IF OBJECT_ID('nx.{b}','U') IS NOT NULL DROP TABLE nx.{b}".format(b=bk))
    cur.execute("""SELECT n.* INTO {S}.{b} FROM {S}.[{t}] n
                    WHERE NOT EXISTS(SELECT 1 FROM {L}.[{t}] l WHERE {on})""".format(
        S=S, b=bk, t=t, L=L, on=on))
    cur.execute("SELECT COUNT(*) FROM {S}.{b}".format(S=S, b=bk))
    got = cur.fetchone()[0]
    print("     ✔ 백업 {}.{}  {:,}행 {}".format(S, bk, got, "OK" if got == n_only else "★불일치"))
    if got != n_only:
        nx.rollback(); print("     ★행수 불일치 — 롤백"); nx.close(); sys.exit(1)

if not APPLY:
    nx.rollback()
    print("\n" + "=" * 100)
    print(" ※dry-run — 반영하려면 --apply")
    nx.close(); sys.exit(0)

nx.commit()

# ── 복구 스크립트 생성 ─────────────────────────────────────────
rp = os.path.join(MIG, "restore_web_outputs_{}.py".format(STAMP))
lines = ["# -*- coding: utf-8 -*-",
         '"""컷오버 후 복구 — r_bulk_copy 가 덮어쓴 뒤 웹 산출물을 되돌린다.',
         "",
         "   백업 시각 {} · protect_web_outputs_260909.py 가 생성.".format(STAMP),
         "   r_bulk_copy 실행 **직후** 돌린다(순서 중요 — 먼저 돌리면 다시 덮인다).",
         '"""',
         "import sys, os, io",
         r'BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"',
         "sys.path.insert(0, BE); os.chdir(BE)",
         'sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)',
         "from common import _nx",
         "",
         'APPLY = "--apply" in sys.argv',
         'S = "PARTNER_ERP_TEST3.nx"',
         "nx = _nx(); nx.autocommit = False",
         "cur = nx.cursor()",
         'print("컷오버 후 웹 산출물 복구 — 모드:", "★반영" if APPLY else "조회만")',
         "PAIRS = ["]
for t, bk, keys, n in made:
    lines.append('    ("{}", "{}", {}),   # {:,}행'.format(t, bk, keys, n))
lines += ["]",
          "for t, bk, keys in PAIRS:",
          '    cur.execute("SELECT COUNT(*) FROM {S}.[{b}]".format(S=S, b=bk))',
          "    nb = cur.fetchone()[0]",
          '    on = " AND ".join("RTRIM(ISNULL(CAST(t.[{c}] AS varchar(60)),\'\'))="',
          '                      "RTRIM(ISNULL(CAST(b.[{c}] AS varchar(60)),\'\'))".format(c=c) for c in keys)',
          '    cur.execute("""SELECT COUNT(*) FROM {S}.[{b}] b',
          '                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{t}] t WHERE {on})""".format(S=S, b=bk, t=t, on=on))',
          "    miss = cur.fetchone()[0]",
          '    print("  {:<26s} 백업 {:,}행 · 원표에 없는 것 {:,}행".format(t, nb, miss))',
          "    if not APPLY or not miss: continue",
          '    cur.execute("""INSERT INTO {S}.[{t}] SELECT b.* FROM {S}.[{b}] b',
          '                    WHERE NOT EXISTS(SELECT 1 FROM {S}.[{t}] t WHERE {on})""".format(S=S, b=bk, t=t, on=on))',
          '    print("     ✔ 복구 {:,}행".format(cur.rowcount))',
          "if APPLY:",
          "    nx.commit()",
          '    print("✅ 커밋")',
          "else:",
          "    nx.rollback()",
          "nx.close()"]
open(rp, "w", encoding="utf-8", newline="").write("\n".join(lines))
print("\n" + "=" * 100)
print(" ✅ 백업 완료 · 복구 스크립트 = {}".format(os.path.basename(rp)))
print("""
 ★남은 조치(수동)
   ① _migration/sub_norm/r_bulk_copy.py 의 PROTECTED 에 아래를 추가하거나,
      TABLES 에서 두 이름을 뺀다:
        "pu_t_month_stock_wh", "cs_m_proc"
      ※PROTECTED 비교가 소문자라 소문자로 넣어야 한다(_bad 판정: t.strip().lower()).
   ② 컷오버 시 r_bulk_copy 를 돌렸다면 **직후** restore 스크립트 실행.
   ③ cutover_mark.py --set --commit 로 마커 설정(현재 nx.cutover_state 비어 있음).""")
nx.close()
