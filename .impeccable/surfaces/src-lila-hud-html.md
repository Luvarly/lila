---
version: 1
slug: "src-lila-hud-html"
primary_target: "src/lila/hud.html"
related_targets: []
---

## Scope

The Lila HUD (`src/lila/hud.html`), opened by `lila --web`. Mode: Operate (a live, read-only status display), also shown in demos. One screen, responsive from phone width to full-screen.

## Audience and job

The user, mid-conversation with Lila, glancing over to see what she is doing; and people watching a demo. Job: know her state instantly, follow what she says and does, see what is running in the background and what the session has used.

## Direction contract

THESIS: The reactor is the conversation itself. A lilac circle whose rings are live instruments (a 4-second circular trace of who spoke, the context window as a segmented arc, background helpers as satellites) refuses the category default of a decorative spinning orb beside a stats dashboard.

OWN-WORLD: Violet-black ground (#0a0612) lit by lilac light (#c9a7ff to #efe2ff); periwinkle (#8fb4ff) is the user's voice, amber (#ffb84d) is a question waiting for a yes, mint for done, coral for failed. Saira across widths (condensed tracked labels, expanded numerals, normal-width captions); system mono only for commands and paths. Hairline lilac rules, fine tick scales, authored 1.5px stroke icons. No cards, no glass.

STORY: The visitor sees whether Lila is listening, thinking or speaking before reading a word, reads her words as captions, sees each tool and helper as it happens, and checks what the session has used.

FIRST VIEWPORT: Desktop: header strip (lowercase lila wordmark, live status, model, folder, uptime). Centre column holds the reactor at about 70% of viewport height with the state word in its core and the context legend beneath; left column captions; right column helpers then activity; a readout strip along the bottom. Approval appears under the reactor in amber. Narrow: reactor first, then captions, helpers, activity, readouts.

FORM: Pinned by the user ("a futuristic circle kind of like Jarvis, but for Lila", lilac light). Signature move: the conversation-trace ring. seed: none (direction pinned by the user)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Memorable moment

Talking to her and watching your voice (periwinkle) and hers (lilac) trace around the circle, while helper satellites pulse on the outer ring.

## Unresolved

Controls (interrupt, stop a helper, approve by click) are deliberately out of scope for now.
