## What changes

<!-- One or two sentences. -->

## Why

<!-- The problem or the request. Link the issue. -->

## Test

I ran these commands and I looked at the PNG files:

1. `python -m py_compile running-card.py examples/make_examples.py`
2. `python running-card.py examples/demo.gpx --output /tmp/demo.png`
3. `python running-card.py examples/dagersheim-waldlauf.fit --output /tmp/race.png`

## Checks

1. [ ] The README matches the new behaviour.
2. [ ] I ran `python examples/make_examples.py` when the card output changed.
3. [ ] The change needs no new dependency, or the README lists the dependency.
