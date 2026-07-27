# Decision 0001: MVP Technology Stack

Status: accepted

Date: 2026-07-27

## Decision

Use:

- React and TypeScript for the dashboard
- FastAPI and Python for the broker, mock bank and simulator
- OPA/Rego for stateless policy decisions
- PostgreSQL for transactional state and audit records
- Docker Compose for local orchestration

## Reason

This stack makes the policy decision point, enforcement point and financial source of truth visibly separate without requiring cloud accounts. It supports a credible concurrency demonstration and remains feasible for two students.

## Deliberate exclusions

Redis, Kafka, Kubernetes, Splunk and cloud deployment are excluded until the core prototype is complete. They would add operational work without strengthening the central demonstration.
