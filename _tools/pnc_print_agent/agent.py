"""PNC 로컬 프린터 에이전트 — 생산전표출력관리(490) 무음 자동출력.

왜 필요한가
-----------
웹(브라우저)은 보안상 "어느 프린터로 보낼지"를 코드로 지정할 수 없다. 그래서 지금까지는
인쇄창을 띄우고 직원이 매번 프린터를 골라야 했다(print.html + window.print()).
가간판(A4)·라벨(40×20)이 **서로 다른 USB 프린터**에 물려 있는 현장에서는 이게 매번 사고다.

구조
----
    [웹 490]  ──▶  ERP 서버 /api/print/*  (PDF·TSPL 생성)
                        │  (내용만 만들어 돌려줌)
                        ▼
    [웹 490]  ──▶  http://127.0.0.1:17650/print   ← 이 프로그램(작업 PC 상주)
                        │  kind=kanban → 가간판 프린터
                        │  kind=label  → 라벨 프린터
                        ▼  무음 출력(인쇄대화상자 없음)

★핵심: 웹은 프린터 이름을 모른다. `kind`(가간판/라벨)만 보내고,
  실제 물리 프린터는 **이 PC의 설정**에서 고른다. PC마다 프린터 구성이 달라도 웹 코드는 하나.

출력 방식
--------
  kanban : PDF 를 받아 무음 인쇄 (PyMuPDF 로 래스터화 → GDI, 외부 프로그램 불필요)
  label  : mode=tspl 이면 TSPL 명령어를 RAW 스풀로 직송(TSC/Bixolon 계열, 가장 선명)
           mode=pdf  이면 가간판과 동일하게 PDF 무음 인쇄

의존성 : pywin32, PyMuPDF(fitz)  — 둘 다 ERP 백엔드 PC 에 이미 있음.
         트레이 아이콘/설정창은 표준 tkinter 사용(추가 설치 없음).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "PNC 프린터 에이전트"
PORT = 17650
VERSION = "1.0.0"

# ★--noconsole(트레이) 로 빌드하면 stdout/stderr 이 None 이다.
#   그 상태에서 무엇이든 화면에 쓰려 하면 AttributeError 로 **즉사**한다
#   (실측: 배포 exe 가 로그 한 줄 못 남기고 종료. 콘솔 빌드는 멀쩡했다).
#   http.server 는 내부적으로 stderr 에 로그를 쓰므로 반드시 막아야 한다.
#   → 없으면 빈 통로로 갈아끼운다. 이후 모든 print/traceback 이 안전해진다.
if sys.stdout is None or sys.stderr is None:
    import io

    class _Null(io.TextIOBase):
        def write(self, s):  # noqa: D102
            return len(s)

        def flush(self):     # noqa: D102
            pass

    if sys.stdout is None:
        sys.stdout = _Null()
    if sys.stderr is None:
        sys.stderr = _Null()


def _boot(tag: str) -> None:
    """기동 추적 — 트레이(--noconsole) 빌드는 오류가 화면에 안 뜨고 조용히 죽는다.
       어디까지 갔는지 boot.log 에 남겨 원인을 좁힌다(실제로 이걸로 taskkill 자살을 찾았다).
       ※용량이 작고 진단 가치가 커서 운영에도 남겨둔다."""
    try:
        p = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                         "PNC_PrintAgent")
        os.makedirs(p, exist_ok=True)
        bl = os.path.join(p, "boot.log")
        if os.path.exists(bl) and os.path.getsize(bl) > 200_000:
            os.replace(bl, bl + ".old")
        with open(bl, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {tag}\n")
    except Exception:
        pass


_boot("import 완료")

# 설정파일 — 사용자 프로필에 둔다(프로그램 폴더는 쓰기권한이 없을 수 있다).
CFG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PNC_PrintAgent")
CFG_PATH = os.path.join(CFG_DIR, "config.json")
LOG_PATH = os.path.join(CFG_DIR, "agent.log")

DEFAULT_CFG = {
    "kanban_printer": "",     # 가간판·전표 (A4)
    "label_printer": "",      # 제품스티커 (40×20)
    "label_mode": "tspl",     # tspl | pdf
    "label_darkness": 8,      # TSPL DENSITY 0~15
    "label_speed": 3,         # TSPL SPEED
    "silent": True,           # False 면 인쇄대화상자를 띄운다(문제 진단용)
}

_cfg_lock = threading.Lock()
_cfg = dict(DEFAULT_CFG)


# ───────────────────────────── 설정 · 로그 ─────────────────────────────
def log(msg: str) -> None:
    """로그 기록. ★어떤 경우에도 예외를 밖으로 내지 않는다.

    ※--noconsole(트레이) 로 빌드하면 stdout 이 없어 print() 가 예외를 던진다.
      그 예외가 起動 경로에서 터지면 **아이콘도 못 띄우고 즉사**한다(실측: 배포 exe 가
      로그 한 줄 남기지 못하고 종료). 그래서 print 는 최후에, 실패해도 무시한다.
    """
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        # 로그가 무한정 커지지 않게 1MB 넘으면 새로 시작
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        # ★utf-8-sig — 메모장·엑셀이 한글을 깨지 않게 BOM 을 붙인다
        #   (CP949 로 읽혀 "?ㅼ젙 ????" 처럼 깨지던 문제).
        with open(LOG_PATH, "a", encoding="utf-8-sig" if not os.path.exists(LOG_PATH)
                  else "utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        if sys.stdout is not None:
            print(line, flush=True)
    except Exception:
        pass


def load_cfg() -> dict:
    global _cfg
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CFG)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_CFG})
        _cfg = merged
    except Exception:
        _cfg = dict(DEFAULT_CFG)
    return _cfg


def save_cfg(cfg: dict) -> None:
    global _cfg
    with _cfg_lock:
        merged = dict(DEFAULT_CFG)
        merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CFG})
        _cfg = merged
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    log(f"설정 저장 — 가간판={merged['kanban_printer']!r} 라벨={merged['label_printer']!r} "
        f"라벨모드={merged['label_mode']}")


# ───────────────────────────── 프린터 ─────────────────────────────
def list_printers() -> list[str]:
    import win32print
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    out = []
    for p in win32print.EnumPrinters(flags, None, 4):
        # level 4 는 dict, 구버전 pywin32 는 tuple 을 주기도 한다
        nm = p.get("pPrinterName") if isinstance(p, dict) else (p[2] if len(p) > 2 else "")
        nm = (nm or "").strip()
        if nm:
            out.append(nm)
    return sorted(set(out))


def default_printer() -> str:
    import win32print
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


def resolve_printer(kind: str) -> str:
    """kind(kanban/label) → 이 PC 에 설정된 물리 프린터 이름."""
    key = "label_printer" if kind == "label" else "kanban_printer"
    with _cfg_lock:
        nm = (_cfg.get(key) or "").strip()
    if not nm:
        raise RuntimeError(
            f"'{'라벨' if kind=='label' else '가간판'}' 프린터가 지정되지 않았습니다. "
            f"트레이의 {APP_NAME} → 설정에서 프린터를 고르세요.")
    if nm not in list_printers():
        raise RuntimeError(f"프린터 '{nm}' 를 이 PC 에서 찾을 수 없습니다(연결·전원 확인).")
    return nm


def _pymupdf():
    """PyMuPDF 모듈. 신 이름(pymupdf) 우선 — 구 `fitz` 는 제거 예정(경고 발생)."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


