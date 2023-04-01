"""
Play media from local, network, and Google Drive folders
"""
import os
import aiofiles

TESTING = True
START_PATH = ['app','src'][TESTING]

CWD = os.getcwd()

os.environ['PYTHON_VLC_LIB_PATH'] = f"{CWD}\\{START_PATH}\\kmexplorer\\vlc-3.0.18\\libvlc.dll"
os.environ['PYTHON_VLC_MODULE_PATH'] = f"{CWD}\\{START_PATH}\\kmexplorer\\vlc-3.0.18"

import vlc
import math
from functools import reduce
from time import sleep
import aiohttp
import asyncio
import requests
import webbrowser
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from enum import Enum
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, RIGHT, LEFT, HIDDEN, VISIBLE, TOP, BOTTOM
from toga_winforms.libs.winforms import WinForms, Color, Size

#region Setup

RESOURCES = f"{START_PATH}\\kmexplorer\\resources"
REPO_PATH = f"{RESOURCES}\\repo.txt"

CLIENT_SECRETS_PATH = f"{RESOURCES}\\client_secrets.json"
GoogleAuth.DEFAULT_SETTINGS['client_config_file'] = CLIENT_SECRETS_PATH

CREDENTIALS_PATH = f"{RESOURCES}\\user_creds.json"

with open(f"{RESOURCES}\\API_KEY.txt", "r", encoding='utf-8') as f:
    API_KEY = f.readline()

MIN_CHUNK_SIZE = 2**18
NUM_DL_PARTS = 12

FOLDER_REPO = "Folder Repo"
VLC_PLAYER =  "VLC Player"
GET_FOLDER = "Enter Folder Name"
RENAME_FOLDER = "Rename Folder"
PROGRESS_WINDOW = "Download Progress"
PLAY_PAUSE = '⏯'
PLAY = '⏵︎'
PAUSE = '⏸︎'
MUTE = '🔇'
UNMUTE = '🔊'

BROWSE = "Browse"
OPEN = "Open"

FINISHED = "Finished"
HANDLED = "Handled"

TIMEOUT_TIME = 2

_ESCAPE = WinForms.Keys.Escape
_SPACE = WinForms.Keys.Space
_DELETE = WinForms.Keys.Delete
_ENTER = WinForms.Keys.Enter

_R = WinForms.Keys.R

_UP = WinForms.Keys.Up
_DOWN = WinForms.Keys.Down
_LEFT = WinForms.Keys.Left
_RIGHT = WinForms.Keys.Right

ARROW_KEYS = {
    _UP,
    _DOWN,
    _LEFT,
    _RIGHT
}

VLC_SUPPORTED_FILE_EXTENSIONS = {
    '.ASX',
    '.DTS',
    '.GXF',
    '.M2V',
    '.M3U',
    '.M4V',
    '.MPEG1',
    '.MPEG2',
    '.MTS',
    '.MXF',
    '.OGM',
    '.PLS',
    '.BUP',
    '.A52',
    '.AAC',
    '.B4S',
    '.CUE',
    '.DIVX',
    '.DV',
    '.FLV',
    '.M1V',
    '.M2TS',
    '.MKV',
    '.MOV',
    '.MPEG4',
    '.OMA',
    '.SPX',
    '.TS',
    '.VLC',
    '.VOB',
    '.XSPF',
    '.DAT',
    '.BIN',
    '.IFO',
    '.PART',
    '.3G2',
    '.AVI',
    '.MPEG',
    '.MPG',
    '.FLAC',
    '.M4A',
    '.MP1',
    '.OGG',
    '.WAV',
    '.XM',
    '.3GP',
    '.SRT',
    '.WMV',
    '.AC3',
    '.ASF',
    '.MOD',
    '.MP2',
    '.MP3',
    '.MP4',
    '.WMA',
    '.MKA',
    '.M4P'
}

class FolderType(Enum):
    INVALID = 0
    LOCAL_OR_NETWORK = 1
    GOOGLE_DRIVE = 2
    FOLDER_REPO = 3

class File:
    def __init__(self, id, name, size=None):
        self.id = id
        self.name = name
        self.size = int(size)
        self.chunk_size = self.size // 100
        
    def GetSizeMB(self):
        return round(self.size / 2**20, 2)
    
    def CreatePartitions(self, num_parts):
        part_size = self.size // num_parts
        remainder = self.size - (part_size * num_parts)

        part_size_list = [int(part_size)] * num_parts
        part_size_list[0] += remainder

        start_byte = 0
        partitions = []
        
        for _part_size in part_size_list:
            partitions.append((start_byte, _part_size + start_byte))
            start_byte += _part_size
        
        return partitions
            
#endregion

#region Startup

