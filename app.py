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
from targeting import Detection, head_point, StableLock, SettlingController

VERSION = '1.3.0'
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


# This source fragment is incorporated into app.py; no extra updater payload file.
class Overlay:
    BONES = [(0,1),(0,2),(1,3),(2,4),(5,6),(5,7),(7,9),(6,8),(8,10),
             (5,11),(6,12),(11,12),(11,13),(13,15),(12,14),(14,16)]
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg='#010101')
        self.window.wm_attributes('-transparentcolor','#010101')
        self.window.wm_attributes('-topmost',True)
        self.canvas = tk.Canvas(self.window,bg='#010101',highlightthickness=0,bd=0)
        self.canvas.pack(fill='both',expand=True)
        self.window.update_idletasks()
        u32.GetAncestor.argtypes = [W.HWND, W.UINT]
        u32.GetAncestor.restype = W.HWND
        self.hwnd = u32.GetAncestor(self.window.winfo_id(), 2)
        getter = u32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u32.GetWindowLongW
        setter = u32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p)==8 else u32.SetWindowLongW
        getter.argtypes=[W.HWND,ctypes.c_int]; getter.restype=ctypes.c_ssize_t
        setter.argtypes=[W.HWND,ctypes.c_int,ctypes.c_ssize_t]; setter.restype=ctypes.c_ssize_t
        setter(self.hwnd,-20,getter(self.hwnd,-20) | 0x80000 | 0x20 | 0x08000000 | 0x80)
        u32.SetWindowDisplayAffinity.argtypes=[W.HWND,W.DWORD]
        u32.SetWindowDisplayAffinity.restype=W.BOOL
        # Exclude our own graphics from the detector input; not a game-access mechanism.
        self.supported=bool(u32.SetWindowDisplayAffinity(self.hwnd,0x11))
        self.rect=None
        self.visible=False
        u32.SetWindowPos.argtypes=[W.HWND,W.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,W.UINT]
        u32.ShowWindow.argtypes=[W.HWND,ctypes.c_int]

    def hide(self):
        self.canvas.delete('all')
        if self.visible:
            u32.ShowWindow(self.hwnd,0)
            self.visible=False

    def draw(self, packet, cfg):
        if not self.supported:
            return
        rect=packet['rect']
        left,top,width,height=rect
        if self.rect != rect:
            self.window.geometry(f'{width}x{height}+0+0')
            self.window.update_idletasks()
            u32.SetWindowPos(self.hwnd,W.HWND(-1),left,top,width,height,0x0010)
            self.rect=rect
        self.canvas.delete('all')
        if cfg['esp']:
            for box in packet['boxes']:
                self.canvas.create_rectangle(box.x1,box.y1,box.x2,box.y2,outline='#72e6b4',width=2)
            if cfg['skeleton']:
                for points in packet['keypoints']:
                    for a,b in self.BONES:
                        if len(points)>max(a,b) and points[a][2]>.6 and points[b][2]>.6:
                            self.canvas.create_line(points[a][0],points[a][1],points[b][0],points[b][1],fill='#bba6ff',width=2)
            if cfg['head_markers']:
                for point,_ in packet['heads']:
                    if point:
                        x,y=point
                        self.canvas.create_oval(x-5,y-5,x+5,y+5,outline='#efc778',width=2)
        cx,cy=width/2,height/2
        if cfg['fov_ring']:
            r=packet['radius']
            self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline='#8f7cd2',width=1)
        if cfg['crosshair']:
            self.canvas.create_line(cx-6,cy,cx+6,cy,fill='white',width=2)
            self.canvas.create_line(cx,cy-6,cx,cy+6,fill='white',width=2)
        if packet['target'] and cfg['esp']:
            x,y=packet['target'][1]
            self.canvas.create_oval(x-9,y-9,x+9,y+9,outline='#ffb763',width=2)
        self.canvas.create_text(width-18,height-16,text=f'Hazmob Snap  v{VERSION}',anchor='se',fill='#b7a5ff',font=('Segoe UI',10))
        if not self.visible:
            u32.ShowWindow(self.hwnd,4) # Show without activating or stealing Chrome focus.
            self.visible=True


