# -*- coding: utf-8 -*-
"""재생 루프 — 30분마다 자동으로 관측 + 재생 (2026-09-01 대표 요청 "계속 돌릴 수 없어?")

무엇을 하나 (한 사이클)
  ① 관측  `replay_pilot --observe` : 지난 사이클 이후 레거시에 새로 들어온 거래
  ② 재생  신규가 있으면 **우리 화면 API 로 다시 입력**(롤백 서버) → 결과 판정
  ③ 기록  한 줄 요약을 `replay_loop_log.txt` 에 append
  ④ 대기  기본 30분

판정 관점 = **"프로그램이 정상 작동하는가"**(대표 2026-09-01)
  4xx 정당 거부 + DB 무기록 = PASS(게이트가 제 일을 한 것) · 5xx/크래시/거부하며 기록 = FAIL

★잠금 범위 (2026-09-01 대표 지적으로 정정)
  롤백 서버가 트랜잭션을 여는 곳은 **nx(신규 ERP) 뿐**이다. 레거시(PARTNER_ERP)는 **읽기만** 한다.
  ⟹ **현업 업무(레거시)에는 영향이 없다.** 처음에 "업무 중이라 위험" 이라 한 것은 과한 걱정이었다.
  다만 nx 는 **운영 웹 ERP(8010)가 공유**하는 DB다(CLAUDE.md §8 "DB 는 dev·운영 공유").
  누군가 신규 화면에서 **입력**하면 그때는 부딪힐 수 있다 — 지금은 조회 위주라 위험이 낮다.
  그래도 사이클마다 하네스가 끝에 `/api/_flow/rollback` 을 불러 **잠금을 즉시 놓는다**.
  서버 자체는 재기동 비용(워밍 2~3분)이 커서 유지한다.

★7:30 매일 마이그 시간대에는 **자동으로 쉰다**. 이건 진짜 충돌이다 —
  마이그가 nx 미러를 통째로 교체(TRUNCATE+INSERT)하는데 트랜잭션이 걸려 있으면 서로 막는다.

사용
    python _migration/replay_loop.py                 # 30분 간격, 계속
    python _migration/replay_loop.py --interval 900  # 15분
    python _migration/replay_loop.py --once          # 1회만
  중단 = Ctrl+C (또는 이 프로세스 종료)
"""
import argparse
import datetime
import io
import os
import subprocess
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
LOG = os.path.join(HERE, 'replay_loop_log.txt')

AP = argparse.ArgumentParser()
AP.add_argument('--interval', type=int, default=1800, help='사이클 간격(초). 기본 1800=30분')
AP.add_argument('--port', type=int, default=8099)
AP.add_argument('--once', action='store_true')
AP.add_argument('--quiet-hours', default='07:20-07:50', help='쉬는 구간(매일 마이그) HH:MM-HH:MM')
ARG = AP.parse_args()
BASE = "http://127.0.0.1:%d" % ARG.port


def now():
    return datetime.datetime.now()


def log(line):
    stamp = now().strftime('%m-%d %H:%M')
    print("  [%s] %s" % (stamp, line))
    with io.open(LOG, 'a', encoding='utf-8') as f:
        f.write("[%s] %s\n" % (stamp, line))


def in_quiet():
    try:
        a, b = ARG.quiet_hours.split('-')
        t = now().strftime('%H:%M')
        return a <= t <= b
    except Exception:
        return False


def server_up():
    try:
        urllib.request.urlopen(BASE + "/api/_flow/probe", timeout=5).read()
        return True
    except Exception:
        return False


def start_server():
    """롤백 서버 기동(워밍 때문에 최대 5분 기다린다)."""
    log("롤백 서버 기동 중… (워밍 2~3분)")
    subprocess.Popen([sys.executable, os.path.join(HERE, 'flow_server.py'), '--port', str(ARG.port)],
                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        time.sleep(2)
        if server_up():
            log("롤백 서버 준비됨")
            return True
    log("★롤백 서버 기동 실패 — 이번 사이클 건너뜀")
    return False


def run(cmd, env=None, timeout=2400):
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable] + cmd, cwd=ROOT, env=e, timeout=timeout,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode('utf-8', 'replace')


def cycle():
    ymd = now().strftime('%y%m%d')
    # ① 관측
    try:
        out = run([os.path.join(HERE, 'replay_pilot.py'), '--observe'], timeout=1200)
    except Exception as e:
        log("관측 실패 - %s" % str(e)[:100]); return
    newn = 0
    for ln in out.splitlines():
        if '신규' in ln and '행' in ln:
            try:
                newn = int(ln.split('신규')[1].split('행')[0].strip())
            except Exception:
                pass
    if newn <= 0:
        log("신규 0행 — 재생 생략")
        return
    log("신규 %d행 관측" % newn)

    # ② 재생 (마이그 이후 구간만 = nx 에 아직 없는 것)
    if not server_up() and not start_server():
        return
    since = now().strftime('%Y-%m-%d 07:30:00')
    try:
        out = run([os.path.join(HERE, 'flow_scenarios.py'), '--port', str(ARG.port), '--only', '재생'],
                  env={'REPLAY_YMD': ymd, 'REPLAY_SINCE': since})
    except Exception as e:
        log("★재생 실행 실패 - %s" % str(e)[:120]); return

    res = [l.strip() for l in out.splitlines() if l.strip().startswith('결과:')]
    clean = ('오염 0 PASS' in out)
    fails = [l.strip()[:150] for l in out.splitlines() if '★FAIL' in l]
    log("재생 %s · 오염%s%s"
        % (res[0] if res else '결과 미확인', '0' if clean else '★의심',
           (' · FAIL %d건' % len(fails)) if fails else ''))
    for f in fails[:5]:
        log("   " + f)


def main():
    log("=== 재생 루프 시작 (간격 %d초 · 포트 %d · 쉬는구간 %s) ==="
        % (ARG.interval, ARG.port, ARG.quiet_hours))
    while True:
        if in_quiet():
            log("매일 마이그 시간대 — 쉼")
        else:
            try:
                cycle()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log("★사이클 예외 - %s" % str(e)[:140])
        if ARG.once:
            break
        time.sleep(ARG.interval)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        log("중단됨(사용자)")
