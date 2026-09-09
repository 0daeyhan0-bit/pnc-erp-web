# -*- coding: utf-8 -*-
"""공정마스터 미러 → 클린 적재 (PR_M_ITEM_PROC_GAGONG → nx.prodinfo_proc)

  ★목적 (CLAUDE.md §1-9-1 클린 단일화)
    「생산공정순서」의 정본을 클린 `nx.prodinfo_proc` 으로 옮긴다.
    지금은 품번 단위 폴백 구조다 — 웹에서 저장한 적 있는 품번만 클린을 읽고
    나머지는 미러(`nx.PR_M_ITEM_PROC_GAGONG`)로 떨어진다(prodinfo.py:191).
    컷오버로 레거시가 은퇴하면 그 폴백 대상이 얼어붙으므로, 미러 전량을 클린에 적재해
    폴백을 걷어낼 수 있게 만든다.

  ★실측 (2026-09-08)
    미러 9,902행 / 4,188품번  (가공공정코드 채워진 품번 4,188 = 100%)
    클린    3행 /     3품번  (웹 편집분 — AJR30133602·AJR73364009·AJR73364010)
    공통분 값 대조 = 가공공정·작업처·ST 전부 불일치 0.00%
    has_gagong=1 품목 4,159 중 공정마스터 누락 0 (=미등록 없음)

  ★안전장치
    · 기본 DRY-RUN. 실제 반영은 --commit
    · ★웹 편집분(이미 클린에 있는 품번)은 **건드리지 않는다** — 웹 값이 최신
    · 적재 전 백업 테이블 자동 생성(nx.bk_prodinfo_proc_<타임스탬프>)
    · 쓰기는 nx 만(§1). 라이브 PARTNER_ERP 무변경. 미러도 무변경(읽기만)
    · 적재 후 전량 재대조를 출력한다

  ★컬럼 매핑 = 미러 24컬럼 중 클린 21컬럼에 1:1 (대문자→소문자)
    KEY_ID 는 미러의 식별자라 그대로 옮긴다. upd_user/upd_at 는 적재 표식.
"""
import sys, os, io
from datetime import datetime

