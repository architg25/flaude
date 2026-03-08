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
// Git info — mirrors git.py get_git_info()
// ---------------------------------------------------------------------------

/// Return (repo_root, branch, is_worktree) for a directory.
///
/// Uses a single `git rev-parse` call.  Returns (None, None, false)
/// if *cwd* is not inside a git repo or on any error.
fn get_git_info(cwd: &str) -> (Option<String>, Option<String>, bool) {
    if cwd.is_empty() {
        return (None, None, false);
    }
    let output = match std::process::Command::new("git")
        .args([
            "-C",
            cwd,
            "rev-parse",
            "--show-toplevel",
            "--git-common-dir",
            "--abbrev-ref",
            "HEAD",
        ])
        .output()
    {
        Ok(o) if o.status.success() => o,
        _ => return (None, None, false),
    };
    let stdout = String::from_utf8_lossy(&output.stdout);
    let lines: Vec<&str> = stdout.trim().lines().collect();
    if lines.len() < 3 {
        return (None, None, false);
    }

    let toplevel = lines[0];
    let git_common_dir = lines[1];
    let branch_raw = lines[2];

    // Resolve git_common_dir to absolute path
    let common_abs = {
        let p = PathBuf::from(git_common_dir);
        if p.is_absolute() {
            p
        } else {
            PathBuf::from(toplevel).join(git_common_dir)
        }
    };
    // Canonicalize to resolve ".." and symlinks; fall back to the joined path
    let common_abs = fs::canonicalize(&common_abs).unwrap_or(common_abs);

    // Canonical repo root = parent of the shared .git directory
    let repo_root = common_abs
        .parent()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_else(|| toplevel.to_string());
    let is_worktree = repo_root != toplevel;

    let branch = if branch_raw == "HEAD" {
        None
    } else {
        Some(branch_raw.to_string())
    };

    (Some(repo_root), branch, is_worktree)
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
struct LoopInfo {
    task_id: String,
    cron_expr: String,
    human_schedule: String,
    prompt: String,
    recurring: bool,
    created_at: String,
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
    #[serde(default)]
    team_name: Option<String>,
    #[serde(default)]
    agent_name: Option<String>,
    #[serde(default)]
    lead_session_id: Option<String>,
    #[serde(default)]
    custom_title: Option<String>,
    #[serde(default)]
    git_repo_root: Option<String>,
    #[serde(default)]
    git_branch: Option<String>,
    #[serde(default)]
    git_is_worktree: bool,
    #[serde(default)]
    is_tmux: Option<bool>,
    #[serde(default)]
    tmux_pane: Option<String>,
    #[serde(default)]
    parent_terminal: Option<String>,
    #[serde(default)]
    loops: HashMap<String, LoopInfo>,
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
        "Edit" | "MultiEdit" | "Write" | "Read" => basename(&get_str("file_path")),
        "Grep" => trunc(&get_str("pattern"), 40),
        "Glob" => get_str("pattern"),
        "Task" => trunc(&get_str("prompt"), 60),
        "WebFetch" => trunc(&get_str("url"), 60),
        "CronCreate" => {
            let cron = get_str("cron");
            let prompt = trunc(&get_str("prompt"), 50);
            format!("{cron} {prompt}").trim().to_string()
        }
        "CronDelete" => get_str("id"),
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
// Tmux detection — mirrors dispatcher._detect_tmux_info()
// ---------------------------------------------------------------------------

fn detect_tmux_info() -> (bool, Option<String>, Option<String>) {
    if env::var("TMUX").is_err() {
        return (false, None, None);
    }

    let pane = env::var("TMUX_PANE").ok();

    // Try to get the parent terminal from tmux's environment
    let parent_terminal = detect_tmux_parent_terminal();

    (true, pane, parent_terminal)
}

fn detect_tmux_parent_terminal() -> Option<String> {
    // Strategy 1: Check TERM_PROGRAM in tmux's environment
    if let Ok(output) = std::process::Command::new("tmux")
        .args(["show-environment", "TERM_PROGRAM"])
        .output()
    {
        if output.status.success() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            let line = stdout.trim();
            if !line.starts_with('-') {
                if let Some(value) = line.strip_prefix("TERM_PROGRAM=") {
                    let result = match value {
                        "iTerm.app" => Some("iTerm2"),
                        "ghostty" => Some("Ghostty"),
                        "Apple_Terminal" => Some("Terminal"),
                        "WarpTerminal" => Some("Warp"),
                        _ => None,
                    };
                    if let Some(name) = result {
                        return Some(name.into());
                    }
                }
            }
        }
    }

    // Strategy 2: Walk the tmux client's parent process tree
    if let Ok(output) = std::process::Command::new("tmux")
        .args(["list-clients", "-F", "#{client_pid}"])
        .output()
    {
        if output.status.success() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            if let Some(first_line) = stdout.trim().lines().next() {
                if let Ok(client_pid) = first_line.parse::<u32>() {
                    if let Some(terminal) = find_terminal_in_ancestors(client_pid) {
                        return Some(terminal);
                    }
                }
            }
        }
    }

    None
}

