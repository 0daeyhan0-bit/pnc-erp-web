# -*- coding: utf-8 -*-
"""협력사 미로그인 계정 초기비번 세팅 (2026-09-07 대표확정)

  대상 = utype='협력사' AND last_login IS NULL      ← 한 번도 로그인한 적 없는 계정
  동작 = pw_hash = hash_pw('1111') · must_change_pw = 1 · fail_cnt = 0 · locked_until = NULL
  제외 = last_login 이 있는 계정은 **손대지 않는다**(이미 쓰고 있다)

  ★DRY-RUN 이 기본이다. 실제 반영은 --commit 을 붙여야 한다
    (_migration/auth_bootstrap.py 와 같은 규약).

  실행
    python _migration/coop_initpw.py             # 대상만 보여준다
    python _migration/coop_initpw.py --commit    # 실제 반영
"""
import sys, os, io

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client                     # noqa: E402
from routers import auth as A                # noqa: E402

COMMIT = "--commit" in sys.argv
INIT = A.INIT_PW

cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  협력사 초기비번 세팅 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print(f"  초기비번 = {INIT}")
print("=" * 78)

A._ensure_user_cols(cur)
if COMMIT:
    cn.commit()

SEL = """SELECT user_id, ISNULL(name,''), ISNULL(partner_code,''), ISNULL(status,'')
           FROM nx.app_user
          WHERE utype=N'협력사' AND last_login IS NULL
          ORDER BY user_id"""
cur.execute(SEL)
rows = cur.fetchall()

cur.execute("""SELECT COUNT(*) FROM nx.app_user WHERE utype=N'협력사'""")
tot = cur.fetchone()[0]
cur.execute("""SELECT COUNT(*) FROM nx.app_user WHERE utype=N'협력사' AND last_login IS NOT NULL""")
used = cur.fetchone()[0]

print(f"\n협력사 전체 {tot}개 · 로그인 이력 있음 {used}개(제외) · **대상 {len(rows)}개**\n")
for i, r in enumerate(rows, 1):
    print(f"  {i:>3}. {str(r[0]).strip():<12} {str(r[1]).strip():<20} 거래처={str(r[2]).strip():<8} {str(r[3]).strip()}")

if not rows:
    print("\n대상이 없습니다.")
    sys.exit(0)

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 {len(rows)}개가 맞는지 확인한 뒤")
    print("   python _migration/coop_initpw.py --commit  로 반영하세요.")
    sys.exit(0)

n = 0
try:
    for r in rows:
        uid = str(r[0]).strip()
        cur.execute("""UPDATE nx.app_user
                          SET pw_hash=?, must_change_pw=1, fail_cnt=0, locked_until=NULL,
                              upd_user=N'coop_initpw', upd_dt=GETDATE()
                        WHERE user_id=?""", A.hash_pw(INIT), uid)
        n += cur.rowcount
    # 그 계정들의 기존 세션은 끊는다(비번이 바뀌었으므로)
    cur.execute("""UPDATE s SET revoked=1
                     FROM nx.app_session s
                     JOIN nx.app_user u ON u.user_id=s.user_id
                    WHERE u.utype=N'협력사' AND u.must_change_pw=1""")
    cn.commit()
    print(f"\n✅ 반영 완료 — {n}개 계정")
    print(f"   안내문: \"아이디 / 초기비번 {INIT} → 접속하면 새 비밀번호를 정하게 됩니다\"")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:200])
    raise
finally:
    cn.close()
