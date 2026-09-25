import os
import sys
import time
import socket
import threading
import ctypes
from ctypes import wintypes
import tkinter as tk
import psutil

# Single instance socket lock
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

class MinimalHealthTextOverlay:
    def __init__(self):
        self.lock = acquire_lock()
        self.sensors = HardwareSensors()

        self.root = tk.Tk()
        self.root.title("PCHealthTextOverlay")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        # Pure transparent background (no box, no container)
        self.trans_color = '#010101'
        self.root.config(bg=self.trans_color)
        self.root.wm_attributes('-transparentcolor', self.trans_color)

        # Compact size & Screen Placement (Mentok pojok kiri bawah)
        self.width = 410
        self.height = 18

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.x = 4
        self.y = sh - 18

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

        # Background sampling thread
        self.running = True
        self.worker = threading.Thread(target=self.metrics_loop, daemon=True)
        self.worker.start()

        # Initial UI draw and loop
        self.update_ui()

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

        # Explicitly apply ColorKey transparency to prevent black background
        cr_key = 0x00010101 # RGB(1, 1, 1) in COLORREF format
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, cr_key, 0, LWA_COLORKEY)

        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, self.x, self.y, self.width, self.height, SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def metrics_loop(self):
        while self.running:
            self.sensors.sample()
            time.sleep(1.0)

    def get_color(self, val, warn=75, crit=90):
        if val >= crit:
            return '#f85149' # Red
        elif val >= warn:
            return '#f0883e' # Amber
        return '#f0f6fc'     # Crisp White

    def update_ui(self):
        self.canvas.delete("all")

        c_cpu = self.get_color(self.sensors.cpu_pct, 75, 90)
        c_ram = self.get_color(self.sensors.ram_pct, 80, 92)
        c_gpu = self.get_color(self.sensors.gpu_pct, 80, 95)
        c_temp = self.get_color(self.sensors.temp_c, 68, 82)

        temp_str = f"{self.sensors.temp_c}°C" if self.sensors.temp_c > 0 else "32°C"
        ram_str = f"{self.sensors.ram_used_gb:.1f}GB/{self.sensors.ram_total_gb}GB"

        # Format: CPU 32%  RAM 6.2GB/16GB  GPU 21%  TEMP 30°C
        items = [
            ("CPU", f"{self.sensors.cpu_pct}%", c_cpu),
            ("RAM", ram_str, c_ram),
            ("GPU", f"{self.sensors.gpu_pct}%", c_gpu),
            ("TEMP", temp_str, c_temp)
        ]

        font_label = ('Segoe UI', 8, 'bold')
        font_value = ('Consolas', 8, 'bold')

        cur_x = 2
        cy = self.height // 2

        for idx, (label, val_str, val_color) in enumerate(items):
            # 1. Label with black shadow
            self.canvas.create_text(cur_x + 1, cy + 1, text=label, fill='#000000', font=font_label, anchor='w')
            t_lbl = self.canvas.create_text(cur_x, cy, text=label, fill='#7dd3fc', font=font_label, anchor='w')
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

        self.root.after(1000, self.update_ui)

    def run(self):
        self.root.mainloop()
        self.running = False

if __name__ == "__main__":
    app = MinimalHealthTextOverlay()
    app.run()
