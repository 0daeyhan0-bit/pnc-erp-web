# -*- coding: utf-8 -*-
"""거래처 클린(nx.cust) 결손 보정 — 이관(7/23) 이후 라이브에서 바뀐 담당자 (2026-09-09)

■ 왜
  nx.cust 는 2026-07-23 17:54 MIGRATION 이후 갱신을 받지 않았다.
  그 사이 라이브 CM_M_CUST 에서 16건이 수정됐고, 그 중 **CHARGE_USER_ID 2건**이
  실제로 어긋나 있다.

     2135 부산교역          클린 우윤택  ←  라이브 조재훈 (2026-08-31 우윤택 수정)
     2352 (주)에이티엠코리아  클린 (빈값)  ←  라이브 우윤택 (2026-09-02 우윤택 수정)

  CHARGE_USER_ID 는 구매담당자 필터(manorder.py:18/64/71)와 마감 담당자 표시
  (purmagam.py:45 · salemagam.py:79)에 쓰인다. 그대로 두고 뷰로 전환하면
  부산교역이 엉뚱한 담당자로 잡힌다.

■ 왜 이 2건뿐인가 (실측 2026-09-09, 361건 전수)
     CUST_DESC·CUST_TYPE·CHARGE_NAME·USE/IN/OUT/OUTSIDE_FLAG
     ·GC_GUBUN·BUSINESS_NO·PHONE_NO·DLVY_DAY(2)·BANK_CODE   전부 불일치 0
     OWNER_NAME 38건 = 앞쪽 공백 제거(' 김원일'→'김원일') = 정규화, 결손 아님
     플래그 ''→'0' 정규화도 마찬가지

■ 안전
  · 쓰기 대상 = nx.cust (§1-1 준수). 라이브는 읽기만.
  · 근거키 스코프 = cust_code 2건 지정. 대량 UPDATE 아님.
  · --commit 없으면 조회만 하고 끝난다.
"""
import sys, os, io, argparse
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

ap = argparse.ArgumentParser()
ap.add_argument("--commit", action="store_true", help="실제 반영")
A = ap.parse_args()

nx = _nx(); cur = nx.cursor()

# ── 대상 산출: 라이브와 CHARGE_USER_ID 가 다른 것 전부 (2건으로 한정하지 않고 재산출)
cur.execute("""SELECT RTRIM(c.cust_code), RTRIM(ISNULL(c.cust_name,'')),
                      RTRIM(ISNULL(c.charge_user_id,'')), RTRIM(ISNULL(l.CHARGE_USER_ID,'')),
                      l.UPDATE_DATETIME
                 FROM nx.cust c
                 JOIN PARTNER_ERP.dbo.CM_M_CUST l ON RTRIM(c.cust_code)=RTRIM(l.CUST_CODE)
                WHERE RTRIM(ISNULL(c.charge_user_id,'')) <> RTRIM(ISNULL(l.CHARGE_USER_ID,''))
                ORDER BY c.cust_code""")
rows = cur.fetchall()

print("=" * 96)
print(" 보정 대상 — nx.cust.charge_user_id")
print("=" * 96)
if not rows:
    print("   대상 없음 — 이미 정합")
    nx.close(); sys.exit(0)
print("   {:<8s} {:<22s} {:<12s} {:<12s} {}".format("코드", "거래처명", "클린(현재)", "라이브(정답)", "라이브 수정시각"))
for a, b, c, d, e in rows:
    print("   {:<8s} {:<22s} {:<12s} {:<12s} {}".format(a, b[:22], c or "(빈값)", d or "(빈값)", str(e)[:19]))
print("\n   {}건".format(len(rows)))

if not A.commit:
    print("\n   [DRY-RUN] --commit 을 붙이면 반영한다.")
    nx.close(); sys.exit(0)

# ── 백업 (근거키 스코프)
cur.execute("""IF OBJECT_ID('nx.bk_cust_charge_260909') IS NOT NULL DROP TABLE nx.bk_cust_charge_260909""")
cur.execute("""SELECT cust_code, cust_name, charge_user_id, upd_user, upd_dt
                 INTO nx.bk_cust_charge_260909 FROM nx.cust
                WHERE RTRIM(cust_code) IN ({})""".format(
    ",".join("'" + str(r[0]) + "'" for r in rows)))
nx.commit()
print("\n   백업 nx.bk_cust_charge_260909 — {}행".format(len(rows)))

n = 0
for code, name, old, new, _ in rows:
    cur.execute("""UPDATE nx.cust SET charge_user_id=?, upd_user='SYNC_260909', upd_dt=getdate()
                    WHERE RTRIM(cust_code)=?""", (new or None), code)
    n += cur.rowcount
nx.commit()
print("   반영 {}행".format(n))

# ── 재검증
cur.execute("""SELECT COUNT(*) FROM nx.v_cm_m_cust v
                 JOIN PARTNER_ERP.dbo.CM_M_CUST l ON RTRIM(v.CUST_CODE)=RTRIM(l.CUST_CODE)
                WHERE RTRIM(ISNULL(v.CHARGE_USER_ID,'')) <> RTRIM(ISNULL(l.CHARGE_USER_ID,''))""")
left = cur.fetchone()[0]
print("\n   재검증 — 뷰 vs 라이브 CHARGE_USER_ID 불일치 {}건 {}".format(left, "✔" if left == 0 else "★"))
nx.close()
