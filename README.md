# Longshot Ocarina

Play the ocarina in **Longshot** (the PC *Ocarina of Time* build) with a **real
ocarina**. The app listens through your microphone, works out which note
you're playing, and presses that note's button on a virtual Xbox controller.
Your real controller keeps working alongside it.

- Only listens while the ocarina is out in-game, so talking, music or a dog
  barking can't move Link around.
- Finds the "ocarina is up" flag in the game's memory automatically, even after
  Longshot restarts.
- Optional fingering pop-up over the game while you learn the notes.
- Ignores the game's own sounds when you play out loud through TV speakers.
- Can start by itself when Longshot starts.

<!-- SCREENSHOT / GIF: replace this comment with e.g.
![Playing the ocarina in Longshot with the fingering pop-up](docs/demo.gif) -->

> Tested with **Longshot v3.0.0-rc.3 and rc.5**. A Longshot update can move the in-game
> flag the app reads; if the Setup tab then says the game flag isn't found, use
> **More settings → Game Flag → Find it manually** (everything else keeps
> working).

> Not affiliated with Nintendo or the Longshot project. You need your own copy
> of Longshot; nothing from the game is included here.

---

## What you need

| | |
|---|---|
| **PC** | Windows 10 or 11 (Linux: experimental, see below) |
| **Game** | Longshot, run **windowed or borderless** (needed for the fingering pop-up) |
| **Ocarina** | A 12-hole Alto C ocarina. We built and tested everything with this 3D-printed one: [Printables model #474058](https://www.printables.com/model/474058). Others work, but the fingering pictures assume a 12-hole Alto C. |
| **Microphone** | Any mic; a headset or webcam mic is fine |
| **Driver** | [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases), the free virtual controller driver. Install it once and reboot. |

## Install

1. Download `OcarinaTranslator.exe` from the [Releases](../../releases) page.
2. Put it in its own folder, e.g. `C:\Games\OcarinaTranslator\`. It saves its
   settings (`config.json`) next to itself.
3. Install **ViGEmBus** if you haven't already (link above).

Windows SmartScreen may warn about an unknown app the first time. Click *More
info → Run anyway*.

**Antivirus warnings:** some antivirus tools may flag the exe. It's a
single-file PyInstaller app (it unpacks Python to a temp folder when it
starts), and it reads another program's memory (Longshot's, to see whether the
ocarina is out). Both of those look suspicious to heuristic scanners. It only
*reads* that one value and never writes to the game. If you'd rather not trust
a downloaded exe, [build it from source](#build-from-source). It's the same
code.

## First-time setup

The app has three main tabs (**Setup**, **Calibrate** and **Play**), worked
through left to right. Everything else is tucked away under **More
settings**, and you don't need it to get going. The **Setup** tab has a
*Ready to play?* checklist with a fix-it button next to anything that isn't
done yet.

1. **Setup**
   - Pick your microphone. The level bar should move when you play.
   - **Close Longshot**, then click **Apply bindings**. This points Longshot's
     ocarina-note slots at the virtual controller. Then click **Fix** next to
     *"Notes only reach Longshot while its window is focused"*, and **Turn it
     off** next to *"Longshot's own microphone input is on"*. All of these back
     up `longshot_options.ini` first.
   - **Turn off Longshot's own microphone input.** Longshot has a built-in
     "Listening for audio…" mic feature. If it's on as well as this app, the
     game hears your ocarina too, and the two fight over every note. The Setup
     checklist does this for you (it sets `microphone=0`), or you can turn it
     off in Longshot's own settings.
   - Start Longshot and load your save. Then click **Measure background
     noise** and stay quiet for 2 seconds, with the game running at your usual
     volume.
   - Playing through TV or speakers instead of headphones? Game sounds are
     filtered out by default; if the game plays through a different output
     than Windows' default, pick it under **More settings → Sound & startup**.
2. **Calibrate**: for each of the 5 notes, finger it as the picture shows,
   click *Record take* (or press Space) and play it. Do 3 takes per note, played
   the way you'd play in the game rather than your most careful note.
   - Optional: **D-pad left** is a sixth row. Record any pitch that isn't one
     of your five notes (e.g. a C) and that note presses D-pad left while the
     ocarina is up. For any other button, see *Custom mappings* below.
3. **Play**: click **Start**, take the ocarina out in Longshot and play.
   Tick *Show note fingerings…* to get the pop-up while you learn.

Want to practise without touching the game? **More settings → Practice**.

That's it. Next time you only need to open the app and click Start, or let it
start by itself (below).

### The five notes

| In-game | Controller button | Pitch |
|---|---|---|
| A | LB | D5 |
| C-Down | RB | F5 |
| C-Right | B | A5 |
| C-Left | X | B5 |
| C-Up | Y | D6 |

## Features

### Listens only while the ocarina is up
*When to listen* (**More settings → Play options**) defaults to **Only while
the ocarina is up**. The app reads this from Longshot's memory, and the Setup checklist shows
*"Game flag found automatically"* when it's working. If it ever can't find the
flag (for example after a Longshot update), it switches to **Scroll Lock** and
tells you, so it never silently stops working. You can then use **More
settings → Game Flag → Find it manually** (see Troubleshooting).

### Fingering pop-up
**Play → Show note fingerings…**: shows the fingering for each note over the game
while the ocarina is up, styled to match the game's ocarina screen, and fades
away when you lower it.
- Drag it to move it. Drag its bottom-right corner to resize it.
- Under **More settings → Play options**, tick a note under **Learned (hide)**
  once you know it and it disappears from the pop-up.

### Start with Longshot
**More settings → Sound & startup → Start automatically when Longshot
starts** adds the app to Windows
startup. It then waits hidden in the background. When Longshot starts, it
appears and starts playing on its own; when Longshot closes, it hides again.

### Brings the game to the front
When you play a note and Longshot isn't the active window, the app focuses it,
so your controller works straight away. You can turn this off in **More
settings → Play options**.

### Custom mappings (advanced)
**More settings → Play options → ▸ Custom mappings**: map any pitch to *any* controller input, such as
the d-pad, sticks, triggers or Start.
- **Hold**: pressed for as long as you hold the note.
- **Timed**: pressed for a set time, with an optional delay. For example, one
  note pushes the left stick forward for 10 seconds.
- To use them with the ocarina put away too, and try playing the whole
  game with an ocarina if you're brave enough, tick *Also listen for D-pad left
  and custom mappings…* under **When to listen** (same tab). It's off by
  default.
- Set the pitch by typing it, picking a note name, or clicking **Listen** and
  playing it.

## Linux (experimental)

The app has Linux support, but it has **not been tested on a real Linux
machine yet**. If you try it, please report back on
[issue #1](https://github.com/maplerouteadmin-dev/longshot-ocarina/issues/1).

Run it from source (there's no Linux download yet):

```bash
sudo apt install python3-tk python3-venv xdotool      # or your distro's equivalents
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py
```

One-time permissions:

- **Virtual controller:** the app creates an Xbox-style pad through
  `/dev/uinput`. Allow your user to do that, then log out and back in:
  ```bash
  echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/60-ocarina-uinput.rules
  sudo usermod -aG input $USER
  ```
- **Reading the ocarina flag:** most distros only let a program read
  another's memory if it started it. Either allow it until the next reboot
  with `sudo sysctl kernel.yama.ptrace_scope=0`, or give Python (or the built
  app) the permission with `sudo setcap cap_sys_ptrace=eip <path>`.

What to expect:

- **Mic, calibration, notes and the virtual pad:** should work like on
  Windows.
- **Ocarina flag:** the automatic lookup isn't set up for the Linux build yet,
  so use **More settings → Game Flag → Find it manually** after each Longshot
  restart. Running `tools/arena_scan.py` on Linux (see
  `tools/FLAG_POINTER_NOTES.md`) would let us add automatic lookup.
- **Fingering pop-up and bringing the game to the front:** X11 only (needs
  `xdotool`). Wayland doesn't allow either, so on Wayland, including Steam
  Deck gaming mode, the pop-up may not show.
- **Start with Longshot:** adds `~/.config/autostart/ocarina-translator.desktop`.
- **Build a single-file binary:** `./build_linux.sh`.

## Troubleshooting

| Problem | Try |
|---|---|
| The game and the app both react to notes, or notes come out doubled | Turn off Longshot's own microphone input (Setup checklist, with Longshot closed) |
| Nothing happens in game | Setup checklist: all ✔? Is Play started? Did you apply the bindings with Longshot **closed**? |
| Notes only work when the game window is clicked | Setup → *Fix* on the background-input line (with Longshot closed) |
| Wrong note, or notes trigger themselves | Re-measure background noise; recalibrate in the room and at the volume you play in; check *More settings → Sound & startup → Game sounds* if you use speakers |
| "Game flag not found" | More settings → Game Flag → *Find it manually*: follow the prompts (away / up / play) and click *Use this flag* |
| Pop-up doesn't appear | Run Longshot windowed or borderless, not exclusive fullscreen |
| A and B (or X and Y) seem swapped | The virtual pad assumes a Switch-style layout in Longshot. Open an issue with your setup. |

**Never** bind Longshot's `key_note_*` (keyboard) slots: that disables the real
controller. The app only uses `pad_note_*`.

## Build from source

Needs Python 3.12 or newer on Windows.

```bash
pip install -r requirements.txt
python app.py
```

`build.bat` builds `dist\OcarinaTranslator.exe` with PyInstaller.

### How it works

- **Pitch:** YIN pitch detection on ~21 ms windows, a reading every ~5 ms. A
  note is pressed once the pitch holds steady for 30 ms, so the sweep while your
  breath ramps up can't cause stray presses. Each note's window is half the
  distance to its nearest neighbour.
- **Game sounds:** captures what the PC sends to your speakers (WASAPI
  loopback) and ignores pitches the game itself is playing.
- **Ocarina flag:** Longshot runs the game inside one large block of emulated
  console memory. The flag sits at fixed offsets inside it, so the app reads 31
  of them and takes a majority vote (`ocarina_flag.py`, `flag_spots.py`). If a
  Longshot update moves them, `tools\arena_scan.py` finds them again. See
  `tools\FLAG_POINTER_NOTES.md`.
- **Output:** a virtual Xbox 360 pad via ViGEmBus (`vgamepad`).

| File | What it does |
|---|---|
| `app.py` | the app (all tabs) |
| `engine.py` | live pipeline: mic → matcher → gate → virtual pad, custom mappings |
| `audio.py`, `pitch.py`, `matcher.py` | mic input, pitch detection, note decisions |
| `echo.py` | game-sound filter (speaker loopback) |
| `ocarina_flag.py`, `flag_spots.py` | read the "ocarina is up" flag |
| `flag_scan.py`, `memscan.py` | the manual flag scan (Game Flag tab) |
| `tools/` | developer tools used to find the flag (`arena_scan.py`, `ptrscan.py`, `flag_probe.py`) and notes |
| `version.py` | the app version shown in the title bar |
| `overlay.py` | fingering pop-up |
| `custom_ui.py`, `gamewin.py` | custom mappings, game window focus |
| `gamepad.py` (`gamepad_win.py` / `gamepad_linux.py`) | virtual pad: ViGEmBus on Windows, uinput on Linux |
| `procmem.py` | finding Longshot and reading its memory on Windows and Linux |
| `setup_helpers.py` | driver check, Longshot ini settings, autostart |
| `calibration.py`, `fingering.py`, `diagram.py` | calibration and fingering charts |
| `translator.py`, `calibrate.py` | older command-line versions |
| `build.bat`, `build_linux.sh` | build the Windows exe / Linux binary |

## License

[MIT](LICENSE) © 2026 The Longshot Ocarina contributors
