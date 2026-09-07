# -*- coding: utf-8 -*-
"""레거시 사용자 → 웹 계정 이관 (2026-09-07)

  대표 지시
    · 협력사 아이디를 **레거시처럼 회사명**으로 바꾼다
    · 협력사 69 + 일반사용자(ER) 전부 만든다 — 단, 단말/현황판 계정은 제외
    · 초기비번은 모두 **1111**(첫 로그인에 본인이 새 비번을 정한다)
    · master*·한대윤2 등 전산개발자(00 등급)는 필요 없다
    · 웹에만 있는 p2xxx 계정 46개는 그대로 둔다

  레거시 정본 = PARTNER_ERP.dbo.CM_M_USERS_INFO
    USER_ID           = 회사명(협력사) / 사람이름(직원)   ← 이게 로그인 ID
    LEVEL_CODE        = OS 외주협력사 · ER 일반사용자 · 00 전산 · SS 전산담당
    OUTSIDE_CUST_CODE = 거래처코드(협력사만, 69명 전원 보유)
    DEPT_CODE/DESC    = 부서(직원)

  이 스크립트가 하는 일
    ① 협력사(OS) — 거래처코드로 웹 계정을 찾아 **ID를 회사명으로 변경**(40건).
                    웹에 없으면 신규 생성(29건). utype='협력사', partner_code=거래처코드.
    ② 직원(ER)   — 신규 생성. 단말/현황판(1라인·4층 현황판…)은 **제외**.
                    부서명으로 역할을 추정해 넣는다(아래 _ROLE 표).
    ③ 비번        — 전부 초기비번 1111 + must_change_pw=1(첫 로그인에 본인이 변경)

  ★ID 변경은 UPDATE 다(삭제 후 재생성 아님) — 권한표(nx.app_perm 등)가 user_id 를
    참조하면 함께 옮겨야 하므로, 참조 테이블도 같이 갱신한다(아래 _REF).

  실행
    python _migration/legacy_users_import.py            # DRY-RUN(대상만 출력)
    python _migration/legacy_users_import.py --commit   # 실제 반영
"""
import sys, os, io, re, json

BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
import common, db_client                                    # noqa: E402
from routers.auth import hash_pw, INIT_PW                    # noqa: E402

COMMIT = "--commit" in sys.argv

# 사람이 아닌 계정(라인 단말·현황판 등) — 웹 로그인이 필요 없다
_SKIP = re.compile(r"(라인|현황판|모니터|단말|공용|테스트|TEST)", re.I)

# 부서명 → 역할 추정. 못 맞추면 빈 역할(로그인은 되고 화면은 권한관리에서 부여)
_ROLE = [
    ("구매", "구매/자재"), ("자재", "구매/자재"), ("물류", "구매/자재"),
    ("영업", "영업"),
    ("품질", "품질"),
    ("생산", "생산"), ("제조", "생산"), ("용접", "생산"),
    ("개발", "원가개발"), ("원가", "원가개발"),
    ("전산", "시스템관리자"),
]


def role_of(dept):
    d = str(dept or "")
    for key, role in _ROLE:
        if key in d:
            return [role]
    return []


cn = db_client.get_connection()
cur = cn.cursor()

print("=" * 78)
print(f"  레거시 사용자 이관 — {'★실제 반영(--commit)' if COMMIT else 'DRY-RUN (반영 안 함)'}")
print("=" * 78)

# ── 레거시 읽기 ──────────────────────────────────────────────
cur.execute("""SELECT RTRIM(USER_ID), RTRIM(ISNULL(USER_NAME,'')), RTRIM(ISNULL(LEVEL_CODE,'')),
                      RTRIM(ISNULL(OUTSIDE_CUST_CODE,'')), RTRIM(ISNULL(DEPT_DESC,'')),
                      RTRIM(ISNULL(CHIEF_DESC,'')), RTRIM(ISNULL(EMAIL,'')),
                      RTRIM(ISNULL(MOBILE_NO,''))
                 FROM PARTNER_ERP.dbo.CM_M_USERS_INFO
                WHERE RTRIM(ISNULL(LEVEL_CODE,'')) IN ('OS','ER')
                ORDER BY LEVEL_CODE, USER_ID""")
leg = [dict(zip(("id", "nm", "lv", "cc", "dept", "pos", "email", "tel"),
                [str(v).strip() for v in r])) for r in cur.fetchall()]

# ── 웹 현황 ──────────────────────────────────────────────────
cur.execute("SELECT user_id, ISNULL(partner_code,''), ISNULL(utype,'') FROM nx.app_user")
web_all = {}
web_by_cc = {}
for uid, pc, ut in cur.fetchall():
    uid = str(uid).strip(); pc = str(pc).strip()
    web_all[uid] = {"cc": pc, "ut": str(ut).strip()}
    if pc and str(ut).strip() == "협력사":
        web_by_cc[pc] = uid

