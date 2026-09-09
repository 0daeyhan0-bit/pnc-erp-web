# -*- coding: utf-8 -*-
"""가공창고 이동계획 SP — 미러 참조를 클린으로 교체 (nx.SP_PR_가공창고_이동계획_WEBPLAN)

  ★목적 (CLAUDE.md §1-9-1 클린 단일화)
    580 화면 조회엔진인 우리 SP 안의 레거시 미러 직독을 클린 테이블로 바꾼다.
    컷오버로 레거시가 은퇴하면 미러는 **얼어붙은 옛 값**이 되므로 지금 클린으로 짠다.

  ★교체 대상 (실측 2026-09-08, DB 실물 1,238줄 기준)
    ① PR_M_ITEM_PROC_GAGONG  5곳 → nx.prodinfo_proc
       (적재 완료 = _migration/prodinfo_proc_seed.py, 9,904행/4,190품번, 전수 대조 100% 일치)
       컬럼: GAGONG_PROC_CODE→gagong_proc_code · ITEM_CODE→item_code · PROC_SEQ→proc_seq
    ② PR_M_ITEM              12곳 → nx.item
       SP 가 읽는 컬럼 6개 중 5개가 1:1 대응(불일치 0.00%):
         ITEM_CODE→item_code · IN_CUST_CODE→in_cust · ITEM_CLASS→item_class
         WORK_CODE→work_code · SAGUB_STOCK_FLAG→sagub_stock_flag
       ★GC_GUBUN 만 nx.item 에 없다 — 그런데 **미러 24,154행 전부 빈값**이고
         SP 는 임시표에 넘기기만 한다(1333행은 'Q' 하드코딩). → '' 로 대체 = 값 동일.
    ③ CM_M_CUST               1곳 → nx.cust   (CUST_DESC→cust_name, 361행 불일치 0.00%)

  ★교체하지 않는 것(이유 명시)
    · PR_M_PROC_GAGONG  5곳 — 클린 대응 미존재(웹이 이 테이블에 직접 CRUD, partmaster.py). 별도 과제.
    · PR_M_ITEM_BOM     4곳 — nx.bom_line 에 유효한 (부모,자재) 5,125쌍 결손. 적재 전 교체 시 소요가 줄어든다.
    · PR_M_ITEM_SUB       — 미러 71,043 vs 클린 14,466(56,577품번 결손).
    · PR_M_WORK · CM_M_MASTER_DETAIL — 코드성 마스터, 클린 미존재.
    · 재고 4종(pu/pr_t_mat_stock_wh·sa_t_item_stock·PU_T_SAGUB_STOCK)
      — 이관대상(그대로) A구분. 이미 실시간 잔액을 읽고 있어 교체 불요.

  ★안전장치
    · 기본 DRY-RUN. 실제 반영은 --commit
    · 교체 전 원본 SP 본문을 파일로 백업(_migration/bk_sp_move580_<타임스탬프>.sql)
    · 치환은 **정규식 단어경계**로 — PR_M_ITEM 이 PR_M_ITEM_BOM/_SUB/_PROC_GAGONG 를 건드리지 않게 (?!_) 사용
    · 치환 건수를 대상수와 대조해 다르면 중단
    · 쓰기는 nx 만(§1). 라이브 무변경.
"""
import sys, os, io, re
from datetime import datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
MIG = r"c:\Users\박근민\Desktop\NEW_ERP_1\_migration"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
TAG = datetime.now().strftime("%y%m%d_%H%M")
SPNM = "SP_PR_가공창고_이동계획_WEBPLAN"

cn = _nx(); cur = cn.cursor()
cur.execute("""SELECT OBJECT_DEFINITION(object_id) FROM sys.objects
                WHERE type='P' AND name=? AND SCHEMA_NAME(schema_id)='nx'""", SPNM)
row = cur.fetchone()
if not row or not row[0]:
    print("★SP 본문을 읽을 수 없습니다(이름 불일치 또는 암호화)"); sys.exit(1)
body = row[0]

print("=" * 100)
print(" 580 SP 미러→클린 교체    모드: {}".format("★COMMIT" if COMMIT else "DRY-RUN"))
print("=" * 100)
print("   원본 {:,}자 / {:,}줄".format(len(body), body.count("\n") + 1))

new = body
plan = []

# ── ① PR_M_ITEM_PROC_GAGONG → nx.prodinfo_proc (컬럼도 소문자 대응) ──
n1 = len(re.findall(r"\bPR_M_ITEM_PROC_GAGONG\b", new, re.I))
new = re.sub(r"\bPR_M_ITEM_PROC_GAGONG\b", "nx.prodinfo_proc", new, flags=re.I)
plan.append(("PR_M_ITEM_PROC_GAGONG → nx.prodinfo_proc", n1, 5))

# ── ② PR_M_ITEM(단독) → nx.item ──
#    (?!_) 로 _BOM/_SUB/_PROC_GAGONG/_COST 등을 제외. 이미 ①에서 치환됐으므로 잔여는 단독뿐.
n2 = len(re.findall(r"\bPR_M_ITEM\b(?!_)", new, re.I))
new = re.sub(r"\bPR_M_ITEM\b(?!_)", "nx.item", new, flags=re.I)
plan.append(("PR_M_ITEM → nx.item", n2, 12))

