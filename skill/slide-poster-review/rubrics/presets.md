# Viewing presets

Used by `scripts/font_size.py`. Context rubrics may override a row by preset name.
Text size is rated by the visual angle of the cap height at the viewing distance.

- `distance` for slides is in projected-image heights (`8H` = 8 times the height of the projected
  image). For posters it is metres from the reader's eyes to the printed poster.
- `L2`, `L3`, `L4` are the lower bounds of each level, in arcminutes of cap height. Below `L2` is L1.
  The bounds follow display standards and reading research (ISO 9241-303, ANSI/HFES 100,
  MIL-STD-1472, Legge): about 10′ is the absolute floor, 16′ the minimum for comfortable
  reading, and 22′ preferred. See `references/legibility-thresholds.md`.
- The bounds are the same for every audience (universal design).
- `default: yes` marks the preset used for each kind when none is chosen.

| preset           | kind   | distance | L2 | L3 | L4 | default | notes                                        |
|------------------|--------|----------|----|----|----|---------|----------------------------------------------|
| slides-8H        | slides | 8H       | 10 | 16 | 22 | yes     | back row at 8H; L2/L3/L4 ≈ 18/29/40 pt        |
| slides-large-room| slides | 12H      | 10 | 16 | 22 | no      | big room, small screen; ≈ 27/43/59 pt        |
| poster-1.5m      | poster | 1.5      | 10 | 16 | 22 | yes     | reading distance; ≈ 18/28/39 pt at print size |
| poster-headline  | poster | 2.0      | 10 | 16 | 22 | no      | passer-by distance; ≈ 24/38/52 pt             |
