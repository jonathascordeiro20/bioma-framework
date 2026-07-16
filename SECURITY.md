# Security Policy

B.I.O.M.A. is security-adjacent software (secret redaction, flood detection,
payload hardening), so we treat reports against the project itself with priority.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | ✅        |

## Reporting a vulnerability

**Do not open a public issue for security reports.**

- Preferred: [GitHub private vulnerability reporting](https://github.com/jonathascordeiro20/bioma-framework/security/advisories/new)
- Alternative: email `jonathas.cordeiro2023@gmail.com` with subject `[SECURITY] bioma-framework`

You can expect an acknowledgement within **72 hours** and a triage verdict within
**7 days**. Please include a minimal reproduction; reports against the *threat
model* (e.g. a payload that bypasses `saturation_scan` or the secret redactor)
are in scope and very welcome.

## Scope notes

- The kernel never sends data anywhere — all processing is in-process. Reports
  about data exfiltration should target the *gateway* configuration surface.
- Prompt-injection payloads that survive dehydration are a quality issue, not a
  vulnerability, unless they also bypass the firewall redaction.
