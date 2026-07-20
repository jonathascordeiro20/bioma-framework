//! `context_apoptosis.rs` — autonomous history dehydration.
//!
//! Long agent sessions (audit logs, massive chats) accumulate low-value ballast:
//! verbose tool output, stale turns, resolved chatter. This engine assigns each
//! message a **metabolic weight** by class, applies an aggressive **half-life
//! decay** (older + lower-value → drains faster), and **purges** any block whose
//! oxygen falls below the safe threshold — before the payload is dispatched to the
//! API. Durable classes (SYSTEM, FACT) are reinforced and never purged.
//!
//! Result: the input context window is dehydrated (universal input-token savings)
//! with a pure-Rust, thread-safe, allocation-light pass.

use std::collections::hash_map::DefaultHasher;
use std::collections::HashSet;
use std::hash::{Hash, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Instant;

use pyo3::prelude::*;
use pyo3::types::PyDict;

// Metabolic signal classes (bitwise flags shared with the Python layer).
pub const SYSTEM: u32 = 1 << 0; // durable instructions — never purge
pub const USER: u32 = 1 << 1; // user turns
pub const ASSISTANT: u32 = 1 << 2; // model turns
pub const FACT: u32 = 1 << 3; // retrieved facts / decisions to keep
pub const TOOL: u32 = 1 << 4; // verbose tool logs / scratchpad — prime target
pub const THINKING: u32 = 1 << 5; // stale reasoning blocks — cheapest to purge
const PROTECTED: u32 = SYSTEM | FACT;

/// ~4 chars/token — identical to the Python side so 'full' and 'pruned' counts agree.
#[inline]
pub fn est_tokens(s: &str) -> u32 {
    ((s.len() / 4) + 1) as u32
}

/// Initial metabolic weight (oxygen) by signal class. Durable data start rich;
/// verbose tool output starts oxygen-poor and dehydrates first.
#[inline]
fn metabolic_weight(signal: u32) -> f32 {
    if signal & PROTECTED != 0 {
        4.0
    } else if signal & (USER | ASSISTANT) != 0 {
        1.0
    } else if signal & THINKING != 0 {
        0.15
    } else if signal & TOOL != 0 {
        0.25
    } else {
        0.6
    }
}

struct Cell {
    content: String,
    oxygen: f32,
    signal: u32,
    tokens: u32,
}

// --------------------------------------------------------------------------- //
//  ContextApoptosis — stateful, incremental engine
// --------------------------------------------------------------------------- //
/// A self-dehydrating context window. Insert blocks, then run `dehydrate` cycles;
/// each cycle halves oxygen over `half_life` and purges anything below the
/// `safe_threshold` (durable classes are reinforced and survive).
#[pyclass]
pub struct ContextApoptosis {
    half_life: f32,
    safe_threshold: f32,
    items: Mutex<Vec<Cell>>,
    inserted_tokens: AtomicU64,
    apoptosed_tokens: AtomicU64,
    apoptosed_count: AtomicU64,
    // Purpose contract: a stable header rendered above everything else. Durable
    // session info lives here instead of being re-derived from old turns, which
    // lets apoptosis prune the history more aggressively.
    purpose: Mutex<Option<String>>,
    // Consolidated STATE ledger: bounded, deduplicated one-liners that absorb
    // the residue of purged turns (opt-in via `dehydrate(absorb=True)`).
    state: Mutex<Vec<(u64, String)>>,
    state_capacity: usize,
}

/// One-line digest of a purged cell for the STATE ledger (first 120 chars,
/// newlines collapsed).
fn digest_line(content: &str) -> String {
    let flat: String = content.split_whitespace().collect::<Vec<_>>().join(" ");
    let mut end = flat.len().min(120);
    while end < flat.len() && !flat.is_char_boundary(end) {
        end += 1;
    }
    if end < flat.len() { format!("{}…", &flat[..end]) } else { flat }
}

fn content_hash(s: &str) -> u64 {
    let mut h = DefaultHasher::new();
    s.hash(&mut h);
    h.finish()
}

#[pymethods]
impl ContextApoptosis {
    #[new]
    #[pyo3(signature = (half_life = 2.0, safe_threshold = 0.35, capacity = 256, state_capacity = 64))]
    fn new(half_life: f32, safe_threshold: f32, capacity: usize, state_capacity: usize) -> Self {
        Self {
            half_life: half_life.max(0.1),
            safe_threshold,
            items: Mutex::new(Vec::with_capacity(capacity)),
            inserted_tokens: AtomicU64::new(0),
            apoptosed_tokens: AtomicU64::new(0),
            apoptosed_count: AtomicU64::new(0),
            purpose: Mutex::new(None),
            state: Mutex::new(Vec::new()),
            state_capacity: state_capacity.max(1),
        }
    }

    /// Set (or clear, with `None`) the purpose contract — the stable header
    /// rendered above the history. Keep it byte-identical between calls so it
    /// stays inside a provider prompt-cache prefix.
    #[pyo3(signature = (text))]
    fn set_purpose(&self, text: Option<String>) {
        *self.purpose.lock().unwrap() = text;
    }

    /// Append a durable fact/decision to the consolidated STATE ledger.
    /// Deduplicated by content hash; oldest entries roll off past capacity.
    fn note_state(&self, fact: String) -> bool {
        let h = content_hash(&fact);
        let mut state = self.state.lock().unwrap();
        if state.iter().any(|(hash, _)| *hash == h) {
            return false;
        }
        state.push((h, fact));
        let cap = self.state_capacity;
        if state.len() > cap {
            let excess = state.len() - cap;
            state.drain(..excess);
        }
        true
    }

    /// The current STATE ledger entries, oldest first.
    fn state_entries(&self) -> Vec<String> {
        self.state.lock().unwrap().iter().map(|(_, s)| s.clone()).collect()
    }

    /// Insert a context block. `oxygen < 0` (default) → auto metabolic weight.
    #[pyo3(signature = (content, signal = 0, oxygen = -1.0))]
    fn insert(&self, content: String, signal: u32, oxygen: f32) {
        let tokens = est_tokens(&content);
        self.inserted_tokens.fetch_add(tokens as u64, Ordering::Relaxed);
        let oxy = if oxygen < 0.0 { metabolic_weight(signal) } else { oxygen };
        self.items.lock().unwrap().push(Cell { content, oxygen: oxy, signal, tokens });
    }

    /// One half-life decay cycle → returns the number of purged blocks. Durable
    /// classes are reinforced by `reinforce_boost`; everything else decays by
    /// `2^(-1/half_life)` and is purged in place if it drops below the threshold.
    ///
    /// With `absorb=True`, purged USER/ASSISTANT cells leave a one-line digest
    /// in the STATE ledger instead of vanishing without trace (TOOL/THINKING
    /// ballast is still dropped silently — it is noise by definition).
    #[pyo3(signature = (reinforce_boost = 0.5, absorb = false))]
    fn dehydrate(&self, py: Python<'_>, reinforce_boost: f32, absorb: bool) -> usize {
        let factor = 2f32.powf(-1.0 / self.half_life);
        let eps = self.safe_threshold;
        let (purged, digests): (usize, Vec<String>) = py.detach(|| {
            let mut items = self.items.lock().unwrap();
            for c in items.iter_mut() {
                if c.signal & PROTECTED != 0 {
                    c.oxygen += reinforce_boost;
                } else {
                    c.oxygen *= factor;
                }
            }
            let before = items.len();
            let mut freed: u64 = 0;
            let mut digests = Vec::new();
            items.retain(|c| {
                let alive = (c.signal & PROTECTED != 0) || c.oxygen >= eps;
                if !alive {
                    freed += c.tokens as u64;
                    if absorb && c.signal & (USER | ASSISTANT) != 0 {
                        digests.push(digest_line(&c.content));
                    }
                }
                alive
            });
            let purged = before - items.len();
            self.apoptosed_count.fetch_add(purged as u64, Ordering::Relaxed);
            self.apoptosed_tokens.fetch_add(freed, Ordering::Relaxed);
            (purged, digests)
        });
        for d in digests {
            self.note_state(d);
        }
        purged
    }

    fn active_context(&self) -> Vec<String> {
        self.items.lock().unwrap().iter().map(|c| c.content.clone()).collect()
    }
    /// The dehydrated context, newline-joined, ready to dispatch. Layout is
    /// cache-friendly: [purpose contract (stable)] + [STATE ledger] + [survivors].
    fn render(&self) -> String {
        let mut out = String::new();
        if let Some(p) = self.purpose.lock().unwrap().as_deref() {
            out.push_str(p);
            out.push('\n');
        }
        {
            let state = self.state.lock().unwrap();
            if !state.is_empty() {
                out.push_str("STATE:\n");
                for (_, s) in state.iter() {
                    out.push_str("- ");
                    out.push_str(s);
                    out.push('\n');
                }
            }
        }
        let items = self.items.lock().unwrap();
        let body = items.iter().map(|c| c.content.as_str()).collect::<Vec<_>>().join("\n");
        out.push_str(&body);
        out
    }
    fn active_tokens(&self) -> u64 {
        self.items.lock().unwrap().iter().map(|c| c.tokens as u64).sum()
    }
    fn inserted_tokens(&self) -> u64 {
        self.inserted_tokens.load(Ordering::Relaxed)
    }
    fn __len__(&self) -> usize {
        self.items.lock().unwrap().len()
    }
    /// Fraction of inserted tokens reclaimed by apoptosis (0..1).
    fn reduction_ratio(&self) -> f32 {
        let ins = self.inserted_tokens();
        if ins == 0 { 0.0 } else { self.apoptosed_tokens.load(Ordering::Relaxed) as f32 / ins as f32 }
    }
}

// --------------------------------------------------------------------------- //
//  dehydrate() — the one-shot stateless filter used by the OpenRouter client
// --------------------------------------------------------------------------- //
/// Dehydrate a whole message history in a single pass (oldest → newest).
///
/// `messages` is a list of `(content, signal_flags)`. Older, lower-value blocks
/// are decayed by recency-weighted half-life and purged below `safe_threshold`;
/// durable classes (SYSTEM, FACT) always survive. Returns the surviving blocks
/// plus audited savings and the pure-kernel latency in microseconds.
///
/// `stable_prefix` is the cache-aware zone: the first N messages are kept
/// verbatim no matter their class, so a provider prompt-cache prefix stays
/// byte-identical between calls. Apoptosis only acts on the mobile suffix.
#[pyfunction]
#[pyo3(signature = (messages, half_life = 6.0, safe_threshold = 0.35, stable_prefix = 0))]
pub fn dehydrate<'py>(
    py: Python<'py>,
    messages: Vec<(String, u32)>,
    half_life: f32,
    safe_threshold: f32,
    stable_prefix: usize,
) -> PyResult<Bound<'py, PyDict>> {
    let hl = half_life.max(0.1);
    let n = messages.len();
    let stable = stable_prefix.min(n);

    // --- the measured kernel hot-path: decide survivors (pure compute, GIL released) ---
    let t0 = Instant::now();
    let decisions: Vec<bool> = py.detach(|| {
        let mut keep = Vec::with_capacity(n);
        for (i, (content, signal)) in messages.iter().enumerate() {
            let protected = i < stable || signal & PROTECTED != 0;
            if protected {
                keep.push(true);
                continue;
            }
            let age = (n - 1 - i) as f32; // 0 = newest
            let oxygen = metabolic_weight(*signal) * 2f32.powf(-age / hl);
            let _ = content; // content length already priced into tokens below
            keep.push(oxygen >= safe_threshold);
        }
        keep
    });
    let latency_us = t0.elapsed().as_nanos() as f64 / 1000.0;

    // --- marshal survivors + audit token savings (not counted in kernel latency) ---
    let kept = pyo3::types::PyList::empty(py);
    let mut tokens_before: u64 = 0;
    let mut tokens_after: u64 = 0;
    let mut stable_tokens: u64 = 0;
    let mut purged: usize = 0;
    for (i, ((content, _sig), &alive)) in messages.iter().zip(decisions.iter()).enumerate() {
        let tok = est_tokens(content) as u64;
        tokens_before += tok;
        if i < stable {
            stable_tokens += tok;
        }
        if alive {
            tokens_after += tok;
            kept.append(content)?;
        } else {
            purged += 1;
        }
    }
    let reduction = if tokens_before == 0 {
        0.0
    } else {
        1.0 - (tokens_after as f64 / tokens_before as f64)
    };

    let d = PyDict::new(py);
    d.set_item("kept", kept)?;
    d.set_item("blocks_in", n)?;
    d.set_item("blocks_kept", n - purged)?;
    d.set_item("blocks_purged", purged)?;
    d.set_item("tokens_before", tokens_before)?;
    d.set_item("tokens_after", tokens_after)?;
    d.set_item("reduction", reduction)?;
    d.set_item("stable_prefix_tokens", stable_tokens)?;
    d.set_item("kernel_latency_us", latency_us)?;
    Ok(d)
}

