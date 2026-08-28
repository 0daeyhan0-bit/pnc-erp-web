# -*- coding: utf-8 -*-
"""단가 델타 동기화 — 레거시 `PR_M_ITEM_COST` → 정본 `nx.price_item`.

정본 = `_schema/CUTOVER_CHECKLIST.md` "단가 이관"

왜
  단가 마스터를 `nx.price_item` 으로 승격(2026-08-29)했지만 컷오버 전까지는 레거시에서도
  단가를 입력한다. **신규 등록분과 수정분**을 정본으로 끌어온다.
  컷오버 밤에 마지막으로 한 번 더 돌리고 레거시 단가화면을 막으면 갈림이 없다.

★안전 원칙
  1. **DELETE 하지 않는다.** 웹에서만 있는 행(업로드 사급가 `vendor_code='LG'` 등)은
     레거시에 없으므로 **손대지 않는다**. 키가 양쪽에 다 있는 행만 UPDATE 대상이다.
     (`r_price_vendor_match.py` 는 DELETE 를 해서 실행 거부 가드를 걸어 뒀다.)
  2. `nx.item` 에 없는 품번은 건너뛴다(조회가 안 되는 단가라 의미 없음). 건수는 보고한다.
  3. `--commit` 없으면 계획만 출력한다.

★성능
  크로스 DB `NOT EXISTS` 로 13만×13만을 돌리면 10분이 넘는다(실측).
  ⟹ 양쪽을 **한 번씩 통째로 읽어 파이썬 dict 로 비교**한다(수 초).

키 = (품번, 거래처, 구분, 적용일)  ·  구분 매핑 S→TAGS · E→TAGE · 1→매입

사용
  python _migration/price_item_delta_sync.py            # DRY
  python _migration/price_item_delta_sync.py --commit   # 실행
"""
import io, sys, os, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

DRY = '--commit' not in sys.argv
TAG2PT = {'S': 'TAGS', 'E': 'TAGE', '1': '매입'}


def k(item, vendor, pt, ymd):
    return (str(item or '').strip().upper(), str(vendor or '').strip(), pt, str(ymd or '').strip())


cn = _nx(); c = cn.cursor()
t0 = time.time()

print("=== 양쪽 읽기 ===")
c.execute("""SELECT LTRIM(RTRIM(ITEM_CODE)), LTRIM(RTRIM(ISNULL(CUST_CODE,''))), LTRIM(RTRIM(COST_TAG)),
                    RIGHT('000000'+LTRIM(RTRIM(COST_APPLY_YMD)),6),
                    CAST(ISNULL(ITEM_COST,0) AS float), ISNULL(NULLIF(LTRIM(RTRIM(CURRENCY)),''),'KRW'),
                    LTRIM(RTRIM(ISNULL(MAIN_FLAG,''))), LTRIM(RTRIM(ISNULL(MKT,''))),
                    LTRIM(RTRIM(ISNULL(REMARKS,''))), LTRIM(RTRIM(ISNULL(INSERT_USER_ID,''))), INSERT_DATETIME,
                    LTRIM(RTRIM(ISNULL(UPDATE_USER_ID,''))), UPDATE_DATETIME,
                    LTRIM(RTRIM(ISNULL(MAT_UNIT,''))), MAT_COST, PROC_COST, OTHER_COST
               FROM PARTNER_ERP.dbo.PR_M_ITEM_COST""")
L = {}
for r in c.fetchall():
    pt = TAG2PT.get(r[2], '매입')
    L[k(r[0], r[1], pt, r[3])] = r
print(f"   레거시 {len(L):,}행")

c.execute("SELECT item_code, ISNULL(vendor_code,''), price_type, apply_ymd, CAST(ISNULL(price,0) AS float) FROM nx.price_item")
P = {}
for r in c.fetchall():
    P[k(r[0], r[1], r[2], r[3])] = float(r[4])
print(f"   정본   {len(P):,}행   ({time.time()-t0:.1f}초)")

c.execute("SELECT UPPER(LTRIM(RTRIM(item_code))) FROM nx.item")
ITEMS = {r[0] for r in c.fetchall()}

new = [key for key in L if key not in P]
new_ok = [key for key in new if key[0] in ITEMS]
new_skip = len(new) - len(new_ok)
upd = [key for key in L if key in P and abs(float(L[key][4]) - P[key]) > 0.001]
webonly = [key for key in P if key not in L]

print(f"\n=== 델타 ===")
print(f"   ① 신규(레거시에만)      {len(new):,}행 → 넣을 것 **{len(new_ok):,}** · 품목마스터 없어 스킵 {new_skip:,}")
print(f"   ② 수정(값 다름)         **{len(upd):,}행**")
print(f"   ③ 웹 전용(레거시에 없음) {len(webonly):,}행 — **손대지 않음**")

for key in sorted(new_ok, key=lambda x: x[3], reverse=True)[:6]:
    r = L[key]
    print(f"      +신규 {key[0]:<20} {key[1]:<6} {key[2]:<5} {key[3]}  {float(r[4]):>12,.2f}")
for key in sorted(upd, key=lambda x: x[3], reverse=True)[:6]:
    print(f"      ~수정 {key[0]:<20} {key[1]:<6} {key[2]:<5} {key[3]}  정본 {P[key]:>10,.2f} → 레거시 {float(L[key][4]):>10,.2f}")

if DRY:
    print("\nDRY — 실행하려면 --commit")
    cn.close(); sys.exit()

print("\n=== 실행 ===")
INS = """INSERT INTO nx.price_item(item_code, price_type, vendor_code, currency, apply_ymd, price,
     main_flag, mkt, remarks, ins_user, ins_dt, upd_user, upd_dt, mat_unit, mat_cost, proc_cost, other_cost)
     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
n = 0
for key in new_ok:
    r = L[key]
    c.execute(INS, r[0], key[2], key[1], r[5], key[3], float(r[4]),
              r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15], r[16])
    n += 1
print(f"   신규 {n:,}행 INSERT")

UPD = """UPDATE nx.price_item SET price=?, currency=?, main_flag=?, mkt=?, remarks=?,
          upd_user=?, upd_dt=?, mat_unit=?, mat_cost=?, proc_cost=?, other_cost=?
        WHERE item_code=? AND vendor_code=? AND price_type=? AND apply_ymd=?"""
m = 0
for key in upd:
    r = L[key]
    c.execute(UPD, float(r[4]), r[5], r[6], r[7], r[8], r[11], r[12], r[13], r[14], r[15], r[16],
              r[0], key[1], key[2], key[3])
    m += 1
print(f"   수정 {m:,}행 UPDATE")

tot = c.execute("SELECT COUNT(*) FROM nx.price_item").fetchone()[0]
lg = c.execute("SELECT COUNT(*) FROM nx.price_item WHERE vendor_code='LG'").fetchone()[0]
print(f"   정본 {tot:,}행 · 업로드 사급가(vendor='LG') {lg:,}행 보존 확인")
cn.close()
