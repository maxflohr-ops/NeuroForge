-- Horde Hunt: walks HordeHuntData one clue at a time, verifies the find in game,
-- and stamps it into the chat log as a whisper to yourself:
--     To <you>: HUNT_DONE <id> <slug>
-- The hunt engine (engine/hunt_server.py) only trusts that outgoing line, so a viewer
-- whispering "HUNT_DONE" at you does nothing.

local ADDON = ...
local D = HordeHuntData
local frame, eyebrow, title, riddle, status, pips, flash

-- one palette, matching the stream board: near-black panel, one crimson, one gold for the door
local C = {
  panel  = { 0.045, 0.035, 0.035, 0.90 },
  accent = { 0.86, 0.24, 0.22 },
  door   = { 0.94, 0.80, 0.50 },
  ink    = { 0.95, 0.93, 0.89 },
  ink2   = { 0.72, 0.69, 0.65 },
  ink3   = { 0.45, 0.42, 0.40 },
  rule   = { 0.24, 0.21, 0.20 },
}

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

local function pad(n) return string.format("%02d", n) end

local function refresh()
  if not frame then return end
  local s = db()
  local step, i = active()
  for k, pip in ipairs(pips) do
    local st = D.steps[k]
    if s.found[st.id] then
      pip:SetColorTexture(C.accent[1], C.accent[2], C.accent[3], 1)
    elseif step and st.id == step.id then
      pip:SetColorTexture(C.ink[1], C.ink[2], C.ink[3], 0.9)
    else
      pip:SetColorTexture(C.rule[1], C.rule[2], C.rule[3], 1)
    end
  end
  if not step then
    eyebrow:SetText("HORDE HUNT  " .. pad(#D.steps) .. " / " .. pad(#D.steps))
    title:SetText("The door is open")
    title:SetTextColor(C.door[1], C.door[2], C.door[3])
    riddle:SetText("Every mark is found.")
    status:SetText("")
    frame.edge:SetColorTexture(C.door[1], C.door[2], C.door[3], 1)
    return
  end
  eyebrow:SetText("HORDE HUNT  " .. pad(i) .. " / " .. pad(#D.steps))
  title:SetText(step.title)
  title:SetTextColor(C.ink[1], C.ink[2], C.ink[3])
  riddle:SetText(step.riddle)
  status:SetText(step.kind == "manual" and "/hunt done" or "searching")
  frame.edge:SetColorTexture(C.accent[1], C.accent[2], C.accent[3], 1)
end

local function markFound(step, how)
  local s = db()
  if s.found[step.id] then return end
  s.found[step.id] = time()
  table.insert(s.order, step.id)
  stamp("DONE", step.id)
  say("found |cffffffff" .. step.title .. "|r (" .. how .. ")")
  PlaySound(SOUNDKIT and SOUNDKIT.IG_QUEST_LIST_COMPLETE or 618)
  if flash then flash:Play() end
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
-- Same voice as the stream board: dark panel, crimson edge, small spaced eyebrow,
-- the title big, the riddle quiet, one pip per clue. Original art: flat colour only.

local W, H = 312, 118
frame = CreateFrame("Frame", "HordeHuntFrame", UIParent)
frame:SetSize(W, H)
frame:SetPoint("TOPRIGHT", -24, -220)
frame:SetMovable(true)
frame:EnableMouse(true)
frame:RegisterForDrag("LeftButton")
frame:SetScript("OnDragStart", frame.StartMoving)
frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
frame:SetClampedToScreen(true)

local bg = frame:CreateTexture(nil, "BACKGROUND")
bg:SetAllPoints()
bg:SetColorTexture(unpack(C.panel))

frame.edge = frame:CreateTexture(nil, "ARTWORK")
frame.edge:SetPoint("TOPLEFT")
frame.edge:SetPoint("BOTTOMLEFT")
frame.edge:SetWidth(2)
frame.edge:SetColorTexture(C.accent[1], C.accent[2], C.accent[3], 1)

-- a soft crimson wash that fades in and out when a find lands
local glow = frame:CreateTexture(nil, "BORDER")
glow:SetAllPoints()
glow:SetColorTexture(C.accent[1], C.accent[2], C.accent[3], 0.22)
glow:SetAlpha(0)
flash = glow:CreateAnimationGroup()
local up = flash:CreateAnimation("Alpha")
up:SetFromAlpha(0); up:SetToAlpha(1); up:SetDuration(0.18); up:SetOrder(1)
local down = flash:CreateAnimation("Alpha")
down:SetFromAlpha(1); down:SetToAlpha(0); down:SetDuration(0.9); down:SetOrder(2)
flash:SetScript("OnFinished", function() glow:SetAlpha(0) end)

local PAD = 14
eyebrow = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
eyebrow:SetPoint("TOPLEFT", PAD, -11)
eyebrow:SetTextColor(C.accent[1], C.accent[2], C.accent[3])
eyebrow:SetSpacing(2)

status = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
status:SetPoint("TOPRIGHT", -PAD, -11)
status:SetTextColor(C.ink3[1], C.ink3[2], C.ink3[3])

title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOPLEFT", eyebrow, "BOTTOMLEFT", 0, -6)
title:SetPoint("RIGHT", -PAD, 0)
title:SetJustifyH("LEFT")
title:SetTextColor(C.ink[1], C.ink[2], C.ink[3])

riddle = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
riddle:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -6)
riddle:SetPoint("RIGHT", -PAD, 0)
riddle:SetJustifyH("LEFT")
riddle:SetJustifyV("TOP")
riddle:SetHeight(40)
riddle:SetTextColor(C.ink2[1], C.ink2[2], C.ink2[3])

-- one pip per clue along the bottom: found = crimson, current = light, sealed = dim
pips = {}
local n = #D.steps
local gap = 4
local pw = (W - PAD * 2 - gap * (n - 1)) / n
for k = 1, n do
  local pip = frame:CreateTexture(nil, "ARTWORK")
  pip:SetSize(pw, 2)
  pip:SetPoint("BOTTOMLEFT", PAD + (k - 1) * (pw + gap), 10)
  pips[k] = pip
end

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
