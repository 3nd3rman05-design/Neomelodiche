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

# --- CONFIGURAZIONE ---
CACHE_DIR = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_v35_final")

# --- AUDIO MANAGER (SINGLETON) ---
class AudioManager:
    def __init__(self):
        # Inizializza con dummy per evitare errori di Flet
        self.audio_control = flet_audio.Audio(
            src="https://raw.githubusercontent.com/flet-dev/examples/master/python/apps/flet-audio/assets/flet_audio.mp3",
            autoplay=False,
            volume=1.0,
            on_state_changed=self._on_state_changed
        )
        self.is_playing = False
        self.current_request_id = 0
        self.ui_callback = None
        
        # Pulizia cache all'avvio
        if os.path.exists(CACHE_DIR):
            try: shutil.rmtree(CACHE_DIR)
            except: pass
        os.makedirs(CACHE_DIR, exist_ok=True)

    def attach_to_page(self, page):
        # Aggiunge l'audio all'overlay se non c'è
        if self.audio_control not in page.overlay:
            page.overlay.append(self.audio_control)
            page.update()

    def stop(self):
        # Ferma tutto (usato solo quando si cambia server/logout)
        self.current_request_id += 1
        self.is_playing = False
        self.audio_control.pause()
        self.audio_control.update()

    def play_track(self, song_data, auth_params, base_url):
        # 1. Invalida richieste precedenti
        self.current_request_id += 1
        my_id = self.current_request_id
        
        # 2. Pausa momentanea
        self.is_playing = False
        self.audio_control.pause()
        self.audio_control.update()
        
        # 3. Avvia download in background
        threading.Thread(
            target=self._download_task,
            args=(song_data, auth_params, base_url, my_id),
            daemon=True
        ).start()

    def _download_task(self, song, params, base_url, req_id):
        try:
            if req_id != self.current_request_id: return

            p = params.copy()
            p["id"] = song["id"]
            # MP3 128k per velocità
            url = f"{base_url}/rest/stream?id={song['id']}&format=mp3&maxBitRate=128"
            for k, v in p.items(): url += f"&{k}={v}"

            path = os.path.join(CACHE_DIR, f"{song['id']}.mp3")

            # Scarica solo se non esiste
            if not (os.path.exists(path) and os.path.getsize(path) > 1000):
                with requests.get(url, stream=True, timeout=15) as r:
                    r.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in r.iter_content(32768):
                            if req_id != self.current_request_id: return
                            if chunk: f.write(chunk)
            
            # Controllo finale
            if req_id != self.current_request_id: return

            # Play
            self.audio_control.src = path
            self.audio_control.update()
            time.sleep(0.1)
            self.audio_control.resume()
            self.is_playing = True
            
            if self.ui_callback: self.ui_callback("PLAYING")

        except Exception as e:
            if self.ui_callback and req_id == self.current_request_id:
                self.ui_callback("ERROR")

    def toggle(self):
        if self.is_playing:
            self.audio_control.pause()
            self.is_playing = False
        else:
            self.audio_control.resume()
            self.is_playing = True
        self.audio_control.update()
        if self.ui_callback: self.ui_callback("TOGGLE")

    def _on_state_changed(self, e):
        if e.data == "completed" and self.ui_callback:
            self.ui_callback("NEXT")


# Creazione Istanza Globale
AUDIO_MGR = AudioManager()


