# -*- coding: utf-8 -*-
"""라인마스터 미러 은퇴 — nx.PR_M_LINE_NO → nx.v_line_no (2026-09-09)

★클린(nx.line_no)은 이미 있고 화면도 이미 그걸 쓴다(기준 마스터 관리 › 라인 마스터).
   그런데 **계획 편성은 아직 미러를 읽는다** — 달력에서 겪은 것과 같은 구조다:

     화면 쓰기  prodinfo.py    → nx.line_no        (클린)
     편성 읽기  planrev.py:365 → {P}PR_M_LINE_NO   (미러)  ★STEP7 직납품 당김
     편성 읽기  planrev.py:1906→ nx.PR_M_LINE_NO   (미러)
     드롭다운   qc.py:53       → nx.PR_M_LINE_NO   (미러)

   ⟹ 화면에서 직납당김을 고쳐도 **편성에 반영되지 않는다.**
      지금은 두 테이블 값이 같아 증상이 안 보일 뿐이다(실측 42=42·불일치 0,
      직납당김은 CA=1 하나뿐). CA 를 화면에서 고치는 순간 갈린다.

★호환뷰를 쓰는 이유 — 클린은 소문자 컬럼(line_no·cust_maint_day)이라
   미러 이름(LINE_NO·CUST_MAINT_DAY)을 그대로 노출하면 SQL 을 한 글자도 안 고친다.
   미러에만 있던 감사컬럼(INSERT_*·UPDATE_IP/COMPUTER/WINDOW)은 NULL 로 채운다(참조 0곳).

★대사 결과(실측 2026-09-09)
   라이브 42 = 미러 42 = 클린 42 · 클린에만/라이브에만 0 · 직납당김 불일치 0

사용: python _migration\\switch_line_no_260909.py [--apply]
"""
import sys, os, io, re, shutil, datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%y%m%d_%H%M")
S = "PARTNER_ERP_TEST3.nx"
T = "PR_M_LINE_NO"

PAT3 = re.compile(r"\bPARTNER_ERP_TEST3\.nx\.{}\b".format(T), re.I)
PATV = re.compile(r"(\{(?:S|SCH|NXS|P)\}\.?)" + T + r"\b", re.I)
PATN = re.compile(r"\bnx\.{}\b".format(T), re.I)
PATB = re.compile(r"\b{}\b".format(T), re.I)
ANY = re.compile(r"\b{}\b".format(T), re.I)
SQLPRE = re.compile(r"\b(FROM|JOIN|INTO|UPDATE|DELETE\s+FROM|TABLE)\s+[\w\.\{\}\[\]]*" + T + r"\b", re.I)

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" 라인마스터 전환 — {} → nx.v_line_no".format(T))
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

# ── 사전 대사 ──────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM {S}.line_no".format(S=S)); n_c = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.{T}".format(S=S, T=T)); n_m = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.{T} m
                WHERE NOT EXISTS(SELECT 1 FROM {S}.line_no c WHERE RTRIM(c.line_no)=RTRIM(m.LINE_NO))""".format(S=S, T=T))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {S}.{T} m
                 JOIN {S}.line_no c ON RTRIM(c.line_no)=RTRIM(m.LINE_NO)
                WHERE ISNULL(c.cust_maint_day,0)<>ISNULL(m.CUST_MAINT_DAY,0)
                   OR ISNULL(c.maint_day,0)<>ISNULL(m.MAINT_DAY,0)
                   OR ISNULL(RTRIM(c.maint_hhmm),'')<>ISNULL(RTRIM(m.MAINT_HHMM),'')""".format(S=S, T=T))
diff = cur.fetchone()[0]
print("\n① 대사 — 클린 {}행 · 미러 {}행 · 결손 {} · 값불일치 {}".format(n_c, n_m, miss, diff))
if miss or diff:
    print("   ★차이가 있다 — 전환하면 편성 값이 바뀐다. 먼저 동기화할 것.")
    nx.rollback(); nx.close(); sys.exit(1)

