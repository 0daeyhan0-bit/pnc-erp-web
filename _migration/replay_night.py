# -*- coding: utf-8 -*-
"""야간 재생 — 하루치를 한 번에 (2026-09-01 대표 "오늘 저녁 8시에 하면 되거든. 한번에 작업을 다해줄 수 있어?")

왜 야간 1회인가 (30분 주기에서 바꾼 이유)
  ① **흐름이 완결된다.** 낮에 30분마다 돌리면 그 시점까지 쌓인 '조각'만 재생된다 —
     생산이 앞뒤 없이 떠 있어 키팅→생산→출하가 이어지지 않는다.
     하루가 끝나면 전 단계가 다 모여 있어 **시각순으로 온전히** 재생할 수 있다.
  ② **잠금을 피한다.** 롤백 서버는 nx 에 미커밋 트랜잭션을 여는데
     `PARTNER_ERP_TEST3` 는 RCSI=OFF 라(실측 2026-09-01) **읽는 쪽이 막힌다.**
     운영 웹 ERP(8010)가 nx 를 읽으므로 업무 중에는 신규 화면이 멈출 수 있다.
     ※RCSI 를 켜면 이 문제는 거의 사라지지만 운영 DB 설정 변경이라 별도 승인 사안이다.

한 번에 하는 것
  1) 롤백 서버 기동 + 워밍 대기(2~3분)
  2) **하루치 전량 재생** — 그날 사람 입력(①)을 시각순으로 우리 API 에 투입
  3) **품번별 흐름 재생** — 흐름이 가장 잘 이어진 상위 품번들을 골라
     시드 → 키팅 → 생산 → 출하 종단 재현
  4) 리포트 파일 생성 + 롤백/오염0 확인 + 서버 종료

판정 관점 = "프로그램이 정상 작동하는가"
  정당한 4xx 거부 + DB 무기록 = PASS(게이트가 제 일을 한 것) · 5xx·거부하며 기록 = FAIL

사용
    python _migration/replay_night.py                 # 오늘자
    python _migration/replay_night.py --ymd 260901    # 날짜 지정
    python _migration/replay_night.py --items 5       # 흐름 재생할 품번 수(기본 3)
    python _migration/replay_night.py --at 20:00      # 그 시각까지 기다렸다 시작
결과 = `_migration/replay_night_<YYMMDD>.txt`
"""
import argparse
import datetime
import io
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'PNC_ERP_Web', 'backend'))

AP = argparse.ArgumentParser()
AP.add_argument('--ymd', default='')
AP.add_argument('--port', type=int, default=8099)
AP.add_argument('--items', type=int, default=3, help='흐름 재생할 품번 수')
AP.add_argument('--since', default='', help="구간 시작 'YYYY-MM-DD HH:MM:SS' (기본=그날 07:30)")
AP.add_argument('--at', default='', help='HH:MM 까지 기다렸다 시작')
AP.add_argument('--keep-server', action='store_true', help='끝나고 서버를 남긴다')
ARG = AP.parse_args()

YMD = ARG.ymd.strip() or datetime.date.today().strftime('%y%m%d')
BASE = "http://127.0.0.1:%d" % ARG.port
REPORT = os.path.join(HERE, 'replay_night_%s.txt' % YMD)
SINCE = ARG.since.strip() or ("20%s-%s-%s 07:30:00" % (YMD[:2], YMD[2:4], YMD[4:6]))


def say(line=""):
    print(line)
    with io.open(REPORT, 'a', encoding='utf-8') as f:
        f.write(line + "\n")


def up():
    try:
        urllib.request.urlopen(BASE + "/api/_flow/probe", timeout=5).read()
        return True
    except Exception:
        return False


