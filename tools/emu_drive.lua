-- Pilote PCSX-Redux pour emu.py : lit CMD_FILE et exécute les commandes à la suite.
-- press BOUTON [images], shot nom, wait images, save nom, load chemin, dump chemin, vram nom, quit
-- r16/r32 adresse (valeur écrite dans le journal), w16/w32 adresse valeur,
-- poke fichier (enregistrements : u32 adresse, u32 longueur, octets ; voir emu.py)
local CMD = os.getenv('CMD_FILE') or 'cmd.txt'
local queue, resume_at = {}, 0
local function u32(s, i) local a, b, c, d = s:byte(i, i + 3); return a + b * 256 + c * 65536 + d * 16777216 end
local function poke(a, path)
  local f = io.open(path, 'rb'); local data = f:read('*a'); f:close()
  local i, n = 1, 0
  while i + 7 <= #data do
    local addr, len = u32(data, i), u32(data, i + 4)
    for k = 0, len - 1 do a.w8(addr + k, data:byte(i + 8 + k)) end
    i = i + 8 + len; n = n + 1
  end
  a.L('POKED '..n)
end
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
    elseif op == 'vram' then a.vram(arg1)
    elseif op == 'quit' then a.quit()
    elseif op == 'r16' then a.L(string.format('R16 %s %04x', arg1, a.r16(tonumber(arg1))))
    elseif op == 'r32' then a.L(string.format('R32 %s %08x', arg1, a.r32(tonumber(arg1))))
    elseif op == 'w16' then
      local v = tonumber(arg2)
      a.w8(tonumber(arg1), v % 256); a.w8(tonumber(arg1) + 1, math.floor(v / 256) % 256)
    elseif op == 'w32' then a.w32(tonumber(arg1), tonumber(arg2))
    elseif op == 'poke' then poke(a, arg1)
    elseif op == 'near' then
      -- near CIBLE POSITION [dz] : copie la position (3 shorts) de CIBLE vers POSITION, z + dz
      local src, dst, dz = tonumber(arg1), tonumber(arg2), tonumber(line:match('%S+%s+%S+%s+%S+%s+(%S+)') or '0')
      for k = 0, 2 do
        local v = a.r16(src + 2 * k)
        if k == 2 then v = (v + dz) % 65536 end
        a.w8(dst + 2 * k, v % 256); a.w8(dst + 2 * k + 1, math.floor(v / 256) % 256)
      end
    end
    if #queue == 0 then a.L('CMDDONE F'..n) end
  end
end
-- une erreur ne doit pas arrêter l'émulateur (le harnais quitte sur erreur)
return { step = function(n, a)
  local ok, err = pcall(step, n, a)
  if not ok then a.L('LUAERR F'..n..' '..tostring(err)) end
end }