/// Walk the process tree from pid upwards looking for a known terminal.
fn find_terminal_in_ancestors(mut pid: u32) -> Option<String> {
    for _ in 0..10 {
        if pid <= 1 {
            break;
        }
        let output = match std::process::Command::new("ps")
            .args(["-p", &pid.to_string(), "-o", "ppid=,comm="])
            .output()
        {
            Ok(o) => o,
            Err(_) => break,
        };
        let text = String::from_utf8_lossy(&output.stdout);
        let line = text.trim();
        if line.is_empty() {
            break;
        }
        let (ppid_str, comm) = match line.split_once(|c: char| c.is_whitespace()) {
            Some(pair) => pair,
            None => break,
        };
        let comm = comm.trim();
        if comm.contains("iTerm") {
            return Some("iTerm2".into());
        }
        if comm.contains("ghostty") {
            return Some("Ghostty".into());
        }
        if comm.contains("Terminal.app") {
            return Some("Terminal".into());
        }
        if comm.contains("Warp") {
            return Some("Warp".into());
        }
        let comm_lower = comm.to_lowercase();
        if comm_lower.contains("jetbrains") || comm_lower.contains("idea") {
            return Some("IntelliJ".into());
        }
        pid = match ppid_str.parse() {
            Ok(p) => p,
            Err(_) => break,
        };
    }
    None
}

// ---------------------------------------------------------------------------
// Transcript token parsing — mirrors dispatcher._get_usage_from_transcript()
// ---------------------------------------------------------------------------

