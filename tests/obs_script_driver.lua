-- Runs obs/crosschat.lua the way OBS would, with a stand-in for OBS's functions, for tests/test_obs_script.py.
-- Under lupa the test sets the globals below; from the command line (luajit, on a Mac) they come as arguments:
--   luajit obs_script_driver.lua SCRIPT APP_OBS PYTHON PRESS WAIT_FOR RUNS SECONDS EXTRA
-- It loads the script, presses PRESS (a button name, or ""), lets the script's 5-second timer run every 0.2 s until
-- WAIT_FOR shows in the script log or hub.py has run RUNS times (at most SECONDS), then EXTRA seconds more, unloads
-- it, and reports the log lines and whether any finished program was left uncollected.
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
  timer_add = function(fn, ms) timers[fn] = true end,
  timer_remove = function(fn) timers[fn] = nil end,
  obs_enum_sources = function() return nil end,       -- no scenes here, so no widgets to refresh
  obs_data_get_string = function(settings, key) return PYTHON end,
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

dofile(SCRIPT)

local ffi = require("ffi")                 -- declared after the script, so its own declarations go in first
local sleep
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
    local due = {}
    for fn in pairs(timers) do table.insert(due, fn) end
    for _, fn in ipairs(due) do fn() end
  end
end

script_load(nil)
if PRESS ~= "" then
  script_properties()
  buttons[PRESS](true)
end
run_for(SECONDS, function()
  if WAIT_FOR ~= "" then return logged(WAIT_FOR) end
  return count("hub") >= RUNS and (PRESS == "" or count("control") >= 1)
end)
run_for(EXTRA, function() return false end)
if ffi.os ~= "Windows" then
  local left = ffi.C.waitpid(-1, ffi.new("int[1]"), 1)   -- WNOHANG: -1 means no children at all
  table.insert(REPORT, "CHILDREN " .. (left == -1 and "none" or "left"))
end
script_unload()
for _, line in ipairs(log_lines) do table.insert(REPORT, "LOG " .. line) end
if arg then
  for _, line in ipairs(REPORT) do print(line) end
end
