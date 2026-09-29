# Vendored: binjgb

`binjgb.js` and `binjgb.wasm` are the prebuilt WebAssembly build of
[binjgb](https://github.com/binji/binjgb), a Game Boy emulator by Ben Smith,
copied unchanged from its `docs/` folder. MIT licensed, see `LICENSE`.

- Upstream: https://github.com/binji/binjgb
- Commit: `16621111ed0ee73bcc45c912a823bcebedcffc0f`
  ("Set sprite palette to SGB color area (#82)")
- Files: `docs/binjgb.js`, `docs/binjgb.wasm`, `LICENSE`

`binjgb.js` is a classic script that defines a global `Binjgb()` factory and
loads `binjgb.wasm` from its own directory. `../player.js` drives it through
the exported C functions listed in upstream `src/emscripten/exported.json`.

To update, copy the two files and `LICENSE` from a newer binjgb checkout and
change the commit above.
