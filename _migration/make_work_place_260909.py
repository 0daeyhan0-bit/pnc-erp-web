# -*- coding: utf-8 -*-
"""작업처 마스터 클린 신설 — nx.work_place (2026-09-09)

★무엇을 — 작업처(P1 용접 / P2 가공)를 담을 클린 마스터를 만들고 미러에서 씨딩한다.

★왜 — 지금 작업처가 **네 곳에 흩어져** 있다:
     ① nx.PR_M_WORK            미러 테이블 (39컬럼인데 실제 쓰는 건 WORK_DESC 하나)
     ② common.py _ITEM_WORK    백엔드 상수
     ③ core.js QC_WORK         프론트 상수
     ④ screens.base.js:720     파트마스터 신규팝업 **하드코드**(<option value="P1">용접</option>)
   미러는 컷오버에 얼어붙고, 하드코드는 작업처를 추가할 때 코드를 고쳐야 한다.
   ⟹ 클린 한 곳으로 모으고, 화면은 API 로 읽는다.

★용도 (대표 확인 2026-09-09)
   레거시에서 PR_M_WORK 는 **파트마스터의 작업처 구분 + 생산공정 연계** 용도다.
   화면 두 곳이 이 값을 드롭다운으로 쓴다 — 파트 마스터 · 생산공정순서(생산정보등록).

★D1(직납)은 여기 넣지 않는다
   직납은 작업처가 아니라 **판정 결과**다 — 모델BOM P/NO 가 작업처 대신 업체를 가지면 직납.
   코드도 그렇게 판정한다(coopplan.py:375 `in_cust==cust and not work_code`).
   `_ITEM_WORK` 의 'D1':'직납' 은 표시용 라벨일 뿐 work_code 에 D1 이 들어가는 곳은 없다.

★안전 — 미러는 읽기만. 새 테이블 생성 + 씨딩. 기존 테이블 무변경.
사용: python _migration\\make_work_place_260909.py [--apply]
"""
import sys, os, io

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

S = "PARTNER_ERP_TEST3.nx"
APPLY = "--apply" in sys.argv

nx = _nx(); nx.autocommit = False
cur = nx.cursor()

print("=" * 96)
print(" 작업처 마스터 클린 신설 — nx.work_place")
print(" 모드: {}".format("★실제 생성(--apply)" if APPLY else "조회만(dry-run)"))
print("=" * 96)

# ── 미러 현황 ───────────────────────────────────────────────────
cur.execute("""SELECT WORK_CODE, ISNULL(PROC_CODE,''), ISNULL(WORK_DESC,''),
                      ISNULL(IN_CUST_CODE,''), ISNULL(PROD_RATE,0)
                 FROM {S}.PR_M_WORK WITH(NOLOCK) ORDER BY WORK_CODE""".format(S=S))
src = [tuple(x) for x in cur.fetchall()]
print("\n① 미러 nx.PR_M_WORK — {}행".format(len(src)))
for r in src:
    print("   {:<4s} proc={:<3s} {:<8s} cust={:<8s} rate={}".format(
        str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip(), str(r[3]).strip(), r[4]))

# ── 이미 있나 ───────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='work_place'""")
exists = cur.fetchone()[0]
print("\n② nx.work_place — {}".format("★이미 존재" if exists else "없음(신설 대상)"))
if exists:
    cur.execute("SELECT COUNT(*) FROM {S}.work_place".format(S=S))
    print("   현재 {}행".format(cur.fetchone()[0]))

print("""
③ 만들 구조
   work_code   varchar(10)  PK   작업처 코드 (P1·P2)
   work_desc   nvarchar(50)      작업처명 (용접·가공)
   proc_code   varchar(10)       공정구분 (A·P) — 레거시 PROC_CODE
   sort_seq    int               정렬순서
   use_yn      varchar(1)        사용여부 ('1'=사용)
   remarks     nvarchar(200)
   upd_user / upd_dt
   ※PROD_RATE 등 미러의 나머지 33컬럼은 **쓰는 곳이 없어** 옮기지 않는다(실측 확인).""")

if not APPLY:
    print("\n   ※dry-run — 생성하려면 --apply")
    nx.rollback(); nx.close(); sys.exit(0)

