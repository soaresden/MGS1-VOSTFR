/* mgs_title_mods.c - MGS (USA Rev 1): a MODS entry under SPECIAL in the title menu.
 *
 * The title menu (overlay "title", work struct passed to every function below) is a
 * carousel of 6 words, NEW GAME, LOAD GAME, OPTION, BRIEFING, SPECIAL, VR TRAINING,
 * looping; the code that moves the cursor and animates the words is written out
 * case by case for each of the 6 entries. This file adds a 7th entry, MODS, between
 * SPECIAL and VR TRAINING without touching the game's bytes (func_override, guarded
 * by the first words of each function, so another overlay at the same address is
 * left alone):
 *
 * - cursor (work+0xA4C) = 6 means MODS. Every switch of the game on the cursor is
 *   bounded (sltiu 6), so with 6 the game moves nothing, draws nothing and does not
 *   highlight anything; the scroll counter (+0xAE8) still advances.
 * - the menu-state function (0x800C7B58) runs first; afterwards, SPECIAL -> down
 *   and VR TRAINING -> up become MODS, and on MODS this file does what the game does
 *   for the other entries (up/down with the same repeat timing, sound, Cross back,
 *   Circle/Start: the in-game menu opens on its Mods page, psx_menu_request_mods_page).
 * - the function that copies the menu polygons into the display lists (0x800C6D38)
 *   is preceded, whenever MODS is in view, by a redraw of the visible words (3 still,
 *   4 while scrolling) with the game's own positions, fades and colours
 *   (title_open_800CF794 of FoxdieTeam/mgs_reversing); MODS borrows the polygon of
 *   an entry that is out of view, with its own texture.
 * - the word MODS is made of the game's letters (M of GAME, O of OPTION, D = B of
 *   BRIEFING without its middle bar, S of SPECIAL), uploaded to a free corner of the
 *   title's texture page (4 bits, page x 64 y 256, u 192 v 240) with SPECIAL's palette.
 */
#include <stdint.h>
#include <string.h>

#include "cpu_state.h"
#include "func_override.h"
#include "mod_plugins.h"

extern uint32_t psx_read_word(uint32_t addr);
extern void psx_write_word(uint32_t addr, uint32_t val);
extern uint16_t psx_read_half(uint32_t addr);
extern void psx_write_half(uint32_t addr, uint16_t val);
extern uint8_t psx_read_byte(uint32_t addr);
extern void psx_write_byte(uint32_t addr, uint8_t val);
extern void gpu_write_gp0(uint32_t val);
extern void psx_menu_request_mods_page(void);

/* overlay functions (USA Rev 1, title loaded at 0x800C5970) */
#define FN_STATE   0x800C7B58u  /* per-frame menu state machine (pad, cursor) */
#define FN_COPY    0x800C6D38u  /* copies the work polygons into the display packets */
#define FN_HILITE  0x800CE7D0u  /* red pulse of the current word (work, polygon index) */
#define FN_SE      0x8003483Cu  /* GM_SeSet2(0, 0x3F, sound) */
static const uint32_t kGuardState[4] = {0x27BDFFB0u, 0xAFB50044u, 0x0080A821u, 0x24020002u};
static const uint32_t kGuardCopy[4] = {0x00806821u, 0x25AA0188u, 0x00005821u, 0x01A06021u};

/* work fields */
#define W_BRIGHT   0x0E0u  /* int[6]: 0x100 shown, 0 hidden */
#define W_PULSE_T  0x180u  /* pulse frame counter */
#define W_POLYS    0x908u  /* POLY_GT4[6], 0x34 bytes each */
#define W_PAD      0xA40u  /* GV_PAD *: +0 held, +2 pressed */
#define W_STATE    0xA48u  /* 6 = PRESS START, 7 = menu */
#define W_CURSOR   0xA4Cu
#define W_PULSE    0xA6Cu  /* pulse phase (2, 3, 4) */
#define W_REINIT   0xAE0u
#define W_SCROLL   0xAE8u  /* 0 / 6 idle, 1..5 scrolling */
#define W_DIR      0xAECu  /* 0 up, 1 down */
#define W_REPEAT   0xAF0u
#define PAD_UP     0x1000u
#define PAD_DOWN   0x4000u
#define PAD_CROSS  0x0040u
#define PAD_OK     0x0820u  /* Circle, Start */
#define SE_CURSOR  0x1F
#define SE_SELECT  0x66

