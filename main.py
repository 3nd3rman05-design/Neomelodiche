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
        
        # Inizializziamo config vuota
        self.config = {
            "ip_home": "http://192.168.1.20:4533", # Default
            "ip_remote": "http://100.x.y.z:4533",
            "user": "admin",
            "pass": "admin"
        }

        # STILE
        self.COLOR_BG = "#000000"       
        self.COLOR_TEXT = "#FFFFFF"     
        self.FONT_NAME = "Courier New"  
        
        self.page.title = "NAVI-X PRO"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = self.COLOR_BG
        self.page.padding = 0

        self.songs_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)
        self.debug_label = ft.Text("SYSTEM READY", color="grey", size=10, font_family=self.FONT_NAME)

    # --- FUNZIONE DI AVVIO SICURO (Chiamata DOPO che l'app è visibile) ---
    def safe_boot(self):
        try:
            # 1. SETUP CACHE (Protetto)
            self.cache_dir = os.path.join(os.getenv("TMPDIR") or "/tmp", "navix_buffer")
            if os.path.exists(self.cache_dir):
                try: shutil.rmtree(self.cache_dir)
                except: pass
            os.makedirs(self.cache_dir, exist_ok=True)
            
            # 2. CARICAMENTO DATI (Protetto)
            # Se fallisce, usa i default e va al setup
            try:
                if self.page.client_storage.contains_key("navix_cfg"):
                    saved = self.page.client_storage.get("navix_cfg")
                    if saved: self.config = saved
                    self.show_selector() # Dati trovati -> Selettore
                else:
                    self.show_setup_screen() # Nessun dato -> Setup
            except Exception as e:
                print(f"Storage Error: {e}")
                self.show_setup_screen() # Errore memoria -> Setup

        except Exception as e:
            self.page.clean()
            self.page.add(ft.Text(f"CRITICAL BOOT ERROR:\n{e}", color="red", size=20))
            self.page.update()

    # --- SCHERMATA SETUP ---
    def show_setup_screen(self):
        self.page.clean()
        
        txt_ip_home = ft.TextField(label="HOME IP", value=self.config["ip_home"], border_color="green", text_style=ft.TextStyle(font_family=self.FONT_NAME))
        txt_ip_remote = ft.TextField(label="REMOTE IP", value=self.config["ip_remote"], border_color="red", text_style=ft.TextStyle(font_family=self.FONT_NAME))
        txt_user = ft.TextField(label="USER", value=self.config["user"], border_color="white", text_style=ft.TextStyle(font_family=self.FONT_NAME))
        txt_pass = ft.TextField(label="PASS", value=self.config["pass"], password=True, can_reveal_password=True, border_color="white", text_style=ft.TextStyle(font_family=self.FONT_NAME))
        
        def save_data(e):
            if not txt_ip_home.value or not txt_user.value:
                txt_user.error_text = "REQUIRED"
                self.page.update()
                return
            
            try:
                self.config = {
                    "ip_home": txt_ip_home.value.strip(),
                    "ip_remote": txt_ip_remote.value.strip(),
                    "user": txt_user.value.strip(),
                    "pass": txt_pass.value.strip()
                }
                self.page.client_storage.set("navix_cfg", self.config)
                self.show_selector()
            except Exception as ex:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"Save Error: {ex}"))
                self.page.snack_bar.open = True
                self.page.update()

        self.page.add(
            ft.Container(
                content=ft.Column([
                    ft.Text("/// INITIAL SETUP ///", size=24, color="white", font_family=self.FONT_NAME),
                    ft.Container(height=20),
                    txt_ip_home, ft.Container(height=10),
                    txt_ip_remote, ft.Container(height=10),
                    txt_user, ft.Container(height=10),
                    txt_pass, ft.Container(height=30),
                    ft.ElevatedButton("SAVE SYSTEM", on_click=save_data, bgcolor="white", color="black")
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=30, alignment=ft.alignment.center, expand=True
            )
        )

    def get_auth_params(self):
        salt = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        token = hashlib.md5((self.config["pass"] + salt).encode('utf-8')).hexdigest()
        return {'u': self.config["user"], 't': token, 's': salt, 'v': '1.16.1', 'c': 'SafeClient', 'f': 'json'}

    # --- SELEZIONE ---
    def show_selector(self):
        self.page.clean()
        
        def reset_config(e):
            self.page.client_storage.remove("navix_cfg")
            self.show_setup_screen()

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
                    ft.Row([ft.IconButton(ft.Icons.SETTINGS, icon_color="grey", on_click=reset_config)], alignment=ft.MainAxisAlignment.END),
                    ft.Text("/// SYSTEM BOOT ///", color="white", size=24, font_family=self.FONT_NAME),
                    ft.Container(height=40),
                    make_btn("LOCAL NETWORK", ft.Icons.HOME, "#00FF00", self.config["ip_home"]),
                    ft.Container(height=20),
                    make_btn("SECURE VPN", ft.Icons.PUBLIC, "#FF0000", self.config["ip_remote"])
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                alignment=ft.alignment.center, expand=True
            )
        )

    # --- LISTA ---
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
            cover_req = requests.Request('GET', f"{self.base_url}/rest/getCoverArt", params=params)
            cover_url = cover_req.prepare().url
        except: cover_url = ""

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
            padding=20, on_
