-- 납품 포장/적재 (BOM 3분리의 '납품' 축) — nx.delivery_pack
-- 개당/박스당/파렛트당/발주당 소요 + 적재수량(units_per) + CEILING(발주÷적재수량, 발주단위 올림)
-- 설치박스처럼 LG품번·시방·이력 관리대상은 is_bom=1. 2026-07-22 생성.
CREATE TABLE nx.delivery_pack (
  id INT IDENTITY(1,1) PRIMARY KEY,
  item_code   NVARCHAR(40)  NOT NULL,           -- 대상 완제품
  seq         INT           NOT NULL DEFAULT 1,
  pack_item   NVARCHAR(40)  NULL,               -- 포장자재 코드(박스/파렛트/앵글/비닐)
  pack_name   NVARCHAR(100) NULL,
  pack_level  NVARCHAR(20)  NULL,               -- 위계: 박스/파렛트/앵글/비닐/기타
  use_basis   NVARCHAR(20)  NOT NULL,           -- 개당/박스당/파렛트당/발주당
  qty_per     DECIMAL(18,4) NOT NULL DEFAULT 1, -- 기준당 소요수량
  units_per   INT           NULL,               -- 적재수량(LG지정, 이 포장1개에 담는 제품수)
  ceiling_flag BIT          NOT NULL DEFAULT 0, -- CEILING(발주수량/units_per) 올림
  is_bom      BIT           NOT NULL DEFAULT 0, -- 설치박스 등 BOM관리대상(LG품번·시방·이력)
  remarks     NVARCHAR(200) NULL,
  upd_user    NVARCHAR(40)  NULL,
  upd_dt      DATETIME      NOT NULL DEFAULT GETDATE()
);
-- 소요계산(엔진): 개당→qty_per×발주 / 발주당→qty_per / 박스·파렛트당→qty_per×(ceiling? CEIL(발주/units_per):발주/units_per)
-- 예 발주50(박스적재50·파렛트적재400·앵글파렛트당4): 박스1·파렛트1·앵글4. 발주450: 박스9·파렛트2·앵글8.
-- 백엔드 /api/delivery/list·save·delete·calc . 화면 개발›납품 포장/적재(SCREEN.delivery).
