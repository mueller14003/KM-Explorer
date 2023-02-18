"""
Play media from local, network, and Google Drive folders
"""
import os
import vlc
from time import sleep
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from enum import Enum
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, RIGHT, LEFT, HIDDEN, VISIBLE, TOP, BOTTOM
from toga_winforms.libs.winforms import WinForms

TESTING = False
START_PATH = ['app','src'][TESTING]
RESOURCES = f"{START_PATH}\\kmexplorer\\resources"

REPO_PATH = f"{RESOURCES}\\repo.txt"

CLIENT_SECRETS_PATH = f"{RESOURCES}\\client_secrets.json"
GoogleAuth.DEFAULT_SETTINGS['client_config_file'] = CLIENT_SECRETS_PATH

CREDENTIALS_PATH = f"{RESOURCES}\\user_creds.json"

FOLDER_REPO = "Folder Repo"
VLC_PLAYER =  "VLC Player"
GET_FOLDER = "Enter Folder Name"
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

_UP = WinForms.Keys.Up
_DOWN = WinForms.Keys.Down
_LEFT = WinForms.Keys.Left
_RIGHT = WinForms.Keys.Right

ARROW_KEYS = [
    _UP,
    _DOWN,
    _LEFT,
    _RIGHT
]

class FolderType(Enum):
    INVALID = 0
    LOCAL_OR_NETWORK = 1
    GOOGLE_DRIVE = 2
    FOLDER_REPO = 3

#region Startup

