# -*- coding: utf-8 -*-
"""OSP 사급실적 업로드 검증 — 최소 5건 이상 (2026-08-31 · 대표 지시)

검증 대상
  ① 식별컬럼 7개(ps_order·line_code·line_name·assembly·gi_type·uit·market) 적재
  ② 사업부 미지정 차단
  ③ 사업부 오선택 차단(양방향)
  ④ 정상 업로드 통과
  ⑤ 멱등성 — 같은 파일 재업로드 시 행수·금액 불변
  ⑥ 판정 불가 파일은 막지 않음(신규 품목 보호)
  ⑦ 합계행(GR/GI Type='Total') 미적재
  ⑧ 오염 0 — 검증 후 원래 상태 복원

★실DB 를 쓰므로 **원본 파일명으로 재적재**해 복원한다(삭제 규칙이 biz+ymd 라 그래야 원상복구).
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(R, "_migration"))
sys.path.insert(0, os.path.join(R, "PNC_ERP_Web", "backend"))

PORT = sys.argv[1] if len(sys.argv) > 1 else "8013"
BASE = "http://127.0.0.1:" + PORT
DL = r"C:\Users\admin\Downloads"
SAC_F = os.path.join(DL, "Transfer History for OSP_1787868090622.xlsx")   # 288행 SAC
RAC_F = os.path.join(DL, "Transfer History for OSP_1787747065764.xlsx")   # 21행 RAC

import flow_cases as FC                                    # noqa: E402
_d = json.dumps({'id': 'super', 'pw': FC.ACCOUNTS['super']}).encode()
_rq = urllib.request.Request(BASE + '/api/auth/login', data=_d,
                             headers={'Content-Type': 'application/json'}, method='POST')
TOK = json.loads(urllib.request.urlopen(_rq, timeout=120).read().decode())['token']

os.chdir(os.path.join(R, "PNC_ERP_Web", "backend"))
from common import _nx                                     # noqa: E402

PASS = []; FAIL = []


def chk(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  {} {:<44} {}".format("✅" if ok else "★FAIL", name, detail))


def up(path, biz, fname=None):
    raw = open(path, 'rb').read()
    fn = fname or os.path.basename(path)
    b = ('--X\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\n' % fn).encode()
    b += b'Content-Type: application/octet-stream\r\n\r\n' + raw + b'\r\n--X--\r\n'
    q = ("?biz=" + biz) if biz else ""
    r = urllib.request.Request(BASE + "/api/lgsagub/upload" + q, data=b, method="POST",
                               headers={"Content-Type": "multipart/form-data; boundary=X",
                                        "Authorization": "Bearer " + TOK})
    try:
        with urllib.request.urlopen(r, timeout=600) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def snap():
    cur = _nx().cursor()
    cur.execute("""SELECT ISNULL(biz,''), COUNT(*), SUM(ISNULL(qty,0)), SUM(ISNULL(amt,0))
                     FROM nx.lg_sagub_actual GROUP BY ISNULL(biz,'')""")
    return {r[0]: (r[1], round(float(r[2] or 0), 2), round(float(r[3] or 0), 2)) for r in cur.fetchall()}


print("=" * 92)
print("  OSP 사급실적 업로드 검증  (port {})".format(PORT))
print("=" * 92)
before = snap()
print("  시작 상태:", {k: v[0] for k, v in before.items()})

# ② 사업부 미지정
st, j = up(SAC_F, "", "osp_noname.xlsx")
chk("② 사업부 미지정 → 차단", st == 400 and "사업부" in str(j.get('detail', '')), "HTTP {}".format(st))

# ③ 오선택 양방향
st, j = up(SAC_F, "RAC")
chk("③-1 SAC 파일을 RAC 로 → 차단", st == 400 and "파일 내용은 SAC" in str(j.get('detail', '')), "HTTP {}".format(st))
st, j = up(RAC_F, "SAC")
chk("③-2 RAC 파일을 SAC 로 → 차단", st == 400 and "파일 내용은 RAC" in str(j.get('detail', '')), "HTTP {}".format(st))

# ④ 정상 업로드
st, j = up(SAC_F, "SAC")
n1 = j.get('rows')
chk("④ 정상(SAC→SAC) 통과", st == 200 and n1 == 288, "HTTP {} rows={}".format(st, n1))

# ① 식별컬럼 적재
cur = _nx().cursor()
cur.execute("""SELECT COUNT(*), SUM(CASE WHEN ISNULL(ps_order,'')<>'' THEN 1 ELSE 0 END),
                      COUNT(DISTINCT NULLIF(line_name,'')), COUNT(DISTINCT NULLIF(uit,'')),
                      COUNT(DISTINCT NULLIF(assembly,''))
                 FROM nx.lg_sagub_actual WHERE ymd='260827' AND biz='SAC'""")
tot, po, ln, u, asm = cur.fetchone()
chk("① 식별컬럼 적재(ps_order/line_name/uit/assembly)",
    tot == 288 and po > 200 and ln >= 1 and u >= 1 and asm >= 1,
    "{}행 · ps_order {} · line {}종 · uit {}종 · assembly {}종".format(tot, po, ln, u, asm))

# ⑦ 합계행 미적재
cur.execute("""SELECT COUNT(*) FROM nx.lg_sagub_actual
                WHERE ymd='260827' AND biz='SAC'
                  AND (ISNULL(LTRIM(RTRIM(item_code)),'')='' OR LOWER(item_code) IN ('total','합계','소계'))""")
chk("⑦ 합계행 미적재", cur.fetchone()[0] == 0)

# ⑤ 멱등성 — 같은 파일 2회 더
cur.execute("SELECT COUNT(*), SUM(ISNULL(qty,0)) FROM nx.lg_sagub_actual WHERE ymd='260827' AND biz='SAC'")
a1 = cur.fetchone()
for _ in range(2):
    up(SAC_F, "SAC")
cur = _nx().cursor()
cur.execute("SELECT COUNT(*), SUM(ISNULL(qty,0)) FROM nx.lg_sagub_actual WHERE ymd='260827' AND biz='SAC'")
a2 = cur.fetchone()
chk("⑤ 멱등성(재업로드 2회) — 행수·수량 불변",
    a1[0] == a2[0] and abs(float(a1[1] or 0) - float(a2[1] or 0)) < 0.01,
    "{}행/{:,.0f} → {}행/{:,.0f}".format(a1[0], float(a1[1] or 0), a2[0], float(a2[1] or 0)))

# ⑥ 판정 불가 파일은 막지 않음 — 사전에 없는 품번만 담은 임시 엑셀
import openpyxl
tmp = os.path.join(os.environ.get("TEMP", "."), "osp_unknown.xlsx")
wb = openpyxl.Workbook(); ws = wb.active
ws.append(["Material", "Description", "GI Qty", "Sales Price", "Sales Amount", "Transaction Date", "P/S Order"])
for i in range(4):
    ws.append(["ZZTEST{:04d}".format(i), "테스트품목", 1, 100, 100, "2026-08-30", "TESTORDER{}".format(i)])
wb.save(tmp)
st, j = up(tmp, "SAC", "osp_unknown_TEST.xlsx")
chk("⑥ 판정불가(신규품목만) → 막지 않음", st == 200, "HTTP {} rows={}".format(st, j.get('rows')))

# ⑧ 오염 0 — 테스트분 삭제 + 원본 재적재
cn = _nx(); c = cn.cursor()
c.execute("DELETE FROM nx.lg_sagub_actual WHERE src_file='osp_unknown_TEST.xlsx'")
cn.commit(); cn.close()
up(SAC_F, "SAC")                                   # 원본 파일명으로 복원
after = snap()
same = all(before.get(k, (0, 0, 0)) == after.get(k, (0, 0, 0)) for k in set(before) | set(after))
chk("⑧ 오염 0 — 시작 상태로 복원", same,
    "{} → {}".format({k: v[0] for k, v in before.items()}, {k: v[0] for k, v in after.items()}))

print("\n" + "=" * 92)
print("  PASS {} · FAIL {}".format(len(PASS), len(FAIL)))
for f in FAIL:
    print("    ★ " + f)
print("  ⟹ {}".format("전건 통과" if not FAIL else "★실패 있음"))