// --------------------------------------------------------------------------- //
//  consolidation_gain() — when is it worth rewriting a cached prefix?
// --------------------------------------------------------------------------- //
/// Decide whether consolidating (rewriting) a provider-cached prefix pays off.
///
/// Rewriting a cached prefix purges `purgeable_tokens` of ballast but forfeits
/// the cache discount on the next call (a fresh cache write). Keeping it stale
/// re-pays the cached read of the ballast on every future call. In input-token
/// equivalents (uncached input = 1.0), over the next `calls_ahead` calls:
///
///   keep:        calls_ahead · prefix · read_ratio
///   consolidate: (prefix − purgeable) · write_ratio
///                + (calls_ahead − 1) · (prefix − purgeable) · read_ratio
///
/// Default ratios match current Anthropic pricing (cache read = 0.1× input,
/// cache write = 1.25× input). Returns the net gain (positive → consolidate
/// now) plus the break-even number of calls.
#[pyfunction]
#[pyo3(signature = (prefix_tokens, purgeable_tokens, calls_ahead = 8, cache_read_ratio = 0.1, cache_write_ratio = 1.25))]
pub fn consolidation_gain<'py>(
    py: Python<'py>,
    prefix_tokens: u64,
    purgeable_tokens: u64,
    calls_ahead: u32,
    cache_read_ratio: f64,
    cache_write_ratio: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let purgeable = purgeable_tokens.min(prefix_tokens);
    let new_prefix = (prefix_tokens - purgeable) as f64;
    let prefix = prefix_tokens as f64;
    let calls = calls_ahead.max(1) as f64;

    let cost_keep = calls * prefix * cache_read_ratio;
    let cost_consolidate = new_prefix * cache_write_ratio + (calls - 1.0) * new_prefix * cache_read_ratio;
    let gain = cost_keep - cost_consolidate;

    // Break-even k: k·prefix·r  =  new·w + (k−1)·new·r
    //             → k = new·(w − r) / (r·(prefix − new))   when purgeable > 0.
    let break_even = if purgeable == 0 {
        f64::INFINITY
    } else {
        (new_prefix * (cache_write_ratio - cache_read_ratio)) / (cache_read_ratio * (prefix - new_prefix))
    };

    let d = PyDict::new(py);
    d.set_item("consolidate", gain > 0.0)?;
    d.set_item("gain_token_equiv", gain)?;
    d.set_item("cost_keep", cost_keep)?;
    d.set_item("cost_consolidate", cost_consolidate)?;
    d.set_item("break_even_calls", break_even)?;
    Ok(d)
}