#define MODS 6
#define POLY(w, i) ((w) + W_POLYS + (uint32_t)(i) * 0x34u)

/* the ring with MODS between SPECIAL (4) and VR TRAINING (5) */
static const int kRing[7] = {0, 1, 2, 3, 4, MODS, 5};
static const int kHalf[7] = {0x26, 0x28, 0x1A, 0x20, 0x1E, 0x2C, 0x13};  /* half widths; [6] MODS */

static int ring_pos(int c) { for (int i = 0; i < 7; i++) if (kRing[i] == c) return i; return 0; }
static int ring_at(int c, int delta) { return kRing[((ring_pos(c) + delta) % 7 + 7) % 7]; }

/* ---- the word MODS ---- */
#define TEX_TPAGE 0x31u
#define TEX_CLUT  0x3B79u      /* SPECIAL's palette: 0 clear, 1 outline, 2 letter */
#define TEX_U     192
#define TEX_V     240
#define TEX_W     40           /* uploaded texels (10 halfwords); the word is 37 */
#define TEX_H     8
static const char *const kLetters[4][8] = {
    {"1111.11111", "1221112221", "1222122221", "1222222221",   /* M (GAME) */
     "1221212221", "1221112221", "1221.12221", "1111.11111"},
    {".111111111", "1122222211", "1221112221", "1221.12221",   /* O (OPTION) */
     "1221.12221", "1221112221", "1122222211", ".111111111"},
    {"1111111111", "1222222211", "1222111221", "1222111221",   /* D (B of BRIEFING) */
     "1222111221", "1222111221", "1222222211", "1111111111"},
    {".111111111", "1122222221", "1222111111", "1122222211",   /* S (SPECIAL) */
     ".111122221", "1111122221", "1222222211", "1111111111"},
};

static void upload_mods_word(void) {
    uint8_t px[TEX_H][TEX_W];
    memset(px, 0, sizeof px);
    for (int l = 0; l < 4; l++)
        for (int y = 0; y < 8; y++)
            for (int x = 0; x < 10; x++) {
                const char c = kLetters[l][y][x];
                const uint8_t v = c == '2' ? 2 : c == '1' ? 1 : 0;
                uint8_t *p = &px[y][l * 9 + x];
                if (v > *p) *p = v;
            }
    /* GP0(A0) CPU -> VRAM: 4-bit texels, 4 per halfword, 2 halfwords per word */
    gpu_write_gp0(0x01000000u);  /* clear the texture cache */
    gpu_write_gp0(0xA0000000u);
    gpu_write_gp0(((256u + TEX_V) << 16) | (64u + TEX_U / 4));
    gpu_write_gp0(((uint32_t)TEX_H << 16) | (TEX_W / 4));
    for (int y = 0; y < TEX_H; y++)
        for (int x = 0; x < TEX_W; x += 8) {
            uint32_t w = 0;
            for (int n = 0; n < 8; n++) w |= (uint32_t)px[y][x + n] << (4 * n);
            gpu_write_gp0(w);
        }
}

/* ---- host state (title menu only: nothing here outlives a menu) ---- */
static uint32_t s_work;          /* work struct the saved textures belong to */
static uint32_t s_tex[6][4];     /* each polygon's own uv0+clut, uv1+tpage, uv2, uv3 */
static int s_borrowed = -1;      /* polygon showing MODS, -1 none */
static int s_uploaded;

static void save_textures(uint32_t w) {
    if (s_work == w) return;
    s_work = w;
    s_borrowed = -1;
    s_uploaded = 0;
    for (int i = 0; i < 6; i++) {
        const uint32_t p = POLY(w, i);
        s_tex[i][0] = psx_read_word(p + 12);
        s_tex[i][1] = psx_read_word(p + 24);
        s_tex[i][2] = psx_read_half(p + 36);
        s_tex[i][3] = psx_read_half(p + 48);
    }
}

