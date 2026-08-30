# -*- coding: utf-8 -*-
"""★인증 1단계 A — nx.app_user / nx.app_session 신설 + 기존 계정 이관 (2026-08-29)

왜 필요한가 (PARTNER_PORTAL_DESIGN.md §1 실측)
  · 로그인이 **프론트 JavaScript 안에서** 끝난다  →  `String(u.pw)!==String(pw)`
  · `GET /api/perm/users` 가 **누구에게나 평문 비밀번호 12개를 그대로 내준다**
  · 협력사 API 는 `cust` 를 쿼리 파라미터로 받는다 → 값만 바꾸면 남의 계획이 보인다
  ⟹ 협력사에게 열기 전에 **서버가 거부**해야 한다. 화면에서 숨기는 것은 보안이 아니다.

이 스크립트가 하는 일 (A단계 · 가산적 · 기존 동작 무변경)
  ① nx.app_user     계정 **행 단위** 실테이블 (지금은 __ALL__ 한 행에 JSON 통째)
  ② nx.app_session  토큰 세션
  ③ web_user JSON → app_user 행 이관 + **평문 비밀번호를 해시로 승격**
  ④ partner **이름** → **거래처코드**(nx.cust) 로 교정
     ※ 지금 `partner:'미래정밀'` 은 이름이라 위험하다 — 동명·개명·공백에 깨진다.

★멱등: 이미 있는 계정의 비밀번호는 **건드리지 않는다**(재실행이 남의 비번을 되돌리면 안 된다).
★단일정본: 이관이 끝나면 nx.app_user 가 계정 정본이다. nx.web_user 는 은퇴 대상.
   (하드룰 — 컷오버 후 단일 테이블·폴백 금지. 두 곳에 계정이 살아 있으면 드리프트가 난다.)
"""
import io
import os
import sys
import json
import hashlib
import secrets

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
_BE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PNC_ERP_Web", "backend")
sys.path.insert(0, os.path.abspath(_BE))

from common import _nx                                    # noqa: E402

COMMIT = "--commit" in sys.argv

DDL_USER = """
IF OBJECT_ID('nx.app_user') IS NULL
CREATE TABLE nx.app_user(
    user_id      NVARCHAR(20)  NOT NULL PRIMARY KEY,
    pw_hash      NVARCHAR(220) NULL,          -- pbkdf2_sha256$iter$salt$hash (평문 금지)
    name         NVARCHAR(60)  NULL,
    utype        NVARCHAR(10)  NULL,          -- 내부 / 협력사
    dept         NVARCHAR(40)  NULL,
    pos          NVARCHAR(40)  NULL,
    roles        NVARCHAR(400) NULL,          -- JSON 배열
    partner_code NVARCHAR(20)  NULL,          -- ★거래처코드(nx.cust.cust_code) — 이름 아님
    email        NVARCHAR(120) NULL,
    tel          NVARCHAR(40)  NULL,
    status       NVARCHAR(10)  NULL,          -- 사용 / 중지
    last_login   DATETIME      NULL,
    fail_cnt     INT           NOT NULL DEFAULT 0,
    locked_until DATETIME      NULL,
    upd_user     NVARCHAR(40)  NULL,
    upd_dt       DATETIME      NULL)
"""

DDL_SESS = """
IF OBJECT_ID('nx.app_session') IS NULL
CREATE TABLE nx.app_session(
    token      NVARCHAR(64)  NOT NULL PRIMARY KEY,
    user_id    NVARCHAR(20)  NOT NULL,
    issued_at  DATETIME      NOT NULL,
    expires_at DATETIME      NOT NULL,
    last_seen  DATETIME      NULL,
    ip         NVARCHAR(45)  NULL,
    ua         NVARCHAR(300) NULL,
    revoked    BIT           NOT NULL DEFAULT 0)
"""

DDL_IDX = [
    "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_app_session_user') "
    "CREATE INDEX IX_app_session_user ON nx.app_session(user_id, revoked, expires_at)",
    "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_app_user_partner') "
    "CREATE INDEX IX_app_user_partner ON nx.app_user(partner_code)",
]

ITER = 120000


