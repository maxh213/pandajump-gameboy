# PandaJump for Game Boy — build with GBDK-2020.
#
#   make            build build/pandajump.gb
#   make run        build, then play it in mGBA (from play/, so the save survives make clean)
#   make test       build, then run the headless test suite (needs PyBoy, see requirements-dev.txt)
#   make web        build, then copy the ROM into web/ for the browser player
#   make web-test   make web, then run the browser smoke test (setup: web/README.md#test)
#   make art        regenerate art/*.png from tools/make_art.py (the art's source)
#   make art-check  check art/*.png match tools/make_art.py
#   make DEBUG=1    build with debug info for Emulicious into build/debug/
#   make clean      delete build/
#
# GBDK_HOME points at the GBDK-2020 install. By default the Makefile uses
# tools/gbdk (installed by tools/get-gbdk.sh), else /opt/gbdk (the AUR package).

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
# The README's virtualenv, when there is one.
PYTHON    ?= $(if $(wildcard .venv/bin/python3),.venv/bin/python3,python3)

NAME  := pandajump
BUILD := build
ifeq ($(DEBUG),1)
  BUILD := build/debug
endif
RES   := $(BUILD)/res
ROM   := $(BUILD)/$(NAME).gb

# MBC5 + RAM + battery (0x1B), one 8 KiB RAM bank, DMG only, non-Japanese.
CART_FLAGS := -Wm-yt0x1B -Wm-ya1 -Wm-yn"PANDAJUMP" -Wm-yj
CFLAGS     := -Wa-l -I$(RES) -Isrc
LDFLAGS    := -Wl-m -Wl-j -Wm-yS $(CART_FLAGS)
ifeq ($(DEBUG),1)
  CFLAGS  += -debug
  LDFLAGS += -debug
endif

SRCS := $(sort $(wildcard src/*.c))
HDRS := $(wildcard src/*.h)
OBJS := $(patsubst src/%.c,$(BUILD)/%.o,$(SRCS))

# Art: each PNG has its own png2asset options.
ASSETS     := bg_tiles panda title_logo fx
ASSET_SRCS := $(patsubst %,$(RES)/%.c,$(ASSETS))
ASSET_HDRS := $(patsubst %,$(RES)/%.h,$(ASSETS))
ASSET_OBJS := $(patsubst %,$(BUILD)/res_%.o,$(ASSETS))

PNG2ASSET_bg_tiles   := -map -tiles_only -keep_duplicate_tiles -noflip -keep_palette_order -no_palettes
PNG2ASSET_title_logo := -map -tile_origin 128 -noflip -keep_palette_order -no_palettes
PNG2ASSET_panda      := -sw 16 -sh 16 -spr8x8 -px 0 -py 0 -noflip -keep_palette_order -no_palettes
PNG2ASSET_fx         := -sw 8 -sh 8 -spr8x8 -px 0 -py 0 -noflip -keep_palette_order -no_palettes

# Runs first in every recipe that needs GBDK, so an up-to-date ROM can still be
# played or copied without it.
CHECK_GBDK = @test -x "$(LCC)" || { \
  echo "GBDK-2020 not found at '$(GBDK_HOME)'."; \
  echo "Run tools/get-gbdk.sh (downloads GBDK-2020 4.5.0 into tools/gbdk),"; \
  echo "install the gbdk-2020 AUR package, or run: make GBDK_HOME=/path/to/gbdk/"; \
  exit 1; }

.PHONY: all run test web web-test art art-check clean

all: $(ROM)

# png2asset writes the .c and the .h together. The header is the target; the
# .c is touched so it never looks older, and a missing .c remakes both.
$(RES)/%.h: art/%.png Makefile
	$(CHECK_GBDK)
	@mkdir -p $(RES)
	$(PNG2ASSET) $< -o $(RES)/$*.c $(PNG2ASSET_$*)
	@touch $(RES)/$*.c

$(RES)/%.c: $(RES)/%.h
	@test -f $@ || { rm -f $<; $(MAKE) --no-print-directory $<; }

$(ASSET_OBJS): $(BUILD)/res_%.o: $(RES)/%.c Makefile
	$(CHECK_GBDK)
	$(LCC) $(CFLAGS) -c -o $@ $<

# Every C file may include any generated header, so build the art first.
$(OBJS): $(BUILD)/%.o: src/%.c $(HDRS) $(ASSET_HDRS) Makefile
	$(CHECK_GBDK)
	@mkdir -p $(BUILD)
	$(LCC) $(CFLAGS) -c -o $@ $<

$(ROM): $(OBJS) $(ASSET_OBJS)
	$(CHECK_GBDK)
	$(LCC) $(LDFLAGS) -o $@ $^

# mGBA keeps the battery save (the high score) next to the ROM, so play a copy
# in play/ rather than in build/, which make clean deletes.
run: $(ROM)
	@mkdir -p play
	cp $(ROM) play/$(NAME).gb
	$(MGBA) play/$(NAME).gb

test: $(ROM)
	$(PYTHON) -m pytest -q tests

web: $(ROM)
	cp $(ROM) web/$(NAME).gb

web-test: web
	@test -d web/tests/node_modules/playwright || { \
	  echo "The smoke test needs Playwright. Once: cd web/tests && npm ci && npx playwright install chromium"; \
	  exit 1; }
	cd web/tests && npm test

art:
	$(PYTHON) tools/make_art.py

art-check:
	$(PYTHON) tools/make_art.py --check

clean:
	rm -rf build