static void restore_borrowed(uint32_t w) {
    if (s_borrowed < 0 || s_work != w) { s_borrowed = -1; return; }
    const uint32_t p = POLY(w, s_borrowed);
    psx_write_word(p + 12, s_tex[s_borrowed][0]);
    psx_write_word(p + 24, s_tex[s_borrowed][1]);
    psx_write_half(p + 36, (uint16_t)s_tex[s_borrowed][2]);
    psx_write_half(p + 48, (uint16_t)s_tex[s_borrowed][3]);
    s_borrowed = -1;
}

static void lend_to_mods(uint32_t w, int slot) {
    const uint32_t p = POLY(w, slot);
    const uint32_t u0 = TEX_U, u1 = TEX_U + 2 * kHalf[MODS], v0 = TEX_V, v1 = TEX_V + TEX_H;
    psx_write_word(p + 12, (TEX_CLUT << 16) | (v0 << 8) | u0);
    psx_write_word(p + 24, (TEX_TPAGE << 16) | (v0 << 8) | u1);
    psx_write_half(p + 36, (uint16_t)((v1 << 8) | u0));
    psx_write_half(p + 48, (uint16_t)((v1 << 8) | u1));
    s_borrowed = slot;
}

/* ---- polygon helpers (the game's own: setXY4, title_open_800C4B94 / 800C4BD4) ---- */
static void set_xy(uint32_t p, int half, int y) {
    const uint32_t l = (uint16_t)(int16_t)-half, r = (uint16_t)half;
    psx_write_word(p + 8, ((uint32_t)(uint16_t)y << 16) | l);
    psx_write_word(p + 20, ((uint32_t)(uint16_t)y << 16) | r);
    psx_write_word(p + 32, ((uint32_t)(uint16_t)(y + 8) << 16) | l);
    psx_write_word(p + 44, ((uint32_t)(uint16_t)(y + 8) << 16) | r);
}
static void set_rgb(uint32_t p, int off, int r, int g, int b) {
    psx_write_byte(p + off, (uint8_t)r);
    psx_write_byte(p + off + 1, (uint8_t)g);
    psx_write_byte(p + off + 2, (uint8_t)b);
}
static void set_grad(uint32_t p, int r0, int g0, int b0, int r2, int g2, int b2) {
    set_rgb(p, 4, r0, g0, b0);
    set_rgb(p, 16, r0, g0, b0);
    set_rgb(p, 28, r2, g2, b2);
    set_rgb(p, 40, r2, g2, b2);
}
static void set_shade(uint32_t p, int top, int bot) {
    set_grad(p, top, top * 192 / 128, top, bot, bot * 192 / 128, bot);
}
static void set_semi(uint32_t p, int on) {
    const uint8_t code = psx_read_byte(p + 7);
    psx_write_byte(p + 7, (uint8_t)(on ? code | 2 : code & ~2));
}

static void guest_call3(struct CPUState *cpu, uint32_t fn, uint32_t a0, uint32_t a1, uint32_t a2) {
    uint32_t saved[32];
    memcpy(saved, cpu->gpr, sizeof saved);
    cpu->gpr[4] = a0;
    cpu->gpr[5] = a1;
    cpu->gpr[6] = a2;
    func_override_guest_call(cpu, fn, saved[31]);
    memcpy(cpu->gpr, saved, sizeof saved);
}

/* ---- the menu state machine: MODS in the ring, MODS's own keys ---- */
static void move_to(struct CPUState *cpu, uint32_t w, int c, int dir, int first) {
    guest_call3(cpu, FN_SE, 0, 0x3F, SE_CURSOR);
    psx_write_word(w + W_CURSOR, (uint32_t)c);
    psx_write_word(w + W_SCROLL, 1);
    if (first) psx_write_word(w + W_REPEAT, 1);
    psx_write_word(w + W_DIR, (uint32_t)dir);
    psx_write_word(w + W_PULSE, 2);
    psx_write_word(w + W_PULSE_T, 0);
}