BE = r"c:\Users\박근민\Desktop\NEW_ERP_1\PNC_ERP_Web\backend"
sys.path.insert(0, BE); os.chdir(BE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from common import _nx

COMMIT = "--commit" in sys.argv
TAG = datetime.now().strftime("%y%m%d_%H%M")
BK = "bk_prodinfo_proc_" + TAG

cn = _nx(); cur = cn.cursor()

print("=" * 100)
print(" 공정마스터 미러 → 클린 적재    모드: {}".format("★COMMIT" if COMMIT else "DRY-RUN"))
print("=" * 100)


def q1(sql, *a):
    c = cn.cursor()
    try:
        c.execute(sql, *a) if a else c.execute(sql)
        return c.fetchone()
    finally:
        c.close()


x = q1("SELECT COUNT(*), COUNT(DISTINCT RTRIM(ITEM_CODE)) FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)")
print("\n   미러 nx.PR_M_ITEM_PROC_GAGONG : {:>7,}행 · {:>6,}품번".format(x[0], x[1]))
y = q1("SELECT COUNT(*), COUNT(DISTINCT RTRIM(item_code)) FROM nx.prodinfo_proc WITH(NOLOCK)")
print("   클린 nx.prodinfo_proc         : {:>7,}행 · {:>6,}품번".format(y[0], y[1]))

# 이미 클린에 있는 품번 = 보존 대상
print("\n   [보존 — 웹 편집분(덮지 않음)]")
c = cn.cursor()
c.execute("""SELECT RTRIM(item_code), COUNT(*), ISNULL(RTRIM(MAX(upd_user)),'')
               FROM nx.prodinfo_proc WITH(NOLOCK) GROUP BY RTRIM(item_code) ORDER BY 1""")
keep = [(str(r[0]).strip(), r[1], str(r[2]).strip()) for r in c.fetchall()]
c.close()
for k, n, u in keep:
    print("      {:<24s} {}행  user={}".format(k, n, u))

# 적재 대상 = 미러에 있고 클린에 그 품번이 없는 것
TGT = """FROM nx.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
          WHERE NOT EXISTS(SELECT 1 FROM nx.prodinfo_proc p WITH(NOLOCK)
                            WHERE RTRIM(p.item_code)=RTRIM(m.ITEM_CODE))"""
x = q1("SELECT COUNT(*), COUNT(DISTINCT RTRIM(m.ITEM_CODE)) " + TGT)
print("\n   ★적재 대상 = {:,}행 · {:,}품번".format(x[0], x[1]))
print("     (미러 전량 − 웹 편집분 {}품번)".format(len(keep)))

if not COMMIT:
    print("""
   [실행 계획]
     ① 백업          nx.{}  ← 현재 클린 {}행
     ② INSERT        미러 → nx.prodinfo_proc  ({:,}행)
     ③ 전량 재대조    미러 vs 클린 불일치 0 확인

   ⟹ 실제 반영하려면  --commit""".format(BK, y[0], x[0]))
    cur.close(); cn.close(); sys.exit(0)

print("\n" + "=" * 100)
print(" 실행")
print("=" * 100)
try:
    cur.execute("SELECT * INTO nx.{} FROM nx.prodinfo_proc".format(BK))
    print("   ① 백업 nx.{} 생성 ({}행)".format(BK, cur.rowcount))

    cur.execute("""
INSERT INTO nx.prodinfo_proc
      (item_code, proc_seq, work_code, gagong_proc_code, s_work_code, mach_code,
       work_qty, std_size, mix_gagong, gagong_proc_flag, gagong_proc_seq,
       ready_st, mach_ct, inwon, human_st, tot_st, jp_proc_method, lt_hr,
       key_id, upd_user, upd_at)
SELECT RTRIM(m.ITEM_CODE), m.PROC_SEQ, m.WORK_CODE, m.GAGONG_PROC_CODE, m.S_WORK_CODE, m.MACH_CODE,
       m.WORK_QTY, m.STD_SIZE, m.MIX_GAGONG, m.GAGONG_PROC_FLAG, m.GAGONG_PROC_SEQ,
       m.READY_ST, m.MACH_CT, m.INWON, m.HUMAN_ST, m.TOT_ST, m.JP_PROC_METHOD, m.LT_HR,
       m.KEY_ID, 'seed260908', GETDATE()
  FROM nx.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
 WHERE NOT EXISTS(SELECT 1 FROM nx.prodinfo_proc p WITH(NOLOCK)
                   WHERE RTRIM(p.item_code)=RTRIM(m.ITEM_CODE))""")
    print("   ② INSERT {:,}행".format(cur.rowcount))
    cn.commit()
    print("   ✅ commit")
except Exception as e:
    cn.rollback()
    print("   ★오류 rollback: {}".format(str(e)[:300]))
    cur.close(); cn.close(); sys.exit(1)

print("\n" + "=" * 100)
print(" 적재 후 검증")
print("=" * 100)
x = q1("SELECT COUNT(*), COUNT(DISTINCT RTRIM(item_code)) FROM nx.prodinfo_proc WITH(NOLOCK)")
print("   클린 nx.prodinfo_proc = {:,}행 · {:,}품번".format(x[0], x[1]))
r = q1("""SELECT COUNT(*) FROM (SELECT DISTINCT RTRIM(ITEM_CODE) k FROM nx.PR_M_ITEM_PROC_GAGONG WITH(NOLOCK)) m
           WHERE NOT EXISTS(SELECT 1 FROM nx.prodinfo_proc p WITH(NOLOCK) WHERE RTRIM(p.item_code)=m.k)""")
print("   ★미러 품번인데 클린에 없음 = {:,}   {}".format(r[0], "✅" if r[0] == 0 else "★확인필요"))

J = """FROM nx.PR_M_ITEM_PROC_GAGONG m WITH(NOLOCK)
        JOIN nx.prodinfo_proc p WITH(NOLOCK)
          ON RTRIM(p.item_code)=RTRIM(m.ITEM_CODE) AND p.proc_seq=m.PROC_SEQ"""
t = q1("SELECT COUNT(*) " + J)[0]
print("\n   공통 (품번,공정SEQ) = {:,}".format(t))
for cm, cc, lbl in (("GAGONG_PROC_CODE", "gagong_proc_code", "가공공정"),
                    ("S_WORK_CODE", "s_work_code", "작업처"),
                    ("TOT_ST", "tot_st", "ST(초)"),
                    ("LT_HR", "lt_hr", "LT(Hr)"),
                    ("JP_PROC_METHOD", "jp_proc_method", "전표")):
    n = q1("""SELECT COUNT(*) {} WHERE ISNULL(RTRIM(CAST(m.{} AS varchar(50))),'')
                                   <>ISNULL(RTRIM(CAST(p.{} AS varchar(50))),'')""".format(J, cm, cc))[0]
    print("   {:<10s} 불일치 {:>6,}  ({:.2f}%)  {}".format(
        lbl, n, 100.0*n/max(1, t), "✅" if n == 0 else "★"))

print("\n   [보존 확인 — 웹 편집분이 그대로인가]")
for k, n, u in keep:
    z = q1("SELECT COUNT(*), ISNULL(RTRIM(MAX(upd_user)),'') FROM nx.prodinfo_proc WHERE RTRIM(item_code)=?", k)
    print("      {:<24s} {}행 user={}  {}".format(
        k, z[0], str(z[1]).strip(), "✅ 보존" if str(z[1]).strip() == u else "★변경됨"))

print("\n   ※롤백: DELETE FROM nx.prodinfo_proc; INSERT INTO nx.prodinfo_proc SELECT * FROM nx.{}".format(BK))
cur.close(); cn.close()
