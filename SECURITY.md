# Security Policy

## Supported versions

Only the most recent release receives fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security -> Report a
vulnerability) rather than opening a public issue.

## Scope

This integration runs inside Home Assistant on a local network and talks to a
projector over an unauthenticated, unencrypted control port (TCP 43728) that
the projector itself exposes. It has no cloud component, stores no
credentials, opens no ports of its own and has no Python runtime dependencies
beyond Home Assistant.

Treat the projector control network as trusted: anyone who can reach port 43728
can control the projector with or without this integration. See
[Network security](README.md#network-security) for a firewall setup.

### What the integration guards against

- Input typed into Home Assistant is validated before use (host, port,
  projector ID, polling interval, macro names, action values). No text typed
  by a user is ever sent to the projector; frames are built from numbers with
  a computed length and checksum.
- Data from the projector is treated as untrusted: frame length and checksum
  are checked, every request and every poll has a time limit, names are cut to
  64 printable characters and the number of thermal sensors is capped.
- The projector is not flooded: one connection, one request at a time,
  commands in a burst share one status refresh, and an unreachable projector
  is retried once per polling interval.
- Diagnostics redact the IP address and the serial number.

### Ports the projector exposes

Taken from Sharp NEC's protocol documentation. Only 43728 is used by this
integration.

| Port | Protocol | Function |
| --- | --- | --- |
| 7 | TCP | Echo |
| 80 | TCP | HTTP (web page, unencrypted) |
| 161 | UDP | SNMP agent |
| 1173 | TCP | D-Cinema security (TLS) |
| 30000 / 30001 | TCP / UDP | Reserved |
| 43680, 43682 | TCP | Cinema control (ICP) |
| 43696, 43701 | TCP | Enigma control and marriage |
| 43712 | TCP | SIB control |
| 43728 | TCP | System control, projector head (used here) |
| 43729 | TCP | System control, ICP |
| 43744-43759 | TCP | IMB control and marriage |
