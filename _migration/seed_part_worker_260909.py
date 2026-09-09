# -*- coding: utf-8 -*-
"""파트별 작업자 클린 이관 — nx.part_worker 신설 + 씨딩 + 호환뷰 (2026-09-09)

★무엇을 — 미러 nx.PR_M_PROC_GAGONG_WORKER(163행)를 클린 nx.part_worker 로 옮긴다.
   데이터는 그대로다(라이브 163 = 미러 163 · 웹 신규등록 0). 새 값을 만들지 않는다.

★왜 — 파트마스터(nx.part_master)는 어제 클린으로 옮겼는데 그 **짝인 작업자만 미러로 남아**
   한 화면(「파트 마스터」 + 우측 「파트별 작업자」)이 두 계보로 갈려 있다.
   이 그리드는 **쓰기가 7곳**(추가·수정·삭제·일괄저장)이라 컷오버로 레거시가 은퇴하면
   웹에서 등록한 작업자가 재적재에 날아가거나 옛 명단을 계속 읽는다(§1-9-1).
   파트마스터가 8/30·9/9 두 번 당한 것과 같은 구조다.

★컬럼 — 미러 13개 중 코드가 실제 읽는 3개(파트·작업자·실작업자플래그) + 감사 4개.
   버림: INSERT/UPDATE_IP·COMPUTER·WINDOW (참조 0곳)
   ※미러에 웹이 추가한 컬럼은 없다(라이브 13 = 미러 13).

★고아 22명 — B0001(10)·K0001(10)·P0004(2) 는 **라이브 파트마스터에도 없는 파트코드**다.
   레거시가 파트를 지웠는데 작업자만 남은 정리 누락. **지우지 않고 그대로 옮긴다**
   (임의 삭제 금지). 화면은 파트를 골라 조회하므로 보이지 않는다. 리포트로만 남긴다.

★clean 이름은 소문자 — CLAUDE.md §1-9.
★안전 — 미러 읽기만. --apply 없으면 조회만.

사용: python _migration\\seed_part_worker_260909.py [--apply]
"""
import sys, os, io

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
T = "PR_M_PROC_GAGONG_WORKER"
APPLY = "--apply" in sys.argv

# (미러, 클린)
COLS = [("GAGONG_PROC_CODE", "part_code"), ("WORKER_CODE", "worker_name"),
        ("WORK_FLAG", "work_flag"),
        ("INSERT_USER_ID", "ins_user"), ("INSERT_DATETIME", "ins_dt"),
        ("UPDATE_USER_ID", "upd_user"), ("UPDATE_DATETIME", "upd_dt")]

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 파트별 작업자 클린 이관 — nx.{} → nx.part_worker".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

