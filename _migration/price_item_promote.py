# -*- coding: utf-8 -*-
"""단가 마스터 승격 — nx.price_item 을 파생 조회본에서 **정본 마스터**로 (멱등).

정본 = `_schema/CUTOVER_CHECKLIST.md` "(A)안 검증"

왜
  컷오버 후 `PR_M_ITEM_COST`(미러)는 죽는다(DO_NOT_USE §18). 그런데 단가관리·단가이력 화면과
  sourcing/coopquote 의 정렬이 미러에만 있는 컬럼(MAIN_FLAG 등)에 의존한다.
  ⟹ 클린에 그 컬럼을 얹어 마스터로 승격한다.

무엇을
  ① 백업 nx.price_item_bak_promote (없을 때만)
  ② 컬럼 추가(전부 NULL 허용 = 기존 코드 무영향):
       main_flag · mkt · remarks · ins_user · ins_dt · upd_user · upd_dt
  ③ 라이브 PARTNER_ERP.dbo.PR_M_ITEM_COST 에서 백필
       조인키 = 품번 + 거래처 + 적용일 + 태그(S→TAGS · E→TAGE · 1→매입)

★안전
  - 추가만 한다. 기존 6컬럼·행·PK 는 건드리지 않는다.
  - 라이브는 **읽기만** 한다(DO_NOT_USE §5).
  - --commit 없으면 계획만 출력.

★승격 후 반드시
  `_migration/sub_norm/r_price_vendor_match.py` 를 폐기하거나 막을 것.
  그 스크립트는 `DELETE FROM nx.price_item WHERE price_type='매입'` 을 한다 —
  마스터가 된 뒤 실행되면 **웹에서 입력한 단가가 지워진다.**

사용:  python _migration/price_item_promote.py            # 계획
       python _migration/price_item_promote.py --commit   # 실행
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
import common
from common import _nx

DRY = '--commit' not in sys.argv
NEWCOLS = [("main_flag", "NVARCHAR(1)"), ("mkt", "NVARCHAR(10)"), ("remarks", "NVARCHAR(500)"),
           ("ins_user", "NVARCHAR(30)"), ("ins_dt", "DATETIME"),
           ("upd_user", "NVARCHAR(30)"), ("upd_dt", "DATETIME"),
           # ★2026-08-29 2차 — 단가관리 화면(pricemgmt)이 쓰는 나머지.
           #   mat_unit 만 실데이터가 있다(5,303행). mat/proc/other_cost 는 2·1·0 행뿐이지만
           #   화면이 입력·표시하므로 **무손실 왕복**을 위해 같이 둔다.
           #   ※ DO_NOT_USE §9 — 이 셋을 '원가분해'로 해석하는 것은 여전히 금지. 저장만 한다.
           ("mat_unit", "NVARCHAR(20)"), ("mat_cost", "FLOAT"),
           ("proc_cost", "FLOAT"), ("other_cost", "FLOAT")]

TAGMAP = "CASE p.price_type WHEN 'TAGS' THEN 'S' WHEN 'TAGE' THEN 'E' ELSE '1' END"
JOIN = f"""FROM nx.price_item p
  JOIN PARTNER_ERP.dbo.PR_M_ITEM_COST L
    ON UPPER(LTRIM(RTRIM(L.ITEM_CODE))) = UPPER(LTRIM(RTRIM(p.item_code)))
   AND LTRIM(RTRIM(ISNULL(L.CUST_CODE,''))) = LTRIM(RTRIM(ISNULL(p.vendor_code,'')))
   AND RIGHT('000000'+LTRIM(RTRIM(L.COST_APPLY_YMD)),6) = p.apply_ymd
   AND LTRIM(RTRIM(L.COST_TAG)) = {TAGMAP}"""

cn = _nx(); c = cn.cursor()
tot = c.execute("SELECT COUNT(*) FROM nx.price_item").fetchone()[0]
have = {r[0].lower() for r in c.execute("""SELECT COLUMN_NAME FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='price_item'""").fetchall()}
todo = [(n, t) for n, t in NEWCOLS if n not in have]
fill = c.execute(f"SELECT COUNT(*) {JOIN}").fetchone()[0]

print(f"nx.price_item {tot:,}행 · 추가할 컬럼 {len(todo)}개 {[n for n,_ in todo]}")
print(f"라이브 조인으로 채울 수 있는 행 {fill:,}  ({fill*100.0/tot:.2f}%)")
if DRY:
    print("DRY — 실행하려면 --commit"); cn.close(); sys.exit()

if c.execute("SELECT OBJECT_ID('nx.price_item_bak_promote','U')").fetchone()[0] is None:
    c.execute("SELECT * INTO nx.price_item_bak_promote FROM nx.price_item")
    print("백업 생성 nx.price_item_bak_promote:",
          f"{c.execute('SELECT COUNT(*) FROM nx.price_item_bak_promote').fetchone()[0]:,}행")
else:
    print("백업 유지(기존):",
          f"{c.execute('SELECT COUNT(*) FROM nx.price_item_bak_promote').fetchone()[0]:,}행")

for n, t in todo:
    c.execute(f"ALTER TABLE nx.price_item ADD {n} {t} NULL")
    print(f"   컬럼 추가 {n} {t}")

c.execute(f"""UPDATE p SET p.main_flag = LTRIM(RTRIM(ISNULL(L.MAIN_FLAG,''))),
                           p.mkt       = LTRIM(RTRIM(ISNULL(L.MKT,''))),
                           p.remarks   = LTRIM(RTRIM(ISNULL(L.REMARKS,''))),
                           p.ins_user  = LTRIM(RTRIM(ISNULL(L.INSERT_USER_ID,''))),
                           p.ins_dt    = L.INSERT_DATETIME,
                           p.upd_user  = LTRIM(RTRIM(ISNULL(L.UPDATE_USER_ID,''))),
                           p.upd_dt    = L.UPDATE_DATETIME,
                           p.mat_unit  = LTRIM(RTRIM(ISNULL(L.MAT_UNIT,''))),
                           p.mat_cost  = L.MAT_COST,
                           p.proc_cost = L.PROC_COST,
                           p.other_cost= L.OTHER_COST
              {JOIN}""")
n = c.execute("SELECT COUNT(*) FROM nx.price_item WHERE main_flag IS NOT NULL").fetchone()[0]
print(f"백필 완료 — main_flag 채워진 행 {n:,} / {tot:,}  ({n*100.0/tot:.2f}%)")
print("★다음: r_price_vendor_match.py 폐기/가드 (DELETE 로 마스터를 지운다)")
cn.close()
