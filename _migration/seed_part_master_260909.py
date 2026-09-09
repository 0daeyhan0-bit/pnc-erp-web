# -*- coding: utf-8 -*-
"""파트마스터 클린 이관 — nx.part_master 신설 + 씨딩 + 호환뷰 (2026-09-09)

★무엇을 — 미러 nx.PR_M_PROC_GAGONG(23행)을 클린 nx.part_master 로 옮긴다.
   데이터는 그대로다(라이브와 동일 · 웹 신규등록 0). 새 값을 만들지 않는다.

★왜 — 웹이 미러에 `ALTER TABLE` 로 얹은 컬럼이 **재적재 때 값째로 날아간다**.
     BARCODE_FLAG      바코드실적 허용
     PROD_RESULT_TYPE  생산실적 방식 ''미지정 / 'R'준비재고 / 'W'자재창고출고
   실제 사고 2회 —
     2026-08-30 : 컬럼 자체가 소실 → 파트마스터 "백엔드 연결 실패", 드래그 실적 전면 불가
     2026-09-09 : 값이 전부 NULL → 대표님이 S8·S10 을 준비재고(R)로 다시 설정
   `_ensure_result_cols()` 는 컬럼만 다시 만들 뿐 **값은 복구하지 못한다**.
   클린 테이블로 옮기면 재적재와 무관해진다.

★컬럼 — 미러 18개 중 코드가 쓰는 14개만 옮긴다(실측).
   버림: MIX_GAGONG · UPDATE_IP/COMPUTER/WINDOW (참조 0곳)
   감사: UPDATE_USER_ID/DATETIME → upd_user/upd_dt

★clean 이름은 소문자 — CLAUDE.md §1-9 "클린 = 재구축 클린본".
★안전 — 미러 읽기만. --apply 없으면 조회만.

사용: python _migration\\seed_part_master_260909.py [--apply]
"""
import sys, os, io, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
APPLY = "--apply" in sys.argv

# (미러, 클린)
COLS = [("GAGONG_PROC_CODE", "part_code"), ("GAGONG_PROC_DESC", "part_name"),
        ("GC_GUBUN", "gc_gubun"), ("PART_GROUP_CODE", "part_group"),
        ("WORK_CODE", "work_code"), ("IN_CUST_CODE", "wh_cust_code"),
        ("SORT_KEY", "sort_key"), ("PROD_RATE", "prod_rate"),
        ("WH_IP_ADDRESS", "wh_ip"), ("RACK_NUMBER", "rack_no"),
        ("BARCODE_FLAG", "barcode_flag"), ("PROD_RESULT_TYPE", "prod_result_type")]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" 파트마스터 클린 이관 — nx.PR_M_PROC_GAGONG → nx.part_master")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

