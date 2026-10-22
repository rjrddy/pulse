# Project-specific interface: The listening room

Status: accepted for local implementation; publication pending approval.

## Context

The existing portfolio consoles shared a generic dashboard vocabulary. This made unrelated engineering problems look alike and hid the project’s primary object. The user explicitly authorized a visual redesign of the five kept projects.

## Decision

A warm instrument enclosure, recessed dark display, physical-looking transport keys and stage indicator lights. Rounded session modules and a disc silhouette give voice processing a different spatial language from the other consoles.

Research reference: [Teenage Engineering field system](https://teenage.engineering/products/field-system). Compact audio instruments distinguish transport, signal stages and the central readout.

The disc turns only while actual browser audio sources are playing. Standby/processing/playback labels use existing state; stage lights depend on received stage events. Public latency readouts use saved proof.json values. Reduced motion disables the disc animation.

## Consequences

Maintain an independent visual vocabulary for this project; do not extract a shared cross-repository dashboard template. Preserve action names and API behavior so existing integration flows remain meaningful. Keep measured evidence and explicit hosting limits visible on the public page. Use system fonts and original code-native diagrams to keep the runtime self-contained. Save browser proof separately from the original benchmarks.

See [UI design and verification](../UI.md).
