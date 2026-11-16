# Ocarina Translator

Play Longshot's ocarina with a real ocarina. The app listens through your mic,
works out which note you're playing, and presses that note's button on a
virtual Xbox controller. Your real controller keeps working alongside it.

## Run it

`dist\OcarinaTranslator.exe`, or `python app.py` from source. Settings live in
`config.json` next to whichever one you run.

Needs the free **ViGEmBus** driver (the Setup tab checks for it and links to it).

## First-time setup (tabs, left to right)

1. **Setup** — pick your mic and watch the level bar respond, then click
   *Measure background noise* while staying quiet. Check that the virtual
   controller driver and Longshot's note bindings show ✔. If bindings show ✘,
   close Longshot and click *Apply note bindings* (it backs the file up first).
2. **Calibrate** — for each note, finger it as the picture shows, then click
   *Record take* and play it 3 times. Blow the way you will while playing, not
   your most careful breath. Recalibrate when you change mic or room.
3. **Test** — play notes or practise a song; nothing reaches the game. Shows
   the detected pitch, how far off the nearest note it is, and song progress.
4. **Play** — click Start, then play in the game.
5. **Game Flag** — if listening never turns on when you take the ocarina out
   (Longshot was restarted), run the scan here to find the flag again.
6. **Advanced** — timing and sensitivity settings.

## When does it listen?

- **Game flag** (default): only while Longshot shows the ocarina is up, read
  from the game's memory. The memory location moves each time Longshot is
  relaunched. When it can't be read, the app switches to Scroll Lock and tells
  you, rather than going quiet.
- **Scroll Lock**: while the Scroll Lock light is on.
- **Always**: for testing only — stray sounds can move your character.

## Playing on TV speakers (no headphones)

Turn on **Setup → Game sounds**. The app then listens to what the PC sends to
your speakers or TV and ignores any pitch the game is playing at that moment.
That covers background music and Link playing your note back right after the
game registers it. Without this, each note gets picked up twice: once from you
and once from Link's playback.

- Pick the output the game plays through (e.g. *TV (NVIDIA High Definition
  Audio)*), or leave it on *Windows default output* if that's already the TV.
- Measure background noise with the game running at your normal volume.
- A held note releases when your breath drops below 30% of its peak, so the
  quieter echo from the TV can't keep it held. No note can stay held for more
  than 4 seconds. Both are adjustable on the Advanced tab.
- This only works when the game's sound goes out through this PC, e.g. HDMI
  to the TV. It can't hear audio that reaches the TV some other way.

## How detection works

- **YIN pitch detection** on overlapping ~21ms windows, a reading every ~5ms.
  It doesn't jump octaves the way the first version did.
- A note is pressed once the pitch **holds steady** for 30ms (Advanced tab).
  The pitch sweep while your breath ramps up never holds steady, so it can't
  trigger a stray press. Readings taken while the volume is still rising
  don't count either.
- Each note's acceptance window is **half the distance to its nearest
  neighbour**, so adding notes tightens the windows instead of letting them
  overlap.
- The held note is **sticky**: a small wobble doesn't flip it to the next note.
- Every press lasts at least 100ms, with a short gap between notes, so the
  game registers it.

## Files

| File | What it does |
|---|---|
| `app.py` | the app (tabs above) |
| `engine.py` | live pipeline: mic → matcher → gate → virtual pad |
| `audio.py`, `pitch.py` | mic selection, sliding-window YIN pitch detection |
| `matcher.py` | readings → note press/release decisions |
| `calibration.py`, `calibrate.py` | take recording; command-line calibration |
| `flag_scan.py`, `memscan.py`, `ocarina_flag.py` | find/read the "ocarina is up" flag |
| `setup_helpers.py` | driver check, Longshot note bindings |
| `gamepad.py`, `keys.py` | virtual controller; Scroll Lock state |
| `fingering.py`, `diagram.py` | fingering charts and pictures |
| `translator.py` | command-line version of the Play tab |
| `build.bat` | builds `dist\OcarinaTranslator.exe` |

## Known gaps

- The **A-button (LB)** and **C-Down (RB)** notes aren't calibrated yet, and
  their fingerings aren't confirmed for the printables #474058 model.
- The LB/RB → note mapping hasn't been tested in-game (the face buttons have).
- Only the 12-hole Alto C fingering chart is included so far.

Do **not** bind Longshot's `key_note_*` (keyboard) slots: that disabled the real
controller entirely in testing. The app only ever uses `pad_note_*`.
