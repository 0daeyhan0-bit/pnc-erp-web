# -*- coding: utf-8 -*-
"""★원복 — nx.plan_part_mat 컬럼추가(2026-09-06) 되돌리기.

무엇을 되돌리나
  협력사자재계획현황(w_pr_outside_040 t1)을 웹 테이블만으로 재현하려고
  `planrev.py` STEP7 의 SELECT INTO 에 6개 컬럼을 추가했다:
    line_no · output_hm · lot_qty · plan_qty · use_qty · model_no
  값은 nx.plan_part_dtl / nx.plan_dtl 에서 조인해 가져온다(파생 아님, 원본 그대로).

되돌리는 방법은 두 가지다
  ① 데이터만 복구  — 이 스크립트. 백업 테이블을 되돌린다(편성 재실행 불필요).
  ② 코드도 원복    — planrev.py 의 해당 블록을 지운다(아래 안내). 그래야 다음 편성에서
                     컬럼이 다시 생기지 않는다.

백업
  nx.bk_planpartmat_260906  (102,687행 · 2026-09-06 컬럼추가 전 스냅샷)

사용
    python _schema/rollback_planpartmat_260906.py          # 상태만 확인
    python _schema/rollback_planpartmat_260906.py --apply  # 실제 복구
"""
import sys, io, argparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
sys.path.insert(0, r"c:\Users\박근민\Desktop\New_ERP")
from db_client import get_connection

AP = argparse.ArgumentParser()
AP.add_argument("--apply", action="store_true", help="실제 복구(없으면 조회만)")
ARG = AP.parse_args()

BK = "bk_planpartmat_260906"
NEW_COLS = ("line_no", "output_hm", "lot_qty", "plan_qty", "use_qty", "model_no")

cn = get_connection()
cu = cn.cursor()

cu.execute(f"SELECT COUNT(*) FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.TABLES "
           f"WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='{BK}'")
if not cu.fetchone()[0]:
    print(f"★백업 테이블 nx.{BK} 이 없습니다 — 복구할 수 없습니다.")
    sys.exit(1)

cu.execute(f"SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.{BK}")
nbk = cu.fetchone()[0]
cu.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.plan_part_mat")
ncur = cu.fetchone()[0]

cu.execute("""SELECT COLUMN_NAME FROM PARTNER_ERP_TEST3.INFORMATION_SCHEMA.COLUMNS
               WHERE TABLE_SCHEMA='nx' AND TABLE_NAME='plan_part_mat'""")
cols = {r[0].lower() for r in cu.fetchall()}
has = [c for c in NEW_COLS if c in cols]

print("=" * 66)
print(" nx.plan_part_mat 원복")
print("=" * 66)
print(f"  현재 테이블 : {ncur:,}행 · 추가컬럼 {len(has)}/6 존재 {has}")
print(f"  백업        : nx.{BK}  {nbk:,}행")

if not ARG.apply:
    print("\n  ※ 조회만 했습니다. 실제 복구하려면 --apply 를 붙이세요.")
    print("  ※ 코드도 되돌리려면 planrev.py 에서 '2026-09-06 신설' 주석이 달린")
    print("     6개 컬럼과 그 아래 LEFT JOIN 2개(pd·pdm)를 삭제하세요.")
    sys.exit(0)

cu.execute("IF OBJECT_ID('nx.plan_part_mat_rbold') IS NOT NULL DROP TABLE nx.plan_part_mat_rbold")
cu.execute("""IF OBJECT_ID('nx.plan_part_mat') IS NOT NULL
                EXEC sp_rename 'nx.plan_part_mat', 'plan_part_mat_rbold'""")
cu.execute(f"SELECT * INTO PARTNER_ERP_TEST3.nx.plan_part_mat "
           f"FROM PARTNER_ERP_TEST3.nx.{BK}")
cu.execute("IF OBJECT_ID('nx.plan_part_mat_rbold') IS NOT NULL DROP TABLE nx.plan_part_mat_rbold")
cn.commit()

cu.execute("SELECT COUNT(*) FROM PARTNER_ERP_TEST3.nx.plan_part_mat")
print(f"\n  ✅ 복구 완료 — {cu.fetchone()[0]:,}행 (백업과 동일해야 정상)")
print("  ⚠ 코드(planrev.py)는 그대로다. 다음 편성에서 컬럼이 다시 생긴다.")
print("     완전히 되돌리려면 위 안내대로 코드도 삭제할 것.")
