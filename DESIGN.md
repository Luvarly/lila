---
name: lila
description: A lilac reactor that shows what a voice assistant is doing right now.
colors:
  ground: "#0a0612"
  lilac: "#c9a7ff"
  lilac-hi: "#efe2ff"
  violet: "#a98bf0"
  you: "#8fb4ff"
  you-ink: "#cddbff"
  amber: "#ffb84d"
  mint: "#7fe0bd"
  coral: "#ff8794"
  ink: "#f2ebff"
  ink-2: "#bdafdc"
  ink-3: "#9686bd"
  rule: "rgb(201 167 255 / 0.13)"
  rule-strong: "rgb(201 167 255 / 0.3)"
  ctx-system: "#9b7bea"
  ctx-mcp: "#e39bf0"
  ctx-memory: "#f2b8d8"
  ctx-reserve: "#8b7bb8"
  ctx-other: "#7d68b8"
typography:
  display:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "clamp(1.35rem, 7.6cqi, 3.5rem)"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.005em"
    fontVariation: "\"wdth\" 108"
  headline:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "1.65rem"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.01em"
    fontVariation: "\"wdth\" 125"
  title:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "1.3rem"
    fontWeight: 500
    lineHeight: 1.2
    fontFeature: "\"tnum\""
    fontVariation: "\"wdth\" 112"
  caption:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "clamp(1.05rem, 0.75rem + 0.55vw, 1.32rem)"
    fontWeight: 400
    lineHeight: 1.5
  body:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Saira, system-ui, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 600
    letterSpacing: "0.16em"
    fontVariation: "\"wdth\" 75"
  mono:
    fontFamily: "Cascadia Mono, Cascadia Code, ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "0.78rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  hairline: "2px"
  tag: "3px"
  pill: "999px"
  disc: "50%"
spacing:
  gutter: "clamp(1rem, 2.2vw, 2rem)"
  row: "0.6rem"
  entry: "1.15rem"
  helper: "0.9rem"
components:
  link-pill:
    textColor: "{colors.ink-3}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "0.28rem 0.7rem 0.28rem 0.6rem"
  link-pill-live:
    textColor: "{colors.mint}"
  link-pill-offline:
    textColor: "{colors.coral}"
  readout-cell:
    textColor: "{colors.ink}"
    typography: "{typography.title}"
    padding: "0.75rem clamp(1rem, 2.2vw, 2rem) 0.85rem"
  caption-lila:
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
  caption-you:
    textColor: "{colors.you-ink}"
    typography: "{typography.body}"
  tool-row:
    textColor: "{colors.ink}"
    padding: "0.6rem 0"
  tool-tag:
    textColor: "{colors.violet}"
    rounded: "{rounded.tag}"
    padding: "0.05rem 0.35rem"
  helper-badge:
    backgroundColor: "{colors.lilac-hi}"
    textColor: "{colors.ground}"
    rounded: "{rounded.disc}"
    size: "1.75rem"
  helper-badge-done:
    backgroundColor: "{colors.mint}"
  helper-badge-failed:
    backgroundColor: "{colors.coral}"
  approval:
    textColor: "{colors.ink}"
    padding: "0.75rem 0.15rem 0.8rem"
  legend-swatch:
    rounded: "{rounded.hairline}"
    size: "0.6rem"
---

# Design System: lila

## Overview

**Creative North Star: "The Lilac Reactor"**

One instrument at the centre of a dark room. A violet-black ground is lit only by lilac light, and the light comes from a circle whose rings are live instruments: an outer tick scale, the context window as a segmented arc, background helpers as satellites on a dotted orbit, a circular trace of who is speaking and how loud, and a core ring that breathes with the voice. Everything around the reactor is flat type on hairline rules: captions on the left, helpers and activity on the right, a readout strip along the bottom, a thin header on top.

The system is a read-only HUD, dense up close and legible from across a desk. Light means something is true right now: the accent colour is the voice state, glow comes only from the reactor's live parts, and motion only plays while the thing it shows is happening. Rejected outright by the user and the build: cards, glass, Jarvis cyan.

**Key Characteristics:**
- Violet-black ground, lilac light, one state accent at a time.
- One variable family (Saira) used across its width axis for every role except commands and paths.
- Hairline rules divide space; nothing floats on a container.
- The reactor is canvas-drawn, scales with its box, and carries all the ambient motion.
- Authored 16px-grid stroke icons at 1.5px, never glyphs.

## Colors

A near-black violet ground, a lilac family for Lila, a periwinkle pair for the user, and three signal hues kept for meaning.

### Primary
- **Lilac** (lilac): Lila herself. Her caption labels, the live caret, tool icons, the focus ring, the listening accent, the "tools" context segment.
- **Lilac Light** (lilac-hi): the brightest state, speaking; the wordmark; running helper badges and satellites; the "messages" context segment.
- **Deep Violet** (violet): the thinking accent and the helper tag on tool rows.

### Secondary
- **Periwinkle** (you): the user's voice. Their caption label, their trace on the reactor, the hearing accent.
- **Periwinkle Ink** (you-ink): the text of what the user said.