static int state_fn(struct CPUState *cpu) {
    const uint32_t w = cpu->gpr[4];
    const uint32_t st0 = psx_read_word(w + W_STATE), cur0 = psx_read_word(w + W_CURSOR);
    const uint32_t scroll0 = psx_read_word(w + W_SCROLL);
    func_override_call_original(cpu);
    if (psx_read_word(w + W_STATE) != 7) return 1;
    const uint32_t pad = psx_read_word(w + W_PAD);
    if ((pad >> 24) != 0x80u) return 1;
    const uint32_t held = psx_read_half(pad), press = psx_read_half(pad + 2);
    const uint32_t cur = psx_read_word(w + W_CURSOR);
    if (st0 == 7 && cur0 != MODS) {
        /* the game just scrolled SPECIAL -> VR TRAINING or back: MODS sits in between */
        const int moved = (scroll0 == 0 || scroll0 == 6) && psx_read_word(w + W_SCROLL) == 1;
        const uint32_t dir = psx_read_word(w + W_DIR);
        if (moved && ((cur0 == 4 && cur == 5 && dir == 1) || (cur0 == 5 && cur == 4 && dir == 0)))
            psx_write_word(w + W_CURSOR, MODS);
        return 1;
    }
    if (cur != MODS) return 1;
    if (st0 == 6) {  /* menu reopened on MODS: what the game's case blocks set */
        psx_write_word(w + W_PULSE, 2);
        psx_write_word(w + W_PULSE_T, 0);
        psx_write_word(w + W_SCROLL, 0);
        return 1;
    }
    /* MODS: the game's case code, with SPECIAL above and VR TRAINING below */
    const uint32_t scroll = psx_read_word(w + W_SCROLL), rep = psx_read_word(w + W_REPEAT);
    if (scroll == 0) {
        if (held & PAD_UP) move_to(cpu, w, 4, 0, 1);
        else if (held & PAD_DOWN) move_to(cpu, w, 5, 1, 1);
        else psx_write_word(w + W_SCROLL, 0);
    } else if (scroll == 6) {
        if (rep < 6) psx_write_word(w + W_REPEAT, rep + 1);
        else if (held & PAD_UP) move_to(cpu, w, 4, 0, 0);
        else if (held & PAD_DOWN) move_to(cpu, w, 5, 1, 0);
        else { psx_write_word(w + W_SCROLL, 0); psx_write_word(w + W_REPEAT, 0); }
    }
    if (psx_read_word(w + W_CURSOR) != MODS) return 1;
    if (press & PAD_OK) {
        guest_call3(cpu, FN_SE, 0, 0x3F, SE_SELECT);
        psx_menu_request_mods_page();
    } else if (press & PAD_CROSS) {  /* back to PRESS START, as the game does */
        psx_write_word(w + W_REINIT, 1);
        psx_write_word(w + W_STATE, 6);
        psx_write_word(w + 0xA5Cu, 0);
        psx_write_word(w + 0xA44u, 0);
        psx_write_word(w + W_SCROLL, 0);
    }
    return 1;
}

