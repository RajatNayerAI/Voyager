# Voyager — The Galactic Odyssey 

A terminal-based starfield and mission demo written in Python using curses.

This single-file project (`starfield.py`) renders an animated starfield, mission objectives, a small HUD, and simple interactions (scan, warp, pickup). The UI is designed to look arcade-like in a modern terminal.

## Features
- Non-blocking animated starfield and galaxy sprites
- Splash screen with mission briefing
- Procedural star systems and simple mission tasks
- AI copilot messages persistently shown at bottom-right
- Simple ship movement, scanning, warp, and pickups
- Saves a mission report on exit (`mission_report.json` and `.txt`)

## Requirements
- Python 3.8+
- A terminal that supports colors and Unicode (Windows Terminal, ConHost, or WSL recommended)
- On Windows, install the `windows-curses` package to provide curses support:

```powershell
# (run in an elevated/activated environment if needed)
pip install windows-curses
```

On Unix-like OSes (Linux, macOS) `curses` is included with Python by default.

## Run
Open a terminal in the project folder (where `starfield.py` lives) and run:

```powershell
# Windows / PowerShell
python .\starfield.py

# Optional: change visual speed and density
python .\starfield.py --speed 1.0 --density 160
```

If your system uses `python3` as the command, replace `python` with `python3`.

## Controls
- Arrow keys / WASD: Move ship
- X or Space: Scan nearby star-system (must be within scan radius)
- P: Pick up power pack (if nearby)
- Z: Warp to the next galaxy (consumes a lot of fuel)
- I: Toggle AI copilot panel
- M: Toggle mission objectives panel
- L: Show crew log (popup)
- T: Toggle mini-map
- + / - : Increase / decrease visual speed
- Q or ESC: Quit (saves report)

## Configuration (in `starfield.py`)
A few useful constants are at the top of `starfield.py` you can tweak:
- `DEFAULT_SPEED`, `MIN_SPEED`, `MAX_SPEED` — movement visuals
- `STAR_DENSITY` — number of stars
- `POWER_SPAWN_CHANCE`, `POWER_LIFE` — pick-up spawn behavior
- `POWER_COLLECT_RADIUS` — how close you must be to pick a pack
- `SCAN_RADIUS` — how far an X-scan reaches (Euclidean radius)

Example: increase `SCAN_RADIUS` to make scanning easier.

## Notes & Troubleshooting
- Blink/terminal attributes: not all terminals support `A_BLINK`; the code provides fallbacks.
- If the screen looks wrong on Windows, try using Windows Terminal or run inside WSL for best results.
- If colors are missing or look odd, try a different terminal emulator or adjust system color settings.

## Extending the project
Suggestions you may consider:
- Move `GALAXY_DB` into an external JSON file to make galaxies editable without changing code.
- Add ship upgrades that increase `SCAN_RADIUS` or change `POWER_COLLECT_RADIUS`.
- Add sound using a small cross-platform library (optional).

## License
MIT — feel free to reuse and extend for learning or hackathon demos.

---

If you'd like, I can:
- Add a small example JSON loader for `GALAXY_DB` and migrate the in-file data to `galaxies.json`.
- Add a quick test script to validate curses initialization on Windows.
- Tweak or expand the README with screenshots (ASCII samples) or a short dev setup guide.

Tell me which follow-up you want and I'll implement it.
