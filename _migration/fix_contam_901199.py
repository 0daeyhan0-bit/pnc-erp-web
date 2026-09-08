# -*- coding: utf-8 -*-
"""오염분 정리 — sheet 901199 에 잘못 딸려온 5210AP4184A 20개 회수

  ★사고 경위 (2026-09-08 실측)
    거래명세표 발행(coopplan.deliv420_issue)이 sheet_no 를 **헤더(set_input_req)만 보고** 채번했다.
    명세(set_input_req_dtl)에는 헤더 없는 고아 행이 670행 쌓여 있었고(헤더 INSERT 실패분),
    명세 MAX(901,533) 가 헤더 MAX(901,199) 보다 334 앞서 있었다.
      06:59:54  고아 명세 5210AP4184A 20개가 sheet=901199 에 남아 있었다(중앙정밀 2048 · BOM 무관)
      10:35:14  ACQ30605001(미래정밀 2096) 발행이 같은 901199 를 받아 그 행을 끌어안았다
      10:35:42  세트입고 처리 시 그 20개가 자재재고로 들어갔다
    → 거래명세표 인쇄는 1줄(ACQ30605001-4-1 5개)인데 DB 명세는 2줄이었다.

  ★코드는 이미 고쳤다(coopplan.py:1569·1608) — 이 스크립트는 **이미 들어간 값**만 회수한다.

  ★안전장치
    · 기본 DRY-RUN. 실제 반영은 --commit 을 붙여야 한다.
    · 대상을 키로 정확히 한정(sheet 901199 · 자재 5210AP4184A · 260908).
    · 원장을 지우지 않고 **역행(−20)을 넣어 이력을 남긴다**(CLAUDE.md §1-3 근거키 스코프).
      단 잔액·미러이력은 그 입고가 없었던 상태로 되돌린다.
"""
import sys, os, io
BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
MAT, SHEET, BC, YMD = '5210AP4184A', '901199', '700049', '260908'
QTY = 20.0
SC, PW = 'Z99990', 'IS0001'

cn = _nx(); cur = cn.cursor()
print("=" * 96)
print(" 오염분 정리 — {} {}개 (sheet {} · 바코드 {})".format(MAT, int(QTY), SHEET, BC))
print(" 모드: {}".format("★COMMIT (실제 반영)" if COMMIT else "DRY-RUN (조회만)"))
print("=" * 96)