/* ---- the words in view, when MODS is one of them ---- */
static int copy_fn(struct CPUState *cpu) {
    const uint32_t w = cpu->gpr[4];
    if (psx_read_word(w + W_STATE) != 7) {  /* menu closed: every word gets its own texture back */
        if (s_work == w) restore_borrowed(w);
        s_work = 0;
        return 0;
    }
    save_textures(w);
    const int c = (int)psx_read_word(w + W_CURSOR);
    const int scroll = (int)psx_read_word(w + W_SCROLL);
    const int dir = (int)psx_read_word(w + W_DIR);
    /* the animation already ran this frame: it drew step scroll-1 (1..4) or the final layout (5) */
    const int k = (scroll >= 2 && scroll <= 5) ? scroll - 1 : 0;
    int item[4], y[4], n;
    if (k == 0) {
        n = 3;
        for (int i = 0; i < 3; i++) { item[i] = ring_at(c, i - 1); y[i] = 0x37 + 15 * i; }
    } else if (dir == 0) {  /* up: the words come down */
        n = 4;
        for (int i = 0; i < 4; i++) { item[i] = ring_at(c, i - 1); y[i] = k * 3 + 0x28 + 15 * i; }
    } else {                /* down: the words go up */
        n = 4;
        for (int i = 0; i < 4; i++) { item[i] = ring_at(c, i - 2); y[i] = 0x37 + 15 * i - k * 3; }
    }
    int has_mods = 0;
    for (int i = 0; i < n; i++) has_mods |= item[i] == MODS;
    if (!has_mods) {  /* the game's own layout is right */
        restore_borrowed(w);
        s_uploaded = 0;   /* uploaded again when MODS comes back into view */
        return 0;
    }
    /* MODS takes the polygon of an entry out of view */
    int slot = -1;
    for (int cand = 1; cand <= 3 && slot < 0; cand++) {
        int used = 0;
        for (int i = 0; i < n; i++) used |= item[i] == cand;
        if (!used) slot = cand;
    }
    if (slot < 0) return 0;
    if (s_borrowed != slot) { restore_borrowed(w); lend_to_mods(w, slot); }
    if (!s_uploaded) { upload_mods_word(); s_uploaded = 1; }
    int poly[4], bright[6] = {0, 0, 0, 0, 0, 0};
    for (int i = 0; i < n; i++) {
        poly[i] = item[i] == MODS ? slot : item[i];
        set_xy(POLY(w, poly[i]), kHalf[item[i]], y[i]);
        bright[poly[i]] = 0x100;
    }
    if (k == 0) {
        set_grad(POLY(w, poly[0]), 0, 0, 0, 0x80, 0xC0, 0x80);
        set_semi(POLY(w, poly[0]), 1);
        set_semi(POLY(w, poly[1]), 0);
        set_grad(POLY(w, poly[2]), 0x80, 0xC0, 0x80, 0, 0, 0);
        set_semi(POLY(w, poly[2]), 1);
        if (c == MODS) {
            /* the game does not highlight cursor 6: same red pulse on MODS's polygon */
            for (int i = 0; i < 6; i++) psx_write_word(w + W_BRIGHT + 4u * i, (uint32_t)bright[i]);
            guest_call3(cpu, FN_HILITE, w, (uint32_t)slot, 0);
            return 0;
        }
    } else if (dir == 0) {
        const int bot1 = k < 3 ? 0 : (k - 2) * 128 / 3;
        const int top2 = k < 4 ? k * 128 / 3 : 0x80;
        const int bot3 = k < 3 ? 0x80 : 0x80 - (k - 2) * 128 / 3;
        const int bot4 = k < 4 ? 0x80 - k * 128 / 3 : 0;
        if (k < 3) bright[poly[0]] = 0;
        if (k >= 4) bright[poly[3]] = 0;
        set_shade(POLY(w, poly[0]), 0, bot1);
        set_shade(POLY(w, poly[1]), top2, 0x80);
        set_shade(POLY(w, poly[2]), 0x80, bot3);
        set_shade(POLY(w, poly[3]), bot4, 0);
        for (int i = 0; i < 4; i++) set_semi(POLY(w, poly[i]), 1);
    } else {
        const int bot1 = k < 4 ? 0x80 - k * 128 / 3 : 0;
        const int top2 = k < 3 ? 0x80 : 0x80 - (k - 2) * 128 / 3;
        const int bot3 = k < 4 ? k * 128 / 3 : 0x80;
        const int bot4 = k < 3 ? 0 : (k - 2) * 128 / 3;
        if (k >= 4) bright[poly[0]] = 0;
        if (k < 3) bright[poly[3]] = 0;
        set_shade(POLY(w, poly[0]), 0, bot1);
        set_shade(POLY(w, poly[1]), top2, 0x80);
        set_shade(POLY(w, poly[2]), 0x80, bot3);
        set_shade(POLY(w, poly[3]), bot4, 0);
        for (int i = 0; i < 4; i++) set_semi(POLY(w, poly[i]), 1);
    }
    for (int i = 0; i < 6; i++) psx_write_word(w + W_BRIGHT + 4u * i, (uint32_t)bright[i]);
    return 0;  /* the game's copy runs with the corrected polygons */
}

PSX_MOD_CONSTRUCTOR(mgs_title_mods_register) {
    (void)func_override_add_guarded("mgs.title-mods.state", FN_STATE, state_fn, kGuardState, 4,
                                    FO_CREDIT_SELF);
    (void)func_override_add_guarded("mgs.title-mods.copy", FN_COPY, copy_fn, kGuardCopy, 4,
                                    FO_CREDIT_SELF);
}
