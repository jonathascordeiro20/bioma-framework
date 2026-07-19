"""
`bioma/carbon_ledger.py` — the auditable efficiency & carbon ledger.

Turns a deployment's REAL gateway audit log (the JSONL the gateway writes, with
`tokens_before` / `tokens_after` per request) into a signed, tamper-evident
report of tokens / energy / CO2e / USD **avoided** — the instrument a CFO, a
CSRD assessor or a third-party auditor can actually verify.

Four properties, because "a carbon number" is only credible if all four hold:

1. **Measured ground truth** — tokens come from the gateway audit, not a model.
2. **Tamper-evident** — the audit rows are hash-chained (each carries the SHA-256
   of its measured content + the previous hash); altering or dropping any row
   breaks the chain. `verify_chain` detects it.
3. **Signed** — the finished ledger (including the log's final hash) is signed
   with Ed25519. A third party verifies with the public key alone — no trust in
   the issuer required.
4. **Transparent coefficients** — energy uses the declared, versioned literature
   range from `bioma.esg` (low/mid/high, never one unqualified number). The
   reduction % is EXACT and coefficient-independent; only the absolute Wh/CO2e
   inherit the coefficient's uncertainty.

Honest by construction: the avoided emissions are a **counterfactual** ("you
would have emitted X; measured Y; difference Z"), reported SEPARATELY — never
netted against Scope 1/2/3 and never called an offset (per the GHG Protocol).

CLI:
    python -m bioma.carbon_ledger keygen --out issuer            # issuer.key / issuer.pub
    python -m bioma.carbon_ledger build bioma_gateway_audit.jsonl \\
        --grid br --price-in 2.0 --key issuer.key --out ledger.json
    python -m bioma.carbon_ledger verify ledger.json --pub issuer.pub --audit bioma_gateway_audit.jsonl

Signing needs `cryptography` (`pip install "bioma-framework[ledger]"`); building
an UNSIGNED ledger needs nothing but the standard library + bioma.esg.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Optional

from bioma.esg import GRID_GCO2_PER_KWH, KWH_PER_MTOK, estimate_saving

GENESIS = "GENESIS"
COEFF_VERSION = "esg-1.0"  # bumped when KWH_PER_MTOK changes; recorded in every ledger
_MEASURED_FIELDS = ("ts", "model", "tokens_before", "tokens_after")


def _canon(obj) -> bytes:
    """Deterministic bytes for hashing/signing: sorted keys, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _row_digest(row: dict, prev_hash: str) -> str:
    payload = {k: row.get(k) for k in _MEASURED_FIELDS}
    payload["prev_hash"] = prev_hash
    return hashlib.sha256(_canon(payload)).hexdigest()


# --------------------------------------------------------------------------- #
# hash chain — tamper evidence over the measured audit rows
# --------------------------------------------------------------------------- #
def chain_audit(rows: list[dict]) -> list[dict]:
    """Return rows with `prev_hash` + `hash` added, chained from GENESIS."""
    out, prev = [], GENESIS
    for r in rows:
        h = _row_digest(r, prev)
        out.append({**r, "prev_hash": prev, "hash": h})
        prev = h
    return out


def verify_chain(chained: list[dict]) -> tuple[bool, Optional[int]]:
    """Recompute the chain; return (ok, first_broken_index or None)."""
    prev = GENESIS
    for i, r in enumerate(chained):
        if r.get("prev_hash") != prev or r.get("hash") != _row_digest(r, prev):
            return False, i
        prev = r["hash"]
    return True, None


def chain_head(chained: list[dict]) -> str:
    return chained[-1]["hash"] if chained else GENESIS


