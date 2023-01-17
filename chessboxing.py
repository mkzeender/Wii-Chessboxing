from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
import logging
from threading import Thread
import time
import traceback

import customtkinter as ctk
import tkinter as tk
import pyautogui as gui
from pywinauto.application import Application
from PIL.Image import Image
import vgamepad as vg

logging.basicConfig(level=logging.INFO)

BOXING_PATH = r"C:\Users\MkZee\Documents\Dolphin Games\Wii Sports (USA) (Rev 1).wbfs"
CHESS_PATH = r"C:\Users\MkZee\Documents\Dolphin Games\Wii Chess (Europe) (En,Fr,De,Es,It).nkit.iso"

WII_CHESS = 'wii chess'
WII_SPORTS = 'wii sports'

@lru_cache
class GamePad(vg.VX360Gamepad):
    def __init__(self):
        super().__init__()
        self.use_count = 0
    def __enter__(self):
        self.use_count += 1
        return self
    
    def __exit__(self, err, err_type, tb):
        self.use_count -= 1
        
        if self.use_count == 0:
            self.update()
            
        return False
        

class TimedGame(ABC):
    
    def __init__(self, duration=60):
        self.start_time: float = 0.0
        self.elapsed: float = 0.0
        self.duration = duration
        self.is_done = False
        
    def update_time(self) -> None:
        if (running := self.clock_running()):
            dt = time.time() - self.start_time - self.elapsed
        else:
            dt = 0
            
        self.elapsed += dt
        
        if self.elapsed >= self.duration and not running:
            self.is_done = True
            
    def run(self) -> None:
        self.start_time = time.time()
        
        while not self.is_done:
            time.sleep(0.01)
            self.update_time()
            
    @abstractmethod
    def clock_running(self) -> bool:
        ...


class Boxing(TimedGame):
    LOC = (101, 1387, 101, 1387)
    COLOR = (0x00, 0x8C, 0xFF)
    
                   
    def clock_running(self) -> bool:
        
        img: Image = gui.screenshot(region=self.LOC)
        logging.debug(img.getpixel((0, 0)))
        logging.debug(img.getpixel((0, 0)) == self.COLOR)
        return img.getpixel((0, 0)) == self.COLOR
            
            
class Chess(TimedGame):
    
    def __init__(self, duration=2.5*60, *, window: TimerWindow):
        self.window = window
        super().__init__(duration)
    
    def clock_running(self) -> bool:
        return self.elapsed <= self.duration
    
    def run(self) -> None:
        self.start_time = time.time()
        while not self.is_done:
            self.update_time()
            self.window.set_time(self.duration - self.elapsed)
            self.window.update()
            time.sleep(1/120)
        
    def _mainloop_ext(self):
        # self.window.after(100, self._mainloop_ext)
        self.update_time()
        self.window.set_time(self.duration - self.elapsed)
        if self.is_done:
            self.window.destroy()
        
               
class TimerWindow(ctk.CTk):
    def __init__(self, on_click:callable, w=200, h=200, **kwargs) -> None:
        self.on_click = on_click
        super().__init__(**kwargs)
        
        ctk.set_appearance_mode('dark')
        
        self.wm_overrideredirect(True)
        self.attributes('-topmost', True)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - w) // 2 * 1.5, (sh - h) // 2
        self.geometry(f'{w}x{h}+{int(x)}+{int(y)}')
        
        self.time_var = tk.StringVar()
        
        ctk.CTkButton(self, textvariable=self.time_var, font=('', 28), command=self.on_click).pack(fill='both', expand=True)
        
    def set_time(self, t: float):
        t: int = int(t)
        mins = t // 60
        secs = t % 60
        self.time_var.set(f'{mins:01}:{secs:02}')
        
        
