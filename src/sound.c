/* Sound effects and music, written straight to the Game Boy's sound
   registers. See docs/DESIGN.md ("Sound API") and the Pan Docs sound pages.

   Channels:
     ch1  pulse  sound effects (jump, double jump, score, death, start, pause)
     ch4  noise  sound effects (the crunch in the death sound)
     ch2  pulse  music melody
     ch3  wave   music bass, using the custom wave shape in bass_wave[]

   Everything is table driven and stepped once per frame by sound_update():

   - A sound effect is a list of steps. Each step sets a pitch, a volume
     envelope and a pitch slide (added to the pitch every frame) for a
     number of frames. The hardware envelope does the fading.
   - A song has one track per channel. A track is an order list of
     patterns, each played with a transposition, and loops back to the
     start at its end. A pattern is a list of (note, length in frames)
     pairs. Both tracks of a song add up to the same length, so they stay
     in step when they loop.

   sound_update() only uses 8-bit counters, table lookups and one 16-bit
   add per frame (no multiply or divide). Measured in PyBoy with a timer:
   about 250 cycles a frame with nothing playing, 450 with music playing,
   and at most about 2100 (3% of the 70224-cycle frame) when notes, a
   pattern change and a new sound effect all land on the same frame.

   Hardware notes:
   - The DACs are turned on once in sound_init() and never turned off:
     switching a DAC on or off makes an audible click. A channel is
     silenced by retriggering it at volume 0 with an "increase" envelope
     (NRx2 = 0x08), which keeps its DAC on; ch3 is muted with NR32.
     (NRx2 = 0x00 would turn the DAC off.)
   - Wave RAM is written once, in sound_init(), while ch3 is off.
   - Retriggering ch3 while it is playing can corrupt wave RAM on the DMG,
     so every bass note is cut by the length counter just before the next
     one starts (see bass_next()), and music_stop() makes ch3 go idle
     within a few milliseconds. */
#include <gb/hardware.h>
#include <stdint.h>

#include "sound.h"

/* ---- Register values ---- */

#define TRIGGER      0x80   /* NRx4: (re)start the channel */
#define LENGTH_ON    0x40   /* NRx4: stop the channel when its length counter runs out */

#define DUTY_12      0x00   /* NRx1: pulse duty cycles; thinner to fuller */
#define DUTY_25      0x40
#define DUTY_50      0x80

/* NRx2: start volume (0-15) that fades by one step every pace/64 s. */
#define ENV(vol, pace)  (((vol) << 4) | (pace))
#define SILENT_ENV   0x08   /* volume 0, "increase" but never steps: silent, DAC stays on */

#define WAVE_MUTE    0x00   /* NR32 output levels */
#define WAVE_FULL    0x20
#define WAVE_HALF    0x40

/* The 11-bit pulse-channel period value for a frequency in Hz (rounded). */
#define HZ(f)  (2048 - (131072UL + (f) / 2) / (f))

/* ---- Notes ---- */

/* Note numbers index the period tables. On the pulse channels note C3 is
   131 Hz; the wave channel plays the same period value an octave lower
   (C3 sounds as C2). */
enum {
    C3, Cs3, D3, Ds3, E3, F3, Fs3, G3, Gs3, A3, As3, B3,
    C4, Cs4, D4, Ds4, E4, F4, Fs4, G4, Gs4, A4, As4, B4,
    C5, Cs5, D5, Ds5, E5, F5, Fs5, G5, Gs5, A5, As5, B5,
    C6, Cs6, D6, Ds6, E6, F6, Fs6, G6, Gs6, A6, As6, B6
};

/* Period values (2048 - 131072 / Hz), equal temperament with A4 = 440 Hz,
   split into the low byte (NRx3) and the top 3 bits (NRx4). */
