-- CrossChat for OBS. Add it in OBS with Tools > Scripts > +.
-- It starts the CrossChat hub (hub\hub.py) alongside OBS. The hub follows OBS from there: it opens the chat window
-- when the stream starts, closes it after the stream ends, and leaves when OBS closes. The buttons below and the
-- hotkeys (Settings > Hotkeys, "CrossChat: ...") ask the hub for things.
local obs = obslua
local ffi = require("ffi")
local bit = require("bit")
local WINDOWS = ffi.os == "Windows"   -- anything else is a Mac or Linux: there the hub is started with posix_spawn
local LINUX = ffi.os == "Linux"       -- Linux: started like on a Mac, with Linux's own folders

if WINDOWS then pcall(ffi.cdef, [[
  int MultiByteToWideChar(unsigned int page, unsigned long flags, const char* text, int size, wchar_t* out, int room);
  void* ShellExecuteW(void* hwnd, const wchar_t* operation, const wchar_t* file, const wchar_t* parameters,
                      const wchar_t* directory, int show);
  int WideCharToMultiByte(unsigned int page, unsigned long flags, const wchar_t* text, int size, char* out, int room,
                          const char* fallback, int* used);
  unsigned long GetCurrentProcessId(void);
  unsigned long GetFileAttributesW(const wchar_t* path);
  unsigned long GetModuleFileNameW(void* module, wchar_t* out, unsigned long room);
  const wchar_t* GetCommandLineW(void);
  typedef struct {
    unsigned long cbSize; unsigned long fMask; void* hwnd; const wchar_t* lpVerb; const wchar_t* lpFile;
    const wchar_t* lpParameters; const wchar_t* lpDirectory; int nShow; void* hInstApp; void* lpIDList;
    const wchar_t* lpClass; void* hkeyClass; unsigned long dwHotKey; void* hIconOrMonitor; void* hProcess;
  } CROSSCHAT_SHELLEXECUTEINFOW;
  int ShellExecuteExW(CROSSCHAT_SHELLEXECUTEINFOW* info);
  int GetExitCodeProcess(void* process, unsigned long* code);
  int CloseHandle(void* handle);
  void* CreateThread(void* security, size_t stack, void* start, void* parameter, unsigned long flags, unsigned long* id);
  typedef struct {
    unsigned int cbSize; void* hwndOwner; void* hInstance; const wchar_t* lpszText; const wchar_t* lpszCaption;
    unsigned long dwStyle; const wchar_t* lpszIcon; size_t dwContextHelpId; void* lpfnMsgBoxCallback; unsigned long dwLanguageId;
  } CROSSCHAT_MSGBOXPARAMSW;
  int MessageBoxIndirectW(const CROSSCHAT_MSGBOXPARAMSW* params);
]]) else pcall(ffi.cdef, [[
  int posix_spawn(int* pid, const char* path, void* const* actions, const void* attributes, char* const argv[], char* const envp[]);
  int posix_spawnp(int* pid, const char* file, void* const* actions, const void* attributes, char* const argv[], char* const envp[]);
  int posix_spawn_file_actions_init(void** actions);
  int posix_spawn_file_actions_addopen(void** actions, int fd, const char* path, int flags, unsigned short mode);
  int posix_spawn_file_actions_destroy(void** actions);
  int posix_spawnattr_init(void** attributes);
  int posix_spawnattr_setflags(void** attributes, short flags);
  int posix_spawnattr_destroy(void** attributes);
  int waitpid(int pid, int* status, int options);
  int getpid(void);
  int access(const char* path, int mode);
  char*** _NSGetEnviron(void);
]]) end
if LINUX then
  pcall(ffi.cdef, "char** environ;")                   -- (a Mac hands its environment over through _NSGetEnviron)
  pcall(ffi.cdef, [[
    int pipe2(int fds[2], int flags);
    int close(int fd);
    int posix_spawn_file_actions_adddup2(void** actions, int fd, int newfd);
    int posix_spawn_file_actions_addclose(void** actions, int fd);
    int posix_spawn_file_actions_addclosefrom_np(void** actions, int from);
    int fcntl(int fd, int cmd, ...);
  ]])
