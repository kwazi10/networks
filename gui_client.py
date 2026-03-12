# ==========================================
# gui_client.py
# Discord-Style Modern Chat Client
# ==========================================
import socket
import threading
import os
import time
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText

import config
import helpers

# --- MODERN COLOR PALETTE ---
BG_SIDEBAR = "#0F172A"
BG_CHAT = "#1E293B"
BG_INPUT = "#334155"
TEXT_LIGHT = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
ACCENT = "#6366F1"
ACCENT_HOVER = "#4F46E5"
SUCCESS = "#10B981"
ERROR = "#EF4444"


class NetworkingCore:
    def __init__(self, event_queue):
        self.q = event_queue
        self.tcp = None
        self.udp = None
        self.udp_port = None
        self.username = None
        self._stop = threading.Event()
        self.pending_file = None

    def put_event(self, **kwargs):
        self.q.put(kwargs)

    def _udp_listener(self):
        file_open = False
        f = None
        while not self._stop.is_set():
            try:
                data, _ = self.udp.recvfrom(4096)
                if data.startswith(b"META:"):
                    filename = f"received_{data[5:].decode(config.ENCODING)}"
                    if file_open and f: f.close()
                    f = open(filename, "wb")
                    file_open = True
                    self.put_event(type="sys", msg=f"Downloading {filename}...")
                elif data == b"EOF":
                    if f: f.close()
                    file_open = False
                    self.put_event(type="success", msg="File transfer complete!")
                else:
                    if file_open and f: f.write(data)
            except: break

    def _udp_sender(self, targets, filepath):
        filename = os.path.basename(filepath)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.put_event(type="sys", msg=f"Uploading '{filename}'...")
        
        meta = b"META:" + filename.encode(config.ENCODING)
        for ip, port in targets: sock.sendto(meta, (ip, port))
        time.sleep(0.05)
        
        with open(filepath, "rb") as file:
            while True:
                chunk = file.read(1024)
                if not chunk: break
                for ip, port in targets: sock.sendto(chunk, (ip, port))
                time.sleep(0.001)
                
        for ip, port in targets: sock.sendto(b"EOF", (ip, port))
        sock.close()
        self.put_event(type="success", msg=f"'{filename}' sent successfully.")

    def _tcp_listener(self):
        while not self._stop.is_set():
            try:
                raw = self.tcp.recv(config.BUFFER_SIZE)
                if not raw: break
                headers, body = helpers.parse_message(helpers.decode_message(raw))
                msg_type, cmd = headers.get("MessageType"), headers.get("Command")

                if msg_type == "DATA" and cmd == "TEXT":
                    sender, recip = headers.get("SenderID"), headers.get("RecipientID")
                    self.put_event(type="chat", sender=sender, target=recip, msg=body)

                elif msg_type == "CONTROL":
                    if cmd == "PEER_INFO":
                        ip, port = body.split(":")
                        if self.pending_file:
                            threading.Thread(target=self._udp_sender, args=([(ip, int(port))], self.pending_file)).start()
                            self.pending_file = None
                    elif cmd == "GROUP_INFO":
                        if not body:
                            self.put_event(type="err", msg="No members online to receive file.")
                        elif self.pending_file:
                            targets = [(p.split(":")[0], int(p.split(":")[1])) for p in body.split(",")]
                            threading.Thread(target=self._udp_sender, args=(targets, self.pending_file)).start()
                        self.pending_file = None
                    elif cmd == "ONLINE_LIST":
                        self.put_event(type="users", data=body)
                    elif cmd == "DM_REQUEST":
                        self.put_event(type="dm_request", sender=body)
                    elif cmd == "GROUP_INVITE":
                        try:
                            grp, owner = body.split(":", 1)
                            self.put_event(type="invite", group=grp, owner=owner)
                        except: pass
                    elif cmd == "INFO":
                        self.put_event(type="sys", msg=body)
                    elif cmd == "ERROR":
                        self.put_event(type="err", msg=body)
                        self.pending_file = None
            except: break
        self.put_event(type="err", msg="Disconnected from server.")

    def connect(self, ip, user, pwd, mode):
        self._stop.clear()
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(("0.0.0.0", 0))
        self.udp_port = self.udp.getsockname()[1]
        threading.Thread(target=self._udp_listener, daemon=True).start()

        self.tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp.connect((ip or "127.0.0.1", config.SERVER_PORT))
        self.username = user
        
        msg = helpers.build_message("COMMAND", mode, user, "SERVER", f"{pwd}:{self.udp_port}")
        self.tcp.sendall(helpers.encode_message(msg))
        
        reply = self.tcp.recv(config.BUFFER_SIZE)
        headers, body = helpers.parse_message(helpers.decode_message(reply))
        self.put_event(type="sys", msg=body)
        if headers.get("Command") != "ACK": raise PermissionError(body)
        
        threading.Thread(target=self._tcp_listener, daemon=True).start()

    def send(self, cmd, target, body=""):
        if self.tcp:
            msg = helpers.build_message("COMMAND", cmd, self.username, target, body)
            self.tcp.sendall(helpers.encode_message(msg))

    def chat(self, target, text):
        if self.tcp:
            msg = helpers.build_message("DATA", "TEXT", self.username, target, text)
            self.tcp.sendall(helpers.encode_message(msg))

    def disconnect(self):
        self._stop.set()
        if self.tcp: self.tcp.close()
        if self.udp: self.udp.close()


class ModernChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Nexus Messenger")
        self.root.geometry("1100x700")
        self.root.configure(bg=BG_CHAT)
        self.root.minsize(900, 600)

        self.q = queue.Queue()
        self.net = NetworkingCore(self.q)
        
        self.active_target = ""
        self.is_group_target = False
        self.pending_dms = set()  # Tracks who has requested to DM us

        self._build_login()
        self.root.after(100, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_btn(self, parent, text, cmd, bg=ACCENT, fg=TEXT_LIGHT, hover=ACCENT_HOVER):
        btn = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=hover, activeforeground=TEXT_LIGHT, font=("Segoe UI", 10, "bold"), bd=0, cursor="hand2", padx=15, pady=8)
        return btn

    def _build_login(self):
        self.login_view = tk.Frame(self.root, bg=BG_CHAT)
        self.login_view.pack(fill="both", expand=True)
        
        card = tk.Frame(self.login_view, bg=BG_SIDEBAR, padx=50, pady=50)
        card.place(relx=0.5, rely=0.5, anchor="center")
        
        tk.Label(card, text="Nexus", font=("Segoe UI", 28, "bold"), fg=ACCENT, bg=BG_SIDEBAR).pack(pady=(0,5))
        tk.Label(card, text="Secure Socket Communication", font=("Segoe UI", 11), fg=TEXT_MUTED, bg=BG_SIDEBAR).pack(pady=(0,30))

        def make_entry(lbl, hide=False):
            tk.Label(card, text=lbl, bg=BG_SIDEBAR, fg=TEXT_LIGHT, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            e = tk.Entry(card, font=("Segoe UI", 12), bg=BG_INPUT, fg=TEXT_LIGHT, bd=0, insertbackground=TEXT_LIGHT, show="*" if hide else "")
            e.pack(fill="x", pady=(5, 15), ipady=8)
            return e

        self.e_ip = make_entry("SERVER IP (Leave blank for localhost)")
        self.e_user = make_entry("USERNAME")
        self.e_pass = make_entry("PASSWORD", hide=True)

        btn_box = tk.Frame(card, bg=BG_SIDEBAR)
        btn_box.pack(fill="x", pady=(10,0))
        self._create_btn(btn_box, "LOGIN", lambda: self._auth("LOGIN")).pack(side="left", expand=True, fill="x", padx=(0,5))
        self._create_btn(btn_box, "REGISTER", lambda: self._auth("REGISTER"), bg=BG_INPUT, hover=TEXT_MUTED).pack(side="left", expand=True, fill="x", padx=(5,0))

    def _build_main(self):
        self.main_view = tk.Frame(self.root, bg=BG_CHAT)
        
        self.sidebar = tk.Frame(self.main_view, bg=BG_SIDEBAR, width=280)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        prof = tk.Frame(self.sidebar, bg=BG_INPUT, pady=15, padx=15)
        prof.pack(fill="x")
        tk.Label(prof, text=f"Logged in as", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_INPUT).pack(anchor="w")
        tk.Label(prof, text=self.net.username, font=("Segoe UI", 14, "bold"), fg=TEXT_LIGHT, bg=BG_INPUT).pack(anchor="w")

        self._make_sidebar_section("ONLINE USERS", self._on_user_select).pack(fill="both", expand=True, padx=15, pady=10)
        
        grp_frame = tk.Frame(self.sidebar, bg=BG_SIDEBAR)
        grp_frame.pack(fill="both", expand=True, padx=15, pady=10)
        tk.Label(grp_frame, text="GROUPS", font=("Segoe UI", 10, "bold"), fg=TEXT_MUTED, bg=BG_SIDEBAR).pack(anchor="w", pady=(0,5))
        
        self.grp_list = tk.Listbox(grp_frame, bg=BG_SIDEBAR, fg=TEXT_LIGHT, bd=0, highlightthickness=0, font=("Segoe UI", 11), selectbackground=BG_INPUT, activestyle="none")
        self.grp_list.pack(fill="both", expand=True)
        self.grp_list.bind("<<ListboxSelect>>", self._on_group_select)
        
        self._create_btn(self.sidebar, "+ New Group", self._prompt_group, bg=BG_INPUT, hover=BG_CHAT).pack(fill="x", padx=15, pady=15)

        self.chat_area = tk.Frame(self.main_view, bg=BG_CHAT)
        self.chat_area.pack(side="left", fill="both", expand=True)
        
        self.toolbar = tk.Frame(self.chat_area, bg=BG_CHAT, height=70, padx=20)
        self.toolbar.pack(fill="x")
        self.toolbar.pack_propagate(False)
        
        self.lbl_target = tk.Label(self.toolbar, text="Select a user or group to start", font=("Segoe UI", 16, "bold"), fg=TEXT_LIGHT, bg=BG_CHAT)
        self.lbl_target.pack(side="left", pady=20)
        
        self.action_frame = tk.Frame(self.toolbar, bg=BG_CHAT)
        self.action_frame.pack(side="right", pady=15)

        self.hist = ScrolledText(self.chat_area, state="disabled", font=("Segoe UI", 11), bg=BG_CHAT, fg=TEXT_LIGHT, bd=0, highlightthickness=0, padx=20, pady=10, wrap="word")
        self.hist.pack(fill="both", expand=True)
        self.hist.tag_config("sys", foreground=TEXT_MUTED, font=("Segoe UI", 10, "italic"))
        self.hist.tag_config("err", foreground=ERROR, font=("Segoe UI", 10, "bold"))
        self.hist.tag_config("success", foreground=SUCCESS, font=("Segoe UI", 10, "bold"))
        self.hist.tag_config("me", foreground=ACCENT)

        input_bar = tk.Frame(self.chat_area, bg=BG_INPUT, padx=10, pady=10)
        input_bar.pack(fill="x", padx=20, pady=20)
        
        self.e_msg = tk.Entry(input_bar, font=("Segoe UI", 12), bg=BG_INPUT, fg=TEXT_LIGHT, bd=0, insertbackground=TEXT_LIGHT)
        self.e_msg.pack(side="left", fill="x", expand=True, ipady=5, padx=(10, 10))
        self.e_msg.bind("<Return>", lambda e: self._send_msg())
        
        tk.Button(input_bar, text="📎", font=("Segoe UI", 14), bg=BG_INPUT, fg=TEXT_MUTED, bd=0, cursor="hand2", command=self._send_file).pack(side="right", padx=5)
        
        # Start background roster refresh
        self._auto_refresh()

    def _make_sidebar_section(self, title, on_select):
        f = tk.Frame(self.sidebar, bg=BG_SIDEBAR)
        tk.Label(f, text=title, font=("Segoe UI", 10, "bold"), fg=TEXT_MUTED, bg=BG_SIDEBAR).pack(anchor="w", pady=(0,5))
        lb = tk.Listbox(f, bg=BG_SIDEBAR, fg=TEXT_LIGHT, bd=0, highlightthickness=0, font=("Segoe UI", 11), selectbackground=BG_INPUT, activestyle="none")
        lb.pack(fill="both", expand=True)
        lb.bind("<<ListboxSelect>>", on_select)
        if title == "ONLINE USERS": self.user_list = lb
        return f

    def _auth(self, mode):
        ip, user, pwd = self.e_ip.get().strip(), self.e_user.get().strip(), self.e_pass.get().strip()
        if not user or not pwd: return messagebox.showerror("Error", "Missing credentials.")
        try:
            self.net.connect(ip, user, pwd, mode)
            self.login_view.pack_forget()
            self._build_main()
            self.main_view.pack(fill="both", expand=True)
            self.net.send("ONLINE_USERS", "SERVER")
        except Exception as e: messagebox.showerror("Auth Error", str(e))

    def _log(self, text, tag=None):
        self.hist.config(state="normal")
        self.hist.insert("end", text + "\n", tag)
        self.hist.config(state="disabled")
        self.hist.see("end")

    def _update_toolbar(self):
        for w in self.action_frame.winfo_children(): w.destroy()
        if not self.active_target: return
        
        if self.is_group_target:
            self.lbl_target.config(text=f"# {self.active_target}")
            self._create_btn(self.action_frame, "+ Invite User", self._invite_to_grp, bg=BG_INPUT, hover=TEXT_MUTED).pack(side="left", padx=5)
        else:
            self.lbl_target.config(text=f"@ {self.active_target}")
            # ONLY show Accept DM if a request was actually sent
            if self.active_target in self.pending_dms:
                self._create_btn(self.action_frame, "Accept DM", self._accept_dm, bg=SUCCESS, hover="#059669").pack(side="left", padx=5)
            else:
                self._create_btn(self.action_frame, "Request DM", lambda: self.net.send("REQUEST_DM", self.active_target), bg=BG_INPUT, hover=TEXT_MUTED).pack(side="left", padx=5)

    def _on_user_select(self, e):
        sel = self.user_list.curselection()
        if sel:
            self.active_target = self.user_list.get(sel[0])
            self.is_group_target = False
            self.grp_list.selection_clear(0, 'end')
            self._update_toolbar()

    def _on_group_select(self, e):
        sel = self.grp_list.curselection()
        if sel:
            self.active_target = self.grp_list.get(sel[0])
            self.is_group_target = True
            self.user_list.selection_clear(0, 'end')
            self._update_toolbar()

    def _prompt_group(self):
        name = simpledialog.askstring("New Group", "Enter group name:")
        if name:
            self.net.send("CREATE_GROUP", "SERVER", name.strip())
            self.grp_list.insert("end", name.strip())

    def _invite_to_grp(self):
        user = simpledialog.askstring("Invite", f"Enter username to invite to '{self.active_target}':")
        if user: self.net.send("INVITE_GROUP", "SERVER", f"{self.active_target}:{user.strip()}")

    def _accept_dm(self):
        self.net.send("ACCEPT_DM", self.active_target)
        if self.active_target in self.pending_dms:
            self.pending_dms.remove(self.active_target)
        self._update_toolbar()

    def _send_msg(self):
        if not self.active_target: return messagebox.showwarning("Wait!", "Select a target from the sidebar first.")
        text = self.e_msg.get().strip()
        if text:
            self.net.chat(self.active_target, text)
            self._log(f"You: {text}", "me")
            self.e_msg.delete(0, "end")

    def _send_file(self):
        if not self.active_target: return messagebox.showwarning("Wait!", "Select a target from the sidebar first.")
        path = filedialog.askopenfilename()
        if path:
            self.net.pending_file = path
            self.net.send("PEER_LOOKUP", self.active_target)

    def _poll(self):
        while not self.q.empty():
            e = self.q.get()
            t = e.get("type")
            if t == "chat": self._log(f"{e.get('sender')}: {e.get('msg')}")
            elif t == "sys": self._log(f"⚙️ {e.get('msg')}", "sys")
            elif t == "err": self._log(f"❌ {e.get('msg')}", "err")
            elif t == "success": self._log(f"✅ {e.get('msg')}", "success")
            elif t == "users":
                self.user_list.delete(0, "end")
                for u in e.get("data").split(","):
                    if u.strip() and "No one" not in u: self.user_list.insert("end", u.strip())
            elif t == "dm_request":
                sender = e.get("sender")
                self.pending_dms.add(sender)
                self._log(f"⚙️ '{sender}' wants to DM you! Select their name and click 'Accept DM'.", "sys")
                if self.active_target == sender:
                    self._update_toolbar()
            elif t == "invite":
                grp, owner = e.get("group"), e.get("owner")
                if messagebox.askyesno("Group Invite", f"'{owner}' invited you to join '{grp}'. Accept?"):
                    self.net.send("ACCEPT_GROUP", "SERVER", grp)
                    if grp not in self.grp_list.get(0, "end"): self.grp_list.insert("end", grp)
                    
        self.root.after(100, self._poll)

    def _auto_refresh(self):
        if hasattr(self, 'main_view'):
            self.net.send("ONLINE_USERS", "SERVER")
        self.root.after(5000, self._auto_refresh)

    def _on_close(self):
        self.net.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    app_root = tk.Tk()
    ModernChatApp(app_root)
    app_root.mainloop()