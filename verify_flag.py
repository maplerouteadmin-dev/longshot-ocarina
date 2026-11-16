"""Live poller: prints the candidate flag's value in real time so we can
visually confirm it tracks ocarina up/down as you toggle it, before trusting
it in the real translator."""
import time
import memscan

ADDR = 0x1F812A0F784

pm = memscan.attach()
print(f"Polling 0x{ADDR:X} every 0.2s. Toggle the ocarina up/down and watch the value. Ctrl+C to stop.")
last = None
try:
    while True:
        val = pm.read_bytes(ADDR, 1)[0]
        if val != last:
            print(f"value changed -> {val}")
            last = val
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\nStopped.")
