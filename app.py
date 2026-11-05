"""Hazmob Snap: experimental local head-keypoint detection and snap aiming."""
import os
import sys
import time
import math
import queue
import threading
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from targeting import Detection, head_point, choose_head, movement, may_move

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('HAZMOB_HOME', str(BASE))).resolve()
os.environ.setdefault('YOLO_CONFIG_DIR', str(DATA / '.model-settings'))

if sys.platform != 'win32':
    raise SystemExit('This application requires Windows.')
u32 = ctypes.WinDLL('user32', use_last_error=True)
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
try:
    u32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    u32.SetProcessDPIAware()

class MonitorInfo(ctypes.Structure):
    _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT), ('flags', W.DWORD)]
class MouseInput(ctypes.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]
class InputUnion(ctypes.Union):
    _fields_ = [('mouse', MouseInput)]
class Input(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', W.DWORD), ('data', InputUnion)]
u32.GetForegroundWindow.restype = W.HWND
u32.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
u32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
u32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
u32.MonitorFromWindow.restype = W.HANDLE
u32.GetMonitorInfoW.argtypes = [W.HANDLE, ctypes.POINTER(MonitorInfo)]
u32.SendInput.argtypes = [W.UINT, ctypes.POINTER(Input), ctypes.c_int]
u32.SendInput.restype = W.UINT
u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
u32.GetAsyncKeyState.restype = ctypes.c_short
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenProcess.restype = W.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
k32.CloseHandle.argtypes = [W.HANDLE]


def key_down(code):
    return bool(u32.GetAsyncKeyState(code) & 0x8000)


def game_window():
    hwnd = u32.GetForegroundWindow()
    if not hwnd:
        return None
    title = ctypes.create_unicode_buffer(1024)
    u32.GetWindowTextW(hwnd, title, len(title))
    if 'hazmob' not in title.value.lower():
        return None
    pid = W.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = k32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = W.DWORD(len(path))
        if not k32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return None
        if Path(path.value).name.lower() != 'chrome.exe':
            return None
    finally:
        k32.CloseHandle(handle)
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    if not u32.GetMonitorInfoW(u32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
        return None
    return hwnd, info.monitor


def send_move(dx, dy):
    if not dx and not dy:
        return
    event = Input(type=0, mouse=MouseInput(dx, dy, 0, 0x0001, 0, 0))
    if u32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise OSError('Windows did not accept mouse movement. Assistance was paused.')


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Hazmob Snap / Experimental')
        self.root.geometry('960x730')
        self.root.minsize(820, 710)
        self.root.configure(bg='#10131c')
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.config = dict(armed=False, assist=True, require_rmb=False, confidence=.60, radius=200,
                           gain=1.0, head_confidence=.60, compensation=0)
        self.updates = queue.Queue(maxsize=2)
        self.worker_started = False
        self.ready = False
        self.previous_keys = {0x77: False, 0x78: False}
        self.preview_image = None
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#10131c')
        style.configure('TLabel', background='#10131c', foreground='#e9edfa', font=('Segoe UI', 10))
        style.configure('TCheckbutton', background='#10131c', foreground='#e9edfa', font=('Segoe UI', 10))
        style.map('TCheckbutton', background=[('active', '#202637')])
        style.configure('TScale', background='#10131c', troughcolor='#252c40')
        style.configure('TButton', background='#8974ed', foreground='#ffffff', padding=10, font=('Segoe UI Semibold', 10))
        style.map('TButton', background=[('active', '#a18dff')])
        outer = ttk.Frame(self.root, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='HAZMOB / SNAP', font=('Segoe UI Semibold', 22)).pack(anchor='w')
        ttk.Label(outer, text='Head-keypoint snap targeting  /  Windows + Chrome  /  Experimental', foreground='#99a7c3').pack(anchor='w', pady=(3, 18))
        content = ttk.Frame(outer)
        content.pack(fill='both', expand=True)
        controls = ttk.Frame(content, width=300)
        controls.pack(side='left', fill='y', padx=(0, 24))
        self.start_button = ttk.Button(controls, text='Load detector', command=self.start_worker)
        self.start_button.pack(fill='x', pady=(0, 12))
        self.arm_button = ttk.Button(controls, text='Paused / F8 to start', command=self.toggle)
        self.arm_button.pack(fill='x', pady=(0, 14))
        self.assist_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='Snap aiming enabled', variable=self.assist_var,
                        command=lambda: self.set_config('assist', self.assist_var.get())).pack(anchor='w', pady=(0, 15))
        self.hold_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text='Require RMB (optional)', variable=self.hold_var,
                        command=lambda: self.set_config('require_rmb', self.hold_var.get())).pack(anchor='w', pady=(0, 10))
        self.slider(controls, 'Detection confidence', 'confidence', .25, .90, .60, 2)
        self.slider(controls, 'Target radius / screen pixels', 'radius', 40, 300, 200, 0)
        self.slider(controls, 'Snap sensitivity / mouse calibration', 'gain', .10, 3.0, 1.0, 2)
        self.slider(controls, 'Head keypoint confidence', 'head_confidence', .35, .90, .60, 2)
        self.slider(controls, 'Downward compensation / pixels per second', 'compensation', 0, 120, 0, 0)
        ttk.Label(controls, text='F8  Pause / resume\nF9  Emergency exit\nF8 starts automatic snapping\nOptional RMB requirement available', foreground='#b9c4dc', justify='left').pack(anchor='w', pady=12)
        right = ttk.Frame(content)
        right.pack(side='left', fill='both', expand=True)
        self.preview = tk.Canvas(right, width=480, height=480, bg='#191e2b', highlightthickness=1, highlightbackground='#30384b')
        self.preview.pack(fill='both', expand=True)
        self.preview.create_text(240, 220, text='DETECTION PREVIEW\n\nLoad the detector, open Hazmob full-screen,\nthen press F8. Snap aiming is ON; F8 arms it.', fill='#99a7c3', font=('Segoe UI', 12), justify='center')
        self.status = tk.StringVar(value='Ready to load. First load downloads a general pose-estimation model.')
        ttk.Label(outer, textvariable=self.status, wraplength=900, foreground='#bdaeff').pack(anchor='w', pady=(16, 6))
        ttk.Label(outer, text='Not trained for Hazmob. Cannot distinguish teammates or see through walls. Head keypoints must be detected; no body-box fallback.',
                  foreground='#99a7c3', wraplength=900).pack(anchor='w')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(30, self.poll)

    def set_config(self, key, value):
        with self.lock:
            self.config[key] = value

    def slider(self, parent, title, key, low, high, value, digits):
        value_label = ttk.Label(parent, text=f'{title}: {value:.{digits}f}', font=('Segoe UI', 9))
        value_label.pack(anchor='w')
        var = tk.DoubleVar(value=value)
        def changed(raw):
            val = float(raw)
            self.set_config(key, val)
            value_label.configure(text=f'{title}: {val:.{digits}f}')
        ttk.Scale(parent, from_=low, to=high, variable=var, command=changed, length=310).pack(fill='x', pady=(3, 11))

    def publish(self, packet):
        try:
            self.updates.put_nowait(packet)
        except queue.Full:
            try:
                self.updates.get_nowait()
            except queue.Empty:
                pass
            try:
                self.updates.put_nowait(packet)
            except queue.Full:
                pass

    def start_worker(self):
        if self.worker_started:
            return
        self.worker_started = True
        self.start_button.configure(state='disabled', text='Loading detector...')
        threading.Thread(target=self.worker, daemon=True).start()

    def toggle(self):
        if not self.ready:
            self.status.set('Load the detector first; wait until it is ready.')
            return
        with self.lock:
            self.config['armed'] = not self.config['armed']
            armed = self.config['armed']
        self.arm_button.configure(text='Running / F8 to pause' if armed else 'Paused / F8 to start')
        if not armed:
            self.status.set('Paused. No capture or mouse movement.')

    def poll(self):
        if self.stop.is_set():
            return
        for code in self.previous_keys:
            down = key_down(code)
            if down and not self.previous_keys[code]:
                if code == 0x78:
                    self.close()
                    return
                self.toggle()
            self.previous_keys[code] = down
        try:
            while True:
                packet = self.updates.get_nowait()
                if 'ready' in packet:
                    self.ready = True
                    self.start_button.configure(text='Detector ready')
                if 'error' in packet:
                    self.set_config('armed', False)
                    self.arm_button.configure(text='Paused / F8 to start')
                    self.status.set(packet['error'])
                    self.worker_started = False
                    self.ready = False
                    self.start_button.configure(state='normal', text='Retry detector')
                elif 'status' in packet:
                    self.status.set(packet['status'])
                if 'image' in packet:
                    from PIL import ImageTk
                    self.preview_image = ImageTk.PhotoImage(packet['image'])
                    self.preview.delete('all')
                    self.preview.create_image(0, 0, anchor='nw', image=self.preview_image)
        except queue.Empty:
            pass
        self.root.after(30, self.poll)

    def worker(self):
        try:
            import mss
            import numpy as np
            from PIL import Image, ImageDraw
            from ultralytics import YOLO
            import torch
            torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) // 2)))
            self.publish({'status': 'Loading YOLO11n-pose. First run may download its weights; screenshots stay local.'})
            model = YOLO(str(DATA / 'yolo11n-pose.pt'))
            model.predict(np.zeros((640,640,3), dtype=np.uint8), imgsz=640, device='cpu', verbose=False)
            self.publish({'ready': True, 'status': 'Detector ready. Use Hazmob full-screen and press F8. F8 activates head snapping. Uncheck Snap aiming for detection-only testing.'})
            fractional_recoil = 0.0
            last = time.monotonic()
            last_preview = 0.0
            with mss.mss() as capture:
                while not self.stop.is_set():
                    with self.lock:
                        cfg = dict(self.config)
                    game = game_window() if cfg['armed'] else None
                    if not game:
                        fractional_recoil = 0.0
                        last = time.monotonic()
                        if cfg['armed']:
                            self.publish({'status': 'Waiting for a foreground Chrome tab with Hazmob in its title.'})
                        self.stop.wait(.15)
                        continue
                    hwnd, rect = game
                    width, height = rect.right-rect.left, rect.bottom-rect.top
                    size = min(640, width, height)
                    region = {'left': rect.left+(width-size)//2, 'top': rect.top+(height-size)//2,
                              'width': size, 'height': size}
                    started = time.monotonic()
                    frame = np.asarray(capture.grab(region))[:,:,:3].copy()
                    results = model.predict(frame, imgsz=640, conf=cfg['confidence'], classes=[0], device='cpu', verbose=False)[0]
                    rows = results.boxes.data.cpu().numpy() if results.boxes is not None else []
                    boxes = [Detection(float(r[0]),float(r[1]),float(r[2]),float(r[3]),float(r[4])) for r in rows]
                    center = (size/2, size/2)
                    keypoints = (results.keypoints.data.cpu().numpy()
                                 if results.keypoints is not None else [])
                    heads = [(head_point(points, box, cfg['head_confidence']), box)
                             for points, box in zip(keypoints, boxes)]
                    target = choose_head(heads, center, cfg['radius'])
                    now = time.monotonic()
                    age = now-started
                    dt = min(now-last, .10)
                    last = now
                    current = game_window()
                    with self.lock:
                        live = dict(self.config)
                    allowed = may_move(live['armed'], live['assist'], (not live['require_rmb'] or key_down(0x02)),
                                       current is not None and current[0] == hwnd, age, self.stop.is_set())
                    if allowed:
                        dx, dy = movement(target[1], center, live['gain'], max_step=240, deadzone=1) if target else (0,0)
                        if key_down(0x01):
                            fractional_recoil += live['compensation']*dt
                            pull = int(fractional_recoil)
                            fractional_recoil -= pull
                            dy += pull
                        else:
                            fractional_recoil = 0.0
                        # Recheck immediately before sending any input.
                        with self.lock:
                            current_config = self.config
                            if (not self.stop.is_set() and current_config['armed'] and current_config['assist']
                                and u32.GetForegroundWindow() == hwnd
                                and (not current_config['require_rmb'] or key_down(0x02))):
                                send_move(dx, dy)
                    else:
                        fractional_recoil = 0.0
                    if now-last_preview > .12:
                        last_preview = now
                        image = Image.fromarray(frame[:,:,::-1])
                        draw = ImageDraw.Draw(image)
                        cx, cy = center
                        radius = cfg['radius']
                        draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius), outline='#9a84ff', width=2)
                        draw.line((cx-8,cy,cx+8,cy),fill='white',width=1)
                        draw.line((cx,cy-8,cx,cy+8),fill='white',width=1)
                        for d in boxes:
                            draw.rectangle((d.x1,d.y1,d.x2,d.y2),outline='#58dba4',width=2)
                            draw.text((d.x1,max(0,d.y1-12)),f'person {d.confidence:.0%}',fill='#58dba4')
                        for point, _ in heads:
                            if point:
                                hx,hy=point
                                draw.ellipse((hx-3,hy-3,hx+3,hy+3),outline='#e9aaff',width=2)
                        if target:
                            x,y=target[1]
                            draw.ellipse((x-5,y-5,x+5,y+5),fill='#ffbf70')
                        mode = 'Snap active' if allowed and target else 'No confident head' if allowed else 'Waiting for RMB' if live['assist'] else 'Detection only'
                        latency = ' / too slow for mouse input' if age > .20 else ''
                        self.publish({'image':image.resize((480,480)), 'status':f'{mode} / {sum(point is not None for point, _ in heads)} head candidates / {age*1000:.0f} ms{latency}'})
                    self.stop.wait(max(0, .05-(time.monotonic()-started)))
        except Exception as exc:
            self.set_config('armed',False)
            self.publish({'error':f'{type(exc).__name__}: {exc}'})

    def close(self):
        self.set_config('armed',False)
        self.stop.set()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    App().run()