# ───────────────────────── RAW 직송 (TSPL) ─────────────────────────
def send_raw(printer: str, data: bytes, doc: str = "PNC RAW") -> None:
    """프린터 드라이버를 거치지 않고 명령어를 그대로 스풀에 넣는다(TSPL/ZPL 용)."""
    import win32print
    h = win32print.OpenPrinter(printer)
    try:
        job = win32print.StartDocPrinter(h, 1, (doc, None, "RAW"))
        try:
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
        finally:
            win32print.EndDocPrinter(h)
        log(f"RAW 전송 완료 — {printer} · job={job} · {len(data)}바이트")
    finally:
        win32print.ClosePrinter(h)


# ───────────────────────── PDF 무음 인쇄 ─────────────────────────
def print_pdf(printer: str, pdf: bytes, doc: str = "PNC PDF", silent: bool = True) -> int:
    """PDF 를 무음 인쇄. PyMuPDF 로 페이지를 렌더해 GDI 로 직접 그린다.

    ★외부 프로그램(SumatraPDF 등) 의존 없음 — 각 PC 에 뭘 더 깔 필요가 없다.
    ★용지 크기는 PDF 의 페이지 크기를 그대로 쓰지 않고, **프린터에 물린 용지의
      인쇄가능영역에 맞춰 등비 축소** 한다. 가간판(210×110)·라벨(40×20)처럼
      전용 용지를 쓰는 경우 드라이버 기본용지가 A4 여도 잘리지 않는다.
    """
    fitz = _pymupdf()      # PyMuPDF
    import win32con
    import win32print
    import win32ui

    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(printer)
    try:
        if not silent:
            log("※ silent=False — 드라이버 설정대로 진행(대화상자는 드라이버가 처리)")
        # 프린터의 물리 해상도와 인쇄가능영역(픽셀)
        px = dc.GetDeviceCaps(win32con.HORZRES)
        py = dc.GetDeviceCaps(win32con.VERTRES)
        dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX) or 300
        dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY) or 300

        pdf_doc = fitz.open(stream=pdf, filetype="pdf")
        pages = pdf_doc.page_count
        dc.StartDoc(doc)
        try:
            for i in range(pages):
                page = pdf_doc.load_page(i)
                # 페이지(pt, 1/72인치) → 프린터 dpi 로 래스터화
                zoom_x = dpi_x / 72.0
                zoom_y = dpi_y / 72.0
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y), alpha=False)

                # 인쇄가능영역을 넘으면 등비 축소(잘림 방지)
                scale = min(px / pix.width, py / pix.height, 1.0)
                w = max(1, int(pix.width * scale))
                h = max(1, int(pix.height * scale))

                dc.StartPage()
                _blit(dc, pix, w, h)
                dc.EndPage()
        finally:
            dc.EndDoc()
        pdf_doc.close()
        log(f"PDF 인쇄 완료 — {printer} · {pages}페이지 · {len(pdf)}바이트")
        return pages
    finally:
        dc.DeleteDC()


