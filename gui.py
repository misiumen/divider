"""Okienko generatora: kampania, suwaki, podgląd z góry, Generuj.   python gui.py   (exe: ArkhamDividers.exe)

Suwaki zmieniają layout.toml w pamięci; podgląd rysuje dokładnie tę geometrię 2D, która idzie do STL.
Ustawienia zapisują się w settings.json obok programu po każdym generowaniu.
"""
import copy
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import arkham_dividers as ad
import divider_cad as cad

SETTINGS = ad.ROOT / "settings.json"
# (sekcja, klucz, etykieta, min, max, krok)
SLIDERS = [
    ("plate", "width", "Szerokość", 60, 110, 1),
    ("plate", "height", "Wysokość", 70, 140, 1),
    ("plate", "corner_radius", "Zaokrąglenie rogów", 1, 6, 0.5),
    ("tab", "width", "Zakładka: szerokość", 15, 50, 1),
    ("tab", "height", "Zakładka: wysokość", 8, 30, 1),
    ("tab", "slots", "Zakładka: pozycje", 1, 5, 1),
    ("tab", "margin", "Zakładka: margines", 4, 20, 0.5),
    ("pattern", "cell", "Wzór: oczko", 3, 14, 0.5),
    ("pattern", "wall", "Wzór: ścianka", 1, 4, 0.1),
    ("pattern", "border", "Wzór: ramka", 2, 12, 0.5),
    ("title", "size", "Tytuł: rozmiar", 4, 12, 0.5),
    ("title", "y", "Tytuł: pozycja Y", -50, 60, 1),
    ("count", "size", "Liczba kart: rozmiar", 3, 12, 0.5),
    ("count", "y", "Liczba kart: pozycja Y", -50, 60, 1),
    ("icon", "size", "Ikona: rozmiar", 5, 30, 0.5),
]
PLATE, HOLE, RELIEF, GHOST = "#e6e2d8", "white", "#2b2b2b", "#b8b8b8"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Arkham Horror LCG – przekładki")
        self.core = ad.fetch(f"{ad.DATA_URL}/core.json", "core.json")
        self.L = ad.load_layout(ad.ROOT / "layout.toml")
        saved = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
        self.counts = saved.pop("counts", {})  # {campaign: {divider code: count}}
        for sec, vals in saved.items():
            self.L[sec].update(vals)
        self.campaigns = {f'{s["name"]}  [{s["code"]}]': s["code"] for s in self.core["stories"] if s.get("is_official")}
        self._job = None

        left = ttk.Frame(self, padding=8)
        left.grid(row=0, column=0, sticky="n")
        left.columnconfigure(1, weight=1)
        self.canvas = tk.Canvas(self, width=440, height=640, bg="white", highlightthickness=0)
        self.canvas.grid(row=0, column=1, padx=8, pady=8, sticky="n")
        self.table = ttk.Treeview(self, columns=("nr", "title", "count"), show="headings", height=30)
        for col, text, w in (("nr", "nr", 36), ("title", "tytuł (dwuklik w liczbę = zmiana)", 230), ("count", "kart", 50)):
            self.table.heading(col, text=text)
            self.table.column(col, width=w, anchor="w" if col == "title" else "e")
        self.table.grid(row=0, column=2, pady=8, sticky="ns")
        scroll = ttk.Scrollbar(self, command=self.table.yview)
        scroll.grid(row=0, column=3, pady=8, sticky="ns")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", lambda _e: self.table.selection() and int(self.table.selection()[0]) != self.preview_idx.get() and self.preview_idx.set(int(self.table.selection()[0])))
        self.table.bind("<Double-1>", self.edit_count)
        self.shown = []

        self.campaign = tk.StringVar(value=next(k for k, v in self.campaigns.items() if v == "eoe"))
        self.lang = tk.StringVar(value="pl")
        self.ret = tk.BooleanVar(value=False)
        self.pattern = tk.StringVar(value=self.L["pattern"]["type"])
        self.preview_idx = tk.IntVar(value=2)
        self.status = tk.StringVar()

        r = 0
        ttk.Label(left, text="Kampania").grid(row=r, column=0, sticky="w")
        ttk.Combobox(left, textvariable=self.campaign, values=list(self.campaigns), state="readonly", width=38).grid(row=r, column=1, columnspan=2, sticky="ew")
        r += 1
        ttk.Label(left, text="Język").grid(row=r, column=0, sticky="w")
        ttk.Combobox(left, textvariable=self.lang, values=self.core["languages"], state="readonly", width=8).grid(row=r, column=1, sticky="w")
        ttk.Checkbutton(left, text="zestawy Return to…", variable=self.ret, command=self.schedule).grid(row=r, column=2, sticky="w")
        r += 1
        ttk.Label(left, text="Wzór").grid(row=r, column=0, sticky="w")
        pat = ttk.Frame(left)
        pat.grid(row=r, column=1, columnspan=2, sticky="w")
        for p in ("hex", "grid", "solid"):
            ttk.Radiobutton(pat, text=p, value=p, variable=self.pattern, command=self.schedule).pack(side="left")
        r += 1
        self.vars = {}
        for sec, key, label, lo, hi, step in SLIDERS:
            v = tk.DoubleVar(value=self.L[sec][key])
            self.vars[(sec, key)] = (v, step)
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w")
            ttk.Scale(left, from_=lo, to=hi, variable=v, command=lambda _e: self.schedule()).grid(row=r, column=1, sticky="ew")
            shown = tk.StringVar()
            v.trace_add("write", lambda *_a, v=v, s=step, out=shown: out.set(f"{self.snap(v.get(), s):g}"))
            shown.set(f"{self.snap(v.get(), step):g}")
            ttk.Label(left, textvariable=shown, width=6).grid(row=r, column=2)
            r += 1
        ttk.Label(left, text="Podgląd przekładki nr").grid(row=r, column=0, sticky="w")
        ttk.Spinbox(left, from_=1, to=99, textvariable=self.preview_idx, width=5, command=self.schedule).grid(row=r, column=1, sticky="w")
        r += 1
        self.progress = ttk.Progressbar(left, maximum=1.0)
        self.progress.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        r += 1
        self.button = ttk.Button(left, text="Generuj STL", command=self.generate)
        self.button.grid(row=r, column=0, columnspan=3, sticky="ew")
        r += 1
        ttk.Label(left, textvariable=self.status, wraplength=360).grid(row=r, column=0, columnspan=3, sticky="w", pady=4)

        for var in (self.campaign, self.lang, self.preview_idx):
            var.trace_add("write", lambda *_a: self.schedule())
        self.after(50, self.refresh)

    @staticmethod
    def snap(value, step):
        return round(round(value / step) * step, 2)

    def layout(self):
        L = copy.deepcopy(self.L)
        for (sec, key), (v, step) in self.vars.items():
            L[sec][key] = int(self.snap(v.get(), step)) if key == "slots" else self.snap(v.get(), step)
        L["pattern"]["type"] = self.pattern.get()
        L["title"]["max_width"] = L["plate"]["width"] - 2 * L["pattern"]["border"] - 2
        return L

    def specs(self, L):
        code = self.campaigns[self.campaign.get()]
        specs = ad.prepare(code, self.lang.get(), L, self.ret.get(), log=lambda m: None)
        over = self.counts.get(code, {})
        for d in specs:  # the only place overrides apply: preview, STL and manifest all see this
            if d["code"] in over:
                d["count_original"], d["count"] = d["count"], over[d["code"]]
        return specs

    def edit_count(self, e):
        row = self.table.identify_row(e.y)
        if not row or self.table.identify_column(e.x) != "#3":
            return
        d = self.shown[int(row) - 1]
        v = simpledialog.askstring("Liczba kart", f"{d['title']}\n(puste = z danych: {d.get('count_original', d['count'])})", initialvalue=d["count"], parent=self)
        if v is None:
            return
        over = self.counts.setdefault(self.campaigns[self.campaign.get()], {})
        if not v.strip():
            over.pop(d["code"], None)
        elif v.strip().isdigit():
            over[d["code"]] = int(v)
        self.schedule()

    def schedule(self, *_):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(150, self.refresh)

    def refresh(self):
        self._job = None
        try:
            L = self.layout()
            specs = self.specs(L)
            i = min(max(1, self.preview_idx.get()), len(specs))
            spec = specs[i - 1]
            if specs != self.shown:
                self.table.delete(*self.table.get_children())
                for d in specs:
                    self.table.insert("", "end", iid=str(d["index"]), values=(d["index"], d["title"], f"{d['count']}*" if "count_original" in d else d["count"]))
                self.shown = specs
            self.table.selection_set(str(i))
            self.table.see(str(i))
            relief = cad.relief_geom(spec, L, ad.ICONS)
            holes = cad.pattern(L, relief)
            ghosts = [cad.outline_geom(L, s) for s in range(L["tab"]["slots"])]
            self.draw(L, ghosts, spec["slot"], holes, relief)
            self.status.set(f"{len(specs)} przekładek · podgląd {i}: {spec['title']} ({spec['count']} kart)")
        except Exception as e:  # ponytail: every validation error lands here as text, nothing crashes
            self.status.set(f"Błąd: {e}")

    def draw(self, L, ghosts, slot, holes, relief):
        c = self.canvas
        c.delete("all")
        W, H, T = L["plate"]["width"], L["plate"]["height"], L["tab"]["height"]
        cw, ch = int(c["width"]), int(c["height"])
        s = min((cw - 20) / W, (ch - 20) / (H + T))
        cx, cy = cw / 2, 10 + (H / 2 + T) * s

        def px(poly):
            return [(cx + x * s, cy - y * s) for x, y in poly.exterior.coords]

        for k, g in enumerate(ghosts):
            if k != slot:
                c.create_polygon(px(g), outline=GHOST, fill="", dash=(3, 3))
        c.create_polygon(px(ghosts[slot]), outline="#555", fill=PLATE, width=1.5)
        for g in cad._polys(holes) if holes is not None else []:
            c.create_polygon(px(g), outline="", fill=HOLE)
        for g in cad._polys(relief):
            c.create_polygon(px(g), outline="", fill=RELIEF)
            for hole in g.interiors:
                c.create_polygon([(cx + x * s, cy - y * s) for x, y in hole.coords], outline="", fill=PLATE)
        c.create_text(8, ch - 8, anchor="sw", text=f"{W:g} × {H + T:g} mm", fill="#777")

    def generate(self):
        try:
            L = self.layout()
            specs = self.specs(L)
            cad.check(L)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return
        self.button.state(["disabled"])
        code, lang = self.campaigns[self.campaign.get()], self.lang.get()
        out = ad.OUT / f"{code}_{lang}"
        out.mkdir(parents=True, exist_ok=True)

        events = queue.Queue()  # worker -> UI; Tk may only be touched from the main thread

        def work():
            try:
                for k, d in enumerate(specs, 1):
                    cad.export(cad.build(d, L, ad.ICONS), out / d["file"])
                    events.put(("progress", k / len(specs)))
                ad.write_manifest(specs, out / "manifest.csv")
                saved = {sec: {k: L[sec][k] for (s2, k) in self.vars if s2 == sec} for sec in {s for s, _ in self.vars}}
                saved["pattern"]["type"] = L["pattern"]["type"]
                saved["counts"] = self.counts
                SETTINGS.write_text(json.dumps(saved, indent=1), encoding="utf-8")
                events.put(("done", None))
            except Exception as e:
                events.put(("done", e))

        threading.Thread(target=work, daemon=True).start()
        self.poll(events, out)

    def poll(self, events, out):
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "progress":
                    self.progress.configure(value=value)
                else:
                    self.button.state(["!disabled"])
                    self.progress.configure(value=0)
                    if value:
                        messagebox.showerror("Błąd", str(value))
                    else:
                        self.status.set(f"Gotowe: {out}")
                        os.startfile(out)
                    return
        except queue.Empty:
            self.after(100, self.poll, events, out)


if __name__ == "__main__":
    App().mainloop()