def start_server():
    say("  롤백 서버 기동 중… (워밍 2~3분)")
    subprocess.Popen([sys.executable, os.path.join(HERE, 'flow_server.py'), '--port', str(ARG.port)],
                     cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(180):
        time.sleep(2)
        if up():
            # ★워밍 직후 첫 요청이 간헐 500 이다(정본 CLAUDE.md §4). 한 번 흘려보낸다.
            try:
                urllib.request.urlopen(BASE + "/api/_flow/probe", timeout=30).read()
            except Exception:
                pass
            say("  롤백 서버 준비됨")
            return True
    say("  ★서버 기동 실패 — 중단")
    return False


def stop_server():
    if ARG.keep_server:
        return
    try:
        import subprocess as sp
        out = sp.run(['netstat', '-ano'], capture_output=True, text=True, timeout=60).stdout
        for ln in out.splitlines():
            if (":%d" % ARG.port) in ln and 'LISTENING' in ln:
                pid = ln.split()[-1]
                sp.run(['taskkill', '/PID', pid, '/F'], capture_output=True, timeout=60)
                say("  서버 종료(PID %s)" % pid)
                return
    except Exception as e:
        say("  서버 종료 실패(수동 확인 필요) - %s" % str(e)[:80])


def run_suite(env, only, label):
    """하네스 1회 실행 → (요약줄, FAIL목록, 오염여부, 총합대조줄)"""
    e = dict(os.environ)
    e.update(env)
    p = subprocess.run([sys.executable, os.path.join(HERE, 'flow_scenarios.py'),
                        '--port', str(ARG.port), '--only', only],
                       cwd=ROOT, env=e, timeout=7200,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode('utf-8', 'replace')
    res = [l.strip() for l in out.splitlines() if l.strip().startswith('결과:')]
    fails = [l.strip() for l in out.splitlines() if '★FAIL' in l]
    tot = [l.strip() for l in out.splitlines() if ('레거시' in l and '우리' in l)]
    clean = ('오염 0 PASS' in out)
    say()
    say("── %s ─────────────────────────" % label)
    say("  %s" % (res[0] if res else "결과 미확인"))
    say("  오염: %s" % ("0 PASS" if clean else "★의심 — 확인 필요"))
    if tot:
        say("  [총합 대조] 레거시 vs 우리")
        for t in tot[:6]:
            say("    " + t)
    if fails:
        say("  ★FAIL %d건" % len(fails))
        for f in fails[:12]:
            say("    " + f[:170])
    return out


def top_items(n):
    """흐름이 가장 잘 이어진 품번 — 단계수(키팅/생산/출하) 많은 순."""
    from common import _conn
    c = _conn().cursor()
    c.execute("""
    SELECT TOP (%d) code FROM (
      SELECT LTRIM(RTRIM(ITEM_CODE)) code, '키팅' st FROM PARTNER_ERP.dbo.PU_T_READY_STOCK_MAINT
        WHERE MAINT_YMD=? AND MAINT_TAG IN ('1','2')
      UNION ALL SELECT LTRIM(RTRIM(ITEM_CODE)), '생산' FROM PARTNER_ERP.dbo.PR_T_PROD_DTL WHERE PROD_YMD=?
      UNION ALL SELECT LTRIM(RTRIM(ITEM_CODE)), '출하' FROM PARTNER_ERP.dbo.SA_T_STOCK_MAINT
        WHERE MAINT_YMD=? AND MAINT_TAG='J'
    ) x WHERE code<>'' GROUP BY code
    ORDER BY COUNT(DISTINCT st) DESC, COUNT(*) DESC""" % n, YMD, YMD, YMD)
    return [r[0] for r in c.fetchall()]


def other_sessions():
    """nx 를 쓰고 있는 다른 사용자 세션 — 재생 전 경고용.

       ★왜 — 롤백 서버는 nx 에 미커밋 트랜잭션을 연다. `PARTNER_ERP_TEST3` 는 RCSI=OFF 라
         (실측 2026-09-01) **읽는 쪽이 막힌다**. 야간엔 보통 아무도 없지만,
         다른 개발 세션이 붙어 있으면 그 세션이 멈춘다 → 미리 알린다.
       권한(VIEW SERVER STATE)이 없으면 조용히 건너뛴다.
    """
    try:
        from common import _nx
        c = _nx().cursor()
        c.execute("""SELECT COUNT(*), MAX(ISNULL(host_name,'')), MAX(ISNULL(program_name,''))
                       FROM sys.dm_exec_sessions
                      WHERE database_id = DB_ID('PARTNER_ERP_TEST3')
                        AND session_id <> @@SPID AND is_user_process = 1""")
        n, host, prog = c.fetchone()
        return int(n or 0), (host or ''), (prog or '')
    except Exception:
        return None, '', ''


def main():
    if ARG.at.strip():
        hh, mm = ARG.at.strip().split(':')
        while True:
            now = datetime.datetime.now()
            if (now.hour, now.minute) >= (int(hh), int(mm)):
                break
            time.sleep(20)

    io.open(REPORT, 'w', encoding='utf-8').write("")
    say("=" * 78)
    say("  야간 재생 — %s  (구간 %s ~ )  시작 %s"
        % (YMD, SINCE, datetime.datetime.now().strftime('%H:%M')))
    say("  판정: 정당한 4xx 거부+무기록 = PASS(게이트가 일한 것) / 5xx·거부하며 기록 = FAIL")
    say("=" * 78)

    n, host, prog = other_sessions()
    if n is None:
        say("  ※nx 활성 세션 확인 불가(권한) — 그대로 진행")
    elif n > 0:
        say("  ★주의: nx 에 붙어 있는 다른 세션 %d개 (예: %s / %s)" % (n, host[:20], prog[:30]))
        say("     재생 중 그 세션의 nx **읽기가 막힐 수 있다**(RCSI=OFF). 업무 중이면 지금 멈추는 게 낫다.")
    else:
        say("  nx 활성 세션 0 — 잠금으로 막힐 상대가 없다")

    if not up() and not start_server():
        return

    # 1) 하루치 전량
    run_suite({'REPLAY_YMD': YMD, 'REPLAY_SINCE': SINCE}, '재생', '① 하루치 전량 재생 (시각순)')

    # 2) 품번별 흐름
    try:
        items = top_items(ARG.items)
    except Exception as e:
        items = []
        say("  ★흐름 대상 선정 실패 - %s" % str(e)[:100])
    for it in items:
        run_suite({'REPLAY_YMD': YMD, 'REPLAY_ITEM': it}, '흐름',
                  '② 흐름 재생 %s (시드→키팅→생산→출하)' % it)

    stop_server()
    say()
    say("=" * 78)
    say("  끝 %s · 리포트 %s" % (datetime.datetime.now().strftime('%H:%M'), REPORT))
    say("=" * 78)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        say("  중단됨(사용자)")
        stop_server()