def _blit(dc, pix, w: int, h: int) -> None:
    """PyMuPDF pixmap 을 프린터 DC 에 그린다 (StretchDIBits)."""
    import win32con
    import win32gui

    # PyMuPDF 는 RGB(top-down). DIB 는 BGR(bottom-up) 이므로 뒤집어 넘긴다.
    import ctypes
    from ctypes import wintypes

    src_w, src_h = pix.width, pix.height
    samples = pix.samples                       # RGB, 행당 pix.stride 바이트
    row_bytes = (src_w * 3 + 3) & ~3            # DIB 는 4바이트 정렬

    # PyMuPDF 는 RGB·top-down, DIB 는 BGR·bottom-up.
    # ★파이썬 루프로 픽셀을 뒤집으면 A4 300dpi 한 장에 수백만 회 반복이라 몇 초씩 걸린다.
    #   Pillow 가 있으면 채널 스왑을 C 로 처리하고, 없으면 행 단위 슬라이스로 처리한다.
    stride = pix.stride
    try:
        from PIL import Image
        im = Image.frombuffer("RGB", (src_w, src_h), samples, "raw", "RGB", stride, 1)
        # BGR 로 스왑 + 상하반전(bottom-up) 을 Pillow 가 한 번에
        im = im.transpose(Image.FLIP_TOP_BOTTOM)
        r, g, b = im.split()
        im = Image.merge("RGB", (b, g, r))
        raw = im.tobytes("raw", "RGB", 0, 1)
        if row_bytes == src_w * 3:
            buf = raw
        else:                                    # 4바이트 정렬 패딩 채우기
            buf = bytearray(row_bytes * src_h)
            for y in range(src_h):
                buf[y * row_bytes:y * row_bytes + src_w * 3] = raw[y * src_w * 3:(y + 1) * src_w * 3]
    except Exception:
        buf = bytearray(row_bytes * src_h)
        for y in range(src_h):
            s = y * stride
            row = bytearray(samples[s:s + src_w * 3])
            row[0::3], row[2::3] = row[2::3], row[0::3]      # RGB → BGR (행 단위 슬라이스)
            d = (src_h - 1 - y) * row_bytes                  # bottom-up
            buf[d:d + src_w * 3] = row

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = src_w
    bmi.biHeight = src_h            # 양수 = bottom-up
    bmi.biPlanes = 1
    bmi.biBitCount = 24
    bmi.biCompression = 0           # BI_RGB
    bmi.biSizeImage = row_bytes * src_h

    hdc = dc.GetSafeHdc()
    gdi = ctypes.windll.gdi32
    gdi.SetStretchBltMode(hdc, win32con.HALFTONE)
    rc = gdi.StretchDIBits(
        hdc, 0, 0, w, h,            # 대상 (좌상단부터)
        0, 0, src_w, src_h,         # 원본 전체
        bytes(buf), ctypes.byref(bmi),
        0,                          # DIB_RGB_COLORS
        win32con.SRCCOPY)
    if rc == 0:
        raise RuntimeError("StretchDIBits 실패 — 프린터 DC 에 그리지 못했습니다.")
    _ = win32gui


