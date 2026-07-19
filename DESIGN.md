# Recall - Design Language

This documents the visual language that already exists in `frontend/src/App.css` (and its
pairing with `frontend/src/App.jsx`). It is written from the code as it stands - every
token, scale, and animation below is something actually in use, not an aspiration for a
future redesign. Treat this as the source of truth for future UI changes: if a new rule
needs a color, radius, or motion, it should reach for something on this page before
inventing a new one-off value.

## Principles

- **Dark-first only.** `:root { color-scheme: dark; }` is hardcoded and there is no light
  theme anywhere in the stylesheet. Every surface, shadow, and glow assumes a near-black
  background.
- **Cinematic / camera-app feel.** The camera stage (`.stage`) has a vignette overlay, a
  scan-line sweep during analysis, and viewfinder corner brackets - the app is meant to
  read like a camera viewfinder HUD, not a generic form-based web app.
- **Glow on interactive/live accent surfaces.** Anything that represents "this is live or
  actionable right now" - the primary button, the recording pill, the PTT orb, the
  recalled-memory card - gets a soft colored `box-shadow` glow in its semantic hue. Passive
  surfaces (panels, rows, chips) do not glow.
- **One semantic hue per state, reused consistently.** Blue (`--accent`) = primary/live/
  informational, purple (`--purple`) = voice/conversational, red (`--danger`) = destructive/
  recording, green (`--green`) = a connected/live status dot. Amber (see below) = caution.

## Color palette

Defined once in `:root`, all consumed via `var()` for solid fills/text (12 uses of
`--accent`, 8 of `--danger`, 6 of `--purple`, etc.) Alpha-blended borders/shadows on top of
these colors are written as literal `rgba(...)` triples that numerically match the hex
above (e.g. `--accent: #60a5fa` <-> `rgba(96, 165, 250, ...)`) rather than through a
computed alpha token - that is the actual, consistent convention in this file, not a bug.

| Token | Value | Meaning / where used |
|---|---|---|
| `--bg` | `#03060d` | Page background (near-black navy) |
| `--panel` | `#0a1120` | Default card/row surface (memory entries, chips container, banners) |
| `--panel-border` | `#162033` | Default 1px border on panel surfaces |
| `--panel-hover` | `#0f1929` | Reserved hover-state panel shade - not yet wired into any rule |
| `--accent` / `--accent-bright` | `#60a5fa` / `#93c5fd` | Primary blue: live status dot, primary button, viewfinder corners, scan sweep, search input focus, "Remembered" badge text (bright variant) |
| `--accent-dim` | `#1a3355` | Dark blue tint for gradients/hover backgrounds (header icon, onboarding step numbers, chip-more, search-ask hover) |
| `--accent-glow` / `--accent-glow-strong` | `rgba(96,165,250,.14)` / `rgba(96,165,250,.32)` | Reserved glow tokens - not currently referenced; glows in practice are hand-written literal `rgba()` per rule (see convention note above) |
| `--purple` | `#a78bfa` | Voice/conversational: voice-start button, PTT orb active state, assistant transcript bubble |
| `--purple-dim` | `#2a1b50` | Dark purple tint for the same gradients/backgrounds |
| `--purple-glow` | `rgba(167,139,250,.18)` | Reserved, not currently referenced (same convention note as accent-glow) |
| `--danger` | `#f87171` | Destructive/recording: rec dot, recording pill border/text, danger button, delete-on-hover |
| `--danger-dim` | `#1e0909` | Dark red tint (delete button hover background) |
| `--green` | `#34d399` | Live WebSocket status dot only |
| `--amber` | `#fbbf24` | **Added in this pass.** Caution: the recording pill's "Flash budget exhausted" state. See "Amber: two families" below. |
| `--text` / `--muted` / `--muted-bright` | `#e2e8f4` / `#5a6b8a` / `#8a9ab8` | Body text, secondary/label text, secondary text one step brighter (used on dark empty-state copy) |
| `--radius` / `--radius-sm` | `18px` / `12px` | See radius scale below |

### Amber: two deliberately separate families (not merged)

The task brief flagged two different amber treatments and asked whether they should
converge on shared tokens. Looking at how the file actually uses color, they map onto an
existing split that already exists for red, so I kept them split rather than merging:

1. **"Pop" semantic color** (`--accent`, `--purple`, `--danger`, and now `--amber`) - a
   solid, saturated hue used directly via `color: var(--x)` on live/interactive surfaces,
   paired with hand-written `rgba()` alpha borders/shadows that numerically match the hex.
   `.recording-pill.budget-warn` is this family: it sits over live camera video with
   `backdrop-filter: blur`, exactly like its sibling `.recording-pill.pill-scanning` (which
   does the same thing with `--accent`). It now uses `var(--amber)` for its text color
   instead of the un-tokenized `#fbbf24` literal it had before.
