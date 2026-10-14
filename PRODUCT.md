# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python package (`src/lila`), run with uv. The HUD is a single static HTML file served by Lila's own process from the standard library (`--web`); no Node, no build step. The user considered a TypeScript/Bun rewrite and chose to keep Python.

## Users

The person whose computer Lila runs on: one user, talking out loud to their own assistant while they work. They also show Lila to other people in demos.

## Product Purpose

Lila is a personal voice assistant. You talk, a Claude agent works in a folder on your machine (files, commands, the web, clipboard, screen), and it answers out loud while the answer is still being written. It remembers things between conversations. The HUD is a read-only window onto what Lila is doing right now: whether she's listening, thinking or speaking, what she says, which tools and background helpers are running, and what the session has used.

## Positioning

A voice-first agent with real hands on your machine, not a chatbot: background helpers keep working while you keep talking, approvals are asked out loud, and everything she does is visible. The HUD shows Lila's actual state from the Claude Agent SDK and her own audio pipeline, never an invented animation of "AI thinking".

## Operating Context

- Usually a browser window beside the terminal, sometimes large; a second monitor if the user had one. Must work from a half-screen window up to full screen.
- Used in demos, so it has to look good and be accurate at the same time.
- Lila keeps running in the terminal; the HUD only shows, it never controls (no buttons that act on Lila).
- Speech in English and Dutch.

## Capabilities and Constraints

- Data available: voice state (listening, hearing you, thinking, speaking, waiting for a yes/no), mic and voice levels, live captions of what Lila writes, transcripts of what the user said, tool calls with their arguments and outcome, background helper tasks (description, tokens, tool uses, elapsed time, final summary), approval questions, context-window usage by category, per-session cost estimate, tokens, cache reads, web searches, reply latency, model, working folder.
- Cost is Claude Code's API-price estimate; with a subscription sign-in it is not what the user pays.
- Helpers report activity, not percent complete: no progress bars that pretend otherwise.
- Local only: served on 127.0.0.1, read-only.

## Brand Commitments

- Name is "lila", written lowercase in the terminal, painted magenta there.
- The HUD is "like Jarvis, but for Lila": a futuristic circle at its heart. Its light is lilac (Lila's own colour; "lila" means lilac), not Jarvis cyan. User-confirmed.
- Lila's voice: dry, kind-hearted, straightforward, plain words.

## Evidence on Hand

No logos, screenshots or brand assets exist yet. All data shown comes from the live session; demo data must be labelled as such and never ships in the page.

## Product Principles

1. Show what is true right now; never animate activity that isn't happening.
2. The voice comes first: the HUD must never demand attention away from the conversation.
3. Readable at a glance from across a desk, detailed up close.
4. Lila's, not a film prop: her colour, her words, her state.
