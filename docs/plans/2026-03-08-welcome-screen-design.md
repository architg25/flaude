# Welcome Screen Design

## Problem

When no sessions exist, flaude shows an empty dashboard with 4 panels full of placeholder text. It looks broken and the tips are crammed into a table cell.

## Design

Replace the entire dashboard layout with a full-screen welcome widget when no sessions are active. Footer bar remains visible.

### Layout

```
        __ _                 _
       / _| | __ _ _   _  __| | ___
      | |_| |/ _` | | | |/ _` |/ _ \
      |  _| | (_| | |_| | (_| |  __/
      |_| |_|\__,_|\__,_|\__,_|\___|
                                 v0.15.18

         n  start a new session
         L  loop manager
         S  settings

      existing sessions appear automatically
      run flaude init if hooks not set up
```

- ASCII art in bold/bright color (theme-aware)
- Version dim, right-aligned under art
- Action keys highlighted (bold/accent), descriptions normal
- Bottom tips in dim italic
- Vertically and horizontally centered

### Behavior

- First session appears → welcome hides, dashboard shows
- All sessions gone → welcome comes back
- All keybindings remain active throughout

### Implementation

- New `WelcomeScreen` widget in `src/flaude/tui/widgets/`
- App `compose` yields both welcome and main split; visibility toggled
- `refresh_sessions` / watcher toggles based on session count
- Remove empty-state row hack from `SessionTable`
