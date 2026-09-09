# -*- coding: utf-8 -*-
"""시스템코드 클린 이관 — nx.code_kind + nx.code_detail + 호환뷰 (2026-09-09)

★레거시 화면 = 「System별 코드별 상세」(시스템코드관리) — 3단 구조
    시스템코드   CM_M_SYSTEM(16행)      ER/PE/MP… 프로젝트 × CM/PR/PU/SA/HR/ZI
    코드군       CM_M_MASTER(186행)     PR003 '생산추가입력라인' · 상세코드SIZE · 이력관리
    상세코드     CM_M_MASTER_DETAIL(3,837행)  AA=설치 · EZ=이지링크 …

★시스템코드는 별도 컬럼이 아니라 **KIND_CODE 앞 2자**다(PR003 → PR=생산관리).
   CM_M_MASTER 에 SYSTEM_CODE 컬럼은 없다(실측). CM_M_SYSTEM 은 (PROJECT_CODE, SYSTEM_CODE) 축이라
   PROJECT_CODE='ER' 만 쓰면 6종(CM·HR·PR·PU·SA·ZI)이 나온다 → 그걸 시스템 목록으로 쓴다.

★무엇을 옮기나 — **필요한 41종만**(대표 확정 2026-09-09 "필요한것만 가져오자").
   레거시 186종 3,837건 중 웹 도메인인 것만 고른다 → 41종 약 260건.

     PR 28종  생산관리 전부. 웹이 이미 읽는 4종(PR003 라인·PR006 소분류·PR008 품목구분·
              PR011 거래처분류)에 더해 PR015 파트코드종류(=파트마스터 gc_gubun)·
              PR019 금속구분(common.py:835 가 밀도를 하드코딩해 둔 것)·PR007 조달구분·
              PR017 파트그룹·PR024 임율구분 등 앞으로 쓸 것들.
     QA  3종  무작업귀책부서·설비분류·비가동유형
     PU  2종  스태커IP·자재재고조정 가능사원
     TT001    UPPH현황구분
     CM  7종  단위·과세구분·마감구분·통화·은행코드·주야구분·완료구분

   ★버리는 것 = HR*(인사급여) · EC*(전자결재) · CS*(원가 1,500여건) · ZI*(이미지) ·
     S000*(레거시 PB 화면색상·보안등급) · CM1xx~CM6xx(스케줄·문의·안전점검).
     전부 **웹이 만들지 않는 모듈**이라 옮겨도 관리 주체가 없다.
     CS* 는 원가지만 우리 원가엔진(NxCostEngine)은 이 코드를 쓰지 않는다(자체 계산).
     S0001 은 시스템코드 목록인데 우리는 KIND_CODE 앞 2자로 뽑으므로 불필요.
   나중에 필요해지면 KINDS 에 추가하고 다시 돌리면 된다(멱등).

★★nx 미러가 없는 테이블이 둘 — CM_M_SYSTEM · CM_M_MASTER 는 nx 에 아예 없다(실측).
   그래서 **라이브(PARTNER_ERP, 읽기전용)에서 직접 읽어** 클린에 씨딩한다.
   상세(CM_M_MASTER_DETAIL)만 nx 미러가 있고 라이브와 완전 동일(3,837 = 3,837 · 차이 0).

★쓰기 — 웹에 등록화면이 없었다(쓰기 0곳). 이번에 「시스템코드관리」 화면을 만들면서
   쓰기가 생기므로, 컷오버 후 코드 추가·수정이 웹에서 가능해진다.

★안전 — 라이브는 SELECT 만. 쓰기는 nx 뿐. --apply 없으면 조회만.

사용: python _migration\\seed_syscode_260909.py [--apply]
"""
import sys, os, io

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

L = "PARTNER_ERP.dbo"
S = "PARTNER_ERP_TEST3.nx"
APPLY = "--apply" in sys.argv

# 코드군 헤더 (미러, 클린)
KCOLS = [("KIND_CODE", "kind_code"), ("KIND_DESC", "kind_desc"), ("DETAIL_SIZE", "detail_size"),
         ("SYSTEM_TAG", "system_tag"), ("KIND_HISTORY_FLAG", "history_flag"),
         ("OTHER_CHAR1_DESC", "char1_desc"), ("OTHER_CHAR2_DESC", "char2_desc"),
         ("OTHER_CHAR3_DESC", "char3_desc"), ("OTHER_CHAR4_DESC", "char4_desc"),
         ("OTHER_CHAR5_DESC", "char5_desc"),
         ("OTHER_NUM1_DESC", "num1_desc"), ("OTHER_NUM2_DESC", "num2_desc"),
         ("OTHER_NUM3_DESC", "num3_desc"), ("OTHER_NUM4_DESC", "num4_desc"),
         ("OTHER_NUM5_DESC", "num5_desc"),
         ("OTHER_FLAG1_DESC", "flag1_desc"), ("OTHER_FLAG2_DESC", "flag2_desc"),
         ("OTHER_FLAG3_DESC", "flag3_desc"),
         ("UPDATE_USER_ID", "upd_user"), ("UPDATE_DATETIME", "upd_dt")]