class CBGame:
    def __init__(self, timer_window: TimerWindow, dolphin:Dolphin) -> None:
        self.pad = GamePad()
        self.timer_window = timer_window
        self.dolphin = dolphin
        self.current: TimedGame|None = None
        self.ended = False
            
    def restore_state(self, first:bool = False):
        p = self.pad
        btn = vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER if first else vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB
        with p:
            p.press_button(btn)
        time.sleep(1/30)
        with p:
            p.release_button(btn)
        
    def save_state(self):
        p = self.pad
        for btn in (vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB, vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER):
            with p:
                p.press_button(btn)
            time.sleep(1/30)
            with p:
                p.release_button(btn)
            time.sleep(1/30)
        time.sleep(5)
                
    def chess_round(self, first:bool, last:bool=False):
        self.current = chess = Chess(window=self.timer_window)
        self.timer_window.deiconify()
        if last:
            chess.duration = 600 # plenty of time
            
        self.dolphin.open_game(WII_CHESS)
        self.restore_state(first=first)
        chess.run()
        self.save_state()
        
    def boxing_round(self, first:bool, last:bool=False):
        self.timer_window.withdraw()
        boxing = Boxing()
        self.dolphin.open_game(WII_SPORTS)
        self.restore_state(first=first)
        boxing.run()
        self.save_state()
              
        
    def run(self):
        rounds = 7
        for i in range(7):
            if self.ended:
                break
            
            round = self.chess_round if i % 2 == 0 else self.boxing_round
            is_first = i in (0, 1)
            is_last = i in (rounds-1, rounds-2)
            round(is_first, is_last)
        
class Dolphin:
    def __init__(self) -> None:
        self.app: Application = Application(backend='uia').start(r'C:\Users\MkZee\AppData\Roaming\.dolphin\Dolphin.exe')
        self.main_win = self.app.Dolphin
        self.main_win.wait('active')
        
    def open_file(self, fp):
        self.app.Dolphin.menu_select('File->Open')
        self.app.Select.name.set_edit_text(fp)
        self.app.Select.Open.click()
        # self.app.OpenDialog.wait_not('visible', timeout=10)
        self.app.window(best_match='Wii').wait(timeout=10)
    
    def wait_for_game(self):
        self.app.window(best_match='Wii').wait('visible')
        
    def open_game(self, game):
        self.app.Dolphin.wait('active', timeout=20)
        gui.press(['home', 'right', 'right'], interval=1/30)
        time.sleep(0.1)
        gui.typewrite(game)
        time.sleep(0.1)
        gui.press('enter')
        time.sleep(5)
        # self.wait_for_game()
        
class GameManager:
    def __init__(self) -> None:
        thread = Thread(target=self.get_commands, daemon=True)
        thread.start()
        
        self.current_game: CBGame|None = None
        self.dolphin = Dolphin()
        self.timer_win = TimerWindow(on_click=self.new)
        self.timer_win.time_var.set('Start Game')
        self.ended = False
        
    def get_commands(self):
        print('Commands: new, next, exit')
        while True:
            cmd = input('>').lower().split()[0]
            getattr(self, cmd)()
            
    def exit(self):
        try:
            self.current_game.ended = True
        except AttributeError:
            pass
        self.ended = True
    
    def new(self):
        try:
            self.current_game.ended = True
        except AttributeError:
            pass
        try:
            self.current_game.current.is_done = True
        except AttributeError:
            pass
        
        self.current_game = CBGame(self.timer_win, self.dolphin)
        
    def run(self):
        
        while self.timer_win.winfo_exists() and not self.ended:
            if self.current_game is None:
                self.timer_win.update()
                time.sleep(1/60)
            else:
                try:
                    self.current_game.run()
                except Exception:
                    traceback.print_exc()
                
                self.current_game = None
                self.timer_win.time_var.set('Start Game')
                self.timer_win.deiconify()
    
def main():
    time.sleep(3)
    GameManager().run()
    
    # CBGame().open_game('wii chess')
    return
    b = Chess(duration=10, window=TimerWindow())
    b.run()
    
    
if __name__ == '__main__':
    main()