2. **"Static alert box" palette** (`.warn`, `.error`, `.ws-banner`) - flat, muted, near-black
   backgrounds with a dim tinted border and a brighter (but not fully saturated) text color,
   used for passive banner messages on the page (not overlaid on video). Notably, `.error`
   already does **not** reference `--danger` at all - it has its own independent hex triple
   (`#100404` / `#350808` / `#fca5a5`). `.warn` and `.ws-banner` follow that same
   already-established "independent alert-box palette" pattern for amber
   (`#100c02`/`#352800`/`#d4a730` and `#120e02`/`#3a2e08`/`#d4a730` respectively - note both
   already share the exact same text color, `#d4a730`). Since this mirrors a pattern that
   already exists for red without being tokenized, I left it as literal hex rather than
   forcing it onto `--amber` - doing so would make amber more tokenized than red for no
   functional reason, and risks two colors of banner drifting apart in future edits for a
   subtlety nobody asked to change. `.ws-reconnect` (the button inside the banner) uses a
   brighter `#f0c040`, mirroring how `--accent-bright` is a lighter variant of `--accent` for
   emphasis on dark surfaces.

If a future change wants a fully consistent light/dark amber pair (or wants to finally wire
up `--accent-glow`/`--purple-glow`), that is a slightly bigger, more invasive pass than "one
night's polish" and is deliberately left alone here.

## Radius scale

`--radius` (18px) and `--radius-sm` (12px) are the two tokens, used on the "big card"
surfaces (stage, onboarding, recalled spotlight, observation, empty-recording, manual-recall,
lightbox image) and the "banner" surfaces (`.warn`, `.error`, `.ws-banner`) respectively.
Beyond the two tokens, there is a real but informal scale of ad hoc radii for smaller
elements, which is intentional graduation by element size rather than drift:

| Radius | Used for |
|---|---|
| `999px` | Pills: buttons, chips, status chip, stats bar, search input, all "capsule" shaped controls |
| `50%` | Perfectly round elements: dots, shutter button, PTT orb, ob-num circles, lightbox close |
| `20px` | `.ctrl-icon` (large icon buttons under the camera stage) |
| `18px` (`--radius`) | Large content cards |
| `14px` | `.memory-entry` timeline rows (mid-size row, one step down from a full card) |
| `11px`-`12px` (`--radius-sm`) | Header icon (11px, close enough to be the same visual step) and banners |
| `10px` | `.memory-thumb` and `.status` debug tiles (small square media/tiles) |
| `6px`-`8px` | Tiny inline icon buttons (`.recalled-x`, `.memory-delete`) |

The one genuine one-off found and fixed in this pass: `.t-bubble` (transcript chat bubbles)
had `border-radius: 18px` written as a literal instead of `var(--radius)`, despite being
exactly the `--radius` value. Changed to reference the token directly - zero visual change,
just removes a duplicate hardcoded number that should have been the variable.

## Typography scale

No formal type scale exists as tokens; sizes are set per-rule in `rem`, but they cluster
into clear bands when read across the file:

| Band | Range | Used for |
|---|---|---|
| Display | `2.4rem`-`2.5rem` | `<h1>` brand wordmark, empty-recording eye icon |
| Large glyph | `1.25rem`-`1.4rem` | PTT mic icon, lightbox close glyph |
| Body emphasis | `0.9rem`-`0.94rem` | Onboarding step titles, memory location line, observation location |
| Body | `0.85rem`-`0.92rem` | Transcript bubbles, warn/error text, empty-recording copy |
| Small / secondary | `0.73rem`-`0.8rem` | Memory description, chips, tag line, latency line |
| Micro / label | `0.58rem`-`0.7rem` | Uppercase tracking labels: ctrl-label, ptt-label, timeline heading, debug summary/labels |

This is a real, working scale even without named tokens - the bands map directly onto a
type-role hierarchy (display -> emphasis -> body -> secondary -> label), so it was left as-is
rather than introducing font-size custom properties for a single-page app this size.

## Motion / animation vocabulary

Every `@keyframes` block in the file and what it communicates:

| Keyframe | Communicates | Used on |
|---|---|---|
| `pulse` | "This is live right now" | Live WS status dot, rec dot, scanning rec dot, active PTT mic icon |
| `slide-in` | "A new item just appeared" | Stats bar on mount, new memory-entry rows, manual search result card |
| `spotlight-in` | "A recalled memory is surfacing" | `.recalled` card (voice-triggered memory recall) |
| `wave` | Voice input is being captured | Waveform bars while talking |
| `float` | Idle/ambient waiting state | Empty-recording eye icon, gentle bob while waiting for the first scan |
| `ring-out` | Voice input is actively listening | Expanding ripple rings behind the active PTT orb |
| `corner-glow` | The camera is actively analyzing a frame | Viewfinder corner brackets while `.stage--scanning` |
| `scan-line` | A scan is in progress | The horizontal sweep overlay during scanning |
| `lb-in` | A modal opened | Lightbox fade-in |

## Known gaps (documented, not changed)

- `--panel-hover`, `--accent-glow`, `--accent-glow-strong`, and `--purple-glow` are defined
  in `:root` but never referenced by any rule. They read as reserved-for-later tokens rather
  than dead code to delete outright; left in place since removing unused `:root` custom
  properties has zero visual effect and isn't part of a "polish to the existing language"
  pass - flagging here so a future pass either wires them in or removes them deliberately.
- The `.warn`/`.ws-banner` static alert-box palette (see "Amber" section above) is close
  but not byte-identical between the two rules; both already share the same text color, so
  this reads as a very minor, imperceptible drift rather than a functional inconsistency -
  left alone to keep this pass's diff limited to changes that are actually visible.
