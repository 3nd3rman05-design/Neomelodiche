import hashlib
import random
import string
import requests
import flet as ft
import flet_audio 
import time
import os
import shutil
import threading

# --- CONFIGURAZIONE E CACHE ---
CACHE_DIR = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_v5")

class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True 
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.is_playing = False 
        
        # --- AUDIO PLAYER UNICO (PERSISTENTE) ---
        # Lo creiamo una volta sola e non lo distruggiamo mai.
        self.audio_player = flet_audio.Audio(
            autoplay=False, # Gestiamo noi il play
            volume=1.0,
            on_state_changed=self.on_audio_state,
            on_position_changed=self.on_audio_position
        )
        # Lo aggiungiamo subito all'overlay
        self.page.overlay.append(self.audio_player)
        
        # Stile
        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        # Setup Cache Pulita
        if os.path.exists(CACHE_DIR):
            try: shutil.rmtree(CACHE_DIR)
            except: pass
        os.makedirs(CACHE_DIR, exist_ok=True)

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.config = {"ip_home": "", "ip_remote": "", "user": "", "pass": ""}
        
        # Elementi UI Riusabili
        self.time_label = ft.Text("--:--", color="green", font_family=self.FONT_NAME)
        self.btn_play_icon = ft.Icon(ft.Icons.PLAY_ARROW, color="white", size=40)

        # Boot
        self.safe_boot()

    def safe_boot(self):
        try:
            if self.page.client_storage.contains_key("navix_cfg"):
                self.config = self.page.client_storage.get("navix_cfg")
                if not self.config.get("ip_home"): self.show_setup_screen()
                else: self.show_selector()
            else:
                self.show_setup_screen()
        except: self.show_setup_screen()

    # --- SETUP SCREEN (AUTO-HTTP) ---
    def show_setup_screen(self, error=None):
        self.page.clean()
        st = ft.TextStyle(font_family=self.FONT_NAME)
        
        val_h = self.config.get("ip_home", "192.168.1.20:4533") # Esempio senza http
        val_r = self.config.get("ip_remote", "100.x.y.z:4533")
        val_u = self.config.get("user", "admin")
        
        t_h = ft.TextField(label="HOME IP", value=val_h, text_style=st, border_color="green", hint_text="192.168.1.x:4533")
        t_r = ft.TextField(label="REMOTE IP", value=val_r, text_style=st, border_color="red", hint_text="100.x.y.z:4533")
        t_u = ft.TextField(label="USER", value=val_u, text_style=st)
        t_p = ft.TextField(label="PASS", password=True, can_reveal_password=True, text_style=st)
        err_lbl = ft.Text(error if error else "", color="red")

        def save(e):
            # LOGICA AUTO-HTTP
            h_raw = t_h.value.strip().rstrip("/")
            r_raw = t_r.value.strip().rstrip("/")
            
            # Se non inizia con http, lo aggiungiamo noi
            if h_raw and not h_raw.startswith("http"): h_raw = "http://" + h_raw
            if r_raw and not r_raw.startswith("http"): r_raw = "http://" + r_raw

            try:
                self.config = {
                    "ip_home": h_raw,
                    "ip_remote": r_raw,
                    "user": t_u.value.strip(),
                    "pass": t_p.value.strip()
                }
                self.page.client_storage.set("navix_cfg", self.config)
                self.show_selector()
            except Exception as ex:
                err_lbl.value = str(ex)
                self.page.update()

        self.page.add(ft.Container(
            content=ft.Column([
                ft.Text("/// SETUP ///", size=24, font_family=self.FONT_NAME),
                err_lbl, t_h, t_r, t_u, t_p,
                ft.ElevatedButton("SAVE CONFIG", on_click=save)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(top=50, left=30, right=30),
            alignment=ft.alignment.center, expand=True
        ))

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'SinglePlayer', 'f': 'json'}

    # --- SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        
        # FERMA L'AUDIO SE TORNU AL MENU (Opzionale, per pulizia)
        if self.audio_player:
            self.audio_player.pause()
            self.is_playing = False
        
        def rst(e): 
            self.page.client_storage.remove("navix_cfg")
            self.show_setup_screen()
        
        def mk(t, i, c, u):
            return ft.Container(
                content=ft.Column([ft.Icon(i,40,"black"), ft.Text(t,weight="bold",color="black",font_family=self.FONT_NAME)], alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=c, width=180, height=140, border=ft.border.all(4, "white"), 
                on_click=lambda _: self.load_library_view(u)
            )

        self.page.add(ft.Container(
            content=ft.Column([
                ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=rst)], alignment=ft.MainAxisAlignment.END),
                ft.Text("SYSTEM BOOT", size=24, font_family=self.FONT_NAME), ft.Container(height=40),
                mk("LOCAL", ft.Icons.HOME, "#00FF00", self.config["ip_home"]), ft.Container(height=20),
                mk("VPN", ft.Icons.PUBLIC, "#FF0000", self.config["ip_remote"])
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), 
            padding=ft.padding.only(top=50), 
            alignment=ft.alignment.center, expand=True
        ))

    # --- LISTA ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        
        header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.STORAGE, color="white"), 
                ft.Text("DATABASE", font_family=self.FONT_NAME, size=20, weight="bold")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#111111", 
            padding=ft.padding.only(top=50, bottom=20, left=20, right=20), 
            border=ft.border.only(bottom=ft.border.BorderSide(2, "white"))
        )
        
        fab = None
        if self.current_song_data:
             fab = ft.FloatingActionButton(
                 icon=ft.Icons.MUSIC_NOTE, bgcolor="white", content=ft.Icon(ft.Icons.MUSIC_NOTE, color="black"),
                 on_click=lambda _: self.show_player_view()
             )

        self.page.add(ft.Column([header, ft.Container(content=self.songs_column, expand=True)], expand=True))
        self.page.floating_action_button = fab
        
        if not self.playlist: self.fetch_songs()
        self.page.update()

    # --- PLAYER UI ---
    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        
        try:
            p = self.get_auth_params()
            p['id'] = self.current_song_data['id']
            p['size'] = 600
            req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=p)
            cover_url = req.prepare().url
        except: cover_url = ""

        img = ft.Image(src=cover_url, width=300, height=300, fit=ft.ImageFit.COVER, error_content=ft.Container(bgcolor="#333"), border_radius=0)
        
        # Aggiorna icona in base allo stato
        self.btn_play_icon.name = ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW
        
        controls = ft.Row([
            ft.Container(content=ft.Text("<<<", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=self.prev_track),
            ft.Container(content=self.btn_play_icon, width=80, height=80, bgcolor="black", border=ft.border.all(3, "white"), border_radius=40, alignment=ft.alignment.center, on_click=self.toggle_play_pause),
            ft.Container(content=ft.Text(">>>", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=self.next_track)
        ], alignment=ft.MainAxisAlignment.CENTER)

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.load_library_view(self.base_url))]),
                    ft.Container(height=20), 
                    ft.Container(content=img, border=ft.border.all(4, "white")),
                    ft.Container(height=30),
                    self.time_label, # Mostra progresso
                    ft.Text(self.current_song_data['title'], size=20, font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Text(self.current_song_data.get('artist','?'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Container(expand=True), 
                    controls, 
                    ft.Container(height=50)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.only(top=50, left=20, right=20, bottom=20), 
                expand=True, bgcolor="black"
            )
        )
        self.page.update()

    # --- LOGICA PLAYBACK (SINGLE PLAYER - NO GHOSTS) ---
    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        # 1. FERMA IL PLAYER ESISTENTE (Senza distruggerlo)
        self.audio_player.pause()
        self.is_playing = False
        
        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.show_player_view() # Aggiorna grafica subito
        
        # 2. SCARICA IN THREAD (Per non bloccare UI)
        threading.Thread(target=self._download_and_swap_source, args=(self.current_song_data,), daemon=True).start()

    def _download_and_swap_source(self, song_data):
        try:
            self.time_label.value = "DOWNLOADING..."
            self.time_label.color = "yellow"
            self.page.update()

            p = self.get_auth_params()
            p['id'] = song_data['id']
            url = f"{self.base_url}/rest/stream?id={song_data['id']}&format=mp3&maxBitRate=128"
            for k, v in p.items(): url += f"&{k}={v}"

            filename = f"track_{song_data['id']}.mp3"
            path = os.path.join(CACHE_DIR, filename)

            # Scarica solo se non esiste o è vuoto
            if not (os.path.exists(path) and os.path.getsize(path) > 1000):
                with requests.get(url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    with open(path, 'wb') as f:
                        for chunk in r.iter_content(32768):
                            if chunk: f.write(chunk)
            
            # 3. CAMBIA SORGENTE E PLAY (Thread Safe su player unico)
            # Usiamo self.audio_player che è stato creato in __init__ ed è UNICO.
            self.audio_player.src = path
            self.audio_player.update() # Aggiorna la proprietà src
            self.audio_player.resume() # Play
            
            self.is_playing = True
            self.btn_play_icon.name = ft.Icons.PAUSE
            self.time_label.value = "PLAYING"
            self.time_label.color = "green"
            self.page.update()

        except Exception as e:
            self.time_label.value = "ERROR"
            self.time_label.color = "red"
            self.page.update()
            print(f"DL Error: {e}")

    def toggle_play_pause(self, e):
        if self.is_playing:
            self.audio_player.pause()
            self.is_playing = False
            self.btn_play_icon.name = ft.Icons.PLAY_ARROW
        else:
            self.audio_player.resume()
            self.is_playing = True
            self.btn_play_icon.name = ft.Icons.PAUSE
        
        self.page.update()

    def on_audio_position(self, e):
        # Aggiorna il tempo solo se siamo nel player view
        if self.page.floating_action_button is None: # Siamo nel player
            ms = int(e.data)
            self.time_label.value = f"{ms // 1000}s"
            self.page.update()

    def on_audio_state(self, e):
        if e.data == "completed":
            self.next_track()

    def next_track(self, e=None):
        self.play_track_index((self.current_index + 1) % len(self.playlist))

    def prev_track(self, e=None):
        self.play_track_index((self.current_index - 1) % len(self.playlist))

    def fetch_songs(self):
        self.songs_column.controls.append(ft.Text("LOADING...", font_family=self.FONT_NAME))
        self.page.update()
        try:
            p = self.get_auth_params()
            p['size'] = 100
            res = requests.get(f"{self.base_url}/rest/getRandomSongs", params=p, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                self.songs_column.controls.clear()
                self.playlist = []
                if 'randomSongs' in data['subsonic-response']:
                    for idx, s in enumerate(data['subsonic-response']['randomSongs']['song']):
                        self.playlist.append(s)
                        self.songs_column.controls.append(ft.Container(
                            content=ft.Row([ft.Icon(ft.Icons.MUSIC_NOTE), ft.Column([ft.Text(s['title'], weight="bold"), ft.Text(s.get('artist','?'), color="grey")], expand=True)]),
                            padding=15, bgcolor="#000000" if idx%2==0 else "#111111",
                            on_click=lambda e, i=idx: self.play_track_index(i)
                        ))
                else: self.songs_column.controls.append(ft.Text("NO SONGS FOUND", color="red"))
            else:
                self.songs_column.controls.append(ft.Text(f"AUTH ERROR: {res.status_code}", color="red"))
        except: self.songs_column.controls.append(ft.Text("CONNECTION ERROR", color="red"))
        self.page.update()

def main(page: ft.Page):
    app = UltimatePlayer(page)

ft.app(target=main)
