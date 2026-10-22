# The listening room

## Direction

A warm instrument enclosure, recessed dark display, physical-looking transport keys and stage indicator lights. Rounded session modules and a disc silhouette give voice processing a different spatial language from the other consoles.

## Outside reference

[Teenage Engineering field system](https://teenage.engineering/products/field-system), inspected on 2026-10-22. Design takeaway: Compact audio instruments distinguish transport, signal stages and the central readout.

This is an original composition and stylesheet. No reference-site code, logos, photographs or proprietary fonts were imported. Fonts use local system stacks; diagrams are original SVG/CSS. No new runtime dependency or third-party request was added.

## Data and behavior

The disc turns only while actual browser audio sources are playing. Standby/processing/playback labels use existing state; stage lights depend on received stage events. Public latency readouts use saved proof.json values. Reduced motion disables the disc animation.

API contracts, authorization, persistence, core algorithms and benchmark datasets were not changed. Existing benchmark outputs remain historical. UI verification and new recordings are saved separately under [docs/results/ui-redesign](results/ui-redesign/).

## Interaction and access

Buttons retain their existing actions and accessible labels. Keyboard focus is visible. Layouts collapse for narrow screens; wide evidence tables scroll inside their own containers. Color is paired with text for status. Motion respects prefers-reduced-motion.

## Review artifacts

- [Actual console](results/ui-redesign/console-desktop.png)
- [Mobile console](results/ui-redesign/console-mobile.png)
- [Browser flow results](results/ui-redesign/browser.json)
- [New console recording](results/ui-redesign/demo.webm)
- [Recording probe](results/ui-redesign/demo-probe.json)
- [Frontend build log](results/ui-redesign/frontend-build.log)

The saved [review-console.py](results/ui-redesign/review-console.py) is the existing real-service browser flow adapted to write into the UI review directory. Run it only against an isolated local demo stack with the normal operator environment configured. Historical performance is not rebenchmarked by this visual review.

Public evidence preview: [desktop](results/ui-redesign/site-desktop.png), [mobile](results/ui-redesign/site-mobile.png), [checks](results/ui-redesign/site-review.json). Publication is a separate approval step.

## Verification disposition

Final build, lint and existing test suites pass. The redesigned console was exercised against actual isolated local services, not mocked counters. The public-page previews use saved evidence and the new actual recording. The local proof was captured before publication. The repository CI workflow reports the currently pushed revision; README lists the public URL where available.
