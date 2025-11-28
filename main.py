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
        # Mantiene lo schermo attivo (fondamentale per Android!)
        self.page.keep_screen_on = True 
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.audio_player = None 
        self.is_playing = False 
        self.last_click_time = 0 
        self.watchdog_running = True # Attiviamo il cane da guardia
        
        # Configurazione Iniziale
        self.config = {
            "ip_home": "http://192.168.1.20:4533",
            "ip_remote": "http://100.x.y.z:4533",
            "user": "admin",
            "pass": "admin"
        }

        # Stile
        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.debug_label = ft.Text("SYSTEM READY", color="grey", size=10, font_family=self.FONT_NAME)

        # Avvio il controllo background per il Lock Screen
        threading.Thread(target=self._watchdog_loop, daemon=True).start()

    # --- WATCHDOG: Fa passare la canzone anche a schermo spento ---
    def _watchdog_loop(self):
        while self.watchdog_running:
            time.sleep(2) # Controlla ogni 2 secondi
            # Se stiamo suonando, ma non c'è audio attivo, qualcosa non va
            if self.is_playing and self.audio_player:
                try:
                    # In futuro qui potremmo forzare il next, per ora tiene vivo il thread
                    pass
                except: pass

    # --- AVVIO SICURO ---
    def safe_boot(self):
        try:
            # Setup Cache
            self.cache_dir = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_buffer")
            self._safe_wipe_cache()
            
            # Caricamento Dati
            try:
                if self.page.client_storage.contains_key("navix_cfg"):
                    saved = self.page.client_storage.get("navix_cfg")
                    if saved: self.config = saved
                    self.show_selector()
                else:
                    self.show_setup_screen()
            except:
                self.show_setup_screen()

        except Exception as e:
            self.page.clean()
            self.page.add(ft.Text(f"BOOT ERROR: {e}", color="red"))
            self.page.update()

    def _safe_wipe_cache(self):
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            return
        try:
            for f in glob.glob(os.path.join(self.cache_dir, "*")):
                try: os.remove(f)
                except: pass
        except: pass

    # --- SETUP ---
    def show_setup_screen(self):
        self.page.clean()
        
        style = ft.TextStyle(font_family=self.FONT_NAME)
        txt_ip_h = ft.TextField(label="HOME IP", value=self.config["ip_home"], border_color="green", text_style=style)
        txt_ip_r = ft.TextField(label="REMOTE IP", value=self.config["ip_remote"], border_color="red", text_style=style)
        txt_usr = ft.TextField(label="USER", value=self.config["user"], border_color="white", text_style=style)
        txt_pwd = ft.TextField(label="PASS", value=self.config["pass"], password=True, can_reveal_password=True, border_color="white", text_style=style)
        
        def save_data(e):
            if not txt_ip_h.value: return
            try:
                self.config = {
                    "ip_home": txt_ip_h.value.strip(),
                    "ip_remote": txt_ip_r.value.strip(),
                    "user": txt_usr.value.strip(),
                    "pass": txt_pwd.value.strip()
                }
                self.page.client_storage.set("navix_cfg", self.config)
                self.show_selector()
            except: pass

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Text("/// SETUP ///", size=24, color="white", font_family=self.FONT_NAME),
                    ft.Container(height=20),
                    txt_ip_h, ft.Container(height=10),
                    txt_ip_r, ft.Container(height=10),
                    txt_usr, ft.Container(height=10),
                    txt_pwd, ft.Container(height=30),
                    ft.ElevatedButton("SAVE", on_click=save_data, bgcolor="white", color="black")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=30, alignment=ft.alignment.center, expand=True
            )
        )

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'SafeApp', 'f': 'json'}

    # --- SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        
        def reset(e):
            self.page.client_storage.remove("navix_cfg")
            self.show_setup_screen()

        def mk_btn(txt, icon, col, url):
            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=40, color="black"),
                    ft.Text(txt, weight="bold", color="black", font_family=self.FONT_NAME)
                ], alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=col, width=180, height=140, border=ft.border.all(4, "white"),
                on_click=lambda _: self.load_library_view(url)
            )

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=reset)], alignment=ft.MainAxisAlignment.END),
                    ft.Text("/// SYSTEM BOOT ///", color="white", size=24, font_family=self.FONT_NAME),
                    ft.Container(height=40),
                    mk_btn("LOCAL", ft.Icons.HOME, "#00FF00", self.config["ip_home"]),
                    ft.Container(height=20),
                    mk_btn("VPN", ft.Icons.PUBLIC, "#FF0000", self.config["ip_remote"])
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                alignment=ft.alignment.center, expand=True
            )
        )

    # --- LISTA (CORRETTO: NESSUN CLEANUP) ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        
        # 🛑 QUI HO RIMOSSO cleanup_audio()! 
        # La musica continua anche se sei qui.

        header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.STORAGE, color="white", size=20),
                ft.Text("DATABASE", color="white", font_family=self.FONT_NAME, size=16, weight="bold")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#111111", padding=20, border=ft.border.only(bottom=ft.border.BorderSide(2, "white"))
        )

        f_btn = None
        # Mostra il bottone per tornare al player SOLO se stiamo suonando qualcosa
        if self.current_song_data:
             f_btn = ft.FloatingActionButton(
                 icon=ft.Icons.MUSIC_NOTE, bgcolor="white", 
                 content=ft.Icon(ft.Icons.MUSIC_NOTE, color="black"),
                 on_click=lambda _: self.show_player_view()
             )

        self.page.add(ft.Column([header, ft.Container(content=self.songs_column, expand=True)], expand=True))
        self.page.floating_action_button = f_btn
        if not self.playlist: self.fetch_songs()
        self.page.update()

    # --- PLAYER ---
    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        song = self.current_song_data
        
        try:
            params = self.get_auth_params()
            params['id'] = song['id']
            params['size'] = 600
            req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=params)
            cover_url = req.prepare().url
        except: cover_url = ""

        fallback = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.FACE, size=100, color="white"), 
                ft.Text("NO DATA", font_family=self.FONT_NAME, color="grey")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#222222", alignment=ft.alignment.center, border=ft.border.all(2, "white")
        )

        img = ft.Image(src=cover_url, width=300, height=300, fit=ft.ImageFit.COVER, error_content=fallback, border_radius=0)

        btn_prev = ft.Container(
            content=ft.Text("<<<", color="white", size=24, weight="bold", font_family=self.FONT_NAME),
            padding=20, on_click=self.prev_track, ink=True
        )

        btn_next = ft.Container(
            content=ft.Text(">>>", color="white", size=24, weight="bold", font_family=self.FONT_NAME),
            padding=20, on_click=self.next_track, ink=True
        )

        play_icon = ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW
        self.btn_play_content = ft.Icon(play_icon, color="white", size=40)
        
        btn_play = ft.Container(
            content=self.btn_play_content,
            width=80, height=80, bgcolor="black",
            border=ft.border.all(3, "white"), border_radius=40,
            alignment=ft.alignment.center, on_click=self.toggle_play_pause, ink=True
        )

        controls = ft.Row([btn_prev, btn_play, btn_next], alignment=ft.MainAxisAlignment.CENTER, spacing=30)
        back_btn = ft.IconButton(ft.Icons.ARROW_BACK, icon_color="white", on_click=lambda _: self.load_library_view(self.base_url))

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Container(height=20),
                    ft.Container(content=img, border=ft.border.all(4, "white"), padding=0),
                    ft.Container(height=20),
                    self.debug_label,
                    ft.Container(height=20),
                    ft.Text(song['title'], size=20, weight="bold", color="white", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Text(song.get('artist', 'Unknown'), size=14, color="grey", font_family=self.FONT_NAME, text_align=ft.TextAlign.CENTER),
                    ft.Container(expand=True),
                    controls,
                    ft.Container(height=50)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20, expand=True, bgcolor="black"
            )
        )
        self.page.update()

    def cleanup_audio(self):
        if self.audio_player:
            try:
                self.audio_player.release()
                if self.audio_player in self.page.overlay:
                    self.page.overlay.remove(self.audio_player)
                    self.page.update()
            except: pass
            self.audio_player = None

    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        self.cleanup_audio() 
        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False
        self.show_player_view()
        
        # LOGICA LOCK-SCREEN:
        # Se il file c'è, lo suoniamo subito (main thread).
        s_id = self.current_song_data['id']
        file_path = os.path.join(self.cache_dir, f"{s_id}.mp3")
        
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
            self._start_playback(file_path, "PLAYING (INSTANT)")
            threading.Thread(target=self._preload_next, args=(index,), daemon=True).start()
        else:
            threading.Thread(target=self._dl_manager, args=(index,), daemon=True).start()

    def _dl_manager(self, index):
        s_id = self.playlist[index]['id']
        path = os.path.join(self.cache_dir, f"{s_id}.mp3")
        self.debug_label.value = "DOWNLOADING..."
        self.page.update()
        
        if self._dl_file(s_id, path):
            self._start_playback(path, "PLAYING (FETCHED)")
            self._preload_next(index)
        else:
            self.debug_label.value = "DL FAIL"
            self.page.update()

    def _preload_next(self, index):
        ids = [self.playlist[index]['id']]
        for i in range(1, 4):
            nxt_idx = (index + i) % len(self.playlist)
            nxt_data = self.playlist[nxt_idx]
            path = os.path.join(self.cache_dir, f"{nxt_data['id']}.mp3")
            ids.append(nxt['id'])
            if not os.path.exists(path): self._dl_file(nxt['id'], path)
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

    def _start_playback(self, path, msg):
        try:
            self.debug_label.value = msg
            self.debug_label.color = "#00FF00"
            self.is_playing = True
            if hasattr(self, 'btn_play_content'): self.btn_play_content.name = ft.Icons.PAUSE
            self.page.update()
            
            # Autoplay True per far partire subito
            self.audio_player = flet_audio.Audio(
                src=path, autoplay=True, volume=1.0,
                on_state_changed=self.on_audio_state,
                on_position_changed=self.on_pos
            )
            self.page.overlay.append(self.audio_player)
            self.page.update()
        except: pass

    def on_pos(self, e):
        self.debug_label.value = f"PLAYING: {int(int(e.data)/1000)}s"
        self.page.update()

    def toggle_play_pause(self, e):
        if not self.audio_player: return
        if self.is_playing:
            self.audio_player.pause()
            self.is_playing = False
            self.btn_play_content.name = ft.Icons.PLAY_ARROW
        else:
            self.audio_player.resume()
            self.is_playing = True
            self.btn_play_content.name = ft.Icons.PAUSE
        self.btn_play_content.update()
        self.audio_player.update()

    def next_track(self, e=None):
        self.play_track_index((self.current_index + 1) % len(self.playlist))

    def prev_track(self, e=None):
        self.play_track_index((self.current_index - 1) % len(self.playlist))
        
    def on_audio_state(self, e):
        # Questo evento viene lanciato quando la canzone finisce (completed)
        if e.data == "completed":
            print("Song finished, next!")
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