# ───────────────────────────── HTTP 서버 ─────────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = f"PNCPrintAgent/{VERSION}"

    def log_message(self, fmt, *args):        # 기본 stderr 로그 억제
        pass

    # 웹(ERP)에서 fetch 로 부르므로 CORS 허용이 필요하다.
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, obj, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/ping", "/"):
            with _cfg_lock:
                c = dict(_cfg)
            return self._json({
                "ok": True, "app": "pnc-print-agent", "version": VERSION,
                "host": os.environ.get("COMPUTERNAME", ""),
                "kanban_printer": c["kanban_printer"],
                "label_printer": c["label_printer"],
                "label_mode": c["label_mode"],
                # 웹이 "설정 안 됨"을 안내할 수 있게 준비상태를 함께 준다
                "ready_kanban": bool(c["kanban_printer"]),
                "ready_label": bool(c["label_printer"]),
            })
        if path == "/printers":
            try:
                return self._json({"ok": True, "rows": list_printers(),
                                   "default": default_printer()})
            except Exception as e:
                return self._json({"ok": False, "detail": str(e)}, 500)
        return self._json({"ok": False, "detail": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            req = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            return self._json({"ok": False, "detail": f"요청 파싱 실패: {e}"}, 400)

        if path == "/config":
            try:
                save_cfg(req)
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"ok": False, "detail": str(e)}, 500)

        if path != "/print":
            return self._json({"ok": False, "detail": "not found"}, 404)

        kind = str(req.get("kind") or "").strip().lower()
        if kind not in ("kanban", "label", "sheet"):
            return self._json({"ok": False, "detail": f"kind 가 잘못됨: {kind!r}"}, 400)
        # 전표(sheet)는 가간판과 같은 A4 프린터로 나간다
        target_kind = "label" if kind == "label" else "kanban"

        try:
            printer = resolve_printer(target_kind)
        except Exception as e:
            log(f"[거부] {kind}: {e}")
            return self._json({"ok": False, "detail": str(e), "need_setup": True}, 409)

        doc = str(req.get("doc") or f"PNC {kind}")[:120]
        copies = max(1, min(int(req.get("copies") or 1), 20))

        try:
            with _cfg_lock:
                silent = bool(_cfg.get("silent", True))
            if req.get("tspl"):
                # 라벨 명령어 직송 (TSC/Bixolon)
                data = req["tspl"]
                payload = base64.b64decode(data) if req.get("b64") else str(data).encode("utf-8")
                for _ in range(copies):
                    send_raw(printer, payload, doc)
                pages = copies
            elif req.get("pdf"):
                pdf = base64.b64decode(req["pdf"])
                pages = 0
                for _ in range(copies):
                    pages += print_pdf(printer, pdf, doc, silent)
            else:
                return self._json({"ok": False, "detail": "pdf 또는 tspl 이 필요합니다."}, 400)
        except Exception as e:
            log(f"[실패] {kind} → {printer}: {e}\n{traceback.format_exc()}")
            return self._json({"ok": False, "detail": str(e)}, 500)

        log(f"[출력] {kind} → {printer} · {doc} · {pages}p")
        return self._json({"ok": True, "printer": printer, "pages": pages})


