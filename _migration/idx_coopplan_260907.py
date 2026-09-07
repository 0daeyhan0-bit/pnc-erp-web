# -*- coding: utf-8 -*-
"""협력사계획현황 조회 인덱스 (2026-09-07)

  왜 — 「협력사 계획현황」 조회가 31일 기준 **93초**였다(대표 지적 "너무 조회속도가 느리네").
       원인은 조인이 아니라 **인덱스가 하나도 없는 HEAP**:
         nx.plan_part_mat  114,984행 · 인덱스 0개
         nx.plan_item_dtl    9,119행 · 인덱스 0개
       특히 coopplan.partner_planstatus 의 자재목록(mats) 조립이
         STUFF((SELECT DISTINCT ','+MAT_CODE FROM plan_part_mat x
                 WHERE x.WORK_ORDER=pp.WORK_ORDER AND x.SPLIT_WORK_ORDER=...
                   AND x.ASSY_ITEM_CODE=... AND x.MAT_WORK_CENTER_CODE=...) FOR XML PATH)
       **행마다 도는 상관 서브쿼리**라(코드 주석도 "여기가 가장 무겁다"고 적어둠),
       그때마다 11만 행을 전체 스캔했다.

  실측 효과 (대원산업 2148)
        2일   19.0초 →  2.98초   (6.4배)
       31일   93.0초 →  7.50초   (12.4배)

  ★쿼리는 한 줄도 안 고쳤다 — 인덱스만 추가. 결과 숫자는 그대로다.
  ★쓰기는 nx 만(§1-1). 라이브 PARTNER_ERP 는 건드리지 않는다.

  실행
    python _migration/idx_coopplan_260907.py            # 현황만 출력
    python _migration/idx_coopplan_260907.py --commit   # 실제 생성
    python _migration/idx_coopplan_260907.py --drop     # 되돌리기
"""
import sys, os, io, time

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client                      # noqa: E402

COMMIT = "--commit" in sys.argv
DROP = "--drop" in sys.argv

# (인덱스명, 테이블, DDL) — 이름으로 존재확인하므로 재실행해도 안전(멱등)
IDX = [
    ("IX_ppm_mats", "plan_part_mat",
     """CREATE INDEX IX_ppm_mats ON nx.plan_part_mat
          (WORK_ORDER, SPLIT_WORK_ORDER, ASSY_ITEM_CODE, MAT_WORK_CENTER_CODE)
        INCLUDE(MAT_CODE, PART_PLAN_YMD)""",
     "자재목록(mats) 상관 서브쿼리 — 가장 큰 효과"),
    ("IX_ppm_wc", "plan_part_mat",
     """CREATE INDEX IX_ppm_wc ON nx.plan_part_mat(MAT_WORK_CENTER_CODE)
        INCLUDE(WORK_ORDER, ASSY_ITEM_CODE, PART_PLAN_YMD)""",
     "작업처(협력사) 필터 — 조회조건 축"),
    ("IX_ppm_wo", "plan_part_mat",
     "CREATE INDEX IX_ppm_wo ON nx.plan_part_mat(WORK_ORDER)",
     "제번 조인"),
    ("IX_pid_wo", "plan_item_dtl",
     "CREATE INDEX IX_pid_wo ON nx.plan_item_dtl(WORK_ORDER)",
     "plan_item_dtl 조인축"),
]

cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  협력사계획현황 인덱스 — {'★DROP' if DROP else ('★생성(--commit)' if COMMIT else '현황만')}")
print("=" * 78)


def has(name, tbl):
    cur.execute("SELECT COUNT(*) FROM sys.indexes WHERE object_id=OBJECT_ID(?) AND name=?",
                f"nx.{tbl}", name)
    return int(cur.fetchone()[0] or 0) > 0


print("\n■ 현황")
for name, tbl, _ddl, why in IDX:
    print(f"   {name:<14}{('있음' if has(name, tbl) else '없음'):<6}nx.{tbl:<18}{why}")

cur.execute("SELECT COUNT(*) FROM nx.plan_part_mat")
print(f"\n   nx.plan_part_mat {int(cur.fetchone()[0]):,}행")

if DROP:
    n = 0
    for name, tbl, _ddl, _why in IDX:
        if has(name, tbl):
            cur.execute(f"DROP INDEX {name} ON nx.{tbl}"); n += 1
            print(f"   DROP {name}")
    cn.commit(); print(f"\n✅ {n}개 제거"); sys.exit(0)

if not COMMIT:
    print("\n※ 현황만 출력했습니다. 생성하려면 --commit 을 붙이세요.")
    sys.exit(0)

made = 0
for name, tbl, ddl, why in IDX:
    if has(name, tbl):
        print(f"   {name:<14}이미 있음 — 건너뜀")
        continue
    t0 = time.time()
    cur.execute(ddl); cn.commit()
    print(f"   {name:<14}생성 {time.time() - t0:.1f}초  ({why})")
    made += 1

print(f"\n✅ {made}개 생성")
print("   ※조회가 여전히 느리면 통계 갱신: UPDATE STATISTICS nx.plan_part_mat")
cn.close()
