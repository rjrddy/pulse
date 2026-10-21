"""Verify the actual console and record a local demonstration, never simulated telemetry."""

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("docs/results")
with sync_playwright() as p:
    executable = os.getenv("CHROMIUM_PATH")
    browser = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        record_video_dir=str(out / "recordings"),
        record_video_size={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    errors: list[str] = []
    received: list[dict] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def frame(payload: str | bytes) -> None:
        event = json.loads(payload)
        if "audio" in event:
            event["audio_base64_length"] = len(event.pop("audio"))
        received.append(event)

    page.on("websocket", lambda socket: socket.on("framereceived", frame))
    started = time.monotonic()
    page.goto("http://localhost:8081")
    page.get_by_label("Operator password").fill(os.environ["PULSE_PASSWORD"])
    page.get_by_role("button", name="Sign in").click()
    page.get_by_text("Gateway connected").wait_for()
    page.get_by_role("button", name="Send text", exact=True).click()
    page.locator(".sectiontitle .badge").filter(has_text="Complete").wait_for(timeout=80000)
    assert page.locator(".first strong").inner_text() != "—"
    page.wait_for_timeout(3000)
    page.get_by_role("button", name="Public speech sample").click()
    page.locator(".sectiontitle .badge").filter(has_text="Complete").wait_for(timeout=80000)
    assert "Waiting for a turn" not in page.locator(".conversation").inner_text()
    page.get_by_role("button", name="Interrupt", exact=False).click()
    page.locator(".sectiontitle .badge").filter(has_text="Interrupted").wait_for()
    page.wait_for_timeout(300)
    cancellations = [i for i, e in enumerate(received) if e["type"] == "cancelled"]
    assert cancellations
    index = cancellations[-1]
    generation = received[index]["generation"]
    assert not any(e["generation"] < generation for e in received[index + 1 :])
    page.get_by_label("Text prompt").fill("How do retries work?")
    page.get_by_role("button", name="Send text", exact=True).click()
    page.locator(".sectiontitle .badge").filter(has_text="Complete").wait_for(timeout=80000)
    page.screenshot(path=str(out / "console-desktop.png"), full_page=True)
    page.get_by_role("heading", name="Durable turn history").scroll_into_view_if_needed()
    page.wait_for_timeout(4000)
    page.evaluate("window.scrollTo(0,0)")
    # Keep an actual live console visible for the requested recording length.
    while time.monotonic() - started < 90:
        remaining = 90 - (time.monotonic() - started)
        page.wait_for_timeout(min(remaining, 10) * 1000)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(500)
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
    page.screenshot(path=str(out / "console-mobile.png"), full_page=True)
    assert not errors, errors
    video = page.video
    context.close()
    video.save_as(str(out / "demo.webm"))
    browser.close()
(out / "browser.json").write_text(
    json.dumps(
        {
            "page_errors": errors,
            "public_speech_processed": True,
            "text_pipeline_processed": True,
            "interruption_acknowledged": True,
            "old_generation_after_cancel_ack": False,
            "replacement_completed": True,
            "mobile_no_overflow": True,
            "events": received,
        },
        indent=2,
    )
    + "\n"
)
print("Actual speech, text, interruption, replacement and responsive checks passed.")