def serve() -> ThreadingHTTPServer:
    # 127.0.0.1 로만 바인딩 — 외부에서 이 PC 프린터를 못 쓰게 한다(보안).
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"{APP_NAME} v{VERSION} 시작 — http://127.0.0.1:{PORT}")
    return srv


# ───────────────────────────── 설정 창 (tkinter) ─────────────────────────────
def open_settings() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    load_cfg()
    printers = list_printers()

    root = tk.Tk()
    root.title(f"{APP_NAME} 설정")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

    pad = {"padx": 10, "pady": 6}
    frm = ttk.Frame(root, padding=12)
    frm.grid(sticky="nsew")

    ttk.Label(frm, text="생산전표출력관리(490) 자동출력 프린터",
              font=("맑은 고딕", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))
    ttk.Label(frm, text="웹에서 발행하면 인쇄창 없이 아래 프린터로 바로 나갑니다.",
              foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(frm, text="가간판 · 전표").grid(row=2, column=0, sticky="w", **pad)
    v_kan = tk.StringVar(value=_cfg["kanban_printer"])
    cb_kan = ttk.Combobox(frm, textvariable=v_kan, values=printers, width=46, state="readonly")
    cb_kan.grid(row=2, column=1, sticky="w", **pad)
    ttk.Label(frm, text="210×110 / A4", foreground="#777").grid(row=2, column=2, sticky="w")

    ttk.Label(frm, text="제품스티커(라벨)").grid(row=3, column=0, sticky="w", **pad)
    v_lab = tk.StringVar(value=_cfg["label_printer"])
    cb_lab = ttk.Combobox(frm, textvariable=v_lab, values=printers, width=46, state="readonly")
    cb_lab.grid(row=3, column=1, sticky="w", **pad)
    ttk.Label(frm, text="40×20", foreground="#777").grid(row=3, column=2, sticky="w")

    ttk.Label(frm, text="라벨 출력방식").grid(row=4, column=0, sticky="w", **pad)
    v_mode = tk.StringVar(value=_cfg["label_mode"])
    fr_mode = ttk.Frame(frm)
    fr_mode.grid(row=4, column=1, sticky="w", **pad)
    ttk.Radiobutton(fr_mode, text="TSPL 직송 (TSC·Bixolon — 선명·빠름)",
                    variable=v_mode, value="tspl").pack(side="left")
    ttk.Radiobutton(fr_mode, text="PDF (일반 프린터)",
                    variable=v_mode, value="pdf").pack(side="left", padx=(12, 0))

    ttk.Label(frm, text="라벨 농도 / 속도").grid(row=5, column=0, sticky="w", **pad)
    fr_ds = ttk.Frame(frm)
    fr_ds.grid(row=5, column=1, sticky="w", **pad)
    v_dark = tk.IntVar(value=int(_cfg["label_darkness"]))
    v_spd = tk.IntVar(value=int(_cfg["label_speed"]))
    ttk.Spinbox(fr_ds, from_=0, to=15, textvariable=v_dark, width=5).pack(side="left")
    ttk.Label(fr_ds, text="(0~15)", foreground="#777").pack(side="left", padx=(4, 14))
    ttk.Spinbox(fr_ds, from_=1, to=8, textvariable=v_spd, width=5).pack(side="left")
    ttk.Label(fr_ds, text="(1~8)", foreground="#777").pack(side="left", padx=(4, 0))

    def do_save(close: bool = True):
        save_cfg({"kanban_printer": v_kan.get(), "label_printer": v_lab.get(),
                  "label_mode": v_mode.get(), "label_darkness": v_dark.get(),
                  "label_speed": v_spd.get(), "silent": True})
        if close:
            root.destroy()

    def do_test(kind: str):
        do_save(close=False)
        try:
            printer = resolve_printer(kind)
        except Exception as e:
            messagebox.showwarning("확인", str(e), parent=root)
            return
        try:
            if kind == "label" and v_mode.get() == "tspl":
                send_raw(printer, tspl_test(v_dark.get(), v_spd.get()), "PNC 테스트")
            else:
                print_pdf(printer, pdf_test(kind), "PNC 테스트")
            messagebox.showinfo("테스트", f"'{printer}' 로 테스트 출력을 보냈습니다.", parent=root)
        except Exception as e:
            messagebox.showerror("테스트 실패", f"{e}", parent=root)

    fr_btn = ttk.Frame(frm)
    fr_btn.grid(row=6, column=0, columnspan=3, sticky="e", pady=(14, 0))
    ttk.Button(fr_btn, text="가간판 테스트출력", command=lambda: do_test("kanban")).pack(side="left", padx=4)
    ttk.Button(fr_btn, text="라벨 테스트출력", command=lambda: do_test("label")).pack(side="left", padx=4)
    ttk.Button(fr_btn, text="로그 열기",
               command=lambda: os.startfile(LOG_PATH) if os.path.exists(LOG_PATH) else None).pack(side="left", padx=4)
    ttk.Button(fr_btn, text="저장", command=do_save).pack(side="left", padx=4)

    ttk.Label(frm, text=f"수신대기 http://127.0.0.1:{PORT}   ·   설정파일 {CFG_PATH}",
              foreground="#888").grid(row=7, column=0, columnspan=3, sticky="w", pady=(12, 0))

    root.mainloop()


# ───────────────────────────── 테스트 출력물 ─────────────────────────────
def tspl_test(darkness: int = 8, speed: int = 3) -> bytes:
    """40×20mm 라벨 테스트(TSPL). QR + 텍스트 — 실제 제품스티커와 같은 배치."""
    cmds = [
        "SIZE 40 mm,20 mm", "GAP 2 mm,0", f"DENSITY {int(darkness)}", f"SPEED {int(speed)}",
        "DIRECTION 1", "CLS",
        'QRCODE 12,12,L,4,A,0,"PNC-TEST-0001"',
        'TEXT 165,20,"3",0,1,1,"PNC Industry"',
        'TEXT 165,60,"2",0,1,1,"TEST LABEL"',
        'TEXT 165,95,"2",0,1,1,"40 x 20 mm"',
        "PRINT 1,1",
    ]
    return ("\r\n".join(cmds) + "\r\n").encode("utf-8")


def pdf_test(kind: str) -> bytes:
    """테스트용 PDF 를 즉석 생성(가간판 210×110 / 라벨 40×20)."""
    fitz = _pymupdf()
    mm = 72.0 / 25.4
    w, h = (210 * mm, 110 * mm) if kind != "label" else (40 * mm, 20 * mm)
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    page.draw_rect(fitz.Rect(2, 2, w - 2, h - 2), color=(0, 0, 0), width=1)
    label = "가간판 테스트 (210 x 110mm)" if kind != "label" else "LABEL TEST"
    page.insert_text((10, 24), "PNC Industry", fontsize=11 if kind != "label" else 6)
    page.insert_text((10, 40), label, fontsize=9 if kind != "label" else 5)
    page.insert_text((10, h - 12), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     fontsize=8 if kind != "label" else 4)
    out = doc.tobytes()
    doc.close()
    return out


# ───────────────────────────── 트레이 상주 ─────────────────────────────
def run_tray() -> None:
    """트레이 아이콘 상주. pystray 가 있으면 그걸 쓰고, 없으면 설정창을 최소화 없이 유지."""
    srv = serve()
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        log("pystray/Pillow 없음 — 설정창 모드로 실행합니다(창을 닫으면 종료).")
        open_settings()
        srv.shutdown()
        return

    img = Image.new("RGB", (64, 64), "#1b4f9c")
    d = ImageDraw.Draw(img)
    d.rectangle([12, 22, 52, 44], fill="white")
    d.rectangle([20, 12, 44, 22], fill="#cfe0f5")
    d.rectangle([20, 44, 44, 56], fill="#cfe0f5")

    def on_settings(icon, item):
        threading.Thread(target=open_settings, daemon=True).start()

    def on_quit(icon, item):
        log("종료 요청")
        srv.shutdown()
        icon.stop()

    def on_uninstall(icon, item):
        # 자동시작만 해제하고 이번 실행은 계속(파일 삭제는 실행 중이라 불가)
        uninstall()

    menu = pystray.Menu(
        pystray.MenuItem(f"{APP_NAME} v{VERSION}", None, enabled=False),
        pystray.MenuItem("설정 / 프린터 지정", on_settings, default=True),
        pystray.MenuItem("로그 열기",
                         lambda i, it: os.startfile(LOG_PATH) if os.path.exists(LOG_PATH) else None),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("자동시작 해제", on_uninstall),
        pystray.MenuItem("종료", on_quit),
    )
    icon = pystray.Icon("pnc_print_agent", img, APP_NAME, menu)
    # 프린터가 아직 안 정해졌으면 처음 한 번 설정창을 띄운다.
    if not (_cfg["kanban_printer"] or _cfg["label_printer"]):
        threading.Thread(target=open_settings, daemon=True).start()
    icon.run()


# ───────────────────────── 자가설치 (최초 실행) ─────────────────────────
#   ★현장 PC 마다 설치 스크립트를 따로 돌리게 하면 반드시 빠지는 PC 가 생긴다.
#     그냥 exe 를 더블클릭하면 알아서 설치되고, 다음부터 로그인 시 자동 실행되게 한다.
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or CFG_DIR, "PNC_PrintAgent")
EXE_NAME = "PNC프린터에이전트.exe"


