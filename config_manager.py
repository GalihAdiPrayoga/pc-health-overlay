import os
import json

DEFAULT_CONFIG = {
    "position": "bottom-left",
    "x_offset": 4,
    "y_offset": 18,
    "font_size": 8,
    "font_family": "Consolas",
    "show_cpu": True,
    "show_ram": True,
    "show_gpu": True,
    "show_temp": True,
    "show_net": False,
    "ram_format": "used_total",  # "used_total" (9.9GB/16GB) or "percent" (62%)
    "refresh_rate_ms": 1000,
    "color_label": "#7dd3fc",
    "color_normal": "#f0f6fc",
    "color_warn": "#f0883e",
    "color_crit": "#f85149"
}

def get_config_path():
    # Prefer local directory, fallback to AppData
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(local_path):
        return local_path
    
    appdata_dir = os.path.expandvars(r"%LOCALAPPDATA%\PCHealthOverlay")
    os.makedirs(appdata_dir, exist_ok=True)
    return os.path.join(appdata_dir, "config.json")

def load_config():
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception as e:
            print(f"Error loading config from {path}: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config to {path}: {e}")
        return False
