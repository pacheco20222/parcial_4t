---
name: Alerta Pluvial Mérida
description: Early-warning flood console built as a civil-protection alert ladder; the worst current status owns the screen.
colors:
  ground: "#f7f7f4"
  ink: "#101820"
  card: "#ffffff"
  line: "#d9d9d2"
  muted: "#565f6a"
  normal: "#2e7d32"
  watch: "#f2b705"
  alert: "#d6402a"
  alert-text: "#b42e1c"
  nodata: "#6b7280"
  nodata-hatch-light: "#eceef0"
  nodata-hatch-dark: "#d5d8dc"
  shell-line: "#283440"
  shell-muted: "#55616b"
  ink-hover: "#2d3a46"
typography:
  display:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "28px"
    fontWeight: 800
    lineHeight: "32px"
    letterSpacing: "0.04em"
  kpi-numeral:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: "48px"
  headline:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.1
  title:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: "24px"
    letterSpacing: "0.04em"
  body:
    fontFamily: "Barlow, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Barlow, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: "16px"
rounded:
  none: "0px"
  marker: "50%"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
components:
  button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
    rounded: "{rounded.none}"
    padding: "9px 15px"
    height: "44px"
  button-hover:
    backgroundColor: "{colors.ink-hover}"
  field:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "9px 10px"
    height: "44px"
  kpi-tile:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "8px 10px 12px"
  signal-field-alert:
    backgroundColor: "{colors.alert}"
    textColor: "{colors.card}"
  signal-field-watch:
    backgroundColor: "{colors.watch}"
    textColor: "{colors.ink}"
  signal-field-normal:
    backgroundColor: "{colors.normal}"
    textColor: "{colors.card}"
  status-band:
    typography: "{typography.display}"
    padding: "8px 24px"
    height: "56px"
  ops-header:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
    height: "56px"
    padding: "0 24px"
---

# Design System: Alerta Pluvial Mérida

## Overview

**Creative North Star: "The Semáforo"**

The console is a civil-protection alert ladder, not a card grid. The city's worst current point status fills a full-width signal band; points sit on rungs of that ladder in solid signal fields. Everything else is a quiet bulletin: off-white ground, ink type, hairlines, square corners. Colour is rationed so that status is the only loud thing on screen.

Density is control-room: desktop gets a viewport-locked three-column panel for long night sessions, and the same content stacks for a 375 px phone. The ground is a bulletin white, the shell is ink. No official seals or Ayuntamiento colours are imitated.

**Key Characteristics:**
- Worst status owns the screen (band), points live on a ladder of solid fields.
- Status is always colour plus label plus drawn glyph, never colour alone.
- Condensed uppercase headings, huge tabular numerals, plain Barlow body.
- Square corners, 1px hairlines, flat surfaces.
- Neutral ink for everything that is not point status.

## Colors

A bulletin-white and ink base with four reserved signal colours.

### Primary
- **Ink** (`colors.ink`): header, text, buttons, focus rings, selected marker outline, work-order priority bars and step markers.

### Secondary
- **Signal Green** (`colors.normal`): Normal point status only.
- **Signal Amber** (`colors.watch`): Watch status only; also the focus ring on ink/red/green fields, text selection, the active-nav underline and the wordmark diamond in the shell.
- **Signal Red** (`colors.alert`): Alert status only, plus the KPI "bad" top rule and an expired SLA bar. Use `alert-text` for red text on light grounds (contrast).
- **Slate Hatch** (`colors.nodata`, with the two hatch greys): Sin datos. Rendered as a 135-degree 6px hatch, never a flat fill, never 0.

### Neutral
- **Bulletin White** (`colors.ground`): page ground and hover wash.
- **Card White** (`colors.card`): KPI tiles, feeds, fields, work orders.
- **Hairline** (`colors.line`): 1px borders and dividers.
- **Muted Slate** (`colors.muted`): secondary text, field borders.
- **Shell Line / Shell Muted**: borders and hover inside the ink header.

### Named Rules
**The Status-Only Rule.** Green, amber, red and hatch mean point status and nothing else. Work-order priority and step indicators, buttons, and chrome stay in neutral ink.
**The Never-Colour-Alone Rule.** Every status shows a colour, a text label (Alerta, Vigilancia, Normal, Sin datos) and a drawn glyph (triangle, diamond, circle, hatched square), also on map markers.

## Typography

**Display / Heading Font:** Barlow Condensed (600/700/800, bundled via fontsource)
**Body Font:** Barlow (400/500/600, bundled)

**Character:** Signage condensed over a humane grotesque body. Tabular numerals are on globally.