static const uint8_t note_lo[48] = {
    0x16, 0x4E, 0x83, 0xB5, 0xE5, 0x11, 0x3B, 0x63, 0x89, 0xAC, 0xCE, 0xED,   /* C3-B3 */
    0x0B, 0x27, 0x42, 0x5B, 0x72, 0x89, 0x9E, 0xB2, 0xC4, 0xD6, 0xE7, 0xF7,   /* C4-B4 */
    0x06, 0x14, 0x21, 0x2D, 0x39, 0x44, 0x4F, 0x59, 0x62, 0x6B, 0x73, 0x7B,   /* C5-B5 */
    0x83, 0x8A, 0x90, 0x97, 0x9D, 0xA2, 0xA7, 0xAC, 0xB1, 0xB6, 0xBA, 0xBE    /* C6-B6 */
};
static const uint8_t note_hi[48] = {
    4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5,
    6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7
};

/* Wave RAM for the bass: 32 4-bit samples, high nibble first. A soft
   sawtooth (harmonics 1 : 1/2 : 1/4 : 1/8): warm, but with enough
   overtones to be heard on the small speaker. It peaks at 12 rather than
   15 to sit a little lower in the mix. */
static const uint8_t bass_wave[16] = {
    0x69, 0xBC, 0xCB, 0xBA, 0x99, 0x98, 0x87, 0x76,
    0x66, 0x55, 0x44, 0x33, 0x32, 0x11, 0x00, 0x13
};

/* ---- Sound effect data ---- */

typedef struct {
    uint8_t len;      /* frames; 0 ends the effect */
    uint8_t duty;     /* NR11 */
    uint8_t env;      /* NR12, and retrigger; 0 = legato: keep the note and
                         its fade going, only change the pitch */
    uint16_t period;  /* 11-bit period value, see HZ() */
    int8_t slide;     /* added to the period every frame: + is up */
} tone_step_t;

typedef struct {
    uint8_t len;      /* frames; 0 ends the effect */
    uint8_t env;      /* NR42, and retrigger; 0 = keep the noise going */
    uint8_t poly;     /* NR43: noise clock (higher = lower rumble) */
} noise_step_t;

/* A rising sweep, bright and snappy: about 460 Hz up to 1 kHz in 0.15 s,
   faded out by 0.18 s. */
static const tone_step_t sfx_jump_steps[] = {
    { 11, DUTY_25, ENV(12, 1), HZ(460), 17 },
    { 0 }
};

/* Two quick chirps, higher than the jump: "bwip-bweep". */
static const tone_step_t sfx_double_jump_steps[] = {
    { 3, DUTY_25, ENV(11, 1), HZ(700), 22 },
    { 10, DUTY_25, ENV(10, 1), HZ(880), 9 },
    { 0 }
};

/* "Ding": A5 then E6, ringing out. */
static const tone_step_t sfx_score_steps[] = {
    { 4, DUTY_50, ENV(10, 0), HZ(880), 0 },
    { 12, DUTY_50, ENV(11, 1), HZ(1319), 0 },
    { 0 }
};

/* A short high hit, then a long fall (G5 down to about 190 Hz) as it fades. */
static const tone_step_t sfx_death_steps[] = {
    { 3, DUTY_50, ENV(15, 2), HZ(988), 0 },
    { 27, DUTY_50, 0, HZ(784), -20 },
    { 0 }
};

/* The crunch under the death sound: noise that drops from a hiss to a rumble. */
static const noise_step_t sfx_death_noise[] = {
    { 2, ENV(15, 1), 0x31 },
    { 4, 0, 0x54 },
    { 10, 0, 0x66 },
    { 0 }
};

/* A quick C major arpeggio: C5 E5 G5 C6. */
static const tone_step_t sfx_start_steps[] = {
    { 3, DUTY_25, ENV(12, 1), HZ(523), 0 },
    { 3, DUTY_25, ENV(12, 1), HZ(659), 0 },
    { 3, DUTY_25, ENV(12, 1), HZ(784), 0 },
    { 12, DUTY_25, ENV(11, 1), HZ(1047), 0 },
    { 0 }
};

/* A short blip (G6). */
static const tone_step_t sfx_pause_steps[] = {
    { 9, DUTY_50, ENV(9, 1), HZ(1568), 0 },
    { 0 }
};

/* ---- Music data ---- */

/* Pattern bytes: note, length in frames; or one of these. */
#define REST  0x40   /* a note number: silence for its length */
#define INS   0xFE   /* INS, a, b: set the track's instrument (see melody_next, bass_next) */
#define END   0xFF   /* end of the pattern: go on to the next order entry */