def show(t):
    print("\n[{}]".format(t))
    cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.stock_ledger WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND MAINT_YMD=? AND MAINT_TAG='S'
                      AND RTRIM(ISNULL(SHEET_NO,''))=?""", MAT, YMD, BC)
    print("   원장(그 입고건)   = {:>8,.0f}".format(float(cur.fetchone()[0] or 0)))
    cur.execute("""SELECT ISNULL(SUM(MAINT_QTY),0) FROM nx.PU_T_STOCK_MAINT WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND MAINT_YMD=? AND MAINT_TAG='S'""", MAT, YMD)
    print("   미러이력(9/8 tagS)= {:>8,.0f}".format(float(cur.fetchone()[0] or 0)))
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM nx.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                MAT, SC, PW)
    print("   잔액              = {:>8,.0f}".format(float(cur.fetchone()[0] or 0)))
    cur.execute("SELECT COUNT(*) FROM nx.set_input_req_dtl WITH(NOLOCK) WHERE sheet_no=? AND RTRIM(mat_code)=?",
                SHEET, MAT)
    print("   명세 고아행       = {:>8,}".format(cur.fetchone()[0]))
    cur.execute("""SELECT ISNULL(SUM(STOCK_QTY),0) FROM PARTNER_ERP.dbo.PU_T_MAT_STOCK_WH WITH(NOLOCK)
                    WHERE RTRIM(MAT_CODE)=?""", MAT)
    print("   (참고) 레거시 잔액 = {:>8,.0f}  ← 목표값".format(float(cur.fetchone()[0] or 0)))


show("정리 전")

# ── 대상 존재 확인
cur.execute("""SELECT COUNT(*) FROM nx.stock_ledger WITH(NOLOCK)
                WHERE RTRIM(MAT_CODE)=? AND MAINT_YMD=? AND MAINT_TAG='S'
                  AND RTRIM(ISNULL(SHEET_NO,''))=? AND MAINT_QTY=?""", MAT, YMD, BC, QTY)
if cur.fetchone()[0] == 0:
    print("\n★대상 원장행이 없다 — 이미 정리됐거나 조건 불일치. 중단.")
    cur.close(); cn.close(); sys.exit(0)

if not COMMIT:
    print("\n" + "=" * 96)
    print(" 실행 예정 (DRY-RUN — 아무것도 바꾸지 않음)")
    print("=" * 96)
    print("   ① 원장에 역행 INSERT : STOCK_POINT='MAT' tag='S' qty=-20 비고='오염분 회수(sheet 901199)'")
    print("   ② 미러이력 역행      : PU_T_STOCK_MAINT tag='S' qty=-20")
    print("   ③ 잔액 −20          : PU_T_MAT_STOCK_WH 40 → 20 (레거시와 일치)")
    print("   ④ 고아 명세 삭제     : set_input_req_dtl id=5907 (sheet 901199 · 5210AP4184A)")
    print("\n   ⟹ 실제 반영하려면 --commit 을 붙여 다시 실행")
    cur.close(); cn.close(); sys.exit(0)

# ══════════════════════════════════════════════════════════
print("\n" + "=" * 96)
print(" 실행")
print("=" * 96)
try:
    # ① 원장 역행 (지우지 않고 되돌린 이력을 남긴다)
    cur.execute("SELECT ISNULL(MAX(MAINT_SEQ),0)+1 FROM nx.stock_ledger WHERE MAINT_YMD=?", YMD)
    lseq = int(cur.fetchone()[0] or 1)
    cur.execute("""INSERT INTO nx.stock_ledger
           (STOCK_POINT,MAINT_YMD,MAINT_SEQ,MAINT_TAG,SHEET_NO,CUST_CODE,WH_CUST_CODE,
            GAGONG_PROC_CODE,MAT_CODE,MAINT_QTY,MAINT_COST,MAINT_AMT,ITEM_CODE,
            REMARKS,INSERT_USER_ID,INSERT_DATETIME)
           VALUES('MAT',?,?,'S',?,?,?,?,?,?,0,0,?,?,?,getdate())""",
        YMD, lseq, int(BC), '2096', SC, PW, MAT, -QTY, 'ACQ30605001',
        '오염분 회수(sheet %s 번호재사용)' % SHEET, 'fix260908')
    print("   ① 원장 역행 INSERT  seq={}  qty={:+,.0f}".format(lseq, -QTY))

    # ② 미러이력 역행
    cur.execute("""SELECT ISNULL(MAX(MAINT_SEQ),19999)+1 FROM nx.PU_T_STOCK_MAINT
                    WHERE MAINT_YMD=? AND MAINT_SEQ>=20000""", YMD)
    mseq = int(cur.fetchone()[0] or 20000)
    cur.execute("""INSERT INTO nx.PU_T_STOCK_MAINT
           (MAINT_YMD,MAINT_SEQ,MAINT_TAG,CUST_CODE,MAT_CODE,MAINT_QTY,REMARKS,
            WH_CUST_CODE,GAGONG_PROC_CODE,ITEM_CODE,
            INSERT_USER_ID,INSERT_DATETIME,INSERT_WINDOW,
            UPDATE_USER_ID,UPDATE_DATETIME,UPDATE_WINDOW)
           VALUES(?,?,'S',?,?,?,?,?,?,?,?,getdate(),'fix260908',?,getdate(),'fix260908')""",
        YMD, mseq, '2096', MAT, -QTY, '오염분 회수(sheet %s)' % SHEET,
        SC, PW, 'ACQ30605001', 'fix260908', 'fix260908')
    print("   ② 미러이력 역행 INSERT  seq={}  qty={:+,.0f}".format(mseq, -QTY))

    # ③ 잔액 차감
    cur.execute("""UPDATE nx.PU_T_MAT_STOCK_WH
                      SET STOCK_QTY=ISNULL(STOCK_QTY,0)-?,
                          UPDATE_USER_ID='fix260908', UPDATE_DATETIME=GETDATE(),
                          UPDATE_WINDOW='fix260908'
                    WHERE RTRIM(MAT_CODE)=? AND CUST_CODE=? AND ISNULL(GAGONG_PROC_CODE,'')=?""",
                QTY, MAT, SC, PW)
    print("   ③ 잔액 UPDATE  −{:,.0f}  (영향 {}행)".format(QTY, cur.rowcount))

    # ④ 고아 명세 삭제
    cur.execute("DELETE FROM nx.set_input_req_dtl WHERE sheet_no=? AND RTRIM(mat_code)=?", SHEET, MAT)
    print("   ④ 고아 명세 DELETE  (영향 {}행)".format(cur.rowcount))

    cn.commit()
    print("\n   ✅ commit 완료")
except Exception as e:
    cn.rollback()
    print("\n   ★오류 — rollback: %s" % str(e)[:200])
    cur.close(); cn.close(); sys.exit(1)

show("정리 후")
print("\n" + "=" * 96)
print(" 완료 — 잔액이 레거시(20)와 같아졌는지 위에서 확인")
print("=" * 96)
cur.close(); cn.close()