class KMExplorer(toga.App):
    def startup(self):
        self.google_authenticated = False
        self.drive = GoogleDrive()
        self.google_folder_id = ''
        self.mouse_hidden = False
        self.counter = 0
        
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
            shortcut=toga.Key.MOD_1 + toga.Key.P,
            group=vlc_group,
            icon=toga.Icon.TOGA_ICON,
            section=0
        )

        stop = toga.Command(
            self.StopVLC,
            label="Stop VLC",
            shortcut=toga.Key.MOD_1 + toga.Key.X,
            group=vlc_group,
            section=0
        )
        
        fullscreen = toga.Command(
            self.ToggleFullscreenVLC,
            label="Toggle Fullscreen",
            shortcut=toga.Key.MOD_1 + toga.Key.F,
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
            load_folder_repo
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
        self.InitVLCWindow()

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
        self.vlc_window._impl.native.PreviewKeyDown += self.control_PreviewKeyDown
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
        
        control_box._impl.native.PreviewKeyDown += self.control_PreviewKeyDown
        
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
            on_slide=self.SetVolume
        )
        
        self.volume_slider_label = toga.Label(
            text=f"Volume: {volume}%",
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
            control._impl.native.PreviewKeyDown += self.control_PreviewKeyDown
        
        self.control_box = control_box         
    
        #endregion
        
        #region Event Handler Overrides
    
    def player_panel_MouseMove(self, sender, event):
        self.counter = 0
        if self.mouse_hidden:
            print("DEBUG: Show Mouse")
            self.mouse_hidden = False
            self.player_panel._impl.native.Cursor.Show()
            self.player_panel._impl.native.ResetMouseEventArgs()
    
    def player_panel_MouseHover(self, sender, event):
        if self.counter >= 3:
            print("DEBUG: Hide Mouse")
            self.mouse_hidden = True
            self.player_panel._impl.native.Cursor.Hide()
        else:
            self.counter += 1
            self.player_panel._impl.native.ResetMouseEventArgs()
       
    def control_PreviewKeyDown(self, sender, event):
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
        
    def GetCurrentWindow(self):
        return self.main_window._impl.native.ActiveForm
        
    def vlc_window_FormClosing(self, sender, event):
        active_form = self.GetCurrentWindow()
        if VLC_PLAYER in active_form.Text:
            print("DEBUG: Close VLC Window Clicked, Hiding VLC Window And Stopping Playback Instead")
            event.Cancel = True
            self.StopVLC()
        
    def player_panel_DoubleClick(self, sender, event):
        print("DEBUG: Double-Click On Player Panel - Toggling Fullscreen")
        self.ToggleFullscreenVLC()
        
        #endregion
            
        #region VLC Player Functions
        
    def SetVolume(self, widget):
        volume = int(widget.value)
        self.volume_slider_label.text = f"Volume: {volume}%"
        self.player.audio_set_volume(volume)
        
    def VolumeUp(self, widget=''):
        volume = int(self.volume_slider.value)
        volume += 5 - (volume % 5) - ((volume // 100) * 5)
        self.volume_slider.value = volume
        self.volume_slider_label.text = f"Volume: {volume}%"
        self.player.audio_set_volume(volume)
    
    def VolumeDown(self, widget=''):
        volume = int(self.volume_slider.value)
        volume -= (volume > 0) * ((volume % 5) + ((volume % 5 == 0) * 5))
        self.volume_slider.value = volume
        self.volume_slider_label.text = f"Volume: {volume}%"
        self.player.audio_set_volume(volume)
    
    def ToggleVisibleVLC(self, widget=''):
        if self.vlc_window.visible:
            print("DEBUG: Hiding VLC Window")
            self.vlc_window.hide()
        else:
            print("DEBUG: Showing VLC Window")
            self.vlc_window.show()
    
    def StopVLC(self, widget='', hide=True):
        print("DEBUG: Stopping VLC Playback, Exiting Fullscreen, And Hiding Window")
        self.player.stop()
        self.vlc_window.title = VLC_PLAYER
        self.exit_full_screen()
        self.RefreshControlMenu()
        if hide:
            self.vlc_window.hide()

    def RefreshControlMenu(self, widget=''):
        if self.vlc_window.visible:
            if self.vlc_box.children.__contains__(self.control_box):
                print("DEBUG: Disposing of old Control Menu")
                self.vlc_box.remove(self.control_box)

            print("DEBUG: Creating new Control Menu")
            self.InitControlBox()
            self.vlc_box.add(self.control_box)

    def ToggleControlMenu(self, widget=''):
        if self.vlc_window.visible:
            if self.vlc_box.children.__contains__(self.control_box):
                print("DEBUG: Hiding Control Menu")
                self.vlc_box.remove(self.control_box)
            else:
                print("DEBUG: Showing Control Menu")
                self.InitControlBox(
                    self.play_button.text, 
                    self.mute_button.text,
                    self.audio_tracks.items,
                    self.subtitles.items,
                    self.audio_tracks.value,
                    self.subtitles.value
                )
                self.vlc_box.add(self.control_box)
    
    def ToggleFullscreenVLC(self, widget=''):
        if self.vlc_window.visible:
            if self.is_full_screen:
                print("DEBUG: Exiting Fullscreen")
                self.exit_full_screen()
                if not self.vlc_box.children.__contains__(self.control_box):
                    self.InitControlBox(
                        self.play_button.text, 
                        self.mute_button.text,
                        self.audio_tracks.items,
                        self.subtitles.items,
                        self.audio_tracks.value,
                        self.subtitles.value
                    )
                    self.vlc_box.add(self.control_box)
            else:
                print("DEBUG: Entering Fullscreen")
                if self.vlc_box.children.__contains__(self.control_box):
                    self.vlc_box.remove(self.control_box)
                self.set_full_screen(self.vlc_window)
    
    def ToggleMute(self, widget=''):
        if self.player.will_play():
            if self.player.audio_get_mute():
                print("DEBUG: Unmuting Audio")
                self.mute_button.text = UNMUTE
            else:
                print("DEBUG: Muting Audio")
                self.mute_button.text = MUTE
                
            self.player.audio_toggle_mute()
    
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
        
    def PlayWithVLC(self, input_str):
        print(f"DEBUG: Playing {input_str} With VLC")
        media = self.VLC_instance.media_new(input_str)
        if self.folder_type == FolderType.GOOGLE_DRIVE:
            http_token = f"--http-token=\'Authorization: Bearer {self.gauth_token}\'"
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
                self.vlc_window.error_dialog(
                    "Unable To Play",
                    f"Unfortunately, VLC Player is unable to play {input_str} at this time."
                )
                self.StopVLC()
            else:
                title = media.get_meta(vlc.Meta.Title)
                self.vlc_window.title = f"{title} - {VLC_PLAYER}"
                self.vlc_window.show()
                
                self.SetupAudioTracks()
                self.SetAudioTrackItems()
                
                self.SetupSubtitles()
                self.SetSubtitleItems()
                self.SetSubtitlesInitial()
                
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
    
    def SetFolderTableLocal(self, folder_str):
        self.google_folder_id = ''
        
        folder_str.replace('/', '\\')
        folder_str += '\\' if folder_str[-1] != '\\' else ''
        local_files = os.listdir(folder_str)
        local_data = [['..', self.GetOneFolderUpLocal(folder_str)]] + [*map(lambda file: [file, folder_str + file], local_files)]
        
        self.SetFolderTableFromData(local_data, self.OnDoubleClickLocalFile, ["Name", "Path"])
        
    def OpenLocalFile(self, file_path):
        print(f"DEBUG: Local File Path = \"{file_path}\"")
        
        if os.path.isdir(file_path):
            self.folder_input.value = file_path
            self.SetFolderTable(file_path)
        else:
            self.PlayWithVLC(file_path)
        
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
    
    def GetGoogleDriveFolderID(self, folder_str):
        return  folder_str.split('/')[-1].replace('?usp=share_link','')
    
    def SetFolderTableGoogleDrive(self, folder_str):
        folder_id = self.GetGoogleDriveFolderID(folder_str)
        
        file_list = self.drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
        file_data = [*map(lambda file: [file['title'], file['id']], file_list)]
        
        self.google_folder_id = folder_id
        
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
            self.PlayGoogleDriveFileInVLC(file.id)
        
    def PlayGoogleDriveFileInVLC(self, file_id):
        url = self.GetGoogleDriveURL(file_id)
        self.PlayWithVLC(url)
    
    def GetGoogleDriveURL(self, file_id):
        return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key=AIzaSyAkP3QKVLA4Vp5OwpHxsMRbzujnqmj7JA8"
      
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
        
    def GoogleAuthenticate(self,*args):
        expired = False
        error = False
        gauth = GoogleAuth()
        
        try:
            gauth.LoadCredentialsFile(CREDENTIALS_PATH)
        except Exception as err:
            print(err)

        if gauth.access_token_expired:
            try:
                gauth.Refresh()
            except Exception as err:
                print(err)
                expired = True
                
        if gauth.credentials is None or expired:
            self.main_window.info_dialog(
                title="Google Authentication",
                message="Please sign in to your Google Account."
            )
            try:
                gauth.LocalWebserverAuth()
            except Exception as err:
                print(err)
                error = True             
        else:
            try:
                gauth.Authorize()
            except Exception as err:
                print(err)
                error = True 
        
        if not error:
            try:
                gauth.SaveCredentialsFile(CREDENTIALS_PATH)
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
        
        self.gauth_token = gauth.credentials.access_token
        
        self.drive = GoogleDrive(gauth)
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
        
        input_label = toga.Label(
            text="Google Drive Folder Name: ",
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
        self.folder_name_input._impl.native.KeyPress += self.OnEnterPress

        button = toga.Button(
            label="Save Folder",
            on_press=self.SaveFolderToRepo,
            style=Pack(
                padding=5
            )
        )

        text_entry_box.add(input_label)
        text_entry_box.add(self.folder_name_input)
        text_entry_box.add(button)
        
        self.text_entry_window = toga.Window(
            title=GET_FOLDER, 
            closeable=False,
            size=(300,100)
        )
        
        self.text_entry_window._impl.native.FormClosing += self.folder_name_FormClosing
        
        self.windows.add(self.text_entry_window)
        self.text_entry_window.content = text_entry_box
    
    def folder_name_FormClosing(self, sender, event):
        if list(self.windows.elements)[0]._impl.native.ActiveForm.Text == GET_FOLDER:
            print("DEBUG: Close Get Folder Name Window Clicked, Hiding Window Instead")
            event.Cancel = True
            self.folder_name_input.value = ''
            self.text_entry_window.hide()

            #endregion
            
            #region Save Folder Methods
            
    def ShowSaveFolderPrompt(self, widget=''):
        if not self.folder_table.data:
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
            
        self.folder_name_input.value = ''
        self.text_entry_window.show()
    
    def SaveUpdatedFolderRepo(self):
        with open(self.folder_repo_filename, "w", encoding='utf-8') as f:
            f.writelines([*map(','.join, self.folder_repo)])
    
    def SaveFolderToRepo(self, widget=''):
        self.text_entry_window.hide()
        folder_name = self.folder_name_input.value.replace(',','_')
        
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
            folder_repo = [*map(lambda line: line.split(','), f.readlines())]
            
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
            self.SetFolderTableLocalFromFolderRepo(folder)
        else:
            self.SetFolderTableGoogleDriveFromFolderRepo(folder)
        
    def SetFolderTableGoogleDriveFromFolderRepo(self, folder_id):
        self.folder_type = FolderType.GOOGLE_DRIVE
        
        if not self.google_authenticated:
            if not self.GoogleAuthentication():
                return
        
        file_list = self.drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
        file_data = [*map(lambda file: [file['title'], file['id']], file_list)]
        
        self.google_folder_id = folder_id
        
        file_data = [['..', FOLDER_REPO]] + file_data
        
        self.SetFolderTableFromGoogleDriveData(file_data, self.OnDoubleClickGoogleDriveFile)
    
    def SetFolderTableLocalFromFolderRepo(self, folder_path):
        self.folder_type = FolderType.LOCAL_OR_NETWORK
        
        self.google_folder_id = ''

        folder_path.replace('/', '\\')
        folder_path += '\\' if folder_path[-1] != '\\' else ''
        local_files = os.listdir(folder_path)
        local_data = [['...', FOLDER_REPO]] + [['..', self.GetOneFolderUpLocal(folder_path)]] + [*map(lambda file: [file, folder_path + file], local_files)]
        
        self.SetFolderTableFromData(local_data, self.OnDoubleClickLocalFile, ["Name", "Path"])
        
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
    
    def DownloadGoogleDriveFolder(self, widget=''):
        if self.google_folder_id:
            download_folder = self.main_window.select_folder_dialog(
                title="Select Download Folder",
                multiselect=False
            ).future.result()
            
            if not download_folder:
                download_folder = "%USERPROFILE%\\Downloads"
            
            file_list = self.drive.ListFile({'q': f"'{self.google_folder_id}' in parents and trashed=false"}).GetList()
            
            for i, file in enumerate(sorted(file_list, key = lambda x: x['title']), start=1):
                print('Downloading {} from Google Drive ({}/{})'.format(file['title'], i, len(file_list)))
                file.GetContentFile(f"{download_folder}\{file['title']}")
                
            self.SetFolderTableLocal(download_folder)
        else:
            self.main_window.error_dialog(
                title="No Google Drive Folder Selected",
                message="Please open a Google Drive folder and try again."
            )
    
    def DownloadFileAndPlayInVLC(self, file):
        download_path = self.main_window.save_file_dialog(
            title="Save File From Google Drive",
            suggested_filename=file.name
        ).future.result()
        
        if not download_path:
            download_path = f"%USERPROFILE%\\Downloads\\{file.name}"
            
        print(f"DEBUG: Downloading file \"{download_path}\"")
            
        gdrive_file = self.drive.CreateFile({'id': file.id})
        gdrive_file.GetContentFile(download_path)
        
        row = lambda: None
        row.path = download_path
        
        self.OnDoubleClickLocalFile(row=row)
    
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
            self.folder_table._impl.native.Columns[0].Width = 300
            if len(headings) == 2:
                self.folder_table._impl.native.Columns[1].Width = 200
        
        self.main_box.add(self.folder_table)
        
    def SetFolderTable(self, folder_str):
        if self.folder_type == FolderType.INVALID:
            return self.main_window.error_dialog(
                title="Invalid Input",
                message="Please enter a valid folder location."
            )
        
        if self.folder_type == FolderType.GOOGLE_DRIVE:
            self.SetFolderTableGoogleDrive(folder_str)
        elif self.folder_type == FolderType.LOCAL_OR_NETWORK:
            self.SetFolderTableLocal(folder_str)
         
    #endregion
            
    def OnClickGetFolderContents(self, widget=''):
        folder_str = self.folder_input.value
        self.SetFolderType(folder_str)
        
        if self.folder_type == FolderType.GOOGLE_DRIVE and not self.google_authenticated:
            if not self.GoogleAuthentication():
                return
            
        self.SetFolderTable(folder_str)
   

def main():
    return KMExplorer()
