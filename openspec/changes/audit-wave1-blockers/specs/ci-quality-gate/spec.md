# CI Quality Gate Specification

## Purpose

CI-side enforcement of a test coverage floor so coverage collapse cannot pass silently, aligned with the project's declared `coverage_threshold: 80`.

## Requirements

### Requirement: Coverage Floor Enforced in CI (CI-COV-001)

The CI workflow's pytest invocation MUST include `--cov-fail-under=80`. The documented project test command (`pytest tests/ -v --cov=src --cov-fail-under=80`) MUST match the CI invocation. If the honest measured baseline at landing time is below 80, the gate MAY be pinned to the measured baseline value as a documented interim threshold with a tracked follow-up (wave 4) to raise it to 80; the gate MUST NOT be permanently weakened or removed.

#### Scenario: CI invocation contains cov-fail-under

- GIVEN `.github/workflows/ci.yml`
- WHEN the pytest step command line is inspected
- THEN it contains `--cov=src` and `--cov-fail-under=<threshold>` where the threshold value is explicitly present in the file
- AND the threshold is 80 or a documented interim baseline recorded in this change's notes

#### Scenario: Coverage below threshold fails the build

- GIVEN a run of the CI pytest step on a codebase whose measured coverage is below the configured threshold
- WHEN the step completes
- THEN pytest exits non-zero due to the fail-under check
- AND the CI job is marked failed

#### Scenario: Local verify command matches CI

- GIVEN the verify/test command declared in project config (`openspec/config.yaml`)
- WHEN compared against the CI pytest invocation
- THEN both include an identical `--cov-fail-under` value

#### Scenario: Threshold is not silently weakened

- GIVEN any future modification to `.github/workflows/ci.yml`
- WHEN the `--cov-fail-under` value is inspected
- THEN it is greater than or equal to the previously pinned value (monotonically non-decreasing toward 80)
