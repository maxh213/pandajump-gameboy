# GitHub Actions workflow

`build.yml` is ready to use. Claude's GitHub App can't create files in
`.github/workflows/`, so it lives here; copy it in to turn it on:

```sh
mkdir -p .github/workflows
cp ci/build.yml .github/workflows/
```

On every push and pull request it:

1. checks `art/*.png` match `tools/make_art.py` (the art's source),
2. builds the ROM and checks the committed `web/pandajump.gb` matches it,
3. runs the headless test suite (`make test`) and uploads the ROM,
4. runs the browser smoke test in `web/tests/` against the committed ROM.

On a push to `main`, once all of that passes, it publishes `web/` (the
browser player and the ROM, without its tests) to GitHub Pages. Turn Pages
on first: Settings > Pages > Source: GitHub Actions.