fn get_usage_from_transcript(
    transcript_path: Option<&str>,
    existing_custom_title: Option<&str>,
) -> (u64, Option<String>, Option<String>) {
    let path_str = match transcript_path {
        Some(p) if !p.is_empty() => p,
        _ => return (0, None, None),
    };
    let path = Path::new(path_str);
    if !path.exists() {
        return (0, None, None);
    }

    // When no cached title, do a full-file scan for custom-title entries.
    // Otherwise skip — we'll check the tail below for re-renames.
    let mut custom_title: Option<String> = existing_custom_title.map(|s| s.to_string());
    if existing_custom_title.is_none() {
        if let Ok(content) = fs::read_to_string(path) {
            for line in content.lines() {
                if !line.contains("custom-title") {
                    continue;
                }
                if let Ok(entry) = serde_json::from_str::<serde_json::Value>(line) {
                    if entry.get("type").and_then(|v| v.as_str()) == Some("custom-title") {
                        custom_title = entry
                            .get("customTitle")
                            .and_then(|v| v.as_str())
                            .filter(|s| !s.is_empty())
                            .map(|s| s.to_string());
                    }
                }
            }
        }
    }

    // Tail read (last 10KB) for tokens, model, and title updates
    let mut file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return (0, None, custom_title),
    };
    let size = match file.metadata() {
        Ok(m) => m.len(),
        Err(_) => return (0, None, custom_title),
    };
    let offset = if size > 51200 { size - 51200 } else { 0 };
    if file.seek(SeekFrom::Start(offset)).is_err() {
        return (0, None, custom_title);
    }
    let mut buf = Vec::new();
    if file.read_to_end(&mut buf).is_err() {
        return (0, None, custom_title);
    }
    let tail_cow = String::from_utf8_lossy(&buf);
    let tail: &str = if offset > 0 {
        match tail_cow.find('\n') {
            Some(idx) => &tail_cow[idx + 1..],
            None => &tail_cow,
        }
    } else {
        &tail_cow
    };

    let mut tokens: u64 = 0;
    let mut model: Option<String> = None;
    let mut found_title_in_tail = false;

    // Search backwards for the latest usage and title updates
    for line in tail.trim().lines().rev() {
        // Check for custom-title re-renames in the tail
        if !found_title_in_tail && line.contains("custom-title") {
            if let Ok(entry) = serde_json::from_str::<serde_json::Value>(line) {
                if entry.get("type").and_then(|v| v.as_str()) == Some("custom-title") {
                    custom_title = entry
                        .get("customTitle")
                        .and_then(|v| v.as_str())
                        .filter(|s| !s.is_empty())
                        .map(|s| s.to_string());
                    found_title_in_tail = true;
                    continue;
                }
            }
        }
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
                    tokens = cache_read + input + cache_creation;
                    model = msg
                        .get("model")
                        .and_then(|v| v.as_str())
                        .map(|s| s.to_string());
                    break;
                }
            }
        }
    }

    (tokens, model, custom_title)
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
            team_name: None,
            agent_name: None,
            lead_session_id: None,
            custom_title: None,
            git_repo_root: None,
            git_branch: None,
            git_is_worktree: false,
            is_tmux: None,
            tmux_pane: None,
            parent_terminal: None,
            loops: HashMap::new(),
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
    if let Some(pm) = get_opt_str(event, "permission_mode") {
        state.permission_mode = pm;
    }
    // Update custom_title if the event provides one — Claude Code sends it after /rename
    if let Some(t) = get_opt_str(event, "customTitle") {
        state.custom_title = Some(t);
    }
    // Backfill git fields for sessions created before worktree support
    if state.git_repo_root.is_none() && !state.cwd.is_empty() {
        let (repo_root, branch, is_wt) = get_git_info(&state.cwd);
        // Use empty string sentinel to avoid re-calling git on non-repo dirs
        state.git_repo_root = Some(repo_root.unwrap_or_default());
        state.git_branch = branch;
        state.git_is_worktree = is_wt;
    }
    // Backfill tmux fields — None = not yet checked (sentinel pattern like git_repo_root)
    if state.is_tmux.is_none() {
        let (is_tmux, tmux_pane, parent_terminal) = detect_tmux_info();
        state.is_tmux = Some(is_tmux);
        state.tmux_pane = tmux_pane;
        state.parent_terminal = parent_terminal;
    }
    // Skip TTY detection for tmux sessions — they use pane IDs
    if state.tty.is_none() && state.is_tmux != Some(true) {
        state.tty = detect_tty();
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

fn read_lead_session_id(team_name: &str) -> Option<String> {
    let home = env::var("HOME").ok()?;
    let config_path = PathBuf::from(home)
        .join(".claude")
        .join("teams")
        .join(team_name)
        .join("config.json");
    let content = fs::read_to_string(config_path).ok()?;
    let config: serde_json::Value = serde_json::from_str(&content).ok()?;
    config
        .get("leadSessionId")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
}

fn handle_session_start(event: &serde_json::Value) {
    let session_id = get_str(event, "session_id");
    let now = utcnow();

    let team_name = get_opt_str(event, "teamName");
    let agent_name = get_opt_str(event, "agentName");
    let lead_session_id = team_name
        .as_deref()
        .and_then(read_lead_session_id);

    let mut state = SessionState {
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
        team_name,
        agent_name,
        lead_session_id,
        custom_title: get_opt_str(event, "customTitle"),
        git_repo_root: None,
        git_branch: None,
        git_is_worktree: false,
        is_tmux: None,
        tmux_pane: None,
        parent_terminal: None,
        loops: HashMap::new(),
    };
    let (repo_root, branch, is_wt) = get_git_info(&state.cwd);
    state.git_repo_root = Some(repo_root.unwrap_or_default());
    state.git_branch = branch;
    state.git_is_worktree = is_wt;
    let (is_tmux, tmux_pane, parent_terminal) = detect_tmux_info();
    state.is_tmux = Some(is_tmux);
    state.tmux_pane = tmux_pane;
    state.parent_terminal = parent_terminal;
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

    // Cron/loop capture from structured tool_response
    if let Some(tool_response) = event.get("tool_response").and_then(|v| v.as_object()) {
        match tool_name.as_str() {
            "CronCreate" => {
                if let Some(task_id) = tool_response.get("id").and_then(|v| v.as_str()) {
                    if !task_id.is_empty() {
                        let tool_input = event.get("tool_input").cloned()
                            .unwrap_or(serde_json::Value::Object(Default::default()));
                        let cron_expr = tool_input.get("cron").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        let prompt = tool_input.get("prompt").and_then(|v| v.as_str()).unwrap_or("").to_string();
                        state.loops.insert(task_id.to_string(), LoopInfo {
                            task_id: task_id.to_string(),
                            cron_expr,
                            human_schedule: tool_response.get("humanSchedule").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                            prompt,
                            recurring: tool_response.get("recurring").and_then(|v| v.as_bool()).unwrap_or(true),
                            created_at: utcnow().format("%Y-%m-%dT%H:%M:%S").to_string(),
                        });
                    }
                }
            }
            "CronDelete" => {
                if let Some(task_id) = tool_response.get("id").and_then(|v| v.as_str()) {
                    state.loops.remove(task_id);
                }
            }
            "CronList" => {
                if let Some(jobs) = tool_response.get("jobs").and_then(|v| v.as_array()) {
                    let mut new_loops = HashMap::new();
                    for job in jobs {
                        let tid = job.get("id").and_then(|v| v.as_str()).unwrap_or("");
                        if tid.is_empty() { continue; }
                        let existing = state.loops.get(tid);
                        new_loops.insert(tid.to_string(), LoopInfo {
                            task_id: tid.to_string(),
                            cron_expr: job.get("cron").and_then(|v| v.as_str())
                                .unwrap_or(existing.map(|e| e.cron_expr.as_str()).unwrap_or(""))
                                .to_string(),
                            human_schedule: job.get("humanSchedule").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                            prompt: job.get("prompt").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                            recurring: job.get("recurring").and_then(|v| v.as_bool()).unwrap_or(true),
                            created_at: existing.map(|e| e.created_at.clone())
                                .unwrap_or_else(|| utcnow().format("%Y-%m-%dT%H:%M:%S").to_string()),
                        });
                    }
                    state.loops = new_loops;
                }
            }
            _ => {}
        }
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

    let (tokens, model, custom_title) = get_usage_from_transcript(
        state.transcript_path.as_deref(),
        state.custom_title.as_deref(),
    );
    state.context_tokens = tokens;
    if let Some(m) = model {
        state.model = Some(m);
    }
    if let Some(t) = custom_title {
        state.custom_title = Some(t);
    }
    // Refresh branch in case user checked out a different branch during the turn
    if !state.cwd.is_empty() {
        let (_, branch, _) = get_git_info(&state.cwd);
        if let Some(b) = branch {
            state.git_branch = Some(b);
        }
    }

    save_session(&state);
    log_activity(&state.session_id, "Stop", "idle");
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

fn handle_permission_request(event: &serde_json::Value) {
    let tool_name = get_str(event, "tool_name");
    let mut state = load_or_create(event);
    // Don't overwrite WAITING_ANSWER (AskUserQuestion) or PLAN (ExitPlanMode)
    if !matches!(
        state.status,
        SessionStatus::WaitingAnswer | SessionStatus::Plan
    ) {
        state.status = SessionStatus::WaitingPermission;
    }
    state.last_event = "PermissionRequest".into();
    state.last_event_at = utcnow();
    save_session(&state);
    log_activity(&state.session_id, "PermissionRequest", &tool_name);
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
        "UserPromptSubmit" => handle_user_prompt_submit(&event),
        "SubagentStop" => handle_subagent_stop(&event),
        "PreCompact" => handle_pre_compact(&event),
        "SessionEnd" => handle_session_end(&event),
        "PermissionRequest" => handle_permission_request(&event),
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
            team_name: None,
            agent_name: None,
            lead_session_id: None,
            custom_title: None,
            git_repo_root: None,
            git_branch: None,
            git_is_worktree: false,
            is_tmux: None,
            tmux_pane: None,
            parent_terminal: None,
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

        let (tokens, model, custom_title) = get_usage_from_transcript(Some(path.to_str().unwrap()), None);
        assert_eq!(tokens, 650);
        assert_eq!(model, Some("claude-opus-4-6".into()));
        assert_eq!(custom_title, None);
    }

    #[test]
    fn test_transcript_parsing_custom_title() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("transcript.jsonl");
        let mut f = File::create(&path).unwrap();

        writeln!(f, r#"{{"type": "custom-title", "customTitle": "my-session", "sessionId": "abc"}}"#).unwrap();

        let (tokens, model, custom_title) = get_usage_from_transcript(Some(path.to_str().unwrap()), None);
        assert_eq!(tokens, 0);
        assert_eq!(model, None);
        assert_eq!(custom_title, Some("my-session".into()));
    }

    #[test]
    fn test_transcript_cached_title_skips_full_scan() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("transcript.jsonl");
        let mut f = File::create(&path).unwrap();

        // Title entry exists but we pass a cached title — full scan is skipped,
        // and since the entry is also in the tail it gets picked up there.
        writeln!(f, r#"{{"type": "custom-title", "customTitle": "old-name", "sessionId": "abc"}}"#).unwrap();

        let (_, _, custom_title) = get_usage_from_transcript(Some(path.to_str().unwrap()), Some("cached-name"));
        // Tail contains the entry so it overwrites the cached value
        assert_eq!(custom_title, Some("old-name".into()));
    }

    #[test]
    fn test_transcript_cached_title_preserved_when_no_entry() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("transcript.jsonl");
        let mut f = File::create(&path).unwrap();

        // No custom-title entry — cached value should be preserved
        writeln!(f, r#"{{"type": "text", "content": "hello"}}"#).unwrap();

        let (_, _, custom_title) = get_usage_from_transcript(Some(path.to_str().unwrap()), Some("cached-name"));
        assert_eq!(custom_title, Some("cached-name".into()));
    }

    #[test]
    fn test_transcript_parsing_empty() {
        let (tokens, model, custom_title) = get_usage_from_transcript(None, None);
        assert_eq!(tokens, 0);
        assert_eq!(model, None);
        assert_eq!(custom_title, None);
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
