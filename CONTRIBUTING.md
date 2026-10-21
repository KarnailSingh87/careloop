# Contributing to CareLoop

Thank you for your interest in contributing to **CareLoop**! We welcome contributions from developers, researchers, caregivers, and open-source enthusiasts.

CareLoop is built to assist families caring for elderly loved ones living alone through ambient smart home routine monitoring, deterministic anomaly detection, and voice interactions via Alexa+ and the Model Context Protocol (MCP).

---

## 1. Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free environment for everyone. Please be respectful, considerate, and collaborative in all communications and reviews.

---

## 2. Prerequisites

- **Python**: 3.11 or 3.12 (macOS, Linux, or WSL2 on Windows)
- **Git**: 2.30+
- **Virtual Environment Tool**: `venv` (standard library)
- **Optional**:
  - AWS CLI and AWS SAM CLI (for cloud infrastructure validation and deployment)
  - Node.js 18+ (only if editing frontend web simulator assets)

---

## 3. Quickstart Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/KarnailSingh87/careloop.git
   cd careloop
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   # Windows: .venv\Scripts\activate
   ```

3. **Install the package and development dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

4. **Verify the local installation**:
   ```bash
   pytest
   ```
   All 178 local unit and integration tests run offline without requiring AWS credentials or network access.

---

## 4. Development & CI Verification Commands

CareLoop uses GitHub Actions for continuous integration. Run all checks locally before submitting a Pull Request:

### Formatting & Linting
```bash
# Check code formatting
ruff format --check careloop/ tests/ scripts/

# Format code automatically
ruff format careloop/ tests/ scripts/

# Lint code for style and syntax errors
ruff check careloop/ tests/ scripts/
```

### Static Type Checking
```bash
# Verify type consistency across the core careloop package
mypy
```

### Security & Compliance Scanning
```bash
# Static Application Security Testing (SAST)
bandit -r careloop/

# Secret scanning against baseline
detect-secrets scan --baseline .secrets.baseline

# Dependency vulnerability scanning
pip-audit --skip-editable
```

### CloudFormation & Infrastructure Linting
```bash
# Validate AWS SAM templates
cfn-lint template.yaml deploy/sam/template.yaml
```

### Unit & Integration Testing
```bash
# Run local test suite with line-by-line coverage
pytest --cov=careloop --cov-report=term-missing

# Run end-to-end interactive demo verification
python scripts/run_demo.py --non-interactive
```

---

## 5. Architectural Principles

When writing or reviewing code for CareLoop, adhere strictly to these core design tenets:

1. **Deterministic Safety Rules over LLMs**:
   - Safety-critical determinations (missed medications, morning non-waking, daytime inactivity, multi-stage caregiver escalations) **must always be computed deterministically** via circular statistics, EWMA baselines, and explicit state machines.
   - Generative LLMs (AWS Bedrock) must **never** decide whether to alert family or escalate an emergency. Bedrock is reserved strictly for empathetic natural language summarization and grounded memory retrieval.

2. **Person-Level Authorization & Multi-Tenancy**:
   - All MCP tools and API endpoints must enforce person-level authorization. A caller authenticated for `dad` must never access `eleanor`'s routine records.
   - Event storage queries must validate caller scopes before retrieving or mutating data.

3. **Privacy & Data Minimization**:
   - Never log personal identifying information (PII), raw voice utterances, tokens, or credentials in application logs.
   - Use structured logging (`logger.info("Event logged", extra={...})`) with sanitized identifiers.

4. **Zero Cloud Dependencies for Local Testing**:
   - All unit tests, integration tests, and simulator workflows must run 100% locally with SQLite and mock clock/bridge implementations.
   - Real AWS tests (e.g., live Bedrock calls, live DynamoDB/SNS) are tagged with `@pytest.mark.aws` and skipped by default (`-m 'not aws'`).

5. **Explainability**:
   - Every alert and risk score calculation must output human-readable, auditable mathematical explanations (z-score, grace window minutes, current stage) so caregivers understand why an alert fired.

---

## 6. Pull Request Process

1. **Branch Naming**:
   - `feature/<short-description>`
   - `fix/<short-description>`
   - `docs/<short-description>`
2. **Commit Messages**:
   - Use concise, imperative commit messages (e.g., `feat: add circular variance clamp to baseline engine`).
3. **Pull Request Checklist**:
   - [ ] All 178 unit and integration tests pass (`pytest`).
   - [ ] Type check passes (`mypy`).
   - [ ] Linting and formatting pass (`ruff check .` and `ruff format --check .`).
   - [ ] No secrets or credentials added (`detect-secrets scan --baseline .secrets.baseline`).
   - [ ] CloudFormation templates validate cleanly (`cfn-lint template.yaml`).
   - [ ] Relevant documentation (README, friction log, architectural diagrams) updated if behavior changed.
