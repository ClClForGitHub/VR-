# Agent Execution Harness Decision Log

## DEC-20260701-core-harness: Use small task packets instead of one large plan

Decision:
- Future coding-agent work will be split into small task packets with explicit file scope, tests, acceptance criteria, and final reports.

Reason:
- Large plans are easy for agents to skim and hard to enforce.
- The project needs visible state, artifacts, frontend status, and verification for every meaningful slice.

Alternatives considered:
- One comprehensive master plan for all remaining work.
- Unstructured chat instructions for each coding session.

Consequences:
- More rounds, but each round has a clearer closure boundary.
- Each task can be reviewed for actual user-flow progress.