### Tertiary
- **Question Amber** (amber): a question waiting for a yes. The asking accent and the approval rules and icon. Nothing else is amber.
- **Done Mint** (mint): finished and live. The live link pill, done tool marks, completed helpers.
- **Failed Coral** (coral): failed and offline. Failed tool marks, failed helpers, the offline link pill.

### Neutral
- **Violet-Black Ground** (ground): the page, plus a soft lilac radial bloom (rgb(124 82 214 / 0.14)) centred behind the reactor.
- **Lilac Ink** (ink): primary text and readout values.
- **Muted Ink** (ink-2): secondary text, older captions, facts, legend labels.
- **Faint Ink** (ink-3): labels, timestamps, empty states, the connecting accent, stopped helpers.
- **Hairline** (rule) and **Strong Hairline** (rule-strong): every divider in the page; the strong one only edges the helper tag.

### Context series
The context legend and the context arc share one series palette: system prompt (ctx-system), system tools (lilac), MCP tools (ctx-mcp), memory files (ctx-memory), messages (lilac-hi), any other category (ctx-other), and the autocompact reserve (ctx-reserve), drawn as a hatched swatch and a dashed arc. Free space is never drawn.

### Named Rules
**The State Is The Light Rule.** One accent is live at a time and it is the voice state: connecting faint ink, listening lilac, hearing periwinkle, thinking violet, speaking lilac light, asking amber. The reactor, the state word and nothing else take it.

**The Signals Mean One Thing Rule.** Amber is only a question, mint only done or live, coral only failed or offline. Never use them for decoration or emphasis.

## Typography

**Display Font:** Saira (self-hosted variable, weights 100 to 900, widths 50% to 125%), with system-ui fallback
**Body Font:** Saira
**Label/Mono Font:** Saira condensed for labels; Cascadia Mono (system mono stack) for commands, paths and arguments only

**Character:** One family worked across its width axis: condensed and tracked for labels, normal width for reading, expanded for numerals and the wordmark. The width change does the work a second family would.