/* Instrument settings for INS. */
#define GATE_STACCATO  1   /* bass notes last about half their length */
#define GATE_LEGATO    2   /* bass notes last nearly all of their length */

typedef struct {
    const uint8_t *pat;
    uint8_t transpose;     /* added to every note in the pattern */
} order_t;

/* In the bass patterns notes are intervals above the chord root, which the
   order list gives as the transposition: 0 root, 7 fifth, 12 octave. */

/* -- MUSIC_TITLE: F major, 8th note = 18 frames (100 BPM), 8 bars. -- */
#define L8   18
#define L4   36
#define L4D  54
#define L2   72
#define L2D  108

static const uint8_t title_mel_a[] = {    /* F | Dm | Bb | C */
    INS, DUTY_50, ENV(6, 7),
    C5, L4,  F5, L4,  A5, L4D, G5, L8,
    F5, L4,  D5, L4,  A4, L2,
    As4, L4, D5, L4,  F5, L4D, D5, L8,
    E5, L4,  C5, L4,  G5, L2,
    END
};

static const uint8_t title_mel_b[] = {    /* F | Dm | Gm C | F */
    INS, DUTY_50, ENV(6, 7),
    C5, L4,  F5, L4,  A5, L4D, C6, L8,
    D6, L4,  C6, L4,  A5, L2,
    As5, L4, A5, L8,  G5, L8,  G5, L4,  E5, L4,
    F5, L2D, REST, L4,
    END
};

static const uint8_t title_bass_bar[] = {   /* root, fifth, octave, fifth */
    INS, WAVE_HALF, GATE_LEGATO,
    0, L4,  7, L4,  12, L4,  7, L4,
    END
};

static const uint8_t title_bass_half[] = {
    INS, WAVE_HALF, GATE_LEGATO,
    0, L4,  7, L4,
    END
};

static const order_t title_melody[] = {
    { title_mel_a, 0 }, { title_mel_b, 0 },
    { 0, 0 }
};

static const order_t title_bass[] = {
    { title_bass_bar, F3 }, { title_bass_bar, D3 }, { title_bass_bar, As3 }, { title_bass_bar, C3 },
    { title_bass_bar, F3 }, { title_bass_bar, D3 },
    { title_bass_half, G3 }, { title_bass_half, C3 }, { title_bass_bar, F3 },
    { 0, 0 }
};

#undef L8
#undef L4
#undef L4D
#undef L2
#undef L2D

/* -- MUSIC_GAME: C major, 8th note = 14 frames (about 129 BPM), 16 bars:
      A (C Am F G), A' (C Am F-G C), B (F G Em Am, calmer), B' (F G Em-Am Dm-G). -- */
#define L8   14
#define L4   28
#define L4D  42
#define L2   56

static const uint8_t game_mel_a[] = {     /* C | Am | F | G */
    INS, DUTY_25, ENV(6, 3),
    C5, L8,  E5, L8,  G5, L8,  E5, L8,  C6, L4,  G5, L8,  E5, L8,
    A4, L8,  C5, L8,  E5, L8,  C5, L8,  A5, L4,  G5, L8,  E5, L8,
    F5, L8,  A5, L8,  C6, L8,  A5, L8,  G5, L8,  F5, L8,  E5, L8,  D5, L8,
    G4, L8,  B4, L8,  D5, L8,  F5, L8,  E5, L4,  D5, L4,
    END
};

static const uint8_t game_mel_a2[] = {    /* C | Am | F G | C */
    INS, DUTY_25, ENV(6, 3),
    C5, L8,  E5, L8,  G5, L8,  E5, L8,  C6, L4,  D6, L8,  E6, L8,
    E6, L4,  D6, L8,  C6, L8,  A5, L4,  C6, L8,  A5, L8,
    A5, L8,  C6, L8,  A5, L8,  F5, L8,  B5, L8,  D6, L8,  B5, L8,  G5, L8,
    C6, L4,  G5, L8,  E5, L8,  C5, L4,  REST, L4,
    END
};

