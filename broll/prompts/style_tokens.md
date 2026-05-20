# Channel style tokens

These tokens are appended to every AI generation prompt to keep the channel's
visual identity consistent across episodes. Edit this file to evolve the
aesthetic; `broll/lib/prompt_assembly.py` parses the fenced blocks below.

The intent is **gentle nudges**, not a hard style transfer. The shot's actual
content (the user's `intent` string) should dominate; the style tokens
should bias lighting, framing, and palette without overriding the subject.

---

## Positive tokens (applied to every shot)

```positive
cinematic composition, naturalistic color grade, soft volumetric light,
35 mm filmic look, subtle film grain, balanced negative space,
gentle motion, documentary tone
```

## Negative tokens (suppressed in every shot)

```negative
text, watermark, logo, signature, captions, overlay graphics,
oversaturated, low resolution, jpeg artifacts, blurry, distorted,
fisheye, vignette
```

## Tone-specific positive overrides

If the shot spec carries a `tone` field, the matching block is appended to
the positive prompt. Unknown tones are ignored silently.

```tone:calm
unhurried camera, wide composition, even lighting
```

```tone:tense
restrained handheld camera, deeper shadows, cooler palette
```

```tone:observational
fixed camera, no zoom, documentary framing
```

```tone:archival
period-accurate color grade, slight chromatic aberration, soft halation
```

```tone:conceptual
abstract composition, allegorical lighting, simplified palette
```

---

## Model-specific tweaks

LTX-Video 2.3 prefers concise prompts (~30–60 words). Wan 2.2 handles longer
prompts (~80–120 words) and benefits from explicit camera-direction language.

The assembler trims to a soft max for LTX and allows more verbosity for Wan;
the trimming logic lives in `prompt_assembly.py`. Don't expand these blocks
above the per-model budget unless you also raise the cap.
