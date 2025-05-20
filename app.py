import os
import sys
import json
import time
import re
import ctypes
import warnings
from ctypes import wintypes
from pypresence import Presence

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def exit_err(msg):
    print(f"[CONFIG ERROR] {msg}", file=sys.stderr)
    sys.exit(1)

if not os.path.isfile(CONFIG_PATH):
    exit_err("Cannot find 'config.json'.\nCreate it next to this script. See README or example.")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
except json.JSONDecodeError as e:
    exit_err(f"JSON syntax error: {e}")

schema = {
    "client_id": str,
    "icon_folder": str,
    "custom_icon_key": str,
    "default_icon_key": str,
    "save_crystals_path": str,
    "crystal_offset": int,
    "crystal_size": int,
    "crystal_endian": str,
    "crystal_divisor": int,
    "update_interval": (int, float),
}

for key, expected in schema.items():
    if key not in cfg:
        exit_err(f"Missing '{key}' in config.json.")
    val = cfg[key]
    ok = isinstance(val, expected) if isinstance(expected, type) else isinstance(val, expected)
    if not ok:
        types = expected.__name__ if isinstance(expected, type) else "/".join(t.__name__ for t in expected)
        exit_err(f"Field '{key}' must be of type {types}.")

if cfg["crystal_endian"] not in ("little", "big"):
    exit_err("Field 'crystal_endian' must be either 'little' or 'big'.")

CLIENT_ID          = cfg["client_id"]
ICON_FOLDER        = cfg["icon_folder"]
CUSTOM_ICON_KEY    = cfg["custom_icon_key"]
DEFAULT_ICON_KEY   = cfg["default_icon_key"]
SAVE_CRYSTALS_PATH = cfg["save_crystals_path"]
CRYSTAL_OFFSET     = cfg["crystal_offset"]
CRYSTAL_SIZE       = cfg["crystal_size"]
CRYSTAL_ENDIAN     = cfg["crystal_endian"]
CRYSTAL_DIVISOR    = cfg["crystal_divisor"]
UPDATE_INTERVAL    = cfg["update_interval"]

TITLE_RE = re.compile(r"Death:(\d+)\s+Time:(\d{1,2}):(\d{1,2}):(\d{1,2})")
warnings.filterwarnings("ignore", category=ResourceWarning)

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GetTextLen = user32.GetWindowTextLengthW
GetText = user32.GetWindowTextW

def find_window_title():
    title = None
    def cb(hwnd, _):
        nonlocal title
        length = GetTextLen(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length+1)
        GetText(hwnd, buf, length+1)
        txt = buf.value
        if "I Wanna Kill The Kamilia 3" in txt:
            title = txt
            return False
        return True
    EnumWindows(EnumProc(cb), 0)
    return title

def choose_icon():
    custom_path = os.path.join(ICON_FOLDER, f"{CUSTOM_ICON_KEY}.png")
    return CUSTOM_ICON_KEY if os.path.isfile(custom_path) else DEFAULT_ICON_KEY

def read_crystals():
    try:
        with open(SAVE_CRYSTALS_PATH, "rb") as f:
            f.seek(CRYSTAL_OFFSET)
            raw = f.read(CRYSTAL_SIZE)
    except OSError:
        return None
    if len(raw) != CRYSTAL_SIZE:
        return None
    val = int.from_bytes(raw, byteorder=CRYSTAL_ENDIAN, signed=False)
    return val // CRYSTAL_DIVISOR

def format_hms(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def main():
    rpc = Presence(CLIENT_ID)
    rpc.connect()
    print("Rich Presence started. Waiting for game...")

    found_once = False
    icon_key = choose_icon()
    prev_state = prev_details = prev_small = None

    while True:
        title = find_window_title()
        crystals = read_crystals()

        if title:
            found_once = True
            m = TITLE_RE.search(title)
            if m:
                deaths = int(m.group(1))
                h, mm, ss = map(int, m.group(2, 3, 4))
                total_s = h * 3600 + mm * 60 + ss
                details = f"Deaths: {deaths}\nTime:   {format_hms(total_s)}"
                small = "In Game"
            else:
                details = "In Menu"
                small = "In Menu"
        else:
            if found_once:
                details = "Process not found"
                small = "Not Running"
            else:
                details = "Waiting for process…"
                small = "…"

        state = f"Crystals: {crystals if crystals is not None else '?'}"

        if (state, details, small) != (prev_state, prev_details, prev_small):
            print(f"[UPDATE] {state} | {small}\n{details}\n")
            prev_state, prev_details, prev_small = state, details, small

        rpc.update(
            state=state,
            details=details,
            large_image=icon_key,
            small_text=small
        )

        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting on Ctrl+C")
