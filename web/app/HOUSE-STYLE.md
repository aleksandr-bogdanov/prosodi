# House style

The shared design language across the personal projects (imprnt, bogdanov.wtf, whenful, gw2-pvp).
This is the first cut of a reusable spec: the tokens, the light/dark mechanism, and the component
patterns. `src/theme.css` is the working implementation. Lift it into a new project and re-skin the
accent.

## Principles

- **Light is the default.** Every project ships both themes, light first. Dark is a companion on a
  toggle, never the only option.
- **Warm neutrals, never clinical.** Paper (`#f6f4ec`) over pure white, near-black warm ink
  (`#1b1d1a`) over `#000`. The blog and imprnt both land here independently.
- **One accent per product.** A single signature colour carries identity. imprnt is green/teal,
  whenful is purple, gw2 is blue, prosodi is teal (the voice/waveform colour). Pick one, commit.
- **Semantic tokens, not raw values.** Radius derives from one base, motion is named by intent
  (fast/normal/slow), colours are roles (bg, ink, accent) not hexes scattered through markup.
- **Mono for the technical register.** JetBrains Mono on eyebrows, chips, stats, code. It signals
  "this is a builder's tool" without a word of copy.

## Type

```
--font-sans:    "Inter Variable", system-ui, sans-serif        body, UI
--font-display: "Space Grotesk Variable", "Inter Variable"      headings, hero
--font-mono:    "JetBrains Mono Variable", ui-monospace          eyebrows, chips, stats, code
```

Display headings: weight 600, line-height ~1.04, letter-spacing -0.02em. Body: ~1.0625rem, line
height 1.6. Eyebrow: mono, 0.74rem, uppercase, letter-spacing 0.16em, in the accent colour.
(The blog swaps in Newsreader serif for an editorial voice; the rest stay on this trio.)

## Colour architecture

Roles, not raw colours. Light values shown; the dark column is the `.dark` override.

| role | light | dark | use |
|------|-------|------|-----|
| `bg` | `#f6f4ec` | `#0a0b0d` | page |
| `bg-soft` | `#efece1` | `#0e1013` | recessed |
| `surface` | `#fbf9f2` | `#131619` | cards |
| `surface-2` | `#f1ede1` | `#1a1e22` | raised |
| `line` | `#ddd7c7` | `#272c33` | borders |
| `ink` | `#1b1d1a` | `#eceae4` | primary text |
| `ink-soft` | `#585b51` | `#a4a7a0` | secondary text |
| `ink-faint` | `#8b8d81` | `#6c706a` | tertiary text |
| `accent` | per product | per product | the one signature colour |

Accent registry (so each product is distinct but kin):

| product | light accent | dark accent |
|---------|-------------|-------------|
| imprnt | `#0f766e` green/teal | `#54c98a` → `#36c7bf` |
| whenful | `#6d5ef6` purple | `#8b7cf7` |
| gw2-pvp | `#6d5ef6` / `#7db8ff` blue | `#7db8ff` |
| prosodi | `#0d9488` teal | `#2dd4bf` |

A second warm accent (`#c2641e` / `#f0a43c`) carries "the human / the real thing" where a product
needs two poles. Semantic discipline matters: whenful uses purple for success, never green, on
purpose. Keep one meaning per colour.

## Radius and motion

```
--radius: 0.75rem;   xs .25 · sm .5 · (base) .75 · lg 1 · xl 1.4 · 2xl 1.9rem
```

Motion is named by intent, not duration, so the feel is consistent without thinking in ms:

```
--dur-instant .1s · --dur-fast .15s · --dur-normal .2s · --dur-slow .3s · --dur-emphasis .45s
--ease-spring  cubic-bezier(0.34, 1.56, 0.64, 1)   buttons, micro-interactions
--ease-out-expo cubic-bezier(0.16, 1, 0.3, 1)      reveals, panel transitions
```

Always honour `prefers-reduced-motion: reduce` (collapse durations to ~0).

## Light / dark mechanism

Tailwind v4, one pattern. Register the colour roles in `@theme` (these become `bg-*`/`text-*`/
`border-*` utilities and live as `--color-*` vars on `:root`). Then re-declare the same `--color-*`
vars inside `.dark {}`. The utilities reference the vars, so a single class on `<html>` swaps the
whole theme at runtime with no rebuild.

```css
@custom-variant dark (&:where(.dark, .dark *));
@theme { --color-bg: #f6f4ec; /* light defaults */ }
.dark  { --color-bg: #0a0b0d; /* runtime override */ }
```

Set the class before first paint from `localStorage` (an inline script in `<head>`) to avoid a
flash. Persist the choice on toggle. Light is the fallback when nothing is stored.

## Components

Patterns that recur across the projects (full CSS in `theme.css`):

- **Button**: pill (`border-radius: 999px`), `--ease-out-expo` transform on hover (`translateY(-2px)`).
  Primary fills with the accent + a soft accent-coloured glow shadow. Ghost is a tinted surface with
  a `--line` border that warms to the accent on hover.
- **Card**: a subtle top-down gradient (`surface` → `bg-soft`), 1px `--line` border, `--radius-xl`.
- **Glass**: `surface` at ~60% with `backdrop-filter: blur(14px) saturate(140%)` for sticky headers
  and overlays.
- **Eyebrow**: mono uppercase label in the accent, sits above a heading.
- **Chip**: mono, pill, `--line` border on a translucent surface, for tags and metadata.
- **Dotgrid**: a faint radial-dot backdrop (`ink` at ~8%, 26px grid) for texture.

## Reusing this in a new project

1. Copy `theme.css`, swap the `--color-accent*` values for the product's signature colour.
2. Keep the role names, the radius scale, the motion tokens, the light/dark mechanism.
3. Reuse the component utilities (`.btn`, `.card`, `.glass`, `.eyebrow`, `.chip`).
4. Pick the font register: this trio for a tool, the blog's Inter + Newsreader for editorial writing.

The point is that a new project should feel like a sibling, not a clone: same bones, one different
accent.
