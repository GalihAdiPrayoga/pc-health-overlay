import os
import sys
import time
import socket
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
import psutil
from PIL import Image, ImageDraw
import pystray

from config_manager import load_config, save_config
from settings_dialog import SettingsWindow

LOCK_PORT = 49294

def acquire_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', LOCK_PORT))
        s.listen(1)
        return s
    except socket.error:
        print(f"Overlay already running on port {LOCK_PORT}.")
        sys.exit(0)

# PDH Structures for Windows GPU & Thermal performance counters
class PDH_FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = [
        ('CStatus', wintypes.DWORD),
        ('doubleValue', ctypes.c_double)
    ]

class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = [
        ('szName', wintypes.LPWSTR),
        ('FmtValue', PDH_FMT_COUNTERVALUE)
    ]

class HardwareSensors:
    """Zero-overhead hardware metrics collector using native Windows PDH & psutil."""
    def __init__(self):
        self.pdh = ctypes.windll.pdh
        self.h_query = wintypes.HANDLE()
        self.h_gpu = wintypes.HANDLE()
        self.h_temp = wintypes.HANDLE()
        self.has_pdh = False

        if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.h_query)) == 0:
            gpu_ok = self.pdh.PdhAddCounterW(self.h_query, r'\GPU Engine(*)\Utilization Percentage', 0, ctypes.byref(self.h_gpu)) == 0
            temp_ok = self.pdh.PdhAddCounterW(self.h_query, r'\Thermal Zone Information(*)\Temperature', 0, ctypes.byref(self.h_temp)) == 0
            if gpu_ok or temp_ok:
                self.has_pdh = True
                self.pdh.PdhCollectQueryData(self.h_query)

        # Network baseline
        self.prev_net = psutil.net_io_counters()
        self.prev_time = time.time()

        # Cached metrics
        self.cpu_pct = 0
        self.ram_pct = 0
        self.ram_used_gb = 0.0
        self.ram_total_gb = round(psutil.virtual_memory().total / (1024**3))
        self.gpu_pct = 0
        self.temp_c = 0
        self.net_down = 0.0
        self.net_up = 0.0

    def sample(self):
        # 1. CPU & RAM (psutil)
        self.cpu_pct = round(psutil.cpu_percent(interval=None))
        mem = psutil.virtual_memory()
        self.ram_pct = round(mem.percent)
        self.ram_used_gb = mem.used / (1024**3)

        # 2. Network Speed
        curr_net = psutil.net_io_counters()
        curr_time = time.time()
        dt = max(curr_time - self.prev_time, 0.1)
        self.net_down = (curr_net.bytes_recv - self.prev_net.bytes_recv) / dt
        self.net_up = (curr_net.bytes_sent - self.prev_net.bytes_sent) / dt
        self.prev_net = curr_net
        self.prev_time = curr_time

        # 3. GPU & Temp via PDH
        if self.has_pdh:
            self.pdh.PdhCollectQueryData(self.h_query)
            PDH_FMT_DOUBLE = 0x00000200

            # GPU
            try:
                buf_size = wintypes.DWORD(0)
                item_count = wintypes.DWORD(0)
                self.pdh.PdhGetFormattedCounterArrayW(self.h_gpu, PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), None)
                if buf_size.value > 0:
                    buf = (ctypes.c_byte * buf_size.value)()
                    if self.pdh.PdhGetFormattedCounterArrayW(self.h_gpu, PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), buf) == 0:
                        items = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
                        total_gpu = sum(max(items[i].FmtValue.doubleValue, 0.0) for i in range(item_count.value))
                        self.gpu_pct = min(round(total_gpu), 100)
            except Exception:
                pass

            # Thermal Zone
            try:
                buf_size = wintypes.DWORD(0)
                item_count = wintypes.DWORD(0)
                self.pdh.PdhGetFormattedCounterArrayW(self.h_temp, PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), None)
                if buf_size.value > 0:
                    buf = (ctypes.c_byte * buf_size.value)()
                    if self.pdh.PdhGetFormattedCounterArrayW(self.h_temp, PDH_FMT_DOUBLE, ctypes.byref(buf_size), ctypes.byref(item_count), buf) == 0:
                        items = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
                        temps = []
                        for i in range(item_count.value):
                            k = items[i].FmtValue.doubleValue
                            if k > 200: # Valid Kelvin
                                temps.append(k - 273.15)
                        if temps:
                            self.temp_c = round(max(temps))
            except Exception:
                pass