// --------------------------------------------------------------------------- //
//  saturation_scan() — cognitive-DDoS / flood detector
// --------------------------------------------------------------------------- //
/// Detect input saturation: the fraction of the payload that is **repetition**.
///
/// Cognitive-DDoS, forged-log floods and jailbreak spam are highly repetitive —
/// they reuse the same phrases to exhaust the context window. This scores the
/// fraction of duplicate `w`-token shingles (default 8): ~1.0 = a repetitive
/// flood (RED ALERT), ~0.0 = natural, high-entropy text. Pure O(n), no
/// allocation (shingles are hashed, not materialised), microsecond-scale.
#[pyfunction]
#[pyo3(signature = (text, window = 8))]
pub fn saturation_scan(text: &str, window: usize) -> f32 {
    let w = window.max(1);
    let tokens: Vec<&str> = text.split_whitespace().collect();
    let n = tokens.len();
    if n < w * 2 {
        return 0.0;
    }
    let windows = n - w + 1;
    let mut seen: HashSet<u64> = HashSet::with_capacity(windows);
    let mut dupes = 0usize;
    for i in 0..windows {
        let mut h = DefaultHasher::new();
        for t in &tokens[i..i + w] {
            t.hash(&mut h);
        }
        if !seen.insert(h.finish()) {
            dupes += 1;
        }
    }
    dupes as f32 / windows as f32
}