static const uint8_t game_mel_b[] = {     /* F | G | Em | Am: longer notes, rounder sound */
    INS, DUTY_50, ENV(6, 5),
    A5, L4D, G5, L8,  F5, L4,  A5, L4,
    G5, L4D, F5, L8,  D5, L4,  B4, L4,
    E5, L8,  G5, L8,  B5, L8,  G5, L8,  E6, L4,  D6, L4,
    C6, L4D, B5, L8,  A5, L2,
    END
};

static const uint8_t game_mel_b2[] = {    /* F | G | Em Am | Dm G7, leading back to the top */
    INS, DUTY_25, ENV(6, 3),
    A5, L8,  C6, L8,  F6, L8,  C6, L8,  A5, L8,  C6, L8,  A5, L8,  F5, L8,
    G5, L8,  B5, L8,  D6, L8,  B5, L8,  G5, L8,  B5, L8,  D6, L4,
    E6, L4,  B5, L8,  G5, L8,  A5, L4,  E5, L8,  C6, L8,
    D6, L8,  A5, L8,  F5, L8,  A5, L8,  G5, L8,  F5, L8,  D5, L8,  B4, L8,
    END
};

static const uint8_t game_bass_bounce[] = {       /* octave-bouncing 8ths, one bar */
    INS, WAVE_HALF, GATE_STACCATO,
    0, L8,  12, L8,  0, L8,  12, L8,  0, L8,  12, L8,  0, L8,  12, L8,
    END
};

static const uint8_t game_bass_bounce_half[] = {  /* the same, half a bar */
    INS, WAVE_HALF, GATE_STACCATO,
    0, L8,  12, L8,  0, L8,  12, L8,
    END
};

static const uint8_t game_bass_stop[] = {         /* stop-time: a breath before B */
    INS, WAVE_HALF, GATE_STACCATO,
    0, L4,  7, L4,  0, L4,  REST, L4,
    END
};

static const uint8_t game_bass_walk[] = {         /* half-time feel for B */
    INS, WAVE_HALF, GATE_LEGATO,
    0, L4D,  0, L8,  12, L4,  7, L4,
    END
};

static const order_t game_melody[] = {
    { game_mel_a, 0 }, { game_mel_a2, 0 }, { game_mel_b, 0 }, { game_mel_b2, 0 },
    { 0, 0 }
};

static const order_t game_bass[] = {
    /* A */
    { game_bass_bounce, C3 }, { game_bass_bounce, A3 }, { game_bass_bounce, F3 }, { game_bass_bounce, G3 },
    /* A' */
    { game_bass_bounce, C3 }, { game_bass_bounce, A3 },
    { game_bass_bounce_half, F3 }, { game_bass_bounce_half, G3 }, { game_bass_stop, C3 },
    /* B */
    { game_bass_walk, F3 }, { game_bass_walk, G3 }, { game_bass_walk, E3 }, { game_bass_walk, A3 },
    /* B' */
    { game_bass_bounce, F3 }, { game_bass_bounce, G3 },
    { game_bass_bounce_half, E3 }, { game_bass_bounce_half, A3 },
    { game_bass_bounce_half, D3 }, { game_bass_bounce_half, G3 },
    { 0, 0 }
};

#undef L8
#undef L4
#undef L4D
#undef L2

typedef struct {
    const order_t *melody;   /* ch2 */
    const order_t *bass;     /* ch3 */
} song_t;

static const song_t songs[] = {
    { title_melody, title_bass },   /* MUSIC_TITLE */
    { game_melody, game_bass }      /* MUSIC_GAME */
};
#define NUM_SONGS (sizeof(songs) / sizeof(songs[0]))

/* ---- State ---- */

/* Channel 1 effect: requested by sfx_*(), started by sound_update(). */
static const tone_step_t *tone_req;
static const tone_step_t *tone_step;   /* step playing now, or 0 when idle */
static uint8_t tone_timer;             /* frames left in this step */
static uint16_t tone_period;
static int8_t tone_slide;

/* Channel 4 effect. */
static const noise_step_t *noise_req;
static const noise_step_t *noise_step;
static uint8_t noise_timer;

typedef struct {
    const order_t *first;   /* start of the order list, where it loops back to */
    const order_t *order;   /* entry playing now */
    const uint8_t *p;       /* next byte of its pattern */
    uint8_t transpose;
    uint8_t timer;          /* frames until the next note */
    uint8_t ins_a, ins_b;   /* instrument, from INS */
} track_t;