def format_net_speed(bytes_per_sec):
    if bytes_per_sec >= 1024 * 1024:
        return f"{bytes_per_sec / (1024*1024):.1f}M"
    elif bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.0f}K"
    else:
        return f"{bytes_per_sec:.0f}B"

def create_tray_image():
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(4, 4), (60, 60)], radius=14, fill=(15, 23, 42, 255), outline=(56, 189, 248, 255), width=3)
    points = [(12, 34), (22, 34), (28, 16), (36, 48), (42, 28), (48, 34), (52, 34)]
    draw.line(points, fill=(56, 189, 248, 255), width=4, joint='round')
    return img

class HealthOverlayApp:
    def __init__(self):
        self.lock = acquire_lock()
        self.config = load_config()
        self.sensors = HardwareSensors()

        self.root = tk.Tk()
        self.root.title("PCHealthOverlay")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        # Pure transparent background
        self.trans_color = '#010101'
        self.root.config(bg=self.trans_color)
        self.root.wm_attributes('-transparentcolor', self.trans_color)

        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self.width = 460
        self.height = 20
        self.x = 4
        self.y = self.sh - 18

        self.calculate_geometry()
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.trans_color,
            highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)
        self.root.update()

        # Apply Win32 Click-Through, ToolWindow, Topmost & Layered Colorkey
        self.apply_win32_styles()

        # Settings window reference
        self.settings_win = None

        # Background metrics collector thread
        self.running = True
        self.worker = threading.Thread(target=self.metrics_loop, daemon=True)
        self.worker.start()

        # System Tray icon
        self.tray_icon = None
        self.start_system_tray()

        # GUI Update Loop
        self.update_ui()

    def calculate_geometry(self):
        pos = self.config.get("position", "bottom-left")
        x_off = self.config.get("x_offset", 4)
        y_off = self.config.get("y_offset", 18)
        font_size = self.config.get("font_size", 8)

        self.height = max(font_size + 10, 18)
        self.width = 480

        if pos == "bottom-left":
            self.x = x_off
            self.y = self.sh - y_off
        elif pos == "bottom-right":
            self.x = self.sw - self.width - x_off
            self.y = self.sh - y_off
        elif pos == "top-left":
            self.x = x_off
            self.y = y_off
        elif pos == "top-right":
            self.x = self.sw - self.width - x_off
            self.y = y_off

    def apply_win32_styles(self):
        hwnd = self.root.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_TOPMOST = 0x00000008
        LWA_COLORKEY = 0x00000001

        styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, styles | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)

        cr_key = 0x00010101
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, cr_key, 0, LWA_COLORKEY)

        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, self.x, self.y, self.width, self.height, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def on_config_updated(self, new_config):
        self.config = new_config
        self.calculate_geometry()
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")
        self.canvas.config(width=self.width, height=self.height)
        self.apply_win32_styles()

    def metrics_loop(self):
        while self.running:
            self.sensors.sample()
            time.sleep(1.0)

    def get_color(self, val, warn=75, crit=90):
        if val >= crit:
            return self.config.get("color_crit", "#f85149")
        elif val >= warn:
            return self.config.get("color_warn", "#f0883e")
        return self.config.get("color_normal", "#f0f6fc")

    def update_ui(self):
        self.canvas.delete("all")

        c_cpu = self.get_color(self.sensors.cpu_pct, 75, 90)
        c_ram = self.get_color(self.sensors.ram_pct, 80, 92)
        c_gpu = self.get_color(self.sensors.gpu_pct, 80, 95)
        c_temp = self.get_color(self.sensors.temp_c, 68, 82)

        temp_str = f"{self.sensors.temp_c}°C" if self.sensors.temp_c > 0 else "32°C"
        
        if self.config.get("ram_format") == "percent":
            ram_str = f"{self.sensors.ram_pct}%"
        else:
            ram_str = f"{self.sensors.ram_used_gb:.1f}GB/{self.sensors.ram_total_gb}GB"

        # Build active items list
        items = []
        if self.config.get("show_cpu", True):
            items.append(("CPU", f"{self.sensors.cpu_pct}%", c_cpu))
        if self.config.get("show_ram", True):
            items.append(("RAM", ram_str, c_ram))
        if self.config.get("show_gpu", True):
            items.append(("GPU", f"{self.sensors.gpu_pct}%", c_gpu))
        if self.config.get("show_temp", True):
            items.append(("TEMP", temp_str, c_temp))
        if self.config.get("show_net", False):
            items.append(("NET", f"↓{format_net_speed(self.sensors.net_down)}", "#38bdf8"))

        font_size = self.config.get("font_size", 8)
        font_label = ('Segoe UI', font_size, 'bold')
        font_value = ('Consolas', font_size, 'bold')
        color_label = self.config.get("color_label", "#7dd3fc")

        cur_x = 2
        cy = self.height // 2

        for idx, (label, val_str, val_color) in enumerate(items):
            # 1. Label with black shadow
            self.canvas.create_text(cur_x + 1, cy + 1, text=label, fill='#000000', font=font_label, anchor='w')
            t_lbl = self.canvas.create_text(cur_x, cy, text=label, fill=color_label, font=font_label, anchor='w')
            bbox_lbl = self.canvas.bbox(t_lbl)
            cur_x = bbox_lbl[2] + 3

            # 2. Value with black shadow
            self.canvas.create_text(cur_x + 1, cy + 1, text=val_str, fill='#000000', font=font_value, anchor='w')
            t_val = self.canvas.create_text(cur_x, cy, text=val_str, fill=val_color, font=font_value, anchor='w')
            bbox_val = self.canvas.bbox(t_val)
            cur_x = bbox_val[2] + 8

        # Periodic Topmost re-enforcement
        hwnd = self.root.winfo_id()
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

        refresh_ms = self.config.get("refresh_rate_ms", 1000)
        self.root.after(refresh_ms, self.update_ui)

    def open_settings(self):
        if self.settings_win is None or not tk.Toplevel.winfo_exists(self.settings_win.root):
            self.settings_win = SettingsWindow(on_config_changed=self.on_config_updated)
        else:
            self.settings_win.root.lift()
            self.settings_win.root.focus_force()

    def set_position(self, pos_name):
        self.config["position"] = pos_name
        save_config(self.config)
        self.on_config_updated(self.config)

    def set_ram_format(self, fmt_name):
        self.config["ram_format"] = fmt_name
        save_config(self.config)
        self.on_config_updated(self.config)

    def start_system_tray(self):
        icon_img = create_tray_image()

        def on_open_settings(icon, item):
            self.root.after(0, self.open_settings)

        def on_set_pos(pos):
            def handler(icon, item):
                self.root.after(0, lambda: self.set_position(pos))
            return handler

        def on_set_ram(fmt):
            def handler(icon, item):
                self.root.after(0, lambda: self.set_ram_format(fmt))
            return handler

        def on_exit(icon, item):
            self.running = False
            icon.stop()
            self.root.after(0, self.root.destroy)

        menu = pystray.Menu(
            pystray.MenuItem("⚙️ Konfigurasi / Settings", on_open_settings, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("📍 Posisi Layar", pystray.Menu(
                pystray.MenuItem("Pojok Kiri Bawah", on_set_pos("bottom-left"), checked=lambda item: self.config.get("position") == "bottom-left"),
                pystray.MenuItem("Pojok Kanan Bawah", on_set_pos("bottom-right"), checked=lambda item: self.config.get("position") == "bottom-right"),
                pystray.MenuItem("Pojok Kiri Atas", on_set_pos("top-left"), checked=lambda item: self.config.get("position") == "top-left"),
                pystray.MenuItem("Pojok Kanan Atas", on_set_pos("top-right"), checked=lambda item: self.config.get("position") == "top-right")
            )),
            pystray.MenuItem("📊 Format RAM", pystray.Menu(
                pystray.MenuItem("Kapasitas (GB / Total)", on_set_ram("used_total"), checked=lambda item: self.config.get("ram_format") == "used_total"),
                pystray.MenuItem("Persentase (%)", on_set_ram("percent"), checked=lambda item: self.config.get("ram_format") == "percent")
            )),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Keluar / Exit", on_exit)
        )

        self.tray_icon = pystray.Icon("PCHealthOverlay", icon_img, "PC Health Overlay", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

    def run(self):
        self.root.mainloop()
        self.running = False

if __name__ == "__main__":
    app = HealthOverlayApp()
    app.run()
