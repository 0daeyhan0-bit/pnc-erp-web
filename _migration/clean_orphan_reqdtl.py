# -*- coding: utf-8 -*-
"""고아 명세 정리 — 헤더 없는 nx.set_input_req_dtl 삭제

  ★경위 (2026-09-08 실측)
    거래명세표 발행(coopplan.deliv420_issue)이 sheet_no 를 헤더(set_input_req)만 보고 채번했는데,
    9/1 15:39 ~ 9/2 10:48 사이 발행 시도에서 **명세만 남고 헤더가 없는 행**이 670행 생겼다.
      고아 sheet 901,204 ~ 901,533 (328개 번호) · 그 구간 헤더 0건
      헤더 최대는 901,199 — 고아가 그 위에 떠 있다
    그 뒤 발행이 같은 번호를 받아 남의 명세를 끌어안았다(sheet 901199 실사고).

  ★재고 영향 없음 — 고아 sheet 로 입고된 원장 0건(실측). 입고 전 상태로 떠 있을 뿐이다.

  ★코드는 이미 고쳤다
    · coopplan.py:1569  채번을 헤더+명세 양쪽 MAX 로
    · coopplan.py:1608  발행 직전 그 번호의 잔여 명세 DELETE + line_no 로컬 카운터

  ★안전장치
    · 기본 DRY-RUN. 실제 삭제는 --commit
    · 삭제 전 백업 테이블 자동 생성(nx.bk_reqdtl_orphan_260908)
    · 헤더가 있는 명세는 절대 건드리지 않는다
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
BK = "bk_reqdtl_orphan_260908"
ORPH = ("NOT EXISTS(SELECT 1 FROM nx.set_input_req h WITH(NOLOCK) "
        "WHERE h.sheet_no = d.sheet_no)")

cn = _nx(); cur = cn.cursor()
print("=" * 96)
print(" 고아 명세 정리 — nx.set_input_req_dtl (헤더 없는 행)")
print(" 모드: {}".format("★COMMIT (실제 삭제)" if COMMIT else "DRY-RUN (조회만)"))
print("=" * 96)


def stat(t):
    print("\n[{}]".format(t))
    cur.execute("SELECT COUNT(*) FROM nx.set_input_req_dtl")
    tot = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT d.sheet_no) FROM nx.set_input_req_dtl d WITH(NOLOCK) WHERE {ORPH}")
    r = cur.fetchone()
    print("   명세 전체 {:,}행 · 고아 {:,}행 / {:,}개 번호".format(tot, r[0], r[1]))
    cur.execute("""SELECT ISNULL(MAX(v),900000)+1 FROM (
                       SELECT MAX(CAST(sheet_no AS bigint)) v FROM nx.set_input_req WHERE ISNUMERIC(sheet_no)=1
                       UNION ALL
                       SELECT MAX(CAST(sheet_no AS bigint)) FROM nx.set_input_req_dtl WHERE ISNUMERIC(sheet_no)=1
                   ) t""")
    print("   다음 채번(수정본 기준) = {:,}".format(int(cur.fetchone()[0])))
    return r[0]


n = stat("정리 전")
if n == 0:
    print("\n   고아 없음 — 할 일 없다.")
    cur.close(); cn.close(); sys.exit(0)

# 삭제 대상 미리보기
cur.execute(f"""SELECT TOP 8 d.sheet_no, d.line_no, RTRIM(d.mat_code), d.mat_qty,
                       CONVERT(varchar(19), d.insert_datetime, 120)
                  FROM nx.set_input_req_dtl d WITH(NOLOCK) WHERE {ORPH}
                 ORDER BY d.sheet_no, d.line_no""")
print("\n   삭제 대상 샘플:")
for x in cur.fetchall():
    print("      sheet={} line={} mat={:<22s} qty={} {}".format(
        x[0], x[1], str(x[2]).strip(), x[3], str(x[4])))

# ★헤더 있는 명세는 안전한가 재확인
cur.execute(f"""SELECT COUNT(*) FROM nx.set_input_req_dtl d WITH(NOLOCK)
                 WHERE EXISTS(SELECT 1 FROM nx.set_input_req h WITH(NOLOCK) WHERE h.sheet_no=d.sheet_no)""")
print("\n   ※보존 대상(헤더 있는 명세) = {:,}행 — 건드리지 않는다".format(cur.fetchone()[0]))

if not COMMIT:
    print("\n" + "=" * 96)
    print(" 실행 예정 (DRY-RUN)")
    print("=" * 96)
    print("   ① 백업  SELECT * INTO nx.{} FROM ... WHERE 고아".format(BK))
    print("   ② 삭제  DELETE FROM nx.set_input_req_dtl WHERE 고아  ({:,}행)".format(n))
    print("\n   ⟹ 실제 반영하려면 --commit 을 붙여 다시 실행")
    cur.close(); cn.close(); sys.exit(0)

print("\n" + "=" * 96)
print(" 실행")
print("=" * 96)
try:
    cur.execute(f"IF OBJECT_ID('nx.{BK}') IS NOT NULL DROP TABLE nx.{BK}")
    cur.execute(f"""SELECT d.* INTO nx.{BK}
                      FROM nx.set_input_req_dtl d WHERE {ORPH}""")
    print("   ① 백업 nx.{} 생성 — {:,}행".format(BK, cur.rowcount))

    cur.execute(f"DELETE FROM nx.set_input_req_dtl WHERE {ORPH.replace('d.sheet_no', 'nx.set_input_req_dtl.sheet_no')}")
    print("   ② DELETE — {:,}행".format(cur.rowcount))

    cn.commit()
    print("\n   ✅ commit 완료")
except Exception as e:
    cn.rollback()
    print("\n   ★오류 — rollback: {}".format(str(e)[:220]))
    cur.close(); cn.close(); sys.exit(1)

stat("정리 후")
print("\n" + "=" * 96)
print(" 완료 — 이제 새 발행이 깨끗한 번호를 받는다")
print(" 백업 = nx.{} (되돌리려면 여기서 복원)".format(BK))
print("=" * 96)
cur.close(); cn.close()
