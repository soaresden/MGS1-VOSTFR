#!/usr/bin/env python3
"""gamelist.py - The EmulationStation entry of the port (Batocera ports/gamelist.xml, RetroBat windows/gamelist.xml).

    python3 gamelist.py <Metal Gear Solid.sh> <gamelist.xml> <entry path>     (run.sh, at each start)
    python3 gamelist.py --images <source picture> <forgamelist folder>        (make_port.py: the three pictures)

Adds the game to the gamelist, or completes its entry: name, the English description below, the pictures of
forgamelist/ (image.png 4:3, thumbnail.png square, fanart.png), developer, date... A field the player filled in stays
as it is, except a description this script wrote before (it is refreshed). Same rules as nfsmw-batocera's mods.py.
"""
import os
import sys

DESC = """Metal Gear Solid (PS1, USA Rev 1), recompiled to native code with alexbeavs' psxrecomp: no emulator. \
With the MGS1-VOSTFR mods: French subtitles under the English voices (Codec, in-game voices, cutscenes, menus), \
Square skips the Codec, tranquilizer M9 and PSG1-T, shooting in first-person view, PSG1 standing or crouched, \
bandana, true 16:9, and a MODS entry in the title menu to switch them.

Hotkey + Start quits; Select + L3 opens the in-game menu.

Port: github.com/soaresden/MGS1-VOSTFR (page: soaresden.github.io/MGS1-VOSTFR). Built on alexbeavs-ps1-ports \
psxrecomp. Your own Metal Gear Solid (USA) discs and BIOS are required."""
GAME = {'name': 'Metal Gear Solid', 'desc': DESC, 'releasedate': '19981021T000000',
        'developer': 'Konami (KCEJ)', 'publisher': 'Konami', 'genre': 'Action / Infiltration', 'players': '1',
        'lang': 'fr'}
MEDIA = {'image': 'image.png', 'thumbnail': 'thumbnail.png', 'fanart': 'fanart.png'}


def gamelist(port, xml, entry, name=None):
    import xml.etree.ElementTree as ET
    here = os.path.dirname(os.path.abspath(xml))
    try:
        tree = ET.parse(xml)
        root = tree.getroot()
    except (OSError, ET.ParseError):
        if os.path.exists(xml):
            print('[gamelist] %s unreadable: left as it is' % xml)
            return
        root = ET.Element('gameList')
        tree = ET.ElementTree(root)
    norm = lambda p: os.path.normcase(os.path.normpath(os.path.join(here, p)))
    game = next((g for g in root.findall('game') if norm(g.findtext('path', '')) == norm(entry)), None)
    added = game is None
    if added:
        game = ET.SubElement(root, 'game')
        ET.SubElement(game, 'path').text = entry
    changed = added
    values = dict(GAME)
    if name:
        values['name'] = name
    media = os.path.join(port, 'forgamelist')
    for tag, fname in MEDIA.items():
        if os.path.isfile(os.path.join(media, fname)):
            rel = os.path.relpath(os.path.join(media, fname), here).replace(os.sep, '/')
            values[tag] = rel if rel.startswith('.') else './' + rel
    for tag, value in values.items():
        el = game.find(tag)
        old = el.text if el is not None else None
        ours = old and (tag == 'desc' and old.startswith(DESC.split(',')[0])
                        or tag in MEDIA and '/forgamelist/' in old.replace('\\', '/'))
        if old and not ours:
            continue
        if old == value:
            continue
        if el is None:
            el = ET.SubElement(game, tag)
        el.text = value
        changed = True
    if not changed:
        return
    if hasattr(ET, 'indent'):
        ET.indent(tree, '\t')
    tree.write(xml, encoding='utf-8', xml_declaration=True)
    print('[gamelist] %s %s in %s' % ('entry added' if added else 'entry completed', entry, xml))


def images(src, out):
    """forgamelist/ from one picture: image.png (4:3, 640 wide), thumbnail.png (square, 512), fanart.png (as is,
    1280 wide at most)."""
    from PIL import Image
    im = Image.open(src).convert('RGB')
    os.makedirs(out, exist_ok=True)
    w, h = im.size
    cw, ch = (w, w * 3 // 4) if w * 3 <= h * 4 else (h * 4 // 3, h)   # 4:3, centred
    im.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)).resize((640, 480), Image.LANCZOS) \
        .save(os.path.join(out, 'image.png'), optimize=True)
    s = min(w, h)
    im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((512, 512), Image.LANCZOS) \
        .save(os.path.join(out, 'thumbnail.png'), optimize=True)
    f = im if w <= 1280 else im.resize((1280, h * 1280 // w), Image.LANCZOS)
    f.save(os.path.join(out, 'fanart.png'), optimize=True)
    print('[gamelist] %s -> %s (image, thumbnail, fanart)' % (src, out))


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--images':
        images(sys.argv[2], sys.argv[3])
    elif len(sys.argv) in (4, 5):
        gamelist(*sys.argv[1:])
    else:
        sys.exit(__doc__)
