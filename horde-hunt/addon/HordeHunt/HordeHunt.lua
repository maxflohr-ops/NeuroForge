-- Horde Hunt: walks HordeHuntData one clue at a time, verifies the find in game,
-- and stamps it into the chat log as a whisper to yourself:
--     To <you>: HUNT_DONE <id> <slug>
-- The hunt engine (engine/hunt_server.py) only trusts that outgoing line, so a viewer
-- whispering "HUNT_DONE" at you does nothing.

local ADDON = ...
local D = HordeHuntData
local frame, title, riddle, status

local function me() return (UnitName("player")) end
local function say(msg) DEFAULT_CHAT_FRAME:AddMessage("|cffd43a3aHorde Hunt|r " .. msg) end

local function db()
  HordeHuntDB = HordeHuntDB or {}
  if HordeHuntDB.slug ~= D.slug then
    HordeHuntDB = { slug = D.slug, found = {}, order = {} }  -- a new hunt starts clean
  end
  return HordeHuntDB
end

local function active()
  local s = db()
  for i, step in ipairs(D.steps) do
    if not s.found[step.id] then return step, i end
  end
end

local function stamp(kind, id)
  -- whisper to self: lands in WoWChatLog.txt as "To <you>: ..."
  SendChatMessage("HUNT_" .. kind .. " " .. id .. " " .. D.slug, "WHISPER", nil, me())
end

local function refresh()
  if not frame then return end
  local step, i = active()
  if not step then
    title:SetText("Hunt complete")
    riddle:SetText("Every mark is found. The door is open.")
    status:SetText(#D.steps .. " / " .. #D.steps)
    return
  end
  title:SetText("Clue " .. i .. " of " .. #D.steps .. ": " .. step.title)
  riddle:SetText(step.riddle)
  status:SetText(step.kind == "manual" and "/hunt done when you have it" or "searching...")
end

local function markFound(step, how)
  local s = db()
  if s.found[step.id] then return end
  s.found[step.id] = time()
  table.insert(s.order, step.id)
  stamp("DONE", step.id)
  say("found |cffffffff" .. step.title .. "|r (" .. how .. ")")
  PlaySound(SOUNDKIT and SOUNDKIT.IG_QUEST_LIST_COMPLETE or 618)
  refresh()
end

-- verification -------------------------------------------------------------

local function checkLocation(step)
  if step.kind ~= "loc" then return end
  if GetRealZoneText() ~= step.zone and GetZoneText() ~= step.zone then return end
  local map = C_Map.GetBestMapForUnit("player")
  if not map then return end
  local pos = C_Map.GetPlayerMapPosition(map, "player")
  if not pos then return end
  local x, y = pos:GetXY()
  local dx, dy = x * 100 - step.x, y * 100 - step.y
  if (dx * dx + dy * dy) <= step.r * step.r then markFound(step, "location") end
end

local function npcName()
  return UnitName("npc") or (UnitExists("target") and CheckInteractDistance("target", 3) and UnitName("target"))
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("ADDON_LOADED")
ev:RegisterEvent("PLAYER_LOGIN")
ev:RegisterEvent("CHAT_MSG_LOOT")
for _, e in ipairs({ "GOSSIP_SHOW", "QUEST_GREETING", "QUEST_DETAIL", "QUEST_PROGRESS", "MERCHANT_SHOW" }) do
  ev:RegisterEvent(e)
end

ev:SetScript("OnEvent", function(_, e, a1)
  if e == "ADDON_LOADED" then
    if a1 == ADDON then db() end
    return
  end
  if e == "PLAYER_LOGIN" then
    if not LoggingChat() then LoggingChat(true) end  -- the engine reads WoWChatLog.txt
    refresh()
    return
  end
  local step = active()
  if not step then return end
  if e == "CHAT_MSG_LOOT" then
    if step.kind == "loot" and a1 and a1:find("You receive", 1, true) and a1:find("[" .. step.item .. "]", 1, true) then
      markFound(step, "loot")
    end
  elseif step.kind == "npc" and npcName() == step.npc then
    markFound(step, "talked to " .. step.npc)
  end
end)

local acc = 0
ev:SetScript("OnUpdate", function(_, dt)
  acc = acc + dt
  if acc < 0.5 then return end
  acc = 0
  local step = active()
  if step then checkLocation(step) end
end)

-- the card -----------------------------------------------------------------

frame = CreateFrame("Frame", "HordeHuntFrame", UIParent, BackdropTemplateMixin and "BackdropTemplate")
frame:SetSize(300, 96)
frame:SetPoint("TOPRIGHT", -24, -220)
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:SetClampedToScreen(true)
if frame.SetBackdrop then
  frame:SetBackdrop({ bgFile = "Interface\\Buttons\\WHITE8X8", edgeFile = "Interface\\Buttons\\WHITE8X8", edgeSize = 1 })
  frame:SetBackdropColor(0.07, 0.06, 0.06, 0.82)
  frame:SetBackdropBorderColor(0.83, 0.23, 0.23, 0.9)
end
title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
title:SetPoint("TOPLEFT", 10, -8)
title:SetPoint("RIGHT", -10, 0)
title:SetJustifyH("LEFT")
riddle = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
riddle:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -6)
riddle:SetPoint("RIGHT", -10, 0)
riddle:SetJustifyH("LEFT")
riddle:SetJustifyV("TOP")
riddle:SetHeight(44)
status = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
status:SetPoint("BOTTOMLEFT", 10, 8)

-- slash --------------------------------------------------------------------

SLASH_HORDEHUNT1 = "/hunt"
SlashCmdList.HORDEHUNT = function(msg)
  msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
  local step, i = active()
  if msg == "done" then
    if step then markFound(step, "by hand") else say("the hunt is already complete") end
  elseif msg == "undo" then
    local s = db()
    local id = table.remove(s.order)
    if id then
      s.found[id] = nil
      stamp("UNDO", id)
      say("undid " .. id)
      refresh()
    else
      say("nothing to undo")
    end
  elseif msg == "peek" then
    -- private: prints to your chat frame only. Don't peek with the chat frame on stream.
    if step and step.kind == "loc" then
      say(("%s %.1f, %.1f (within %.1f)"):format(step.zone, step.x, step.y, step.r))
    elseif step then
      say(step.kind .. ": " .. (step.item or step.npc or "manual"))
    end
  elseif msg == "hide" then
    frame:Hide()
  elseif msg == "show" then
    frame:Show()
    refresh()
  elseif msg == "reset yes" then
    HordeHuntDB = nil
    db()
    say("progress cleared")
    refresh()
  elseif msg == "reset" then
    say("type /hunt reset yes to clear every find")
  else
    if step then say("clue " .. i .. "/" .. #D.steps .. ": " .. step.title) else say("hunt complete") end
    say("/hunt done | undo | peek | hide | show | reset")
  end
end