static track_t melody;      /* ch2: ins_a = NR21 duty, ins_b = NR22 envelope */
static track_t bass;        /* ch3: ins_a = NR32 level, ins_b = gate (GATE_*) */
static uint8_t music_on;
static uint8_t music_paused;

/* ---- Sound effect player ---- */

/* Plays the step tone_step points at, or ends the effect at the end marker. */
static void tone_play_step(void) {
    const tone_step_t *s = tone_step;

    if (s->len == 0) {
        tone_step = 0;
        NR12_REG = SILENT_ENV;
        NR14_REG = TRIGGER;
        return;
    }
    tone_timer = s->len;
    tone_period = s->period;
    tone_slide = s->slide;
    NR11_REG = s->duty;
    NR13_REG = (uint8_t)tone_period;
    if (s->env) {
        NR12_REG = s->env;
        NR14_REG = TRIGGER | (uint8_t)(tone_period >> 8);
    } else {
        NR14_REG = (uint8_t)(tone_period >> 8);   /* new pitch, same note */
    }
}

static void noise_play_step(void) {
    const noise_step_t *s = noise_step;

    if (s->len == 0) {
        noise_step = 0;
        NR42_REG = SILENT_ENV;
        NR44_REG = TRIGGER;
        return;
    }
    noise_timer = s->len;
    NR43_REG = s->poly;
    if (s->env) {
        NR42_REG = s->env;
        NR44_REG = TRIGGER;
    }
}

/* ---- Music player ---- */

/* Moves a track's read pointer on to a note when it is at the end of a
   pattern (going on to the next order entry, or back to the start of the
   song) and/or at an INS command. So every pattern must hold at least one
   note, with at most one INS before each note. It is inlined into
   melody_seek() and bass_seek(), which lets the compiler work on the track
   globals directly instead of through a pointer: far fewer cycles. */
static inline void track_seek(track_t *t) {
    const uint8_t *p = t->p;
    const order_t *o;

    if (*p == END) {
        o = t->order + 1;
        if (!o->pat) o = t->first;   /* end of the song: loop */
        t->order = o;
        t->transpose = o->transpose;
        p = o->pat;
    }
    if (*p == INS) {
        t->ins_a = p[1];
        t->ins_b = p[2];
        p += 3;
    }
    t->p = p;
}

static void melody_seek(void) { track_seek(&melody); }
static void bass_seek(void)   { track_seek(&bass); }

/* The next note of each track. These use the track globals directly (no
   pointers), which is what keeps sound_update() cheap on note frames. */
static void melody_next(void) {
    const uint8_t *p;
    uint8_t n;

    if (*melody.p >= INS) melody_seek();   /* if there was no frame to do it in */
    p = melody.p;
    n = p[0];
    melody.timer = p[1];
    melody.p = p + 2;

    if (n == REST) {
        NR22_REG = SILENT_ENV;
        NR24_REG = TRIGGER;
        return;
    }
    n += melody.transpose;
    NR21_REG = melody.ins_a;
    NR22_REG = melody.ins_b;
    NR23_REG = note_lo[n];
    NR24_REG = TRIGGER | note_hi[n];
}

static void bass_next(void) {
    const uint8_t *p;
    uint8_t n, ticks, g;

    if (*bass.p >= INS) bass_seek();
    p = bass.p;
    n = p[0];
    ticks = p[1];
    bass.timer = ticks;
    bass.p = p + 2;

    if (n == REST) {
        NR32_REG = WAVE_MUTE;
        return;
    }
    n += bass.transpose;
    /* Gate: the length counter runs at 256 Hz, about 4.3 ticks per frame.
       Giving the note (frames << gate) ticks ends it just before the next
       note (at 94% of its length for GATE_LEGATO, 47% for GATE_STACCATO), so
       ch3 is always idle when it is retriggered. 256 ticks (written as 0)
       is the most. */
    for (g = bass.ins_b; g; g--) {
        if (ticks & 0x80) {
            ticks = 0;
            break;
        }
        ticks <<= 1;
    }
    NR31_REG = (uint8_t)(0 - ticks);   /* 256 - ticks */
    NR32_REG = bass.ins_a;
    NR33_REG = note_lo[n];
    NR34_REG = TRIGGER | LENGTH_ON | note_hi[n];
}

