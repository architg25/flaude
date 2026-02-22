# Rust Hook Dispatcher

## Why

Claude Code invokes the hook dispatcher on every event — tool calls, session start/end, prompts, notifications. A busy session doing search-and-edit work fires dozens of events per minute. Each invocation is a fresh process: start up, parse JSON from stdin, update state, exit.

With the Python dispatcher, each invocation pays for:

1. Python interpreter startup (~25-30ms)
2. Module imports — json, os, pathlib, pydantic, yaml (~20-50ms first run, ~5ms cached)
3. Actual work — parse JSON, read/write state file, append log (~2ms)

The actual work is ~2ms. The other ~248ms is overhead. A native binary eliminates it.

## Performance

Measured on Apple Silicon (M-series Mac), 5 runs each, using `/usr/bin/time -p` on a SessionStart event:

| Dispatcher | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Avg    |
| ---------- | ----- | ----- | ----- | ----- | ----- | ------ |
| Python     | 280ms | 220ms | 220ms | 200ms | 310ms | ~246ms |
| Rust       | 30ms  | 10ms  | 10ms  | 10ms  | 10ms  | ~14ms  |

**~18x faster per invocation.**

The first Rust invocation is slightly slower (30ms) due to cold disk cache. Subsequent runs settle at ~10ms.

## Impact

At 30 tool calls per minute (a typical busy session), each call fires PreToolUse and PostToolUse — 60 hook invocations per minute.

| Dispatcher | Per invocation | Per minute (60 calls) | Per hour    |
| ---------- | -------------- | --------------------- | ----------- |
| Python     | ~246ms         | ~14.8s                | ~14.7 min   |
| Rust       | ~14ms          | ~0.8s                 | ~0.8 min    |
| **Saved**  | **~232ms**     | **~14s**              | **~14 min** |

The Python dispatcher adds ~15 seconds of cumulative latency per minute to Claude Code's pipeline. The Rust binary reduces this to under 1 second.

This matters because Claude Code invokes hooks synchronously — the session waits for the hook to return before proceeding to the next tool call.

## What changed

The Rust binary is a direct port of the Python dispatcher. Same input, same output, same file format. The TUI doesn't know or care which wrote the state files.

| Component ported     | Python source         | Rust location      |
| -------------------- | --------------------- | ------------------ |
| Event routing        | `hooks/dispatcher.py` | `rust/src/main.rs` |
| Session state models | `state/models.py`     | `rust/src/main.rs` |
| State file I/O       | `state/manager.py`    | `rust/src/main.rs` |
| Rules engine         | `rules/engine.py`     | `rust/src/main.rs` |
| Tool summarization   | `hooks/dispatcher.py` | `rust/src/main.rs` |
| Transcript parsing   | `hooks/dispatcher.py` | `rust/src/main.rs` |
| Terminal detection   | `hooks/dispatcher.py` | `rust/src/main.rs` |

The Python dispatcher is kept as a fallback for environments without a Rust toolchain.

## Binary size

The release binary with LTO and symbol stripping is ~1.7MB.

## Contract verification

A contract test pipes the same events through both dispatchers and compares output. All 19 state fields match (timestamps excluded since they differ by milliseconds between runs). The Rust binary also has 17 unit tests covering models, rules, transcript parsing, and tool summarization.
