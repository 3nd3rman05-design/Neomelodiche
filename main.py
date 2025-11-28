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

# --- 🎵 GESTIONE AUDIO GLOBALE (SINGLETON) ---
# Questa variabile è l'unica autorità audio dell'app.
_GLOBAL_PLAYER = None

def kill_global_audio(page):
    """Termina brutalmente qualsiasi audio attivo."""
    global _GLOBAL_PLAYER
    if _GLOBAL_PLAYER:
        try:
            _GLOBAL_PLAYER.release()
            if _GLOBAL_PLAYER in page.overlay:
                page.overlay.remove(_GLOBAL_PLAYER)
            page.update()
        except: pass
        _GLOBAL_PLAYER = None

# --- CONFIGURAZIONE ---
CACHE_DIR = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_v4")

class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True 
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.is_playing = False 
        
        # Stile
        self.COLOR_BG = "#000000"       
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        # Setup Cache
        if os.path.exists(CACHE_DIR):
            try: shutil.rmtree(CACHE_DIR)
            except: pass
        os.makedirs(CACHE_DIR, exist_ok=True)

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.config = {"ip_home": "", "ip_remote": "", "user": "", "pass": ""}

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

    # --- HELPER UTILI ---
    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'FinalFix', 'f': 'json'}

    # --- 1. SETUP ---
    def show_setup_screen(self, error=None):
        self.page.clean()
        st = ft.TextStyle(font_family=self.FONT_NAME)
        
        # Pre-fill
        h = self.config.get("ip_home", "http://192.168.1.20:4533")
        r = self.config.get("ip_remote", "http://100.")
        u = self.config.get("user", "admin")
        
        t_h = ft.TextField(label="HOME IP", value=h, text_style=st, border_color="green")
        t_r = ft.TextField(label="REMOTE IP", value=r, text_style=st, border_color="red")
        t_u = ft.TextField(label="USER", value=u, text_style=st)
        t_p = ft.TextField(label="PASS", password=True, can_reveal_password=True, text_style=st)
        err_lbl = ft.Text(error if error else "", color="red")

        def save(e):
            # Test veloce connessione
            try:
                base = t_h.value.strip().rstrip("/")
                test_p = {'u': t_u.value, 'p': t_p.value, 'v': '1.16.1', 'c': 'Test', 'f': 'json'}
                # Non usiamo requests qui per non bloccare, salviamo e basta. 
                # L'errore apparirà dopo se non va.
                self.config = {
                    "ip_home": base,
                    "ip_remote": t_r.value.strip().rstrip("/"),
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
            padding=ft.padding.only(top=50, left=30, right=30), # Padding alto
            alignment=ft.alignment.center, expand=True
        ))

    # --- 2. SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        kill_global_audio(self.page) # Stop musica se torni qui
        
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
            padding=ft.padding.only(top=50), # Padding alto per il notch
            alignment=ft.alignment.center, expand=True
        ))

    # --- 3. LISTA ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        
        # Header con margine alto per il "2mm" request
        header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.STORAGE, color="white"), 
                ft.Text("DATABASE", font_family=self.FONT_NAME, size=20, weight="bold")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#111111", 
            # ⚠️ QUI ABBIAMO ABBASSATO L'INTERFACCIA (50px = ~2-3mm + notch)
            padding=ft.padding.only(top=50, bottom=20, left=20, right=20), 
            border=ft.border.only(bottom=ft.border.BorderSide(2, "white"))
        )
        
        # Bottone "Now Playing" se c'è musica
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

    # --- 4. PLAYER ---
    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        
        # Cover
        try:
            p = self.get_auth_params()
            p['id'] = self.current_song_data['id']
            p['size'] = 600
            req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=p)
            cover_url = req.prepare().url
        except: cover_url = ""

        img = ft.Image(src=cover_url, width=300, height=300, fit=ft.ImageFit.COVER, error_content=ft.Container(bgcolor="#333"), border_radius=0)
        
        self.btn_play_icon = ft.Icon(ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW, color="white", size=40)
        
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
                    ft.Text(self.current_song_data['title'], size=20, font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Text(self.current_song_data.get('artist','?'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Container(expand=True), 
                    controls, 
                    ft.Container(height=50)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                # ⚠️ ANCHE QUI PADDING ALTO PER IL PLAYER
                padding=ft.padding.only(top=50, left=20, right=20, bottom=20), 
                expand=True, bgcolor="black"
            )
        )
        self.page.update()

    # --- LOGICA PLAYBACK (Thread Safe + Singleton) ---
    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        # Kill immediato del vecchio audio
        kill_global_audio(self.page)

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False # Aspettiamo il download
        self.show_player_view() # Mostra subito la grafica
        
        # Avvia download e play in background
        threading.Thread(target=self._download_and_play, args=(self.current_song_data,), daemon=True).start()

    def _download_and_play(self, song_data):
        try:
            # 1. DOWNLOAD
            p = self.get_auth_params()
            p['id'] = song_data['id']
            # Forziamo MP3 128k (massima compatibilità)
            url = f"{self.base_url}/rest/stream?id={song_data['id']}&format=mp3&maxBitRate=128"
            for k, v in p.items(): url += f"&{k}={v}"

            # File locale univoco per evitare conflitti
            filename = f"current_{int(time.time())}.mp3"
            path = os.path.join(CACHE_DIR, filename)

            # Scarica
            with requests.get(url, stream=True, timeout=10) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(32768):
                        if chunk: f.write(chunk)
            
            # 2. PLAY (Thread Safe Call)
            self._start_playback_safe(path)

        except Exception as e:
            print(f"DL Error: {e}")

    def _start_playback_safe(self, path):
        # Poiché siamo in un thread, non possiamo toccare la UI direttamente se non siamo attenti.
        # Ma Flet gestisce bene gli aggiornamenti se passiamo per page.update()
        global _GLOBAL_PLAYER
        try:
            self.is_playing = True
            
            # Creiamo il player
            _GLOBAL_PLAYER = flet_audio.Audio(
                src=path,
                autoplay=True,
                volume=1.0,
                on_state_changed=self.on_audio_state
            )
            
            # Lo iniettiamo nella pagina
            self.page.overlay.append(_GLOBAL_PLAYER)
            
            # Aggiorniamo icona e pagina
            if hasattr(self, 'btn_play_icon'): 
                self.btn_play_icon.name = ft.Icons.PAUSE
            self.page.update()
            
        except Exception as e:
            print(f"Playback Error: {e}")

    def toggle_play_pause(self, e):
        global _GLOBAL_PLAYER
        if not _GLOBAL_PLAYER: return
        
        if self.is_playing:
            _GLOBAL_PLAYER.pause()
            self.is_playing = False
            self.btn_play_icon.name = ft.Icons.PLAY_ARROW
        else:
            _GLOBAL_PLAYER.resume()
            self.is_playing = True
            self.btn_play_icon.name = ft.Icons.PAUSE
        
        self.page.update()
        _GLOBAL_PLAYER.update()

    def next_track(self, e=None):
        self.play_track_index((self.current_index + 1) % len(self.playlist))

    def prev_track(self, e=None):
        self.play_track_index((self.current_index - 1) % len(self.playlist))
        
    def on_audio_state(self, e):
        if e.data == "completed":
            self.next_track()

    # --- FETCH DATA ---
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
