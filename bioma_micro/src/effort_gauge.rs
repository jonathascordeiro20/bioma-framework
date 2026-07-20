//! `effort_gauge.rs` — O(n) task-complexity gauge for dynamic thinking budgets.
//!
//! Reasoning ("extended thinking") tokens are decode-priced (~5× input) and
//! sequential — the single most expensive token class. Yet most real workload
//! turns are trivial ("yes", "continue", short corrections) and pay a full
//! thinking budget for nothing. This gauge scores a request with cheap lexical
//! signals — no LLM, no allocation-heavy NLP, single lowercase pass — and maps
//! the score to a recommended thinking budget the caller forwards to the API
//! (`budget_tokens` on Anthropic, `reasoning_effort` on OpenAI).
//!
//! Deterministic and auditable: the returned dict exposes every raw signal so
//! a pipeline can log *why* a budget was chosen.

use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Hard-task verb stems (en + pt) — matched by prefix so imperatives,
/// infinitives and inflections all count ("analise", "analisar", "analyzing").
/// Every stem is ≥5 chars to avoid false prefixes.
const HARD_STEMS: &[&str] = &[
    // en + shared latin roots
    "design", "architect", "optimi", "refactor", "implement", "analy", "compar",
    "debug", "deriv", "evaluat", "integrat", "migrat", "audit",
    // pt
    "projet", "arquitet", "otimiz", "refator", "implement", "analis", "planej",
    "avali", "estud", "viabilid", "estrateg", "constru", "desenvolv", "valid",
    "verific", "revis", "integr", "corrij", "corrig", "diagnostic", "investig",
];

/// Hard-task exact words too short or ambiguous for stemming.
const HARD_WORDS: &[&str] = &[
    "prove", "plan", "why", "how", "erro", "error", "bug", "falha", "broken",
    "gere", "monte", "compare", "depure", "prova",
];

const CONSTRAINT_MARKERS: &[&str] = &[
    // en
    "must", "never", "always", "without", "ensure", "require", "requirement",
    "constraint", "invariant", "except",
    // pt
    "deve", "nunca", "sempre", "sem", "garanta", "requisito", "restrição",
    "restricao", "invariante", "exceto", "obrigatório", "obrigatorio",
];

const TRIVIAL_MARKERS: &[&str] = &[
    // en
    "ok", "okay", "yes", "no", "thanks", "continue", "sure", "great", "good",
    // pt
    "sim", "não", "nao", "obrigado", "obrigada", "continue", "prossiga",
    "segue", "beleza", "certo", "show", "valeu",
];

const CODE_KEYWORDS: &[&str] = &[
    "fn", "def", "class", "import", "return", "const", "let", "select", "async",
    "struct", "impl", "function", "var", "pub",
];

#[inline]
fn contains_word(words: &[&str], table: &[&str]) -> usize {
    words.iter().filter(|w| table.contains(&w.trim_matches(|c: char| !c.is_alphanumeric()))).count()
}

#[inline]
fn hard_hits(words: &[&str]) -> usize {
    words
        .iter()
        .map(|w| w.trim_matches(|c: char| !c.is_alphanumeric()))
        .filter(|w| HARD_WORDS.contains(w) || HARD_STEMS.iter().any(|s| w.starts_with(s)))
        .count()
}

/// Gauge the reasoning effort a request deserves. Returns a dict:
/// `score` (0..1), `tier` ("off" | "low" | "medium" | "high"),
/// `budget_tokens` (0 | 1024 | 4096 | 16384) and the raw `signals`.
#[pyfunction]
#[pyo3(signature = (text,))]
pub fn effort_gauge<'py>(py: Python<'py>, text: &str) -> PyResult<Bound<'py, PyDict>> {
    let lower = text.to_lowercase();
    let words: Vec<&str> = lower.split_whitespace().collect();
    let n = words.len();

    // --- raw signals, all O(n) ---
    let len_score = (n as f32 / 400.0).min(1.0);

    let code_chars = lower
        .bytes()
        .filter(|b| matches!(b, b'{' | b'}' | b';' | b'(' | b')' | b'=' | b'<' | b'>' | b'`'))
        .count();
    let code_hits = contains_word(&words, CODE_KEYWORDS) + code_chars / 6;
    let code_score = (code_hits as f32 / 12.0).min(1.0);

    let digit_ratio = if lower.is_empty() {
        0.0
    } else {
        lower.bytes().filter(|b| b.is_ascii_digit()).count() as f32 / lower.len() as f32
    };
    let digit_score = (digit_ratio * 8.0).min(1.0);

    let hard_hits = hard_hits(&words);
    let hard_score = (hard_hits as f32 / 3.0).min(1.0);

    let constraint_hits = contains_word(&words, CONSTRAINT_MARKERS);
    let constraint_score = (constraint_hits as f32 / 6.0).min(1.0);

    // Novelty: unique-word ratio. Repetitive floods and boilerplate don't
    // deserve reasoning budget (they deserve `saturation_scan`).
    let novelty = if n == 0 {
        0.0
    } else {
        let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::with_capacity(n);
        let unique = words.iter().filter(|w| seen.insert(**w)).count();
        unique as f32 / n as f32
    };

    // --- combination ---
    let raw = 0.30 * len_score
        + 0.25 * hard_score
        + 0.20 * constraint_score
        + 0.15 * code_score
        + 0.10 * digit_score;
    let mut score = (raw * (0.5 + 0.5 * novelty)).clamp(0.0, 1.0);

    // Trivial override: very short, no hard verbs, no code — or a pure
    // acknowledgement — is a no-thinking turn regardless of other signals.
    let trivial_hits = contains_word(&words, TRIVIAL_MARKERS);
    if (n < 8 && hard_hits == 0 && code_hits == 0) || (n <= 3 && trivial_hits > 0) {
        score = score.min(0.05);
    }

    let (tier, budget): (&str, u32) = if score < 0.15 {
        // An explicit hard-task verb guarantees at least a small budget — a
        // short "analyze the plan" still deserves *some* reasoning.
        if hard_hits >= 1 && n >= 4 && score > 0.05 {
            ("low", 1024)
        } else {
            ("off", 0)
        }
    } else if score < 0.40 {
        ("low", 1024)
    } else if score < 0.70 {
        ("medium", 4096)
    } else {
        ("high", 16384)
    };

    let signals = PyDict::new(py);
    signals.set_item("words", n)?;
    signals.set_item("len_score", len_score)?;
    signals.set_item("hard_hits", hard_hits)?;
    signals.set_item("constraint_hits", constraint_hits)?;
    signals.set_item("code_hits", code_hits)?;
    signals.set_item("digit_ratio", digit_ratio)?;
    signals.set_item("novelty", novelty)?;
    signals.set_item("trivial_hits", trivial_hits)?;

    let d = PyDict::new(py);
    d.set_item("score", score)?;
    d.set_item("tier", tier)?;
    d.set_item("budget_tokens", budget)?;
    d.set_item("signals", signals)?;
    Ok(d)
}
