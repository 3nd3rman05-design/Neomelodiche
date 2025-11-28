import hashlib
import random
import string
import requests
import flet as ft
import flet_audio 
import time
import os
import shutil

# --- 🔮 IL SIGILLO GLOBALE (SINGLETON) 🔮 ---
# Questa variabile esiste al di fuori della classe. 
# È l'unica entità audio permessa in tutto il programma.
_GLOBAL_AUDIO_PLAYER = None

# --- CONFIGURAZIONE ---
# Percorsi e costanti
CACHE_DIR = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_v3")

class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True 
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.is_playing = False 
        self.last_click_time = 0 
        
        # Stile
        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        
        # Init Cache
        if os.path.exists(CACHE_DIR):
            try: shutil.rmtree(CACHE_DIR)
            except: pass
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Config default
        self.config = {"ip_home": "", "ip_remote": "", "user": "", "pass": ""}

    # --- DIAGNOSTICA AVANZATA (Errori Precisi) ---
    def check_connection(self, url, user, pwd):
        """Interroga il server come fanno i client veri (Ping)"""
        try:
            salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
            token = hashlib.md5((pwd + salt).encode('utf-8')).hexdigest()
            params = {'u': user, 't': token, 's': salt, 'v': '1.16.1', 'c': 'Check', 'f': 'json'}
            
            # Testiamo il ping
            res = requests.get(f"{url}/rest/ping.view", params=params, timeout=5)
            
            if res.status_code == 200:
                data = res.json()
                if 'subsonic-response' in data:
                    resp = data['subsonic-response']
                    if resp['status'] == 'ok':
                        return "OK", None
                    else:
                        # Errore logico (es. versione API vecchia)
                        return "API ERROR", str(resp.get('error', {}).get('message', 'Unknown API Error'))
            
            # Errori HTTP standard
            if res.status_code == 401: return "AUTH FAILED", "Wrong Username or Password"
            if res.status_code == 403: return "FORBIDDEN", "User not allowed"
            if res.status_code == 404: return "NOT FOUND", "Check URL (remove /index.html?)"
            return "HTTP ERROR", f"Code: {res.status_code}"

        except requests.exceptions.ConnectionError:
            return "NET ERROR", "Server unreachable (Check IP/VPN)"
        except requests.exceptions.Timeout:
            return "TIMEOUT", "Server too slow (Check signal)"
        except Exception as e:
            return "CRITICAL", str(e)

    # --- BOOT ---
    def safe_boot(self):
        try:
            if self.page.client_storage.contains_key("navix_cfg"):
                self.config = self.page.client_storage.get("navix_cfg")
                if not self.config.get("ip_home"): self.show_setup_screen()
                else: self.show_selector()
            else:
                self.show_setup_screen()
        except: self.show_setup_screen()

    # --- SETUP SCREEN (Con Diagnostica) ---
    def show_setup_screen(self, error_msg=None):
        self.page.clean()
        style = ft.TextStyle(font_family=self.FONT_NAME)
        
        # Valori precaricati o default
        val_h = self.config.get("ip_home", "http://192.168.1.20:4533")
        val_r = self.config.get("ip_remote", "http://100.")
        val_u = self.config.get("user", "admin")
        
        t_ip_h = ft.TextField(label="HOME IP", value=val_h, text_style=style, border_color="green")
        t_ip_r = ft.TextField(label="REMOTE IP", value=val_r, text_style=style, border_color="red")
        t_u = ft.TextField(label="USER", value=val_u, text_style=style)
        t_p = ft.TextField(label="PASS", password=True, can_reveal_password=True, text_style=style)
        
        lbl_err = ft.Text(error_msg, color="red", weight="bold") if error_msg else ft.Container()

        def try_connect(e):
            # Pulizia stringhe
            home = t_ip_h.value.strip().rstrip("/")
            remote = t_ip_r.value.strip().rstrip("/")
            user = t_u.value.strip()
            pwd = t_p.value.strip()

            if not home or not user:
                lbl_err.value = "FIELDS REQUIRED"
                self.page.update()
                return

            # Testiamo la connessione PRIMA di salvare
            lbl_err.value = "TESTING CONNECTION..."
            lbl_err.color = "yellow"
            self.page.update()

            # Proviamo prima l'IP Home, se fallisce proviamo Remote (se inserito)
            status, msg = self.check_connection(home, user, pwd)
            
            if status != "OK" and remote and "http" in remote:
                 # Se Home fallisce, prova Remote
                 status, msg = self.check_connection(remote, user, pwd)

            if status == "OK":
                self.config = {"ip_home": home, "ip_remote": remote, "user": user, "pass": pwd}
                self.page.client_storage.set("navix_cfg", self.config)
                self.show_selector()
            else:
                lbl_err.value = f"{status}: {msg}"
                lbl_err.color = "red"
                self.page.update()

        self.page.add(ft.Container(content=ft.Column([
            ft.Text("/// SETUP ///", size=24, color="white", font_family=self.FONT_NAME),
            ft.Container(height=20),
            lbl_err,
            t_ip_h, t_ip_r, t_u, t_p,
            ft.ElevatedButton("TEST & SAVE", on_click=try_connect, bgcolor="white", color="black")
        ]), padding=30, alignment=ft.alignment.center, expand=True))

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'FinalApp', 'f': 'json'}

    # --- SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        self.terminate_audio_session() # Uccidi tutto se torni qui
        
        def reset(e): 
            self.page.client_storage.remove("navix_cfg")
            self.show_setup_screen()
        def mk(t, i, c, u):
            return ft.Container(content=ft.Column([ft.Icon(i,40,"black"), ft.Text(t,weight="bold",color="black",font_family=self.FONT_NAME)], alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=c, width=180, height=140, border=ft.border.all(4, "white"), on_click=lambda _: self.load_library_view(u))

        self.page.add(ft.Container(content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=reset)], alignment=ft.MainAxisAlignment.END),
            ft.Text("SYSTEM BOOT", size=24, font_family=self.FONT_NAME), ft.Container(height=40),
            mk("LOCAL", ft.Icons.HOME, "#00FF00", self.config["ip_home"]), ft.Container(height=20),
            mk("VPN", ft.Icons.PUBLIC, "#FF0000", self.config["ip_remote"])
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), alignment=ft.alignment.center, expand=True))

    # --- LISTA ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        
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

    # --- PLAYER VIEW ---
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
            ft.Container(height=20),
            ft.Text(self.current_song_data['title'], size=20, font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Text(self.current_song_data.get('artist','?'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Container(expand=True), controls, ft.Container(height=50)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20, expand=True))
        self.page.update()

    # --- 🛑 GESTIONE AUDIO SINGLETON (NO GHOSTS) 🛑 ---
    def terminate_audio_session(self):
        """Uccide l'unico player globale esistente."""
        global _GLOBAL_AUDIO_PLAYER
        if _GLOBAL_AUDIO_PLAYER:
            try:
                _GLOBAL_AUDIO_PLAYER.release()
                if _GLOBAL_AUDIO_PLAYER in self.page.overlay:
                    self.page.overlay.remove(_GLOBAL_AUDIO_PLAYER)
                self.page.update()
            except: pass
            _GLOBAL_AUDIO_PLAYER = None

    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        # Debounce
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        # 1. STOP & KILL (Brutale ma necessario per i fantasmi)
        self.terminate_audio_session()

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False # Aspettiamo il buffer
        self.show_player_view()
        
        # 2. Avvia download nel thread
        threading.Thread(target=self._download_and_play, args=(self.current_song_data,), daemon=True).start()

    def _download_and_play(self, song_data):
        try:
            params = self.get_auth_params()
            params['id'] = song_data['id']
            # MP3 128k = Compatibilità massima Android
            url = f"{self.base_url}/rest/stream?id={song_data['id']}&format=mp3&maxBitRate=128"
            for k, v in params.items(): url += f"&{k}={v}"

            # Scarica
            file_path = os.path.join(CACHE_DIR, f"{song_data['id']}.mp3")
            
            # Se non esiste, scarica. Se esiste ed è valido, usa.
            if not (os.path.exists(file_path) and os.path.getsize(file_path) > 1000):
                with requests.get(url, stream=True, timeout=15) as r:
                    r.raise_for_status()
                    with open(file_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
            
            # Suona
            self._start_playback(file_path)

        except Exception as e:
            print(f"Play Error: {e}")

    def _start_playback(self, path):
        global _GLOBAL_AUDIO_PLAYER
        try:
            self.is_playing = True
            if hasattr(self, 'btn_play_icon'): self.btn_play_icon.name = ft.Icons.PAUSE
            self.page.update()

            # CREAZIONE DELL'UNICO PLAYER PERMESSO
            _GLOBAL_AUDIO_PLAYER = flet_audio.Audio(
                src=path,
                autoplay=True,
                volume=1.0,
                on_state_changed=self.on_audio_state
            )
            self.page.overlay.append(_GLOBAL_AUDIO_PLAYER)
            self.page.update()
        except: pass

    def toggle_play_pause(self, e):
        global _GLOBAL_AUDIO_PLAYER
        if not _GLOBAL_AUDIO_PLAYER: return
        
        if self.is_playing:
            _GLOBAL_AUDIO_PLAYER.pause()
            self.is_playing = False
            self.btn_play_icon.name = ft.Icons.PLAY_ARROW
        else:
            _GLOBAL_AUDIO_PLAYER.resume()
            self.is_playing = True
            self.btn_play_icon.name = ft.Icons.PAUSE
        self.page.update()
        _GLOBAL_AUDIO_PLAYER.update()

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