# ── ③ CM_M_CUST → nx.cust ──
n3 = len(re.findall(r"\bCM_M_CUST\b(?!_)", new, re.I))
new = re.sub(r"\bCM_M_CUST\b(?!_)", "nx.cust", new, flags=re.I)
plan.append(("CM_M_CUST → nx.cust", n3, 1))

# ── 컬럼 매핑 (클린은 소문자·이름이 다른 것만) ──
COLMAP = [
    # nx.item 별칭(am/m/b)이 읽는 컬럼
    (r"\b(am|m|b)\.ITEM_DESC\b", r"\1.item_name", "ITEM_DESC→item_name"),
    (r"\b(am|m|b)\.IN_CUST_CODE\b", r"\1.in_cust", "IN_CUST_CODE→in_cust"),
    (r"\b(am|m|b)\.GC_GUBUN\b", r"''", "GC_GUBUN→''(전량 빈값)"),
    # nx.cust
    (r"\bCUST_DESC\s+FROM\s+nx\.cust\b", "cust_name FROM nx.cust", "CUST_DESC→cust_name"),
]
for pat, rep, lbl in COLMAP:
    c = len(re.findall(pat, new, re.I))
    if c:
        new = re.sub(pat, rep, new, flags=re.I)
    plan.append(("  " + lbl, c, None))

print("\n   {:<46s} {:>6s} {:>8s}".format("치환", "건수", "예상"))
bad = False
for lbl, got, exp in plan:
    mark = ""
    if exp is not None:
        mark = "✅" if got == exp else "★불일치"
        if got != exp: bad = True
    print("   {:<46s} {:>6} {:>8} {}".format(lbl, got, exp if exp is not None else "-", mark))

# 잔존 미러 확인
print("\n   [교체 후 SP 에 남는 미러]")
for t in ("PR_M_PROC_GAGONG", "PR_M_ITEM_BOM", "PR_M_ITEM_SUB", "PR_M_WORK",
          "CM_M_MASTER_DETAIL", "sa_t_sale_dtl", "PU_T_SAGUB_STOCK"):
    c = len(re.findall(r"\b" + t + r"\b", new, re.I))
    if c: print("      {:<26s} {:>3}곳  (의도적 유지)".format(t, c))

if bad:
    print("\n   ★치환 건수가 예상과 다릅니다 — 중단합니다.")
    sys.exit(1)

# ALTER 문 생성
alter = re.sub(r"^\s*CREATE\s+PROC(EDURE)?\b", "ALTER PROCEDURE", new, count=1, flags=re.I)
if not re.match(r"^\s*ALTER\s+PROCEDURE\b", alter, re.I):
    print("\n   ★CREATE PROCEDURE 머리말을 찾지 못했습니다 — 중단합니다.")
    print("   머리 120자: {!r}".format(new[:120]))
    sys.exit(1)

bkp = os.path.join(MIG, "bk_sp_move580_{}.sql".format(TAG))
newp = os.path.join(MIG, "sp_move580_clean_{}.sql".format(TAG))

if not COMMIT:
    open(bkp, "w", encoding="utf-8").write(body)
    open(newp, "w", encoding="utf-8").write(alter)
    print("""
   [파일 저장]
     원본 백업 : {}
     교체본    : {}

   ⟹ 실제 반영하려면  --commit""".format(bkp, newp))
    cur.close(); cn.close(); sys.exit(0)

print("\n" + "=" * 100)
print(" 실행")
print("=" * 100)
open(bkp, "w", encoding="utf-8").write(body)
open(newp, "w", encoding="utf-8").write(alter)
print("   ① 백업 {}".format(bkp))
try:
    cur.execute(alter)
    cn.commit()
    print("   ② ALTER PROCEDURE 적용 ✅")
except Exception as e:
    cn.rollback()
    print("   ★오류 rollback: {}".format(str(e)[:400]))
    cur.close(); cn.close(); sys.exit(1)

cur.execute("""SELECT OBJECT_DEFINITION(object_id), CONVERT(varchar(19),modify_date,120)
                FROM sys.objects WHERE type='P' AND name=? AND SCHEMA_NAME(schema_id)='nx'""", SPNM)
r = cur.fetchone()
print("\n   적용 확인: {:,}자 · 수정일 {}".format(len(r[0] or ""), r[1]))
for t in ("PR_M_ITEM_PROC_GAGONG", "CM_M_CUST"):
    print("      {:<26s} 잔존 {}곳".format(t, len(re.findall(r"\b" + t + r"\b", r[0], re.I))))
print("      {:<26s} 잔존 {}곳".format("PR_M_ITEM(단독)",
      len(re.findall(r"\bPR_M_ITEM\b(?!_)", r[0], re.I))))
print("\n   ※롤백: {} 파일 내용을 ALTER 로 재적용".format(bkp))
cur.close(); cn.close()
