import hashlib
import random
import string
import requests
import flet as ft
import flet_audio 
import time
import threading
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn # <--- L'ARMA SEGRETA
from urllib.parse import urlparse, parse_qs

# --- ⚠️ CONFIGURAZIONE ⚠️ ---
IP_CASA = 'http://192.168.1.20:4533'   
IP_REMOTO = 'http://100.96.220.44:4533'    
USERNAME = 'Gino'
PASSWORD = 'XRtKMoaoSroMC1yJ'             
# ----------------------------

# --- 🛡️ PROXY MULTI-THREAD (Non si blocca mai) ---
PROXY_PORT = 54321

# Questa classe magica permette di gestire più richieste insieme
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class StreamProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return # Zitto nei log

    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            query = parse_qs(parsed_path.query)
            
            if 'q' not in query:
                self.send_error(400, "No Data")
                return
            
            b64_url = query['q'][0]
            real_url = base64.b64decode(b64_url).decode('utf-8')
            
            # Scarichiamo con stream=True
            with requests.get(real_url, stream=True, timeout=10) as r:
                if r.status_code == 200:
                    self.send_response(200)
                    for key, value in r.headers.items():
                        if key.lower() in ['content-type', 'content-length', 'accept-ranges']:
                            self.send_header(key, value)
                    self.end_headers()
                    
                    # Inviamo i dati a pacchetti
                    for chunk in r.iter_content(chunk_size=32768):
                        if chunk:
                            try:
                                self.wfile.write(chunk)
                            except BrokenPipeError:
                                break # Il telefono ha chiuso la connessione, usciamo
                else:
                    self.send_error(r.status_code, "Remote Error")
                        
        except Exception as e:
            pass

def start_proxy_server():
    try:
        # Usiamo il server Threaded invece di quello base
        server = ThreadedHTTPServer(('127.0.0.1', PROXY_PORT), StreamProxyHandler)
        print(f"PROXY STARTED ON {PROXY_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"PROXY ERROR: {e}")

threading.Thread(target=start_proxy_server, daemon=True).start()
# --- FINE HACK ---


class UltimatePlayer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.base_url = ""
        self.playlist = []
        self.current_song_data = None
        self.current_index = -1
        self.audio_player = None 
        self.is_playing = False 
        self.last_click_time = 0 

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
        return {'u': USERNAME, 't': token, 's': salt, 'v': '1.16.1', 'c': 'ThreadClient', 'f': 'json'}

    # --- 1. SELEZIONE ---
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

    # --- 2. LISTA ---
    def load_library_view(self, url):
        self.base_url = url
        self.page.clean()
        self.cleanup_audio() 

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

    # --- 3. PLAYER ---
    def show_player_view(self):
        self.page.clean()
        self.page.floating_action_button = None 
        if not self.current_song_data: return
        song = self.current_song_data
        
        # Cover
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

    def play_track_index(self, index):
        if index < 0 or index >= len(self.playlist): return
        
        if time.time() - self.last_click_time < 0.5: return 
        self.last_click_time = time.time()

        self.cleanup_audio() 

        self.current_index = index
        self.current_song_data = self.playlist[index]
        self.is_playing = True

        params = self.get_auth_params()
        params['id'] = self.current_song_data['id']
        real_url = f"{self.base_url}/rest/stream?id={self.current_song_data['id']}&format=mp3&maxBitRate=192"
        for k, v in params.items(): real_url += f"&{k}={v}"

        b64_url = base64.b64encode(real_url.encode('utf-8')).decode('utf-8')
        proxy_url = f"http://127.0.0.1:{PROXY_PORT}/stream.mp3?q={b64_url}"

        self.debug_label.value = "BUFFERING (SECURE THREAD)..."
        self.page.update()

        self.audio_player = flet_audio.Audio(
            src=proxy_url,
            autoplay=True,
            volume=1.0,
            on_state_changed=self.on_audio_state,
            on_position_changed=self.on_audio_position,
            on_loaded=lambda _: self.on_loaded_ok()
        )
        
        self.page.overlay.append(self.audio_player)
        self.page.update()
        self.show_player_view()

    def on_loaded_ok(self):
        self.debug_label.value = "PLAYING (PROXY OK)"
        self.debug_label.color = "#00FF00"
        self.page.update()

    def on_audio_position(self, e):
        sec = int(int(e.data) / 1000)
        self.debug_label.value = f"PLAYING: {sec}s"
        self.page.update()

    def toggle_play_pause(self, e):
        if time.time() - self.last_click_time < 0.3: return 
        self.last_click_time = time.time()
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
