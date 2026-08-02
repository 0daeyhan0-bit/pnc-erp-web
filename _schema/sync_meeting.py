# -*- coding: utf-8 -*-
"""
품질 반성회의록 — nx.meeting 신규 + 레거시 cm_user_meeting_1 이관.
근거: w_cm_user_meeting_200/205, cm_user_meeting_1(372행). 코드마스터 없음(순수 텍스트).
비용 규칙: pay = (member_count+1) * duration_min * 358.3 (프론트/백엔드 자동계산).
멱등: legacy_seq 존재시 skip. 조치사항 5슬롯 1:1 이관(실사용 1~2, 데이터무손실).
대상 DB: PARTNER_ERP_TEST3 (레거시=dbo, 신규=nx).
"""
import sys
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
sys.path.insert(0, r'd:\피앤씨인더스트리\100_AI_AGENT\Projects\New_ERP')
import db_client
ex, q = db_client.execute_query, db_client.run_query
assert db_client.DB_DATABASE.strip().upper() != 'PARTNER_ERP', "운영DB 금지"

# ── 1) nx.meeting DDL (멱등) ──
ddl = """
IF OBJECT_ID('nx.meeting') IS NULL
CREATE TABLE nx.meeting (
  meeting_id    bigint IDENTITY(1,1) PRIMARY KEY,
  legacy_seq    numeric(18) NULL,
  meeting_type  nvarchar(20)  NULL,        -- 유형(반성/아침조회/실장회의 등, 신설 보완)
  meeting_ymd   nvarchar(8)   NULL,        -- 회의일자
  subject       nvarchar(900) NULL,        -- 제목
  member        nvarchar(200) NULL,        -- 참석자
  member_count  int NULL,                  -- 참석인원
  duration_min  int NULL,                  -- 소요시간(분)
  pay_amount    int NULL,                  -- 회의비용(자동계산)
  note          nvarchar(max) NULL,        -- 내용 본문
  note2         nvarchar(max) NULL,        -- 내용 본문2
  organizer     nvarchar(20)  NULL,        -- 작성자/주관
  action1_desc nvarchar(900) NULL, action1_person nvarchar(60) NULL, action1_due nvarchar(60) NULL,
  action2_desc nvarchar(900) NULL, action2_person nvarchar(60) NULL, action2_due nvarchar(60) NULL,
  action3_desc nvarchar(900) NULL, action3_person nvarchar(60) NULL, action3_due nvarchar(60) NULL,
  action4_desc nvarchar(900) NULL, action4_person nvarchar(60) NULL, action4_due nvarchar(60) NULL,
  action5_desc nvarchar(900) NULL, action5_person nvarchar(60) NULL, action5_due nvarchar(60) NULL,
  upd_user      nvarchar(20) NULL,
  upd_dt        datetime NULL CONSTRAINT df_meeting_dt DEFAULT getdate()
);
"""
ex(ddl)
print("nx.meeting 준비 완료")

# ── 2) 이관 (legacy_seq 미존재분만) ──
ins = """
INSERT INTO nx.meeting
  (legacy_seq, meeting_ymd, organizer, subject, member, member_count, duration_min, pay_amount, note, note2,
   action1_desc,action1_person,action1_due, action2_desc,action2_person,action2_due,
   action3_desc,action3_person,action3_due, action4_desc,action4_person,action4_due,
   action5_desc,action5_person,action5_due, upd_user, upd_dt)
SELECT s.seq, s.meeting_ymd, s.insert_user, s.meeting_subject, s.meeting_member, s.meeting_member_count,
   s.meeting_due, s.meeting_pay, s.meeting_note, s.meeting_note_1,
   s.meeting_list_1,s.meeting_person_1,s.meeting_limit_1, s.meeting_list_2,s.meeting_person_2,s.meeting_limit_2,
   s.meeting_list_3,s.meeting_person_3,s.meeting_limit_3, s.meeting_list_4,s.meeting_person_4,s.meeting_limit_4,
   s.meeting_list_5,s.meeting_person_5,s.meeting_limit_5, 'legacy', GETDATE()
FROM dbo.cm_user_meeting_1 s
WHERE NOT EXISTS (SELECT 1 FROM nx.meeting m WHERE m.legacy_seq = s.seq)
"""
ex(ins)

# ── 3) 검증 ──
nx_n = int(q("SELECT COUNT(*) n FROM nx.meeting")['n'][0])
lg_n = int(q("SELECT COUNT(*) n FROM dbo.cm_user_meeting_1")['n'][0])
print(f"이관: nx.meeting {nx_n} / 레거시 {lg_n}  {'OK' if nx_n>=lg_n else 'DIFF'}")
# 비용식 검증 (샘플 5건)
print("\n비용식 검증 (pay =? (인원+1)*시간*358.3):")
print(q("""SELECT TOP 5 legacy_seq, member_count, duration_min, pay_amount,
   CAST(ROUND((member_count+1)*duration_min*358.3,0) AS int) calc
   FROM nx.meeting WHERE member_count IS NOT NULL AND duration_min IS NOT NULL AND pay_amount>0
   ORDER BY legacy_seq DESC""").to_string(index=False))
print("\n제목 상위:")
print(q("SELECT TOP 5 subject, COUNT(*) n FROM nx.meeting GROUP BY subject ORDER BY n DESC").to_string(index=False))
