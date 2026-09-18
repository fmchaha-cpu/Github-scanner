# v0.10.0

Built from the first fully successful v0.9.3 production scan.

## Measured inputs
- 130 listings, 6 candidates, 0 errors
- seller completeness 94.6%; server 87.7%; detail verification 25.4%
- identity verified 0; strict live 0
- 17 historical records active (12 SOLD_CONFIRMED)
- EpicNPC produced an implausible $1.10 whale price
- all 6 candidates had historical comparisons, but all were very-low confidence

## Changes
- identity/merit separation and safer C6 mismatch semantics
- blocked-detail preservation instead of challenge-page parsing
- rich-title preservation against generic H1/domain headings
- exact normalized seller consensus across card/detail profile links
- price plausibility holds plus dedicated verification probes
- identity/plausibility diagnostics in scan quality output
- distinct any-vs-usable historical comparable coverage metrics
- collector v0.10 reuses Worker API v0.9; no Cloudflare deployment required
- GitHub Actions checkout/setup-python moved to Node-24-native major versions

## Validation
- 81 Python tests
- known-case benchmark 6/6
- workflow YAML parsed locally