static void track_start(track_t *t, const order_t *o) {
    t->first = o;
    t->order = o;
    t->transpose = o->transpose;
    t->p = o->pat;
    /* The first note plays on the second sound_update(), by when music_stop()
       has let ch3 go idle. */
    t->timer = 2;
}

/* Silences ch2 and ch3 without turning their DACs off. */
static void music_silence(void) {
    NR22_REG = SILENT_ENV;
    NR24_REG = TRIGGER;
    NR32_REG = WAVE_MUTE;
    NR31_REG = 0xFF;          /* one length tick left: ch3 stops within 4 ms */
    NR34_REG = LENGTH_ON;
}

/* ---- API ---- */

void sound_init(void) {
    uint8_t i;

    NR52_REG = 0x00;          /* APU off: clears every sound register */
    NR52_REG = AUDENA_ON;
    NR50_REG = 0x77;          /* master volume: full on both sides, no cartridge audio */
    NR51_REG = 0xFF;          /* every channel to both sides */

    NR10_REG = 0x00;          /* no hardware sweep: slides are done in software */
    NR11_REG = DUTY_50;
    NR12_REG = SILENT_ENV;    /* DACs on, at volume 0 */
    NR21_REG = DUTY_50;
    NR22_REG = SILENT_ENV;
    NR42_REG = SILENT_ENV;

    NR30_REG = 0x00;          /* wave RAM can only be written while ch3 is off */
    for (i = 0; i != sizeof(bass_wave); i++) AUD3WAVE[i] = bass_wave[i];
    NR30_REG = 0x80;          /* ch3 DAC on */
    NR32_REG = WAVE_MUTE;

    tone_req = 0;
    tone_step = 0;
    noise_req = 0;
    noise_step = 0;
    music_on = 0;
    music_paused = 0;
}

void sound_update(void) {
    uint8_t seek;

    /* Channel 1 effect */
    if (tone_req) {
        tone_step = tone_req;
        tone_req = 0;
        tone_play_step();
    } else if (tone_step) {
        if (--tone_timer == 0) {
            tone_step++;
            tone_play_step();
        } else if (tone_slide) {
            tone_period += tone_slide;
            NR13_REG = (uint8_t)tone_period;
            NR14_REG = (uint8_t)(tone_period >> 8) & 0x07;
        }
    }

    /* Channel 4 effect */
    if (noise_req) {
        noise_step = noise_req;
        noise_req = 0;
        noise_play_step();
    } else if (noise_step) {
        if (--noise_timer == 0) {
            noise_step++;
            noise_play_step();
        }
    }

    /* Music. A track that has reached the end of a pattern moves on to the
       next one in a frame between its notes, and only one track does that
       per frame: this keeps the most expensive frame cheap. */
    if (music_on && !music_paused) {
        seek = 1;
        if (--melody.timer == 0) {
            melody_next();
        } else if (*melody.p >= INS) {
            melody_seek();
            seek = 0;
        }
        if (--bass.timer == 0) bass_next();
        else if (seek && *bass.p >= INS) bass_seek();
    }
}

void sfx_jump(void)        { tone_req = sfx_jump_steps; }
void sfx_double_jump(void) { tone_req = sfx_double_jump_steps; }
void sfx_score(void)       { tone_req = sfx_score_steps; }
void sfx_start(void)       { tone_req = sfx_start_steps; }
void sfx_pause(void)       { tone_req = sfx_pause_steps; }

void sfx_death(void) {
    tone_req = sfx_death_steps;
    noise_req = sfx_death_noise;
}

void music_play(uint8_t song) {
    const song_t *s;

    if (song >= NUM_SONGS) return;
    music_stop();
    s = &songs[song];
    track_start(&melody, s->melody);
    track_start(&bass, s->bass);
    music_on = 1;
}

void music_stop(void) {
    music_on = 0;
    music_paused = 0;
    music_silence();
}

void music_pause(void) {
    if (music_on && !music_paused) {
        music_paused = 1;
        music_silence();
    }
}

void music_resume(void) {
    music_paused = 0;
}
