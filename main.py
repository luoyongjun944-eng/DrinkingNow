#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DrinkingNow — Windows 健康提醒小工具
定时弹窗提醒喝水和久坐活动，后台静默运行，温柔不打扰。
Apple 毛玻璃视觉风格，克制优雅。
"""

import os
import sys
import json
import time
import queue
import random
import ctypes
import threading
import subprocess
import tkinter as tk
from pathlib import Path

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

from PIL import Image, ImageDraw
import pystray

# Pillow 旧版兼容：极旧版本中 LANCZOS 名为 ANTIALIAS
if not hasattr(Image, 'LANCZOS'):
    Image.LANCZOS = Image.ANTIALIAS

# ═══════════════════════════════════════════════════════════
APP_NAME = "DrinkingNow"
CONFIG_DIR = Path.home() / ".drinkingnow"
CONFIG_FILE = CONFIG_DIR / "settings.json"
ICON_SIZE = 64
ICON_DRAW_SIZE = 256

DEFAULT_SETTINGS = {
    "water_interval": 30,
    "sedentary_interval": 45,
    "sound_enabled": True,
    "autostart": False,
    "first_run": True,
    "theme": "blue",
    "force_water": False,
    "force_sedentary": False,
}

if getattr(sys, 'frozen', False):
    _SCRIPT_DIR = Path(sys._MEIPASS)
elif '__file__' in dir():
    _SCRIPT_DIR = Path(__file__).resolve().parent
else:
    _SCRIPT_DIR = Path(sys.executable).parent
ICO_PATH = str(_SCRIPT_DIR / "waterdrop.ico")

# ═══════════════════════════════════════════════════════════
#  Windows 版本检测（Win7 兼容）
# ═══════════════════════════════════════════════════════════

def _is_legacy_windows():
    """检测是否为 Windows 7 或更早版本。"""
    try:
        ver = sys.getwindowsversion()
        # Win7 = major 6, minor 1; Vista = 6.0; XP = 5.x
        return ver.major < 6 or (ver.major == 6 and ver.minor <= 1)
    except Exception:
        return False

IS_LEGACY_WIN = _is_legacy_windows()


# ═══════════════════════════════════════════════════════════
#  文本 / 图标（Win7 兼容：去掉 emoji 避免方框乱码）
# ═══════════════════════════════════════════════════════════

if IS_LEGACY_WIN:
    # 纯文本版（无 emoji）
    WATER_MESSAGES = [
        "来一杯水",
        "补充能量时刻～",
        "身体在喊渴了",
    ]
    SEDENTARY_MESSAGES = [
        "站一站，走一走",
        "你的腰在感谢你",
        "眼睛也该歇歇了",
        "伸个懒腰吧",
    ]
    POPUP_ICON_WATER = "水"
    POPUP_ICON_SIT   = "坐"
    POPUP_ICON_FONT  = ("Microsoft YaHei UI", 42)
    LABEL_SETTINGS   = "设置"
    LABEL_WATER_INT  = "喝水提醒间隔（分钟）"
    LABEL_SIT_INT    = "久坐提醒间隔（分钟）"
    LABEL_SOUND      = "提示音"
    LABEL_AUTOSTART  = "开机自启"
else:
    # 含 emoji 的原版
    WATER_MESSAGES = [
        "来一杯水 🌊",
        "补充能量时刻～",
        "身体在喊渴了 🗣️",
    ]
    SEDENTARY_MESSAGES = [
        "站一站，走一走 🚶",
        "你的腰在感谢你",
        "眼睛也该歇歇了 👀",
        "伸个懒腰吧 🫴",
    ]
    POPUP_ICON_WATER = "💧"
    POPUP_ICON_SIT   = "🧘"
    POPUP_ICON_FONT  = ("Segoe UI Symbol", 38)
    LABEL_SETTINGS   = "⚙️ 设置"
    LABEL_WATER_INT  = "🥤 喝水提醒间隔（分钟）"
    LABEL_SIT_INT    = "🪑 久坐提醒间隔（分钟）"
    LABEL_SOUND      = "🔔 提示音"
    LABEL_AUTOSTART  = "🚀 开机自启"


WATER_COLOR_NORMAL  = (100, 180, 255)
WATER_COLOR_ALERT   = (60,  160, 255)
WATER_COLOR_PAUSED  = (160, 160, 160)

# ═══════════════════════════════════════════════════════════
#  主题颜色定义（仅影响 UI 控件，不影响托盘图标）
# ═══════════════════════════════════════════════════════════

THEMES = {
    "blue":   {"name": "蓝色",   "accent": "#007AFF", "bg": "#F2F2F7", "label": "蓝"},
    "green":  {"name": "护眼绿", "accent": "#5E9E6D", "bg": "#F1F5F2", "label": "绿"},
    "gray":   {"name": "灰色",   "accent": "#8E8E93", "bg": "#F2F2F7", "label": "灰"},
    "black":  {"name": "深灰",   "accent": "#555B66", "bg": "#F3F4F6", "label": "深"},
    "purple": {"name": "柔紫",   "accent": "#9B8EC4", "bg": "#F5F3F8", "label": "紫"},
    "orange": {"name": "暖橙",   "accent": "#D49068", "bg": "#F3F1EF", "label": "橙"},
}
DEFAULT_THEME = "blue"

THEME_ORDER = ["blue", "green", "gray", "black", "purple", "orange"]


def get_theme_colors(theme_key):
    """返回 (accent, bg) 颜色元组，key 无效时回退到默认主题。"""
    t = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
    return t["accent"], t["bg"]


# ═══════════════════════════════════════════════════════════
#  设置管理器
# ═══════════════════════════════════════════════════════════

class SettingsManager:
    """读写 JSON 配置文件。"""

    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.settings.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DrinkingNow] 保存设置失败: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()


# ═══════════════════════════════════════════════════════════
#  水滴图标绘制器
# ═══════════════════════════════════════════════════════════

class WaterDropIcon:
    """使用 Pillow 在高分辨率画布上绘制水滴，缩放后获得平滑边缘。"""

    @staticmethod
    def create(state='normal', size=ICON_SIZE):
        draw_size = ICON_DRAW_SIZE
        img = Image.new('RGBA', (draw_size, draw_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if state == 'paused':
            color = WATER_COLOR_PAUSED
        elif state == 'alert':
            color = WATER_COLOR_ALERT
        else:
            color = WATER_COLOR_NORMAL

        cx = draw_size / 2
        cy = draw_size / 2

        # 底部球体
        bulb_r = draw_size * 0.185
        bulb_cy = cy + draw_size * 0.12
        draw.ellipse(
            [cx - bulb_r, bulb_cy - bulb_r, cx + bulb_r, bulb_cy + bulb_r],
            fill=color
        )

        # 上方过渡圆
        upper_r = draw_size * 0.12
        upper_cy = cy - draw_size * 0.10
        draw.ellipse(
            [cx - upper_r, upper_cy - upper_r, cx + upper_r, upper_cy + upper_r],
            fill=color
        )

        # 连接矩形
        bridge_w = upper_r
        draw.rectangle(
            [cx - bridge_w, upper_cy, cx + bridge_w, bulb_cy - bulb_r],
            fill=color
        )

        # 顶部尖角
        tip_y = cy - draw_size * 0.42
        draw.polygon([
            (cx - upper_r * 0.65, upper_cy - upper_r * 0.15),
            (cx + upper_r * 0.65, upper_cy - upper_r * 0.15),
            (cx, tip_y),
        ], fill=color)

        return img.resize((size, size), Image.LANCZOS)


# ═══════════════════════════════════════════════════════════
#  提醒弹窗
# ═══════════════════════════════════════════════════════════

class ReminderPopup(tk.Toplevel):
    """从屏幕右下角滑入的毛玻璃提醒弹窗。"""

    def __init__(self, master, reminder_type, message, on_dismiss, on_snooze, theme_color='#007AFF', force=False):
        super().__init__(master)
        self.reminder_type = reminder_type
        self.message = message
        self._on_dismiss_cb = on_dismiss
        self._on_snooze_cb = on_snooze
        self._theme_color = theme_color
        self._force = force
        self._slide_in_id = None
        self._stay_id = None
        self._slide_out_id = None
        self._closed = False

        self.overrideredirect(True)
        self.attributes('-topmost', True)
        try:
            self.attributes('-alpha', 0.93)
        except tk.TclError:
            # Win7 经典主题等环境下窗口透明不可用，回退不透明
            pass

        self.win_w = 370
        self.win_h = 210

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        margin = 20
        self.target_x = screen_w - self.win_w - margin
        self.target_y = screen_h - self.win_h - margin - 40

        self._cur_y = screen_h + 60
        self.geometry(f"{self.win_w}x{self.win_h}+{self.target_x}+{self._cur_y}")

        self._build_ui()
        self._slide_in()

    def _build_ui(self):
        self.canvas = tk.Canvas(
            self, width=self.win_w, height=self.win_h,
            bg='white', highlightthickness=0
        )
        self.canvas.pack(fill='both', expand=True)

        self._round_rect(3, 5, self.win_w - 3, self.win_h - 3, 22, '#C8C8CC')
        self._round_rect(1, 1, self.win_w - 1, self.win_h - 1, 20, '#FFFFFF')

        emoji = POPUP_ICON_WATER if self.reminder_type == 'water' else POPUP_ICON_SIT

        self.canvas.create_text(
            self.win_w // 2, 48, text=emoji,
            font=POPUP_ICON_FONT, anchor='center'
        )
        self.canvas.create_text(
            self.win_w // 2, 108, text=self.message,
            font=('Microsoft YaHei UI', 15, 'bold'),
            fill='#1C1C1E', anchor='center'
        )

        btn_y = 165
        self._btn(self.win_w // 2 - 130, btn_y, 115, 34, "知道了", self._theme_color, self._on_dismiss)
        self._btn(self.win_w // 2 + 15,  btn_y, 115, 34, "再提醒我", '#8E8E93', self._on_snooze)

    def _round_rect(self, x1, y1, x2, y2, r, fill):
        pts = [
            x1 + r, y1,  x2 - r, y1,  x2, y1,  x2, y1 + r,
            x2, y2 - r,  x2, y2,  x2 - r, y2,  x1 + r, y2,
            x1, y2,  x1, y2 - r,  x1, y1 + r,  x1, y1,
        ]
        return self.canvas.create_polygon(pts, fill=fill, smooth=True, outline='')

    def _btn(self, x, y, w, h, text, color, cb):
        rid = self._round_rect(x, y, x + w, y + h, 17, color)
        tid = self.canvas.create_text(
            x + w // 2, y + h // 2, text=text,
            font=('Microsoft YaHei UI', 11), fill='white', anchor='center'
        )
        for tag in (rid, tid):
            self.canvas.tag_bind(tag, '<Button-1>', lambda e, c=cb: c())
            self.canvas.tag_bind(tag, '<Enter>', lambda e: self.canvas.config(cursor='hand2'))
            self.canvas.tag_bind(tag, '<Leave>', lambda e: self.canvas.config(cursor=''))

    def _slide_in(self):
        target = self.target_y
        if self._cur_y > target:
            self._cur_y -= max(1, int((self._cur_y - target) * 0.28))
            self.geometry(f"{self.win_w}x{self.win_h}+{self.target_x}+{self._cur_y}")
            self._slide_in_id = self.after(8, self._slide_in)
        else:
            self._cur_y = target
            self.geometry(f"{self.win_w}x{self.win_h}+{self.target_x}+{self._cur_y}")
            if not self._force:
                self._stay_id = self.after(8000, self._slide_out)

    def _slide_out(self):
        screen_h = self.winfo_screenheight()
        target = screen_h + 60
        if self._cur_y < target:
            self._cur_y += max(1, int((target - self._cur_y) * 0.28))
            self.geometry(f"{self.win_w}x{self.win_h}+{self.target_x}+{self._cur_y}")
            self._slide_out_id = self.after(8, self._slide_out)
        else:
            self._destroy()

    def dismiss(self):
        for tid in (self._stay_id, self._slide_in_id, self._slide_out_id):
            if tid:
                try:
                    self.after_cancel(tid)
                except Exception:
                    pass
        self._stay_id = self._slide_in_id = self._slide_out_id = None
        self._slide_out()

    def _on_dismiss(self):
        self.dismiss()
        if self._on_dismiss_cb:
            self._on_dismiss_cb()

    def _on_snooze(self):
        self.dismiss()
        if self._on_snooze_cb:
            self._on_snooze_cb()

    def _destroy(self):
        if not self._closed:
            self._closed = True
            try:
                self.destroy()
            except Exception:
                pass

    @property
    def closed(self):
        return self._closed


# ═══════════════════════════════════════════════════════════
#  设置面板
# ═══════════════════════════════════════════════════════════

class SettingsPanel(tk.Toplevel):
    """毛玻璃风格设置面板。"""

    def __init__(self, master, settings_manager, on_save_cb):
        super().__init__(master)
        self._sm = settings_manager
        self._on_save_cb = on_save_cb

        theme_key = self._sm.get('theme', DEFAULT_THEME)
        self._theme_accent, self._theme_bg = get_theme_colors(theme_key)
        self._current_theme = theme_key

        self.title(f"{APP_NAME} 设置")
        self.resizable(False, False)

        w, h = 390, 530
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")
        self.configure(bg=self._theme_bg)
        try:
            self.attributes('-alpha', 0.96)
        except tk.TclError:
            pass

        if os.path.exists(ICO_PATH):
            self.iconbitmap(ICO_PATH)

        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _build_ui(self):
        bg = self._theme_bg

        hdr = tk.Frame(self, bg=bg)
        hdr.pack(fill='x', padx=24, pady=(24, 8))
        tk.Label(hdr, text=LABEL_SETTINGS, font=('Microsoft YaHei UI', 18, 'bold'),
                 fg='#1C1C1E', bg=bg).pack(side='left')

        sep = tk.Frame(self, bg='#C6C6C8', height=1)
        sep.pack(fill='x', padx=24)

        body = tk.Frame(self, bg=bg)
        body.pack(fill='both', expand=True, padx=24, pady=18)

        self._sv_water = tk.StringVar(value=str(self._sm.get('water_interval', 30)))
        self._row(body, 0, LABEL_WATER_INT, self._sv_water)

        self._sv_sit = tk.StringVar(value=str(self._sm.get('sedentary_interval', 45)))
        self._row(body, 1, LABEL_SIT_INT, self._sv_sit)

        self._sv_sound = tk.BooleanVar(value=self._sm.get('sound_enabled', True))
        self._toggle_row(body, 2, LABEL_SOUND, self._sv_sound)

        self._sv_force_w = tk.BooleanVar(value=self._sm.get('force_water', False))
        self._toggle_row(body, 3, "🥤 喝水强制提醒", self._sv_force_w,
                         hint="开启后喝水弹窗不会自动消失，需手动点击关闭")

        self._sv_force_s = tk.BooleanVar(value=self._sm.get('force_sedentary', False))
        self._toggle_row(body, 4, "🪑 久坐强制提醒", self._sv_force_s,
                         hint="开启后久坐弹窗不会自动消失，需手动点击关闭")

        self._sv_auto = tk.BooleanVar(value=self._sm.get('autostart', False))
        self._toggle_row(body, 5, LABEL_AUTOSTART, self._sv_auto)

        # ── 主题颜色选择器 ──
        self._sv_theme = tk.StringVar(value=self._current_theme)
        self._theme_frm = tk.Frame(body, bg=bg)
        self._theme_frm.grid(row=6, column=0, sticky='ew', pady=12)
        tk.Label(self._theme_frm, text='主题颜色', font=('Microsoft YaHei UI', 12),
                 fg='#1C1C1E', bg=bg).pack(side='left')
        self._theme_canvas = tk.Canvas(
            self._theme_frm, width=264, height=36, bg=bg, highlightthickness=0
        )
        self._theme_canvas.pack(side='right')
        self._draw_theme_swatches()

        bf = tk.Frame(self, bg=bg)
        bf.pack(fill='x', padx=24, pady=(0, 24))
        self._pill_btn(bf, '保存', self._theme_accent, self._save)

    def _row(self, parent, row, label, sv):
        bg = self._theme_bg
        f = tk.Frame(parent, bg=bg)
        f.grid(row=row, column=0, sticky='ew', pady=8)
        tk.Label(f, text=label, font=('Microsoft YaHei UI', 12),
                 fg='#1C1C1E', bg=bg).pack(side='left')
        e = tk.Entry(f, textvariable=sv, width=6, font=('Microsoft YaHei UI', 12),
                     justify='center', relief='solid', borderwidth=1)
        e.pack(side='right')
        vcmd = (self.register(lambda P: P == '' or P.isdigit()), '%P')
        e.config(validate='key', validatecommand=vcmd)

    def _toggle_row(self, parent, row, label, bv, hint=None):
        bg = self._theme_bg
        f = tk.Frame(parent, bg=bg)
        f.grid(row=row, column=0, sticky='ew', pady=10)
        lbl_frm = tk.Frame(f, bg=bg)
        lbl_frm.pack(side='left')
        tk.Label(lbl_frm, text=label, font=('Microsoft YaHei UI', 12),
                 fg='#1C1C1E', bg=bg).pack(side='left')
        if hint:
            info = tk.Label(lbl_frm, text=" ⓘ", font=('Microsoft YaHei UI', 10),
                           fg='#8E8E93', bg=bg, cursor='hand2')
            info.pack(side='left')
            self._bind_tooltip(info, hint)
        tk.Checkbutton(f, variable=bv, bg=bg,
                       activebackground=bg).pack(side='right')

    def _bind_tooltip(self, widget, text):
        """鼠标悬停时显示圆润气泡提示，离开时消失。"""
        tip = None

        def show(_):
            nonlocal tip
            if tip is not None:
                return
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.attributes('-topmost', True)
            try:
                tip.attributes('-alpha', 0.95)
            except tk.TclError:
                pass

            bg = '#8E8E93'  # 浅灰，白字可读
            tw = 230
            r = 14  # 圆角半径

            # 量文字高度
            tmp = tk.Label(tip, text=text, font=('Microsoft YaHei UI', 10),
                           wraplength=tw - 28)
            req_h = tmp.winfo_reqheight()
            tmp.destroy()
            th = req_h + 24

            c = tk.Canvas(tip, width=tw, height=th,
                          bg=self._theme_bg, highlightthickness=0)
            c.pack()

            # 圆角矩形
            pts = [r, 0, tw - r - 1, 0, tw - 1, 0, tw - 1, r,
                   tw - 1, th - r - 1, tw - 1, th - 1, tw - r - 1, th - 1,
                   r, th - 1, 0, th - 1, 0, th - r - 1,
                   0, r, 0, 0, r, 0]
            c.create_polygon(pts, fill=bg, smooth=True, outline='')

            # 白字
            c.create_text(tw // 2, th // 2, text=text, anchor='center',
                          font=('Microsoft YaHei UI', 10),
                          fill='white', width=tw - 28)

            # 定位
            wx = widget.winfo_rootx()
            wy = widget.winfo_rooty() + widget.winfo_height() + 6
            screen_w = widget.winfo_screenwidth()
            if wx + tw > screen_w - 12:
                wx = screen_w - tw - 12
            tip.geometry(f'{tw}x{th}+{wx}+{wy}')

        def hide(_):
            nonlocal tip
            if tip is not None:
                tip.destroy()
                tip = None

        widget.bind('<Enter>', show, add='+')
        widget.bind('<Leave>', hide, add='+')

    def _pill_btn(self, parent, text, color, cb):
        c = tk.Canvas(parent, width=342, height=44, bg=self._theme_bg, highlightthickness=0)
        c.pack()
        w, h = 342, 44
        r = h // 2  # 22
        # 左半圆 + 中间矩形 + 右半圆（完美抗锯齿圆角）
        c.create_oval(0, 0, 2 * r, h, fill=color, outline='')
        c.create_oval(w - 2 * r, 0, w, h, fill=color, outline='')
        c.create_rectangle(r, 0, w - r, h, fill=color, outline='')
        c.create_text(w // 2, h // 2, text=text,
                      font=('Microsoft YaHei UI', 13, 'bold'),
                      fill='white', anchor='center')
        c.bind('<Button-1>', lambda e: cb())
        c.bind('<Enter>', lambda e: c.config(cursor='hand2'))
        c.bind('<Leave>', lambda e: c.config(cursor=''))

    def _draw_theme_swatches(self):
        """绘制 6 个主题色圆点。"""
        self._theme_canvas.delete('all')
        c = self._theme_canvas
        r = 10  # 圆点半径
        gap = 34  # 圆点间距
        start_x = 16  # 左侧留出选中环的空间 (r + 3 + 余量)

        # 调整 canvas 宽度以容纳 6 个点 + 右侧留白
        c.config(width=gap * 6 + start_x + 12)

        for i, key in enumerate(THEME_ORDER):
            cx = start_x + i * gap
            cy = 16
            t = THEMES[key]
            fill = t["accent"]

            # 外圈（选中时高亮）
            if key == self._sv_theme.get():
                c.create_oval(cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
                              outline=fill, width=2)

            # 色点
            dot = c.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=fill, outline='')
            c.tag_bind(dot, '<Button-1>', lambda e, k=key: self._on_theme_select(k))
            c.tag_bind(dot, '<Enter>', lambda e: c.config(cursor='hand2'))
            c.tag_bind(dot, '<Leave>', lambda e: c.config(cursor=''))

    def _on_theme_select(self, key):
        """点击色点切换主题，实时预览。"""
        self._sv_theme.set(key)
        self._current_theme = key
        self._theme_accent, self._theme_bg = get_theme_colors(key)
        self._apply_theme()

    def _apply_theme(self):
        """保存表单值 → 重建 UI → 恢复表单值，实现无丢失颜色切换。"""
        # 保存当前表单编辑中的值
        saved_water = self._sv_water.get()
        saved_sit = self._sv_sit.get()
        saved_sound = self._sv_sound.get()
        saved_force_w = self._sv_force_w.get()
        saved_force_s = self._sv_force_s.get()
        saved_auto = self._sv_auto.get()

        # 重建所有子控件
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()

        # 恢复表单值
        self._sv_water.set(saved_water)
        self._sv_sit.set(saved_sit)
        self._sv_sound.set(saved_sound)
        self._sv_force_w.set(saved_force_w)
        self._sv_force_s.set(saved_force_s)
        self._sv_auto.set(saved_auto)

    def _save(self):
        try:
            wi = int(self._sv_water.get())
            si = int(self._sv_sit.get())
            clamped = wi < 5 or si < 5
            if wi < 5:
                wi = 5
            if si < 5:
                si = 5
        except ValueError:
            return

        self._sm.set('water_interval', wi)
        self._sm.set('sedentary_interval', si)
        self._sm.set('sound_enabled', self._sv_sound.get())
        self._sm.set('force_water', self._sv_force_w.get())
        self._sm.set('force_sedentary', self._sv_force_s.get())
        self._sm.set('autostart', self._sv_auto.get())
        self._sm.set('theme', self._sv_theme.get())
        self._sm.set('first_run', False)

        self._toggle_autostart(self._sv_auto.get())

        if self._on_save_cb:
            self._on_save_cb()

        if clamped:
            # 自动更新输入框数字为 5
            if self._sv_water.get() != str(wi):
                self._sv_water.set(str(wi))
            if self._sv_sit.get() != str(si):
                self._sv_sit.set(str(si))
            self._show_min_hint()
        # 保存后页面不自动关闭，由用户手动关

    def _show_min_hint(self):
        """显示间隔最低 5 分钟的提示，2 秒后淡出消失，页面不关。"""
        w, h = 340, 42
        c = tk.Canvas(self, width=w, height=h,
                      bg=self._theme_bg, highlightthickness=0)
        c.place(relx=0.5, rely=0.88, anchor='center')
        self._hint_canvas = c

        # 圆角背景
        r = 21
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h,
               w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        c.create_polygon(pts, fill='#FFF9C4', smooth=True, outline='#FFD54F', width=1)
        c.create_text(w // 2, h // 2, text="⏱ 间隔最少为 5 分钟，已自动调整",
                      font=('Microsoft YaHei UI', 11),
                      fill='#F57F17', anchor='center')

        # 2 秒后淡出 hint，页面不动
        self.after(2000, self._dismiss_hint)

    def _dismiss_hint(self):
        if hasattr(self, '_hint_canvas'):
            self._hint_canvas.destroy()
            del self._hint_canvas

    def _toggle_autostart(self, enable):
        startup = Path(os.environ.get('APPDATA', '')) / \
                  r'Microsoft\Windows\Start Menu\Programs\Startup'
        lnk = startup / f'{APP_NAME}.lnk'

        try:
            if enable:
                if getattr(sys, 'frozen', False):
                    target = sys.executable
                    args = ''
                    wdir = os.path.dirname(sys.executable)
                else:
                    target = sys.executable.replace('python.exe', 'pythonw.exe')
                    args = f'"{os.path.abspath(__file__)}"'
                    wdir = os.path.dirname(os.path.abspath(__file__))

                ps = (
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
                    f"$s.TargetPath='{target}';"
                    f"$s.Arguments='{args}';"
                    f"$s.WorkingDirectory='{wdir}';"
                    f"$s.WindowStyle=7;"
                    f"$s.Save()"
                )
                subprocess.run(
                    ['powershell', '-NoProfile', '-Command', ps],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
            else:
                if lnk.exists():
                    lnk.unlink()
        except Exception as e:
            print(f"[DrinkingNow] 开机自启设置失败: {e}")

    def _close(self):
        self.destroy()

    def _fade_out_and_close(self):
        """保存后淡出动画，约 250ms 后关闭。"""
        try:
            current = self.attributes('-alpha')
        except tk.TclError:
            self._close()
            return
        if current <= 0.04:
            self._close()
            return
        new_alpha = max(0.0, current - 0.1)
        self.attributes('-alpha', new_alpha)
        self.after(20, self._fade_out_and_close)


# ═══════════════════════════════════════════════════════════
#  托盘图标（继承 pystray，覆盖左键行为）
# ═══════════════════════════════════════════════════════════

class TrayIcon(pystray.Icon):
    """pystray.Icon 子类，左键点击时触发自定义回调。"""

    def __init__(self, name, icon, title, menu, on_left_click=None):
        super().__init__(name, icon=icon, title=title, menu=menu)
        self._on_left_click = on_left_click

    def __call__(self):
        """pystray 在左键点击托盘图标时自动调用此方法。"""
        if self._on_left_click:
            self._on_left_click()


# ═══════════════════════════════════════════════════════════
#  主应用程序
# ═══════════════════════════════════════════════════════════

class DrinkingNowApp:
    """主控制器。"""

    def __init__(self):
        self.settings = SettingsManager()
        self._event_q = queue.Queue()
        self._popup = None
        self._settings_win = None

        self._running = True
        self._paused = False
        self._pause_until = 0.0
        self._alerting = False

        self._water_elapsed = 0
        self._sit_elapsed = 0
        self._water_sec = self.settings.get('water_interval', 30) * 60
        self._sit_sec   = self.settings.get('sedentary_interval', 45) * 60

        self._tray = None
        self._icon_state = 'normal'

        self._root = tk.Tk()
        self._root.withdraw()
        self._root.protocol('WM_DELETE_WINDOW', lambda: None)

        # 任务栏图标：设为水滴（所有子窗口继承）
        if os.path.exists(ICO_PATH):
            self._root.iconbitmap(default=ICO_PATH)

        self._init_tray()
        self._start_timers()
        self._poll_events()

        if self.settings.get('first_run', True):
            self._root.after(500, self.show_settings)

    # ── 托盘 ──────────────────────────────────────────────

    def _init_tray(self):
        img = WaterDropIcon.create('normal')
        menu = self._build_menu()
        self._tray = TrayIcon(APP_NAME, img, APP_NAME, menu,
                              on_left_click=self._on_tray_left_click)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _build_menu(self):
        items = []

        if self._paused:
            remaining = ''
            if self._pause_until != float('inf'):
                left = max(0, int(self._pause_until - time.time()))
                if left >= 3600:
                    remaining = f'（剩余 {left // 3600} 小时 {(left % 3600) // 60} 分钟）'
                elif left >= 60:
                    remaining = f'（剩余 {left // 60} 分钟）'
                else:
                    remaining = f'（剩余 {left} 秒）'
            else:
                remaining = '（手动恢复）'

            items.append(pystray.MenuItem(
                f'当前已暂停 {remaining}',
                None, enabled=False
            ))
            items.append(pystray.MenuItem('恢复提醒', self._menu_resume))
        else:
            items.append(pystray.MenuItem('暂停提醒', pystray.Menu(
                pystray.MenuItem('暂停 1 小时',  lambda: self._menu_pause(3600)),
                pystray.MenuItem('暂停 2 小时',  lambda: self._menu_pause(7200)),
                pystray.MenuItem('直到手动恢复', lambda: self._menu_pause(float('inf'))),
            )))

        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出', self._menu_exit),
        ]
        return pystray.Menu(*items)

    def _refresh_menu(self):
        try:
            self._tray.update_menu()
        except Exception:
            pass

    def _update_icon(self):
        if not self._tray:
            return
        if self._paused:
            s = 'paused'
        elif self._alerting:
            s = 'alert'
        else:
            s = 'normal'
        if s != self._icon_state:
            self._icon_state = s
            self._tray.icon = WaterDropIcon.create(state=s)

    # ── 菜单回调 ───────────────────────────────────────────

    def _menu_settings(self, icon=None, item=None):
        self._event_q.put(('show_settings',))

    def _menu_pause(self, seconds):
        self._paused = True
        self._pause_until = time.time() + seconds if seconds != float('inf') else float('inf')
        self._update_icon()
        self._tray.menu = self._build_menu()
        self._refresh_menu()

    def _menu_resume(self, icon=None, item=None):
        self._paused = False
        self._pause_until = 0.0
        self._update_icon()
        self._tray.menu = self._build_menu()
        self._refresh_menu()

    def _menu_exit(self, icon=None, item=None):
        self._running = False
        if self._tray:
            self._tray.stop()
        try:
            self._root.after(0, self._shutdown)
        except Exception:
            pass

    # ── 托盘左键 ──────────────────────────────────────────

    def _on_tray_left_click(self):
        """左键点击托盘图标 → 打开设置。"""
        self._event_q.put(('show_settings',))

    # ── 计时器 ─────────────────────────────────────────────

    def _start_timers(self):
        threading.Thread(target=self._water_timer, daemon=True).start()
        threading.Thread(target=self._sit_timer, daemon=True).start()

    def _tick(self, elapsed_attr, interval_attr, event_name):
        while self._running:
            time.sleep(1)
            if not self._running:
                break
            if self._paused:
                continue

            val = getattr(self, elapsed_attr) + 1
            setattr(self, elapsed_attr, val)

            if val >= getattr(self, interval_attr):
                setattr(self, elapsed_attr, 0)
                self._event_q.put((event_name,))

    def _water_timer(self):
        self._tick('_water_elapsed', '_water_sec', 'water')

    def _sit_timer(self):
        self._tick('_sit_elapsed', '_sit_sec', 'sedentary')

    # ── 事件轮询 ──────────────────────────────────────────

    def _poll_events(self):
        try:
            if self._paused and self._pause_until != float('inf'):
                if time.time() >= self._pause_until:
                    # 暂停时间到，自动恢复
                    self._paused = False
                    self._pause_until = 0.0
                    self._update_icon()
                    self._tray.menu = self._build_menu()
                    self._refresh_menu()
                else:
                    # 每 2 秒刷新菜单，让倒计时实时更新
                    if int(time.time()) % 2 == 0:
                        self._tray.menu = self._build_menu()
                        self._refresh_menu()

            while True:
                try:
                    ev = self._event_q.get_nowait()
                except queue.Empty:
                    break
                self._dispatch(ev)

        except Exception as e:
            print(f"[DrinkingNow] 事件循环异常: {e}")

        if self._running:
            self._root.after(500, self._poll_events)

    def _dispatch(self, ev):
        kind = ev[0]

        if kind == 'water':
            self._show_reminder('water')
        elif kind == 'sedentary':
            self._show_reminder('sedentary')
        elif kind == 'show_settings':
            self.show_settings()
        elif kind == 'refresh_settings':
            self._apply_settings()
        elif kind == 'snooze':
            self._handle_snooze(ev[1])

    # ── 弹窗 ──────────────────────────────────────────────

    def _show_reminder(self, rtype):
        if self._popup is not None:
            # 新提醒替换旧弹窗
            try:
                self._popup.dismiss()
            except Exception:
                pass
            self._popup = None
            self._alerting = False
            self._pending_reminder = None

        msg = random.choice(WATER_MESSAGES if rtype == 'water' else SEDENTARY_MESSAGES)
        self._play_sound()

        self._alerting = True
        self._update_icon()

        def on_dismiss():
            self._alerting = False
            self._update_icon()
            self._flush_pending()

        def on_snooze():
            self._alerting = False
            self._update_icon()
            self._event_q.put(('snooze', rtype))
            self._flush_pending()

        theme_key = self.settings.get('theme', DEFAULT_THEME)
        theme_accent, _ = get_theme_colors(theme_key)
        force = self.settings.get('force_water' if rtype == 'water' else 'force_sedentary', False)
        self._popup = ReminderPopup(self._root, rtype, msg, on_dismiss, on_snooze, theme_color=theme_accent, force=force)
        self._watch_popup()

    def _watch_popup(self):
        if self._popup is not None:
            try:
                if self._popup.closed or not self._popup.winfo_exists():
                    self._popup = None
                else:
                    self._root.after(200, self._watch_popup)
            except Exception:
                self._popup = None

    def _flush_pending(self):
        """弹窗关闭后，5 秒后弹出排队的提醒。"""
        if self._pending_reminder:
            pending = self._pending_reminder
            self._pending_reminder = None

            def delayed():
                time.sleep(5)
                if self._running:
                    self._event_q.put((pending,))

            threading.Thread(target=delayed, daemon=True).start()

    def _handle_snooze(self, rtype):
        def delayed():
            time.sleep(300)
            if self._running:
                self._event_q.put((rtype,))
        threading.Thread(target=delayed, daemon=True).start()

    # ── 提示音 ────────────────────────────────────────────

    def _play_sound(self):
        if not self.settings.get('sound_enabled', True):
            return
        try:
            if HAS_WINSOUND:
                winsound.PlaySound(
                    'SystemAsterisk',
                    winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT
                )
        except Exception:
            pass

    # ── 设置 ──────────────────────────────────────────────

    def show_settings(self):
        if self._settings_win is not None:
            try:
                self._settings_win.lift()
                self._settings_win.focus_force()
            except Exception:
                self._settings_win = None
            return

        self._settings_win = SettingsPanel(
            self._root, self.settings,
            on_save_cb=self._on_settings_saved
        )
        self._settings_win.protocol('WM_DELETE_WINDOW', self._on_settings_closed)
        self._watch_settings()

    def _watch_settings(self):
        if self._settings_win is not None:
            try:
                if not self._settings_win.winfo_exists():
                    self._settings_win = None
                else:
                    self._root.after(300, self._watch_settings)
            except Exception:
                self._settings_win = None

    def _on_settings_saved(self):
        self._event_q.put(('refresh_settings',))

    def _on_settings_closed(self):
        if self._settings_win:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
        self._settings_win = None

    def _apply_settings(self):
        self._water_sec = self.settings.get('water_interval', 30) * 60
        self._sit_sec   = self.settings.get('sedentary_interval', 45) * 60
        self._water_elapsed = 0
        self._sit_elapsed = 0

    # ── 退出 ──────────────────────────────────────────────

    def _shutdown(self):
        self._running = False

        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

        if self._settings_win:
            try:
                self._settings_win.destroy()
            except Exception:
                pass
            self._settings_win = None

        try:
            self._root.quit()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════
def main():
    # 单实例锁：重复启动时静默退出，确保托盘只有一个图标
    mutex_name = 'DrinkingNow_SingleInstance_Mutex'
    ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return

    app = DrinkingNowApp()
    app._root.mainloop()


if __name__ == '__main__':
    main()
