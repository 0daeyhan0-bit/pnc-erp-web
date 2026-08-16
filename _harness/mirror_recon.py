# -*- coding: utf-8 -*-
"""
병행운영 실측 대조 하네스 — nx 미러 vs dbo 라이브 정합 모니터
================================================================
목적: 하드컷오버 확신 근거. 웹(nx)이 레거시앱과 실거래로 일치하는지의 근본 = "nx 미러가 라이브 dbo만큼 최신인가".
  - 코드는 접두어(dbo->nx)만 바뀌어 쿼리 로직은 레거시와 동일(동기화 데이터에서 결과일치 이미 증명).
  - 따라서 유일 리스크 = 미러 lag. 이 스크립트가 트랜잭션 미러를 dbo-라이브와 CHECKSUM 대조.
  - 매일 실행 -> 며칠 초록불 = 미러 동기화 SLA 충족 = 컷오버 seamless 증명.

분류(테이블 명명규칙):
  _T_ (트랜잭션)  -> 미러 필수 최신. dbo와 불일치 = 동기화 lag = RED.
  _M_ (마스터)    -> repoint됨(정제/불변). dbo와 차이는 의도적일 수 있음 = INFO.
  소문자(clean)   -> nx 전용(dbo 짝 없음) = 스킵.

사용:
  python mirror_recon.py                 # 전 라우터 nx참조 자동수집, 대조, 로그append
  python mirror_recon.py --files kitting soyo gagong coopplan   # 특정 라우터만(4프로그램)
로그: _harness/mirror_recon_log.jsonl (timestamp별 이력). GREEN이면 exit 0.
"""
import sys, io, os, re, glob, json, argparse, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"d:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP")
import pyodbc, db_client

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTERS = os.path.join(HERE, "..", "PNC_ERP_Web", "backend", "routers")
LOG = os.path.join(HERE, "mirror_recon_log.jsonl")

def _cur():
    return pyodbc.connect(
        f'DRIVER={{SQL Server}};SERVER={db_client.DB_SERVER},{db_client.DB_PORT};'
        f'DATABASE=PARTNER_ERP_TEST3;UID={db_client.DB_USER};PWD={db_client.DB_PASSWORD}',
        timeout=30).cursor()

def discover_nx_tables(files=None):
    """라우터 파일들에서 PARTNER_ERP_TEST3.nx.<TABLE> 및 nx.<TABLE> 참조 자동수집."""
    paths = []
    if files:
        for f in files:
            paths.append(os.path.join(ROUTERS, f if f.endswith(".py") else f + ".py"))
    else:
        paths = glob.glob(os.path.join(ROUTERS, "*.py"))
    tbls = {}
    pat = re.compile(r'(?:PARTNER_ERP_TEST3\.)?nx\.([A-Za-z_][A-Za-z0-9_]+)')
    # 파이썬 메서드(nx.close/commit/cursor/rollback/dbo/execute...) 오탐 제외
    NOISE = {'close', 'commit', 'cursor', 'rollback', 'dbo', 'execute', 'fetchall',
             'fetchone', 'description', 'autocommit'}
    for p in paths:
        if not os.path.exists(p):
            continue
        base = os.path.basename(p)[:-3]
        txt = open(p, encoding='utf-8').read()
        for m in pat.findall(txt):
            if m.lower() in NOISE:
                continue
            # SQL은 대소문자 무관 -> 물리테이블 하나로 정규화(대문자 canonical)
            tbls.setdefault(m.upper(), set()).add(base)
    return tbls

def classify(name):
    u = name.upper()
    if re.search(r'_T_', u):
        return 'TX'      # 트랜잭션 미러 = 최신 필수
    if re.search(r'_M_', u):
        return 'MASTER'  # 마스터 repoint = 차이 허용
    return 'NXONLY'      # 소문자 clean 등

def obj_exists(cur, db, schema, name):
    cur.execute(
        "SELECT COUNT(*) FROM {}.INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA=? AND TABLE_NAME=?".format(db), (schema, name))
    return cur.fetchone()[0] > 0

