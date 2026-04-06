import sys
import time
import ctypes

# Windows virtual-key codes for media keys
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1

KEYEVENTF_KEYUP = 0x0002


def press_key(vk_code: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python media_keys_test.py [play|next|prev]")
        return 2
    cmd = sys.argv[1].strip().lower()
    if cmd in ("play", "pause", "toggle"):
        press_key(VK_MEDIA_PLAY_PAUSE)
        print("Sent: Play/Pause")
        return 0
    if cmd in ("next", "n"):
        press_key(VK_MEDIA_NEXT_TRACK)
        print("Sent: Next Track")
        return 0
    if cmd in ("prev", "previous", "p"):
        press_key(VK_MEDIA_PREV_TRACK)
        print("Sent: Previous Track")
        return 0
    print("Unknown command. Use: play|next|prev")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