def hash_pw(pw, salt=None):
    """PBKDF2-HMAC-SHA256. 표준 라이브러리만 쓴다(새 의존성 없이 서버에 그대로 올라가야 한다)."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', str(pw).encode('utf-8'), salt.encode('utf-8'), ITER)
    return f"pbkdf2_sha256${ITER}${salt}${dk.hex()}"


def main():
    cn = _nx()
    cur = cn.cursor()
    print("=" * 62)
    print(f"  인증 1단계 A — 계정 테이블 신설·이관   ({'COMMIT' if COMMIT else 'DRY-RUN'})")
    print("=" * 62)

    # ── ① DDL ────────────────────────────────────────────────
    for name, ddl in (("nx.app_user", DDL_USER), ("nx.app_session", DDL_SESS)):
        cur.execute(f"SELECT CASE WHEN OBJECT_ID('{name}') IS NULL THEN 0 ELSE 1 END")
        before = cur.fetchone()[0]
        if COMMIT:
            cur.execute(ddl)
        print(f"  {name:<16} {'이미 있음' if before else ('생성' if COMMIT else '생성 예정')}")
    if COMMIT:
        for q in DDL_IDX:
            cur.execute(q)
        cn.commit()
        print("  인덱스 2개 확인")

    if not COMMIT:
        # DRY-RUN 은 테이블이 없을 수 있으므로 이관 계획만 보여주고 끝낸다.
        cur.execute("SELECT CASE WHEN OBJECT_ID('nx.app_user') IS NULL THEN 0 ELSE 1 END")
        if not cur.fetchone()[0]:
            print("\n  (테이블이 아직 없어 이관 계획만 계산합니다)")

    # ── ② 원본 계정 읽기 ──────────────────────────────────────
    cur.execute("SELECT udata FROM nx.web_user WHERE user_id='__ALL__'")
    r = cur.fetchone()
    users = json.loads(r[0]) if r and r[0] else []
    print(f"\n  원본 nx.web_user 계정 {len(users)}명")

    # ── ③ 거래처 이름 → 코드 (nx.cust = 클린 정본) ───────────
    cur.execute("SELECT cust_code, LTRIM(RTRIM(cust_name)) FROM nx.cust")
    by_name = {}
    for code, nm in cur.fetchall():
        by_name.setdefault(str(nm or "").strip(), []).append(str(code).strip())

    def resolve(nm):
        """이름 → 코드. **모호하면 코드를 넣지 않는다**(틀린 코드는 남의 데이터를 여는 길이다)."""
        nm = str(nm or "").strip()
        if not nm:
            return None, ""
        hit = by_name.get(nm)
        if hit and len(hit) == 1:
            return hit[0], "정확일치"
        if hit:
            return None, f"★모호({len(hit)}건: {hit})"
        cand = [c for k, v in by_name.items() if nm in k or k in nm for c in v]
        if len(set(cand)) == 1:
            return cand[0], "부분일치"
        return None, ("★모호(부분 %d건)" % len(set(cand))) if cand else "★없음"

    # ── ④ 이관 ───────────────────────────────────────────────
    exists = set()
    try:
        cur.execute("SELECT user_id FROM nx.app_user")
        exists = {str(x[0]).strip() for x in cur.fetchall()}
    except Exception:
        pass

    ins = skip = 0
    warn = []
    print(f"\n  {'계정':<10} {'유형':<6} {'거래처코드':<10} 비고")
    print("  " + "-" * 58)
    for u in users:
        uid = str(u.get("id", "")).strip()
        if not uid:
            continue
        utype = str(u.get("type", "내부")).strip() or "내부"
        pcode, how = resolve(u.get("partner"))
        if utype == "협력사" and not pcode:
            warn.append(f"{uid}: 협력사인데 거래처코드 미해석 — partner='{u.get('partner')}' {how}")
        print(f"  {uid:<10} {utype:<6} {str(pcode or '-'):<10} "
              f"{how if u.get('partner') else ''}")

        if uid in exists:
            skip += 1
            continue
        if not COMMIT:
            ins += 1
            continue
        cur.execute("""INSERT INTO nx.app_user(user_id,pw_hash,name,utype,dept,pos,roles,partner_code,
                                               email,tel,status,fail_cnt,upd_user,upd_dt)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,0,'auth_bootstrap',getdate())""",
                    uid, hash_pw(u.get("pw", "")), str(u.get("nm", "")).strip(), utype,
                    str(u.get("dept", "")).strip(), str(u.get("pos", "")).strip(),
                    json.dumps(u.get("roles") or [], ensure_ascii=False), pcode,
                    str(u.get("email", "")).strip(), str(u.get("tel", "")).strip(),
                    str(u.get("status", "사용")).strip() or "사용")
        ins += 1

    if COMMIT:
        cn.commit()

    print("\n  " + "-" * 58)
    print(f"  신규 {ins}명 · 기존유지 {skip}명 (기존 계정의 비밀번호는 건드리지 않음)")
    if warn:
        print("\n  ★확인 필요")
        for w in warn:
            print("   ", w)

    # ── ⑤ 검증 ───────────────────────────────────────────────
    if COMMIT:
        print("\n  === 검증 ===")
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN pw_hash LIKE 'pbkdf2_sha256$%' THEN 1 ELSE 0 END) FROM nx.app_user")
        n, h = cur.fetchone()
        print(f"   app_user {n}명 · 해시저장 {h}명 ⟹ {'PASS 평문 0' if n == h else '★평문 잔존'}")
        cur.execute("""SELECT COUNT(*) FROM nx.app_user
                        WHERE utype='협력사' AND (partner_code IS NULL OR partner_code='')""")
        bad = cur.fetchone()[0]
        print(f"   거래처코드 없는 협력사 {bad}명 ⟹ {'PASS' if bad == 0 else '★확인'}")
        cur.execute("""SELECT a.user_id, a.partner_code FROM nx.app_user a
                        WHERE a.utype='협력사' AND a.partner_code IS NOT NULL
                          AND NOT EXISTS(SELECT 1 FROM nx.cust c WHERE c.cust_code=a.partner_code)""")
        orph = cur.fetchall()
        print(f"   거래처에 없는 코드 {len(orph)}건 ⟹ {'PASS' if not orph else orph}")
        # 해시 왕복 — 저장한 비밀번호로 실제 로그인이 되는지
        cur.execute("SELECT TOP 1 user_id, pw_hash FROM nx.app_user WHERE user_id='super'")
        rr = cur.fetchone()
        if rr:
            _, it, salt, _ = str(rr[1]).split("$")
            ok = hash_pw("super", salt) == rr[1]
            print(f"   해시 왕복(super) ⟹ {'PASS 검증 가능' if ok else '★FAIL'}")
    cn.close()
    print("\n  " + ("완료" if COMMIT else "DRY-RUN — 반영하려면 --commit"))


if __name__ == "__main__":
    main()
