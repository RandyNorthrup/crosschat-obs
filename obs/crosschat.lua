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
]])
local kernel32 = ffi.load("kernel32")
local shell32 = ffi.load("shell32")

local VERSION = "1.4.0"
local PORT = 4466
local python_setting = ""
local hotkeys = {}

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

local function python_run(script, arguments)
  local exe, prefix = python()
  local hub = app_folder() .. "\\hub"
  local ok = run(exe, prefix .. '"' .. hub .. "\\" .. script .. '" ' .. (arguments or ""), hub)
  if not ok then
    obs.script_log(obs.LOG_WARNING, "could not start Python (" .. exe .. "). Run Install.cmd again, or set the Python field in "
      .. "Tools > Scripts > crosschat.lua.")
  end
  return ok
end

local function start_hub()
  local folder = obs_config_folder()
  obs.script_log(obs.LOG_INFO, "starting the hub (OBS settings in " .. folder .. ")")
  python_run("hub.py", string.format('--obs-pid %d --obs-config "%s"', kernel32.GetCurrentProcessId(), folder))
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
end

function script_save(settings)
  for name, id in pairs(hotkeys) do
    local saved = obs.obs_hotkey_save(id)
    obs.obs_data_set_array(settings, name, saved)
    obs.obs_data_array_release(saved)
  end
end
