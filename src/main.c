/* PandaJump: start-up, the main loop and the game states.

   Every frame: wait for VBlank, read the buttons, write the tiles queued
   last frame while the LCD is still in VBlank, update the sound, then run
   the current state from line 1 of the new frame.
   The state code only touches RAM (shadow OAM, the "next" scroll values,
   queued tiles), so what it does appears all at once on the next frame.

   States: title -> play <-> paused, play -> dead -> play. */
#include <gb/gb.h>
#include <gb/metasprites.h>
#include <rand.h>
#include <stdint.h>

#include "config.h"
#include "tiles.h"
#include "game.h"
#include "world.h"
#include "player.h"
#include "hud.h"
#include "save.h"
#include "sound.h"
#include "bg_tiles.h"
#include "title_logo.h"
#include "panda.h"
#include "fx.h"

uint8_t game_state;
uint16_t score;
uint16_t high_score;
uint8_t frame_count;
uint8_t debug_invincible;

static uint8_t joy_prev;
static uint8_t pressed;           /* buttons that went down this frame */
static uint8_t state_timer;
static uint8_t ramp_count;        /* points since the last difficulty step */
static uint8_t rng_seeded;
static uint8_t music_on = 1;
static uint8_t prompt_shown;

#ifdef DEBUG_TIMING
/* Lines of LCD time the frame's work took, counted from the start of
   VBlank (line 144). The logic has to end before the next VBlank, so
   anything under 154 fits in the frame. */
uint8_t debug_lines;
uint8_t debug_lines_max;

static void measure_frame(void) {
    uint8_t ly = LY_REG;

    debug_lines = (ly >= 144) ? ly - 144 : ly + 10;
    if (debug_lines > debug_lines_max) debug_lines_max = debug_lines;
}
#endif

static void start_run(void) {
    uint8_t from_title = (game_state == STATE_TITLE);

    hud_prompt(0);
    hud_messages_clear();
    world_start_run(from_title);
    player_reset();
    player_draw();                /* back on its feet in the new run's first frame */
    score = 0;
    ramp_count = 0;
    hud_score(0);
    sfx_start();
    if (music_on) music_play(MUSIC_GAME);
    game_state = STATE_PLAY;
}

/* State changes set game_state last, so whoever sees the new state (the
   tests, reading RAM between frames) also sees everything that goes with it. */
static void die(void) {
    uint8_t new_best = 0;

    state_timer = 0;
    prompt_shown = 0;
    player_die();
    sfx_death();
    music_stop();
    if (score > high_score) {
        high_score = score;
        save_store(high_score);
        hud_high(high_score);
        new_best = 1;
    }
    hud_message(0, 7, "GAME OVER");
    hud_message_num(1, 8, new_best ? "NEW BEST! " : "SCORE ", score);
    game_state = STATE_DEAD;
}

static void title_state(void) {
    world_scroll();               /* no boxes on the title */
    player_run();
    player_draw();
    if ((frame_count & BLINK_FRAMES) ? prompt_shown : !prompt_shown) {
        prompt_shown = !prompt_shown;
        hud_prompt(prompt_shown);
    }
    if (rng_seeded) {
        rand();                   /* stir: the run also depends on when Start comes */
    } else if (pressed) {
        /* The only entropy is when the player presses: the joypad and DIV
           are read at the same point of every frame, so this seed is a
           function of the press frame. */
        initrand(((uint16_t)DIV_REG << 8) | frame_count);
        rng_seeded = 1;
    }
    if (pressed & J_SELECT) {
        music_on = !music_on;
        if (music_on) music_play(MUSIC_TITLE);
        else music_stop();
    }
    if (pressed & (J_START | J_A)) start_run();
}

