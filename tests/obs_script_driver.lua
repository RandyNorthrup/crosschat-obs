-- Runs obs/crosschat.lua the way OBS would, with a stand-in for OBS's functions, for tests/test_obs_script.py.
-- Under lupa the test sets the globals below; from the command line (luajit, on a Mac) they come as arguments:
--   luajit obs_script_driver.lua SCRIPT APP_OBS PYTHON PRESS WAIT_FOR RUNS SECONDS EXTRA
-- It loads the script, presses PRESS (a button name, or ""), lets the script's 5-second timer run every 0.2 s until
-- WAIT_FOR shows in the script log (when given) and hub.py has run RUNS times (at most SECONDS), then EXTRA seconds
-- more, unloads it, and reports the log lines, the script's description, any alert box and whether any finished
-- program was left uncollected.
jit.off()                                  -- (giving up on a hot loop raises an exception inside LuaJIT, which pytest prints as "fatal")
local given = arg or {}
SCRIPT = SCRIPT or given[1]
APP_OBS = APP_OBS or given[2]
PYTHON = PYTHON or given[3] or ""
PRESS = PRESS or given[4] or ""
WAIT_FOR = WAIT_FOR or given[5] or ""
RUNS = tonumber(RUNS or given[6] or 1)
SECONDS = tonumber(SECONDS or given[7] or 15)
EXTRA = tonumber(EXTRA or given[8] or 0)
REPORT = {}

log_lines, timers, buttons = {}, {}, {}
obslua = {
  LOG_INFO = 300, LOG_WARNING = 200, OBS_PATH_FILE = 0,
  script_log = function(level, text) table.insert(log_lines, text) end,
  timer_add = function(fn, ms) timers[1] = fn end,
  timer_remove = function(fn) timers[1] = nil end,
  obs_data_get_string = function(settings, key) return PYTHON end,
  obs_data_create_from_json_file = function(path)        -- OBS's JSON reader: all the script asks it for is "port"
    local f = io.open(path, "r")
    if not f then return nil end
    local text = f:read("*a")
    f:close()
    return { port = tonumber(text:match('"port"%s*:%s*(%d+)')) or 0 }
  end,
  obs_data_get_int = function(settings, key) return settings[key] end,
  obs_data_release = function() end,
  obs_hotkey_register_frontend = function() return 1 end,
  obs_data_get_array = function() return nil end,
  obs_hotkey_load = function() end,
  obs_data_array_release = function() end,
  obs_properties_create = function() return {} end,
  obs_properties_add_button = function(props, name, text, callback) buttons[name] = callback end,
  obs_properties_add_path = function() return {} end,
  obs_property_set_long_description = function() end,
}
function script_path() return APP_OBS end

local ffi = require("ffi")
if ffi.os == "Windows" then
  -- A real box would wait for someone to press OK, so the one call that puts it up is answered here: it says what the
  -- box would have said, and that the thread would have run the box.
  local load = ffi.load
  ffi.load = function(name)
    local lib = load(name)
    if name ~= "kernel32" then return lib end
    local function utf8(text)
      local size = lib.WideCharToMultiByte(65001, 0, text, -1, nil, 0, nil, nil)
      local out = ffi.new("char[?]", size)
      lib.WideCharToMultiByte(65001, 0, text, -1, out, size, nil, nil)
      return ffi.string(out)
    end
    local real_box = ffi.cast("void*", load("user32").MessageBoxIndirectW)
    return setmetatable({
      CreateThread = function(security, stack, start, parameter, flags, id)
        local box = ffi.cast("const CROSSCHAT_MSGBOXPARAMSW*", parameter)
        assert(start == real_box, "the thread has to run MessageBoxIndirectW")
        table.insert(REPORT, "ALERT " .. utf8(box.lpszCaption) .. ": " .. utf8(box.lpszText))
        return nil
      end,
    }, { __index = lib })
  end
end

dofile(SCRIPT)

local sleep                                -- (declared after the script, so its own declarations go in first)
if ffi.os == "Windows" then
  pcall(ffi.cdef, "void Sleep(unsigned long ms);")
  sleep = function() ffi.C.Sleep(200) end
else
  pcall(ffi.cdef, "int usleep(unsigned int microseconds);")
  sleep = function() ffi.C.usleep(200000) end
end

local function count(name)
  local f = io.open(APP_OBS .. "../" .. name .. ".jsonl", "r")
  if not f then return 0 end
  local n = 0
  for _ in f:lines() do n = n + 1 end
  f:close()
  return n
end

local function logged(text)
  for _, line in ipairs(log_lines) do
    if text ~= "" and line:find(text, 1, true) then return true end
  end
  return false
end

local function run_for(seconds, done)
  local stop = os.time() + seconds
  while os.time() < stop and not done() do
    sleep()
    if timers[1] then timers[1]() end
  end
end

-- OBS has files and sockets of its own open (its log, its WebSocket server): one here too, which the programs the
-- script starts must not get (test_obs_script.py looks for it in the stand-in hub)
OBS_HELD = io.open(APP_OBS .. "../obs-held.txt", "w")

script_load(nil)
table.insert(REPORT, "DESCRIPTION " .. script_description())
if PRESS == "restart" then                 -- the first hub is up by now, as when a streamer presses it
  run_for(SECONDS, function() return count("hub") >= 1 end)
end
if PRESS ~= "" then
  script_properties()
  buttons[PRESS](true)
end
run_for(SECONDS, function()
  if WAIT_FOR ~= "" then return logged(WAIT_FOR) and count("hub") >= RUNS end
  return count("hub") >= RUNS and (PRESS == "" or PRESS == "restart" or count("control") >= 1)
end)
run_for(EXTRA, function() return false end)
if ffi.os ~= "Windows" then
  local left = ffi.C.waitpid(-1, ffi.new("int[1]"), 1)   -- WNOHANG: -1 means no children at all
  table.insert(REPORT, "CHILDREN " .. (left == -1 and "none" or "left"))
end
script_unload()
OBS_HELD:close()
for _, line in ipairs(log_lines) do table.insert(REPORT, "LOG " .. line) end
if arg then
  for _, line in ipairs(REPORT) do print(line) end
end
