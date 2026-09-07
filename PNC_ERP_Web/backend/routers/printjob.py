"""생산전표출력관리(490) — 무음 자동출력용 인쇄물 생성.

왜 필요한가
-----------
웹(브라우저)은 보안상 "어느 프린터로 보낼지"를 코드로 지정할 수 없어서, 지금까지는
인쇄창을 띄우고 직원이 매번 프린터를 골라야 했다. 가간판(A4)·라벨(40×20)이 서로 다른
USB 프린터에 물려 있는 현장에서는 매번 오출력 위험이 있다.

  [웹 490] ─▶ 이 라우터(PDF/TSPL 생성) ─▶ [작업 PC 트레이 에이전트] ─▶ 지정 프린터 무음출력
                                            (_tools/pnc_print_agent)

★웹은 프린터 이름을 모른다. kind(kanban/label)만 보내고 실제 프린터는 그 PC 의 설정이 정한다.
  PC 마다 프린터 구성이 달라도 웹 코드는 하나로 유지된다.

★양식은 화면(screens.prod.js)의 HTML/CSS 실측 레이아웃을 mm 단위로 옮긴 것이다.
  브라우저 인쇄와 달리 여백·인쇄불가영역에 좌우되지 않아 잘림이 구조적으로 없다
  (화면 쪽은 2026-08-28·08-31 두 차례 상단 잘림 교정 이력이 있다).

의존성: PyMuPDF(fitz) — 이미 설치돼 있음. 미설치 시 501 로 명확히 알린다.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from routers.prodsheet import (prodsheet_kanban_print, prodsheet_label_print,
                               _qr_code)

router = APIRouter()

MM = 72.0 / 25.4          # mm → pt(1/72인치)
_FONT_CACHE: dict[str, str | None] = {}


# ───────────────────────────── 공통 ─────────────────────────────
def _fitz():
    """PyMuPDF 모듈. ★신 이름(pymupdf) 우선 — 구 `fitz` 는 deprecated(제거 예정, 경고 발생).

    ※미설치면 501 로 명확히 알린다. 화면은 이 실패를 받아 **기존 인쇄창으로 폴백**하므로
      현장이 멈추지는 않지만, 자동출력은 안 된다 → 백엔드 PC 마다 설치돼 있어야 한다
      (실측: 8011 로 띄운 개발 백엔드에 없어서 인쇄창이 떴다. requirements.txt 에 등재).
    """
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz
        return fitz
    except ImportError:
        raise HTTPException(501, "PyMuPDF 미설치 — pip install PyMuPDF")


def _font_path(bold: bool = False) -> str | None:
    """한글 폰트(맑은 고딕) 경로. 화면 양식이 '맑은 고딕'이라 동일하게 맞춘다."""
    key = "bd" if bold else "rg"
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    names = ["malgunbd.ttf", "malgun.ttf"] if bold else ["malgun.ttf", "malgunbd.ttf"]
    win = os.environ.get("WINDIR", r"C:\Windows")
    found = None
    for nm in names:
        p = os.path.join(win, "Fonts", nm)
        if os.path.exists(p):
            found = p
            break
    _FONT_CACHE[key] = found
    return found


_MEASURE_CACHE: dict = {}


def _measure_font(fontfile: str):
    """폭 측정용 Font 객체(캐시). 생성이 무거워 매 텍스트마다 만들면 안 된다."""
    f = _MEASURE_CACHE.get(fontfile)
    if f is None:
        f = _fitz().Font(fontfile=fontfile)
        _MEASURE_CACHE[fontfile] = f
    return f


def _finish(doc) -> bytes:
    """PDF 직렬화 + 압축.

    ★맑은 고딕은 파일 하나가 13MB 다. 그대로 embed 하면 라벨 한 장짜리 PDF 가 26MB 가 돼
      현장 PC 로 보내는 것 자체가 부담이다(실측). subset_fonts() 로 **실제 쓴 글자만** 남기면
      수십 KB 로 줄어든다. 구버전 PyMuPDF 에 없을 수 있어 실패해도 출력은 계속되게 한다.
    """
    try:
        doc.subset_fonts()
    except Exception:
        pass
    try:
        out = doc.tobytes(deflate=True, garbage=4)
    except TypeError:              # 구버전 시그니처 대비
        out = doc.tobytes()
    doc.close()
    return out


def _mkdoc(w_mm: float, h_mm: float):
    """지정 mm 크기의 빈 PDF 문서 생성."""
    fitz = _fitz()
    doc = fitz.open()
    doc.__pnc_size = (w_mm * MM, h_mm * MM)      # type: ignore[attr-defined]
    return doc


def _newpage(doc):
    w, h = doc.__pnc_size                        # type: ignore[attr-defined]
    return doc.new_page(width=w, height=h)


class Pen:
    """페이지에 mm 좌표로 그리는 얇은 헬퍼(표·텍스트).

    ★HTML 표를 그대로 옮기기 위해 '셀' 개념만 제공한다. 좌표는 전부 mm.
    """

    def __init__(self, page, doc):
        self.p = page
        self.doc = doc
        self.fr = _font_path(False)
        self.fb = _font_path(True)
        # 폰트를 문서에 등록(한 번만)
        self._fn_r = "malgun" if self.fr else "helv"
        self._fn_b = "malgunbd" if self.fb else "hebo"

    def rect(self, x, y, w, h, width=0.4, fill=None):
        fitz = _fitz()
        r = fitz.Rect(x * MM, y * MM, (x + w) * MM, (y + h) * MM)
        self.p.draw_rect(r, color=(0, 0, 0), fill=fill, width=width)
        return r

    def text(self, x, y, s, size=9, bold=False, align="left", w=None, color=(0, 0, 0)):
        """(x,y)=텍스트 좌상단 mm. align 이 center/right 면 w(폭 mm) 안에서 정렬."""
        s = "" if s is None else str(s)
        if not s:
            return
        fitz = _fitz()
        fontfile = self.fb if bold else self.fr
        fontname = self._fn_b if bold else self._fn_r
        tw = None
        if fontfile:
            # 폰트파일을 쓰면 get_text_length 가 이름을 모르므로 Font 로 잰다.
            # ★Font 객체 생성은 13MB 파일 파싱이라 비싸다 — 반드시 캐시(장당 수십 회 호출).
            try:
                tw = _measure_font(fontfile).text_length(s, fontsize=size)
            except Exception:
                tw = size * 0.5 * len(s)
        else:
            try:
                tw = fitz.get_text_length(s, fontname=fontname, fontsize=size)
            except Exception:
                tw = None
        px = x * MM
        if align in ("center", "right") and w:
            avail = w * MM
            tw = tw if tw is not None else size * 0.5 * len(s)
            px = x * MM + (avail - tw) / 2 if align == "center" else x * MM + (avail - tw)
        # baseline 보정 — y 는 셀 상단이므로 폰트 크기만큼 내린다
        self.p.insert_text((px, y * MM + size * 0.80), s, fontsize=size, color=color,
                           fontname=fontname, fontfile=fontfile)

    def cell(self, x, y, w, h, s="", size=9, bold=False, align="center", fill=None,
             pad=1.0, valign="middle"):
        """테두리 있는 셀 + 가운데(기본) 정렬 텍스트."""
        self.rect(x, y, w, h, fill=fill)
        if s == "" or s is None:
            return
        ty = y + (h - size / MM * 1.0) / 2 if valign == "middle" else y + pad
        ty = max(y + 0.2, ty)
        if align == "left":
            self.text(x + pad, ty, s, size, bold, "left")
        else:
            self.text(x, ty, s, size, bold, align, w)

    def image(self, x, y, w, h, png: bytes, keep=True):
        fitz = _fitz()
        r = fitz.Rect(x * MM, y * MM, (x + w) * MM, (y + h) * MM)
        self.p.insert_image(r, stream=png, keep_proportion=keep)


# ───────────────────────── 바코드 이미지 ─────────────────────────
def _qr_png(text: str, scale: int = 6, border: int = 1) -> bytes:
    from io import BytesIO
    import qrcode
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=max(1, scale), border=max(0, border))
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("1")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _c128_png(text: str, h: int = 80, scale: int = 2, quiet: int = 8) -> bytes:
    """Code128-B — ready.py 의 구현과 동일 규칙(스캐너 호환 유지)."""
    from io import BytesIO
    from PIL import Image
    from routers.ready import _C128_PAT, _C128_STOP
    s = "".join(ch for ch in str(text or "") if 32 <= ord(ch) <= 126)
    if not s:
        raise HTTPException(400, "빈 바코드 문자열")
    codes = [104] + [ord(ch) - 32 for ch in s]
    chk = codes[0]
    for i, c in enumerate(codes[1:], start=1):
        chk += c * i
    codes.append(chk % 103)
    bits = "".join(_C128_PAT[c] for c in codes) + _C128_STOP
    w = (len(bits) + quiet * 2) * scale
    img = Image.new("1", (w, h), 1)
    px = img.load()
    x = quiet * scale
    for b in bits:
        if b == "1":
            for dx in range(scale):
                for y in range(h):
                    px[x + dx, y] = 0
        x += scale
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ───────────────────────────── 가간판 PDF ─────────────────────────────
_WD = ["월", "화", "수", "목", "금", "토", "일"]


def _ymdw(s: str) -> str:
    """YYMMDD → 'YY/MM/DD(요일)' — 화면(screens.prod.js ymdw)과 동일 표기."""
    d = "".join(c for c in str(s or "") if c.isdigit())
    if len(d) < 6:
        return str(s or "")
    try:
        dt = datetime(2000 + int(d[0:2]), int(d[2:4]), int(d[4:6]))
        return f"{d[0:2]}/{d[2:4]}/{d[4:6]}({_WD[dt.weekday()]})"
    except Exception:
        return f"{d[0:2]}/{d[2:4]}/{d[4:6]}"


def _nf(v) -> str:
    try:
        return f"{int(round(float(v or 0))):,}"
    except Exception:
        return str(v or "")


def build_kanban_pdf(cards: list[dict]) -> bytes:
    """가간판 PDF — 210×110mm, 1장=1페이지.

    레이아웃은 화면 양식(screens.prod.js card())의 실측 비율을 그대로 옮겼다:
      1행 라인 / 도번 / 수량      (높이 22mm)
      2행 박스종류·표준포장수·바코드
      3행 생산날짜·엘지날짜·품명 / 공정순서
      4행 불량이력·검수란 / 시방이력
      5행 용접자·검사자
      푸터 출력일시·발행자 / 용접전표번호
    ★상하 여백은 6/3mm — 프린터 인쇄불가영역(보통 3~5mm)보다 크게 두어 첫 행이 잘리지 않게 한다.
    """
    doc = _mkdoc(210, 110)
    ML, MT = 3.0, 6.0                 # 좌·상 여백(mm)
    W = 210 - ML * 2                  # 본문 폭 204mm

    for c in cards:
        page = _newpage(doc)
        d = Pen(page, doc)
        y = MT

        # ── 1행: 라인 / 도번 / 수량 (h=22mm)
        h1 = 22.0
        w_line, w_item = W * 0.12, W * 0.58
        w_qty = W - w_line - w_item
        # ★도번·수량 확대(2026-09-04 사용자 요청 — 레거시 실물이 이 비율이다).
        #   화면(screens.prod.js)과 반드시 같은 크기를 유지할 것. 여기만 27pt 로 남으면
        #   에이전트 설치 PC 의 인쇄물만 작게 나온다.
        #   도번은 길이가 제각각(11~17자)이라 고정 pt 로 키우면 긴 도번이 셀을 넘친다.
        #   굵은 글꼴 글자폭 ≈ 0.62em → 셀폭(w_item mm)에 맞는 pt 를 역산하고 24~37pt 로 제한.
        _it = str(c.get("item", "") or "")
        _sz = 48.0 if not _it else max(26.0, min(48.0, (w_item - 4) * MM / (len(_it) * 0.60)))
        # ★라인 — 화면(screens.prod.js) 38px 과 같은 급. 굵게.
        d.cell(ML, y, w_line, h1, c.get("line", ""), size=26, bold=True)
        d.cell(ML + w_line, y, w_item, h1, _it, size=_sz, bold=True)
        d.cell(ML + w_line + w_item, y, w_qty, h1, _nf(c.get("qty")), size=48, bold=True)
        y += h1

        # ── 2행: (빈칸) 박스종류 / 표준포장수 / 바코드 (h=11mm)
        h2 = 11.0
        xs = [W * 0.12, W * 0.14, W * 0.18, W * 0.16, W * 0.10]
        x = ML
        d.cell(x, y, xs[0], h2)                                             # 좌측 빈칸
        x += xs[0]
        d.cell(x, y, xs[1], h2, "박스종류", size=9, bold=True); x += xs[1]
        d.cell(x, y, xs[2], h2, c.get("pack_kind", ""), size=10); x += xs[2]
        d.cell(x, y, xs[3], h2, "표준포장수", size=9, bold=True); x += xs[3]
        d.cell(x, y, xs[4], h2, (str(c.get("pack_qty") or "") if c.get("pack_qty") else ""),
               size=10, bold=True); x += xs[4]
        w_bc = ML + W - x
        d.rect(x, y, w_bc, h2)
        bar = str(c.get("barcode") or "")
        if bar:
            try:
                # ★바코드 + 번호 — 셀 11mm 안에 겹치지 않게 세로로 나눈다(2026-09-04).
                #   종전 8.0mm 바코드 + y+h2-2.9 텍스트는 서로 겹쳤다(사용자 지적).
                #   바코드 0.8~7.0mm(6.2mm) / 번호 baseline 9.6mm → 사이 2.6mm 여유.
                #   번호는 7.5pt 굵게 — 바코드 줄무늬와 구분되게(사용자 요청).
                d.image(x + 1.5, y + 0.8, w_bc - 3, 6.2, _c128_png(bar))
                d.text(x, y + 9.6, bar, size=7.5, bold=True, align="center", w=w_bc)
            except Exception:
                d.text(x, y + 4, bar, size=7, align="center", w=w_bc)
        y += h2

        # ── 3행: 생산날짜 / 엘지날짜 / 품명 (h=9mm)
        h3 = 9.0
        cols = [W * 0.12, W * 0.20, W * 0.14, W * 0.20, W * 0.08]
        x = ML
        d.cell(x, y, cols[0], h3, "생산날짜", size=9, bold=True); x += cols[0]
        d.cell(x, y, cols[1], h3, _ymdw(c.get("plan_ymd")), size=10, bold=True); x += cols[1]
        d.cell(x, y, cols[2], h3, "엘지날짜", size=9, bold=True); x += cols[2]
        d.cell(x, y, cols[3], h3, _ymdw(c.get("plan_ymd")), size=10, bold=True); x += cols[3]
        d.cell(x, y, cols[4], h3, "품명", size=9, bold=True); x += cols[4]
        d.cell(x, y, ML + W - x, h3, c.get("nm", ""), size=8, align="left", pad=1.2)
        y += h3

        # 공정순서
        d.cell(ML, y, cols[0], h3, "공정순서", size=9, bold=True)
        d.cell(ML + cols[0], y, W - cols[0], h3, c.get("proc_nm", ""), size=10, bold=True,
               align="left", pad=1.5)
        y += h3

        # ── 4행: 불량이력 / 검수란, 시방이력 (각 h=14mm)
        h4 = 14.0
        c1, c3 = W * 0.12, W * 0.26
        c2 = W - c1 - c3
        d.cell(ML, y, c1, h4, "불량이력", size=11, bold=True)
        d.cell(ML + c1, y, c2, h4)
        d.cell(ML + c1 + c2, y, c3, h4, "검수란", size=10, bold=True)
        y += h4
        d.cell(ML, y, c1, h4, "시방이력", size=11, bold=True)
        d.cell(ML + c1, y, c2, h4)
        d.cell(ML + c1 + c2, y, c3, h4)
        y += h4

        # ── 5행: 용접자 / 검사자 (h=9mm)
        h5 = 9.0
        e = [W * 0.12, W * 0.26, W * 0.14, W * 0.22]
        x = ML
        d.cell(x, y, e[0], h5, "용접자", size=9, bold=True); x += e[0]
        d.cell(x, y, e[1], h5, c.get("prod_worker", ""), size=10, bold=True); x += e[1]
        d.cell(x, y, e[2], h5, "검사자", size=9, bold=True); x += e[2]
        d.cell(x, y, e[3], h5, c.get("insp_worker", ""), size=10, bold=True); x += e[3]
        d.cell(x, y, ML + W - x, h5)
        y += h5

        # ── 푸터(테두리 없음)
        pdt = str(c.get("print_dt") or "")[2:16].replace("T", " ").replace("-", "/")
        d.text(ML + 1, y + 0.8, f"출력일시 : {pdt} {c.get('print_user','')}", size=7, bold=True)
        d.text(ML, y + 0.8, f"용접전표번호 : {c.get('sheet_no_fmt','')}", size=7, bold=True,
               align="right", w=W - 1)

    out = _finish(doc)
    return out


# ───────────────────────────── 라벨 ─────────────────────────────
def build_label_pdf(j: dict) -> bytes:
    """제품스티커 PDF — 40×20mm, 1장=1페이지.
       양식(QR3 실측): 좌 QR / PNC Industry / {출력일자} {라벨번호}-{일련4} / n / 전체 / 도번 / 용접사/검사자
    """
    doc = _mkdoc(40, 20)
    labels = j.get("labels") or []
    tot = j.get("org_qty") or j.get("qty") or len(labels)
    for L in labels:
        page = _newpage(doc)
        d = Pen(page, doc)
        # 좌측 QR 11mm (화면 .lb .qr 와 동일 — 17→13mm(260904) → 11mm(260907 "1단계 더")).
        #   ★화면 CSS·TSPL 과 **반드시 같은 값**을 유지할 것. 한 경로만 남으면
        #     "화면에서는 줄었는데 실제 인쇄물은 그대로"가 된다(에이전트 설치 PC 는 이쪽으로 출력).
        #   ★11mm 안전근거 = 실측: 최악 데이터(한글도번 24자)가 QR 버전3(29모듈)이라
        #     border 포함 31칸 → 셀 0.355mm. 열전사 권장하한 0.33mm 를 넘는다.
        #     10mm 는 0.323mm 로 하한에 닿으므로 더 줄이지 않는다(screens.prod.js 주석에 표 있음).
        #   세로 중앙정렬 — 라벨 높이 20mm 기준 (20-11)/2 = 4.5mm.
        try:
            d.image(1.2, 4.5, 11.0, 11.0, _qr_png(L.get("qr", ""), scale=6, border=1))
        except Exception:
            d.text(1.2, 8, "QR?", size=5)
        # 우측 텍스트 — 화면 .tx 의 5줄. QR 이 줄어든 만큼 왼쪽으로 당기고 폭을 넓힌다.
        tx, tw = 13.0, 26.0
        d.text(tx, 2.0, "PNC Industry", size=4.4, bold=True, align="center", w=tw)
        d.text(tx, 5.4, str(L.get("disp", "")), size=4.0, align="center", w=tw)
        d.text(tx, 8.8, f"{L.get('n','')} / {tot}", size=4.4, bold=True, align="center", w=tw)
        d.text(tx, 12.2, str(j.get("item", "")), size=5.0, bold=True, align="center", w=tw)
        d.text(tx, 15.8, f"{j.get('worker','')}/{j.get('inspector','')}", size=3.8,
               align="center", w=tw)
    return _finish(doc)


# ★라벨 갭(라벨과 라벨 사이 간격) — 현장 실측 3mm(2026-09-07).
#   종전 2mm 로는 프린터가 라벨 시작점을 잘못 잡아 인쇄가 위로 밀리고
#   빈 라벨이 섞여 나왔다. 용지를 바꾸면 이 값만 고치면 된다.
LABEL_GAP_MM = 3

# ★GAPDETECT — 프린터가 갭을 **실측**해 라벨 시작점을 다시 잡는다(2026-09-07).
#   GAP 3mm 로 고치고 헤더를 1회로 줄여 빈 라벨은 사라졌으나, 여전히 내용이
#   라벨 경계를 넘어 밀리는 현상이 남았다(현장 사진 — 아래 한 장만 정상).
#   좌표는 y=14~130dot 으로 20mm(160dot) 안에 들어가므로 좌표 문제가 아니라
#   **프린터가 라벨의 시작 위치를 모르는 것**이다.
#
#   ★측정값은 프린터 내부(EEPROM)에 저장되므로 **한 번만 하면 된다.**
#     그래서 매 작업 넣지 않고 **서버 기동 후 첫 출력 1회**만 보낸다 —
#     라벨 낭비(측정 시 1~2장 배출)를 그 1회로 끝낸다.
#   ※용지를 바꿨을 때 다시 하려면 백엔드를 재기동하거나
#     아래 _GAP_DONE 을 False 로 되돌리면 된다.
LABEL_GAPDETECT = True
_GAP_DONE = False          # 이번 프로세스에서 이미 측정을 보냈는가


def build_label_tspl(j: dict, darkness: int = 8, speed: int = 3) -> str:
    """제품스티커 TSPL — TSC/Bixolon 계열 직송용.

    ★프린터가 QR·텍스트를 직접 그리므로 래스터(PDF)보다 훨씬 선명하고 빠르다.
      40×20mm = 8dot/mm 기준 320×160 dot.
    ★한글(용접사/검사자 이름)은 프린터 내장 폰트로 안 나올 수 있어
      TSPL 유니코드 지정(CODEPAGE UTF-8)을 준다. 그래도 안 나오면 화면에서 PDF 모드로 전환.
    """
    labels = j.get("labels") or []
    tot = j.get("org_qty") or j.get("qty") or len(labels)
    item = str(j.get("item", ""))
    wi = f"{j.get('worker','')}/{j.get('inspector','')}"
    # ★★용지 설정은 **작업 전체에 한 번만** 보낸다(2026-09-07 교정).
    #   실사용 오류 — 라벨이 위쪽 경계를 넘어 잘리고 **빈 라벨이 2장씩 섞여** 나왔다.
    #   원인 두 가지
    #     ① GAP 2mm 인데 실물 라벨 간격은 **3mm** 였다(현장 실측).
    #        갭이 틀리면 프린터가 라벨 시작점을 잘못 잡아 인쇄가 밀린다.
    #     ② SIZE/GAP 을 **라벨 한 장마다** 다시 보냈다. TSPL 에서 이 두 명령은
    #        용지 파라미터 재설정이라, 매 장 재설정하면 위치가 어긋나고
    #        프린터가 용지를 과하게 밀어 빈 라벨이 나온다.
    #   ⟹ 헤더(SIZE·GAP·DENSITY·SPEED·DIRECTION·CODEPAGE)는 1회,
    #      장마다 반복하는 것은 CLS ~ PRINT 뿐이다.
    #   ※그래도 밀리면 프린터 자체 캘리브레이션(전원 켠 뒤 FEED 길게 눌러 용지 자동감지)을
    #     한 번 해야 한다 — 센서 기준값은 프린터에 저장된다.
    out = [
        "SIZE 40 mm,20 mm",
        f"GAP {LABEL_GAP_MM} mm,0",
        f"DENSITY {max(0, min(int(darkness), 15))}",
        f"SPEED {max(1, min(int(speed), 8))}",
        "DIRECTION 1",
        "CODEPAGE UTF-8",
    ]
    global _GAP_DONE
    if LABEL_GAPDETECT and not _GAP_DONE:
        out.append("GAPDETECT")      # ★첫 1회만 — 측정값은 프린터에 저장된다
        _GAP_DONE = True
    for L in labels:
        out += [
            "CLS",
            # 좌측 QR — cell width 3.
            #   ★실측(2026-09-07): 최악 데이터(한글도번 24자)가 QR 버전3=29모듈이라
            #     border1 포함 31칸 × 3dot = 93dot = **11.6mm**. 즉 TSPL 은 이미 11mm 급이다
            #     (종전 주석의 "≈13mm 상당"은 틀린 계산이었다 — 화면 13mm 와 맞춘다고 적었으나
            #      실제로는 그때도 11.6mm 로 나가고 있었다).
            #   ⟹ 화면·PDF 를 11mm 로 내린 지금이 오히려 세 경로가 일치하는 상태다.
            #   ★cell=2 로 더 내리지 말 것 — 셀 0.250mm 로 열전사 권장하한 0.33mm 미만이다
            #     (cell=3 은 0.375mm 로 안전). 더 줄여야 하면 QR 데이터를 줄여야 한다.
            #   세로 중앙정렬 — (20mm − 11.6mm)/2 ≈ 4.2mm → 34dot.
            f'QRCODE 10,34,M,3,A,0,"{L.get("qr","")}"',
            # 텍스트 시작 x — QR(10dot 시작 + 93dot) 뒤. 104dot=13mm 로 PDF(tx=13.0)와 맞춘다.
            f'TEXT 104,14,"2",0,1,1,"PNC Industry"',
            f'TEXT 104,42,"1",0,1,1,"{L.get("disp","")}"',
            f'TEXT 104,66,"2",0,1,1,"{L.get("n","")} / {tot}"',
            f'TEXT 104,96,"3",0,1,1,"{item}"',
            f'TEXT 104,130,"1",0,1,1,"{wi}"',
            "PRINT 1,1",
        ]
    return "\r\n".join(out) + "\r\n"


# ───────────────────────────── 엔드포인트 ─────────────────────────────
@router.get("/api/print/kanban")
def print_kanban(box_no: str = Query(..., description="간판번호(콤마로 여러 장)")):
    """가간판 인쇄물(PDF, base64). 에이전트가 이걸 받아 지정 프린터로 무음 출력한다."""
    nos = [x.strip() for x in str(box_no or "").split(",") if x.strip()]
    if not nos:
        raise HTTPException(400, "간판번호 필수")
    cards = []
    for bn in nos:
        j = prodsheet_kanban_print(box_no=bn)
        if not j.get("ok"):
            raise HTTPException(404, j.get("detail") or f"간판 {bn} 조회 실패")
        cards.append(j)
    pdf = build_kanban_pdf(cards)
    return {"ok": True, "kind": "kanban", "cnt": len(cards),
            "doc": f"가간판 {cards[0].get('item','')} ({len(cards)}장)",
            "pdf": base64.b64encode(pdf).decode("ascii")}


@router.get("/api/print/label")
def print_label(print_seq: str = Query(...), start_no: int = Query(0), end_no: int = Query(0),
                worker: str = Query(""), inspector: str = Query(""),
                mode: str = Query("pdf", description="pdf | tspl"),
                darkness: int = Query(8), speed: int = Query(3)):
    """제품스티커 인쇄물. mode=pdf 면 PDF(base64), mode=tspl 이면 TSPL 명령어 문자열."""
    j = prodsheet_label_print(print_seq=print_seq, start_no=start_no, end_no=end_no,
                              worker=worker, inspector=inspector)
    if not j.get("ok"):
        raise HTTPException(404, j.get("detail") or "라벨 조회 실패")
    doc = f"제품스티커 {j.get('item','')} ({j.get('qty',0)}장)"
    if str(mode).lower() == "tspl":
        return {"ok": True, "kind": "label", "mode": "tspl", "cnt": j.get("qty", 0), "doc": doc,
                "tspl": build_label_tspl(j, darkness, speed)}
    return {"ok": True, "kind": "label", "mode": "pdf", "cnt": j.get("qty", 0), "doc": doc,
            "pdf": base64.b64encode(build_label_pdf(j)).decode("ascii")}


# ───────────────────── 에이전트 배포(다운로드) ─────────────────────
#   ★USB 로 돌리면 반드시 빠지는 PC 가 생기고 버전 올릴 때도 문제가 된다.
#     화면에서 바로 받게 한다 — 받아서 더블클릭하면 자가설치된다.
#   exe(67MB)는 git 에 넣지 않는다(_tools/pnc_print_agent/.gitignore).
#   운영 배포 시 아래 경로에 exe 를 복사해 두면 이 엔드포인트가 서빙한다.
AGENT_EXE_NAME = "PNC프린터에이전트.exe"


def _agent_exe_path() -> str | None:
    """배포용 exe 를 찾는다. 없으면 None."""
    here = os.path.dirname(os.path.abspath(__file__))            # backend/routers
    root = os.path.dirname(os.path.dirname(here))                # PNC_ERP_Web
    repo = os.path.dirname(root)                                 # 저장소 루트
    for p in (
        os.path.join(root, "download", AGENT_EXE_NAME),          # ★운영 배포 위치(권장)
        os.path.join(repo, "_tools", "pnc_print_agent", "dist", AGENT_EXE_NAME),  # 개발 PC 빌드본
    ):
        if os.path.exists(p):
            return p
    return None


@router.get("/api/print/agent-info")
def print_agent_info():
    """설치파일이 준비돼 있는지 · 크기 · 빌드일시. 화면의 안내문에 쓴다."""
    p = _agent_exe_path()
    if not p:
        return {"ok": False, "available": False,
                "detail": "설치파일이 서버에 없습니다(관리자에게 문의)."}
    stt = os.stat(p)
    return {"ok": True, "available": True, "name": AGENT_EXE_NAME,
            "size_mb": round(stt.st_size / 1024 / 1024, 1),
            "built": datetime.fromtimestamp(stt.st_mtime).strftime("%Y-%m-%d %H:%M")}


AGENT_ZIP_NAME = "PNC프린터에이전트.zip"


def _agent_zip_path() -> str | None:
    """배포용 zip 을 만들어(없거나 낡았으면) 그 경로를 준다. exe 가 없으면 None.

    ★왜 zip 인가 (2026-09-07 현장 오류)
      서명 없는 .exe 를 브라우저로 직접 받으면 SmartScreen 이
        "PNC프린터에이전트.exe은(는) 일반적으로 다운로드되지 않습니다"
      로 막아, 사용자가 [유지]→[자세히]→[무시하고 계속] 을 뚫어야 했다.
      PC 마다 이 과정을 시키면 반드시 빠지는 사람이 생긴다.
      zip 으로 감싸면 다운로드 단계 경고가 사라진다(실행 시 1회만 뜬다).

    ★캐시 — exe 가 67MB 라 매 요청 압축하면 느리다.
      zip 이 exe 보다 새것이면 그대로 재사용하고, 낡았으면 다시 만든다.
      (에이전트를 새로 빌드해 exe 를 갈아끼우면 자동으로 다시 압축된다)
    """
    import zipfile
    exe = _agent_exe_path()
    if not exe:
        return None
    zp = os.path.join(os.path.dirname(exe), AGENT_ZIP_NAME)
    try:
        if os.path.exists(zp) and os.path.getmtime(zp) >= os.path.getmtime(exe):
            return zp
        # ZIP_DEFLATED — exe 는 이미 압축돼 있어 크게 줄진 않지만, 전송량이 조금 준다.
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe, AGENT_EXE_NAME)
        return zp
    except Exception:
        return None      # 압축 실패(권한·디스크) 시엔 exe 직접 제공으로 폴백


@router.get("/api/print/agent-download")
def print_agent_download(raw: str = Query("")):
    """프린터 에이전트 설치파일 다운로드.

    기본 = zip(브라우저 경고 없음). 압축 풀고 더블클릭하면 자동 설치된다.
    raw=1 이면 종전처럼 exe 를 직접 준다(zip 을 못 만든 경우의 폴백 포함).
    """
    from fastapi.responses import FileResponse
    from urllib.parse import quote
    if not str(raw).strip():
        zp = _agent_zip_path()
        if zp:
            return FileResponse(
                zp, media_type="application/zip",
                headers={"Content-Disposition":
                         "attachment; filename=\"PNC_PrintAgent.zip\"; "
                         f"filename*=UTF-8''{quote(AGENT_ZIP_NAME)}"})
    p = _agent_exe_path()
    if not p:
        raise HTTPException(404, "설치파일이 서버에 없습니다. 관리자에게 문의하세요.")
    # ★한글 파일명 — RFC5987(filename*) 로 줘야 브라우저가 안 깨뜨린다.
    fn = quote(AGENT_EXE_NAME)
    return FileResponse(
        p, media_type="application/octet-stream",
        headers={"Content-Disposition":
                 f"attachment; filename=\"PNC_PrintAgent.exe\"; filename*=UTF-8''{fn}"})


@router.get("/api/print/selftest")
def print_selftest(kind: str = Query("kanban")):
    """양식 확인용 더미 인쇄물(DB 조회 없음). 에이전트·용지 점검에 쓴다."""
    if kind == "label":
        item = "AJR73324403"
        labels = [{"n": i, "seq": i, "qr": _qr_code(item, "260904", i),
                   "disp": f"260904 9999-{i:04d}"} for i in (1, 2)]
        j = {"ok": True, "item": item, "qty": 2, "org_qty": 2, "labels": labels,
             "worker": "테스트", "inspector": "검사"}
        return {"ok": True, "kind": "label", "mode": "pdf", "cnt": 2, "doc": "라벨 테스트",
                "pdf": base64.b64encode(build_label_pdf(j)).decode("ascii")}
    card = {"line": "06라인", "item": "AJR73324403", "qty": 15, "pack_kind": "TP-01",
            "pack_qty": 20, "barcode": "GP00268017", "plan_ymd": "260901",
            "nm": "Supporter Assembly", "proc_nm": "06라인(용접)-06라인(조립)",
            "prod_worker": "홍길동", "insp_worker": "김검사",
            "print_dt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "print_user": "테스트", "sheet_no_fmt": "00268017"}
    return {"ok": True, "kind": "kanban", "cnt": 1, "doc": "가간판 테스트",
            "pdf": base64.b64encode(build_kanban_pdf([card])).decode("ascii")}