cur.execute("SELECT COUNT(*) FROM {S}.PR_M_PROC_GAGONG".format(S=S)); n_m = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='part_master'""")
ex = cur.fetchone()[0]
print("\n① 미러 {}행 · nx.part_master {}".format(n_m, "이미 있음" if ex else "없음(신설)"))

sel = ", ".join("m.{}".format(a) for a, _ in COLS)
cur.execute("SELECT {} FROM {S}.PR_M_PROC_GAGONG m ORDER BY m.WORK_CODE, m.SORT_KEY".format(sel, S=S))
src = [tuple(x) for x in cur.fetchall()]
print("\n   — 옮길 내용(전량) —")
for r in src:
    print("   {:<8s} {:<20s} 구분={} 작업처={:<3s} 정렬={:<3} 효율={:<6g} bc={} pt={}".format(
        str(r[0]).strip(), str(r[1] or "").strip()[:20], str(r[2] or "").strip() or "-",
        str(r[4] or "").strip() or "-", r[6], float(r[7] or 0),
        str(r[10] or "").strip() or "-", str(r[11] or "").strip() or "-"))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 테이블 신설 ────────────────────────────────────────────────
cur.execute("""IF OBJECT_ID('nx.part_master','U') IS NULL
CREATE TABLE nx.part_master(
    part_code        varchar(10)   NOT NULL PRIMARY KEY,   -- GAGONG_PROC_CODE
    part_name        nvarchar(30)  NULL,                   -- GAGONG_PROC_DESC
    gc_gubun         varchar(1)    NULL,                   -- W자재창고 P생산파트 V생산창고 Q가공파트
    part_group       varchar(2)    NULL,
    work_code        varchar(4)    NULL,                   -- 작업처(P1·P2) → nx.work_place
    wh_cust_code     varchar(10)   NULL,                   -- 연동창고(거래처코드)
    sort_key         smallint      NULL,
    prod_rate        decimal(18,4) NULL,                   -- 생산효율(=키팅 회수율)
    wh_ip            varchar(30)   NULL,
    rack_no          tinyint       NULL,
    -- ★웹 고유(미러에 얹었다가 두 번 날아간 것)
    barcode_flag     varchar(1)    NULL,                   -- '1'=바코드실적 허용
    prod_result_type varchar(1)    NULL,                   -- ''미지정 / 'R'준비재고 / 'W'자재창고출고
    use_yn           varchar(1)    NULL DEFAULT '1',
    remarks          nvarchar(200) NULL,
    upd_user         nvarchar(40)  NULL,
    upd_dt           datetime      NULL
)""")
print("\n② 테이블 확보")

# ── 씨딩(멱등) ─────────────────────────────────────────────────
ccols = ", ".join(c for _, c in COLS)
ph = ", ".join("?" * len(COLS))
setc = ", ".join("{}=?".format(c) for _, c in COLS[1:])
n_i = n_u = 0
for r in src:
    code = str(r[0]).strip()
    cur.execute("SELECT 1 FROM {S}.part_master WHERE part_code=?".format(S=S), code)
    if cur.fetchone():
        cur.execute("""UPDATE {S}.part_master SET {sc}, upd_user='SEED260909', upd_dt=GETDATE()
                        WHERE part_code=?""".format(S=S, sc=setc), *(list(r[1:]) + [code]))
        n_u += 1
    else:
        cur.execute("""INSERT INTO {S}.part_master({cc}, use_yn, upd_user, upd_dt)
                       VALUES({ph}, '1', 'SEED260909', GETDATE())""".format(S=S, cc=ccols, ph=ph), *r)
        n_i += 1
print("③ 씨딩 — 신규 {} · 갱신 {}".format(n_i, n_u))

# ── 호환 뷰 (미러 컬럼명 그대로) ───────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_part_master','V') IS NOT NULL DROP VIEW nx.v_part_master")
vsel = ",\n       ".join("{} AS {}".format(c, a) for a, c in COLS)
cur.execute("""CREATE VIEW nx.v_part_master AS
SELECT {sel},
       CAST(NULL AS tinyint)   AS MIX_GAGONG,
       upd_user                AS UPDATE_USER_ID,
       upd_dt                  AS UPDATE_DATETIME,
       use_yn                  AS USE_YN,
       remarks                 AS REMARKS
  FROM nx.part_master""".format(sel=vsel))
print("④ 호환뷰 nx.v_part_master 생성")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_PROC_GAGONG m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.v_part_master v
                                  WHERE RTRIM(v.GAGONG_PROC_CODE)=RTRIM(m.GAGONG_PROC_CODE))""".format(S=S))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_PROC_GAGONG m
                 JOIN {S}.v_part_master v ON RTRIM(v.GAGONG_PROC_CODE)=RTRIM(m.GAGONG_PROC_CODE)
                WHERE ISNULL(RTRIM(CAST(m.GAGONG_PROC_DESC AS varchar(40))),'')
                      <>ISNULL(RTRIM(CAST(v.GAGONG_PROC_DESC AS varchar(40))),'')
                   OR ISNULL(RTRIM(CAST(m.WORK_CODE AS varchar(8))),'')
                      <>ISNULL(RTRIM(CAST(v.WORK_CODE AS varchar(8))),'')
                   OR ISNULL(RTRIM(CAST(m.GC_GUBUN AS varchar(4))),'')
                      <>ISNULL(RTRIM(CAST(v.GC_GUBUN AS varchar(4))),'')
                   OR ABS(ISNULL(m.PROD_RATE,0)-ISNULL(v.PROD_RATE,0))>0.0001
                   OR ISNULL(m.SORT_KEY,0)<>ISNULL(v.SORT_KEY,0)
                   OR ISNULL(RTRIM(CAST(m.PROD_RESULT_TYPE AS varchar(4))),'')
                      <>ISNULL(RTRIM(CAST(v.PROD_RESULT_TYPE AS varchar(4))),'')""".format(S=S))
diff = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_part_master".format(S=S)); n_v = cur.fetchone()[0]
print("\n⑤ 검증 — 미러 {}행 · 뷰 {}행 · 결손 {} · 값불일치 {}".format(n_m, n_v, miss, diff))

if miss == 0 and diff == 0:
    nx.commit(); print("   ✅ 커밋 완료")
    cur.execute("""SELECT part_code, part_name, work_code, prod_rate, barcode_flag, prod_result_type
                     FROM {S}.part_master WHERE ISNULL(prod_result_type,'')<>'' ORDER BY sort_key""".format(S=S))
    print("\n   ★실적처리방법 설정분(보존 확인):")
    for r in cur.fetchall():
        print("      {} {} → {}".format(str(r[0]).strip(), str(r[1]).strip(),
              {"R": "준비재고", "W": "자재창고출고"}.get(str(r[5]).strip(), str(r[5]))))
    print("""
   다음 — 치환 대상
     코드 80곳 · SP 20곳
     nx.PR_M_PROC_GAGONG → nx.v_part_master
     ★partmaster.py 의 쓰기(INSERT/UPDATE/DELETE)는 뷰가 아니라 nx.part_master 로
     ★_ensure_result_cols() 는 제거 — 클린은 날아가지 않는다""")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