# --------------------------------------------------------------------------- #
# ledger — measured tokens -> bounded energy / CO2e / USD avoided
# --------------------------------------------------------------------------- #
def build_ledger(rows: list[dict], *, grid: str = "world",
                 price_in_per_mtok: Optional[float] = None,
                 period: Optional[str] = None) -> dict:
    """Aggregate the audit into a ledger dict (unsigned). `rows` may be raw or
    already hash-chained; if chained, the chain is verified and its head recorded."""
    if grid not in GRID_GCO2_PER_KWH:
        raise ValueError(f"unknown grid {grid!r}; options: {sorted(GRID_GCO2_PER_KWH)}")

    chained = rows if rows and "hash" in rows[0] else chain_audit(rows)
    ok, broken = verify_chain(chained)
    if not ok:
        raise ValueError(f"audit chain broken at row {broken} — refusing to build a ledger")

    before = sum(int(r.get("tokens_before", 0)) for r in chained)
    after = sum(int(r.get("tokens_after", 0)) for r in chained)
    saved = before - after
    est = estimate_saving(saved, grid=grid) if saved > 0 else None
    usd = (saved / 1e6 * price_in_per_mtok) if (price_in_per_mtok and saved > 0) else None

    return {
        "schema": "bioma.carbon_ledger/1",
        "period": period,
        "requests": len(chained),
        "tokens": {"before": before, "after": after, "saved": saved},
        # EXACT and coefficient-independent:
        "input_reduction_pct": round(100 * (1 - after / before), 4) if before else 0.0,
        "grid": grid,
        "grid_gco2e_per_kwh": GRID_GCO2_PER_KWH[grid],
        "coefficient": {"version": COEFF_VERSION, "kwh_per_mtok": dict(KWH_PER_MTOK),
                        "note": "declared literature range; replace with your measured factor"},
        # ESTIMATES with low/mid/high bounds — never a single number:
        "wh_avoided": list(est["wh"]) if est else [0.0, 0.0, 0.0],
        "gco2e_avoided": list(est["gco2e"]) if est else [0.0, 0.0, 0.0],
        "usd_input_avoided": round(usd, 6) if usd is not None else None,
        "audit_chain_head": chain_head(chained),
        "accounting_note": (
            "AVOIDED emissions are a counterfactual (measured baseline minus "
            "measured shielded), reported separately. NOT a Scope 1/2/3 reduction "
            "and NOT an offset (GHG Protocol). Tokens measured; energy estimated "
            "with the declared coefficient bounds; the reduction % is exact."),
    }


# --------------------------------------------------------------------------- #
# signing — Ed25519 (optional dependency: cryptography)
# --------------------------------------------------------------------------- #
def _load_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey, Ed25519PublicKey)
        return serialization, Ed25519PrivateKey, Ed25519PublicKey
    except ImportError:
        raise SystemExit('signing needs cryptography — pip install "bioma-framework[ledger]"')


def keygen(stem: str) -> tuple[str, str]:
    """Write `<stem>.key` (private, PEM) and `<stem>.pub` (public, PEM)."""
    serialization, Ed25519PrivateKey, _ = _load_crypto()
    sk = Ed25519PrivateKey.generate()
    with open(f"{stem}.key", "wb") as f:
        f.write(sk.private_bytes(serialization.Encoding.PEM,
                                 serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()))
    with open(f"{stem}.pub", "wb") as f:
        f.write(sk.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo))
    return f"{stem}.key", f"{stem}.pub"


def sign_ledger(ledger: dict, private_key_pem: bytes) -> dict:
    """Return a signed envelope {ledger, signature_ed25519_hex, ...}."""
    serialization, _, _ = _load_crypto()
    sk = serialization.load_pem_private_key(private_key_pem, password=None)
    sig = sk.sign(_canon(ledger))
    return {"ledger": ledger, "signature_ed25519_hex": sig.hex(),
            "signed_over": "canonical JSON of `ledger` (sorted keys, compact)"}