cur.execute("SELECT COUNT(*) FROM {S}.{T}".format(S=S, T=T)); n_m = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='part_worker'""")
print("\n① 미러 {}행 · nx.part_worker {}".format(n_m, "이미 있음" if cur.fetchone()[0] else "없음(신설)"))

cur.execute("""SELECT w.GAGONG_PROC_CODE, ISNULL(p.part_name,''), COUNT(*),
                      SUM(CASE WHEN RTRIM(ISNULL(w.WORK_FLAG,''))='1' THEN 1 ELSE 0 END)
                 FROM {S}.{T} w
                 LEFT JOIN {S}.part_master p ON RTRIM(p.part_code)=RTRIM(w.GAGONG_PROC_CODE)
                GROUP BY w.GAGONG_PROC_CODE, p.part_name
                ORDER BY COUNT(*) DESC""".format(S=S, T=T))
print("\n   — 파트별 인원 —")
orphan = 0
for r in cur.fetchall():
    nm = str(r[1]).strip()
    if not nm: orphan += r[2]
    print("      {:<8s} {:<18s} {:>3}명 (실작업자 {}){}".format(
        str(r[0]).strip(), nm[:18] or "-", r[2], r[3], "  ★파트마스터에 없음" if not nm else ""))
print("   → 고아 {}명 (그대로 이관)".format(orphan))

sel = ", ".join("w.{}".format(a) for a, _ in COLS)
cur.execute("SELECT {} FROM {S}.{T} w ORDER BY w.GAGONG_PROC_CODE, w.WORKER_CODE".format(sel, S=S, T=T))
src = [tuple(x) for x in cur.fetchall()]

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 테이블 신설 ────────────────────────────────────────────────
cur.execute("""IF OBJECT_ID('nx.part_worker','U') IS NULL
CREATE TABLE nx.part_worker(
    part_code    varchar(10)  NOT NULL,          -- GAGONG_PROC_CODE → nx.part_master
    worker_name  nvarchar(30) NOT NULL,          -- WORKER_CODE (코드가 아니라 이름이다)
    work_flag    varchar(1)   NULL,              -- '1'=실작업자 (키팅 인원수·공수 산정에 쓰임)
    ins_user     nvarchar(40) NULL,
    ins_dt       datetime     NULL,
    upd_user     nvarchar(40) NULL,
    upd_dt       datetime     NULL,
    CONSTRAINT PK_nx_part_worker PRIMARY KEY(part_code, worker_name)
)""")
print("\n② 테이블 확보")

# ── 씨딩(멱등) ─────────────────────────────────────────────────
ccols = ", ".join(c for _, c in COLS)
ph = ", ".join("?" * len(COLS))
setc = ", ".join("{}=?".format(c) for _, c in COLS[2:])
n_i = n_u = 0
for r in src:
    pc, wn = str(r[0]).strip(), str(r[1]).strip()
    cur.execute("SELECT 1 FROM {S}.part_worker WHERE part_code=? AND worker_name=?".format(S=S), pc, wn)
    if cur.fetchone():
        cur.execute("UPDATE {S}.part_worker SET {sc} WHERE part_code=? AND worker_name=?".format(S=S, sc=setc),
                    *(list(r[2:]) + [pc, wn])); n_u += 1
    else:
        cur.execute("INSERT INTO {S}.part_worker({cc}) VALUES({ph})".format(S=S, cc=ccols, ph=ph), *r)
        n_i += 1
print("③ 씨딩 — 신규 {} · 갱신 {}".format(n_i, n_u))

# ── 호환 뷰 (미러 컬럼명 그대로) ───────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_part_worker','V') IS NOT NULL DROP VIEW nx.v_part_worker")
vsel = ",\n       ".join("{} AS {}".format(c, a) for a, c in COLS)
cur.execute("""CREATE VIEW nx.v_part_worker AS
SELECT {sel},
       CAST(NULL AS varchar(20)) AS INSERT_IP,
       CAST(NULL AS varchar(20)) AS INSERT_COMPUTER,
       CAST(NULL AS varchar(30)) AS INSERT_WINDOW,
       CAST(NULL AS varchar(20)) AS UPDATE_IP,
       CAST(NULL AS varchar(20)) AS UPDATE_COMPUTER,
       CAST(NULL AS varchar(30)) AS UPDATE_WINDOW
  FROM nx.part_worker""".format(sel=vsel))
print("④ 호환뷰 nx.v_part_worker 생성")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.{T} m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.v_part_worker v
                        WHERE RTRIM(v.GAGONG_PROC_CODE)=RTRIM(m.GAGONG_PROC_CODE)
                          AND RTRIM(v.WORKER_CODE)=RTRIM(m.WORKER_CODE))""".format(S=S, T=T))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.{T} m
                 JOIN {S}.v_part_worker v ON RTRIM(v.GAGONG_PROC_CODE)=RTRIM(m.GAGONG_PROC_CODE)
                                         AND RTRIM(v.WORKER_CODE)=RTRIM(m.WORKER_CODE)
                WHERE ISNULL(RTRIM(m.WORK_FLAG),'')<>ISNULL(RTRIM(v.WORK_FLAG),'')""".format(S=S, T=T))
diff = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_part_worker".format(S=S)); n_v = cur.fetchone()[0]
cur.execute("""SELECT SUM(CASE WHEN RTRIM(ISNULL(WORK_FLAG,''))='1' THEN 1 ELSE 0 END)
                 FROM {S}.v_part_worker""".format(S=S)); n_r = cur.fetchone()[0]
print("\n⑤ 검증 — 미러 {}행 · 뷰 {}행(실작업자 {}) · 결손 {} · 플래그불일치 {}".format(
    n_m, n_v, n_r, miss, diff))

if miss == 0 and diff == 0 and n_v == n_m:
    nx.commit(); print("   ✅ 커밋 완료")
    print("""
   다음 — 치환
     조회 → nx.v_part_worker  (partmaster·gongsu·kitting·prodsheet)
     쓰기 → nx.part_worker    (partmaster.py 7곳 — 컬럼명이 소문자라 수동)""")
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