# ── 생성 ───────────────────────────────────────────────────────
cur.execute("""IF OBJECT_ID('nx.work_place','U') IS NULL
CREATE TABLE nx.work_place(
    work_code  varchar(10)  NOT NULL PRIMARY KEY,
    work_desc  nvarchar(50) NULL,
    proc_code  varchar(10)  NULL,
    sort_seq   int          NULL,
    use_yn     varchar(1)   NULL DEFAULT '1',
    remarks    nvarchar(200) NULL,
    upd_user   nvarchar(40) NULL,
    upd_dt     datetime     NULL
)""")
print("\n④ 테이블 확보")

# ── 씨딩(멱등) ─────────────────────────────────────────────────
n_ins = n_upd = 0
for i, r in enumerate(src, 1):
    code = str(r[0]).strip()
    cur.execute("SELECT COUNT(*) FROM {S}.work_place WHERE work_code=?".format(S=S), code)
    if cur.fetchone()[0]:
        cur.execute("""UPDATE {S}.work_place SET work_desc=?, proc_code=?, sort_seq=?,
                          upd_user='SEED260909', upd_dt=GETDATE() WHERE work_code=?""".format(S=S),
                    str(r[2]).strip(), str(r[1]).strip(), i, code)
        n_upd += 1
    else:
        cur.execute("""INSERT INTO {S}.work_place(work_code,work_desc,proc_code,sort_seq,use_yn,upd_user,upd_dt)
                       VALUES(?,?,?,?,'1','SEED260909',GETDATE())""".format(S=S),
                    code, str(r[2]).strip(), str(r[1]).strip(), i)
        n_ins += 1
print("   씨딩 — 신규 {} · 갱신 {}".format(n_ins, n_upd))

# ── 호환 뷰(미러 모양) ─────────────────────────────────────────
#   코드 28곳이 nx.PR_M_WORK 를 WORK_CODE/WORK_DESC 로 JOIN 한다.
#   뷰를 두면 테이블명만 바꿔 전환할 수 있다(달력과 같은 방식).
cur.execute("IF OBJECT_ID('nx.v_work_place','V') IS NOT NULL DROP VIEW nx.v_work_place")
cur.execute("""CREATE VIEW nx.v_work_place AS
SELECT work_code                    AS WORK_CODE,
       work_desc                    AS WORK_DESC,
       proc_code                    AS PROC_CODE,
       sort_seq                     AS SORT_SEQ,
       use_yn                       AS USE_YN,
       upd_user                     AS UPDATE_USER_ID,
       upd_dt                       AS UPDATE_DATETIME
  FROM nx.work_place""")
print("   호환뷰 nx.v_work_place 생성 (PR_M_WORK 모양)")

# ── 검증 ───────────────────────────────────────────────────────
cur.execute("""SELECT COUNT(*) FROM {S}.PR_M_WORK m
                 JOIN {S}.v_work_place v ON v.WORK_CODE=m.WORK_CODE
                WHERE ISNULL(RTRIM(m.WORK_DESC),'')<>ISNULL(RTRIM(v.WORK_DESC),'')""".format(S=S))
d = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.PR_M_WORK".format(S=S)); a = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM {S}.v_work_place".format(S=S)); b = cur.fetchone()[0]
print("\n⑤ 검증 — 미러 {}행 · 뷰 {}행 · 이름 불일치 {}".format(a, b, d))

if a == b and d == 0:
    nx.commit()
    print("   ✅ 커밋 완료")
    cur.execute("SELECT work_code, work_desc, proc_code, sort_seq FROM {S}.work_place ORDER BY sort_seq".format(S=S))
    print("\n   nx.work_place:")
    for r in cur.fetchall():
        print("      {} | {} | proc={} | seq={}".format(
            str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip(), r[3]))
    print("""
   다음 단계
     ① prodinfo.py:286  nx.PR_M_WORK → nx.v_work_place  (생산공정순서 드롭다운)
     ② 파트마스터 신규팝업 하드코드 → /api/prodinfo/opts 의 works 사용
     ③ 나머지 JOIN 26곳 → nx.v_work_place
     ④ 화면에 작업처 등록·수정 (기준 마스터 관리 탭)""")
else:
    nx.rollback()
    print("   ★검증 실패 — 롤백")
    nx.close(); sys.exit(1)
nx.close()