static void play_state(void) {
    uint8_t jump;

    if (pressed & J_START) {
        sfx_pause();
        music_pause();            /* silent, but keeps its place in the song */
        hud_message(0, 8, "PAUSED");
        game_state = STATE_PAUSED;
        return;
    }
    if (pressed & J_A) {
        jump = player_press();
        if (jump == JUMPED) {
            sfx_jump();
        } else if (jump == DOUBLE_JUMPED) {
            sfx_double_jump();
            fx_start((uint8_t)(panda_y >> 8) + 12);
        }
    }
    jump = player_physics();
    if (jump) {                   /* landed */
        fx_start(GROUND_Y - 8);
        if (jump == JUMPED) sfx_jump();   /* a kept press took off again */
    }
    world_scroll();
    world_clouds(world_speed);
    player_run();

    if (!debug_invincible && world_hit(player_feet())) {
        die();
    } else if (world_cleared()) {
        score++;
        hud_score(score);
        sfx_score();
        if (++ramp_count == RAMP_EVERY) {
            ramp_count = 0;
            world_ramp();
        }
    }
    player_draw();
    fx_update(world_step);
}

static void paused_state(void) {
    if (pressed & J_START) {
        hud_message_clear(0);
        sfx_pause();
        if (music_on) music_resume();
        game_state = STATE_PLAY;
    }
}

static void dead_state(void) {
    player_dead_fall();
    player_draw();
    fx_update(0);
    world_clouds(SPEED_BASE);     /* the sky keeps drifting */
    if (state_timer < DEAD_DELAY) {
        state_timer++;
        return;
    }
    if ((frame_count & BLINK_FRAMES) ? prompt_shown : !prompt_shown) {
        prompt_shown = !prompt_shown;
        if (prompt_shown) hud_message(2, 9, "PRESS START");
        else hud_message_clear(2);
    }
    if (pressed & (J_START | J_A)) start_run();
}

void main(void) {
    uint8_t joy;
    uint8_t ly;

    DISPLAY_OFF;
    BGP_REG = 0xE4;
    OBP0_REG = 0xD0;
    OBP1_REG = 0xD0;
    set_bkg_data(0, bg_tiles_TILE_COUNT, bg_tiles_tiles);
    set_bkg_data(T_LOGO_BASE, title_logo_TILE_COUNT, title_logo_tiles);
    set_sprite_data(S_PANDA_BASE, panda_TILE_COUNT, panda_tiles);
    set_sprite_data(S_FX_BASE, fx_TILE_COUNT, fx_tiles);
    hide_sprites_range(0, MAX_HARDWARE_SPRITES);

    world_init();
    hud_init();
    high_score = save_load();
    hud_score_hide();             /* no score on the title */
    hud_high(high_score);
    hud_vram();
    sound_init();

    game_state = STATE_TITLE;
    world_title();
    player_reset();
    player_draw();
    if (music_on) music_play(MUSIC_TITLE);

    SHOW_BKG;
    SHOW_WIN;
    SHOW_SPRITES;
    DISPLAY_ON;

    /* A button held since power-on is not a press: it has to be released
       and pressed again (otherwise it would skip the title, and with the
       same seed every time). */
    joy_prev = joypad();

    while (1) {
        vsync();
        /* Sample the buttons at the same moment every frame (the start of
           VBlank), before the variable amount of tile writing. */
        joy = joypad();
        frame_count++;
        hud_vram();               /* the score row is the first one drawn */
        world_vram();
        sound_update();

        pressed = joy & (uint8_t)~joy_prev;
        joy_prev = joy;

        /* Run the game logic in the visible part of the frame, from line 1
           (LY also reads 0 during most of line 153). This costs a few idle
           lines but keeps each frame's RAM changes together within one
           emulator frame, so headless tests see whole frames and a fixed
           input latency. LY is read once per test: reading it twice could
           see 153 and then 0 and leave during line 153. */
        if (LCDC_REG & LCDCF_ON) {
            do {
                ly = LY_REG;
            } while (ly == 0 || ly >= 144);
        }

        switch (game_state) {
        case STATE_TITLE:  title_state();  break;
        case STATE_PLAY:   play_state();   break;
        case STATE_PAUSED: paused_state(); break;
        default:           dead_state();   break;
        }
#ifdef DEBUG_TIMING
        measure_frame();
#endif
    }
}