### Hierarchy
- **Display** (state word in the reactor core): sized to the reactor (7.6cqi), slightly expanded, tinted 55% accent toward white.
- **Headline** (the lowercase "lila" wordmark): fully expanded, lilac light.
- **Title** (readout values, 1.3rem; context percent, 1.45rem): expanded tabular numerals.
- **Caption** (Lila's live words): fluid, 1.5 line height. The user's words sit at 1.02rem; anything older than the last two entries drops to 0.95rem muted ink.
- **Body** (helper descriptions, tool names at 0.94rem, details): normal width.
- **Label** (section heads, field names, speaker tags, link pill): condensed, uppercase, 0.16em tracking, faint ink.
- **Mono** (tool arguments, approval command): one line, ellipsised, full text in a title tooltip.

### Named Rules
**The Width Axis Rule.** Hierarchy comes from Saira's width before size: labels at 75%, reading text at 100%, numerals at 112% with tabular figures, the wordmark at 125%.

**The Mono Is Evidence Rule.** Monospace appears only for literal machine text: commands, paths, search queries, URLs. Never for labels or numbers.

## Layout

Three rows: header strip, main, readout strip. Space is divided by 1px hairlines, never by containers. The side gutter is fluid (gutter token) and shared by header, columns and readouts.

- **1180px and wider:** three columns, captions | reactor | work, at 1fr : 1.8fr : 1fr with 17rem minimum sides. Readouts in one row of eight.
- **760 to 1179px:** reactor on the left (1.15fr) spanning two rows; captions top right, helpers and activity bottom right (1fr). Readouts tighten their side padding to 0.85rem.
- **Below 960px:** readouts wrap to four columns with a hairline between rows.
- **Below 760px:** one column in story order: reactor, captions, work; readouts in two columns; header values cap at 16ch.
- **600px height rule:** only when the window is at least 760px wide and 600px tall is the HUD locked to one screen (100dvh, no page scroll). The core becomes a size container and the reactor fits its height (100cqh minus 8rem, never below 13rem, at most 26rem wide). Smaller windows scroll the page and cap each log at 28rem.

Logs scroll inside their column. Captions pin to the bottom and fade in at the top (2.75rem mask); helpers and activity fade out at the bottom. A log follows its newest entry only if the reader was already there. The approval and the context legend share one slot under the reactor (min 6.25rem tall) so asking never shifts the reactor.

## Elevation & Depth

Flat. No surface casts a shadow and nothing sits on a card or a blurred panel. Depth is light: the ground bloom behind the reactor, and glow drawn on canvas around the core ring, the trace head and the helper satellites, scaled by voice level. The only CSS shadow is the expanding halo on a running helper badge.

### Shadow Vocabulary
- **Helper halo** (`box-shadow: 0 0 0 0 → 0 0 0 0.55rem rgb(239 226 255 / 0)` over 2s, ease-out, infinite): a running helper's number badge only.

### Named Rules
**The Live Light Rule.** Glow is emitted only by parts of the reactor that are measuring something live. Static UI never glows.

## Shapes

Straight hairlines and circles. Panels have no corners because there are no panels. Rounding is functional and small: 2px legend swatches, 3px tags and focus ring, pill only for the link status, full circles for helper badges, status dots and everything on the reactor. Icons are drawn on a 16px grid with 1.5px round-capped strokes (1.75px for status marks), inherit currentColor, and live in one inline SVG sprite.

## Components

### Header link pill
A 1px currentColor outline pill with a status dot and a condensed label. Connecting is faint ink, live is mint with the dot beating (opacity to 0.35 over 2.4s), offline is coral. Colour transitions over 0.4s.

### Header meta
A row of label-over-value pairs pushed right; values in muted ink, ellipsised at 24ch with the full value in a tooltip.

### The Reactor (signature)
A square canvas, at most 26rem, drawn each frame from live data; all radii are fractions of the half-width R so it scales cleanly.
- **Outer scale** (0.948 to 0.988R): 120 ticks, every tenth longer, accent at 30%. Turns slowly only while thinking.
- **Satellite orbit** (0.906R): dotted ring. Each helper is a numbered disc on one of eight fixed slots with a fading trail whose length grows with its tool calls; running discs are lilac light with a pulse ring, finished ones flash mint or coral and fade over 8s.
- **Context arc** (0.842R, 3% of R thick): one segment per category in series colours from twelve o'clock, thin gaps between, framed by two hairlines and a 20-tick scale.
- **Conversation trace** (0.585R, reaching 0.165R outward): 180 samples (6 s at 30 per second), each a radial stroke whose length is loudness and colour is the speaker (periwinkle for the user, lilac for Lila), fading with age. A glowing head line and a soft conic wedge sweep behind the newest sample.
- **Thinking arcs** (0.508R and 0.482R): two counter-rotating broken arcs, present only while thinking.
- **Core** (0.43R, swelling 3.5% with level): a glowing accent ring over a radial fill, an inner hairline and four quarter ticks; the state word and a two-line detail sit inside.
- Colour eases toward the state accent; level rises fast and falls slow.

### Caption entries
A condensed speaker label (lilac for Lila, periwinkle for the user) over plain text. The last two entries stay full size; older ones step down to muted. Lila's current reply carries a blinking lilac block caret while she thinks or speaks.

### Helper rows
A 1.75rem numbered disc (ground-coloured numerals) beside a description, a facts line led by a bold status word in the status colour, an optional "now using" line in faint ink, and a summary clamped to three lines. Running helpers halo; done turns the disc mint, failed coral, stopped faint ink.

### Tool rows
Hairline-topped rows: stroke icon in lilac, tool name, optional helper tag (condensed label in a 3px strong-hairline box, violet), a tabular timestamp, a one-line mono argument, and a status mark at the end: lilac spinner running, mint check, coral cross (and a rose-tinted argument), faint dash when ended. Newest on top.

### Approval
Replaces the context legend while asking: amber hairlines above and below, an amber question icon, the question in 1.12rem ink (two lines max) and the command in pale amber mono.

### Legend swatches
0.6rem squares, 2px corners, in series colours, followed by the category name and a faint tabular token count. The reserve swatch is a diagonal hatch with an outline.

### Readout strip
Eight label-over-value cells divided by hairlines, values in expanded tabular numerals with an optional small faint unit. Explanations live in tooltips.

### Motion
New entries rise 6px out of a 4px blur over 0.5s (ease-out, cubic-bezier(0.16, 1, 0.3, 1)); the state word re-enters from a 6px blur with tighter tracking over 0.55s. Under prefers-reduced-motion every CSS animation and transition stops and the reactor freezes its rotation, pulses and sweep while still drawing live values.

### Offline
What was last seen stays: side columns dim to 62%, all motion stops, running spinners hide, helper facts read "last seen", the reactor falls to a dim violet with no level, no sweep and faded satellites, and the core reads "Offline" with the reconnect hint.

## Do's and Don'ts

### Do:
- **Do** take every colour from the root tokens and route state through the single accent variable.
- **Do** divide space with 1px hairlines (rule) and the shared gutter.
- **Do** set labels in condensed, uppercase, 0.16em-tracked Saira and numerals in expanded tabular Saira.
- **Do** draw new icons on the 16px grid with 1.5px round strokes in currentColor, added to the sprite.
- **Do** stop motion that represents activity the moment the activity stops, offline included.
- **Do** keep long values to one line with an ellipsis and the full value in a tooltip.

### Don't:
- **Don't** put content on cards, glass or blurred panels, or give any surface a drop shadow.
- **Don't** use cyan or any non-lilac light for the reactor.
- **Don't** use amber, mint or coral for anything but question, done/live and failed/offline.
- **Don't** add a second type family; mono is for literal machine text only.
- **Don't** draw a progress bar or percentage for helpers; they report activity, not completion.
- **Don't** set an uppercase label above a heading as an eyebrow; labels name fields, sections and speakers.