class KMExplorer(toga.App):
    def startup(self):
        self.google_authenticated = False
        self.drive = GoogleDrive()
        self.google_folder_id = ''
        self.mouse_hidden = False
        self.mouse_counter = 0
        
        #region Commands
        
            #region Base Commands
            
        about, exit_app, preferences, homepage = sorted(list(self.commands._commands), key=lambda c: c.text)
            
        self.commands._commands.remove(preferences)
            
            #endregion
        
            #region VLC Group
        
        vlc_group = toga.Group(text="VLC")
        
        play_pause = toga.Command(
            self.PlayPauseVLC,
            label="Play/Pause",
            group=vlc_group,
            icon=toga.Icon.TOGA_ICON,
            section=0
        )

        stop = toga.Command(
            self.StopVLC,
            label="Stop VLC",
            group=vlc_group,
            section=0
        )
        
        fullscreen = toga.Command(
            self.ToggleFullscreenVLC,
            label="Toggle Fullscreen",
            group=vlc_group,
            section=1
        )
        
        toggle_window = toga.Command(
            self.ToggleVisibleVLC,
            label="Toggle Visible",
            group=vlc_group,
            section=1
        )
        
        toggle_controls = toga.Command(
            self.ToggleControlMenu,
            label="Toggle Controls",
            group=vlc_group,
            section=1
        )
        
            #endregion
        
            #region File Group
        
        file_group = toga.Group.FILE
        
        import_folder_repo = toga.Command(
            self.ImportFolderRepo,
            label="Import Folder Repo",
            shortcut=toga.Key.MOD_1 + toga.Key.I,
            group=file_group,
            section=0
        )
        
        load_folder_repo = toga.Command(
            self.LoadFolderRepo,
            label="Load Folder Repo",
            shortcut=toga.Key.MOD_1 + toga.Key.L,
            group=file_group,
            section=0
        )
        
        save_folder_to_repo = toga.Command(
            self.ShowSaveFolderPrompt,
            label="Save Folder to Repo",
            shortcut=toga.Key.MOD_1 + toga.Key.S,
            group=file_group,
            section=0
        )
        
        google_authenticate = toga.Command(
            self.GoogleAuthentication,
            label="Google Authenticate",
            shortcut=toga.Key.MOD_1 + toga.Key.E,
            group=file_group,
            section=1
        )
        
        download_gdrive_folder = toga.Command(
            self.DownloadGoogleDriveFolder,
            label="Download Google Drive Folder",
            shortcut=toga.Key.MOD_1 + toga.Key.D,
            group=file_group,
            section=1
        )

            #endregion
        
            #region Help Group
            
        help_group = toga.Group.HELP
        
        check_latest = toga.Command(
            self.CheckLatestVersion,
            label="Check For Updates",
            group=help_group,
            section=1
        )
            
            #endregion
        
        self.commands.add(
            play_pause, 
            stop, 
            fullscreen, 
            toggle_window, 
            toggle_controls, 
            import_folder_repo, 
            google_authenticate, 
            download_gdrive_folder, 
            save_folder_to_repo, 
            load_folder_repo,
            check_latest
        )
        
        #endregion
        
        self.main_box = toga.Box(style=Pack(direction=COLUMN))

        input_label = toga.Label(
            'Enter a folder location: ',
            style=Pack(padding=(0, 5))
        )

        self.folder_input = toga.TextInput(style=Pack(flex=1), placeholder="C:\\Users\\user01\\Videos", on_change=self.ChangeButton)
        self.folder_input._impl.native.KeyPress += self.OnEnterPress

        self.button = toga.Button(
            text="Browse",
            on_press=self.BrowseLocalFolders,
            style=Pack(padding_left=5)
        )

        input_box = toga.Box(style=Pack(direction=ROW, padding=5, alignment=CENTER))
        input_box.add(input_label)
        input_box.add(self.folder_input)
        input_box.add(self.button)

        self.main_box.add(input_box)
        
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.main_box
        self.main_window.show()
        
        self.InitFolderTable()
        self.InitTextEntryWindow()
        self.InitDownloadProgressBarWindow()
        self.InitVLCWindow()

        #region Supporting Methods

    def ChangeButton(self, widget=''):
        if self.folder_input.value:
            if self.button.text == BROWSE:
                print("DEBUG: Changing Button to \"Open\"")
                self.button.text = OPEN
                self.button.on_press = self.OnClickGetFolderContents
        else:
            print("DEBUG: Changing Button to \"Browse\"")
            self.button.text = BROWSE
            self.button.on_press = self.BrowseLocalFolders 

    def OnEnterPress(self, sender, event):
        print(f"DEBUG: Key Entered To TextBox: {repr(event.KeyChar)}")
        if event.KeyChar == '\r':
            self.OnClickGetFolderContents()
            event.Handled = True
            
    def CheckLatestVersion(self, widget=''):
        try:
            latest = f"{self.home_page}/releases/latest"
            response = requests.get(latest)
            version = response.url.split('/')[-1][1:]
            
            if self.version != version:
                webbrowser.open(latest)
            else:
                self.main_window.info_dialog(
                    "Already Up To Date",
                    f"You already have the latest version (v{version})."
                )
        except Exception as err:
            print(f"EXCEPTION WHILE CHECKING FOR LATEST: {err}")
            self.main_window.error_dialog(
                "Error Checking For Updates",
                "There was an error while checking for updates.\n\nPlease try again later."
            )
        #endregion
    
    #endregion

    #region VLC Player
    
        #region VLC Window (and control box)
        
    def InitVLCWindow(self, widget=''):
        self.player_panel = toga.Box(style=Pack(flex=1))
        player_hwnd = self.player_panel._impl.native.Handle # IntPtr
        self.player_panel._impl.native.DoubleClick += self.player_panel_DoubleClick
        self.player_panel._impl.native.MouseMove += self.player_panel_MouseMove
        self.player_panel._impl.native.MouseHover += self.player_panel_MouseHover

        self.VLC_instance = vlc.Instance('--verbose 2'.split())
        
        self.player = self.VLC_instance.media_player_new()
        self.player.set_hwnd(str(player_hwnd))
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)

        self.vlc_box = toga.Box(
            style=Pack(
                direction=COLUMN
            )
        )
        
        self.InitControlBox()
        
        self.vlc_box.add(self.player_panel)
        self.vlc_box.add(self.control_box)
        
        self.vlc_window = toga.Window(title=VLC_PLAYER, closeable=False, size=(800,510))
        self.vlc_window._impl.native.KeyPreview = True
        self.vlc_window._impl.native.PreviewKeyDown += self.enable_arrow_keys_PreviewKeyDown
        self.vlc_window._impl.native.KeyDown += self.vlc_window_KeyDown
        self.vlc_window._impl.native.FormClosing += self.vlc_window_FormClosing
        
        self.windows.add(self.vlc_window)
        self.vlc_window.content = self.vlc_box
        
        self.vlc_window.hide()
    
    def InitControlBox(self, play_button_text=PLAY_PAUSE, mute_button_text=MUTE, audio_tracks=[], subtitles=[], audio_track=None, subtitle=None, volume=100):
        control_box = toga.Box(
            style=Pack(
                direction=ROW,
                height=50,
                alignment=CENTER,
                padding=5,
            )
        )
        
        control_box._impl.native.PreviewKeyDown += self.enable_arrow_keys_PreviewKeyDown
        
        #region Init Control Box Widgets
        
        self.play_button = toga.Button(
            play_button_text, 
            on_press=self.PlayPauseVLC, 
            style=Pack(
                padding_right=15,
                font_size=24.5,
                height=50,
                width=50,
                alignment=CENTER
            )
        )
        
        skip_back = toga.Button(
            '⏮︎',
            on_press=self.SkipBackVLC,
            style=Pack(
                padding_right=5,
                font_size=14,
                height=35,
                width=35,
                alignment=CENTER
            )
        )
        
        stop_button = toga.Button(
            '⏹',
            on_press=self.StopVLC,
            style=Pack(
                padding_right=5,
                font_size=14,
                height=35,
                width=35,
                alignment=CENTER
            )
        )
        
        skip_forward = toga.Button(
            '⏭︎',
            on_press=self.SkipForwardVLC,
            style=Pack(
                padding_right=15,
                font_size=14,
                height=35,
                width=35,
                alignment=CENTER
            )
        )
        
            #region Audio Tracks Selector
        
        audio_tracks_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                height=50,
                width=50,
                alignment=LEFT,
                padding_right=10
            )
        )
        
        audio_tracks_label = toga.Label(
            text="Audio Track:",
            style=Pack(padding_bottom=5)
        )
        
        self.audio_tracks = toga.Selection(
            items=audio_tracks,
            on_select=self.SetAudioTrack
        )
        
        self.AdjustDropDownWidth(self.audio_tracks)
        
        if audio_track:
            self.audio_tracks.value = audio_track
        
        audio_tracks_box.add(audio_tracks_label)
        audio_tracks_box.add(self.audio_tracks)
        
            #endregion
        
            #region Subtitles Selector
        
        subtitles_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                height=50,
                width=50,
                alignment=LEFT,
                padding_right=10
            )
        )
        
        subtitles_label = toga.Label(
            text="Subtitles:",
            style=Pack(padding_bottom=5)
        )
        
        self.subtitles = toga.Selection(
            items=subtitles,
            on_select=self.SetSubtitle
        )
        
        self.AdjustDropDownWidth(self.subtitles)
        
        if subtitle:
            self.subtitles.value = subtitle
        
        subtitles_box.add(subtitles_label)
        subtitles_box.add(self.subtitles)
        
            #endregion
        
        spacy_boi = toga.Label(
            '',
            style=Pack(
                flex=1,
                visibility=HIDDEN
            )
        )
        
            #region Volume Slider
        
        volume = round(volume)
        
        volume_slider_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                height=50,
                width=50,
                alignment=CENTER,
                padding_right=5
            )
        )
        
        self.volume_slider = toga.Slider(
            value=volume,
            range=(0,100),
            tick_count=101,
            style=Pack(
                alignment=BOTTOM,
                height=25
            ),
            on_change=self.SetVolume
        )
        
        self.volume_slider_label = toga.Label(
            text=f"Volume: {volume}%{' '*self.GetVolumeSpace(volume)}",
            style=Pack(padding_bottom=3)
        )
        
        volume_slider_box.add(self.volume_slider_label)
        volume_slider_box.add(self.volume_slider)
        
            #endregion
        
        self.mute_button = toga.Button(
            mute_button_text,
            on_press=self.ToggleMute,
            style=Pack(
                padding_right=15,
                font_size=14,
                height=35,
                width=35,
                alignment=CENTER
            )
        )
        
        fullscreen_button = toga.Button(
            '⛶',
            on_press=self.ToggleFullscreenVLC,
            style=Pack(
                font_size=24.5,
                height=50,
                width=50,
                alignment=CENTER
            )
        )
        
        #endregion
        
        #region Add Control Box Widgets
        
        control_box.add(self.play_button)
        control_box.add(skip_back)
        control_box.add(stop_button)
        control_box.add(skip_forward)
        control_box.add(audio_tracks_box)
        control_box.add(subtitles_box)
        control_box.add(spacy_boi)
        control_box.add(volume_slider_box)
        control_box.add(self.mute_button)
        control_box.add(fullscreen_button)
        
        #endregion
        
        for control in control_box.children:
            control._impl.native.PreviewKeyDown += self.enable_arrow_keys_PreviewKeyDown
        
        self.control_box = control_box
    
        #endregion
        
        #region Event Handler Overrides
    
    def player_panel_MouseMove(self, sender, event):
        self.mouse_counter = 0
        if self.mouse_hidden:
            print("DEBUG: Show Mouse")
            self.mouse_hidden = False
            self.player_panel._impl.native.Cursor.Show()
            self.player_panel._impl.native.ResetMouseEventArgs()
        event.Handled = True
    
    def player_panel_MouseHover(self, sender, event):
        if self.mouse_counter >= 3:
            print("DEBUG: Hide Mouse")
            self.mouse_hidden = True
            self.player_panel._impl.native.Cursor.Hide()
        else:
            self.mouse_counter += 1
            self.player_panel._impl.native.ResetMouseEventArgs()
        event.Handled = True
       
    def enable_arrow_keys_PreviewKeyDown(self, sender, event):
        if event.KeyCode in ARROW_KEYS:
            event.IsInputKey = True
       
    def vlc_window_KeyDown(self, sender, event):
        if self.vlc_window.visible:
            print(f"DEBUG: VLC Window KeyPress Recorded: {event.KeyCode}")
            if self.is_full_screen and event.KeyCode == _ESCAPE:
                print("DEBUG: Escape On VLC Window - Exiting Fullscreen")
                self.ToggleFullscreenVLC()
            if event.KeyCode == _SPACE:
                active_form = self.GetCurrentWindow()
                if VLC_PLAYER in active_form.Text:
                    self.player_panel._impl.native.Focus()
                    print("DEBUG: Space On VLC Window - Toggling PlayPause")
                    self.PlayPauseVLC()
            if event.KeyCode == _UP:
                print("DEBUG: Up Arrow On VLC Window - +5 Volume")
                self.VolumeUp()
            if event.KeyCode == _DOWN:
                print("DEBUG: Down Arrow On VLC Window - -5 Volume")
                self.VolumeDown()
            if event.KeyCode == _RIGHT:
                print("DEBUG: Right Arrow On VLC Window - Skipping +10 Seconds")
                self.SkipForwardVLC()
            if event.KeyCode == _LEFT:
                print("DEBUG: Left Arrow On VLC Window - Skipping -10 Seconds")
                self.SkipBackVLC()
        event.Handled = True
  
    def vlc_window_FormClosing(self, sender, event):
        active_form = self.GetCurrentWindow()
        if VLC_PLAYER in active_form.Text:
            print("DEBUG: Close VLC Window Clicked, Hiding VLC Window And Stopping Playback Instead")
            event.Cancel = True
            self.StopVLC()
        
    def player_panel_DoubleClick(self, sender, event):
        print("DEBUG: Double-Click On Player Panel - Toggling Fullscreen")
        self.ToggleFullscreenVLC()
        event.Handled = True
        
        #endregion
            
        #region VLC Player Functions
    
            #region Volume Controls
    
    def GetVolumeSpace(self, volume):
        if volume > 0:
            return int(4 - (int(math.log10(volume))))
        return 4
        
    def SetVolume(self, widget):
        volume = round(widget.value)
        print(f"DEBUG: SetVolume to {volume}")
        self.volume_slider_label.text = f"Volume: {volume}%{' '*self.GetVolumeSpace(volume)}"
        self.player.audio_set_volume(volume)
        
    def VolumeUp(self, widget=''):
        volume = round(self.volume_slider.value)
        volume_up = volume + (5 - (volume % 5) - ((volume // 100) * 5))
        print(f"DEBUG: VolumeUp from {volume} to {volume_up}")
        self.volume_slider.value = volume_up
        self.volume_slider_label.text = f"Volume: {volume_up}%{' '*self.GetVolumeSpace(volume_up)}"
        self.player.audio_set_volume(volume_up)
    
    def VolumeDown(self, widget=''):
        volume = round(self.volume_slider.value)
        volume_down = volume - ((volume > 0) * ((volume % 5) + ((volume % 5 == 0) * 5)))
        print(f"DEBUG: VolumeDown from {volume} to {volume_down}")
        self.volume_slider.value = volume_down
        self.volume_slider_label.text = f"Volume: {volume_down}%{' '*self.GetVolumeSpace(volume_down)}"
        self.player.audio_set_volume(volume_down)
    
    def ToggleMute(self, widget=''):
        if self.player.will_play():
            if self.player.audio_get_mute():
                print("DEBUG: Unmuting Audio")
                self.mute_button.text = UNMUTE
            else:
                print("DEBUG: Muting Audio")
                self.mute_button.text = MUTE
                
            self.player.audio_toggle_mute()
            
            #endregion
    
            #region Control Menu
    
    def RefreshControlMenu(self, widget=''):
        if self.vlc_window.visible:
            if self.vlc_box.children.__contains__(self.control_box):
                print("DEBUG: Disposing of old Control Menu")
                self.vlc_box.remove(self.control_box)

            print("DEBUG: Creating new Control Menu")
            self.InitControlBox()
            self.vlc_box.add(self.control_box)

    def DisableControlMenu(self, widget=''):
        print("DEBUG: Hiding Control Menu")
        self.vlc_box.remove(self.control_box)

    def EnableControlMenu(self, widget=''):
        print("DEBUG: Showing Control Menu")
        self.InitControlBox(
            self.play_button.text, 
            self.mute_button.text,
            self.audio_tracks.items,
            self.subtitles.items,
            self.audio_tracks.value,
            self.subtitles.value,
            self.volume_slider.value
        )
        self.vlc_box.add(self.control_box)

    def ToggleControlMenu(self, widget=''):
        if self.vlc_window.visible:
            print("DEBUG: Toggling Control Menu Visibility")
            if self.vlc_box.children.__contains__(self.control_box):
                self.DisableControlMenu()
            else:
                self.EnableControlMenu()
    
            #endregion
    
            #region Window Controls
    
    def GetCurrentWindow(self):
        return self.main_window._impl.native.ActiveForm
    
    def ToggleVisibleVLC(self, widget=''):
        if self.vlc_window.visible:
            print("DEBUG: Hiding VLC Window")
            self.vlc_window.hide()
        else:
            print("DEBUG: Showing VLC Window")
            self.vlc_window.show()
    
    def ToggleFullscreenVLC(self, widget=''):
        if self.vlc_window.visible:
            if self.is_full_screen:
                print("DEBUG: Exiting Fullscreen")
                self.exit_full_screen()
                
                if not self.vlc_box.children.__contains__(self.control_box):
                    self.EnableControlMenu()
            else:
                print("DEBUG: Entering Fullscreen")
                if self.vlc_box.children.__contains__(self.control_box):
                    self.DisableControlMenu()
                    
                self.set_full_screen(self.vlc_window)
    
            #endregion
    
            #region Playback Controls
    
    def StopVLC(self, widget='', hide=True):
        print("DEBUG: Stopping VLC Playback, Exiting Fullscreen, And Hiding Window")
        self.player.stop()
        self.vlc_window.title = VLC_PLAYER
        self.exit_full_screen()
        self.RefreshControlMenu()
        if hide:
            self.vlc_window.hide()
    
    def PlayPauseVLC(self, widget=''):
        if self.player.will_play():
            if self.player.is_playing():
                print("DEBUG: Pausing Playback")
                self.play_button.text=PLAY
            else:
                print("DEBUG: Resuming Playback")
                self.play_button.text=PAUSE
                
            self.player.pause()        
        
    def SkipForwardVLC(self, widget=''):
        length = self.player.get_length()
        current_time = self.player.get_time()
        self.player.set_time([length,current_time+10000][current_time+10000<length])
        
    def SkipBackVLC(self, widget=''):
        current_time = self.player.get_time()
        self.player.set_time([0,current_time-10000][current_time-10000>0])
        
            #endregion
        
            #region Audio Track Selection
        
    def SetupAudioTracks(self, widget=''):
        audio_track_descriptions = self.player.audio_get_track_description()
        self.audio_track_dict = {a[1].decode(): a[0] for a in audio_track_descriptions}
        self.audio_track_dict.pop('Disable')
        print(f"\nDEBUG: Audio Track Dict: {self.audio_track_dict}\n")
        
    def SetAudioTrack(self, widget=''):
        track_id = self.audio_track_dict.get(widget.value)
        print(f"\nDEBUG: Audio Track Set To: {{\'{widget.value}\': {track_id}}}\n")
        self.player.audio_set_track(track_id)
        
    def SetAudioTrackItems(self):
        self.audio_tracks.items = sorted([*self.audio_track_dict.keys()], key=self.audio_track_dict.get)
        
            #endregion
    
            #region Subtitle Selection
        
    def SetupSubtitles(self, widget=''):
        subtitle_descriptions = self.player.video_get_spu_description()
        self.subtitle_dict = {s[1].decode(): s[0] for s in subtitle_descriptions}
        print(f"\nDEBUG: Subtitle Dict: {self.subtitle_dict}\n")
        
    def SetSubtitle(self, widget=''):
        sub_id = self.subtitle_dict.get(widget.value)
        print(f"\nDEBUG: Subtitles Set To: {{\'{widget.value}\': {sub_id}}}\n")
        self.player.video_set_spu(sub_id)
        
    def SetSubtitleItems(self):
        self.subtitles.items = sorted([*self.subtitle_dict.keys()], key=self.subtitle_dict.get)
        
    def SetSubtitlesInitial(self):
        if len(self.subtitles.items) > 1:
            sorted_subs = sorted(self.subtitles.items, key=self.subtitle_dict.get)
            print(f"\n\nSORTED SUBS: {sorted_subs}\n\n")
            self.subtitles.value = sorted_subs[1]
        
            #endregion
         
    def AdjustDropDownWidth(self, combo_box):
        if combo_box.items:
            width = combo_box._impl.native.DropDownWidth
            graphics = combo_box._impl.native.CreateGraphics()
            font = combo_box._impl.native.Font
            
            max_width = round(max(map(lambda item: graphics.MeasureString(item, font).Width, combo_box.items)))
            width = max_width if max_width > width else width
            
            combo_box._impl.native.DropDownWidth = width
            
    def IsPlayableWithVLC(self, filename):
        file_extension = '.' + filename.split('.')[-1].upper()
        return file_extension in VLC_SUPPORTED_FILE_EXTENSIONS    
         
        #endregion
        
    def PlayWithVLC(self, input_str, filename):
        print(f"DEBUG: Playing {input_str} With VLC")
        media = self.VLC_instance.media_new(input_str)
        if self.folder_type == FolderType.GOOGLE_DRIVE:
            http_token = f"http-token=\'Authorization: Bearer {self.gauth_token}\'"
            print(http_token)
            media.add_option(http_token)
        self.player.set_media(media)
        self.player.play()
        
        if not self.player.is_playing():
            retry_count = 0
            while media.get_state() in [vlc.State.NothingSpecial, vlc.State.Opening, vlc.State.Buffering]:
                print(f"DEBUG: Attempting to load {input_str}\nCURRENT_STATE: {media.get_state()}\nRETRY_COUNTER = {retry_count}")
                sleep(1)
                retry_count += 1
            
            if not self.player.is_playing():
                print(f"DEBUG: Media State When Failed = {media.get_state()}")
                if self.folder_type == FolderType.GOOGLE_DRIVE:
                    download_file = self.main_window.question_dialog(
                        title="Unable To Stream File",
                        message=f"Unable to stream \"{filename}\" at this time.\n\nWould you like to download and play the file?"
                    ).future.result()
                    
                    if download_file:
                        file = lambda: None
                        file.id = input_str.split('/')[-1].split('?')[0]
                        file.name = filename
                        self.DownloadFileAndPlayInVLC(file)
                else:       
                    self.vlc_window.error_dialog(
                        "Unable To Play",
                        f"Unfortunately, VLC Player is unable to play {input_str} at this time."
                    )
                    self.StopVLC()
            else:
                self.vlc_window.title = f"{filename} - {VLC_PLAYER}"
                if not self.vlc_window.visible:
                    self.vlc_window._impl.native.WindowState = WinForms.FormWindowState.Minimized
                    self.vlc_window.show()
                self.vlc_window._impl.native.WindowState = WinForms.FormWindowState.Normal
                self.player_panel._impl.native.Focus()
                
                self.SetupAudioTracks()
                self.SetAudioTrackItems()
                self.AdjustDropDownWidth(self.audio_tracks)
                
                self.SetupSubtitles()
                self.SetSubtitleItems()
                self.SetSubtitlesInitial()
                self.AdjustDropDownWidth(self.subtitles)
                
                self.play_button.text=PAUSE

                if self.player.audio_get_mute():
                    self.mute_button.text = MUTE
                else:
                    self.mute_button.text = UNMUTE
            
    #endregion

    #region Get Folder Type
        
    def SetFolderType(self, folder_str):
        self.folder_type = self.GetFolderType(folder_str)
        
    def GetFolderType(self, folder_str):
        if self.IsGoogleDriveFolder(folder_str):
            return FolderType.GOOGLE_DRIVE    
        if self.IsLocalFolder(folder_str) or self.IsNetworkFolder(folder_str):
            return FolderType.LOCAL_OR_NETWORK
        return FolderType.INVALID
    
    def IsGoogleDriveFolder(self, folder_str):
        return folder_str[:39] == "https://drive.google.com/drive/folders/"
        
    def IsNetworkFolder(self, folder_str):
        return folder_str[:2] == "\\\\" or folder_str[:17] == "http://127.0.0.1:"
        
    def IsLocalFolder(self, folder_str):
        return folder_str[1:3] == ":\\" or folder_str[1:3] == ":/"
        
    #endregion

    #region Local Folder
    
    def BrowseLocalFolders(self, widget=''):
        selected_folder = self.main_window.select_folder_dialog(
            "Browse Local Folders",
            multiselect=False
        ).future.result()
        
        if selected_folder:
            self.folder_input.value = selected_folder
            self.OnClickGetFolderContents()
    
    def GetOneFolderUpLocal(self, folder_str):
        split_folder = folder_str[:-1].split('\\')[:-1]
        if len(split_folder):
            return '\\'.join(split_folder)+'\\'
        return folder_str
    
    def SetFolderTableLocal(self, folder_str, from_folder_repo=False):
        self.folder_type = FolderType.LOCAL_OR_NETWORK
        
        self.google_folder_id = ''
        
        folder_str = str(folder_str).replace('/', '\\').rstrip('\\')
        self.local_folder_path = folder_str
        folder_str += '\\'
        local_files = os.listdir(folder_str)
        local_data = [['..', self.GetOneFolderUpLocal(folder_str)]] + [*map(lambda file: [file, folder_str + file], local_files)]
        
        if from_folder_repo:
            local_data = [['...', FOLDER_REPO]] + local_data
        
        self.SetFolderTableFromData(local_data, self.OnDoubleClickLocalFile, ["Name", "Path"])
        
    def OpenLocalFile(self, file_path):
        file_path = str(file_path)
        print(f"DEBUG: Local File Path = \"{file_path}\"")
        
        if os.path.isdir(file_path):
            self.folder_input.value = file_path
            self.SetFolderTable(file_path)
        else:
            filename = file_path.split('\\')[-1]
            
            if self.IsPlayableWithVLC(filename):
                self.PlayWithVLC(file_path, filename)
            else:
                print(f"DEBUG: Opening {filename} with default app")
                os.startfile(file_path)
        
    def OnDoubleClickLocalFile(self, *args, **kwargs):
        file_path = kwargs["row"].path
        
        if file_path == FOLDER_REPO:
            self.SetFolderTableFolderRepo()
        else:
            self.OpenLocalFile(file_path)
        
    #endregion

    #region Google Drive
    
    def SetFolderTableFromGoogleDriveData(self, data, on_double_click):
        self.SetFolderTableFromData(data, on_double_click, ["Name", "ID"])
    
    def GetGoogleDriveFolderID(self, folder_url):
        return  folder_url.split('/')[-1].replace('?usp=share_link','')
    
    def SetFolderTableGoogleDrive(self, folder_url="", folder_id="", from_folder_repo=False):
        self.folder_type = FolderType.GOOGLE_DRIVE
        
        if not from_folder_repo:
            folder_id = self.GetGoogleDriveFolderID(folder_url)
            
        if (not self.google_authenticated) or self.gauth.access_token_expired or self.gauth.credentials is None:
            if not self.GoogleAuthenticate():
                return
        
        file_list = self.drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
        file_data = [*map(lambda file: [file['title'], file['id']], file_list)]
        
        self.google_folder_id = folder_id
        
        if from_folder_repo:
            file_data = [['..', FOLDER_REPO]] + file_data
        
        self.SetFolderTableFromGoogleDriveData(file_data, self.OnDoubleClickGoogleDriveFile)
        
    def OnDoubleClickGoogleDriveFile(self, *args, **kwargs):
        file = kwargs["row"]
        
        if file.id == FOLDER_REPO:
            self.SetFolderTableFolderRepo()
        else:
            self.OpenGoogleDriveFile(file)
        
    def OpenGoogleDriveFile(self, file):
        print(f"DEBUG: Google Drive File ID = \"{file.id}\"")
        
        download_file = self.main_window.question_dialog(
            title="Google Drive Download File",
            message=f"Would you like to download \"{file.name}\"?\n\nClick \"No\" to just play the file without downloading."
        ).future.result()
        
        if download_file:
            self.DownloadFileAndPlayInVLC(file)
        else:
            self.PlayGoogleDriveFileInVLC(file)
        
    def PlayGoogleDriveFileInVLC(self, file):
        url = self.GetGoogleDriveURL(file.id)
        self.PlayWithVLC(url, file.name)
    
    def GetGoogleDriveURL(self, file_id):
        return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={API_KEY}"
      
    #endregion
    
    #region Google Authentication
    
    def GoogleAuthentication(self, widget=''):
        if self.google_authenticated:
            return self.main_window.confirm_dialog(
                title="Already Google Authenticated",
                message="It appears that you have already signed in with your Google account.\n\nWould you like to proceed anyway?",
                on_result=self.GoogleReAuthenticate
            )
        else:
            return self.GoogleAuthenticate()
        
    def GoogleAuthenticate(self):
        expired = False
        error = False
        self.gauth = GoogleAuth()
        
        try:
            self.gauth.LoadCredentialsFile(CREDENTIALS_PATH)
        except Exception as err:
            print(err)

        if self.gauth.access_token_expired:
            try:
                self.gauth.Refresh()
            except Exception as err:
                print(err)
                expired = True
                
        if self.gauth.credentials is None or expired:
            self.main_window.info_dialog(
                title="Google Authentication",
                message="Please sign in to your Google Account."
            )
            try:
                self.gauth.LocalWebserverAuth()
            except Exception as err:
                print(err)
                error = True             
        else:
            try:
                self.gauth.Authorize()
            except Exception as err:
                print(err)
                error = True 
        
        if not error:
            try:
                self.gauth.SaveCredentialsFile(CREDENTIALS_PATH)
            except Exception as err:
                print(err)
                error = True
        
        if error:
            self.google_authenticated = False
            self.main_window.error_dialog(
                title="Google Authentication Failed",
                message="Google authentication failed. Please try again later."
            )
            return False
        
        self.gauth_token = self.gauth.credentials.access_token
        
        self.drive = GoogleDrive(self.gauth)
        self.google_authenticated = True
        
        return True
    
    def GoogleReAuthenticate(self, *args, **kwargs):
        if args[1]:
            self.GoogleAuthenticate()
        
    #endregion
    
    #region Folder Repo
    
        #region Save Folder
        
            #region Save Folder Window
    
    def InitTextEntryWindow(self, widget=''):
        text_entry_box = toga.Box(
            style=Pack(
                direction=COLUMN
            )
        )
        
        self.folder_name_input_label = toga.Label(
            text="Folder Name: ",
            style=Pack(
                padding=5
            )
        )

        self.folder_name_input = toga.TextInput(
            style=Pack(
                flex=1,
                padding=5
            ), 
            placeholder="Folder Name"
        )        
        self.folder_name_input._impl.native.KeyDown += self.folder_name_input_KeyDown

        self.folder_save_button = toga.Button(
            label="Save",
            on_press=self.SaveFolderToRepo,
            style=Pack(
                padding=5
            )
        )

        text_entry_box.add(self.folder_name_input_label)
        text_entry_box.add(self.folder_name_input)
        text_entry_box.add(self.folder_save_button)
        
        self.text_entry_window = toga.Window(
            title=GET_FOLDER, 
            closeable=False,
            size=(300,100)
        )
        
        self.text_entry_window._impl.native.FormClosing += self.folder_name_FormClosing
        
        self.windows.add(self.text_entry_window)
        self.text_entry_window.content = text_entry_box
    
    def folder_name_input_KeyDown(self, sender, event):
        if self.text_entry_window.visible:
            print(f"DEBUG: Key Entered To TextBox: {event.KeyCode}")
            if event.KeyCode == _ENTER:
                self.folder_save_button.on_press(widget='')
                event.Handled = True
    
    def folder_name_FormClosing(self, sender, event):
        print("DEBUG: Close Get Folder Name Window Clicked, Hiding Window Instead")
        event.Cancel = True
        self.CloseTextEntryWindow()

    def CloseTextEntryWindow(self):
        self.text_entry_window.hide()
        self.folder_name_input_label.text = "Folder Name: "
        self.folder_name_input.value = ''
        self.folder_save_button.on_press = self.SaveFolderToRepo
        self.text_entry_window.title = GET_FOLDER

            #endregion
            
            #region Save Folder Methods
            
    def ShowSaveFolderPrompt(self, widget=''):
        if not self.folder_table.data or self.folder_type == FolderType.FOLDER_REPO:
            return self.main_window.error_dialog(
                title="No Folder Open",
                message="You do not have a folder open.\n\nPlease open a folder and try again."
            )
        
        while not self.folder_repo_filename:
            import_repo = self.main_window.question_dialog(
                title="No Folder Repo Loaded",
                message="You have not loaded a Folder Repo.\n\nWould you like to import a Folder Repo?"
            ).future.result()
            
            if not import_repo:
                create_new_repo = self.main_window.question_dialog(
                    title="Create New Folder Repo",
                    message="Would you like to create a new Folder Repo?"
                ).future.result()
                
                if create_new_repo:
                    self.CreateFolderRepo(set_folder_table=False)
                    
                else:
                    return self.main_window.error_dialog(
                        title="No Folder Repo",
                        message="You did not import or create a Folder Repo."
                    )

            else:
                self.ImportFolderRepo(set_folder_table=False)
        
        self.folder_name_input.value = self.GetFolderName()
        self.text_entry_window._impl.native.ShowDialog(self.main_window._impl.native)
    
    def SaveUpdatedFolderRepo(self):
        with open(self.folder_repo_filename, "w", encoding='utf-8') as f:
            f.writelines([*map(','.join, self.folder_repo)])
    
    def SaveFolderToRepo(self, widget=''):
        folder_name = self.folder_name_input.value.replace(',','_')
        
        self.CloseTextEntryWindow()
        
        folder_location = self.folder_input.value
        
        if self.GetFolderType(folder_location) == FolderType.GOOGLE_DRIVE:
            folder_location = self.GetGoogleDriveFolderID(folder_location)
            
        self.folder_repo.append([folder_name, folder_location+'\n'])
        
        self.SaveUpdatedFolderRepo()
            
        self.SetFolderTableFolderRepo()

    def DeleteRowFromFolderTable(self, row):
        self.folder_repo.remove(row)          
        self.SaveUpdatedFolderRepo()
        self.SetFolderTableFolderRepo()

            #endregion
            
        #endregion
    
        #region Create Folder Repo
    
    def CreateFolderRepo(self, set_folder_table=True, widget=''):
        filename = self.main_window.save_file_dialog(
            title="Create Google Drive Repo",
            suggested_filename="repo.txt",
            file_types=["txt"]
        ).future.result()

        if filename:
            with open(filename, "w", encoding='utf-8') as f_repo:
                f_repo.write("")
            with open(REPO_PATH, "w", encoding='utf-8') as f_location:
                f_location.write(str(filename))

        self.folder_repo = [[]]
        self.folder_repo_filename = filename
        
        if set_folder_table:
            self.SetFolderTableFolderRepo()
            
        #endregion
    
        #region Import Folder Repo
    
    def ImportFolderRepo(self, set_folder_table=True, widget=''):
        filename = self.main_window.open_file_dialog(
            title="Import Google Drive Repo",
            file_types=["txt"]
        ).future.result()
        
        if filename:
            with open(REPO_PATH, "w", encoding='utf-8') as f:
                f.write(str(filename))
            
            self.ProcessFolderRepo(filename, set_folder_table)
    
    def ProcessFolderRepo(self, filename, set_folder_table=True):
        if set_folder_table:
            self.folder_type = FolderType.FOLDER_REPO
            
        folder_repo = [[]]
        
        with open(filename, "r", encoding='utf-8') as f:
            folder_repo = sorted([*map(lambda line: line.split(','), f.readlines())], key=lambda l: l[0])
            
        if self.invalid_folder_repo(folder_repo):
            self.show_folder_repo_err(folder_repo)
        
        else:
            self.folder_repo_filename = filename
            self.folder_repo = folder_repo
            
            if set_folder_table:
                self.SetFolderTableFolderRepo()
    
    def LoadFolderRepo(self, widget=''):
        if self.folder_repo_filename:
            self.SetFolderTableFolderRepo()
        
        elif os.path.isfile(REPO_PATH):
            with open(REPO_PATH, "r", encoding='utf-8') as f:
                path = f.read()
            if os.path.isfile(path):
                print(f"DEBUG: Automatically Loading Folder Repo At \"{path}\"")
                self.ProcessFolderRepo(path)
            else:
                self.show_folder_repo_err(path)
           
        #endregion
    
        #region Set Folder Table
        
    def SetFolderTableFolderRepo(self):
        self.folder_type = FolderType.FOLDER_REPO
        self.google_folder_id = ''
        
        self.SetFolderTableFromData(self.folder_repo, self.SetFolderTableFromFolderRepo, ['Name', 'Location'])
        
    def SetFolderTableFromFolderRepo(self, *args, **kwargs):
        folder = kwargs["row"].location.replace('\n', '')
        
        if self.IsLocalFolder(folder) or self.IsNetworkFolder(folder):
            self.SetFolderTableLocal(folder, from_folder_repo=True)
        else:
            self.SetFolderTableGoogleDrive(folder_id=folder, from_folder_repo=True)
        
        #endregion
        
        #region Validation and Errors
        
    def invalid_folder_repo(self, folder_repo):
        if len(folder_repo) == 0:
            return True
        if folder_repo == [[]]:
            return False
        if len(folder_repo) > 0 and any(map(lambda gd: len(gd) != 2, folder_repo)):
            return True
        return False
    
    def show_folder_repo_err(self, path):
        m_string = f"The Folder Repo at '{path}' is invalid.\n\n" \
                    "Please locate a valid Folder Repo or create a new one and try again."

        self.main_window.error_dialog(
            title="Invalid Folder Repo",
            message=m_string
        )
        
        #endregion
    
    #endregion
    
    #region Download Google Drive
    
        #region Progressbar Window
    
    def InitDownloadProgressBarWindow(self, widget=''):
        self.download_progress_label = toga.Label(
            text="Downloading File",
            style=Pack(padding=(5,0))
        )
        
        self.progress_bar = toga.ProgressBar(
            value=0,
            max=100
        )
        
        self.progress_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=5
            )
        )
        
        self.progress_box.add(self.download_progress_label)
        self.progress_box.add(self.progress_bar)
        
        self.progress_window = toga.Window(title=PROGRESS_WINDOW, closeable=False, size=(500,55))
        
        self.windows.add(self.progress_window)
        self.progress_window.content = self.progress_box
        
        self.progress_window.hide()
    
        #endregion
    
        #region Download Initialization
    
    def DownloadGoogleDriveFolder(self, widget=''):
        if self.google_folder_id:
            folder_name = self.GetFolderName()
            
            download_folder = self.main_window.select_folder_dialog(
                title="Select Download Folder",
                multiselect=False
            ).future.result()
            
            if not download_folder:
                download_folder = "%USERPROFILE%\\Downloads"
            download_file = f"{download_folder}\\%s" 
            
            file_list = self.drive.ListFile({'q': f"'{self.google_folder_id}' in parents and trashed=false"}).GetList()
            num_files = len(file_list)
            
            parts_per_file = ((NUM_DL_PARTS - 1) // num_files) + 1
            
            folder_size = sum(map(lambda f: int(f['fileSize']), file_list))
            self.download_progress_label.text = f"Downloading all files in \"{folder_name}\" ({round(folder_size / 2**20, 2):0.1f} MB)"
            self.progress_bar.max = folder_size + ((parts_per_file - 1) * num_files)
            self.progress_bar.value = 0
            
            print(f"\nDownloading folder \"{folder_name}\"\nFolder size: {folder_size}\n")
            
            async def CustomDownloadFolder(widget, **kwargs):
                self.progress_window.show()
                self.progress_bar.start()
                
                await asyncio.gather(*map(lambda i, file: asyncio.create_task(self.DownloadFile(File(file['id'], file['title'], file['fileSize']), download_file % file['title'], True, parts_per_file)), *zip(*enumerate(sorted(file_list, key = lambda x: x['title']), start=1))))
                
                self.progress_bar.stop()
                self.progress_window.hide()
                
                open_folder = self.main_window.question_dialog(
                    title="Opening Download Folder",
                    message=f"Finished downloading files in \"{folder_name}\"!\n\nWould you like to open the download folder?"
                ).future.result()
                
                if open_folder:
                    self.SetFolderTableLocal(download_folder)
            
            self.app.add_background_task(CustomDownloadFolder)
                        
        else:
            self.main_window.error_dialog(
                title="No Google Drive Folder Selected",
                message="Please open a Google Drive folder and try again."
            )
    
    def DownloadFileAndPlayInVLC(self, _file):        
        download_path = self.main_window.save_file_dialog(
            title="Save File From Google Drive",
            suggested_filename=_file.name
        ).future.result()
        
        if not download_path:
            return
            
        gdrive_file = self.drive.CreateFile({'id': _file.id})
        gdrive_file.FetchMetadata(fields='fileSize')
        
        file = File(_file.id, _file.name, gdrive_file.metadata['fileSize'])
        
        self.download_progress_label.text = f"Downloading \"{file.name}\" ({file.GetSizeMB():0.1f} MB)"
        self.progress_bar.max = file.size + NUM_DL_PARTS - 1
        self.progress_bar.value = 0
        
        print(f"\nDownloading file \"{download_path}\"\nFile size: {file.size}\n")
        
        async def CustomDownloadFile(widget, **kwargs):
            self.progress_window.show()
            self.progress_bar.start()
            
            # Each partial download is limited to 20 mbps and my internet speed is 250 mbps, 
            # so I chose NUM_DL_PARTS = 12 because 12 * 20 mbps = 240 mbps. 
            # You can adjust this number according to your own internet speed.
            await self.DownloadFile(file, download_path, True, NUM_DL_PARTS)
            
            self.progress_bar.stop()
            self.progress_window.hide()
            
            open_file = self.main_window.question_dialog(
                title="Download Finished",
                message=f"Finished downloading \"{file.name}\"!\n\nWould you like to play the file?"
            ).future.result()
            
            if open_file:
                row = lambda: None
                row.path = download_path
                
                self.OnDoubleClickLocalFile(row=row)
        
        self.app.add_background_task(CustomDownloadFile)
    
        #endregion
    
        #region Asynchronous Downloads
    
    async def DownloadPart(self, file, show_progress_bar, start_byte, end_byte):
        async with aiohttp.ClientSession(read_bufsize=MIN_CHUNK_SIZE) as client:
            data = await self.FetchFile(client, file, show_progress_bar, partitioned=True, start_byte=start_byte, end_byte=end_byte)
            
        return data

    async def DownloadFile(self, file : File, download_path, show_progress_bar, num_parts=None):
        if num_parts and file.size >= (MIN_CHUNK_SIZE*100):
            data_list = await asyncio.gather(*map(lambda part: self.DownloadPart(file, show_progress_bar, part[0], part[1]), file.CreatePartitions(num_parts)))
            
            if not data_list or not all(data_list):
                data = None
            else:
                data = reduce(lambda a, b: a + b, data_list)
                    
        else:
            async with aiohttp.ClientSession(read_bufsize=MIN_CHUNK_SIZE) as client:
                data = await self.FetchFile(client, file, show_progress_bar)
                
        if not data:
            self.main_window.error_dialog(
                title="Download Failed",
                message=f"Failed to download \"{file.name}\". Please try again later."
            )
            return
        
        async with aiofiles.open(download_path, "wb") as f:
            await f.write(data)

        print(f"\nFinished Downloading \"{file.name}\"!\n")

    async def FetchFile(self, client : aiohttp.ClientSession, file : File, show_progress_bar, partitioned=False, start_byte=None, end_byte=None):
        headers = {"Authorization": f"Bearer {self.gauth_token}",
                   "Accept": "application/json"}
        params = {"supportsAllDrives": "true"}
        
        download_string = f"Downloading \"{file.name}\""
        
        if partitioned:
            headers["Range"] = f"bytes={start_byte}-{end_byte}"
            download_string += f" from byte {start_byte} to {end_byte} ({end_byte - start_byte} bytes)"
        
        print(download_string)
        
        async with client.get(self.GetGoogleDriveURL(file.id), params=params, headers=headers) as resp:
            if resp.status in [200, 206]:
                data = bytearray()
                if show_progress_bar and file.chunk_size >= MIN_CHUNK_SIZE:
                    async for chunk, _ in resp.content.iter_chunks():
                        data += chunk
                        self.progress_bar.value += len(chunk)
                    data = await self.FixTrashData(data, start_byte, end_byte)
                    
                else:
                    data = await resp.content.read()
                
                return data
            
            else:
                print(f"ERROR: Ecountered an error while {download_string}\nResponse Status: {resp.status}\nResponse Content: {resp.content}")
                return None
    
    async def FixTrashData(self, data, start_byte, end_byte):
        data_len = len(data)
        difference = data_len - (end_byte - start_byte)
        print(f"\nDownloaded {data_len}, Expected {end_byte - start_byte}; Difference = {difference}{f' ({data[-difference:]})' if difference else ''}")
        
        if (difference > 0):
            data = data[:-difference]
            data_len = len(data)
            difference = data_len - (end_byte - start_byte)
            print(f"After fix: Downloaded {data_len}, Expected {end_byte - start_byte}; Difference = {difference}")
            
        return data

        #endregion
        
    #endregion
    
    #region Full Screen Overrides
    
    def set_full_screen(self, *windows):
        if not windows:
            self.exit_full_screen()
        else:
            windows[0]._impl.native.WindowState = WinForms.FormWindowState.Normal
            windows[0]._impl.native.FormBorderStyle = getattr(WinForms.FormBorderStyle,'None')
            windows[0]._impl.native.WindowState = WinForms.FormWindowState.Maximized
            self._full_screen_windows = windows
        
    def exit_full_screen(self):
        if self.is_full_screen:
            for window in self._full_screen_windows:
                window._impl.native.FormBorderStyle = WinForms.FormBorderStyle.Sizable
                window._impl.native.WindowState = WinForms.FormWindowState.Normal
            self._full_screen_windows = None
    
    #endregion
        
    #region Folder Table
    
    def InitFolderTable(self):
        self.folder_type = FolderType.INVALID
        self.folder_table = toga.Table(
            headings=[],
            data=[],
            style=Pack(
                flex=1, 
                padding=5
            )
        )
        self.folder_table._impl.native.KeyDown += self.folder_table_KeyDown
        self.folder_repo = [[]]
        self.folder_repo_filename = ''
        
        self.LoadFolderRepo()
        
    def folder_table_KeyDown(self, sender, event):
        print(f"DEBUG: Key Entered In Folder Table: {event.KeyCode}")
        if event.KeyCode == _DELETE:
            if self.folder_table.selection and self.folder_type == FolderType.FOLDER_REPO:
                folder_name = self.folder_table.selection.name
                folder_location = self.folder_table.selection.location
                delete_from_repo = self.main_window.question_dialog(
                    "Remove Folder From Repo",
                    f"Would you like to remove the folder \"{folder_name}\" from your folder repo?"
                ).future.result()
                
                if delete_from_repo:
                    row = [folder_name, folder_location]
                    self.DeleteRowFromFolderTable(row)
        if event.KeyCode == _ENTER:
            if self.folder_table.selection:
                if self.folder_type == FolderType.FOLDER_REPO:
                    self.SetFolderTableFromFolderRepo(row = self.folder_table.selection)
                if self.folder_type == FolderType.GOOGLE_DRIVE:
                    self.OnDoubleClickGoogleDriveFile(row = self.folder_table.selection)
                if self.folder_type == FolderType.LOCAL_OR_NETWORK:
                    self.OnDoubleClickLocalFile(row = self.folder_table.selection)
        if event.KeyCode == _R:
            if self.folder_table.selection and self.folder_type == FolderType.FOLDER_REPO:
                self.old_folder_name = self.folder_table.selection.name
                self.folder_location = self.folder_table.selection.location
                
                self.folder_name_input.value = self.old_folder_name
                self.folder_name_input_label.text = f"Rename \"{self.old_folder_name}\": "
                self.text_entry_window.title = RENAME_FOLDER
                self.folder_save_button.on_press = self.RenameFolderRepoFolder
                self.text_entry_window._impl.native.ShowDialog(self.main_window._impl.native)
     
    def RenameFolderRepoFolder(self, widget=''):
        old_folder_name = self.old_folder_name
        folder_location = self.folder_location
        folder_name = self.folder_name_input.value.replace(',','_')

        self.CloseTextEntryWindow()
        
        try:
            index = self.folder_repo.index([old_folder_name, folder_location])
            self.folder_repo[index] = [folder_name, folder_location]
            
            self.SaveUpdatedFolderRepo()
                
            self.SetFolderTableFolderRepo()
        except Exception as err:
            print(f"DEBUG: ERROR WHILE RENAMING FOLDER\n\n{err}\n\n")
            self.main_window.error_dialog(
                title="Error While Renaming Folder",
                message=f"Unfortunately there was an error while renaming the folder from \"{old_folder_name}\" to \"{folder_name}\". Please try again later."
            )
        
    def SetFolderTableFromData(self, data, on_double_click, headings):
        self.main_box.remove(self.folder_table)
        
        self.folder_table = toga.Table(
            headings=headings,
            data=data,
            style=Pack(
                flex=1, 
                padding=5
            ),
            on_double_click=on_double_click
        )
        self.folder_table._impl.native.KeyDown += self.folder_table_KeyDown
        
        if len(headings) > 0:
            self.folder_table._impl.native.Columns[0].Width = 400
            if len(headings) == 2:
                self.folder_table._impl.native.Columns[1].Width = 200
        
        self.main_box.add(self.folder_table)
        self.main_window.title = f"{self.formal_name} - {self.GetFolderName()}"
        self.folder_table.focus()
        
    def SetFolderTable(self, folder_str):
        if self.folder_type == FolderType.INVALID:
            return self.main_window.error_dialog(
                title="Invalid Input",
                message="Please enter a valid folder location."
            )
        
        if self.folder_type == FolderType.GOOGLE_DRIVE:
            self.SetFolderTableGoogleDrive(folder_url=folder_str)
        elif self.folder_type == FolderType.LOCAL_OR_NETWORK:
            self.SetFolderTableLocal(folder_str)
         
    #endregion
    
    def GetFolderName(self):
        if self.folder_type == FolderType.GOOGLE_DRIVE:
            folder = self.drive.CreateFile({'id': self.google_folder_id})
            folder.FetchMetadata(fields='title')
            return folder['title']
        if self.folder_type == FolderType.LOCAL_OR_NETWORK:
            folder = self.local_folder_path
            path_list = folder.split('\\')
            return path_list[-1]
        if self.folder_type == FolderType.FOLDER_REPO:
            return 'Folder Repo'
        return ''
        
    def OnClickGetFolderContents(self, widget=''):
        folder_str = self.folder_input.value
        self.SetFolderType(folder_str)
        
        if self.folder_type == FolderType.GOOGLE_DRIVE and not self.google_authenticated:
            if not self.GoogleAuthentication():
                return
            
        self.SetFolderTable(folder_str)
   

def main():
    return KMExplorer()