cur.execute("SELECT line_no, cust_maint_day FROM {S}.line_no WHERE ISNULL(cust_maint_day,0)<>0 ORDER BY line_no".format(S=S))
print("   직납당김 보유 라인: " + (", ".join("{}={}".format(str(a).strip(), b) for a, b in cur.fetchall()) or "없음"))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 호환 뷰 ────────────────────────────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_line_no','V') IS NOT NULL DROP VIEW nx.v_line_no")
cur.execute("""CREATE VIEW nx.v_line_no AS
SELECT line_no        AS LINE_NO,
       apply_ymd      AS APPLY_YMD,
       maint_day      AS MAINT_DAY,
       maint_hhmm     AS MAINT_HHMM,
       link_cust_code AS LINK_CUST_CODE,
       cust_maint_day AS CUST_MAINT_DAY,
       upd_user       AS UPDATE_USER_ID,
       upd_dt         AS UPDATE_DATETIME,
       CAST(NULL AS varchar(20)) AS INSERT_USER_ID,
       CAST(NULL AS datetime)    AS INSERT_DATETIME,
       CAST(NULL AS varchar(20)) AS INSERT_IP,
       CAST(NULL AS varchar(20)) AS INSERT_COMPUTER,
       CAST(NULL AS varchar(30)) AS INSERT_WINDOW,
       CAST(NULL AS varchar(20)) AS UPDATE_IP,
       CAST(NULL AS varchar(20)) AS UPDATE_COMPUTER,
       CAST(NULL AS varchar(30)) AS UPDATE_WINDOW
  FROM nx.line_no""")
nx.commit()
print("\n② 호환뷰 nx.v_line_no 생성")

# ── 코드 치환 ──────────────────────────────────────────────────
BK = os.path.join(r"c:\Users\박근민\Desktop\NEW_ERP_1\_schema", "bk_lineno_{}".format(STAMP))
RD = os.path.join(BE, "routers")
files = ["common.py", "live_api.py", "app.py"] + \
        [os.path.join("routers", x) for x in sorted(os.listdir(RD)) if x.endswith(".py")]
tot = kept = 0
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    src = open(p, encoding="utf-8").read()
    if not ANY.search(src): continue
    out, n, keep = [], 0, []
    for i, ln in enumerate(src.split("\n"), 1):
        if not ANY.search(ln):
            out.append(ln); continue
        if ln.lstrip().startswith("#") or not SQLPRE.search(ln):
            out.append(ln); keep.append((i, ln.strip()[:66])); continue
        new = PAT3.sub("PARTNER_ERP_TEST3.nx.v_line_no", ln)
        new = PATV.sub(lambda m: m.group(1) + "v_line_no", new)
        new = PATN.sub("nx.v_line_no", new)
        new = PATB.sub("nx.v_line_no", new)
        if new != ln: n += 1
        out.append(new)
    if n or keep:
        print("\n■ {:<24s} 치환 {:<3d} 보존 {}".format(f, n, len(keep)))
        for i, s in keep: print("     보존 L{:<5d} {}".format(i, s))
    tot += n; kept += len(keep)
    if n:
        os.makedirs(BK, exist_ok=True)
        shutil.copy2(p, os.path.join(BK, os.path.basename(f)))
        open(p, "w", encoding="utf-8", newline="").write("\n".join(out))

print("\n③ 코드 치환 {}곳 · 보존 {}곳 · 백업 {}".format(tot, kept, BK))

# ── 뷰 동작 확인 ───────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.v_line_no v
                 JOIN {S}.{T} m ON RTRIM(m.LINE_NO)=RTRIM(v.LINE_NO)
                WHERE ISNULL(v.CUST_MAINT_DAY,0)<>ISNULL(m.CUST_MAINT_DAY,0)""".format(S=S, T=T))
d2 = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_line_no".format(S=S)); n_v = cur.fetchone()[0]
print("④ 뷰 검증 — {}행 · 미러와 직납당김 불일치 {}".format(n_v, d2))

bad = 0
for f in files:
    p = os.path.join(BE, f)
    if not os.path.exists(p): continue
    for i, ln in enumerate(open(p, encoding="utf-8").read().split("\n"), 1):
        if re.search(r"\}\.nx\.v_line_no|nx\.nx\.", ln):
            print("   ★이중접두어 {} L{}".format(os.path.basename(f), i)); bad += 1
print("⑤ 이중접두어: {}".format("✔ 없음" if bad == 0 else "★{}곳".format(bad)))
print("\n   ※편성 재실행으로 STEP7 직납당김이 동일한지 확인할 것(nx.plan_direct_pull)")
nx.close()
