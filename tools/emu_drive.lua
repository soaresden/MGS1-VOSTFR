-- Pilote PCSX-Redux pour emu.py : lit CMD_FILE et exécute les commandes à la suite.
-- press BOUTON [images], shot nom, wait images, save nom, load chemin, dump chemin, quit
local CMD = os.getenv('CMD_FILE') or 'cmd.txt'
local queue, resume_at = {}, 0
local function step(n, a)
  if n % 5 == 0 then
    local f = io.open(CMD, 'r')
    if f then
      local cmds = f:read('*a'); f:close(); os.remove(CMD)
      for line in cmds:gmatch('[^\n]+') do queue[#queue + 1] = line end
    end
  end
  while #queue > 0 and n >= resume_at do
    local line = table.remove(queue, 1)
    local op, arg1, arg2 = line:match('(%S+)%s*(%S*)%s*(%S*)')
    if op == 'press' then a.press(a.B[arg1], tonumber(arg2) or 8)
    elseif op == 'wait' then resume_at = n + (tonumber(arg1) or 1)
    elseif op == 'shot' then a.shot(arg1)
    elseif op == 'save' then a.save(arg1)
    elseif op == 'load' then a.load(arg1)
    elseif op == 'dump' then a.dump(arg1)
    elseif op == 'quit' then a.quit()
    end
    if #queue == 0 then a.L('CMDDONE F'..n) end
  end
end
-- une erreur ne doit pas arrêter l'émulateur (le harnais quitte sur erreur)
return { step = function(n, a)
  local ok, err = pcall(step, n, a)
  if not ok then a.L('LUAERR F'..n..' '..tostring(err)) end
end }
