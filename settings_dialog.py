import tkinter as tk
from tkinter import ttk
from config_manager import load_config, save_config, DEFAULT_CONFIG

class SettingsWindow:
    def __init__(self, on_config_changed=None):
        self.on_config_changed = on_config_changed
        self.config = load_config()

        self.root = tk.Toplevel()
        self.root.title("Konfigurasi PC Health Overlay")
        self.root.geometry("420x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        # Bring to front
        self.root.attributes("-topmost", True)

        self.setup_ui()

    def setup_ui(self):
        # Header
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=16, pady=12)
        header_frame.pack(fill="x")

        title = tk.Label(
            header_frame,
            text="⚙️ Pengaturan PC Health Overlay",
            font=("Segoe UI", 12, "bold"),
            fg="#f8fafc",
            bg="#1e293b"
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            header_frame,
            text="Kustomisasi posisi layar, metrik aktif, dan format tampilan",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b"
        )
        subtitle.pack(anchor="w")

        # Main Scrollable / Form Body
        body = tk.Frame(self.root, bg="#0f172a", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        # 1. Posisi Layar
        pos_lbl = tk.Label(body, text="Posisi Layar", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a")
        pos_lbl.pack(anchor="w", pady=(4, 2))

        self.var_pos = tk.StringVar(value=self.config.get("position", "bottom-left"))
        pos_frame = tk.Frame(body, bg="#0f172a")
        pos_frame.pack(fill="x", pady=(0, 10))

        positions = [
            ("Pojok Kiri Bawah", "bottom-left"),
            ("Pojok Kanan Bawah", "bottom-right"),
            ("Pojok Kiri Atas", "top-left"),
            ("Pojok Kanan Atas", "top-right")
        ]
        for text, val in positions:
            rb = tk.Radiobutton(
                pos_frame,
                text=text,
                variable=self.var_pos,
                value=val,
                fg="#e2e8f0",
                bg="#0f172a",
                selectcolor="#1e293b",
                activebackground="#0f172a",
                activeforeground="#38bdf8",
                font=("Segoe UI", 9),
                command=self.apply_live
            )
            rb.pack(anchor="w")

        # 2. Ukuran Font
        font_lbl = tk.Label(body, text="Ukuran Font (pt)", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a")
        font_lbl.pack(anchor="w", pady=(6, 2))

        font_frame = tk.Frame(body, bg="#0f172a")
        font_frame.pack(fill="x", pady=(0, 10))

        self.var_font_size = tk.IntVar(value=self.config.get("font_size", 8))
        self.slider_font = tk.Scale(
            font_frame,
            from_=6,
            to=14,
            orient="horizontal",
            variable=self.var_font_size,
            bg="#0f172a",
            fg="#e2e8f0",
            highlightthickness=0,
            troughcolor="#1e293b",
            activebackground="#38bdf8",
            command=lambda e: self.apply_live()
        )
        self.slider_font.pack(fill="x")

        # 3. Metrik yang Ditampilkan
        metric_lbl = tk.Label(body, text="Pilih Metrik", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a")
        metric_lbl.pack(anchor="w", pady=(6, 2))

        self.var_cpu = tk.BooleanVar(value=self.config.get("show_cpu", True))
        self.var_ram = tk.BooleanVar(value=self.config.get("show_ram", True))
        self.var_gpu = tk.BooleanVar(value=self.config.get("show_gpu", True))
        self.var_temp = tk.BooleanVar(value=self.config.get("show_temp", True))
        self.var_net = tk.BooleanVar(value=self.config.get("show_net", False))

        metrics = [
            ("Tampilkan CPU Usage (%)", self.var_cpu),
            ("Tampilkan RAM Usage", self.var_ram),
            ("Tampilkan GPU Usage (%)", self.var_gpu),
            ("Tampilkan Suhu CPU/GPU (°C)", self.var_temp),
            ("Tampilkan Kecepatan Network (↓/↑)", self.var_net),
        ]
        for text, var in metrics:
            cb = tk.Checkbutton(
                body,
                text=text,
                variable=var,
                fg="#e2e8f0",
                bg="#0f172a",
                selectcolor="#1e293b",
                activebackground="#0f172a",
                activeforeground="#38bdf8",
                font=("Segoe UI", 9),
                command=self.apply_live
            )
            cb.pack(anchor="w")

        # 4. Format RAM
        ram_lbl = tk.Label(body, text="Format Tampilan RAM", font=("Segoe UI", 9, "bold"), fg="#38bdf8", bg="#0f172a")
        ram_lbl.pack(anchor="w", pady=(10, 2))

        self.var_ram_format = tk.StringVar(value=self.config.get("ram_format", "used_total"))
        ram_frame = tk.Frame(body, bg="#0f172a")
        ram_frame.pack(fill="x", pady=(0, 10))

        ram_opts = [
            ("Kapasitas Riil (Misal: 9.9GB/16GB)", "used_total"),
            ("Persentase (Misal: 62%)", "percent")
        ]
        for text, val in ram_opts:
            rb = tk.Radiobutton(
                ram_frame,
                text=text,
                variable=self.var_ram_format,
                value=val,
                fg="#e2e8f0",
                bg="#0f172a",
                selectcolor="#1e293b",
                activebackground="#0f172a",
                activeforeground="#38bdf8",
                font=("Segoe UI", 9),
                command=self.apply_live
            )
            rb.pack(anchor="w")

        # Footer Buttons
        footer = tk.Frame(self.root, bg="#1e293b", padx=16, pady=12)
        footer.pack(fill="x", side="bottom")

        btn_save = tk.Button(
            footer,
            text="Simpan & Tutup",
            font=("Segoe UI", 9, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=6,
            command=self.save_and_close
        )
        btn_save.pack(side="right", padx=(8, 0))

        btn_reset = tk.Button(
            footer,
            text="Reset Default",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#e2e8f0",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            command=self.reset_defaults
        )
        btn_reset.pack(side="left")

    def collect_form_data(self):
        return {
            "position": self.var_pos.get(),
            "font_size": self.var_font_size.get(),
            "show_cpu": self.var_cpu.get(),
            "show_ram": self.var_ram.get(),
            "show_gpu": self.var_gpu.get(),
            "show_temp": self.var_temp.get(),
            "show_net": self.var_net.get(),
            "ram_format": self.var_ram_format.get(),
            "x_offset": self.config.get("x_offset", 4),
            "y_offset": self.config.get("y_offset", 18),
            "refresh_rate_ms": self.config.get("refresh_rate_ms", 1000),
            "color_label": self.config.get("color_label", "#7dd3fc"),
            "color_normal": self.config.get("color_normal", "#f0f6fc"),
            "color_warn": self.config.get("color_warn", "#f0883e"),
            "color_crit": self.config.get("color_crit", "#f85149")
        }

    def apply_live(self):
        new_conf = self.collect_form_data()
        self.config.update(new_conf)
        if self.on_config_changed:
            self.on_config_changed(self.config)

    def save_and_close(self):
        new_conf = self.collect_form_data()
        self.config.update(new_conf)
        save_config(self.config)
        if self.on_config_changed:
            self.on_config_changed(self.config)
        self.root.destroy()

    def reset_defaults(self):
        self.config = DEFAULT_CONFIG.copy()
        self.var_pos.set(self.config["position"])
        self.var_font_size.set(self.config["font_size"])
        self.var_cpu.set(self.config["show_cpu"])
        self.var_ram.set(self.config["show_ram"])
        self.var_gpu.set(self.config["show_gpu"])
        self.var_temp.set(self.config["show_temp"])
        self.var_net.set(self.config["show_net"])
        self.var_ram_format.set(self.config["ram_format"])
        self.apply_live()
