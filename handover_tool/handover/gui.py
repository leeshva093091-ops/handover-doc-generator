"""네이티브 데스크톱 GUI (tkinter — 표준 라이브러리, 외부 의존성 0).

- 여러 프로젝트(폴더/파일/Git URL)를 큐에 담아 한 번에 분석
- 분석 결과는 프로젝트별 탭으로 누적 (이전 결과 유지)
- 각 결과는 '요약'(개요 카드 + 준비사항 + 설치·실행 + 민감정보 표)과
  '문서'(서식 적용된 Markdown) 하위 탭으로 표시

분석(특히 Git 클론)은 백그라운드 스레드에서 돌리고, 위젯 조작은 root.after로 메인
스레드에서만 수행한다(tkinter 제약).
"""

from __future__ import annotations

import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from . import __version__, export, source
from .service import generate_document

_C_BG = "#f7f8fa"
_C_CARD = "#ffffff"
_C_ACCENT = "#2d6cdf"
_C_WARN = "#b00020"
_C_OK = "#1a7f37"
_CONF_COLOR = {"높음": "#fde7e9", "중간": "#fff4e5", "낮음": "#eeeeee"}


def _make_close_image(color: str, size: int = 14) -> tk.PhotoImage:
    """탭 닫기용 ✕ 아이콘을 코드로 그린다 (외부 이미지 파일 불필요).

    배경은 투명, 대각선 두 줄로 ✕를 그린다 (Tk 8.6 transparency_set 사용).
    """
    img = tk.PhotoImage(width=size, height=size)
    for x in range(size):
        for y in range(size):
            img.transparency_set(x, y, True)
    for t in range(3, size - 3):
        for dx in (-1, 0):
            for px, py in ((t + dx, t), (t + dx, size - 1 - t)):
                if 0 <= px < size and 0 <= py < size:
                    img.put(color, (px, py))
                    img.transparency_set(px, py, False)
    return img


class ClosableNotebook(ttk.Notebook):
    """탭 제목 옆 ✕로 닫을 수 있는 Notebook (tkinter 표준 recipe 응용)."""

    _initialized = False

    def __init__(self, master, on_close=None, **kw):
        if not ClosableNotebook._initialized:
            ClosableNotebook._img_normal = _make_close_image("#999")
            ClosableNotebook._img_active = _make_close_image("#d11")
            self._init_style()
            ClosableNotebook._initialized = True
        super().__init__(master, style="Closable.TNotebook", **kw)
        self._on_close = on_close
        self._active = None
        self.bind("<ButtonPress-1>", self._on_press, True)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event):
        if "close" in self.identify(event.x, event.y):
            self.state(["pressed"])
            self._active = self.index(f"@{event.x},{event.y}")
            return "break"
        return None

    def _on_release(self, event):
        if not self.instate(["pressed"]):
            return
        self.state(["!pressed"])
        if "close" in self.identify(event.x, event.y):
            index = self.index(f"@{event.x},{event.y}")
            if index == self._active and self._on_close:
                self._on_close(self.tabs()[index])
        self._active = None

    @classmethod
    def _init_style(cls):
        style = ttk.Style()
        style.element_create("close", "image", cls._img_normal,
                             ("active", cls._img_active), border=6, sticky="")
        style.layout("Closable.TNotebook", [("Closable.TNotebook.client", {"sticky": "nswe"})])
        style.layout("Closable.TNotebook.Tab", [
            ("Closable.TNotebook.tab", {"sticky": "nswe", "children": [
                ("Closable.TNotebook.padding", {"side": "top", "sticky": "nswe", "children": [
                    ("Closable.TNotebook.focus", {"side": "top", "sticky": "nswe", "children": [
                        ("Closable.TNotebook.label", {"side": "left", "sticky": ""}),
                        ("Closable.TNotebook.close", {"side": "left", "sticky": ""}),
                    ]})
                ]})
            ]})
        ])


class HandoverApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._results: dict[str, dict] = {}  # 탭 경로 -> {"doc","name"}
        self._analyzing = False
        root.title(f"인수인계 문서 생성기 v{__version__}")
        root.geometry("1040x760")
        # 입력 영역 + 대기목록 + 결과 탭(2단 요약/표)이 잘리지 않는 최소 크기
        root.minsize(900, 680)
        root.configure(bg=_C_BG)
        self._init_fonts()
        self._init_style()
        self._build()

    def _init_fonts(self) -> None:
        self.f_title = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.f_h2 = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.f_h3 = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body = tkfont.Font(family="Segoe UI", size=10)
        self.f_mono = tkfont.Font(family="Consolas", size=10)
        self.f_label = tkfont.Font(family="Segoe UI", size=9, weight="bold")

    def _init_style(self) -> None:
        """플랫하고 심플한 테마 (clam 기반 커스텀)."""
        style = ttk.Style()
        try:
            style.theme_use("clam")  # 평탄한 커스터마이즈에 적합
        except tk.TclError:
            pass
        bg, card, line, ink, sub = _C_BG, _C_CARD, "#e4e7ec", "#1b1b1b", "#667085"

        style.configure(".", background=bg, foreground=ink, font=("Segoe UI", 10),
                        borderwidth=0, focuscolor=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=ink)
        style.configure("TLabelframe", background=bg, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=bg, foreground=sub,
                        font=("Segoe UI", 9, "bold"))
        # 버튼: 연한 회색 채움 + 또렷한 테두리 → 배경(거의 흰색)과 분명히 구분.
        btn_bg, btn_bd = "#eef1f6", "#aab2c0"
        style.configure("TButton", background=btn_bg, foreground="#1f2937",
                        borderwidth=1, relief="solid", padding=(12, 7),
                        bordercolor=btn_bd, lightcolor=btn_bd, darkcolor=btn_bd)
        style.map("TButton",
                  background=[("active", "#e0e6ef"), ("pressed", "#d2dae6"),
                              ("disabled", "#f1f2f4")],
                  foreground=[("disabled", "#9aa1ab")],   # 비활성도 읽히는 회색
                  bordercolor=[("active", "#8e98a8"), ("disabled", "#dde0e5")],
                  lightcolor=[("active", "#8e98a8"), ("disabled", "#dde0e5")],
                  darkcolor=[("active", "#8e98a8"), ("disabled", "#dde0e5")])
        # 강조 버튼(분석): 파랑 채움 + 굵게
        style.configure("Accent.TButton", background=_C_ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(14, 8),
                        bordercolor="#2559c4", lightcolor="#2559c4", darkcolor="#2559c4")
        style.map("Accent.TButton",
                  background=[("active", "#2559c4"), ("pressed", "#1f4fb5"),
                              ("disabled", "#bcc6dd")],
                  foreground=[("disabled", "#eef1f6")],
                  bordercolor=[("disabled", "#bcc6dd")],
                  lightcolor=[("disabled", "#bcc6dd")], darkcolor=[("disabled", "#bcc6dd")])
        # 입력
        style.configure("TEntry", fieldbackground="white", borderwidth=1, relief="solid",
                        padding=4)
        # 노트북: 플랫 탭
        for nb in ("TNotebook", "Closable.TNotebook"):
            style.configure(nb, background=bg, borderwidth=0, tabmargins=(2, 4, 2, 0))
        for tab in ("TNotebook.Tab", "Closable.TNotebook.Tab"):
            style.configure(tab, background="#e7eaef", foreground=sub,
                            padding=(16, 8), borderwidth=0)
            # 선택/비선택 모두 동일 padding·expand로 강제 → 크기 고정, 차이는 배경색만.
            style.map(
                tab,
                background=[("selected", card), ("active", "#dfe4ea")],
                foreground=[("selected", ink)],
                expand=[("selected", "0 0 0 0"), ("!selected", "0 0 0 0")],
                padding=[("selected", (16, 8)), ("!selected", (16, 8))],
            )
        # 표
        style.configure("Treeview", background="white", fieldbackground="white",
                        borderwidth=1, relief="solid", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#eef1f5", relief="flat",
                        font=("Segoe UI", 9, "bold"))
        style.configure("TProgressbar", background=_C_ACCENT, troughcolor="#e7eaef",
                        borderwidth=0)
        # 카드용 라벨
        style.configure("Card.TLabel", background=card, font=("Segoe UI", 10))
        style.configure("Key.TLabel", background=card, font=("Segoe UI", 9, "bold"),
                        foreground=sub)
        style.configure("Title.TLabel", background=card, font=("Segoe UI", 16, "bold"))

    # ---------- 레이아웃 ----------
    def _build(self) -> None:
        # 상단바: 제목(좌) + Git 사용 가능 상태/도움말(우)
        topbar = ttk.Frame(self.root, padding=(12, 8, 12, 0))
        topbar.pack(fill="x")
        ttk.Label(topbar, text="📄 인수인계 문서 생성기", font=self.f_h2).pack(side="left")
        # ? 도움말 버튼 (부드러운 플랫 칩 모양) — 상태칩의 '오른쪽'에 배치
        self.git_help_btn = tk.Button(topbar, text="ⓘ", command=self._show_git_help,
                                      font=("Segoe UI", 10, "bold"), bd=0,
                                      relief="flat", bg="#e8eef7", fg=_C_ACCENT,
                                      activebackground="#dce6f5", padx=8, pady=1,
                                      highlightthickness=0, cursor="hand2")
        self.git_status = tk.Label(topbar, font=("Segoe UI", 9, "bold"), bg=_C_BG,
                                   cursor="hand2")
        self.git_help_btn.pack(side="right")          # 가장 오른쪽
        self.git_status.pack(side="right", padx=(0, 8))  # 그 왼쪽에 상태칩
        self.git_status.bind("<Button-1>", lambda _e: self._refresh_git_status())
        self._refresh_git_status()

        # 프로젝트 추가 영역 — 찾아보기(폴더/파일) 또는 Git URL 입력
        src_frame = ttk.LabelFrame(self.root, text=" 프로젝트 추가 ", padding=8)
        src_frame.pack(fill="x", padx=12, pady=(12, 4))

        # 1행: 프로젝트 찾아보기 (하나의 버튼 → 폴더/파일 선택 메뉴)
        ttk.Label(src_frame, text="📂 프로젝트", font=self.f_label,
                  foreground=_C_OK).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.browse_btn = ttk.Button(src_frame, text="프로젝트 찾아보기…",
                                     command=self._browse_menu)
        self.browse_btn.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(src_frame, text="프로젝트 폴더 또는 개별 파일(.java/.py/문서 등)을 골라 목록에 담습니다.",
                  foreground="#888").grid(row=0, column=2, columnspan=2, sticky="w", padx=(8, 0))

        # 2행: Git URL 또는 경로 직접 입력
        ttk.Label(src_frame, text="🔗 Git URL/경로", font=self.f_label,
                  foreground=_C_ACCENT).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        self.entry = ttk.Entry(src_frame, font=self.f_body)
        self.entry.grid(row=1, column=1, columnspan=2, sticky="we", pady=(6, 0))
        self.entry.bind("<Return>", lambda _e: self._add_to_queue())
        self.entry.bind("<KeyRelease>", self._on_entry_change)
        self.add_btn = ttk.Button(src_frame, text="＋ 목록에 추가", command=self._add_to_queue)
        self.add_btn.grid(row=1, column=3, padx=(6, 0), pady=(6, 0))
        # 입력 인식 표시 (Git URL인지 폴더/파일 경로인지 실시간 안내)
        self.type_label = ttk.Label(src_frame, text="", foreground="#888")
        self.type_label.grid(row=2, column=1, columnspan=2, sticky="w")
        src_frame.columnconfigure(2, weight=1)

        # 분석 대기 큐
        qframe = ttk.LabelFrame(self.root, text=" 분석 대기 목록 ", padding=6)
        qframe.pack(fill="x", padx=12, pady=(4, 0))
        self.queue_list = tk.Listbox(qframe, height=3, font=self.f_body, activestyle="none")
        self.queue_list.pack(side="left", fill="both", expand=True)
        self.queue_list.bind("<<ListboxSelect>>", lambda _e: self._refresh_buttons())
        qbtns = ttk.Frame(qframe)
        qbtns.pack(side="right", fill="y", padx=(6, 0))
        self.del_btn = ttk.Button(qbtns, text="선택 삭제", command=self._del_selected)
        self.del_btn.pack(fill="x")
        self.clear_btn = ttk.Button(qbtns, text="전체 비우기", command=self._clear_queue)
        self.clear_btn.pack(fill="x", pady=(4, 0))
        self.analyze_btn = ttk.Button(qbtns, text="분석 ▶ (전체)", style="Accent.TButton",
                                      command=self._analyze)
        self.analyze_btn.pack(fill="x", pady=(8, 0))

        bar = ttk.Frame(self.root, padding=(12, 4))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, anchor="w", foreground="#444",
                                text="프로젝트를 추가하고 [분석 ▶ (전체)]을 누르세요. (Git URL은 git 설치 필요)")
        self.status.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)

        # 결과 영역: 결과가 없으면 사용 가이드, 있으면 프로젝트별 탭(✕로 닫기).
        self.results_area = ttk.Frame(self.root)
        self.results_area.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.guide_frame = ttk.Frame(self.results_area)
        self._build_guide(self.guide_frame)
        self.results_nb = ClosableNotebook(self.results_area, on_close=self._on_tab_close)
        self.results_nb.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_buttons())
        self._update_results_view()  # 처음엔 가이드 표시

        self._refresh_buttons()  # 초기 비활성 상태 적용

    def _build_guide(self, parent: ttk.Frame) -> None:
        # 중앙 정렬된 박스. grid로 제목/설명 열을 분리해 겹침을 방지한다.
        box = ttk.Frame(parent, padding=30)
        box.pack(expand=True)
        ttk.Label(box, text="📄 인수인계 문서 생성기", font=self.f_title,
                  foreground=_C_ACCENT).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, foreground="#555", font=self.f_body, justify="left",
                  text="프로젝트 폴더나 Git 저장소를 넣으면 설치·실행·주의사항을\n"
                       "정형 인수인계 문서로 자동 정리해 줍니다.").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 16))
        steps = [
            ("①  프로젝트 추가", "‘프로젝트 찾아보기…’로 폴더/파일을 고르거나, Git URL을 입력하고 ‘＋ 목록에 추가’"),
            ("②  분석 실행", "‘분석 ▶ (전체)’를 누르면 목록의 항목들을 한 번에 분석합니다"),
            ("③  결과 확인", "프로젝트별 탭에서 ‘요약·파일·문서’를 보고, 탭 안의 ‘💾 이 결과 저장’으로 내보내기"),
        ]
        for i, (title, desc) in enumerate(steps, start=2):
            ttk.Label(box, text=title, font=self.f_h3, foreground="#222").grid(
                row=i, column=0, sticky="nw", padx=(0, 16), pady=5)
            ttk.Label(box, text=desc, font=self.f_body, foreground="#555",
                      wraplength=520, justify="left").grid(row=i, column=1, sticky="w", pady=5)
        ttk.Label(box, foreground="#888", font=("Segoe UI", 9), justify="left",
                  text="• 여러 프로젝트를 목록에 담아 한 번에 분석 · 결과는 탭으로 누적됩니다.\n"
                       "• 비밀번호·키 등 민감정보를 자동 탐지해 ‘주의’로 표시합니다.\n"
                       "• Git URL 분석에는 실행 PC에 git이 설치돼 있어야 합니다.").grid(
            row=len(steps) + 2, column=0, columnspan=2, sticky="w", pady=(18, 0))

    def _update_results_view(self) -> None:
        """결과 유무에 따라 가이드/탭 노트북 중 하나만 보여준다."""
        if self._results:
            self.guide_frame.pack_forget()
            if not self.results_nb.winfo_ismapped():
                self.results_nb.pack(fill="both", expand=True)
        else:
            self.results_nb.pack_forget()
            self.guide_frame.pack(fill="both", expand=True)

    # ---------- 입력 인식 / 버튼 토글 ----------
    def _on_entry_change(self, _event=None) -> None:
        text = self.entry.get().strip()
        if not text:
            self.type_label.config(text="")
        elif ";" in text or "\n" in text:
            self.type_label.config(text="🗂 여러 항목 — [목록에 추가]로 담으세요", foreground="#888")
        elif source.is_url(text):
            self.type_label.config(text="🔗 Git URL로 인식 (git clone)", foreground=_C_ACCENT)
        else:
            self.type_label.config(text="📁 폴더/파일 경로로 인식", foreground=_C_OK)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """현재 상태(입력칸/큐/결과 탭/분석중)에 맞춰 버튼 활성/비활성을 토글한다."""
        has_text = bool(self.entry.get().strip())
        qcount = self.queue_list.size()
        self.add_btn.config(state="normal" if has_text else "disabled")
        self.clear_btn.config(state="normal" if qcount else "disabled")
        self.del_btn.config(state="normal" if self.queue_list.curselection() else "disabled")
        if not self._analyzing:
            self.analyze_btn.config(state="normal" if (qcount or has_text) else "disabled")

    # ---------- 공통 ----------
    def _center_popup(self, top: tk.Toplevel) -> None:
        """팝업을 메인 창 중앙에 배치한다."""
        top.update_idletasks()
        w, h = top.winfo_width(), top.winfo_height()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        x = max(rx + (rw - w) // 2, 0)
        y = max(ry + (rh - h) // 2, 0)
        top.geometry(f"+{x}+{y}")

    # ---------- Git 상태 ----------
    def _refresh_git_status(self) -> None:
        """git 사용 가능 여부를 점검해 상단 상태칩과 도움말 버튼을 갱신한다."""
        available = shutil.which("git") is not None
        if available:
            self.git_status.config(text="● Git 사용 가능", fg=_C_OK)
            self.git_help_btn.config(fg=_C_ACCENT)
        else:
            self.git_status.config(text="● Git 없음 (URL 분석 불가)", fg=_C_WARN)
            self.git_help_btn.config(fg=_C_WARN)  # 없을 땐 빨강으로 주목

    def _show_git_help(self) -> None:
        """git 설치/연결 안내 팝업 (상태에 따라 내용이 달라짐)."""
        available = shutil.which("git") is not None
        top = tk.Toplevel(self.root)
        top.title("Git 안내")
        top.transient(self.root)
        top.configure(bg=_C_BG, padx=18, pady=16)
        if available:
            ttk.Label(top, text="Git 사용 가능", font=self.f_h3,
                      foreground=_C_OK).pack(anchor="w")
            msg = (
                "이 PC에서 git이 인식됩니다. ‘🔗 Git URL/경로’에 저장소 URL을 입력하면\n"
                "임시로 클론(`git clone --depth 1`)해 분석하고 끝나면 자동 정리합니다.\n\n"
                "● 폴더·파일 분석은 git과 무관하게 동작합니다.\n"
                "● 사내 GitHub(Enterprise)도 git 접근이 되면 동일하게 동작합니다."
            )
        else:
            ttk.Label(top, text="Git이 설치되어 있지 않습니다", font=self.f_h3,
                      foreground=_C_WARN).pack(anchor="w")
            msg = (
                "Git 저장소 URL을 입력해 분석하려면 실행 PC에 git이 필요합니다.\n"
                "(폴더·파일 분석은 git 없이도 정상 동작합니다.)\n\n"
                "● 설치 방법 (Windows)\n"
                "   - 인터넷 가능: https://git-scm.com/download/win 에서 설치\n"
                "     또는 명령창에서  winget install Git.Git\n"
                "   - 폐쇄망: 위 설치본(.exe)을 인터넷 PC에서 받아 사내 반입 후 설치\n\n"
                "● 설치 후 이 프로그램을 다시 실행하거나 ‘다시 확인’을 누르면 인식됩니다."
            )
        ttk.Label(top, text=msg, justify="left", foreground="#333",
                  wraplength=520).pack(anchor="w", pady=(8, 12))

        btns = ttk.Frame(top)
        btns.pack(fill="x")
        ttk.Button(btns, text="확인", style="Accent.TButton", command=top.destroy).pack(side="right")
        top.bind("<Escape>", lambda _e: top.destroy())
        self._center_popup(top)
        top.grab_set()

    # ---------- 큐 관리 ----------
    def _browse_menu(self) -> None:
        """하나의 '찾아보기' 버튼 → 폴더/파일 선택 메뉴를 버튼 아래에 띄운다."""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="📁 프로젝트 폴더 선택…", command=self._add_folder)
        menu.add_command(label="📄 개별 파일 선택…", command=self._add_files)
        b = self.browse_btn
        try:
            menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            menu.grab_release()

    def _add_folder(self) -> None:
        chosen = filedialog.askdirectory(title="분석할 프로젝트 폴더 선택")
        if chosen:
            self._enqueue([chosen])

    def _add_files(self) -> None:
        # 여러 파일 동시 선택 가능 (자바·문서 등 개별 파일 분석)
        paths = filedialog.askopenfilenames(title="분석할 프로젝트 파일 선택")
        if paths:
            self._enqueue(list(paths))

    def _add_to_queue(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        # 여러 줄 또는 세미콜론으로 여러 개 입력 지원
        parts = [p.strip() for chunk in text.split("\n") for p in chunk.split(";")]
        self._enqueue([p for p in parts if p])
        self.entry.delete(0, "end")
        self._on_entry_change()

    def _enqueue(self, items: list[str]) -> None:
        existing = set(self.queue_list.get(0, "end"))
        for it in items:
            if it not in existing:
                self.queue_list.insert("end", it)
                existing.add(it)
        self._refresh_buttons()

    def _del_selected(self) -> None:
        for idx in reversed(self.queue_list.curselection()):
            self.queue_list.delete(idx)
        self._refresh_buttons()

    def _clear_queue(self) -> None:
        self.queue_list.delete(0, "end")
        self._refresh_buttons()

    # ---------- 분석 ----------
    def _analyze(self) -> None:
        sources = list(self.queue_list.get(0, "end"))
        pending = self.entry.get().strip()
        if pending:  # 큐에 안 넣고 입력칸에만 있는 것도 포함
            for chunk in pending.split("\n"):
                for p in chunk.split(";"):
                    p = p.strip()
                    if p and p not in sources:
                        sources.append(p)
        if not sources:
            messagebox.showwarning("입력 필요", "분석할 프로젝트(폴더/파일/Git URL)를 추가하세요.")
            return

        self._analyzing = True
        self.analyze_btn.config(state="disabled")
        self.progress.pack(side="right")
        self.progress.start(12)
        self._clear_queue()
        self.entry.delete(0, "end")
        self._on_entry_change()
        threading.Thread(target=self._worker, args=(sources,), daemon=True).start()

    def _worker(self, sources: list[str]) -> None:
        failures: list[tuple[str, str]] = []
        total = len(sources)
        for i, src in enumerate(sources, 1):
            self.root.after(0, lambda i=i, s=src: self.status.config(
                text=f"분석 중 ({i}/{total}): {s}"))
            try:
                doc, meta = generate_document(src)
                self.root.after(0, self._add_result_tab, meta, doc)
            except source.SourceError as exc:
                failures.append((src, str(exc)))
            except (PermissionError, OSError) as exc:
                failures.append((src, f"파일 접근 오류: {exc}"))
            except Exception as exc:  # noqa: BLE001
                failures.append((src, f"예기치 못한 오류: {exc}"))
        self.root.after(0, self._finish, total, failures)

    def _finish(self, total: int, failures: list[tuple[str, str]]) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self._analyzing = False
        self._refresh_buttons()
        ok = total - len(failures)
        self.status.config(text=f"완료: 성공 {ok} / 실패 {len(failures)} (총 {total})")
        if failures:
            msg = "\n".join(f"• {s}\n   → {e}" for s, e in failures)
            messagebox.showwarning("일부 분석 실패", msg)

    # ---------- 결과 탭 ----------
    @staticmethod
    def _todo_count(doc: str) -> int:
        """직접 작성이 필요한 빈 항목(placeholder) 수."""
        return doc.count("직접 작성")

    def _add_result_tab(self, meta, doc: str) -> None:
        outer = ttk.Frame(self.results_nb, padding=0)
        tab_id = str(outer)
        n_sens = len(meta.sensitive)

        # 탭 상단 헤더: (좌) 민감정보 상태 + 직접작성 잔여(클릭 이동) / (우) 저장
        header = tk.Frame(outer, bg=_C_BG)
        header.pack(fill="x", padx=8, pady=(8, 0))
        if n_sens:
            tk.Label(header, bg=_C_BG, fg=_C_WARN, font=self.f_label,
                     text=f"⚠️ 민감정보 {n_sens}건").pack(side="left")
        else:
            tk.Label(header, bg=_C_BG, fg=_C_OK, font=self.f_label,
                     text="✓ 민감정보 없음").pack(side="left")
        todo_label = tk.Label(header, bg=_C_BG, font=self.f_label)
        todo_label.pack(side="left")
        todo_label.bind("<Button-1>", lambda _e: self._jump_to_todo(tab_id))

        save = tk.Button(header, text="💾  이 결과 저장", command=lambda: self._save_tab(tab_id),
                         bg=_C_OK, fg="white", activebackground="#15692d", activeforeground="white",
                         font=("Segoe UI", 10, "bold"), relief="flat", padx=14, pady=5, cursor="hand2")
        save.pack(side="right")

        sub = ttk.Notebook(outer)
        sub.pack(fill="both", expand=True, pady=(8, 0))
        tab_summary = ttk.Frame(sub, padding=10)
        tab_files = ttk.Frame(sub, padding=10)
        tab_doc = ttk.Frame(sub, padding=0)
        sens_mark = f" ⚠{n_sens}" if n_sens else ""
        sub.add(tab_summary, text=f"  요약{sens_mark}  ")
        sub.add(tab_files, text=f"  파일 ({len(meta.files)})  ")
        sub.add(tab_doc, text="  문서  ")
        self._build_summary(tab_summary, meta)
        self._build_files(tab_files, meta)

        # 문서 탭: 안쪽 상단에 수정 버튼(예쁜 색) + 그 아래 문서 뷰
        doc_bar = tk.Frame(tab_doc, bg=_C_BG)
        doc_bar.pack(fill="x", padx=8, pady=(8, 2))
        tk.Label(doc_bar, bg=_C_BG, fg="#888", font=("Segoe UI", 9),
                 text="문서를 직접 다듬을 수 있어요").pack(side="left")
        edit_btn = tk.Button(doc_bar, text="✏  문서 직접 수정",
                             command=lambda: self._toggle_edit(tab_id),
                             bg="#eaf1ff", fg=_C_ACCENT, activebackground="#d8e6ff",
                             activeforeground=_C_ACCENT, font=("Segoe UI", 10, "bold"),
                             relief="flat", bd=0, padx=14, pady=5, cursor="hand2")
        edit_btn.pack(side="right")
        doc_host = ttk.Frame(tab_doc)
        doc_host.pack(fill="both", expand=True)
        doc_widget = self._make_doc_widget(doc_host)
        self._render_doc(doc_widget, doc)

        # 민감정보 유무를 탭에서 색(빨강/초록 점)으로 구분
        label = (meta.name or "result")[:24]
        dot = "🔴" if n_sens else "🟢"
        self.results_nb.add(outer, text=f"  {dot} {label}  ")
        self._results[tab_id] = {
            "doc": doc, "name": meta.name, "widget": doc_widget,
            "sub": sub, "tab_doc": tab_doc, "edit_btn": edit_btn,
            "todo_label": todo_label, "editing": False, "edited": set(),
            # 초기화용: 원본 '직접 작성 필요' 줄을 줄번호별로 보관
            "original_todo": {i: ln for i, ln in enumerate(doc.split("\n"))
                              if "직접 작성" in ln},
        }
        self._update_todo_label(tab_id)
        self._update_results_view()
        self.results_nb.select(outer)
        self._refresh_buttons()

    def _update_todo_label(self, tab_id: str) -> None:
        rec = self._results[tab_id]
        n = self._todo_count(rec["doc"])
        if n:
            rec["todo_label"].config(text=f"    ✍ 직접 작성 필요 {n}곳 (클릭해 이동)",
                                     fg="#a15c00", cursor="hand2")
        else:
            rec["todo_label"].config(text="    ✓ 빈 항목 없음", fg=_C_OK, cursor="")

    def _jump_to_todo(self, tab_id: str) -> None:
        """직접작성 표시 클릭 시 문서에서 다음 '직접 작성' 위치로 스크롤·강조한다."""
        rec = self._results.get(tab_id)
        if not rec:
            return
        rec["sub"].select(rec["tab_doc"])  # 문서 탭으로 전환
        w = rec["widget"]
        start = rec.get("todo_pos", "1.0")
        pos = w.search("직접 작성", start, stopindex="end")
        if not pos:  # 끝까지 갔으면 처음부터 다시 (순환)
            pos = w.search("직접 작성", "1.0", stopindex="end")
        if not pos:
            self.status.config(text="직접 작성이 필요한 위치가 없습니다.")
            return
        w.see(pos)
        w.tag_remove("jump", "1.0", "end")
        w.tag_add("jump", f"{pos} linestart", f"{pos} lineend")
        rec["todo_pos"] = f"{pos}+1c"  # 다음 클릭은 그 다음 항목으로
        self.status.config(text="직접 작성이 필요한 위치로 이동했습니다. (다시 클릭하면 다음 위치)")

    def _toggle_edit(self, tab_id: str) -> None:
        """문서 탭을 읽기/편집 모드로 토글한다."""
        rec = self._results.get(tab_id)
        if not rec:
            return
        self.results_nb.select(tab_id)
        rec["sub"].select(rec["tab_doc"])  # 문서 하위 탭으로 전환
        w = rec["widget"]
        if not rec["editing"]:
            # 편집 모드: 원본 Markdown을 평문으로 열어 직접 수정
            rec["editing"] = True
            w.config(state="normal", bg="#fffdf5")
            for t in ("h1", "h2", "h3", "code", "quote", "bullet", "todo"):
                w.tag_remove(t, "1.0", "end")
            w.delete("1.0", "end")
            w.insert("1.0", rec["doc"])
            w.focus_set()
            rec["edit_btn"].config(text="✓  수정 완료", fg="white", bg=_C_ACCENT,
                                   activebackground="#2559c4", activeforeground="white")
            self.status.config(text="편집 모드 — Markdown을 직접 수정한 뒤 ‘수정 완료’를 누르세요.")
        else:
            # 읽기 모드 복귀: 변경분 반영 + 다시 렌더
            rec["editing"] = False
            rec["doc"] = w.get("1.0", "end-1c")
            rec["edited"] = set()  # 전체 편집은 줄 번호가 바뀔 수 있어 직접입력 표시 초기화
            w.config(bg=_C_CARD)
            self._render_doc(w, rec["doc"])
            rec["edit_btn"].config(text="✏  문서 직접 수정", fg=_C_ACCENT, bg="#eaf1ff",
                                   activebackground="#d8e6ff", activeforeground=_C_ACCENT)
            self._update_todo_label(tab_id)
            self.status.config(text="문서를 수정했습니다. ‘이 결과 저장’으로 내보내세요.")

    def _on_tab_close(self, tab_id: str) -> None:
        """탭 제목의 ✕ 클릭 시 호출."""
        if tab_id in self._results:
            self.results_nb.forget(tab_id)
            self._results.pop(tab_id, None)
            self._update_results_view()
            self._refresh_buttons()

    def _save_tab(self, tab_id: str) -> None:
        rec = self._results.get(tab_id)
        if rec:
            self._save_doc(rec["doc"], rec["name"])

    def _save_doc(self, doc: str, name: str) -> None:
        path = filedialog.asksaveasfilename(
            title="문서 저장", defaultextension=".md",
            initialfile=f"{name}-handover.md",
            filetypes=[("Markdown", "*.md"), ("HTML", "*.html"),
                       ("텍스트", "*.txt"), ("모든 파일", "*.*")])
        if not path:
            return
        # 선택한 확장자에 맞춰 변환 (HTML이면 변환, 그 외엔 Markdown 원문).
        content = export.render(doc, Path(path).suffix, f"{name} 인수인계 문서")
        try:
            Path(path).write_text(content, encoding="utf-8")
            self.status.config(text=f"저장됨: {path}")
        except OSError as exc:
            messagebox.showerror("저장 실패", str(exc))

    # ---------- 요약 렌더 ----------
    @staticmethod
    def _project_summary(meta) -> str:
        """이 프로젝트가 어떤 것인지 한 줄 요약. README 첫 설명 줄 우선, 없으면 도출."""
        if meta.readme_excerpt:
            lines = meta.readme_excerpt.splitlines()
            # 헤딩(#)이 아닌 첫 설명 줄을 우선 사용
            for line in lines:
                s = line.strip()
                if s and not s.startswith("#"):
                    return s[:200]
            # 설명 줄이 없으면 제목이라도
            for line in lines:
                s = line.strip().lstrip("#").strip()
                if s:
                    return s[:200]
        langs = ", ".join(meta.languages) or "유형 미상"
        bits = [f"{langs} 프로젝트"]
        if meta.run_entries:
            bits.append(f"진입점 {len(meta.run_entries)}개")
        if meta.ports:
            bits.append("포트 " + ", ".join(meta.ports))
        return " · ".join(bits) + "  (README 설명 없음)"

    def _fill_sensitive(self, frame: ttk.LabelFrame, meta) -> None:
        """민감정보 표를 주어진 프레임에 채운다 (프로젝트/파일 요약 공용)."""
        if meta.sensitive:
            tv = ttk.Treeview(frame, columns=("kind", "loc", "conf"), show="headings", height=8)
            tv.heading("kind", text="종류")
            tv.heading("loc", text="위치")
            tv.heading("conf", text="신뢰도")
            tv.column("kind", width=150)
            tv.column("loc", width=130)
            tv.column("conf", width=55, anchor="center")
            for conf, color in _CONF_COLOR.items():
                tv.tag_configure(conf, background=color)
            for s in meta.sensitive:
                tv.insert("", "end", values=(s.kind, f"{s.file}:{s.line}", s.confidence),
                          tags=(s.confidence,))
            tv.pack(fill="both", expand=True)
            ttk.Label(frame, foreground="#777", font=("Segoe UI", 8),
                      text="값은 마스킹됨. 환경변수/시크릿 매니저로 분리 권장.").pack(anchor="w", pady=(4, 0))
        else:
            ttk.Label(frame, foreground=_C_OK,
                      text="✓ 발견된 민감정보 의심 항목이 없습니다.").pack(pady=20)

    def _build_file_summary(self, parent: ttk.Frame, meta) -> None:
        """단일 파일용 요약 — 파일 카드 + 코드 분석 + 민감정보."""
        c = meta.code
        card = tk.Frame(parent, bg=_C_CARD, highlightbackground="#e3e6ea", highlightthickness=1)
        card.pack(fill="x", pady=(0, 8))
        inner = tk.Frame(card, bg=_C_CARD, padx=12, pady=10)
        inner.pack(fill="x")
        ttk.Label(inner, text=f"📄 {meta.name}", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        desc_text = (c.description if c and c.description
                     else (meta.languages[0] + " 파일" if meta.languages else "비코드/문서 파일"))
        tk.Label(inner, text=desc_text, bg=_C_CARD, fg="#444", font=self.f_body,
                 wraplength=820, justify="left", anchor="w").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 10))

        def kv(r, key, val):
            ttk.Label(inner, text=key, style="Key.TLabel").grid(
                row=r, column=0, sticky="nw", pady=2, padx=(0, 10))
            ttk.Label(inner, text=val or "—", style="Card.TLabel",
                      wraplength=820, justify="left").grid(row=r, column=1, sticky="w", pady=2)

        kv(2, "출처", meta.root)
        kv(3, "언어", ", ".join(meta.languages) or "비코드/미상")
        kv(4, "코드 줄 수", f"{c.loc}줄" if c else "—")
        inner.columnconfigure(1, weight=1)

        cols = ttk.Frame(parent)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)
        cols.rowconfigure(0, weight=1)

        # 코드 분석 (무엇을 하는 코드인가)
        left = ttk.LabelFrame(cols, text=" 코드 분석 (무엇을 하는 코드인가) ", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        lt = tk.Text(left, wrap="word", font=self.f_body, relief="flat", bg="#fbfbfc")
        lsb = ttk.Scrollbar(left, command=lt.yview)
        lt.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        lt.pack(side="left", fill="both", expand=True)
        lt.tag_configure("hd", font=("Segoe UI", 9, "bold"), foreground=_C_ACCENT)
        if c:
            for line in c.summary:
                lt.insert("end", f"• {line}\n")
            lt.insert("end", "\n■ 구조\n", "hd")
            lt.insert("end", f"   임포트: {', '.join(c.imports) if c.imports else '없음'}\n")
            lt.insert("end", f"   클래스: {', '.join(c.classes) if c.classes else '없음'}\n")
            lt.insert("end", f"   함수/메서드: {', '.join(c.functions) if c.functions else '없음'}\n")
        else:
            lt.insert("end", "코드 파일이 아니거나 내용 분석을 생략했습니다.\n"
                             "(바이너리/문서 파일은 구조 분석 대상이 아닙니다.)")
        lt.configure(state="disabled")

        right = ttk.LabelFrame(cols, text=" ⚠️ 민감정보 의심 ", padding=6)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._fill_sensitive(right, meta)

    def _build_summary(self, parent: ttk.Frame, meta) -> None:
        if meta.kind == "file":
            self._build_file_summary(parent, meta)
            return
        card = tk.Frame(parent, bg=_C_CARD, highlightbackground="#e3e6ea", highlightthickness=1)
        card.pack(fill="x", pady=(0, 8))
        inner = tk.Frame(card, bg=_C_CARD, padx=12, pady=10)
        inner.pack(fill="x")
        ttk.Label(inner, text=f"📦 {meta.name}", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w")
        # 제목 아래 간격 + 이 프로젝트가 어떤 것인지 한눈 요약
        desc = tk.Label(inner, text=self._project_summary(meta), bg=_C_CARD,
                        fg="#444", font=self.f_body, wraplength=820, justify="left",
                        anchor="w")
        desc.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 10))

        def kv(r, key, val):
            ttk.Label(inner, text=key, style="Key.TLabel").grid(
                row=r, column=0, sticky="nw", pady=2, padx=(0, 10))
            ttk.Label(inner, text=val or "—", style="Card.TLabel",
                      wraplength=820, justify="left").grid(row=r, column=1, sticky="w", pady=2)

        kv(2, "출처", meta.root)
        kv(3, "주요 언어", ", ".join(meta.languages) or "확인 필요")
        kv(4, "파일 수", f"{len(meta.files)}개")
        kv(5, "감지된 포트", ", ".join(meta.ports) or "없음")
        kv(6, "필요 환경변수", ", ".join(meta.env_vars) or "없음")
        inner.columnconfigure(1, weight=1)

        cols = ttk.Frame(parent)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)
        cols.rowconfigure(0, weight=1)

        # 준비 · 설치 · 실행
        left = ttk.LabelFrame(cols, text=" 준비 · 설치 · 실행 ", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        lt = tk.Text(left, wrap="word", font=self.f_mono, relief="flat", bg="#fbfbfc")
        lsb = ttk.Scrollbar(left, command=lt.yview)
        lt.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        lt.pack(side="left", fill="both", expand=True)
        lt.tag_configure("hd", font=("Segoe UI", 9, "bold"), foreground=_C_ACCENT)
        if meta.prerequisites:
            lt.insert("end", "■ 준비사항\n", "hd")
            for p in meta.prerequisites:
                lt.insert("end", f"   - {p}\n")
            lt.insert("end", "\n")
        if meta.dependencies:
            lt.insert("end", "■ 의존성\n", "hd")
            for g in meta.dependencies:
                lt.insert("end", f"   {g.source}\n")
                for item in g.items:
                    lt.insert("end", f"      - {item}\n")
            lt.insert("end", "\n")
        if meta.run_entries:
            lt.insert("end", "■ 실행 방법\n", "hd")
            for e in meta.run_entries:
                lt.insert("end", f"   - ({e.kind}) {e.detail}\n")
        if not (meta.prerequisites or meta.dependencies or meta.run_entries):
            lt.insert("end", "자동 감지된 항목 없음 — 직접 확인 필요")
        lt.configure(state="disabled")

        # 민감정보 표 (공용 헬퍼)
        right = ttk.LabelFrame(cols, text=" ⚠️ 민감정보 의심 ", padding=6)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._fill_sensitive(right, meta)

    # ---------- 파일 목록 렌더 ----------
    def _build_files(self, parent: ttk.Frame, meta) -> None:
        from collections import Counter

        def ext_of(path: str) -> str:
            base = path.rsplit("/", 1)[-1]
            return "." + base.rsplit(".", 1)[1].lower() if "." in base else "(확장자 없음)"

        # 확장자 분포 요약 (파일 종류 통계)
        counts = Counter(ext_of(f) for f in meta.files)
        top = "  ·  ".join(f"{e} {c}" for e, c in counts.most_common(10))
        ttk.Label(parent, text=f"총 {len(meta.files)}개 파일    {top}",
                  foreground="#555", wraplength=820, justify="left").pack(
            anchor="w", pady=(0, 6))

        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        tv = ttk.Treeview(holder, columns=("path", "type"), show="headings")
        tv.heading("path", text="경로")
        tv.heading("type", text="종류")
        tv.column("path", width=540)
        tv.column("type", width=110, anchor="center")
        sb = ttk.Scrollbar(holder, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)
        for f in meta.files:
            tv.insert("", "end", values=(f, ext_of(f)))
        if not meta.files:
            ttk.Label(parent, foreground="#888",
                      text="분석 대상 파일이 없습니다.").pack(anchor="w")

    # ---------- 문서 렌더 ----------
    def _make_doc_widget(self, parent: ttk.Frame) -> tk.Text:
        w = tk.Text(parent, wrap="word", font=self.f_body, padx=14, pady=12,
                    relief="flat", bg=_C_CARD, spacing1=2, spacing3=2, undo=True)
        sb = ttk.Scrollbar(parent, command=w.yview)
        w.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        w.pack(side="left", fill="both", expand=True)
        w.tag_configure("h1", font=self.f_title, foreground=_C_ACCENT, spacing1=10, spacing3=6)
        w.tag_configure("h2", font=self.f_h2, foreground="#222", spacing1=10, spacing3=4)
        w.tag_configure("h3", font=self.f_h3, spacing1=6, spacing3=2)
        w.tag_configure("code", font=self.f_mono, background="#f1f3f5", lmargin1=14, lmargin2=14)
        w.tag_configure("quote", font=self.f_body, foreground="#777", lmargin1=10, lmargin2=10)
        w.tag_configure("bullet", font=self.f_body, lmargin1=18, lmargin2=30)
        # 직접 작성/확인 필요 강조 (노란 배경). 편집은 줄 우측의 ✏ 버튼으로 한다.
        w.tag_configure("todo", background="#fff3bf", foreground="#7a5d00")
        # 사용자가 직접 입력한 줄 (옅은 파랑)
        w.tag_configure("filled", background="#e8f0ff", foreground="#13386b")
        # 클릭 이동 시 해당 줄 강조
        w.tag_configure("jump", background="#ffe08a")
        w._todo_btns = []  # type: ignore[attr-defined]  # 줄 우측 편집 버튼들
        return w

    def _render_doc(self, w: tk.Text, md: str) -> None:
        """Markdown을 서식 적용해 읽기 전용으로 표시.

        - '직접 작성 필요' 줄: 노란 강조 + 우측 ✏ 편집 버튼
        - 사용자가 직접 입력한 줄(rec['edited']): 옅은 파랑 + 우측 ✏ 편집 버튼(재편집)
        표시 줄 ↔ 원본 줄 매핑(w._disp_to_src / w._src_to_disp)도 남긴다.
        """
        edited = self._edited_set_for(w)
        w.config(state="normal")
        for b in getattr(w, "_todo_btns", []):
            b.destroy()
        w._todo_btns = []  # type: ignore[attr-defined]
        for t in ("h1", "h2", "h3", "code", "quote", "bullet", "todo", "filled", "jump"):
            w.tag_remove(t, "1.0", "end")
        w.delete("1.0", "end")
        disp_to_src: dict[int, int] = {}
        src_to_disp: dict[int, int] = {}
        disp = 1
        in_code = False
        for src_i, line in enumerate(md.split("\n")):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue  # 코드펜스 줄은 표시하지 않음
            if in_code or stripped.startswith("|"):
                w.insert("end", line + "\n", "code")
            elif line.startswith("### "):
                w.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                w.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                w.insert("end", line[2:] + "\n", "h1")
            elif stripped.startswith("> "):
                w.insert("end", stripped[2:] + "\n", "quote")
            elif stripped.startswith("- "):
                indent = "    " if line.startswith("  ") else ""
                w.insert("end", f"{indent}•  {stripped[2:]}\n", "bullet")
            else:
                w.insert("end", line + "\n")
            disp_to_src[disp] = src_i
            src_to_disp[src_i] = disp

            has_todo = "직접 작성" in line
            is_filled = (src_i in edited) and not has_todo
            if is_filled:  # 직접 입력한 줄은 옅은 파랑으로 표시
                w.tag_add("filled", f"{disp}.0", f"{disp}.end")
            if has_todo or is_filled:  # 두 경우 모두 우측에 편집 버튼 유지
                bg, fg = ("#fff0b8", _C_ACCENT) if has_todo else ("#dbe7ff", "#13386b")
                btn = tk.Button(w, text="✏ 편집",
                                command=lambda s=src_i: self._edit_line_at(w, s),
                                font=("Segoe UI", 8, "bold"), fg=fg, bg=bg,
                                activebackground="#cfe0ff", activeforeground=fg,
                                relief="flat", bd=0, padx=6, pady=0, cursor="hand2")
                w.window_create(f"{disp}.end", window=btn, padx=6)
                w._todo_btns.append(btn)
            disp += 1
        w._disp_to_src = disp_to_src   # type: ignore[attr-defined]
        w._src_to_disp = src_to_disp   # type: ignore[attr-defined]
        # 직접 작성/확인 필요 문구 강조
        for marker in ("확인 필요", "직접 작성"):
            start = "1.0"
            while True:
                pos = w.search(marker, start, stopindex="end")
                if not pos:
                    break
                w.tag_add("todo", pos, f"{pos}+{len(marker)}c")
                start = f"{pos}+{len(marker)}c"
        w.configure(state="disabled")

    def _edited_set_for(self, w: tk.Text) -> set:
        """이 문서 위젯에 해당하는 rec의 '직접 입력된 줄' 집합을 돌려준다."""
        rec = next((r for r in self._results.values() if r["widget"] is w), None)
        return rec.get("edited", set()) if rec else set()

    def _edit_line_at(self, w: tk.Text, src_i: int) -> None:
        """줄 우측 ✏ 버튼 클릭 → 그 원본 줄만 편집."""
        tab_id, rec = next(((tid, r) for tid, r in self._results.items()
                            if r["widget"] is w), (None, None))
        if rec is None or rec.get("editing"):
            return
        self._edit_single_line(tab_id, rec, src_i)

    _TODO_MARK = "✍ **직접 작성 필요**"

    @staticmethod
    def _section_title(src_lines: list, src_i: int) -> str:
        """해당 줄 위쪽의 가장 가까운 '## N. 제목' 섹션 제목을 돌려준다."""
        for i in range(min(src_i, len(src_lines) - 1), -1, -1):
            s = src_lines[i].strip()
            if s.startswith("## "):
                return s[3:].strip()
        return ""

    @staticmethod
    def _field_label(prefix: str) -> str:
        """접두에서 항목명(굵게 **..** 또는 `..`)을 뽑는다."""
        for sep in ("**", "`"):
            if prefix.count(sep) >= 2:
                return prefix.split(sep)[1].strip()
        return ""

    def _edit_single_line(self, tab_id: str, rec: dict, src_i: int) -> None:
        """원본 Markdown의 한 줄만 팝업으로 편집한다.

        '✍ 직접 작성 필요 — 힌트' 줄은 접두(라벨)는 유지하고, 힌트를 입력칸의
        회색 플레이스홀더로 보여준 뒤 사용자가 값만 채우게 한다.
        """
        src_lines = rec["doc"].split("\n")
        if not (0 <= src_i < len(src_lines)):
            return
        current = src_lines[src_i]

        section = self._section_title(src_lines, src_i)
        if self._TODO_MARK in current:
            prefix, after = current.split(self._TODO_MARK, 1)
            hint = after.lstrip(" —").strip() or "내용을 입력하세요"
            field = self._field_label(prefix)
            prefilled, is_placeholder_line = "", True
        else:
            prefix, hint, field = "", "", ""
            prefilled, is_placeholder_line = current, False

        top = tk.Toplevel(self.root)
        top.title("직접 작성")
        top.transient(self.root)
        top.configure(bg=_C_BG, padx=16, pady=14)
        # 위: 이 줄이 속한 섹션(숫자.제목) / 아래: 작성 항목
        ttk.Label(top, text=f"📄 {section}" if section else "직접 작성",
                  font=self.f_h3, foreground=_C_ACCENT).pack(anchor="w")
        ttk.Label(top, text=(f"작성 항목: {field}" if field else "이 줄의 내용을 작성하세요"),
                  foreground="#666").pack(anchor="w", pady=(2, 8))

        ph_color, normal_color = "#9aa1ab", "#1b1b1b"
        entry = tk.Entry(top, width=92, font=self.f_body, fg=normal_color,
                         relief="solid", bd=1)
        entry.pack(fill="x", ipady=4, pady=(8, 8))

        state = {"placeholder": False}

        def show_placeholder():
            entry.delete(0, "end")
            entry.insert(0, hint)
            entry.config(fg=ph_color)
            state["placeholder"] = True

        def real_value() -> str:
            return "" if state["placeholder"] else entry.get().strip()

        if is_placeholder_line and hint:
            show_placeholder()
            entry.icursor(0)  # 커서를 맨 앞에 둬서 '플레이스홀더 뒤' 느낌 제거
        else:
            entry.insert(0, prefilled)
            entry.icursor("end")

        def on_key(event):
            if state["placeholder"] and event.char and event.char.isprintable():
                entry.delete(0, "end")
                entry.config(fg=normal_color)
                state["placeholder"] = False

        def on_focus_out(_e):
            if is_placeholder_line and hint and not entry.get().strip():
                show_placeholder()
                entry.icursor(0)

        entry.bind("<Key>", on_key)
        entry.bind("<FocusOut>", on_focus_out)
        entry.focus_set()
        entry.icursor(0)

        def _rerender_to(src_index: int, msg: str):
            self._render_doc(rec["widget"], rec["doc"])
            self._update_todo_label(tab_id)
            disp = getattr(rec["widget"], "_src_to_disp", {}).get(src_index)
            if disp:
                rec["widget"].see(f"{disp}.0")
            self.status.config(text=msg)

        has_original = src_i in rec.get("original_todo", {})

        def reset_to_todo():
            """이 줄을 수정 전 '직접 작성 필요' 상태(노란 강조)로 되돌린다."""
            orig = rec.get("original_todo", {}).get(src_i)
            if orig is not None:
                src_lines[src_i] = orig
                rec["doc"] = "\n".join(src_lines)
                rec.get("edited", set()).discard(src_i)
                _rerender_to(src_i, "‘직접 작성 필요’ 상태로 되돌렸습니다.")
            top.destroy()

        def apply(_e=None):
            value = real_value()
            if value:
                src_lines[src_i] = f"{prefix}{value}" if is_placeholder_line else value
                rec["doc"] = "\n".join(src_lines)
                rec.setdefault("edited", set()).add(src_i)  # 직접 입력 표시(파랑) 유지
                _rerender_to(src_i, "해당 줄을 작성했습니다. ‘이 결과 저장’으로 내보내세요.")
                top.destroy()
            elif has_original:
                # 빈 값으로 적용하면 원래 '직접 작성 필요' 상태로 되돌린다.
                reset_to_todo()
            else:
                top.destroy()

        btns = ttk.Frame(top)
        btns.pack(fill="x")
        ttk.Button(btns, text="적용", style="Accent.TButton", command=apply).pack(side="right")
        ttk.Button(btns, text="취소", command=top.destroy).pack(side="right", padx=(0, 6))
        if has_original:
            ttk.Button(btns, text="↩ 초기화(직접작성 필요로)",
                       command=reset_to_todo).pack(side="left")
        entry.bind("<Return>", apply)
        top.bind("<Escape>", lambda _e: top.destroy())
        self._center_popup(top)
        top.grab_set()


def run() -> None:
    """GUI 앱을 실행한다 (창이 닫힐 때까지 블로킹)."""
    root = tk.Tk()
    HandoverApp(root)
    root.mainloop()