# 상세코드 (미러, 클린)
DCOLS = [("KIND_CODE", "kind_code"), ("DETAIL_CODE", "detail_code"), ("APPLY_YMD", "apply_ymd"),
         ("DETAIL_DESC", "detail_desc"), ("DETAIL_DESCS", "detail_descs"),
         ("OTHER_CHAR1", "char1"), ("OTHER_CHAR2", "char2"), ("OTHER_CHAR3", "char3"),
         ("OTHER_CHAR4", "char4"), ("OTHER_CHAR5", "char5"),
         ("OTHER_NUM1", "num1"), ("OTHER_NUM2", "num2"), ("OTHER_NUM3", "num3"),
         ("OTHER_NUM4", "num4"), ("OTHER_NUM5", "num5"),
         ("OTHER_FLAG1", "flag1"), ("OTHER_FLAG2", "flag2"), ("OTHER_FLAG3", "flag3"),
         ("SORT_SEQ", "sort_seq"), ("USE_FLAG", "use_flag"),
         ("UPDATE_USER_ID", "upd_user"), ("UPDATE_DATETIME", "upd_dt")]

SYSNAME = {"CM": "공통관리", "PR": "생산관리", "PU": "구매관리",
           "SA": "영업관리", "QA": "품질관리", "TT": "생산관리"}

