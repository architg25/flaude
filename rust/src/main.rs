//! flaude-hook: Native hook dispatcher for Claude Code events.
//!
//! Drop-in replacement for `python3 -m flaude.hooks.dispatcher`.
//! Reads JSON from stdin, updates session state files, appends to
//! activity log, evaluates rules. Produces identical output to the
//! Python version — the TUI reads these files.

use std::collections::HashMap;
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::process;

use chrono::{NaiveDateTime, Utc};
use regex::Regex;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

fn state_dir() -> PathBuf {
    PathBuf::from(env::var("FLAUDE_STATE_DIR").unwrap_or_else(|_| "/tmp/flaude".into()))
}

fn sessions_dir() -> PathBuf {
    state_dir().join("state")
}

fn activity_log_path() -> PathBuf {
    state_dir().join("logs").join("activity.log")
}

fn rules_path() -> PathBuf {
    let p = env::var("FLAUDE_RULES_PATH")
        .unwrap_or_else(|_| "~/.config/flaude/rules.yaml".into());
    expand_tilde(&p)
}

fn expand_tilde(path: &str) -> PathBuf {
    if let Some(rest) = path.strip_prefix("~/") {
        if let Ok(home) = env::var("HOME") {
            return PathBuf::from(home).join(rest);
        }
    }
    PathBuf::from(path)
}

fn utcnow() -> NaiveDateTime {
    Utc::now().naive_utc()
}

fn ensure_dirs() {
    let _ = fs::create_dir_all(sessions_dir());
    let _ = fs::create_dir_all(state_dir().join("logs"));
}

// ---------------------------------------------------------------------------
// Models — mirrors state/models.py
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum SessionStatus {
    New,
    Working,
    Idle,
    WaitingPermission,
    WaitingAnswer,
    Plan,
    Error,
    Ended,
}

