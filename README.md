# 📊 PC Health Overlay (HUD)

Lightweight, click-through, always-on-top PC health monitor overlay for Windows.  
Designed with a clean, minimal Steam-like HUD aesthetic that floats transparently at the bottom of the screen without interfering with active applications or mouse clicks.

---

## ✨ Features

- **Floating & Always on Top (`HWND_TOPMOST`):** Stays visible while switching across Chrome, VS Code, Discord, games, and full-screen apps.
- **True Click-Through (`WS_EX_TRANSPARENT`):** Mouse clicks pass directly through to whatever window is underneath.
- **Pure Transparent Text:** Zero background box; rendered using Windows DWM ColorKey layering (`SetLayeredWindowAttributes`).
- **Live Hardware Sensors:**
  - **CPU:** Real-time usage percentage (`psutil`).
  - **RAM:** Dynamic capacity usage (`X.XGB/XXGB` format).
  - **GPU:** Multi-engine 3D & Video utilization via native Windows Performance Data Helper (`pdh.dll`).
  - **Temperature:** Real-time ACPI / Thermal Zone Celsius reading.
- **Adaptive Color States:**
  - Normal: Crisp White / Cyan
  - High Load (>75%): Amber Gold
  - Critical Load (>90%): Crimson Red
- **Zero Overhead:** Direct Win32 C-types & PDH queries (0% CPU impact).
- **Stealth Tool Window:** Hidden from taskbar and `Alt + Tab` switcher (`WS_EX_TOOLWINDOW`).

---

## 🚀 Installation & Running

### Requirements
- Windows 10 or 11
- Python 3.10+
- Dependencies: `psutil`

```bash
pip install psutil
```

### Run
```bash
# Run in background without terminal console window
pythonw overlay.py
```

---

## 🛠️ Windows Auto-Start Setup

To make the overlay start automatically when Windows boots:

1. Create a shortcut to `pythonw.exe C:\Project\pc-health-overlay\overlay.py`.
2. Press `Win + R`, type `shell:startup`, and press **Enter**.
3. Move the shortcut into the Windows **Startup** folder.

Alternatively, register it via Windows Task Scheduler or include it in your logon batch script.

---

## 📜 Architecture & Tech Stack

- **GUI Framework:** Python `tkinter` (Canvas rendering with double buffering).
- **OS Interop:** Windows Win32 API via `ctypes` (`user32.dll`, `pdh.dll`).
- **Styles Applied:** `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_TOPMOST`.
- **Single Instance:** Bound local socket lock on port `49294`.

---

## 📄 License

MIT License © 2026 Muhammad Galih Adi Prayoga (GalihMaximoff)