# ★가져올 코드군 (대표 확정 2026-09-09) — 나중에 필요해지면 여기 추가하고 다시 돌린다(멱등)
KINDS = (
    # 생산관리 28종 — 전부
    ["PR{:03d}".format(i) for i in range(1, 29)] +
    # 품질 3종
    ["QA001", "QA002", "QA003"] +
    # 구매 2종
    ["PU001", "PU002"] +
    # 영업/생산 지표
    ["TT001"] +
    # 공통 7종 — 웹이 쓰거나 쓸 것만
    ["CM002",   # 단위 EA·KG·LI·RL
     "CM003",   # 과세구분
     "CM008",   # 마감구분 D일마감·M월마감
     "CM014",   # 통화 KRW·USD·EUR·RMB
     "CM701",   # 은행코드 ★웹 사용중
     "CM998",   # 주야구분
     "CM999"]   # 완료구분
)
IN_KINDS = ", ".join("'{}'".format(k) for k in KINDS)

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 100)
print(" 시스템코드 클린 이관 — CM_M_MASTER/CM_M_MASTER_DETAIL → nx.code_kind/nx.code_detail")
print(" 모드: {}".format("★실제 반영(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 100)

cur.execute("SELECT COUNT(*) FROM {L}.CM_M_MASTER".format(L=L)); n_all = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {L}.CM_M_MASTER_DETAIL".format(L=L)); n_dall = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {L}.CM_M_MASTER WHERE KIND_CODE IN ({I})".format(L=L, I=IN_KINDS))
n_k = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {L}.CM_M_MASTER_DETAIL WHERE KIND_CODE IN ({I})".format(L=L, I=IN_KINDS))
n_dl = cur.fetchone()[0]
print("\n① 라이브 전체 {}종 {}건 → ★가져올 {}종 {}건".format(n_all, n_dall, n_k, n_dl))
print("   ※헤더(CM_M_MASTER)·시스템(CM_M_SYSTEM)은 nx 미러가 없어 라이브에서 직접 읽는다")

miss_k = [k for k in KINDS]
cur.execute("SELECT KIND_CODE FROM {L}.CM_M_MASTER WHERE KIND_CODE IN ({I})".format(L=L, I=IN_KINDS))
have = {str(r[0]).strip() for r in cur.fetchall()}
gone = [k for k in KINDS if k not in have]
if gone:
    print("   ★라이브에 없는 코드군: {}".format(", ".join(gone)))

cur.execute("""SELECT sys, COUNT(*), SUM(n) FROM (
                 SELECT LEFT(m.KIND_CODE,2) sys, m.KIND_CODE,
                        (SELECT COUNT(*) FROM {L}.CM_M_MASTER_DETAIL d
                          WHERE d.KIND_CODE=m.KIND_CODE) n
                   FROM {L}.CM_M_MASTER m WHERE m.KIND_CODE IN ({I})) t
                GROUP BY sys ORDER BY sys""".format(L=L, I=IN_KINDS))
print("\n   — 가져올 시스템별 —")
for a, b, c in cur.fetchall():
    k = str(a).strip()
    print("      {:<4s} {:<10s} {:>3}종 {:>5}건".format(k, SYSNAME.get(k, "-"), b, c))

if not APPLY:
    print("\n   ※dry-run — 반영하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 테이블 ─────────────────────────────────────────────────────
cur.execute("""IF OBJECT_ID('nx.code_kind','U') IS NULL
CREATE TABLE nx.code_kind(
    kind_code    varchar(5)   NOT NULL PRIMARY KEY,  -- 'PR003' (앞2자=시스템코드)
    kind_desc    nvarchar(50) NULL,                  -- '생산추가입력라인'
    detail_size  int          NULL,                  -- 상세코드 자릿수
    system_tag   char(1)      NULL,                  -- 'M'=마스터
    history_flag char(1)      NULL,                  -- 이력관리 Y/N (apply_ymd 로 여러 벌)
    char1_desc   nvarchar(30) NULL, char2_desc nvarchar(30) NULL, char3_desc nvarchar(30) NULL,
    char4_desc   nvarchar(30) NULL, char5_desc nvarchar(30) NULL,
    num1_desc    nvarchar(30) NULL, num2_desc  nvarchar(30) NULL, num3_desc  nvarchar(30) NULL,
    num4_desc    nvarchar(30) NULL, num5_desc  nvarchar(30) NULL,
    flag1_desc   nvarchar(30) NULL, flag2_desc nvarchar(30) NULL, flag3_desc nvarchar(30) NULL,
    upd_user     nvarchar(40) NULL,
    upd_dt       datetime     NULL
)""")
cur.execute("""IF OBJECT_ID('nx.code_detail','U') IS NULL
CREATE TABLE nx.code_detail(
    kind_code    varchar(5)    NOT NULL,
    detail_code  varchar(10)   NOT NULL,
    apply_ymd    varchar(8)    NOT NULL DEFAULT '',  -- 이력관리 코드군은 이걸로 여러 벌
    detail_desc  nvarchar(255) NULL,
    detail_descs nvarchar(255) NULL,                 -- 일어명
    char1 nvarchar(255) NULL, char2 nvarchar(255) NULL, char3 nvarchar(255) NULL,
    char4 nvarchar(255) NULL, char5 nvarchar(255) NULL,
    num1  real NULL, num2 real NULL, num3 real NULL, num4 real NULL, num5 real NULL,
    flag1 char(1) NULL, flag2 char(1) NULL, flag3 char(1) NULL,
    sort_seq     real          NULL,
    use_flag     char(1)       NULL,
    upd_user     nvarchar(40)  NULL,
    upd_dt       datetime      NULL,
    CONSTRAINT PK_nx_code_detail PRIMARY KEY(kind_code, detail_code, apply_ymd)
)""")
print("\n② 테이블 확보")

# ── 헤더 씨딩 ──────────────────────────────────────────────────
sel = ", ".join(a for a, _ in KCOLS)
cur.execute("SELECT {} FROM {L}.CM_M_MASTER WHERE KIND_CODE IN ({I}) ORDER BY KIND_CODE".format(sel, L=L, I=IN_KINDS))
krows = [tuple(x) for x in cur.fetchall()]
cc = ", ".join(c for _, c in KCOLS); ph = ", ".join("?" * len(KCOLS))
setc = ", ".join("{}=?".format(c) for _, c in KCOLS[1:])
ki = ku = 0
for r in krows:
    k = str(r[0]).strip()
    cur.execute("SELECT 1 FROM {S}.code_kind WHERE kind_code=?".format(S=S), k)
    if cur.fetchone():
        cur.execute("UPDATE {S}.code_kind SET {sc} WHERE kind_code=?".format(S=S, sc=setc), *(list(r[1:]) + [k])); ku += 1
    else:
        cur.execute("INSERT INTO {S}.code_kind({cc}) VALUES({ph})".format(S=S, cc=cc, ph=ph), *r); ki += 1
print("③ 코드군 — 신규 {} · 갱신 {}".format(ki, ku))

# ── 상세 씨딩 (라이브 기준) ────────────────────────────────────
sel = ", ".join("ISNULL(APPLY_YMD,'')" if a == "APPLY_YMD" else a for a, _ in DCOLS)
cur.execute("""SELECT {} FROM {L}.CM_M_MASTER_DETAIL WHERE KIND_CODE IN ({I})
                ORDER BY KIND_CODE, DETAIL_CODE, APPLY_YMD""".format(sel, L=L, I=IN_KINDS))
drows = [tuple(x) for x in cur.fetchall()]
cc = ", ".join(c for _, c in DCOLS); ph = ", ".join("?" * len(DCOLS))
setc = ", ".join("{}=?".format(c) for _, c in DCOLS[3:])
di = du = 0
for r in drows:
    k, d, y = str(r[0]).strip(), str(r[1]).strip(), str(r[2] or "").strip()
    cur.execute("SELECT 1 FROM {S}.code_detail WHERE kind_code=? AND detail_code=? AND apply_ymd=?".format(S=S), k, d, y)
    if cur.fetchone():
        cur.execute("""UPDATE {S}.code_detail SET {sc}
                        WHERE kind_code=? AND detail_code=? AND apply_ymd=?""".format(S=S, sc=setc),
                    *(list(r[3:]) + [k, d, y])); du += 1
    else:
        cur.execute("INSERT INTO {S}.code_detail({cc}) VALUES({ph})".format(S=S, cc=cc, ph=ph), *r); di += 1
print("④ 상세코드 — 신규 {} · 갱신 {}".format(di, du))

# ── 호환 뷰 (미러 컬럼명 그대로) ───────────────────────────────
cur.execute("IF OBJECT_ID('nx.v_code_detail','V') IS NOT NULL DROP VIEW nx.v_code_detail")
vsel = ",\n       ".join("{} AS {}".format(c, a) for a, c in DCOLS)
cur.execute("CREATE VIEW nx.v_code_detail AS\nSELECT {}\n  FROM nx.code_detail".format(vsel))
cur.execute("IF OBJECT_ID('nx.v_code_kind','V') IS NOT NULL DROP VIEW nx.v_code_kind")
vsel = ",\n       ".join("{} AS {}".format(c, a) for a, c in KCOLS)
cur.execute("CREATE VIEW nx.v_code_kind AS\nSELECT {}\n  FROM nx.code_kind".format(vsel))
print("⑤ 호환뷰 nx.v_code_detail · nx.v_code_kind 생성")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM {S}.code_kind".format(S=S)); c_k = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.code_detail".format(S=S)); c_d = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {L}.CM_M_MASTER_DETAIL l
                WHERE l.KIND_CODE IN ({I})
                  AND NOT EXISTS(SELECT 1 FROM {S}.v_code_detail v
                        WHERE RTRIM(v.KIND_CODE)=RTRIM(l.KIND_CODE)
                          AND RTRIM(v.DETAIL_CODE)=RTRIM(l.DETAIL_CODE)
                          AND ISNULL(RTRIM(v.APPLY_YMD),'')=ISNULL(RTRIM(l.APPLY_YMD),''))""".format(S=S, L=L, I=IN_KINDS))
miss = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM {L}.CM_M_MASTER_DETAIL l
                 JOIN {S}.v_code_detail v ON RTRIM(v.KIND_CODE)=RTRIM(l.KIND_CODE)
                                         AND RTRIM(v.DETAIL_CODE)=RTRIM(l.DETAIL_CODE)
                                         AND ISNULL(RTRIM(v.APPLY_YMD),'')=ISNULL(RTRIM(l.APPLY_YMD),'')
                WHERE l.KIND_CODE IN ({I})
                  AND (ISNULL(RTRIM(l.DETAIL_DESC),'')<>ISNULL(RTRIM(v.DETAIL_DESC),'')
                    OR ISNULL(RTRIM(l.USE_FLAG),'')<>ISNULL(RTRIM(v.USE_FLAG),'')
                    OR ABS(ISNULL(l.SORT_SEQ,0)-ISNULL(v.SORT_SEQ,0))>0.001)""".format(S=S, L=L, I=IN_KINDS))
diff = cur.fetchone()[0]
print("\n⑥ 검증 — 코드군 {}/{} · 상세 {}/{} · 결손 {} · 값불일치 {}".format(c_k, n_k, c_d, n_dl, miss, diff))

if c_k == n_k and c_d == n_dl and miss == 0 and diff == 0:
    nx.commit(); print("   ✅ 커밋 완료")
    WEB = ("PR003", "PR006", "PR008", "PR011", "CM701")
    cur.execute("""SELECT k.kind_code, k.kind_desc, COUNT(d.detail_code)
                     FROM {S}.code_kind k
                     LEFT JOIN {S}.code_detail d ON d.kind_code=k.kind_code
                    GROUP BY k.kind_code, k.kind_desc ORDER BY k.kind_code""".format(S=S))
    print("\n   — 이관된 코드군 —")
    for r in cur.fetchall():
        k = str(r[0]).strip()
        print("      {} {:<8s} {:<22s} {:>4}건".format(
            "★웹" if k in WEB else "  ", k, str(r[1]).strip()[:22], r[2]))
else:
    nx.rollback(); print("   ★검증 실패 — 롤백"); nx.close(); sys.exit(1)
nx.close()