class App:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title(f'Hazmob Snap {VERSION}')
        self.root.geometry('500x800')
        self.root.minsize(460,780)
        self.root.configure(bg='#11141d')
        self.stop=threading.Event()
        self.lock=threading.Lock()
        self.config=dict(aimbot=False,esp=False,skeleton=True,head_markers=True,
                         fov_ring=False,crosshair=False,recoil=False,paused=False)
        self.events=queue.SimpleQueue()
        self.frames=queue.Queue(maxsize=1)
        self.ready=False
        self.worker_started=False
        self.previous_keys={0x77:False,0x78:False}
        self.overlay=Overlay(self.root)
        self.last_packet=None
        self.variables={}
        style=ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame',background='#11141d')
        style.configure('TLabel',background='#11141d',foreground='#e9edfa',font=('Segoe UI',10))
        style.configure('Switch.TCheckbutton',background='#1b2030',foreground='#e9edfa',font=('Segoe UI Semibold',11),padding=5)
        style.map('Switch.TCheckbutton',background=[('active','#252c40')])
        outer=ttk.Frame(self.root,padding=22)
        outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='HAZMOB / SNAP',font=('Segoe UI Semibold',23)).pack(anchor='w')
        ttk.Label(outer,text='Simple controls. Stable targeting.',foreground='#9aabc7').pack(anchor='w',pady=(4,18))
        self.add_toggle(outer,'Aimbot','Lock onto a confirmed visible head.','aimbot')
        ttk.Label(outer,text='ON-SCREEN OVERLAY',foreground='#aa96fa',font=('Segoe UI Semibold',9)).pack(anchor='w',pady=(16,8))
        self.add_toggle(outer,'Player ESP','Boxes around visible detected players.','esp')
        self.add_toggle(outer,'Skeleton','Show detected body keypoints with ESP.','skeleton')
        self.add_toggle(outer,'Head markers','Show detected head points with ESP.','head_markers')
        self.add_toggle(outer,'Target circle','Display the aiming area.','fov_ring')
        self.add_toggle(outer,'Crosshair','Show a centered crosshair.','crosshair')
        self.add_toggle(outer,'Recoil compensation','Fixed downward pull while holding both mouse buttons.','recoil')
        self.status=tk.StringVar(value='Loading detector...')
        ttk.Label(outer,textvariable=self.status,wraplength=450,foreground='#bba8ff').pack(anchor='w',pady=(14,8))
        footer=ttk.Frame(outer)
        footer.pack(side='bottom',fill='x',pady=(10,0))
        ttk.Label(footer,text='F8 Pause / resume   |   F9 Exit',font=('Segoe UI',9),foreground='#8c9bb5').pack(side='left')
        ttk.Label(footer,text=f'v{VERSION}',foreground='#bba8ff',font=('Segoe UI Semibold',10)).pack(side='right')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(100,self.start_worker)
        self.root.after(30,self.poll)

    def add_toggle(self,parent,title,subtitle,key):
        frame=tk.Frame(parent,bg='#1b2030')
        frame.pack(fill='x',pady=3)
        variable=tk.BooleanVar(value=self.config[key])
        self.variables[key]=variable
        ttk.Checkbutton(frame,text=title,variable=variable,style='Switch.TCheckbutton',
                        command=lambda:self.set_config(key,variable.get())).pack(anchor='w',fill='x')
        tk.Label(frame,text=subtitle,bg='#1b2030',fg='#96a6c1',font=('Segoe UI',9),anchor='w').pack(fill='x',padx=11,pady=(0,6))

    def set_config(self,key,value):
        with self.lock:
            self.config[key]=bool(value)

    def snapshot(self):
        with self.lock:
            return dict(self.config)

    def publish(self,packet):
        if 'rect' not in packet:
            self.events.put(packet)
            return
        try: self.frames.get_nowait()
        except queue.Empty: pass
        try: self.frames.put_nowait(packet)
        except queue.Full: pass

    def start_worker(self):
        if self.worker_started or self.stop.is_set(): return
        self.worker_started=True
        threading.Thread(target=self.worker,daemon=True).start()

    def poll(self):
        if self.stop.is_set(): return
        for code in self.previous_keys:
            down=key_down(code)
            if down and not self.previous_keys[code]:
                if code==0x78:
                    self.close(); return
                cfg=self.snapshot()
                self.set_config('paused',not cfg['paused'])
            self.previous_keys[code]=down
        try:
            while True:
                event=self.events.get_nowait()
                if event.get('ready'): self.ready=True
                if 'error' in event:
                    self.set_config('paused',True)
                    self.status.set(event['error'])
                elif 'status' in event: self.status.set(event['status'])
        except queue.Empty: pass
        try: self.last_packet=self.frames.get_nowait()
        except queue.Empty: pass
        cfg=self.snapshot()
        packet=self.last_packet
        active=self.ready and not cfg['paused'] and any(cfg[k] for k in ('aimbot','esp','fov_ring','crosshair','recoil'))
        if (active and packet and time.monotonic()-packet['captured']<.22
            and u32.GetForegroundWindow()==packet['hwnd']):
            self.overlay.draw(packet,cfg)
            self.status.set(packet['status'] if self.overlay.supported else packet['status']+' / Overlay unavailable on this Windows capture setup.')
        else:
            self.overlay.hide()
            if self.ready:
                self.status.set('Paused / F8 to resume' if cfg['paused'] else 'Choose a feature, then return to fullscreen Hazmob in Chrome.' if not active else 'Waiting for a fresh game frame.')
        self.root.after(30,self.poll)

    def worker(self):
        try:
            import mss
            import numpy as np
            from ultralytics import YOLO
            import torch
            torch.set_num_threads(max(1,min(4,(os.cpu_count() or 4)//2)))
            self.publish({'status':'Loading pose detector. First load can download model weights.'})
            model=YOLO(str(DATA/'yolo11n-pose.pt'))
            model.predict(np.zeros((640,640,3),dtype=np.uint8),imgsz=640,device='cpu',verbose=False)
            self.publish({'ready':True,'status':'Ready. Turn on Aimbot or Player ESP.'})
            tracker=StableLock()
            controller=SettlingController()
            generation=0
            fraction=0.0
            last=time.monotonic()
            was_aiming=False
            with mss.mss() as capture:
                while not self.stop.is_set():
                    cfg=self.snapshot()
                    active=not cfg['paused'] and any(cfg[k] for k in ('aimbot','esp','fov_ring','crosshair','recoil'))
                    game=game_window() if active else None
                    if not game:
                        tracker.reset(); controller.reset(); was_aiming=False
                        fraction=0.0; last=time.monotonic()
                        self.stop.wait(.10); continue
                    hwnd,rect=game
                    width,height=rect.right-rect.left,rect.bottom-rect.top
                    region={'left':rect.left,'top':rect.top,'width':width,'height':height}
                    started=time.monotonic()
                    frame=np.asarray(capture.grab(region))[:,:,:3].copy()
                    result=model.predict(frame,imgsz=640,conf=.65,classes=[0],device='cpu',verbose=False)[0]
                    rows=result.boxes.data.cpu().numpy() if result.boxes is not None else []
                    boxes=[Detection(*map(float,row[:5])) for row in rows]
                    keypoints=result.keypoints.data.cpu().numpy().tolist() if result.keypoints is not None else []
                    center=(width/2,height/2)
                    radius=min(190,height*.22)
                    heads=[(head_point(points,box,.65),box) for points,box in zip(keypoints,boxes)]
                    now=time.monotonic()
                    age=now-started
                    dt=min(now-last,.10); last=now
                    live=self.snapshot()
                    fresh=age<=.20 and u32.GetForegroundWindow()==hwnd and not self.stop.is_set()
                    aiming=live['aimbot'] and not live['paused'] and fresh
                    if aiming:
                        if not was_aiming: tracker.reset(); controller.reset()
                        target=tracker.update(heads,center,radius,now)
                        if generation!=tracker.generation:
                            controller.reset(); generation=tracker.generation
                    else:
                        target=None
                        tracker.reset(); controller.reset()
                    was_aiming=aiming
                    dx,dy=controller.step(target[1],center,now) if target else (0,0)
                    if live['recoil'] and not target and fresh and key_down(0x01) and key_down(0x02):
                        fraction+=22*dt
                        pull=int(fraction); fraction-=pull; dy+=pull
                    else: fraction=0.0
                    if fresh:
                        with self.lock:
                            current=self.config
                            permitted=(current['aimbot'] and target is not None) or (current['recoil'] and key_down(0x01) and key_down(0x02))
                            if permitted and not current['paused'] and not self.stop.is_set() and u32.GetForegroundWindow()==hwnd:
                                send_move(dx,dy)
                    mode='Head locked' if target else 'Confirming target' if aiming and tracker.box is not None else 'Searching for a confident head' if aiming else 'Overlay active'
                    if not fresh: mode='Frame too slow / aiming paused'
                    self.publish({'rect':(rect.left,rect.top,width,height),'hwnd':hwnd,'captured':started,
                                  'boxes':boxes,'keypoints':keypoints,'heads':heads,'target':target,'radius':radius,
                                  'status':f'{mode} / {len(boxes)} visible players / {age*1000:.0f} ms'})
                    self.stop.wait(max(0,.045-(time.monotonic()-started)))
        except Exception as exc:
            self.set_config('paused',True)
            self.publish({'error':f'{type(exc).__name__}: {exc}. Restart the app to retry.'})

    def close(self):
        self.set_config('paused',True)
        self.stop.set()
        self.overlay.hide()
        self.root.destroy()

    def run(self): self.root.mainloop()

if __name__=='__main__': App().run()
