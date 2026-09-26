"""Regenerate the feature-tour screenshots in docs/assets/screenshots/.

    python docs/make_screenshots.py

Opens the desktop app, runs each test below with made-up data, and saves a picture
of the result, trimmed to the useful part. Needs Windows (or another desktop) and
the `app` extra.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageGrab

from cedikit.app import desktop as d

OUT = Path(__file__).parent / "assets" / "screenshots"


def _grab(root: tk.Tk) -> Image.Image:
    root.update()
    time.sleep(0.5)
    root.update()
    left, top = root.winfo_rootx(), root.winfo_rooty()
    box = (left, top, left + root.winfo_width(), top + root.winfo_height())
    return ImageGrab.grab(bbox=box, all_screens=True)


def _text_lines(img: Image.Image) -> list[tuple[int, int]]:
    """(top, bottom) of each run of rows with content: dark text (some dark pixels,
    but not a solid border line), or a coloured result banner."""
    rgb = img.convert("RGB").crop((40, 0, img.width - 40, img.height))
    width = rgb.width
    pixels = rgb.load()
    assert pixels is not None
    runs: list[tuple[int, int]] = []
    for y in range(rgb.height):
        samples = [pixels[x, y] for x in range(0, width, 2)]
        dark = sum(1 for r, g, b in samples if (r + g + b) / 3 < 110)  # type: ignore[misc]
        coloured = sum(1 for r, g, b in samples if max(r, g, b) - min(r, g, b) > 60)  # type: ignore[misc]
        if 0 < dark < len(samples) * 0.3 or coloured > len(samples) * 0.3:
            if runs and y - runs[-1][1] <= 2:
                runs[-1] = (runs[-1][0], y)
            else:
                runs.append((y, y))
    return runs


def _trim(img: Image.Image) -> Image.Image:
    """Cut the empty space below the last thing shown, and any line cut off by the
    window's edge."""
    lines = _text_lines(img)
    if len(lines) > 2:
        heights = sorted(bottom - top for top, bottom in lines)
        usual = heights[len(heights) // 2]
        last_top, last_bottom = lines[-1]
        # A line sliced by the window (or a box's) edge is shorter than usual.
        if last_bottom - last_top < 0.7 * usual or last_bottom >= img.height - 15:
            lines = lines[:-1]
    bottom = min((lines[-1][1] if lines else img.height) + 28, img.height)
    return img.crop((0, 0, img.width, bottom))


def main() -> None:
    d._enable_sharp_text()
    root = tk.Tk()
    app = d.CedikitApp(root)
    OUT.mkdir(parents=True, exist_ok=True)
    tabs = app.tabs
    check, ledger, phones = tabs["check"], tabs["ledger"], tabs["phones"]
    money_tab, ids = tabs["money"], tabs["ids"]
    assert isinstance(check, d.CheckTab) and isinstance(ledger, d.LedgerTab)
    assert isinstance(phones, d.PhonesTab) and isinstance(money_tab, d.MoneyTab)
    assert isinstance(ids, d.IdsTab)

    def example(name: str) -> None:
        check.example.set(name)
        check._load_example()

    def ids_check(value: str) -> None:
        ids.value.delete(0, "end")
        ids.value.insert(0, value)
        ids.check()

    def money_test() -> None:
        money_tab.amount.delete(0, "end")
        money_tab.amount.insert(0, "1250.50")
        money_tab.show_amount()
        money_tab.estimate()

    scenes: list[tuple[str, tk.Misc, Callable[[], None]]] = [
        ("tour_check_fake", check, lambda: example("Fake cash-in")),
        ("tour_check_blocked", check, lambda: example("Fake 'account blocked'")),
        ("tour_check_genuine", check, lambda: example("Genuine MTN payment")),
        ("tour_check_screenshot", check, check.try_sample_screenshot),
        ("tour_ledger", ledger, ledger.load_sample),
        ("tour_phones", phones, phones.load_sample),
        ("tour_money", money_tab, money_test),
        ("tour_ghana_card", ids, lambda: ids_check("gha 123456789 0")),
        ("tour_foreign_card", ids, lambda: ids_check("FGN-987654321-5")),
        ("tour_address", ids, lambda: ids_check("ak0395028")),
        ("tour_id_invalid", ids, lambda: ids_check("GHA-12345-6")),
    ]

    def run() -> None:
        for name, tab, action in scenes:
            app.notebook.select(tab)  # type: ignore[no-untyped-call]
            action()
            _trim(_grab(root)).save(OUT / f"{name}.png", optimize=True)
            print("saved", name)
        root.destroy()

    root.after(400, run)
    root.mainloop()


if __name__ == "__main__":
    main()
