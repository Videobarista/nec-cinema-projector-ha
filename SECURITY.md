# Security Policy

## Supported versions

Only the most recent release receives fixes.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security -> Report a
vulnerability) rather than opening a public issue.

## Scope

This integration runs inside Home Assistant on a local network and talks to a
projector over an unauthenticated control port (TCP 43728) that the projector
itself exposes. It has no cloud component, stores no credentials and has no
Python runtime dependencies beyond Home Assistant.

Treat the projector control network as trusted: anyone who can reach port 43728
can control the projector with or without this integration.
