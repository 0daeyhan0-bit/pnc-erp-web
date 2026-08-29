# -*- coding: utf-8 -*-
"""컷오버 완료 마커 — 이 마커가 켜지면 '레거시가 주인'이던 도구들이 스스로 멈춘다.

정본 = `_schema/CUTOVER_CHECKLIST.md` "델타싱크 컷오버 가드"

왜 필요한가
  컷오버 전과 후는 **데이터의 주인이 뒤바뀐다.**
    · 컷오버 전 : 레거시가 주인 → 레거시 값으로 nx 를 맞추는 게 **맞다**
    · 컷오버 후 : 웹이 주인   → 같은 동작이 **웹 입력을 지운다**
  사람이 기억해서 막는 방식은 언젠가 실패한다. **코드가 스스로 알게** 한다.

이 마커를 보는 도구
  · `_migration/sub_norm/r_delta_sync.py` — TRUNCATE + 라이브 전량 INSERT 를 한다.
    대상에 웹이 쓰는 재고 잔량 테이블이 있다(PU_T_MAT_STOCK_WH 10곳 · PR_T_MAT_STOCK_WH 8곳 등).

사용
  python _migration/cutover_mark.py                 # 현재 상태 확인
  python _migration/cutover_mark.py --set --commit  # 컷오버 완료 표시(컷오버 밤에)
  python _migration/cutover_mark.py --clear --commit# 롤백 시 해제
"""
import io, sys, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'PNC_ERP_Web', 'backend'))
from common import _nx

cn = _nx(); c = cn.cursor()
c.execute("""IF OBJECT_ID('nx.cutover_state','U') IS NULL
             CREATE TABLE nx.cutover_state(
               done_flag BIT NOT NULL, done_at DATETIME NOT NULL DEFAULT GETDATE(),
               note NVARCHAR(200) NULL)""")

DRY = '--commit' not in sys.argv

if '--set' in sys.argv:
    print("컷오버 완료 표시")
    if DRY:
        print("  DRY — 실행하려면 --commit"); cn.close(); sys.exit()
    c.execute("DELETE FROM nx.cutover_state")
    c.execute("INSERT INTO nx.cutover_state(done_flag, note) VALUES(1, ?)",
              "컷오버 완료 — 레거시 기준 sync 도구 정지")
    print("  설정됨. 이제 r_delta_sync.py 는 실행을 거부한다.")
elif '--clear' in sys.argv:
    print("컷오버 마커 해제(롤백)")
    if DRY:
        print("  DRY — 실행하려면 --commit"); cn.close(); sys.exit()
    c.execute("DELETE FROM nx.cutover_state")
    print("  해제됨. sync 도구가 다시 돈다.")
else:
    c.execute("SELECT done_flag, done_at, note FROM nx.cutover_state WHERE done_flag=1")
    r = c.fetchone()
    if r:
        print(f"★컷오버 완료 상태 — {r[1]}  ({r[2]})")
        print("  r_delta_sync.py 는 실행을 거부한다.")
    else:
        print("컷오버 전 — sync 도구 정상 동작")
cn.close()