def _is_frozen() -> bool:
    """PyInstaller 로 묶인 exe 로 실행 중인가(파이썬 스크립트 실행과 구분)."""
    return bool(getattr(sys, "frozen", False))


def _startup_lnk() -> str:
    return os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows",
        "Start Menu", "Programs", "Startup", "PNC 프린터 에이전트.lnk")


def _make_shortcut(target: str, lnk: str) -> bool:
    """시작프로그램 바로가기 생성. COM 이 막혀 있으면 조용히 실패(설치는 계속)."""
    try:
        import pythoncom            # noqa: F401  (pywin32 COM 초기화)
        from win32com.client import Dispatch
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        sc = Dispatch("WScript.Shell").CreateShortCut(lnk)
        sc.TargetPath = target
        sc.WorkingDirectory = os.path.dirname(target)
        sc.Description = "PNC ERP 생산전표출력관리 자동출력"
        sc.save()
        return True
    except Exception as e:
        log(f"바로가기 생성 실패(무시): {e}")
        return False


def ensure_installed() -> bool:
    """설치돼 있지 않으면 설치한다. 새 위치에서 재실행했으면 True(현재 프로세스는 종료).

    설치 = ①%LOCALAPPDATA%\\PNC_PrintAgent 로 exe 복사 ②시작프로그램 등록.
    관리자 권한 불필요(사용자 영역만 건드린다).
    """
    if not _is_frozen():
        return False                       # 개발 중(py 실행)에는 설치하지 않는다
    me = os.path.abspath(sys.executable)
    dst = os.path.join(INSTALL_DIR, EXE_NAME)

    # 이미 설치 위치에서 돌고 있으면 바로가기만 확인하고 계속 실행
    if os.path.normcase(me) == os.path.normcase(dst):
        if not os.path.exists(_startup_lnk()):
            _make_shortcut(dst, _startup_lnk())
            log("시작프로그램 재등록")
        return False

    # ── 최초 실행(USB·공유폴더 등에서 실행) → 설치
    _boot(f"설치 시작 {me} -> {dst}")
    try:
        import ctypes
        import shutil
        import subprocess
        os.makedirs(INSTALL_DIR, exist_ok=True)
        # 구버전이 돌고 있으면 종료해야 덮어쓸 수 있다.
        # ★단 이름이 같으므로 /IM 로 죽이면 **자기 자신도 함께 죽는다**
        #   (실측: 설치 로그를 남기고 그 줄에서 즉사 — 설치가 한 번도 끝나지 않았다).
        #   → PID 를 지정해 '나를 제외한' 같은 이름만 종료한다.
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", EXE_NAME, "/FI", f"PID ne {os.getpid()}"],
                capture_output=True, timeout=15)
        except Exception:
            pass
        shutil.copy2(me, dst)
        _make_shortcut(dst, _startup_lnk())
        log(f"설치 완료 — {dst}")
        # 설치 위치에서 다시 띄우고 현재 프로세스는 종료
        os.startfile(dst)                                    # noqa: S606
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"{APP_NAME} 설치가 끝났습니다.\n\n"
                f"작업표시줄 오른쪽 트레이의 아이콘을 눌러\n"
                f"가간판·라벨 프린터를 지정하세요.\n\n"
                f"다음부터는 PC 를 켜면 자동으로 실행됩니다.",
                APP_NAME, 0x40)
        except Exception:
            pass
        return True
    except Exception as e:
        log(f"설치 실패(설치 없이 계속 실행): {e}")
        return False


