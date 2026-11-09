# Security Architecture

## Overview
The ConsequenceMap platform is designed to facilitate secure interactions between agents and the core system.

## Trust Boundaries
1. **Agent (Untrusted)** <-> **ConsequenceMap Core** <-> **Security Guard (Trusted)** <-> **Human Authorizer (External Device)**

### Where Each Component Lives
- *Agent*: Runs on the local system with untrusted execution.
- *ConsequenceMap Core*: Operates as a protected module
- *Security Guard*: Runs in a separate process and OS identity.
- *Human Authorizer*: Utilizes a phone-based mobile authorization mechanism.

### Enforcement Mechanisms
Trust boundaries are enforced through:
- **Authorization Checks**: Mandatory checks in the security guard.
- **Process Isolation**: Ensures that the Security Guard operates separately from untrusted agents.
- **Physical Isolation**: The Human Authorizer uses an independent device to enhance security.

### Architectural Problem
Currently, the Guardian runs in-process as a Hermes plugin, which poses a risk to the trust model. It is imperative to refactor this into a separate process.