rename, create, skip = [], [], []
for u in leg:
    if _SKIP.search(u["id"]):
        skip.append((u["id"], "단말/현황판")); continue
    if u["lv"] == "OS":
        if not u["cc"]:
            skip.append((u["id"], "거래처코드 없음")); continue
        cur_id = web_by_cc.get(u["cc"])
        if cur_id == u["id"]:
            skip.append((u["id"], "이미 같은 ID")); continue
        if cur_id:
            if u["id"] in web_all:
                skip.append((u["id"], f"새 ID가 기존계정과 충돌")); continue
            rename.append((cur_id, u)); continue
        if u["id"] in web_all:
            skip.append((u["id"], "이미 존재")); continue
        create.append(u)
    else:                                            # ER 직원
        if u["id"] in web_all:
            skip.append((u["id"], "이미 존재")); continue
        create.append(u)

print(f"\n■ ID 변경(협력사) {len(rename)}건")
print(f"  {'거래처':<7}{'현재 ID':<12}→ {'새 ID(회사명)':<20}")
for old, u in rename[:10]:
    print(f"  {u['cc']:<7}{old:<12}→ {u['id']:<20}")
if len(rename) > 10: print(f"  … 외 {len(rename)-10}건")

_os = [u for u in create if u["lv"] == "OS"]
_er = [u for u in create if u["lv"] == "ER"]
print(f"\n■ 신규 생성 {len(create)}건 (협력사 {len(_os)} · 직원 {len(_er)})")
print(f"  {'ID':<16}{'구분':<7}{'거래처/부서':<18}역할")
for u in create[:12]:
    print(f"  {u['id'][:15]:<16}{('협력사' if u['lv']=='OS' else '내부'):<7}"
          f"{(u['cc'] if u['lv']=='OS' else u['dept'])[:16]:<18}{','.join(role_of(u['dept'])) or '-'}")
if len(create) > 12: print(f"  … 외 {len(create)-12}건")

print(f"\n■ 건너뜀 {len(skip)}건")
from collections import Counter
for why, n in Counter(w for _, w in skip).most_common():
    print(f"  {n:>4}건  {why}")

if not COMMIT:
    print(f"\n※ DRY-RUN 입니다. 위 내용이 맞으면")
    print("   python _migration/legacy_users_import.py --commit  으로 반영하세요.")
    print(f"   ※초기비번은 전부 '{INIT_PW}' 이고 첫 로그인에 본인이 새 비번을 정합니다.")
    sys.exit(0)

# ── 반영 ─────────────────────────────────────────────────────
# user_id 를 참조하는 테이블 — ID 변경 시 함께 옮긴다(있는 것만)
_REF = [("nx.app_perm", "user_id"), ("nx.user_pref", "user_id")]

n_ren = n_new = 0
try:
    for old, u in rename:
        cur.execute("UPDATE nx.app_user SET user_id=?, name=?, upd_user='legacy_import', upd_dt=getdate() "
                    "WHERE user_id=?", u["id"], u["nm"] or u["id"], old)
        for tb, col in _REF:
            try:
                cur.execute(f"IF OBJECT_ID('{tb}') IS NOT NULL UPDATE {tb} SET {col}=? WHERE {col}=?",
                            u["id"], old)
            except Exception:
                pass
        n_ren += 1

    for u in create:
        is_os = (u["lv"] == "OS")
        cur.execute("""INSERT INTO nx.app_user(user_id,pw_hash,name,utype,dept,pos,roles,partner_code,
                         email,tel,status,fail_cnt,must_change_pw,upd_user,upd_dt)
                       VALUES(?,?,?,?,?,?,?,?,?,?,N'사용',0,1,'legacy_import',getdate())""",
                    u["id"], hash_pw(INIT_PW), u["nm"] or u["id"],
                    "협력사" if is_os else "내부",
                    "" if is_os else u["dept"], "" if is_os else u["pos"],
                    json.dumps(["협력사"] if is_os else role_of(u["dept"]), ensure_ascii=False),
                    u["cc"] if is_os else None,
                    u["email"], u["tel"])
        n_new += 1

    # 변경·생성 계정 전부 초기비번으로(대표 지시: 초기비번 모두 1111)
    ids = [u["id"] for _, u in rename] + [u["id"] for u in create]
    for i in range(0, len(ids), 500):
        chunk = ids[i:i+500]
        ph = ",".join("?" * len(chunk))
        cur.execute(f"""UPDATE nx.app_user
                           SET pw_hash=?, must_change_pw=1, fail_cnt=0, locked_until=NULL
                         WHERE user_id IN ({ph})""", hash_pw(INIT_PW), *chunk)

    cn.commit()
    print(f"\n✅ 반영 완료 — ID변경 {n_ren} · 신규 {n_new} · 초기비번 {len(ids)}건")
    print(f"   초기비번 '{INIT_PW}' · 첫 로그인에 본인이 새 비번을 정합니다.")
except Exception as e:
    cn.rollback()
    print("\n★실패 — 롤백했습니다:", str(e)[:250])
    raise
finally:
    cn.close()