def main() -> None:
    _boot(f"main 진입 argv={sys.argv[1:]} frozen={_is_frozen()} exe={sys.executable}")
    load_cfg()
    args = set(a.lower() for a in sys.argv[1:])
    if "--settings" in args:
        open_settings()
        return
    if "--uninstall" in args:
        uninstall()
        return
    if "--console" in args:      # 진단용 — 트레이 없이 서버만
        serve()
        log("콘솔 모드 — Ctrl+C 로 종료")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    # ★최초 실행이면 설치하고 설치본을 띄운 뒤 이 프로세스는 종료
    if "--no-install" not in args and ensure_installed():
        return
    run_tray()


def uninstall() -> None:
    """제거 — 시작프로그램 해제 + 설치본 삭제(설정·로그는 보존)."""
    import ctypes
    try:
        lnk = _startup_lnk()
        if os.path.exists(lnk):
            os.remove(lnk)
        msg = f"{APP_NAME} 자동시작을 해제했습니다.\n설정은 보존됩니다:\n{CFG_DIR}"
    except Exception as e:
        msg = f"제거 중 오류: {e}"
    log(msg.replace("\n", " "))
    try:
        ctypes.windll.user32.MessageBoxW(None, msg, APP_NAME, 0x40)
    except Exception:
        pass


if __name__ == "__main__":
    # ★트레이(--noconsole) 빌드는 오류가 화면에 안 뜬다. 그대로 두면 "더블클릭해도
    #   아무 일도 안 난다"가 되어 현장에서 원인을 알 수 없다 — 반드시 보이게 한다.
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        try:
            log("치명적 오류\n" + err)
        except Exception:
            pass
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"{APP_NAME} 실행 중 오류가 발생했습니다.\n\n{err[-900:]}\n\n"
                      f"로그: {LOG_PATH}", APP_NAME, 0x10)
        except Exception:
            pass
        sys.exit(1)
