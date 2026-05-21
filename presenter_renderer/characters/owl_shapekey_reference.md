# Owl Shape Key Reference

Human-readable **contract** for every shape key on `characters/owl.blend`.
The animation + lipsync layers reference these by name; renaming a key here is a
breaking change for every scene (AGENT.md "Pitfalls: linked owl gotchas").

Layered, additive system (recap.md §6): 9 visemes + 6 emotions + 8
micro-expressions combine to cover ~80 expressions without pre-baking each one.

## Visemes — Rhubarb 9-shape, owl-adapted (Phase 0)
| Key | Rhubarb | Notes |
|-----|---------|-------|
| `Basis` | — | neutral default |
| `viseme_A` | A (M/B/P) | closed beak |
| `viseme_B` | B | |
| `viseme_C` | C | |
| `viseme_D` | D (A/O) | wide-open vowel |
| `viseme_E` | E | |
| `viseme_F` | F (F/V) | |
| `viseme_G` | G | |
| `viseme_H` | H (L) | |
| `viseme_X` | X | silence / rest |

## Emotion overlays — additive (Phase 1)
`emo_neutral`, `emo_concerned`, `emo_alert`, `emo_contemplative`,
`emo_skeptical`, `emo_focused`

## Micro-expressions — additive, low values (Phase 1)
`brow_raise_inner`, `brow_raise_outer`, `brow_furrow`, `eye_squint_L`,
`eye_squint_R`, `beak_part_slight`, `horn_L_flare`, `horn_R_flare`

> TODO: fill in actual per-key descriptions as the owl is built.
