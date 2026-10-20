# CareLoop

> **Self-hosted MCP Server for Alexa+ Elder Care Monitoring**  
> *Built for the Amazon Developer Hackathon (Alexa+ Track, AWS Builder, and Open Source Mini-Challenges)*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Spec](https://img.shields.io/badge/MCP%20Spec-2025--11--25+-green.svg)](https://modelcontextprotocol.io/)

CareLoop allows **Alexa+** to look after an elderly parent living alone. It logs routine events (pills, meals, movement, door), learns normal daily schedules, detects missed or anomalous events, checks in naturally by voice, and alerts family only when truly needed.

---

## Key Architectural Principles

1. **Deterministic Alert Engine**: The LLM (Amazon Bedrock) is used **only** for family summaries and memory Q&A. It **never** decides whether to alert or escalate. Alerts are generated strictly by deterministic statistical schedule analysis.
2. **Strict Privacy**: CareLoop records only structured event metadata (person, type, timestamp, sensor tags). Ambient audio or voice recordings are **never** stored.
3. **Full Auditability**: Every alert includes explicit, human-readable reasons explaining the expected baseline, what happened, and why an action was taken.
4. **Time Simulation Ready**: All time logic uses an injectable clock (`Clock`, `SystemClock`, `SimulatedClock`), enabling rapid multi-day scenario testing and live demo acceleration.
5. **Pluggable Storage**: Abstracted storage interface supporting **SQLite** for zero-dependency local execution and **DynamoDB** on AWS.
6. **Open Source & Tested**: Fully typed with Pydantic v2 and covered by comprehensive pytest test suites.

---

## Installation & Quick Start

```bash
# 1. Create and activate a Python 3.11+ virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run the test suite
pytest -v
```
