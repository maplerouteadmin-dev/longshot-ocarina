# Ocarina Translator

A small companion app that listens to your real ocarina through your mic and
presses your EXISTING A/Y/X/L/R controls for you, instead of relying on
Longshot's own (unreliable) built-in mic pitch detection.

## Important: do not touch longshot_options.ini's key_note_* fields

We tried routing this through Longshot's separate `key_note_l/r/a/y/x`
binding slots first. Don't do that -- binding ANY of them to a real key
disables controller-based note input entirely, even with a controller still
plugged in and no mic conflict. `longshot_options.ini` has been fully
restored to your original settings (backup still kept at
`longshot_options.ini.backup` for reference) and should stay untouched.

Instead, `keys.py`'s `NOTE_KEYS` just mirrors your CURRENT, already-working
`key_a` / `key_y` / `key_x` / `key_l` / `key_r` bindings and presses those
directly -- the same inputs your keyboard (or in Y's case, left mouse
button -- Longshot encodes mouse buttons in the same numeric field as
keyboard keys) already triggers those controls with. If you ever rebind
A/Y/X/L/R in Longshot's own Controls menu, update `NOTE_KEYS` in `keys.py`
to match.

## One-time setup

```bash
cd /a/OcarinaTranslator
python -m pip install sounddevice numpy
```
(numpy's likely already installed; sounddevice was added for this project.)

## Step 1: Calibrate to your ocarina

```bash
python calibrate.py
```

It'll prompt you to play each of the 5 ocarina notes (A, C-Up, C-Down,
C-Left, C-Right) one at a time, with a 3-2-1 countdown. Hold each note
steady for the full prompt. Results are saved to `notes.json`.

The slot-to-button mapping (`calibrate.py`'s `NOTE_SLOTS`) is a best guess at
which Longshot slot is which real ocarina note. If a note comes out wrong
in-game, swap the two mismatched entries in that list -- no need to
recalibrate, just re-run `translator.py`.

## Step 2: Run the translator while you play

```bash
python translator.py
```

- Press **Scroll Lock** to toggle listening on/off -- it only reads the mic
  while toggled ON, so background noise/talking doesn't get misread as notes
  when you're not actually playing the ocarina.
- Toggle it ON right before you bring up the ocarina in-game, OFF when
  you're done.
- Ctrl+C in the terminal to quit entirely.

## If notes still feel off

- Re-run `calibrate.py` -- a steadier, more consistent breath per note
  during calibration directly improves matching accuracy.
- `MAX_CENTS_OFF` in `translator.py` controls how forgiving the pitch match
  is (150 cents = a bit over a semitone). Lower it for stricter matching if
  it's confusing two close notes; raise it if accurate notes are being
  missed as "no match."
