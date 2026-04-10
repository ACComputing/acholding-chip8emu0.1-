import tkinter as tk
from tkinter import filedialog, ttk
import threading
import time
import os
import random
import math

# ---------- AC HOLDING CHIP-8 CORE ----------
class Emulator:
    def __init__(self):
        # Memory: 4KB (0x000-0xFFF)
        self.memory = bytearray(4096)
        # Standard Fontset: 0-9, A-F
        self.fontset = [
            0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
            0x20, 0x60, 0x20, 0x20, 0x70, # 1
            0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
            0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
            0x90, 0x90, 0xF0, 0x10, 0x10, # 4
            0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
            0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
            0xF0, 0x10, 0x20, 0x40, 0x40, # 7
            0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
            0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
            0xF0, 0x90, 0xF0, 0x90, 0x90, # A
            0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
            0xF0, 0x80, 0x80, 0x80, 0xF0, # C
            0xE0, 0x90, 0x90, 0x90, 0xE0, # D
            0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
            0xF0, 0x80, 0xF0, 0x80, 0x80  # F
        ]
        for i, byte in enumerate(self.fontset):
            self.memory[i] = byte

        self.V = [0] * 16          # 16 8-bit registers
        self.I = 0                 # 16-bit address register
        self.pc = 0x200            # Program counter starts at 0x200
        self.stack = []            # Stack for subroutines
        self.delay_timer = 0
        self.sound_timer = 0
        self.keys = [False] * 16   # Key states
        self.display = [[0]*64 for _ in range(32)] # 64x32 pixels

        self.rom_loaded = False
        self.beep_callback = None

    def load_rom(self, path):
        with open(path, 'rb') as f:
            rom_data = f.read()
        # Reset memory (keeping font)
        self.memory[0x200:] = bytearray(4096 - 0x200)
        # Load ROM
        for i, byte in enumerate(rom_data):
            if 0x200 + i < 4096:
                self.memory[0x200 + i] = byte
        self.rom_loaded = True
        self.reset()

    def reset(self):
        self.V = [0] * 16
        self.I = 0
        self.pc = 0x200
        self.stack.clear()
        self.delay_timer = 0
        self.sound_timer = 0
        self.display = [[0]*64 for _ in range(32)]
        self.keys = [False] * 16

    def step(self):
        if not self.rom_loaded or self.pc >= 4095:
            return
        
        # Fetch Opcode (2 bytes)
        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc += 2
        
        self._execute(opcode)

    def _execute(self, opcode):
        c = (opcode & 0xF000) >> 12
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        n = (opcode & 0x000F)
        nn = (opcode & 0x00FF)
        nnn = (opcode & 0x0FFF)

        if opcode == 0x00E0: # CLS
            self.display = [[0]*64 for _ in range(32)]
        elif opcode == 0x00EE: # RET
            if self.stack: self.pc = self.stack.pop()
        elif c == 0x1: # JP addr
            self.pc = nnn
        elif c == 0x2: # CALL addr
            self.stack.append(self.pc)
            self.pc = nnn
        elif c == 0x3: # SE Vx, byte
            if self.V[x] == nn: self.pc += 2
        elif c == 0x4: # SNE Vx, byte
            if self.V[x] != nn: self.pc += 2
        elif c == 0x5: # SE Vx, Vy
            if self.V[x] == self.V[y]: self.pc += 2
        elif c == 0x6: # LD Vx, byte
            self.V[x] = nn
        elif c == 0x7: # ADD Vx, byte
            self.V[x] = (self.V[x] + nn) & 0xFF
        elif c == 0x8:
            if n == 0x0: self.V[x] = self.V[y]
            elif n == 0x1: self.V[x] |= self.V[y]
            elif n == 0x2: self.V[x] &= self.V[y]
            elif n == 0x3: self.V[x] ^= self.V[y]
            elif n == 0x4:
                res = self.V[x] + self.V[y]
                self.V[0xF] = 1 if res > 255 else 0
                self.V[x] = res & 0xFF
            elif n == 0x5:
                self.V[0xF] = 1 if self.V[x] > self.V[y] else 0
                self.V[x] = (self.V[x] - self.V[y]) & 0xFF
            elif n == 0x6:
                self.V[0xF] = self.V[x] & 1
                self.V[x] >>= 1
            elif n == 0x7:
                self.V[0xF] = 1 if self.V[y] > self.V[x] else 0
                self.V[x] = (self.V[y] - self.V[x]) & 0xFF
            elif n == 0xE:
                self.V[0xF] = (self.V[x] >> 7) & 1
                self.V[x] = (self.V[x] << 1) & 0xFF
        elif c == 0x9: # SNE Vx, Vy
            if self.V[x] != self.V[y]: self.pc += 2
        elif c == 0xA: # LD I, addr
            self.I = nnn
        elif c == 0xB: # JP V0, addr
            self.pc = nnn + self.V[0]
        elif c == 0xC: # RND Vx, byte
            self.V[x] = random.randint(0, 255) & nn
        elif c == 0xD: # DRW Vx, Vy, nibble
            vx = self.V[x] % 64
            vy = self.V[y] % 32
            self.V[0xF] = 0
            for row in range(n):
                if self.I + row >= 4096: break
                sprite_byte = self.memory[self.I + row]
                for col in range(8):
                    if (sprite_byte & (0x80 >> col)) != 0:
                        px = (vx + col) % 64
                        py = (vy + row) % 32
                        if self.display[py][px] == 1:
                            self.V[0xF] = 1
                        self.display[py][px] ^= 1
        elif c == 0xE:
            if nn == 0x9E: # SKP Vx
                if self.keys[self.V[x] & 0xF]: self.pc += 2
            elif nn == 0xA1: # SKNP Vx
                if not self.keys[self.V[x] & 0xF]: self.pc += 2
        elif c == 0xF:
            if nn == 0x07: self.V[x] = self.delay_timer
            elif nn == 0x0A: # LD Vx, K (Wait for key)
                pressed = False
                for i, k in enumerate(self.keys):
                    if k:
                        self.V[x] = i
                        pressed = True
                        break
                if not pressed: self.pc -= 2
            elif nn == 0x15: self.delay_timer = self.V[x]
            elif nn == 0x18: self.sound_timer = self.V[x]
            elif nn == 0x1E: self.I = (self.I + self.V[x]) & 0xFFFF
            elif nn == 0x29: self.I = (self.V[x] & 0xF) * 5
            elif nn == 0x33:
                val = self.V[x]
                self.memory[self.I] = val // 100
                self.memory[self.I + 1] = (val // 10) % 10
                self.memory[self.I + 2] = val % 10
            elif nn == 0x55:
                for i in range(x + 1): self.memory[self.I + i] = self.V[i]
            elif nn == 0x65:
                for i in range(x + 1): self.V[i] = self.memory[self.I + i]

    def update_timers(self):
        if self.delay_timer > 0: self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1
            if self.sound_timer > 0 and self.beep_callback:
                self.beep_callback()

# ---------- GUI APPLICATION ----------
class ACHoldingChip8Emu:
    def __init__(self, root):
        self.root = root
        self.root.title("AC HOLDING CHIP 8 EMU")
        self.root.geometry("850x500")
        self.root.configure(bg="#121212")
        
        # UI Styling
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background="#121212")
        self.style.configure("TLabel", background="#121212", foreground="#00FF41", font=("Courier", 10))

        # Emulator Setup
        self.emulator = Emulator()
        self.emulator.beep_callback = self.trigger_beep
        self.running = False
        self.rom_path = None
        
        # Layout
        self.main_container = tk.Frame(root, bg="#121212")
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Display (Canvas)
        self.canvas_frame = tk.Frame(self.main_container, bg="#000000", bd=4, relief="ridge")
        self.canvas_frame.pack(side=tk.LEFT)
        
        self.canvas = tk.Canvas(self.canvas_frame, width=640, height=320, bg="#000000", highlightthickness=0)
        self.canvas.pack()
        
        # Sidebar Controls
        self.sidebar = tk.Frame(self.main_container, bg="#1a1a1a", width=180)
        self.sidebar.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(20, 0))
        
        tk.Label(self.sidebar, text="AC HOLDING", fg="#FFFFFF", bg="#1a1a1a", font=("Arial", 14, "bold")).pack(pady=10)
        tk.Label(self.sidebar, text="CHIP-8 EMU V1.2", fg="#00FF41", bg="#1a1a1a", font=("Courier", 8)).pack()
        
        # Define common button style
        btn_style = {
            "bg": "black",
            "fg": "#0099ff", # Bright blue for visibility
            "activebackground": "#222222",
            "activeforeground": "#00ccff",
            "bd": 0,
            "pady": 8,
            "font": ("Arial", 9, "bold")
        }

        self.load_btn = tk.Button(self.sidebar, text="LOAD ROM", command=self.load_rom, **btn_style)
        self.load_btn.pack(fill=tk.X, pady=(20, 10), padx=10)
        
        self.run_btn = tk.Button(self.sidebar, text="START", command=self.toggle_run, state=tk.DISABLED, **btn_style)
        self.run_btn.pack(fill=tk.X, pady=5, padx=10)
        
        self.reset_btn = tk.Button(self.sidebar, text="RESET", command=self.reset_emu, **btn_style)
        self.reset_btn.pack(fill=tk.X, pady=5, padx=10)
        
        # Speed Control
        tk.Label(self.sidebar, text="Cycles Per Frame", fg="#888", bg="#1a1a1a").pack(pady=(20, 0))
        self.speed_var = tk.IntVar(value=10)
        self.speed_scale = tk.Scale(self.sidebar, from_=1, to=50, orient=tk.HORIZONTAL, variable=self.speed_var,
                                    bg="#1a1a1a", fg="white", highlightthickness=0)
        self.speed_scale.pack(fill=tk.X, padx=10)
        
        # Info Box
        self.status_var = tk.StringVar(value="Status: Ready")
        tk.Label(self.sidebar, textvariable=self.status_var, fg="#00FF41", bg="#000", font=("Courier", 8),
                 wraplength=150, pady=10).pack(side=tk.BOTTOM, fill=tk.X)

        # Keyboard Mapping
        self.root.bind("<KeyPress>", self.key_press)
        self.root.bind("<KeyRelease>", self.key_release)
        
        # Keymap: 
        # 1 2 3 4 -> 1 2 3 C
        # Q W E R -> 4 5 6 D
        # A S D F -> 7 8 9 E
        # Z X C V -> A 0 B F
        self.key_map = {
            '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
            'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
            'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
            'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF
        }

        # Start Graphics Loop
        self.pixel_ids = [[None for _ in range(64)] for _ in range(32)]
        self._init_canvas_pixels()
        self.update_graphics()

    def _init_canvas_pixels(self):
        for y in range(32):
            for x in range(64):
                self.pixel_ids[y][x] = self.canvas.create_rectangle(
                    x*10, y*10, (x+1)*10, (y+1)*10,
                    fill="#000000", outline=""
                )

    def load_rom(self):
        path = filedialog.askopenfilename(filetypes=[("CHIP-8 ROMs", "*.ch8 *.rom *.c8")])
        if path:
            self.rom_path = path
            self.emulator.load_rom(path)
            self.status_var.set(f"Loaded: {os.path.basename(path)}")
            self.run_btn.config(state=tk.NORMAL)
            self.reset_emu()

    def toggle_run(self):
        self.running = not self.running
        if self.running:
            self.run_btn.config(text="PAUSE")
            self.status_var.set("Status: Running")
            self.emu_loop()
        else:
            self.run_btn.config(text="RESUME")
            self.status_var.set("Status: Paused")

    def reset_emu(self):
        self.emulator.reset()
        if self.rom_path:
            self.emulator.load_rom(self.rom_path)
        self.status_var.set("Status: Reset Complete")
        self.draw_frame()

    def trigger_beep(self):
        # Uses the built-in Tkinter bell as a fallback for sound
        self.root.bell()

    def key_press(self, event):
        k = event.char.lower()
        if k in self.key_map:
            self.emulator.keys[self.key_map[k]] = True

    def key_release(self, event):
        k = event.char.lower()
        if k in self.key_map:
            self.emulator.keys[self.key_map[k]] = False

    def emu_loop(self):
        if self.running:
            # Run several cycles per frame to simulate speed
            for _ in range(self.speed_var.get()):
                self.emulator.step()
            self.emulator.update_timers()
            self.root.after(16, self.emu_loop) # ~60Hz loop

    def update_graphics(self):
        self.draw_frame()
        self.root.after(33, self.update_graphics) # ~30fps for UI refresh

    def draw_frame(self):
        # Optimized drawing: only change color if state differs
        for y in range(32):
            for x in range(64):
                color = "#00FF41" if self.emulator.display[y][x] else "#000000"
                # Accessing tag_configure or itemconfig
                self.canvas.itemconfig(self.pixel_ids[y][x], fill=color)

if __name__ == "__main__":
    root = tk.Tk()
    # Centering the window
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws/2) - (850/2)
    y = (hs/2) - (500/2)
    root.geometry('%dx%d+%d+%d' % (850, 500, x, y))
    
    app = ACHoldingChip8Emu(root)
    root.mainloop()
