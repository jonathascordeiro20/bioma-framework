//! B.I.O.M.A. Micro-Kernel — a lean efficiency & resilience core for LLM infra.
//!
//! Lean topology: proven primitives only, nothing else.
//!   * [`hormonal_bus`]       — lock-free in-memory signal injection (~2M sig/s, ~5μs).
//!   * [`context_apoptosis`]  — autonomous history dehydration (universal input-token
//!                              savings), cache-aware since 1.1.0 (`stable_prefix`).
//!   * [`effort_gauge`]       — O(n) task-complexity score → dynamic thinking budgets.
//!
//! No agents, no mitosis, no orchestration — only the microsecond hot path and the
//! apoptosis/effort filters, exposed to Python via PyO3.

mod context_apoptosis;
mod effort_gauge;
mod hormonal_bus;

use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

use context_apoptosis::{consolidation_gain, dehydrate, saturation_scan, ContextApoptosis};
use hormonal_bus::{HormonalBus, HormonalSignal};

/// The native module — `import bioma_micro`.
#[pymodule]
fn bioma_micro(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Signal injection
    m.add_class::<HormonalBus>()?;
    m.add_class::<HormonalSignal>()?;
    // Apoptosis filter
    m.add_class::<ContextApoptosis>()?;
    m.add_function(wrap_pyfunction!(dehydrate, m)?)?;
    m.add_function(wrap_pyfunction!(saturation_scan, m)?)?;
    // Cache economics + reasoning-budget gauge
    m.add_function(wrap_pyfunction!(consolidation_gain, m)?)?;
    m.add_function(wrap_pyfunction!(effort_gauge::effort_gauge, m)?)?;

    // Metabolic signal classes (bitwise flags) for the Python layer.
    m.add("SYSTEM", context_apoptosis::SYSTEM)?;
    m.add("USER", context_apoptosis::USER)?;
    m.add("ASSISTANT", context_apoptosis::ASSISTANT)?;
    m.add("FACT", context_apoptosis::FACT)?;
    m.add("TOOL", context_apoptosis::TOOL)?;
    m.add("THINKING", context_apoptosis::THINKING)?;

    m.add("__doc__", "B.I.O.M.A. Micro-Kernel — lock-free hormonal bus + context apoptosis.")?;
    m.add("__version__", "1.1.0")?;
    Ok(())
}
