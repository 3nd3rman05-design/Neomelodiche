import hashlib
import random
import string
import requests
import flet as ft
import flet_audio 
import time
import os
import threading
import glob
import shutil

class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True 
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.audio_player = None 
        self.is_playing = False 
        self.last_click_time = 0 
        
        # Cache Folder Setup
        self.cache_dir = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_buffer")
        if os.path.exists(self.cache_dir):
            try: shutil.rmtree(self.cache_dir)
            except: pass
        os.makedirs(self.cache_dir, exist_ok=True)

        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.debug_label = ft.Text("SYSTEM READY", color="grey", size=10, font_family=self.FONT_NAME)
        
        self.config = {"ip_home": "", "ip_remote": "", "user": "", "pass": ""}

    def safe_boot(self):
        try:
            if self.page.client_storage.contains_key("navix_cfg"):
                self.config = self.page.client_storage.get("navix_cfg")
                self.show_selector()
            else:
                self.show_setup_screen()
        except: self.show_setup_screen()

    def show_setup_screen(self):
        self.page.clean()
        style = ft.TextStyle(font_family=self.FONT_NAME)
        t_ip_h = ft.TextField(label="HOME IP", value="http://192.168.1.20:4533", text_style=style)
        t_ip_r = ft.TextField(label="REMOTE IP", value="http://100.", text_style=style)
        t_u = ft.TextField(label="USER", value="admin", text_style=style)
        t_p = ft.TextField(label="PASS", password=True, can_reveal_password=True, text_style=style)
        
        def save(e):
            if not t_ip_h.value: return
            self.config = {"ip_home": t_ip_h.value.strip(), "ip_remote": t_ip_r.value.strip(), "user": t_u.value.strip(), "pass": t_p.value.strip()}
            self.page.client_storage.set("navix_cfg", self.config)
            self.show_selector()

        self.page.add(ft.Container(content=ft.Column([
            ft.Text("SETUP", size=24, font_family=self.FONT_NAME), t_ip_h, t_ip_r, t_u, t_p,
            ft.ElevatedButton("SAVE", on_click=save)
        ]), padding=30, alignment=ft.alignment.center, expand=True))

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'AudioFix', 'f': 'json'}

    def show_selector(self):
        self.page.clean()
        self.kill_ghosts() # Pulizia totale al menu
        
        def rst(e): 
            self.page.client_storage.remove("navix_cfg")
            self.show_setup_screen()
        def mk(t, i, c, u):
            return ft.Container(content=ft.Column([ft.Icon(i,40,"black"), ft.Text(t,weight="bold",color="black",font_family=self.FONT_NAME)], alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=c, width=180, height=140, border=ft.border.all(4, "white"), on_click=lambda _: self.load_library_view(u))

        self.page.add(ft.Container(content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=rst)], alignment=ft.MainAxisAlignment.END),
            ft.Text("SYSTEM BOOT", size=24, font_family=self.FONT_NAME), ft.Container(height=40),
            mk("LOCAL", ft.Icons.HOME, "#00FF00", self.config["ip_home"]), ft.Container(height=20),
            mk("VPN", ft.Icons.PUBLIC, "#FF0000", self.config["ip_remote"])
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), alignment=ft.alignment.center, expand=True))

    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        # NESSUN KILL_GHOSTS QUI! La musica continua.
        
        header = ft.Container(content=ft.Row([ft.Icon(ft.Icons.STORAGE, color="white"), ft.Text("DATABASE", font_family=self.FONT_NAME)], alignment=ft.MainAxisAlignment.CENTER), bgcolor="#111111", padding=20)
        
        btn = None
        if self.current_song_data:
             btn = ft.FloatingActionButton(
                 icon=ft.Icons.MUSIC_NOTE, bgcolor="white", 
                 content=ft.Icon(ft.Icons.MUSIC_NOTE, color="black"),
                 on_click=lambda _: self.show_player_view()
             )

        self.page.add(ft.Column([header, ft.Container(content=self.songs_column, expand=True)], expand=True))
        self.page.floating_action_button = btn
        if not self.playlist: self.fetch_songs()
        self.page.update()

    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        
        try:
            p = self.get_auth_params()
            p['id'] = self.current_song_data['id']
            p['size'] = 600
            req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=p)
            url = req.prepare().url
        except: url = ""

        img = ft.Image(src=url, width=300, height=300, fit=ft.ImageFit.COVER, error_content=ft.Container(bgcolor="#333"), border_radius=0)
        
        self.btn_play_icon = ft.Icon(ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW, color="white", size=40)
        
        controls = ft.Row([
            ft.Container(content=ft.Text("<<<", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=self.prev_track),
            ft.Container(content=self.btn_play_icon, width=80, height=80, bgcolor="black", border=ft.border.all(3, "white"), border_radius=40, alignment=ft.alignment.center, on_click=self.toggle_play_pause),
            ft.Container(content=ft.Text(">>>", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=self.next_track)
        ], alignment=ft.MainAxisAlignment.CENTER)

        self.page.add(ft.Container(content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.load_library_view(self.base_url))]),
            ft.Container(height=20), ft.Container(content=img, border=ft.border.all(4, "white")),
            ft.Container(height=20), self.debug_label, ft.Container(height=20),
            ft.Text(self.current_song_data['title'], size=20, font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Text(self.current_song_data.get('artist','?'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Container(expand=True), controls, ft.Container(height=50)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20, expand=True))
        self.page.update()

    # --- KILLER GHOSTS (VERSIONE BRUTALE) ---
    def kill_ghosts(self):
        # Rimuove TUTTI gli audio dall'overlay. Punto.
        items_to_remove = []
        for control in self.page.overlay:
            if isinstance(control, flet_audio.Audio):
                try: control.release()
                except: pass
                items_to_remove.append(control)
        
        for item in items_to_remove:
            self.page.overlay.remove(item)
        
        self.page.update()
        self.audio_player = None

    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        # Debounce
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        # KILL GHOSTS QUI: Prima di fare qualsiasi cosa, uccidi tutto.
        self.kill_ghosts()

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False # Aspettiamo il download

        self.show_player_view()
        
        # Download in thread separato
        threading.Thread(target=self._download_and_play, args=(self.current_song_data,), daemon=True).start()

    def _download_and_play(self, song_data):
        try:
            self.debug_label.value = "DOWNLOADING..."
            self.debug_label.color = "yellow"
            self.page.update()

            params = self.get_auth_params()
            params['id'] = song_data['id']
            url = f"{self.base_url}/rest/stream?id={song_data['id']}&format=mp3&maxBitRate=128"
            for k, v in params.items(): url += f"&{k}={v}"

            # PULIZIA VECCHI MP3 (Lascia solo il corrente per non intasare)
            try:
                for f in glob.glob(os.path.join(self.cache_dir, "*.mp3")):
                    try: os.remove(f)
                    except: pass
            except: pass

            filename = f"track_{int(time.time())}.mp3"
            file_path = os.path.join(self.cache_dir, filename)

            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            self._start_playback(file_path)

        except Exception as e:
            self.debug_label.value = "DL ERROR"
            self.debug_label.color = "red"
            self.page.update()

    def _start_playback(self, path):
        # Questo gira nel thread, quindi usiamo try/catch per UI
        try:
            self.debug_label.value = "PLAYING"
            self.debug_label.color = "#00FF00"
            self.is_playing = True
            if hasattr(self, 'btn_play_icon'): self.btn_play_icon.name = ft.Icons.PAUSE
            self.page.update()

            # Creiamo il player NUOVO DI ZECCA
            self.audio_player = flet_audio.Audio(
                src=path,
                autoplay=True,
                volume=1.0,
                on_state_changed=self.on_audio_state
            )
            
            self.page.overlay.append(self.audio_player)
            self.page.update()
        except: pass

    def toggle_play_pause(self, e):
        if not self.audio_player: return
        if self.is_playing:
            self.audio_player.pause()
            self.is_playing = False
            self.btn_play_icon.name = ft.Icons.PLAY_ARROW
        else:
            self.audio_player.resume()
            self.is_playing = True
            self.btn_play_icon.name = ft.Icons.PAUSE
        self.page.update()
        self.audio_player.update()

    def next_track(self, e=None):
        self.play_track_index((self.current_index + 1) % len(self.playlist))

    def prev_track(self, e=None):
        self.play_track_index((self.current_index - 1) % len(self.playlist))
        
    def on_audio_state(self, e):
        if e.data == "completed":
            self.next_track()

    def fetch_songs(self):
        self.songs_column.controls.append(ft.Text("LOADING...", font_family=self.FONT_NAME))
        self.page.update()
        try:
            p = self.get_auth_params()
            p['size'] = 100
            res = requests.get(f"{self.base_url}/rest/getRandomSongs", params=p, timeout=10)
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
        except: self.songs_column.controls.append(ft.Text("ERROR", color="red"))
        self.page.update()

def main(page: ft.Page):
    app = UltimatePlayer(page)
    page.add(ft.Text("BOOT...", font_family="Courier New"))
    time.sleep(0.5)
    page.clean()
    app.safe_boot()

ft.app(target=main)