end
local kernel32 = WINDOWS and ffi.load("kernel32") or nil
local shell32 = WINDOWS and ffi.load("shell32") or nil
local user32 = WINDOWS and ffi.load("user32") or nil
local SEP = WINDOWS and "\\" or "/"

local VERSION = "1.9.0"
local DEFAULT_PORT = 4466
local python_setting = ""
local hotkeys = {}
-- Each hub is { process = its handle (Windows) or pid, pipe = OBS's end of its pipe (Flatpak) }.
local running_hub = nil       -- the hub this script started, watched so a crash doesn't leave you without chat
local second_hub = nil        -- one started while that one runs ("Start the hub again"): it ends at once if that one still answers
local restarts = {}           -- when it was restarted, to give up on a hub that can't stay up
local STILL_ACTIVE = 259
local ALREADY_RUNNING = 3     -- the hub's exit code when another CrossChat hub already answers on its port

-- Windows wants UTF-16; OBS and Lua speak UTF-8 (so folders with accents or other scripts work).
local function wide(text)
  local size = kernel32.MultiByteToWideChar(65001, 0, text, -1, nil, 0)
  local out = ffi.new("wchar_t[?]", size)
  kernel32.MultiByteToWideChar(65001, 0, text, -1, out, size)
  return out
end

local function narrow(text)
  local size = kernel32.WideCharToMultiByte(65001, 0, text, -1, nil, 0, nil, nil)
  local out = ffi.new("char[?]", size)
  kernel32.WideCharToMultiByte(65001, 0, text, -1, out, size, nil, nil)
  return ffi.string(out)
end

local function exists(path)
  return kernel32.GetFileAttributesW(wide(path)) ~= 0xFFFFFFFF
end

-- ShellExecute hidden: no console window flashes (os.execute and io.popen both flash one)
local function run(file, parameters, directory)
  local done = shell32.ShellExecuteW(nil, wide("open"), wide(file), parameters and wide(parameters) or nil,
                                     directory and wide(directory) or nil, 0)
  return tonumber(ffi.cast("intptr_t", done)) > 32
end

-- The CrossChat folder: the one above this script's obs folder.
local function app_folder()
  if not WINDOWS then
    return script_path() .. ".."
  end
  return ((script_path() .. ".."):gsub("/", "\\"))
end

-- macOS and Linux: programs are started with posix_spawn (no shell, so nothing to quote) and collected with
-- waitpid, so the watchdog below sees the hub's exit code just as it does on Windows.
local helpers = {}            -- other programs started from here, collected once they finish (or they'd linger as zombies)

-- Linux: a started program gets standard input, output and error, never the files and sockets OBS has open (its
-- WebSocket port among them: a hub holding that would keep an OBS started again from listening). glibc 2.34 and newer
-- close them all in one step; on older ones, each one OBS has open right now.
local CLOSEFROM = LINUX and pcall(function() return ffi.C.posix_spawn_file_actions_addclosefrom_np end)

local function close_the_rest(actions)
  if CLOSEFROM then
    ffi.C.posix_spawn_file_actions_addclosefrom_np(actions, 3)
    return
  end
  for fd = 3, 1023 do
    if ffi.C.fcntl(fd, 1) ~= -1 then                   -- F_GETFD: it's open
      ffi.C.posix_spawn_file_actions_addclose(actions, fd)
    end
  end
end

local function spawn(argv, stdin)
  local args = ffi.new("char*[?]", #argv + 1)          -- zero-filled, so the list ends with NULL
  local keep = {}
  for i, text in ipairs(argv) do
    keep[i] = ffi.new("char[?]", #text + 1, text)
    args[i - 1] = keep[i]
  end
  local actions = ffi.new("void*[16]")      -- a Mac's file actions are one pointer; glibc's (Linux) a structure of 80 bytes
  ffi.C.posix_spawn_file_actions_init(actions)
  for fd = 0, 2 do
    if fd == 0 and stdin ~= nil then
      ffi.C.posix_spawn_file_actions_adddup2(actions, stdin, 0)
    else
      ffi.C.posix_spawn_file_actions_addopen(actions, fd, "/dev/null", fd == 0 and 0 or 1, 0)   -- O_RDONLY, O_WRONLY
    end
  end
  if LINUX then
    close_the_rest(actions)
  end
  -- The program gets only those three (stdin, stdout, stderr): without POSIX_SPAWN_CLOEXEC_DEFAULT it would also get
  -- every file and socket OBS has open, and a hub holding OBS's WebSocket server socket keeps OBS's port taken after
  -- OBS has closed.
  local attributes = nil
  if ffi.os == "OSX" then
    attributes = ffi.new("void*[1]")
    ffi.C.posix_spawnattr_init(attributes)
    ffi.C.posix_spawnattr_setflags(attributes, 0x4000)  -- POSIX_SPAWN_CLOEXEC_DEFAULT
  end
  local pid = ffi.new("int[1]")
  local failed = ffi.C.posix_spawnp(pid, argv[1], actions, attributes, args, LINUX and ffi.C.environ or ffi.C._NSGetEnviron()[0])
  ffi.C.posix_spawn_file_actions_destroy(actions)
  if attributes ~= nil then
    ffi.C.posix_spawnattr_destroy(attributes)
  end
  if failed ~= 0 then
    return nil
  end
  return pid[0]
end

local function reap()
  local status = ffi.new("int[1]")
  local left = {}
  for _, pid in ipairs(helpers) do
    if ffi.C.waitpid(pid, status, 1) == 0 then          -- WNOHANG: 0 while it still runs
      table.insert(left, pid)
    end
  end
  helpers = left
end

-- OBS from Flathub (Linux): CrossChat's Python lives outside OBS's sandbox, so the script asks flatpak-spawn to run it
-- on the computer itself (the OBS Flatpak is allowed to). The sandbox's process ids mean nothing out there, so instead
-- of --obs-pid the hub gets a pipe as its input whose other end only OBS holds: it ends when OBS ends, and the hub too.
local FLATPAK = false

if not WINDOWS then
  exists = function(path)
    return ffi.C.access(path, 0) == 0
  end
  FLATPAK = LINUX and exists("/.flatpak-info")
  run = function(file, arguments)
    local argv = { file }
    for _, text in ipairs(arguments or {}) do
      table.insert(argv, text)
    end
    local pid = spawn(argv)
    if pid ~= nil then
      table.insert(helpers, pid)
    end
    return pid ~= nil
  end
end

-- OBS's settings folder (where obs-websocket keeps its port and password). Portable OBS (started with --portable,
-- or with a portable_mode file next to its bin folder) keeps it in config\obs-studio inside its own folder. On Linux it
-- is in $XDG_CONFIG_HOME (~/.config unless that says otherwise), as OBS itself looks for it.
local function obs_config_folder()
  if LINUX then
    local base = os.getenv("XDG_CONFIG_HOME") or ""
    if base:sub(1, 1) ~= "/" then
      base = (os.getenv("HOME") or "") .. "/.config"
    end
    return base .. "/obs-studio"
  end
  if not WINDOWS then
    return (os.getenv("HOME") or "") .. "/Library/Application Support/obs-studio"
  end
  local buffer = ffi.new("wchar_t[?]", 32768)
  kernel32.GetModuleFileNameW(nil, buffer, 32768)
  local root = (narrow(buffer):gsub("[/\\]bin[/\\]64bit[/\\][^/\\]+$", ""))
  local line = " " .. narrow(kernel32.GetCommandLineW()):lower() .. " "
  local portable = line:find(" %-%-portable ", 1) or line:find(" %-p ", 1)
  for _, marker in ipairs({ "portable_mode", "obs_portable_mode", "portable_mode.txt", "obs_portable_mode.txt" }) do
    portable = portable or exists(root .. "\\" .. marker)
  end
  if portable and exists(root .. "\\config\\obs-studio") then
    return root .. "\\config\\obs-studio"
  end
  return (os.getenv("APPDATA") or "") .. "\\obs-studio"
end

-- pythonw.exe to run the hub with: the setting, else the Python CrossChat's setup brings, else the one Install.cmd
-- made, else the Python launcher.
local function python()
  if python_setting ~= "" then
    return python_setting, ""
  end
  if not WINDOWS then
    local mine = app_folder() .. "/.venv/bin/python3"
    if FLATPAK then                         -- (in the sandbox, /usr/bin/python3 is the Flatpak's own: ask for the folder)
      return exists(app_folder() .. "/.venv/pyvenv.cfg") and mine or "python3", ""
    end
    return exists(mine) and mine or "python3", ""
  end
  for _, mine in ipairs({ app_folder() .. "\\python\\pythonw.exe", app_folder() .. "\\.venv\\Scripts\\pythonw.exe" }) do
    if exists(mine) then
      return mine, ""
    end
  end
  return "pyw.exe", "-3 "
end

-- A hub just started is watched at once when none is. While one runs it waits as the second hub: "Start the hub
-- again" with a hub already there ends by itself, and the watchdog below must not lose sight of the running one.
local function watch_new_hub(started)
  if running_hub == nil then
    running_hub = started
  else
    second_hub = started
  end
  return true
end

-- Like run(), but keeps a handle on the new process so the watchdog below can see whether it is still running.
local function run_watched(file, parameters, directory)
  local info = ffi.new("CROSSCHAT_SHELLEXECUTEINFOW")
  info.cbSize = ffi.sizeof(info)
  info.fMask = 0x440          -- SEE_MASK_NOCLOSEPROCESS, SEE_MASK_FLAG_NO_UI (Windows' own error box would stop OBS's thread)
  local verb, path, args, folder = wide("open"), wide(file), wide(parameters), wide(directory)   -- kept until the call returns
  info.lpVerb, info.lpFile, info.lpParameters, info.lpDirectory = verb, path, args, folder
  info.nShow = 0
  local started = shell32.ShellExecuteExW(info)
  if started == 0 or info.hProcess == nil then
    return false
  end
  return watch_new_hub({ process = info.hProcess })
end

-- macOS and Linux: the same, with the pid to wait for. (Flatpak: with the pipe described above as the hub's input.)
local function spawn_watched(argv)
  local fds = nil
  if FLATPAK then
    fds = ffi.new("int[2]")
    if ffi.C.pipe2(fds, 0x80000) ~= 0 then             -- O_CLOEXEC: no other program started from OBS gets either end
      fds = nil
    end
  end
  local pid = spawn(argv, fds and fds[0] or nil)
  if fds ~= nil then
    ffi.C.close(fds[0])                                -- the hub's end is the hub's now
    if pid == nil then
      ffi.C.close(fds[1])
    end
  end
  if pid == nil then
    return false
  end
  return watch_new_hub({ process = pid, pipe = fds and fds[1] or nil })
end

-- Flatpak: run a program on the computer itself rather than in OBS's sandbox.
local function on_host(argv)
  local out = { "flatpak-spawn", "--host", "--watch-bus" }
  for _, text in ipairs(argv) do
    table.insert(out, text)
  end
  return out
end

-- Something the streamer has to know about: in the script log, and in a box of its own (few open that log).
local ALERT_GAP = 60          -- seconds: a button pressed again and again while Python is missing shows one box
local last_alert = 0
local boxes = {}              -- (Windows) what the boxes on screen read: kept for as long as the script runs

local function alert(text)
  obs.script_log(obs.LOG_WARNING, text)
  local now = os.time()
  if now - last_alert < ALERT_GAP then
    return
  end
  last_alert = now
  if WINDOWS then
    -- The box waits for OK, so it gets a thread of its own, with no Lua on it: the watchdog runs on OBS's video thread.
    -- (MessageBoxIndirectW takes one pointer, as a thread's start function does.)
    local box, message, title = ffi.new("CROSSCHAT_MSGBOXPARAMSW"), wide(text), wide("CrossChat")
    box.cbSize = ffi.sizeof(box)
    box.lpszText, box.lpszCaption = message, title
    box.dwStyle = 0x50030     -- MB_ICONWARNING, MB_SETFOREGROUND, MB_TOPMOST
    table.insert(boxes, { box, message, title })
    local thread = kernel32.CreateThread(nil, 0, ffi.cast("void*", user32.MessageBoxIndirectW), box, 0, nil)
    if thread ~= nil then
      kernel32.CloseHandle(thread)
    end
  elseif LINUX then
    -- (a shell, to ask for whichever the desktop has; from a Flatpak OBS, on the computer itself, where they are)
    local argv = { "sh", "-c", 'if command -v zenity > /dev/null; then exec zenity --warning --no-markup --title=CrossChat "--text=$1"; '
      .. 'else exec kdialog --title CrossChat --sorry "$1"; fi', "sh", text }
    if FLATPAK then
      argv = on_host(argv)
    end
    run(argv[1], { unpack(argv, 2) })
  else
    run("osascript", { "-e", "on run argv", "-e", 'display alert "CrossChat" message (item 1 of argv) as warning', "-e", "end run", text })
  end
end

local function python_run(script, arguments, watched)
  local exe, prefix = python()
  local hub = app_folder() .. SEP .. "hub"
  local ok
  if not WINDOWS then
    local argv = { exe, hub .. "/" .. script }
    for _, text in ipairs(type(arguments) == "table" and arguments or { arguments }) do
      table.insert(argv, text)
    end
    if FLATPAK then
      argv = on_host(argv)
    end
    if watched then
      ok = spawn_watched(argv)
    else
      ok = run(argv[1], { unpack(argv, 2) })
    end
  else
    local parameters = prefix .. '"' .. hub .. "\\" .. script .. '" ' .. (arguments or "")
    if watched then
      ok = run_watched(exe, parameters, hub)
    else
      ok = run(exe, parameters, hub)
    end
  end
  if not ok then
    alert("CrossChat could not start Python (" .. exe .. "). Run "
      .. (WINDOWS and "CrossChat's setup" or LINUX and "CrossChat's scripts/install.sh" or "Install.command")
      .. " again, or set the Python field in Tools > Scripts > crosschat.lua.")
  end
  return ok
end

local function start_hub()
  if second_hub ~= nil then
    obs.script_log(obs.LOG_INFO, "a second hub is still starting: not starting another")
    return
  end
  local folder = obs_config_folder()
  obs.script_log(obs.LOG_INFO, "starting the hub (OBS settings in " .. folder .. ")")
  if FLATPAK then
    python_run("hub.py", { "--obs-stdin", "--obs-config", folder }, true)
    return
  end
  if not WINDOWS then
    python_run("hub.py", { "--obs-pid", tostring(ffi.C.getpid()), "--obs-config", folder }, true)
    return
  end
  python_run("hub.py", string.format('--obs-pid %d --obs-config "%s"', kernel32.GetCurrentProcessId(), folder), true)
end

-- How a hub this script started has ended: nil while it still runs, else its exit code.
local function hub_ended(started)
  if WINDOWS then
    local code = ffi.new("unsigned long[1]")
    if kernel32.GetExitCodeProcess(started.process, code) == 0 or code[0] == STILL_ACTIVE then
      return nil
    end
    kernel32.CloseHandle(started.process)
    return tonumber(code[0])
  end
  local status = ffi.new("int[1]")
  local done = ffi.C.waitpid(started.process, status, 1)   -- WNOHANG
  if done == 0 then
    return nil
  end
  if started.pipe ~= nil then
    ffi.C.close(started.pipe)
  end
  if done < 0 then
    return 0                  -- someone else collected it: nothing to go on, so no restart
  end
  if bit.band(status[0], 0x7f) == 0 then
    return bit.band(bit.rshift(status[0], 8), 0xff)
  end
  return 128 + bit.band(status[0], 0x7f)                -- ended by a signal
end

-- The watchdog: if the hub stops with an error (not when it ended normally, or another hub already answers on its
-- port: that's code 3), start it again. Five restarts in ten minutes means something is really wrong: then it stops
-- trying and tells you.
local function watch_hub()
  if not WINDOWS then
    reap()
  end
  if second_hub ~= nil then
    local code = hub_ended(second_hub)
    if code ~= nil then
      second_hub = nil
      if code == ALREADY_RUNNING then
        obs.script_log(obs.LOG_INFO, "the hub is already running: leaving it as it is")
      elseif code ~= 0 then
        obs.script_log(obs.LOG_WARNING, "a second hub stopped with an error (code " .. code .. "); the first one keeps running")
      end
    end
  end
  if running_hub == nil then
    return
  end
  local code = hub_ended(running_hub)
  if code == nil then
    return
  end
  running_hub = nil
  if second_hub ~= nil then
    running_hub, second_hub = second_hub, nil           -- the second hub came up as this one ended: watch that one now
    return
  end
  if code == ALREADY_RUNNING then
    obs.script_log(obs.LOG_INFO, "another CrossChat hub is already running: leaving it as it is")
    return
  end
  if code == 0 or not exists(app_folder() .. SEP .. "hub" .. SEP .. "hub.py") then
    return                    -- it ended normally, or CrossChat was uninstalled
  end
  local now = os.time()
  local recent = {}
  for _, at in ipairs(restarts) do
    if now - at < 600 then
      table.insert(recent, at)
    end
  end
  restarts = recent
  if #restarts >= 5 then
    alert("CrossChat's hub keeps stopping with an error, so it was not started again. See crosschat.log in the CrossChat folder, "
      .. "then press Start the hub again in Tools > Scripts > crosschat.lua.")
    return
  end
  table.insert(restarts, now)
  obs.script_log(obs.LOG_WARNING, "the hub stopped with an error (code " .. code .. "); starting it again")
  start_hub()
end

local function control(command)
  return function(pressed)
    if pressed == nil or pressed then
      python_run("control.py", command)
    end
    return false
  end
end

-- The port the hub listens on: "port" in config.json, read with OBS's own JSON reader.
local function hub_port()
  local settings = obs.obs_data_create_from_json_file(app_folder() .. SEP .. "config.json")
  if settings == nil then
    return DEFAULT_PORT
  end
  local port = obs.obs_data_get_int(settings, "port")
  obs.obs_data_release(settings)
  return port > 0 and port or DEFAULT_PORT
end

function script_description()
  local address = "<code>http://127.0.0.1:" .. hub_port() .. "/overlay/"
  return "<b>CrossChat " .. VERSION .. "</b><br>Every platform's chat in one window, on-stream chat widgets, and X Live "
    .. "started with OBS.<br><br>On-stream widgets (add each as a Browser Source):<br>"
    .. address .. "chat</code><br>"
    .. address .. "featured</code><br>"
    .. address .. "viewers</code><br>"
    .. address .. "alerts</code><br>"
    .. "Restyle them in the Theme Studio."
end

function script_properties()
  local props = obs.obs_properties_create()
  obs.obs_properties_add_button(props, "show", "Open chat window", control("show"))
  obs.obs_properties_add_button(props, "studio", "Open Theme Studio", control("studio"))
  obs.obs_properties_add_button(props, "unfeature", "Hide featured message", control("unfeature"))
  obs.obs_properties_add_button(props, "x_live", "Go live on X now", control("x-live"))
  obs.obs_properties_add_button(props, "x_dry", "Test X (fill the form, never go live)", control("x-dry"))
  obs.obs_properties_add_button(props, "restart", "Start the hub again", function()
    restarts = {}
    start_hub()
    return false
  end)
  local field = obs.obs_properties_add_path(props, "python", "Python (optional)", obs.OBS_PATH_FILE,
    WINDOWS and "pythonw.exe (pythonw.exe)" or "Python (python3*)", nil)
  obs.obs_property_set_long_description(field, "Leave empty: CrossChat uses the Python the installer set up.")
  return props
end

function script_update(settings)
  python_setting = obs.obs_data_get_string(settings, "python")
end

local HOTKEYS = {
  { "crosschat.show", "CrossChat: open chat window", "show" },
  { "crosschat.x_live", "CrossChat: go live on X", "x-live" },
  { "crosschat.unfeature", "CrossChat: hide featured message", "unfeature" },
}

function script_load(settings)
  python_setting = obs.obs_data_get_string(settings, "python")
  for _, key in ipairs(HOTKEYS) do
    local id = obs.obs_hotkey_register_frontend(key[1], key[2], control(key[3]))
    local saved = obs.obs_data_get_array(settings, key[1])
    obs.obs_hotkey_load(id, saved)
    obs.obs_data_array_release(saved)
    hotkeys[key[1]] = id
  end
  start_hub()
  obs.timer_add(watch_hub, 5000)
end

function script_unload()
  obs.timer_remove(watch_hub)
  if WINDOWS then
    for _, started in pairs({ running_hub, second_hub }) do
      kernel32.CloseHandle(started.process)
    end
  end
  running_hub, second_hub = nil, nil                    -- (on a Mac or Linux the hub stays a child of OBS and leaves with it)
end

function script_save(settings)
  for name, id in pairs(hotkeys) do
    local saved = obs.obs_hotkey_save(id)
    obs.obs_data_set_array(settings, name, saved)
    obs.obs_data_array_release(saved)
  end
end