# --- INTERFACCIA UTENTE ---
class NavixUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.keep_screen_on = True
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = "#000000"
        self.page.padding = 0
        self.FONT_NAME = "Courier New"
        
        AUDIO_MGR.attach_to_page(page)
        AUDIO_MGR.ui_callback = self.on_audio_update

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.base_url = ""
        self.playlist = []
        self.current_song_idx = -1
        self.current_song_data = None
        self.config = {}
        
        # Liste download
        self.downloads_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        
        # UI Elements
        self.track_duration = 0
        self.track_pos = 0
        self.timer_running = True
        self.time_label = ft.Text("--:--", color="green", font_family=self.FONT_NAME)
        self.btn_play_icon = ft.Icon(ft.Icons.PLAY_ARROW, color="white", size=40)
        
        # --- POPUP DOWNLOAD ---
        self.txt_link_input = ft.TextField(
            multiline=True, min_lines=1, max_lines=3,
            text_style=ft.TextStyle(font_family=self.FONT_NAME, color="white", size=12),
            border_color="white", bgcolor="#000000",
            hint_text="http://...", content_padding=10, text_align=ft.TextAlign.CENTER
        )

        self.popup_box = ft.Container(
            content=ft.Column([
                ft.Text("LINK INPUT / DOWNLOADS", font_family=self.FONT_NAME, weight="bold", color="green", size=14),
                ft.Container(height=5),
                self.txt_link_input,
                ft.Container(height=10),
                ft.Row([
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="grey", on_click=self.clear_popup_text),
                    ft.Container(expand=True),
                    ft.TextButton("X", on_click=self.close_popup, style=ft.ButtonStyle(color="red")),
                    ft.TextButton("GO", on_click=self.close_popup_save, style=ft.ButtonStyle(color="green")),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=10),
                ft.Text("STATUS LOG", font_family=self.FONT_NAME, color="white", size=12),
                ft.Container(
                    content=self.downloads_column, height=100, bgcolor="#111111",
                    border=ft.border.all(1, "white"), padding=5
                )
            ], tight=True, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor="#222222", border=ft.border.all(2, "white"), padding=15,
            width=260, border_radius=0,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color="black"),
        )

        self.popup_overlay = ft.Container(
            content=self.popup_box, bgcolor="#CC000000", alignment=ft.alignment.center,
            visible=False, left=0, top=0, right=0, bottom=0,
        )
        self.page.overlay.append(self.popup_overlay)

        threading.Thread(target=self._timer_loop, daemon=True).start()
        self.safe_boot()

    # --- LOGICA POPUP ---
    def open_popup(self, e):
        if self.page.client_storage.contains_key("saved_link"):
            self.txt_link_input.value = self.page.client_storage.get("saved_link") or ""
        else:
            self.txt_link_input.value = ""

        self.popup_overlay.visible = True
        self.downloads_column.controls.clear()
        self.downloads_column.controls.append(ft.Text("Ready.", color="grey", size=11, font_family=self.FONT_NAME))
        self.page.update()

    def clear_popup_text(self, e):
        self.txt_link_input.value = ""
        self.page.client_storage.remove("saved_link")
        self.page.update()

    def close_popup(self, e):
        self.popup_overlay.visible = False
        self.page.update()

    def close_popup_save(self, e):
        val = (self.txt_link_input.value or "").strip()
        if val:
            self.page.client_storage.set("saved_link", val)
            self.downloads_column.controls.append(ft.Text(f"SENDING: {val[:20]}...", color="yellow", font_family=self.FONT_NAME, size=10))
            self.page.update()
            
            # Lancia il download sul server
            threading.Thread(target=self._handle_external_link_download, args=(val,), daemon=True).start()
        else:
            self.page.client_storage.remove("saved_link")
            self.popup_overlay.visible = False
            self.page.update()

    def _handle_external_link_download(self, link):
        try:
            if not self.config.get("ip_home"): raise RuntimeError("No IP Config")
            
            # CAMBIO PORTA: 4533 -> 5000 per parlare col nostro server python
            base = self.config["ip_home"].rstrip("/")
            # Se l'utente è connesso via VPN (Tailscale), usa quell'IP, altrimenti Home
            # L'app usa self.base_url di solito, ma qui prendiamo dalla config per sicurezza
            # Se sei connesso in VPN, self.base_url sarà quello VPN.
            
            # Usa l'URL attivo corrente se disponibile, altrimenti fallback su home
            active_url = self.base_url if self.base_url else base
            
            # Sostituisci la porta. Navidrome è 4533, il nostro server è 5000.
            # Esempio: http://192.168.1.20:4533 -> http://192.168.1.20:5000
            if ":4533" in active_url:
                dl_base = active_url.replace(":4533", ":5000")
            else:
                # Fallback se non c'è la porta nell'URL (es. proxy inverso), proviamo ad aggiungere :5000
                dl_base = active_url.rstrip("/") + ":5000"

            url = f"{dl_base}/download"

            resp = requests.post(url, json={"url": link}, timeout=10)
            
            if resp.status_code == 200:
                self.page.snack_bar = ft.SnackBar(ft.Text("DOWNLOAD STARTED ON SERVER!", color="green"))
                self.page.snack_bar.open = True
                self.popup_overlay.visible = False
            else:
                raise Exception(f"Server Error {resp.status_code}")

        except Exception as ex:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"ERROR: {ex}", color="red"))
            self.page.snack_bar.open = True
        
        self.page.update()

    # --- TIMER ---
    def _timer_loop(self):
        while self.timer_running:
            time.sleep(1)
            if AUDIO_MGR.is_playing and self.track_duration > 0:
                self.track_pos += 1
                try:
                    m, s = divmod(self.track_pos, 60)
                    mt, st = divmod(self.track_duration, 60)
                    self.time_label.value = f"{m:02d}:{s:02d} / {mt:02d}:{st:02d}"
                    self.page.update()
                except: pass
                
                if self.track_pos >= self.track_duration + 2:
                    self.next_track()

    def next_track_safe(self):
        try: self.next_track()
        except: pass

    def on_audio_update(self, status):
        try:
            if status == "PLAYING" or status == "TOGGLE":
                icon = ft.Icons.PAUSE if AUDIO_MGR.is_playing else ft.Icons.PLAY_ARROW
                self.btn_play_icon.name = icon
                self.page.update()
            elif status == "NEXT":
                self.next_track()
        except: pass

    # --- BOOT ---
    def safe_boot(self):
        try:
            if self.page.client_storage.contains_key("navix_cfg"):
                self.config = self.page.client_storage.get("navix_cfg")
                if not self.config.get("ip_home"): self.go_setup()
                else: self.go_home()
            else: self.go_setup()
        except: self.go_setup()

    def go_setup(self, err=""):
        self.page.controls.clear()
        st = ft.TextStyle(font_family=self.FONT_NAME)
        h = self.config.get("ip_home", "") 
        r = self.config.get("ip_remote", "")
        t_h = ft.TextField(label="HOME IP", value=h, text_style=st, border_color="green", hint_text="192.168.1.x:4533")
        t_r = ft.TextField(label="REMOTE IP", value=r, text_style=st, border_color="red", hint_text="100.x.y.z:4533")
        t_u = ft.TextField(label="USER", value=self.config.get("user","admin"), text_style=st)
        t_p = ft.TextField(label="PASS", password=True, can_reveal_password=True, text_style=st)
        
        def save(e):
            hv = t_h.value.strip().rstrip("/")
            rv = t_r.value.strip().rstrip("/")
            if hv and not hv.startswith("http"): hv = "http://" + hv
            if rv and not rv.startswith("http"): rv = "http://" + rv
            try:
                self.config = {"ip_home": hv, "ip_remote": rv, "user": t_u.value.strip(), "pass": t_p.value.strip()}
                self.page.client_storage.set("navix_cfg", self.config)
                self.go_home()
            except Exception as ex: self.go_setup(str(ex))

        self.page.add(ft.Container(content=ft.Column([
            ft.Text("/// SETUP ///", size=24, font_family=self.FONT_NAME),
            ft.Text(err, color="red"), t_h, t_r, t_u, t_p,
            ft.ElevatedButton("SAVE", on_click=save)
        ], horizontal_alignment="center"), padding=30, alignment=ft.alignment.center, expand=True))
        self.page.update()

    def go_home(self):
        self.page.controls.clear()
        AUDIO_MGR.stop()
        def rst(e):
            self.page.client_storage.remove("navix_cfg")
            self.go_setup()
        def mk(t, c, u):
            return ft.Container(
                content=ft.Text(t, weight="bold", color="black", font_family=self.FONT_NAME),
                bgcolor=c, width=200, height=100, border=ft.border.all(2, "white"), alignment=ft.alignment.center,
                on_click=lambda _: self.go_list(u)
            )
        self.page.add(ft.Container(content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=rst)], alignment="end"),
            ft.Text("SYSTEM BOOT", size=24, font_family=self.FONT_NAME),
            ft.Container(height=40),
            mk("LOCAL NETWORK", "#00FF00", self.config["ip_home"]),
            ft.Container(height=20),
            mk("SECURE VPN", "#FF0000", self.config["ip_remote"])
        ], horizontal_alignment="center"), padding=ft.padding.only(top=50), alignment=ft.alignment.center, expand=True))
        self.page.update()

    def go_list(self, url):
        self.page.controls.clear()
        self.base_url = url
        head = ft.Container(content=ft.Row([
            ft.IconButton(ft.Icons.HOME, icon_color="red", on_click=lambda _: self.go_home()),
            ft.Row([ft.Icon(ft.Icons.STORAGE, color="white"), ft.Text("DATABASE", font_family=self.FONT_NAME, size=20, weight="bold")], alignment="center"),
            ft.IconButton(ft.Icons.DOWNLOAD, icon_color="blue", on_click=self.open_popup)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), bgcolor="#111111", padding=ft.padding.only(top=50, bottom=20, left=10, right=10), border=ft.border.only(bottom=ft.border.BorderSide(2, "white")))
        fab = None
        if self.current_song_data: fab = ft.FloatingActionButton(icon=ft.Icons.MUSIC_NOTE, bgcolor="white", content=ft.Icon(ft.Icons.MUSIC_NOTE, color="black"), on_click=lambda _: self.go_player())
        self.page.add(ft.Column([head, ft.Container(content=self.songs_column, expand=True)], expand=True))
        self.page.floating_action_button = fab
        self.page.update()
        if not self.playlist: threading.Thread(target=self._fetch_songs, daemon=True).start()

    def get_auth(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'NavixMgr', 'f': 'json'}

    def _fetch_songs(self):
        try:
            self.songs_column.controls.append(ft.Text("LOADING...", font_family=self.FONT_NAME))
            self.page.update()
            p = self.get_auth()
            p['size'] = 100
            res = requests.get(f"{self.base_url}/rest/getRandomSongs", params=p, timeout=10)
            if res.status_code == 200:
                data = res.json()
                self.songs_column.controls.clear()
                self.playlist = []
                if 'randomSongs' in data['subsonic-response']:
                    self.playlist = data['subsonic-response']['randomSongs']['song']
                    for idx, s in enumerate(self.playlist):
                        self.songs_column.controls.append(ft.Container(
                            content=ft.Row([ft.Icon(ft.Icons.MUSIC_NOTE), ft.Column([ft.Text(s['title'], weight="bold", font_family=self.FONT_NAME), ft.Text(s.get('artist','?'), color="grey")], expand=True)]),
                            padding=15, bgcolor="#000000" if idx%2==0 else "#111111",
                            on_click=lambda e, i=idx: self.play_index(i)
                        ))
                else: self.songs_column.controls.append(ft.Text("NO SONGS"))
            else: self.songs_column.controls = [ft.Text("AUTH ERROR", color="red")]
        except: self.songs_column.controls = [ft.Text("NET ERROR", color="red")]
        self.page.update()

    def go_player(self):
        self.page.controls.clear()
        if not self.current_song_data: return
        try:
            p = self.get_auth()
            p['id'] = self.current_song_data['id']
            p['size'] = 600
            req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=p)
            url = req.prepare().url
        except: url = ""
        img = ft.Image(src=url, width=300, height=300, fit=ft.ImageFit.COVER, error_content=ft.Container(bgcolor="#333"))
        self.btn_play_icon.name = ft.Icons.PAUSE if AUDIO_MGR.is_playing else ft.Icons.PLAY_ARROW
        ctr = ft.Row([
            ft.Container(content=ft.Text("<<<", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=lambda _: self.prev_track()),
            ft.Container(content=self.btn_play_icon, width=80, height=80, bgcolor="black", border=ft.border.all(3,"white"), border_radius=40, alignment=ft.alignment.center, on_click=lambda _: AUDIO_MGR.toggle()),
            ft.Container(content=ft.Text(">>>", size=24, weight="bold", font_family=self.FONT_NAME), padding=20, on_click=lambda _: self.next_track())
        ], alignment="center")
        self.page.add(ft.Container(content=ft.Column([
            ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.go_list(self.base_url))]),
            ft.Container(height=20), ft.Container(content=img, border=ft.border.all(4,"white")),
            ft.Container(height=20), self.time_label,
            ft.Text(self.current_song_data['title'], size=20, text_align="center", font_family=self.FONT_NAME),
            ft.Container(expand=True), ctr, ft.Container(height=50)
        ], horizontal_alignment="center"), padding=ft.padding.only(top=50), expand=True))
        self.page.update()

    def play_index(self, idx):
        if idx < 0 or idx >= len(self.playlist): return
        self.current_song_idx = idx
        self.current_song_data = self.playlist[idx]
        self.track_pos = 0
        try: self.track_duration = int(self.current_song_data.get("duration", 180))
        except: self.track_duration = 180
        self.go_player()
        AUDIO_MGR.play_track(self.current_song_data, self.get_auth(), self.base_url)

    def next_track(self): self.play_index((self.current_song_idx + 1) % len(self.playlist))
    def prev_track(self): self.play_index((self.current_song_idx - 1) % len(self.playlist))

def main(page: ft.Page):
    NavixUI(page)

ft.app(target=main)
