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
        
        # --- IL TUO SISTEMA DI CRONOMETRO ---
        self.track_duration = 0      # Durata totale (da Navidrome)
        self.track_position = 0      # Secondo attuale (contato da noi)
        self.watchdog_running = True # Motore acceso
        
        # Cache
        self.cache_dir = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_buffer")
        self._safe_wipe_cache()

        # Stile
        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        
        # Etichetta che farà da "Barra di Caricamento"
        self.time_label = ft.Text("--:-- / --:--", color="#00FF00", size=14, font_family=self.FONT_NAME, weight="bold")

        self.config = {"ip_home": "", "ip_remote": "", "user": "", "pass": ""}

        # Avvio il Cervello del Timer
        threading.Thread(target=self._manual_timer_loop, daemon=True).start()

    # --- FORMATTAZIONE TEMPO (es. 125s -> 02:05) ---
    def format_time(self, seconds):
        if seconds < 0: return "00:00"
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    # --- IL CRONOMETRO MANUALE (Cuore del sistema) ---
    def _manual_timer_loop(self):
        while self.watchdog_running:
            time.sleep(1) # Aspetta 1 secondo esatto
            
            # Se la musica sta suonando E abbiamo una durata valida
            if self.is_playing and self.track_duration > 0:
                self.track_position += 1
                
                # Calcola progresso
                curr_str = self.format_time(self.track_position)
                tot_str = self.format_time(self.track_duration)
                
                # Aggiorna la scritta a schermo (Thread Safe)
                # Mostra: PLAYING: 01:15 / 03:20
                try:
                    self.time_label.value = f"TIME: {curr_str} / {tot_str}"
                    self.page.update()
                except: pass

                # CONTROLLO FINE CANZONE (+3 secondi di buffer come hai chiesto)
                if self.track_position >= (self.track_duration + 3):
                    print("MANUAL TIMER: Song Finished -> Next")
                    self.track_position = 0 
                    self.track_duration = 0
                    self.next_track_safe()

    def next_track_safe(self):
        try: self.next_track()
        except: pass

    # --- BOOT ---
    def safe_boot(self):
        try:
            if self.page.client_storage.contains_key("navix_cfg"):
                self.config = self.page.client_storage.get("navix_cfg")
                self.show_selector()
            else:
                self.show_setup_screen()
        except: self.show_setup_screen()

    def _safe_wipe_cache(self):
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            return
        try:
            for f in glob.glob(os.path.join(self.cache_dir, "*")):
                try: os.remove(f)
                except: pass
        except: pass

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
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'ChronoClient', 'f': 'json'}

    def show_selector(self):
        self.page.clean()
        # Reset totale quando siamo al menu
        self.is_playing = False 
        self.track_position = 0
        self.kill_ghosts() 
        
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
            ft.Container(height=20), 
            # QUI C'È LA TUA BARRA DI CARICAMENTO TESTUALE
            self.time_label, 
            ft.Container(height=20),
            ft.Text(self.current_song_data['title'], size=20, font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Text(self.current_song_data.get('artist','?'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
            ft.Container(expand=True), controls, ft.Container(height=50)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20, expand=True))
        self.page.update()

    def kill_ghosts(self):
        if self.audio_player:
            try:
                self.audio_player.release()
                if self.audio_player in self.page.overlay:
                    self.page.overlay.remove(self.audio_player)
            except: pass
            self.audio_player = None

    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        self.kill_ghosts() 

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False # Aspettiamo il download
        
        # --- RESETTA IL CRONOMETRO ---
        self.track_position = 0
        try:
            self.track_duration = int(self.current_song_data.get("duration", 180)) # Prende la durata vera!
        except: self.track_duration = 180
        
        self.time_label.value = "LOADING..." # Feedback immediato

        self.show_player_view()
        
        s_id = self.current_song_data['id']
        path = os.path.join(self.cache_dir, f"{s_id}.mp3")
        
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            self._start_playback(path)
            threading.Thread(target=self._preload_next, args=(index,), daemon=True).start()
        else:
            threading.Thread(target=self._download_manager, args=(index,), daemon=True).start()

    def _download_manager(self, index):
        s_id = self.playlist[index]['id']
        path = os.path.join(self.cache_dir, f"{s_id}.mp3")
        
        if self._dl_file(s_id, path):
            self._start_playback(path)
            self._preload_next(index)
        else:
            self.time_label.value = "DL ERROR"
            self.page.update()

    def _preload_next(self, index):
        ids = [self.playlist[index]['id']]
        for i in range(1, 4):
            nxt_idx = (index + i) % len(self.playlist)
            nxt = self.playlist[nxt_idx]
            p = os.path.join(self.cache_dir, f"{nxt['id']}.mp3")
            ids.append(nxt['id'])
            if not os.path.exists(p): self._dl_file(nxt['id'], p)
        self._prune(ids)

    def _dl_file(self, s_id, path):
        try:
            p = self.get_auth_params()
            p['id'] = s_id
            url = f"{self.base_url}/rest/stream?id={s_id}&format=mp3&maxBitRate=128"
            for k, v in p.items(): url += f"&{k}={v}"
            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                with open(path+".tmp", 'wb') as f:
                    for c in r.iter_content(8192): f.write(c)
                os.rename(path+".tmp", path)
            return True
        except: return False

    def _prune(self, ids):
        try:
            for f in glob.glob(os.path.join(self.cache_dir, "*.mp3")):
                if os.path.basename(f).replace(".mp3", "") not in ids:
                    try: os.remove(f)
                    except: pass
        except: pass

    def _start_playback(self, path):
        try:
            self.is_playing = True
            if hasattr(self, 'btn_play_icon'): self.btn_play_icon.name = ft.Icons.PAUSE
            self.page.update()
            
            # NOTA: Rimuoviamo gli eventi on_audio_state perché gestiamo tutto noi col cronometro
            self.audio_player = flet_audio.Audio(src=path, autoplay=True, volume=1.0)
            self.page.overlay.append(self.audio_player)
            self.page.update()
        except: pass

    def toggle_play_pause(self, e):
        if not self.audio_player: return
        if self.is_playing:
            self.audio_player.pause()
            self.is_playing = False # IL CRONOMETRO SI FERMA QUI
            self.btn_play_icon.name = ft.Icons.PLAY_ARROW
        else:
            self.audio_player.resume()
            self.is_playing = True # IL CRONOMETRO RIPARTE QUI
            self.btn_play_icon.name = ft.Icons.PAUSE
        self.page.update()
        self.audio_player.update()

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
