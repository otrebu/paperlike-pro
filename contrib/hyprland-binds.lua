-- paperlike hotkeys for Hyprland 0.56+ (Lua config).
-- UNTESTED: written against Hyprland 0.56's Lua config API, not yet loaded into a running Hyprland.
-- Paste these lines into your config, or copy this file to ~/.config/hypr/paperlike-binds.lua
-- and load it from hyprland.lua:
--   dofile(os.getenv("HOME") .. "/.config/hypr/paperlike-binds.lua")
-- The keys are suggestions: check they're free in your config first.
-- Omarchy's helper takes a description too: o.bind("SUPER + ALT + C", "Paperlike: quick clear", "paperlike clear")

-- if ~/.local/bin isn't on Hyprland's PATH, use the full path:
-- local paperlike = os.getenv("HOME") .. "/.local/bin/paperlike"
local paperlike = "paperlike"

local function run(args)
  return hl.dsp.exec_cmd(paperlike .. " " .. args)
end

hl.bind("SUPER + ALT + C",         run("clear"),        { description = "Paperlike: quick ghost clear" })
hl.bind("SUPER + ALT + SHIFT + C", run("clear --full"), { description = "Paperlike: full clear" })
hl.bind("SUPER + ALT + A",         run("mode a2"),      { description = "Paperlike: A2 (black and white, fast)" })
hl.bind("SUPER + ALT + D",         run("mode floyd"),   { description = "Paperlike: Floyd (dithered greys)" })
hl.bind("SUPER + ALT + P",         run("mode 16"),      { description = "Paperlike: 16 greys (photos)" })
hl.bind("SUPER + ALT + W",         run("wake"),         { description = "Paperlike: bring the picture back" })

-- Simpler than the systemd unit: start the watcher with Hyprland.
-- hl.on("hyprland.start", function() hl.exec_cmd(paperlike .. " watch") end)
