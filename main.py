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

# --- ⚠️ CONFIGURAZIONE ⚠️ ---
IP_CASA = 'http://192.168.1.20:4533'   
IP_REMOTO = 'http://100.96.220.44:4533'    
USERNAME = 'Gino'
PASSWORD = 'XRtKMoaoSroMC1yJ'             
# ----------------------------

class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True # AIUTO EXTRA PER ANDROID
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.audio_player = None 
        self.is_playing = False 
        self.last_click_time = 0 
        
        # CACHE
        self.cache_dir = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_buffer")
        # Nuke on start per pulizia
        if os.path.exists(self.cache_dir):
            try: shutil.rmtree(self.cache_dir)
            except: pass
        os.makedirs(self.cache_dir, exist_ok=True)

        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X FINAL"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.debug_label = ft.Text("SYSTEM READY", color="grey", size=10, font_family=self.FONT_NAME)

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((PASSWORD + salt).encode('utf-8')).hexdigest()
        return {'u': USERNAME, 't': token, 's': salt, 'v': '1.16.1', 'c': 'LockProof', 'f': 'json'}

    # --- SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        def make_btn(text, icon, color, url):
            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=40, color="black"),
                    ft.Text(text, weight="bold", color="black", font_family=self.FONT_NAME)
                ], alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=color,
                width=180, height=140,
                border=ft.border.all(4, "white"),
                on_click=lambda _: self.load_library_view(url)
            )

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Text("/// SYSTEM BOOT ///", color="white", size=24, font_family=self.FONT_NAME),
                    ft.Container(height=40),
                    make_btn("LOCAL NETWORK", ft.Icons.HOME, "#00FF00", IP_CASA),
                    ft.Container(height=20),
                    make_btn("SECURE VPN", ft.Icons.PUBLIC, "#FF0000", IP_REMOTO)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                alignment=ft.alignment.center,
                expand=True
            )
        )

    # --- LISTA ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        # NOTA: Qui NON chiamiamo cleanup_audio(). La musica deve continuare.

        header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.STORAGE, color="white", size=20),
                ft.Text("DATABASE", color="white", font_family=self.FONT_NAME, size=16, weight="bold")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#111111", padding=20,
            border=ft.border.only(bottom=ft.border.BorderSide(2, "white"))
        )

        floating_btn = None
        if self.current_song_data:
             floating_btn = ft.FloatingActionButton(
                 icon=ft.Icons.MUSIC_NOTE, bgcolor="white", 
                 content=ft.Icon(ft.Icons.MUSIC_NOTE, color="black"),
                 on_click=lambda _: self.show_player_view()
             )

        self.page.add(
            ft.Column([header, ft.Container(content=self.songs_column, expand=True)], expand=True)
        )
        self.page.floating_action_button = floating_btn
        if not self.playlist: self.fetch_songs()
        self.page.update()

    # --- PLAYER ---
    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        song = self.current_song_data
        
        params = self.get_auth_params()
        params['id'] = song['id']
        params['size'] = 600
        cover_req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=params)
        cover_url = cover_req.prepare().url

        fallback_image = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.FACE, size=100, color="white"), 
                ft.Text("NO DATA", font_family=self.FONT_NAME, color="grey")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#222222", alignment=ft.alignment.center, border=ft.border.all(2, "white")
        )

        album_art = ft.Image(
            src=cover_url, width=300, height=300, fit=ft.ImageFit.COVER,
            error_content=fallback_image, border_radius=0, 
        )

        btn_prev = ft.Container(
            content=ft.Text("<<<", color="white", size=24, weight="bold", font_family=self.FONT_NAME),
            padding=20, on_click=self.prev_track, ink=True
        )

        btn_next = ft.Container(
            content=ft.Text(">>>", color="white", size=24, weight="bold", font_family=self.FONT_NAME),
            padding=20, on_click=self.next_track, ink=True
        )

        # FIX BUG 1: L'icona DEVE riflettere lo stato reale
        play_icon = ft.Icons.PAUSE if self.is_playing else ft.Icons.PLAY_ARROW
        self.btn_play_content = ft.Icon(play_icon, color="white", size=40)
        
        btn_play = ft.Container(
            content=self.btn_play_content,
            width=80, height=80, bgcolor="black",
            border=ft.border.all(3, "white"), border_radius=40,
            alignment=ft.alignment.center,
            on_click=self.toggle_play_pause, ink=True
        )

        controls = ft.Row([btn_prev, btn_play, btn_next], alignment=ft.MainAxisAlignment.CENTER, spacing=30)
        back_btn = ft.IconButton(ft.Icons.ARROW_BACK, icon_color="white", on_click=lambda _: self.load_library_view(self.base_url))

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Row([back_btn], alignment=ft.MainAxisAlignment.START),
                    ft.Container(height=20),
                    ft.Container(content=album_art, border=ft.border.all(4, "white"), padding=0),
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

    # --- LOGICA PLAYBACK BLINDATA ---
    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        # Debounce
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        self.cleanup_audio() 

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = False # Reset stato

        self.show_player_view()
        
        s_id = self.current_song_data['id']
        file_path = os.path.join(self.cache_dir, f"{s_id}.mp3")

        # FIX BUG 2 (LOCK SCREEN):
        # Se il file esiste, lo suoniamo DIRETTAMENTE nel main thread.
        # Android non blocca il main thread per operazioni locali veloci.
        # Creare un Thread separato (come prima) veniva bloccato da Android a schermo spento.
        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
            print("FAST PATH: Playing local file")
            self._start_playback(file_path, "PLAYING (INSTANT)")
            # Avviamo il preload della prossima canzone in background (se fallisce amen, ma la corrente suona)
            threading.Thread(target=self._preload_next, args=(index,), daemon=True).start()
        else:
            # Se non c'è, dobbiamo scaricarlo. Qui usiamo il thread ma speriamo lo schermo sia acceso.
            threading.Thread(target=self._download_and_play_manager, args=(index,), daemon=True).start()

    def _download_and_play_manager(self, index):
        song_data = self.playlist[index]
        s_id = song_data['id']
        file_path = os.path.join(self.cache_dir, f"{s_id}.mp3")
        
        self.debug_label.value = "DOWNLOADING..."
        self.debug_label.color = "yellow"
        self.page.update()
        
        if self._download_file(s_id, file_path):
            self._start_playback(file_path, "PLAYING (FETCHED)")
            self._preload_next(index)
        else:
            self.debug_label.value = "DOWNLOAD FAILED"
            self.page.update()

    def _preload_next(self, index):
        # Scarica le prossime 3 canzoni e pulisce il resto
        ids_to_keep = [self.playlist[index]['id']]
        for i in range(1, 4):
            next_idx = (index + i) % len(self.playlist)
            next_data = self.playlist[next_idx]
            next_path = os.path.join(self.cache_dir, f"{next_data['id']}.mp3")
            ids_to_keep.append(next_data['id'])
            
            if not os.path.exists(next_path):
                print(f"Preloading: {next_data['title']}")
                self._download_file(next_data['id'], next_path)
        
        self._prune_cache(ids_to_keep)

    def _download_file(self, s_id, path):
        try:
            params = self.get_auth_params()
            params['id'] = s_id
            url = f"{self.base_url}/rest/stream?id={s_id}&format=mp3&maxBitRate=128"
            for k, v in params.items(): url += f"&{k}={v}"

            with requests.get(url, stream=True, timeout=15) as r:
                r.raise_for_status()
                temp_path = path + ".tmp"
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                os.rename(temp_path, path)
            return True
        except Exception as e:
            return False

    def _prune_cache(self, keep_ids):
        try:
            files = glob.glob(os.path.join(self.cache_dir, "*.mp3"))
            for f in files:
                fname = os.path.basename(f).replace(".mp3", "")
                if fname not in keep_ids:
                    try: os.remove(f)
                    except: pass
        except: pass

    def _start_playback(self, path, status_msg):
        # Questa funzione viene chiamata anche dai thread, quindi usiamo try/catch per UI
        try:
            self.debug_label.value = status_msg
            self.debug_label.color = "#00FF00"
            self.is_playing = True
            if hasattr(self, 'btn_play_content'):
                self.btn_play_content.name = ft.Icons.PAUSE
            self.page.update()

            self.audio_player = flet_audio.Audio(
                src=path,
                autoplay=True,
                volume=1.0,
                on_state_changed=self.on_audio_state,
                on_position_changed=self.on_audio_position
            )
            self.page.overlay.append(self.audio_player)
            self.page.update()
        except Exception as e:
            print(f"Playback Error: {e}")

    def on_audio_position(self, e):
        sec = int(int(e.data) / 1000)
        # Aggiorniamo la UI solo ogni secondo per non intasare
        self.debug_label.value = f"PLAYING: {sec}s"
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
        new_index = (self.current_index + 1) % len(self.playlist)
        self.play_track_index(new_index)

    def prev_track(self, e=None):
        new_index = (self.current_index - 1) % len(self.playlist)
        self.play_track_index(new_index)
        
    def on_audio_state(self, e):
        if e.data == "completed":
            # Quando finisce, chiama la prossima.
            # Poiché abbiamo il preload, play_track_index userà il "Fast Path" 
            # e partirà anche se lo schermo è spento.
            self.next_track()

    def fetch_songs(self):
        self.songs_column.controls.append(ft.Text("LOADING...", color="white", font_family=self.FONT_NAME))
        self.page.update()
        try:
            params = self.get_auth_params()
            params['size'] = 100
            res = requests.get(f"{self.base_url}/rest/getRandomSongs", params=params, timeout=10)
            data = res.json()
            self.songs_column.controls.clear()
            self.playlist = []
            if 'randomSongs' in data['subsonic-response']:
                songs = data['subsonic-response']['randomSongs']['song']
                for idx, s in enumerate(songs):
                    self.playlist.append(s)
                    row = ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.MUSIC_NOTE, color="white"),
                            ft.Column([
                                ft.Text(s['title'], color="white", weight="bold", font_family=self.FONT_NAME, no_wrap=True),
                                ft.Text(s.get('artist', 'Unknown'), color="grey", size=12, font_family=self.FONT_NAME)
                            ], expand=True)
                        ]),
                        padding=15,
                        bgcolor="#000000" if idx % 2 == 0 else "#111111",
                        border=ft.border.only(bottom=ft.border.BorderSide(1, "#333333")),
                        on_click=lambda e, i=idx: self.play_track_index(i)
                    )
                    self.songs_column.controls.append(row)
            else: self.songs_column.controls.append(ft.Text("NO SONGS", color="red"))
        except Exception: self.songs_column.controls.append(ft.Text("ERROR", color="red"))
        self.page.update()

def main(page: ft.Page):
    app = UltimatePlayer(page)
    app.show_selector()

ft.app(target=main)
