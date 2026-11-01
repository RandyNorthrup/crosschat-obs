-- CrossChat for OBS. Add it in OBS with Tools > Scripts > +.
-- It starts the CrossChat hub (hub\hub.py) alongside OBS. The hub follows OBS from there: it opens the chat window
-- when the stream starts, closes it after the stream ends, and leaves when OBS closes. The buttons below and the
-- hotkeys (Settings > Hotkeys, "CrossChat: ...") ask the hub for things.
local obs = obslua
local ffi = require("ffi")

pcall(ffi.cdef, [[
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
]])
local kernel32 = ffi.load("kernel32")
local shell32 = ffi.load("shell32")

local VERSION = "1.6.0"
local PORT = 4466
local python_setting = ""
local hotkeys = {}
local hub_process = nil       -- the hub this script started, watched so a crash doesn't leave you without chat
local restarts = {}           -- when it was restarted, to give up on a hub that can't stay up
local STILL_ACTIVE = 259

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

-- ShellExecute with show = 0: no console window flashes (os.execute and io.popen both flash one)
local function run(file, parameters, directory, show)
  local done = shell32.ShellExecuteW(nil, wide("open"), wide(file), parameters and wide(parameters) or nil,
                                     directory and wide(directory) or nil, show or 0)
  return tonumber(ffi.cast("intptr_t", done)) > 32
end

-- The CrossChat folder: the one above this script's obs folder.
local function app_folder()
  return ((script_path() .. ".."):gsub("/", "\\"))
end

-- OBS's settings folder (where obs-websocket keeps its port and password). Portable OBS (started with --portable,
-- or with a portable_mode file next to its bin folder) keeps it in config\obs-studio inside its own folder.
local function obs_config_folder()
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

-- pythonw.exe to run the hub with: the setting, else the installer's own copy, else the Python launcher.
local function python()
  if python_setting ~= "" then
    return python_setting, ""
  end
  local mine = app_folder() .. "\\.venv\\Scripts\\pythonw.exe"
  if exists(mine) then
    return mine, ""
  end
  return "pyw.exe", "-3 "
end

-- Like run(), but keeps a handle on the new process so the watchdog below can see whether it is still running.
local function run_watched(file, parameters, directory)
  local info = ffi.new("CROSSCHAT_SHELLEXECUTEINFOW")
  info.cbSize = ffi.sizeof(info)
  info.fMask = 0x40           -- SEE_MASK_NOCLOSEPROCESS
  local verb, path, args, folder = wide("open"), wide(file), wide(parameters), wide(directory)   -- kept until the call returns
  info.lpVerb, info.lpFile, info.lpParameters, info.lpDirectory = verb, path, args, folder
  info.nShow = 0
  local started = shell32.ShellExecuteExW(info)
  if started == 0 or info.hProcess == nil then
    return false
  end
  if hub_process ~= nil then
    kernel32.CloseHandle(hub_process)
  end
  hub_process = info.hProcess
  return true
end

local function python_run(script, arguments, watched)
  local exe, prefix = python()
  local hub = app_folder() .. "\\hub"
  local parameters = prefix .. '"' .. hub .. "\\" .. script .. '" ' .. (arguments or "")
  local ok
  if watched then
    ok = run_watched(exe, parameters, hub)
  else
    ok = run(exe, parameters, hub)
  end
  if not ok then
    obs.script_log(obs.LOG_WARNING, "could not start Python (" .. exe .. "). Run Install.cmd again, or set the Python field in "
      .. "Tools > Scripts > crosschat.lua.")
  end
  return ok
end

local function start_hub()
  local folder = obs_config_folder()
  obs.script_log(obs.LOG_INFO, "starting the hub (OBS settings in " .. folder .. ")")
  python_run("hub.py", string.format('--obs-pid %d --obs-config "%s"', kernel32.GetCurrentProcessId(), folder), true)
end

-- The watchdog: if the hub stops with an error (not because OBS is closing or another hub already runs, which end
-- it normally), start it again. Five restarts in ten minutes means something is really wrong: then it stops trying
-- and says so in the script log.
local function watch_hub()
  if hub_process == nil then
    return
  end
  local code = ffi.new("unsigned long[1]")
  if kernel32.GetExitCodeProcess(hub_process, code) == 0 or code[0] == STILL_ACTIVE then
    return
  end
  kernel32.CloseHandle(hub_process)
  hub_process = nil
  if code[0] == 0 or not exists(app_folder() .. "\\hub\\hub.py") then
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
    obs.script_log(obs.LOG_WARNING, "the hub keeps stopping with an error; see crosschat.log, then press Start the hub again")
    return
  end
  table.insert(restarts, now)
  obs.script_log(obs.LOG_WARNING, "the hub stopped with an error (code " .. tonumber(code[0]) .. "); starting it again")
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

function script_description()
  return "<b>CrossChat " .. VERSION .. "</b><br>Every platform's chat in one window, on-stream chat widgets, and X Live "
    .. "started with OBS.<br><br>On-stream widgets (add each as a Browser Source):<br>"
    .. "<code>http://127.0.0.1:" .. PORT .. "/overlay/chat</code><br>"
    .. "<code>http://127.0.0.1:" .. PORT .. "/overlay/featured</code><br>"
    .. "<code>http://127.0.0.1:" .. PORT .. "/overlay/viewers</code><br>"
    .. "<code>http://127.0.0.1:" .. PORT .. "/overlay/alerts</code><br>"
    .. "Restyle them in the Theme Studio."
end

function script_properties()
  local props = obs.obs_properties_create()
  obs.obs_properties_add_button(props, "show", "Open chat window", control("show"))
  obs.obs_properties_add_button(props, "studio", "Open Theme Studio", function()
    run("http://127.0.0.1:" .. PORT .. "/studio", nil, nil, 1)
    return false
  end)
  obs.obs_properties_add_button(props, "unfeature", "Hide featured message", control("unfeature"))
  obs.obs_properties_add_button(props, "x_live", "Go live on X now", control("x-live"))
  obs.obs_properties_add_button(props, "x_dry", "Test X (fill the form, never go live)", control("x-dry"))
  obs.obs_properties_add_button(props, "restart", "Start the hub again", function()
    restarts = {}
    start_hub()
    return false
  end)
  local field = obs.obs_properties_add_path(props, "python", "Python (optional)", obs.OBS_PATH_FILE, "pythonw.exe (pythonw.exe)", nil)
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
  if hub_process ~= nil then
    kernel32.CloseHandle(hub_process)
    hub_process = nil
  end
end

function script_save(settings)
  for name, id in pairs(hotkeys) do
    local saved = obs.obs_hotkey_save(id)
    obs.obs_data_set_array(settings, name, saved)
    obs.obs_data_array_release(saved)
  end
end