def recon_one(cur, name):
    """nx.<name> vs dbo.<name> 정합. dict 반환."""
    r = {'table': name, 'class': classify(name)}
    dbo_ok = obj_exists(cur, 'PARTNER_ERP', 'dbo', name)
    nx_ok = obj_exists(cur, 'PARTNER_ERP_TEST3', 'nx', name)
    r['dbo_exists'], r['nx_exists'] = dbo_ok, nx_ok
    if not nx_ok:
        r['verdict'] = 'NX_MISSING'; return r
    if not dbo_ok:
        r['verdict'] = 'NX_ONLY'; return r
    try:
        cur.execute(f"SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) "
                    f"FROM PARTNER_ERP.dbo.{name} WITH(NOLOCK)")
        dc, dk = cur.fetchone()
        cur.execute(f"SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) "
                    f"FROM PARTNER_ERP_TEST3.nx.{name} WITH(NOLOCK)")
        nc, nk = cur.fetchone()
    except Exception as e:
        r['verdict'] = 'ERR'; r['err'] = str(e)[:120]; return r
    r['dbo_rows'], r['nx_rows'] = int(dc), int(nc)
    r['dbo_chk'], r['nx_chk'] = dk, nk
    if dc == nc and dk == nk:
        r['verdict'] = 'MATCH'
    elif dc != nc:
        r['verdict'] = 'DRIFT_ROWS'
    else:
        r['verdict'] = 'DRIFT_CONTENT'
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', nargs='*', help='특정 라우터만(예: kitting soyo gagong coopplan)')
    ap.add_argument('--stamp', default=None, help='실행 타임스탬프(YYYY-MM-DD HH:MM). 미지정시 now')
    args = ap.parse_args()
    stamp = args.stamp or datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    tbls = discover_nx_tables(args.files)
    cur = _cur()
    results = []
    for name in sorted(tbls):
        rr = recon_one(cur, name)
        rr['routers'] = sorted(tbls[name])
        results.append(rr)

    # 분류별 집계
    tx = [r for r in results if r['class'] == 'TX']
    ms = [r for r in results if r['class'] == 'MASTER']
    nxo = [r for r in results if r['class'] == 'NXONLY']
    tx_bad = [r for r in tx if r['verdict'] not in ('MATCH',)]
    ms_diff = [r for r in ms if r['verdict'] in ('DRIFT_ROWS', 'DRIFT_CONTENT')]

    print(f"=== 미러 정합 대조 @ {stamp} ===")
    print(f"수집: 트랜잭션 {len(tx)} · 마스터 {len(ms)} · nx전용 {len(nxo)}\n")
    print("【트랜잭션 미러 (최신 필수) — nx vs dbo】")
    for r in sorted(tx, key=lambda x: (x['verdict'] == 'MATCH', x['table'])):
        v = r['verdict']
        icon = '✅' if v == 'MATCH' else ('⚠️' if v in ('NX_ONLY',) else '❌')
        det = ''
        if v in ('MATCH', 'DRIFT_ROWS', 'DRIFT_CONTENT'):
            det = f"dbo={r['dbo_rows']} nx={r['nx_rows']}"
            if v == 'DRIFT_CONTENT':
                det += " (건수동일·내용상이=lag)"
        elif v == 'ERR':
            det = r.get('err', '')
        print(f"  {icon} {r['table']:<28} {v:<14} {det}  [{','.join(r['routers'])}]")
    if ms:
        print("\n【마스터 (repoint·차이허용) — 참고】")
        for r in sorted(ms, key=lambda x: x['table']):
            det = (f"dbo={r.get('dbo_rows','?')} nx={r.get('nx_rows','?')}"
                   if r['verdict'] != 'NX_ONLY' else 'nx전용')
            print(f"  · {r['table']:<28} {r['verdict']:<14} {det}")

    ok = len(tx_bad) == 0
    print("\n" + "=" * 50)
    if ok:
        print(f"★ GREEN — 트랜잭션 미러 {len(tx)}개 전부 dbo-라이브와 일치. 컷오버 seamless.")
    else:
        print(f"★ RED — 트랜잭션 미러 {len(tx_bad)}개 drift(동기화 lag). 컷오버 전 재싱크 필요:")
        for r in tx_bad:
            print(f"    - {r['table']}: {r['verdict']}")

    # 로그 append (이력)
    logrow = {'stamp': stamp, 'tx_total': len(tx), 'tx_match': len(tx) - len(tx_bad),
              'tx_bad': [r['table'] for r in tx_bad], 'green': ok,
              'ms_diff': [r['table'] for r in ms_diff]}
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(logrow, ensure_ascii=False) + "\n")
    print(f"\n로그 기록: {LOG}")
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