def verify_ledger(envelope: dict, public_key_pem: bytes) -> bool:
    """True iff the signature matches the ledger under the public key."""
    serialization, _, _ = _load_crypto()
    from cryptography.exceptions import InvalidSignature
    pk = serialization.load_pem_public_key(public_key_pem)
    try:
        pk.verify(bytes.fromhex(envelope["signature_ed25519_hex"]),
                  _canon(envelope["ledger"]))
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# audit IO
# --------------------------------------------------------------------------- #
def read_audit(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main(argv: Optional[list] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="B.I.O.M.A. auditable carbon ledger.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pk = sub.add_parser("keygen", help="generate an Ed25519 issuer keypair")
    pk.add_argument("--out", default="issuer")

    pb = sub.add_parser("build", help="build a (signed) ledger from a gateway audit log")
    pb.add_argument("audit")
    pb.add_argument("--grid", default="world", choices=sorted(GRID_GCO2_PER_KWH))
    pb.add_argument("--price-in", type=float, default=None)
    pb.add_argument("--period", default=None)
    pb.add_argument("--key", default=None, help="Ed25519 private key PEM; omit for unsigned")
    pb.add_argument("--out", default="ledger.json")

    pv = sub.add_parser("verify", help="verify a ledger: signature + recompute from audit")
    pv.add_argument("ledger")
    pv.add_argument("--pub", required=True)
    pv.add_argument("--audit", default=None, help="recompute the ledger from this audit and compare")

    args = ap.parse_args(argv)

    if args.cmd == "keygen":
        k, p = keygen(args.out)
        print(f"wrote {k} (private — keep secret) and {p} (public — share with auditors)")
        return 0

    if args.cmd == "build":
        rows = read_audit(args.audit)
        if not rows:
            print(f"no audit rows in {args.audit}", file=sys.stderr)
            return 2
        ledger = build_ledger(rows, grid=args.grid, price_in_per_mtok=args.price_in,
                              period=args.period)
        if args.key:
            with open(args.key, "rb") as f:
                envelope = sign_ledger(ledger, f.read())
        else:
            envelope = {"ledger": ledger, "signature_ed25519_hex": None}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2, ensure_ascii=False)
        wl, wm, wh = ledger["wh_avoided"]
        print(f"ledger -> {args.out}")
        print(f"  requests {ledger['requests']:,} · tokens {ledger['tokens']['before']:,} -> "
              f"{ledger['tokens']['after']:,} (saved {ledger['tokens']['saved']:,}, "
              f"-{ledger['input_reduction_pct']:.1f}%)")
        print(f"  energy avoided {wl:,.1f}/{wm:,.1f}/{wh:,.1f} Wh · CO2e "
              f"{'/'.join(f'{g:,.1f}' for g in ledger['gco2e_avoided'])} g (grid {ledger['grid']})")
        if ledger["usd_input_avoided"] is not None:
            print(f"  input cost avoided ${ledger['usd_input_avoided']:,.4f}")
        print(f"  chain head {ledger['audit_chain_head'][:16]}… · "
              f"signed {'yes' if args.key else 'NO (unsigned)'}")
        return 0

    if args.cmd == "verify":
        with open(args.ledger, encoding="utf-8") as f:
            envelope = json.load(f)
        with open(args.pub, "rb") as f:
            sig_ok = verify_ledger(envelope, f.read())
        print(f"signature      : {'VALID' if sig_ok else 'INVALID'}")
        recompute_ok = None
        if args.audit:
            rows = read_audit(args.audit)
            rebuilt = build_ledger(rows, grid=envelope["ledger"]["grid"],
                                   period=envelope["ledger"].get("period"))
            # compare the measured core (tokens + chain head); ignore optional $ field
            core = ("tokens", "input_reduction_pct", "audit_chain_head")
            recompute_ok = all(rebuilt[k] == envelope["ledger"][k] for k in core)
            print(f"recompute      : {'MATCHES audit' if recompute_ok else 'MISMATCH — audit differs'}")
        ok = sig_ok and (recompute_ok is not False)
        print(f"verdict        : {'TRUSTWORTHY' if ok else 'DO NOT TRUST'}")
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
