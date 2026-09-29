# PandaJump for Game Boy — build with GBDK-2020.
#
#   make          build build/pandajump.gb
#   make run      build, then open the ROM in mGBA
#   make test     build, then run the headless test suite (needs PyBoy)
#   make art      regenerate art/*.png from tools/make_art.py
#   make web      build, then copy the ROM into web/ for the browser player
#   make clean    delete build/
#
# GBDK_HOME points at the GBDK-2020 install (the AUR package uses /opt/gbdk).

ifndef GBDK_HOME
  ifneq ($(wildcard tools/gbdk/bin/lcc),)
    GBDK_HOME := tools/gbdk/
  else
    GBDK_HOME := /opt/gbdk/
  endif
endif

LCC       := $(GBDK_HOME)/bin/lcc
PNG2ASSET := $(GBDK_HOME)/bin/png2asset
MGBA      ?= mgba-qt
PYTHON    ?= python3

NAME  := pandajump
BUILD := build
RES   := $(BUILD)/res
ROM   := $(BUILD)/$(NAME).gb

# MBC5 + RAM + battery (0x1B), one 8 KiB RAM bank, DMG only.
CART_FLAGS := -Wm-yt0x1B -Wm-ya1 -Wm-yn"PANDAJUMP"
CFLAGS     := -Wa-l -I$(RES) -Isrc
LDFLAGS    := -Wl-m -Wl-j -Wm-yS $(CART_FLAGS)

SRCS := $(sort $(wildcard src/*.c))
OBJS := $(patsubst src/%.c,$(BUILD)/%.o,$(SRCS))

# Art: each PNG has its own png2asset options.
ASSETS     := bg_tiles panda title_logo fx
ASSET_SRCS := $(patsubst %,$(RES)/%.c,$(ASSETS))
ASSET_OBJS := $(patsubst %,$(BUILD)/res_%.o,$(ASSETS))

PNG2ASSET_bg_tiles   := -map -tiles_only -keep_duplicate_tiles -noflip -keep_palette_order -no_palettes
PNG2ASSET_title_logo := -map -tile_origin 128 -noflip -keep_palette_order -no_palettes
PNG2ASSET_panda      := -sw 16 -sh 16 -spr8x8 -px 0 -py 0 -noflip -keep_palette_order -no_palettes
PNG2ASSET_fx         := -sw 8 -sh 8 -spr8x8 -px 0 -py 0 -noflip -keep_palette_order -no_palettes

.PHONY: all run test art web clean check-gbdk
.SECONDARY: $(ASSET_SRCS)

all: $(ROM)

check-gbdk:
	@test -x "$(LCC)" || { echo "GBDK-2020 not found at '$(GBDK_HOME)'. Install it (see README) or run: make GBDK_HOME=/path/to/gbdk/"; exit 1; }

$(RES)/%.c: art/%.png | check-gbdk
	@mkdir -p $(RES)
	$(PNG2ASSET) $< -o $@ $(PNG2ASSET_$*)

$(BUILD)/res_%.o: $(RES)/%.c
	$(LCC) $(CFLAGS) -c -o $@ $<

# Every C file may include any generated header, so build the art first.
$(BUILD)/%.o: src/%.c $(wildcard src/*.h) $(ASSET_SRCS) | check-gbdk
	@mkdir -p $(BUILD)
	$(LCC) $(CFLAGS) -c -o $@ $<

$(ROM): $(OBJS) $(ASSET_OBJS)
	$(LCC) $(LDFLAGS) -o $@ $^

run: $(ROM)
	$(MGBA) $(ROM)

test: $(ROM)
	$(PYTHON) -m pytest -q tests

art:
	$(PYTHON) tools/make_art.py

web: $(ROM)
	cp $(ROM) web/$(NAME).gb

clean:
	rm -rf $(BUILD)