impl Default for SessionStatus {
    fn default() -> Self {
        SessionStatus::Working
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LastTool {
    name: String,
    summary: String,
    at: NaiveDateTime,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SessionState {
    session_id: String,
    #[serde(default)]
    status: SessionStatus,
    #[serde(default)]
    cwd: String,
    #[serde(default = "default_permission_mode")]
    permission_mode: String,
    started_at: NaiveDateTime,
    #[serde(default)]
    last_event: String,
    last_event_at: NaiveDateTime,
    #[serde(default)]
    transcript_path: Option<String>,
    #[serde(default)]
    tool_stats: HashMap<String, u64>,
    #[serde(default)]
    last_tool: Option<LastTool>,
    #[serde(default)]
    last_prompt: Option<String>,
    #[serde(default)]
    pending_question: Option<serde_json::Value>,
    #[serde(default)]
    terminal: Option<String>,
    #[serde(default)]
    tty: Option<String>,
    #[serde(default)]
    turn_started_at: Option<NaiveDateTime>,
    #[serde(default)]
    last_turn_duration: f64,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    context_tokens: u64,
    #[serde(default)]
    error_count: u64,
    #[serde(default)]
    subagent_count: i64,
}

fn default_permission_mode() -> String {
    "default".into()
}

// ---------------------------------------------------------------------------
// State I/O — mirrors state/manager.py
// ---------------------------------------------------------------------------

fn session_path(session_id: &str) -> PathBuf {
    sessions_dir().join(format!("{session_id}.json"))
}

fn save_session(state: &SessionState) {
    let path = session_path(&state.session_id);
    let data = match serde_json::to_string_pretty(state) {
        Ok(d) => d,
        Err(_) => return,
    };
    atomic_write(&path, &data);
}

fn load_session(session_id: &str) -> Option<SessionState> {
    let path = session_path(session_id);
    let text = fs::read_to_string(&path).ok()?;
    serde_json::from_str(&text).ok()
}

fn delete_session(session_id: &str) {
    let _ = fs::remove_file(session_path(session_id));
}

fn atomic_write(path: &Path, data: &str) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let tmp = path.with_extension(format!(
        "{}.tmp",
        path.extension().unwrap_or_default().to_string_lossy()
    ));
    if fs::write(&tmp, data).is_ok() {
        let _ = fs::rename(&tmp, path);
    }
}

// ---------------------------------------------------------------------------
// Activity logging — mirrors dispatcher._log()
// ---------------------------------------------------------------------------

fn log_activity(session_id: &str, event: &str, detail: &str) {
    let ts = utcnow().format("%Y-%m-%dT%H:%M:%S");
    let sid = if session_id.len() >= 8 {
        &session_id[..8]
    } else if session_id.is_empty() {
        "????????"
    } else {
        session_id
    };
    let line = if detail.is_empty() {
        format!("{ts} [{sid}] {event}\n")
    } else {
        format!("{ts} [{sid}] {event} {detail}\n")
    };
    let path = activity_log_path();
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&path) {
        let _ = f.write_all(line.as_bytes());
    }
}

// ---------------------------------------------------------------------------
// Tool summarization — mirrors dispatcher._SUMMARIZERS
// ---------------------------------------------------------------------------

fn trunc(s: &str, n: usize) -> String {
    if s.len() > n {
        format!("{}...", &s[..n])
    } else {
        s.to_string()
    }
}

fn basename(path: &str) -> String {
    if path.is_empty() {
        return String::new();
    }
    Path::new(path)
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default()
}

fn summarize_tool(tool_name: &str, tool_input: &serde_json::Value) -> String {
    let get_str = |key: &str| -> String {
        tool_input
            .get(key)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    };
    match tool_name {
        "Bash" => trunc(&get_str("command"), 80),
        "Edit" | "Write" | "Read" => basename(&get_str("file_path")),
        "Grep" => trunc(&get_str("pattern"), 40),
        "Glob" => get_str("pattern"),
        "Task" => trunc(&get_str("prompt"), 60),
        "WebFetch" => trunc(&get_str("url"), 60),
        _ => tool_name.to_string(),
    }
}

// ---------------------------------------------------------------------------
// Terminal detection — mirrors dispatcher._detect_terminal_from_env()
// ---------------------------------------------------------------------------

fn detect_tty() -> Option<String> {
    // Walk up the process tree from our parent to find a process with a TTY.
    // The hook's fds are all piped (no controlling terminal), but the parent
    // process (Claude Code) runs on a real TTY.
    let mut pid = unsafe { libc::getppid() } as u32;
    for _ in 0..5 {
        if pid <= 1 {
            break;
        }
        let output = std::process::Command::new("ps")
            .args(["-p", &pid.to_string(), "-o", "tty=,ppid="])
            .output()
            .ok()?;
        let text = String::from_utf8_lossy(&output.stdout);
        let parts: Vec<&str> = text.trim().split_whitespace().collect();
        if parts.is_empty() {
            break;
        }
        let tty = parts[0];
        if !tty.is_empty() && tty != "??" {
            return Some(format!("/dev/{tty}"));
        }
        if parts.len() >= 2 {
            pid = match parts[1].parse() {
                Ok(p) => p,
                Err(_) => break,
            };
        } else {
            break;
        }
    }
    None
}

fn detect_terminal_from_env() -> Option<String> {
    if let Ok(term) = env::var("TERM_PROGRAM") {
        match term.as_str() {
            "iTerm.app" => return Some("iTerm2".into()),
            "ghostty" => return Some("Ghostty".into()),
            "Apple_Terminal" => return Some("Terminal".into()),
            "WarpTerminal" => return Some("Warp".into()),
            _ => {}
        }
    }
    if let Ok(emu) = env::var("TERMINAL_EMULATOR") {
        if emu.contains("JetBrains") {
            return Some("IntelliJ".into());
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Transcript token parsing — mirrors dispatcher._get_usage_from_transcript()
// ---------------------------------------------------------------------------

fn get_usage_from_transcript(transcript_path: Option<&str>) -> (u64, Option<String>) {
    let path_str = match transcript_path {
        Some(p) if !p.is_empty() => p,
        _ => return (0, None),
    };
    let path = Path::new(path_str);
    if !path.exists() {
        return (0, None);
    }

    let mut file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return (0, None),
    };

    let size = match file.metadata() {
        Ok(m) => m.len(),
        Err(_) => return (0, None),
    };

    // Read last 10KB
    let offset = if size > 10240 { size - 10240 } else { 0 };
    if file.seek(SeekFrom::Start(offset)).is_err() {
        return (0, None);
    }

    let mut buf = Vec::new();
    if file.read_to_end(&mut buf).is_err() {
        return (0, None);
    }

    let tail = String::from_utf8_lossy(&buf);

    // Discard partial first line when we seeked to mid-file
    let tail = if offset > 0 {
        match tail.find('\n') {
            Some(idx) => &tail[idx + 1..],
            None => &tail,
        }
    } else {
        &tail
    };

    // Search backwards for the latest usage
    for line in tail.trim().lines().rev() {
        if let Ok(entry) = serde_json::from_str::<serde_json::Value>(line) {
            if let Some(msg) = entry.get("message") {
                if let Some(usage) = msg.get("usage") {
                    let cache_read = usage
                        .get("cache_read_input_tokens")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    let input = usage
                        .get("input_tokens")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    let cache_creation = usage
                        .get("cache_creation_input_tokens")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    let tokens = cache_read + input + cache_creation;
                    let model = msg
                        .get("model")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string());
                    return (tokens, model);
                }
            }
        }
    }

    (0, None)
}

// ---------------------------------------------------------------------------
// Permission output — mirrors dispatcher._emit_decision()
// ---------------------------------------------------------------------------

fn emit_decision(decision: &str) {
    let output = serde_json::json!({
        "hookSpecificOutput": {
            "permissionDecision": decision
        }
    });
    let _ = serde_json::to_writer(io::stdout(), &output);
    process::exit(0);
}

// ---------------------------------------------------------------------------
// Rules engine — mirrors rules/engine.py
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct RulesFile {
    #[serde(default)]
    rules: Vec<Rule>,
    #[allow(dead_code)]
    #[serde(default)]
    defaults: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct Rule {
    #[serde(default)]
    name: Option<String>,
    action: String,
    #[serde(default)]
    tools: Vec<String>,
    #[serde(default, rename = "match")]
    match_spec: Option<HashMap<String, String>>,
    #[allow(dead_code)]
    #[serde(default)]
    reason: Option<String>,
    #[allow(dead_code)]
    #[serde(default)]
    timeout: Option<u64>,
}

struct RuleResult {
    action: String,
    rule_name: Option<String>,
}

fn load_rules() -> Vec<Rule> {
    let path = rules_path();
    if !path.exists() {
        return Vec::new();
    }
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return Vec::new(),
    };
    let file: RulesFile = match serde_yaml::from_str(&text) {
        Ok(f) => f,
        Err(_) => return Vec::new(),
    };
    file.rules
}

fn evaluate_rules(
    rules: &[Rule],
    tool_name: &str,
    tool_input: &serde_json::Value,
    cwd: &str,
) -> RuleResult {
    for rule in rules {
        if !rule.tools.contains(&tool_name.to_string()) {
            continue;
        }
        if !input_matches(rule, tool_input, cwd) {
            continue;
        }
        return RuleResult {
            action: rule.action.clone(),
            rule_name: rule.name.clone(),
        };
    }
    RuleResult {
        action: "no_match".into(),
        rule_name: None,
    }
}

fn input_matches(rule: &Rule, tool_input: &serde_json::Value, cwd: &str) -> bool {
    let match_spec = match &rule.match_spec {
        Some(m) => m,
        None => return true,
    };
    for (field, pattern) in match_spec {
        let value = tool_input
            .get(field)
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let resolved = pattern.replace("$CWD", &regex::escape(cwd));
        match Regex::new(&resolved) {
            Ok(re) => {
                if !re.is_match(value) {
                    return false;
                }
            }
            Err(_) => return false,
        }
    }
    true
}

// ---------------------------------------------------------------------------
// Session loading helper — mirrors dispatcher._load_or_create()
// ---------------------------------------------------------------------------

fn load_or_create(event: &serde_json::Value) -> SessionState {
    let session_id = event
        .get("session_id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let mut state = load_session(&session_id).unwrap_or_else(|| {
        let now = utcnow();
        SessionState {
            session_id: session_id.clone(),
            status: SessionStatus::Working,
            cwd: get_str(event, "cwd"),
            permission_mode: default_permission_mode(),
            started_at: now,
            last_event: String::new(),
            last_event_at: now,
            transcript_path: get_opt_str(event, "transcript_path"),
            tool_stats: HashMap::new(),
            last_tool: None,
            last_prompt: None,
            pending_question: None,
            terminal: detect_terminal_from_env(),
            tty: detect_tty(),
            turn_started_at: None,
            last_turn_duration: 0.0,
            model: None,
            context_tokens: 0,
            error_count: 0,
            subagent_count: 0,
        }
    });

    // Backfill missing fields from event data
    if state.transcript_path.is_none() {
        state.transcript_path = get_opt_str(event, "transcript_path");
    }
    if let Some(cwd) = get_opt_str(event, "cwd") {
        state.cwd = cwd;
    }
    if state.terminal.is_none() {
        state.terminal = detect_terminal_from_env();
    }
    if state.tty.is_none() {
        state.tty = detect_tty();
    }
    if let Some(pm) = get_opt_str(event, "permission_mode") {
        state.permission_mode = pm;
    }

    state
}

// ---------------------------------------------------------------------------
// JSON helpers
// ---------------------------------------------------------------------------

fn get_str(v: &serde_json::Value, key: &str) -> String {
    v.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

fn get_opt_str(v: &serde_json::Value, key: &str) -> Option<String> {
    v.get(key)
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

// ---------------------------------------------------------------------------
// Event handlers — mirrors dispatcher._handle_*()
// ---------------------------------------------------------------------------

fn handle_session_start(event: &serde_json::Value) {
    let session_id = get_str(event, "session_id");
    let now = utcnow();
    let state = SessionState {
        session_id: session_id.clone(),
        status: SessionStatus::New,
        cwd: get_str(event, "cwd"),
        permission_mode: get_str(event, "permission_mode"),
        started_at: now,
        last_event: "SessionStart".into(),
        last_event_at: now,
        transcript_path: get_opt_str(event, "transcript_path"),
        tool_stats: HashMap::new(),
        last_tool: None,
        last_prompt: None,
        pending_question: None,
        terminal: detect_terminal_from_env(),
        tty: detect_tty(),
        turn_started_at: None,
        last_turn_duration: 0.0,
        model: None,
        context_tokens: 0,
        error_count: 0,
        subagent_count: 0,
    };
    save_session(&state);
    log_activity(&session_id, "SessionStart", "");
}

fn handle_pre_tool_use(event: &serde_json::Value) {
    let tool_name = get_str(event, "tool_name");
    let tool_input = event
        .get("tool_input")
        .cloned()
        .unwrap_or(serde_json::Value::Object(Default::default()));
    let now = utcnow();

    let mut state = load_or_create(event);

    let summary = summarize_tool(&tool_name, &tool_input);
    state.last_tool = Some(LastTool {
        name: tool_name.clone(),
        summary: summary.clone(),
        at: now,
    });
    *state.tool_stats.entry(tool_name.clone()).or_insert(0) += 1;
    state.status = SessionStatus::Working;
    state.last_event = "PreToolUse".into();
    state.last_event_at = now;

    if tool_name == "ExitPlanMode" {
        state.pending_question = Some(tool_input.clone());
        state.status = SessionStatus::Plan;
    } else if tool_name == "AskUserQuestion" {
        state.pending_question = Some(tool_input.clone());
        state.status = SessionStatus::WaitingAnswer;
    } else {
        state.pending_question = None;
    }

    save_session(&state);
    log_activity(
        &state.session_id,
        "PreToolUse",
        &format!("{tool_name} \"{summary}\""),
    );

    // Evaluate rules — only deny is actionable
    let rules = load_rules();
    let result = evaluate_rules(&rules, &tool_name, &tool_input, &state.cwd);
    if result.action == "deny" {
        let rule_name = result.rule_name.as_deref().unwrap_or("unnamed");
        log_activity(
            &state.session_id,
            "DENY",
            &format!("{tool_name} blocked by rule: {rule_name}"),
        );
        emit_decision("deny");
    }
}

fn handle_post_tool_use(event: &serde_json::Value) {
    let tool_name = get_str(event, "tool_name");
    let mut state = load_or_create(event);
    state.last_event = "PostToolUse".into();
    state.last_event_at = utcnow();
    state.pending_question = None;
    if matches!(
        state.status,
        SessionStatus::WaitingAnswer | SessionStatus::Plan | SessionStatus::WaitingPermission
    ) {
        state.status = SessionStatus::Working;
    }

    save_session(&state);
    log_activity(&state.session_id, "PostToolUse", &tool_name);
}

fn handle_stop(event: &serde_json::Value) {
    let mut state = load_or_create(event);
    state.status = SessionStatus::Idle;
    state.pending_question = None;

    if let Some(turn_start) = state.turn_started_at {
        let now = utcnow();
        state.last_turn_duration = (now - turn_start).num_milliseconds() as f64 / 1000.0;
    }
    state.turn_started_at = None;
    state.last_event = "Stop".into();
    state.last_event_at = utcnow();

    let (tokens, model) = get_usage_from_transcript(state.transcript_path.as_deref());
    state.context_tokens = tokens;
    if let Some(m) = model {
        state.model = Some(m);
    }

    save_session(&state);
    log_activity(&state.session_id, "Stop", "idle");
}

fn handle_notification(event: &serde_json::Value) {
    let message = get_str(event, "message").to_lowercase();
    let mut state = load_or_create(event);

    if message.contains("permission") {
        state.status = SessionStatus::WaitingPermission;
    } else if message.contains("needs your attention") && state.status != SessionStatus::Plan {
        state.status = SessionStatus::WaitingAnswer;
    }

    state.last_event = "Notification".into();
    state.last_event_at = utcnow();
    save_session(&state);
    log_activity(&state.session_id, "Notification", &trunc(&message, 60));
}

fn handle_user_prompt_submit(event: &serde_json::Value) {
    let mut state = load_or_create(event);
    let prompt = get_str(event, "user_prompt");
    state.status = SessionStatus::Working;
    state.turn_started_at = Some(utcnow());
    if !prompt.is_empty() {
        let truncated = if prompt.len() > 200 {
            prompt[..200].to_string()
        } else {
            prompt.clone()
        };
        state.last_prompt = Some(truncated);
    }
    state.pending_question = None;
    state.last_event = "UserPromptSubmit".into();
    state.last_event_at = utcnow();

    save_session(&state);
    let detail = if prompt.is_empty() {
        String::new()
    } else {
        trunc(&prompt, 80)
    };
    log_activity(&state.session_id, "UserPrompt", &detail);
}

fn handle_subagent_stop(event: &serde_json::Value) {
    let mut state = load_or_create(event);
    state.subagent_count = (state.subagent_count - 1).max(0);
    state.last_event = "SubagentStop".into();
    state.last_event_at = utcnow();
    save_session(&state);
    log_activity(&state.session_id, "SubagentStop", "");
}

fn handle_pre_compact(event: &serde_json::Value) {
    let session_id = get_str(event, "session_id");
    log_activity(&session_id, "PreCompact", "");
}

fn handle_session_end(event: &serde_json::Value) {
    let session_id = get_str(event, "session_id");
    delete_session(&session_id);
    log_activity(&session_id, "SessionEnd", "");
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

fn main() {
    // A hook crash must NEVER block Claude Code. Catch everything at top level.
    if let Err(e) = run() {
        log_activity("", "ERROR", &e.to_string());
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    ensure_dirs();

    let event: serde_json::Value = serde_json::from_reader(io::stdin())?;
    let event_name = event
        .get("hook_event_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    match event_name {
        "SessionStart" => handle_session_start(&event),
        "PreToolUse" => handle_pre_tool_use(&event),
        "PostToolUse" => handle_post_tool_use(&event),
        "Stop" => handle_stop(&event),
        "Notification" => handle_notification(&event),
        "UserPromptSubmit" => handle_user_prompt_submit(&event),
        "SubagentStop" => handle_subagent_stop(&event),
        "PreCompact" => handle_pre_compact(&event),
        "SessionEnd" => handle_session_end(&event),
        _ => {} // Unknown events silently ignored
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    fn make_event(name: &str, session_id: &str) -> serde_json::Value {
        serde_json::json!({
            "hook_event_name": name,
            "session_id": session_id,
            "cwd": "/tmp/test-project",
            "permission_mode": "default",
        })
    }

    #[test]
    fn test_trunc_short() {
        assert_eq!(trunc("hello", 10), "hello");
    }

    #[test]
    fn test_trunc_long() {
        assert_eq!(trunc("hello world", 5), "hello...");
    }

    #[test]
    fn test_basename_empty() {
        assert_eq!(basename(""), "");
    }

    #[test]
    fn test_basename_path() {
        assert_eq!(basename("/foo/bar/baz.txt"), "baz.txt");
    }

    #[test]
    fn test_summarize_bash() {
        let input = serde_json::json!({"command": "ls -la"});
        assert_eq!(summarize_tool("Bash", &input), "ls -la");
    }

    #[test]
    fn test_summarize_edit() {
        let input = serde_json::json!({"file_path": "/src/main.rs"});
        assert_eq!(summarize_tool("Edit", &input), "main.rs");
    }

    #[test]
    fn test_summarize_unknown() {
        let input = serde_json::json!({});
        assert_eq!(summarize_tool("CustomTool", &input), "CustomTool");
    }

    #[test]
    fn test_detect_terminal_iterm() {
        env::set_var("TERM_PROGRAM", "iTerm.app");
        assert_eq!(detect_terminal_from_env(), Some("iTerm2".into()));
        env::remove_var("TERM_PROGRAM");
    }

    #[test]
    fn test_session_status_serialization() {
        let json = serde_json::to_string(&SessionStatus::WaitingPermission).unwrap();
        assert_eq!(json, "\"waiting_permission\"");
    }

    #[test]
    fn test_session_status_deserialization() {
        let status: SessionStatus = serde_json::from_str("\"working\"").unwrap();
        assert_eq!(status, SessionStatus::Working);
    }

    #[test]
    fn test_session_state_roundtrip() {
        let now = utcnow();
        let state = SessionState {
            session_id: "test-123".into(),
            status: SessionStatus::Working,
            cwd: "/tmp/test".into(),
            permission_mode: "default".into(),
            started_at: now,
            last_event: "SessionStart".into(),
            last_event_at: now,
            transcript_path: None,
            tool_stats: HashMap::new(),
            last_tool: None,
            last_prompt: None,
            pending_question: None,
            terminal: Some("iTerm2".into()),
            tty: Some("/dev/ttys006".into()),
            turn_started_at: None,
            last_turn_duration: 0.0,
            model: None,
            context_tokens: 0,
            error_count: 0,
            subagent_count: 0,
        };
        let json = serde_json::to_string_pretty(&state).unwrap();
        let parsed: SessionState = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.session_id, "test-123");
        assert_eq!(parsed.status, SessionStatus::Working);
        assert_eq!(parsed.terminal, Some("iTerm2".into()));
    }

    #[test]
    fn test_rules_evaluate_deny() {
        let rules = vec![Rule {
            name: Some("block-rm".into()),
            action: "deny".into(),
            tools: vec!["Bash".into()],
            match_spec: Some(HashMap::from([(
                "command".into(),
                "rm\\s+-rf".into(),
            )])),
            reason: Some("dangerous".into()),
            timeout: None,
        }];

        let input = serde_json::json!({"command": "rm -rf /"});
        let result = evaluate_rules(&rules, "Bash", &input, "/tmp");
        assert_eq!(result.action, "deny");
        assert_eq!(result.rule_name, Some("block-rm".into()));
    }

    #[test]
    fn test_rules_evaluate_no_match() {
        let rules = vec![Rule {
            name: Some("block-rm".into()),
            action: "deny".into(),
            tools: vec!["Bash".into()],
            match_spec: Some(HashMap::from([(
                "command".into(),
                "rm\\s+-rf".into(),
            )])),
            reason: None,
            timeout: None,
        }];

        let input = serde_json::json!({"command": "ls -la"});
        let result = evaluate_rules(&rules, "Bash", &input, "/tmp");
        assert_eq!(result.action, "no_match");
    }

    #[test]
    fn test_rules_wrong_tool() {
        let rules = vec![Rule {
            name: None,
            action: "deny".into(),
            tools: vec!["Bash".into()],
            match_spec: None,
            reason: None,
            timeout: None,
        }];

        let input = serde_json::json!({});
        let result = evaluate_rules(&rules, "Read", &input, "/tmp");
        assert_eq!(result.action, "no_match");
    }

    #[test]
    fn test_transcript_parsing() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("transcript.jsonl");
        let mut f = File::create(&path).unwrap();

        writeln!(
            f,
            r#"{{"message": {{"role": "assistant", "usage": {{"input_tokens": 100, "cache_read_input_tokens": 500, "cache_creation_input_tokens": 50}}, "model": "claude-opus-4-6"}}}}"#
        )
        .unwrap();

        let (tokens, model) = get_usage_from_transcript(Some(path.to_str().unwrap()));
        assert_eq!(tokens, 650);
        assert_eq!(model, Some("claude-opus-4-6".into()));
    }

    #[test]
    fn test_transcript_parsing_empty() {
        let (tokens, model) = get_usage_from_transcript(None);
        assert_eq!(tokens, 0);
        assert_eq!(model, None);
    }

    #[test]
    fn test_cwd_replacement_in_rules() {
        let rules = vec![Rule {
            name: None,
            action: "deny".into(),
            tools: vec!["Bash".into()],
            match_spec: Some(HashMap::from([(
                "command".into(),
                "cd $CWD".into(),
            )])),
            reason: None,
            timeout: None,
        }];

        let input = serde_json::json!({"command": "cd /tmp/my-project"});
        let result = evaluate_rules(&rules, "Bash", &input, "/tmp/my-project");
        assert_eq!(result.action, "deny");
    }
}