### Hierarchy
- **Display** (800, 28px/32px, uppercase, 0.04em; 24px at <=767px): status-band word.
- **KPI numeral** (700, 40px/48px; clamp(26px, 2.3vw, 40px) in the desktop panel): the five KPI values.
- **Headline** (700, 22px; h1 32px, h3 20px base): page and column headings, rung headings 24px.
- **Title** (700, 18px/24px, uppercase, 0.04em): panel section headings.
- **Body** (400, 16px/1.45): default; compact rows use 14px, work-order folio is Condensed 700 16px.
- **Label** (500-600, 12-13px, sentence case, muted): KPI captions, timestamps, details.

### Named Rules
**The Condensed-Is-Signage Rule.** Barlow Condensed is for headings, folios and numerals; running text and form controls are Barlow.

## Layout

Square-cornered grid on a 4/8 rhythm (8, 12, 16, 24 px most used). The shell is an ink header (56 px) over the status band (min 56 px), with a "datos simulados" footer.

- **>=1200 px:** viewport-locked three-column panel, height = 100dvh minus header, band and footer. Columns: ladder 240-280 px | KPI row of 5 over the Leaflet map | alerts feed over work orders 300-360 px. Feeds scroll internally; the page does not.
- **768-1199 px:** two columns (ladder 240 px | KPIs in 3 columns over map), activity row beneath in two columns; header nav collapses to a menu button.
- **<=767 px:** single stack in order: ladder, KPIs (2 columns), alerts, work orders, map. Touch targets min 44 px.
- Work-order board: 4 columns, 2 at <=1100 px, a tabbed single column at <=640 px.
- Ladder rungs flex by weight (Alert/Normal 3, Watch/NoData 2) so the worst rung is tallest.

## Elevation & Depth

Flat. No shadows exist in the build. Depth comes from hairline borders, the 4px ink top rule on KPI tiles, and solid colour fields. Focus is a 2px ink outline, offset 3px (amber on dark or coloured fields).

### Named Rules
**The Flat-Hairline Rule.** Separate with 1px `line` borders or the 4px KPI top rule, never shadows.

## Shapes

Square corners everywhere (form controls reset to 0 radius). The only curves are the Normal map glyph and the live-connection dot, which are circles because the circle is the Normal status glyph. Status glyphs: triangle (Alerta), rotated diamond (Vigilancia), circle (Normal), hatched square (Sin datos).

## Components

### Buttons
Solid ink, white 600 text, 1px ink border, 0 radius, min-height 44px, padding 9px 15px. Hover lifts to a lighter ink; disabled is 65% opacity with a wait cursor. In ink/dark shells, secondary buttons are transparent with a shell-muted border. Status tabs use a pressed state of ink fill.

### Fields
White, 1px muted border, 0 radius, min-height 44px; focus-visible shows the ink outline.

### Status band
Full width, min 56px, worst-status colour fill with a 180 ms background crossfade; shows glyph and label, a plain-language sentence, and an outlined "En vivo" connection chip (filled circle when connected, hollow square otherwise).

### Alert ladder
Four stacked signal fields (Alerta, Vigilancia, Normal, Sin datos), each with a rung heading and point rows separated by half-opacity hairlines. A changed point FLIP-animates between rungs in 180 ms with a short highlight overlay.

### KPI tile
White, 1px hairline, 4px ink top rule (red for a bad value), muted caption, tabular Condensed numeral. Five across at desktop.

### Alert and work-order rows
Alert rows: 32px status-coloured glyph square, bold title, muted detail and time. Work-order rows: Condensed folio, SLA text, and neutral-ink indicators.

### Work-order indicators
Priority is four ascending-fill bars (1px-wide steps in ink, remaining bars in hairline) plus a label. Step is a bordered square numeral 1-4 plus a label (Cancelled shows a dash). Both are ink on neutral, never status colours. SLA is an 8px ink progress bar that turns red when expired.

### Map markers
20px glyph shapes matching the status glyphs on a white ink-bordered tile; selected adds a 3px ink outline.

## Do's and Don'ts

### Do:
- **Do** pair every status with colour, label and drawn glyph.
- **Do** keep priority, step and chrome in neutral ink.
- **Do** keep corners square, surfaces flat, borders 1px.
- **Do** respect `prefers-reduced-motion`: a global rule removes animations and transitions, and the FLIP helper returns early.
- **Do** keep motion at 180 ms with `cubic-bezier(0.16, 1, 0.3, 1)`, only for status changes (band crossfade, rung FLIP).
- **Do** size touch targets to at least 44 px.
- **Do** write styles in component stylesheets or classes: CSP forbids inline `style` attributes, and component styles are delivered with a per-request nonce (`ngCspNonce`, `style-src 'self' 'nonce-...'`).
- **Do** bundle fonts locally; no external CDNs.

### Don't:
- **Don't** use green, amber, red or hatch for anything but point status (or the alert-red bad-KPI rule and expired SLA).
- **Don't** show Sin datos as 0 or a flat colour.
- **Don't** add shadows, rounded corners, gradients or glassy surfaces.
- **Don't** set `style="..."` or `[style]` bindings in templates.
- **Don't** imitate official Ayuntamiento seals, logos or colours.
