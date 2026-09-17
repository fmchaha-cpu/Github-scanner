# v0.9.0 — Evidence-preserving marketplace hydration

Built from the first production v0.8 scan.

## What the v0.8 scan taught us

- Recall jumped from 79 to 294 final listings because PlayerAuctions browser discovery became usable again.
- PlayerAuctions contributed 215 unique listings, but seller/server completeness collapsed because the same product is often linked by a rich title anchor and a later generic `BUY NOW` anchor. The old card map kept the last observation and discarded richer evidence.
- ZeusX seller extraction improved strongly, but detail availability and identity binding remained weak.
- The persistent historical seed was still absent from D1, so the historical engine had no reliable seed pool during the scan.

## v0.9 changes

- Merge repeated anchors for the same exact listing URL instead of overwriting the earlier observation.
- Prefer rich title/image labels over generic `BUY NOW`, `View`, or `Details` anchors.
- Recover conservative PlayerAuctions server/AR hints from product slugs and known EU query context.
- Tighten PlayerAuctions pattern-drift diagnostics so category/filter URLs are not counted as missed product URLs.
- Extend AR parsing for marketplace forms such as `MaleAR55`, `FemaleAR 55`, and the common `Famale` typo.
- Recognize ZeusX `Server/Region` detail labels and semantically-styled buy controls.
- Reserve deep-verification capacity: candidates no longer consume the full hard cap; affordable high-merit incomplete rows get dedicated `merit_probe` verification.
- Automatically import/repair the evidence-backed historical tracker seed when D1 is missing it, then verify the persistent count.
- Keep historical comparables descriptive only; they do not change alert decisions in v0.9.
- Worker/collector version handshake updated to v0.9.

## Regression coverage

v0.9 adds regression tests for duplicate PlayerAuctions title/BUY-NOW anchors, URL/query hydration, AR concatenation, product-pattern diagnostics, ZeusX server/availability evidence, and verification-budget reservation.
