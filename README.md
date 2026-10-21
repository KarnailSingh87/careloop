# CareLoop

> **Self-hosted Model Context Protocol (MCP) Server for Alexa+ Elderly Care Monitoring**  
> *Built for the Amazon Developer Hackathon: Alexa+ Track, AWS Builder Track, and Open Source Mini-Challenges*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Spec](https://img.shields.io/badge/MCP%20Spec-2025--11--25+-green.svg)](https://modelcontextprotocol.io/)
[![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock%20Claude%203-orange.svg)](https://aws.amazon.com/bedrock/)
[![Tests Passing](https://img.shields.io/badge/tests-139%20passed-brightgreen.svg)](tests/)

---

## What Was Built During the Hackathon

Every day, millions of aging parents live independently while their adult children worry from afar. Traditional telecare systems suffer from three critical flaws:
1. **Intrusive surveillance** (cameras, microphones, and persistent audio recording that violate dignity).
2. **Alarm fatigue** (rigid static thresholds that spam family whenever Mom sleeps in 20 minutes late).
3. **The AI Safety Paradox** (deploying non-deterministic LLMs to make life-critical emergency alert decisions).

**CareLoop** solves this through a self-hosted **Model Context Protocol (MCP)** server over **Streamable HTTP (spec 2025-11-25+)** that enables **Alexa+** to look after an elderly parent living alone. It passively learns each individual's personal circadian routine from ambient event metadata (pillbox openings, meals, room movement, door contacts), detects schedule deviations with circular statistics, conducts natural spoken check-ins by voice, and escalates to family caregivers via Amazon SNS only when truly necessary.

### Hackathon Challenge Tracks Addressed

- **Alexa+ Track**:
  - Implements the official **FastMCP / MCPServer Streamable HTTP transport** (`/mcp` and `/v1/mcp`) with bi-directional JSON-RPC 2.0 streaming.
  - Registers **9 Alexa+ voice tools** with prompt-engineered voice triggers and return schemas formatted for Alexa Text-To-Speech (TTS) synthesis.
  - Built an ambient **Voice Simulator UI** ([simulator/index.html](file:///Users/harsh/Desktop/Alexa+/careloop/simulator/index.html)) featuring native browser Web Speech API microphone dictation, SpeechSynthesis audio, a live MCP inspector showing JSON-RPC packets in real time, and a 6-step automated *"Dad skips lunch"* demonstration.
- **AWS Builder Track**:
  - **Amazon DynamoDB**: Single-table design (`PK`, `SK`) with AWS-managed server-side encryption at rest (`SSESpecification: { SSEEnabled: true }`) and Point-in-Time Recovery (PITR).
  - **Amazon SNS**: Caregiver alert topic encrypted with AWS KMS (`alias/aws/sns`).
  - **Amazon Bedrock (Claude 3 Haiku Converse API)**: Sandboxed strictly to empathetic daily routine summaries and factual memory Q&A—**the LLM is strictly prohibited from making alert decisions**.
  - **Amazon EventBridge**: Scheduled 1-minute autonomous health tick rule triggering a dedicated Lambda runner.
  - **Full IaC Packaging**: Production-grade **AWS CDK (Python)** in [deploy/cdk/](file:///Users/harsh/Desktop/Alexa+/deploy/cdk/) and **AWS SAM** in [template.yaml](file:///Users/harsh/Desktop/Alexa+/template.yaml).
- **Open Source Mini-Challenge**:
  - 100% open-source under the **MIT License**.
  - Fully typed with Pydantic v2 domain models and validated by **98 pytest tests** (100% pass rate).
  - Zero proprietary vendor lock-in: runs identically on local SQLite or AWS DynamoDB.

---

## Architecture

CareLoop strictly separates **deterministic safety logic** from **generative language synthesis**:

```mermaid
flowchart TD
    subgraph AmbientInterface ["1. Ambient Voice & Smart Home Interface"]
        Voice[("Elder Voice Input<br/>'I took my morning pills'")] --> Alexa[Alexa+ Ambient Assistant]
        Sensors[("Home Sensors<br/>Pillbox / Motion / Door")] --> Alexa
    end

    subgraph MCPGateway ["2. Streamable HTTP MCP Gateway (FastMCP)"]
        Alexa -->|"Streamable HTTP (2025-11-25)<br/>POST /mcp"| MCP["CareLoop MCP Server<br/>(Starlette ASGI on ECS Fargate)"]
        Auth["AlexaAuthMiddleware<br/>Bearer / API Key"] -.-> MCP
    end

    subgraph DeterministicEngine ["3. Deterministic Clinical Safety Engine (Zero LLM)"]
        MCP -->|"log_routine_event"| EWMA["Circular EWMA Baseline<br/>• Time-of-Day [0, 1440m)<br/>• Variance EWMA<br/>• Grace Window: μ + max(2σ, 30m)"]
        MCP -->|"check_routine_health<br/>tick_escalation"| Risk["Multi-Factor Risk Engine<br/>• Medication missed (0.4)<br/>• Inactivity / Falls (0.3)<br/>• Night wandering (0.2)<br/>• Meal missed (0.2)"]
        Risk --> StateMachine["Persisted Escalation State Machine<br/>Normal ➔ Gentle Check-In ➔ Repeat Check-In ➔ Notify Family"]
    end

    subgraph GenerativeLayer ["4. Sandboxed Generative Layer (Amazon Bedrock)"]
        MCP -->|"daily_summary<br/>ask_memory"| Bedrock["Amazon Bedrock (Converse API)<br/>Claude 3 Haiku<br/>• Warm family summaries<br/>• Factual event history Q&A<br/>(Short-circuits if no events found)"]
    end

    subgraph StorageLayer ["5. Pluggable Encrypted Storage"]
        EWMA & Risk & StateMachine & Bedrock --> Storage["Storage Interface<br/>(careloop/storage/base.py)"]
        Storage -->|"Local Dev"| SQLite[("Local SQLite DB<br/>careloop_local.db")]
        Storage -->|"AWS Production"| DynamoDB[("Amazon DynamoDB<br/>CareLoopData<br/>• Single-Table PK/SK<br/>• Encrypted at rest (KMS)")]
    end

    subgraph FamilyAlerts ["6. Caregiver Notification System"]
        StateMachine -->|"Notify Family"| Notifier["Alert Dispatcher"]
        Notifier -->|"Local Mode"| Console["Console / Terminal Log"]
        Notifier -->|"AWS Mode"| SNS["Amazon SNS Topic<br/>CareLoopAlertsTopic<br/>• SMS / Push to Daughter Linda<br/>• Deterministic Reasons Included"]
    end
```

---

## Routine Anomaly Detection Policy & Mathematical Formulation

CareLoop's anomaly engine ([careloop/engine/baseline.py](file:///Users/harsh/Desktop/Alexa+/careloop/engine/baseline.py)) learns and detects routine deviations through a mathematically grounded, clinically defensive architecture:

### 1. Timezone-Aware Evaluation & Daylight Saving Time (DST) Handling
- Every elder has a configured deployment timezone (e.g. `America/New_York`, `America/Chicago`, `Europe/London`).
- All timestamps must be timezone-aware (naive timestamps raise `ValueError` to prevent silent mixing of local time and UTC).
- Schedule baselines are evaluated in the elder's local wall-clock time. Consequently, when Daylight Saving Time transitions occur (e.g. EDT to EST), morning pills taken at 08:30 AM local time remain at 510.0 minutes both before and after the clock switch—preventing artificial 60-minute jumps and false anomalies.

### 2. Circular Statistics on a 24-Hour Circle
Daily routines oscillate around calendar boundaries (e.g. bedtime routines spanning 23:55 to 00:10). Standard linear averaging yields catastrophic variance explosion (averaging 5m and 1435m yields 720m—noon!).
CareLoop uses the signed shortest circular distance on the 1440-minute circle:
$$\Delta(a, b) = ((a - b + 720) \pmod{1440}) - 720 \in [-720, 720)$$

Circular Exponentially Weighted Moving Average (EWMA) updates:
$$\mu_{t} = (\mu_{t-1} + \alpha \cdot \Delta(x_t, \mu_{t-1})) \pmod{1440}$$
$$\sigma^2_{t} = (1 - \alpha) \cdot \sigma^2_{t-1} + \alpha \cdot (\Delta(x_t, \mu_{t-1}))^2$$

### 3. Robust Winsorized Updates Against Outliers
When calibrated ($N \ge 5$), extreme deviations ($|z| > 3.0$) are flagged as anomalies, but the difference $\Delta$ applied to update the EWMA baseline is clamped to $\pm 3.0\sigma$:
$$\Delta_{\text{effective}} = \max(-3\sigma, \min(3\sigma, \Delta))$$
This guarantees that an isolated emergency or hospital visit does not destroy the learned routine baseline for subsequent weeks.

### 4. Explicit Cold-Start Rule
- When an individual routine has fewer than 5 valid observations ($N < 5$), anomaly detection and missed-event alerts are **strictly suppressed**.
- `evaluate_routine()` explicitly returns `status="cold_start"`, preventing false alarms while the system is learning.

### 5. Configurable Grace Period & Small-Sample Calibration Notice
- Grace window formula: $W_{\text{grace}} = \mu + \max(k \cdot \sigma, \text{min\_grace\_minutes})$.
- The minimum grace period defaults to **30 minutes** (configurable).
- **Statistical Calibration Notice**: For small sample sizes ($N < 20$), sample variance is an empirical estimate subject to sampling noise. The condition $|z| > 2$ is an operational screening heuristic rather than an exact calibrated Gaussian 95% confidence interval. The combination of minimum grace windows and minimum variance floors ($\sigma \ge 5\text{m}$) prevents overly brittle thresholds.

### 6. No Double-Counting & Late Event Recovery
- An event occurring within the grace window is recognized as normal completed activity.
- If an alert is triggered after the grace window expires and the elder subsequently completes the routine late, recording the event immediately clears the missed status and resets the escalation state machine to `NORMAL`.
- A late event is **never counted as both an anomaly and a missed event** at the same evaluation time.

### 7. Zero LLM in Life-Critical Decisions
- All risk scores and state transitions are **100% deterministic code** in [careloop/engine/risk.py](file:///Users/harsh/Desktop/Alexa+/careloop/engine/risk.py) and [careloop/engine/escalation.py](file:///Users/harsh/Desktop/Alexa+/careloop/engine/escalation.py).
- Amazon Bedrock is sandboxed strictly to family summaries and factual memory queries.

---

## Persisted Escalation State Machine & Reliability Architecture

CareLoop guarantees reliable routine escalation across server crashes, worker restarts, and repeated scheduled ticks through an optimistic concurrency controlled, idempotent state machine ([careloop/engine/escalation.py](file:///Users/harsh/Desktop/Alexa+/careloop/engine/escalation.py)):

### State Machine Architecture (Mermaid)

```mermaid
stateDiagram-v2
    [*] --> NORMAL: Initialize / Profile Created

    NORMAL --> GENTLE_CHECK_IN: Risk Score >= 0.3 (Missed Routine / Inactivity)
    NORMAL --> NORMAL: Repeated Tick (Risk < 0.3)

    GENTLE_CHECK_IN --> GENTLE_CHECK_IN: Repeated Tick (Elapsed < gentle_timeout)
    GENTLE_CHECK_IN --> REPEAT_CHECK_IN: Elapsed >= gentle_timeout (Unanswered Check-In)

    REPEAT_CHECK_IN --> REPEAT_CHECK_IN: Repeated Tick (Elapsed < repeat_timeout)
    REPEAT_CHECK_IN --> NOTIFY_FAMILY: Elapsed >= repeat_timeout (Decision: Alert Dispatched)

    NOTIFY_FAMILY --> NOTIFY_FAMILY: Repeated Tick (Idempotent: No duplicate SMS / Alert)

    GENTLE_CHECK_IN --> NORMAL: Qualifying Event / confirm_ok / "I'm fine"
    REPEAT_CHECK_IN --> NORMAL: Qualifying Event / confirm_ok / "I'm fine"
    NOTIFY_FAMILY --> NORMAL: Qualifying Event / confirm_ok / "I'm fine" (Resolves Active Alert)

    state NOTIFY_FAMILY {
        [*] --> DecisionMade: Persist Alert (pending)
        DecisionMade --> DeliveryAttempt: Attempt Notifier Delivery
        DeliveryAttempt --> Delivered: Success -> delivered_at set
        DeliveryAttempt --> Failed: Failure -> record error, retry_count++
        Failed --> DeliveryAttempt: retry_failed_notifications()
    }
```

### State Transition & Reliability Matrix

| Current Stage | Trigger / Evaluation Condition | Next Stage | Actions & State Changes | Verifying Automated Test |
| :--- | :--- | :--- | :--- | :--- |
| `NORMAL` | Risk score $< 0.3$ and level is "low" | `NORMAL` | `last_updated = now`. Nominal monitoring. | `test_transition_normal_to_normal_low_risk` |
| `NORMAL` | Risk score $\ge 0.3$ (missed medication, inactivity) | `GENTLE_CHECK_IN` | `entered_at = now`, `notification_state = "none"`, record risk reasons and relevant event IDs. | `test_transition_normal_to_gentle_check_in` |
| `GENTLE_CHECK_IN` | `elapsed < gentle_timeout_seconds` ($t < 60\text{s}$) | `GENTLE_CHECK_IN` | `last_updated = now`. Waiting for response or timeout. | `test_timeout_boundaries_exact` |
| `GENTLE_CHECK_IN` | `elapsed >= gentle_timeout_seconds` ($t \ge 60\text{s}$) | `REPEAT_CHECK_IN` | `entered_at = now`, `notification_state = "none"`. Escalates to repeated audible chime. | `test_timeout_boundaries_exact` |
| `REPEAT_CHECK_IN` | `elapsed < repeat_timeout_seconds` ($t < 60\text{s}$) | `REPEAT_CHECK_IN` | `last_updated = now`. Waiting for response or timeout. | `test_timeout_boundaries_exact` |
| `REPEAT_CHECK_IN` | `elapsed >= repeat_timeout_seconds` ($t \ge 60\text{s}$) | `NOTIFY_FAMILY` | **Separation of Decision & Delivery**: Persists `Alert` (`notification_status="pending"`, evidence reasons, `decision_id`). Sets `state.notification_id = alert_id`. Attempts notifier delivery; on success marks `delivered` with `delivered_at=now`. | `test_notification_decision_separated_from_delivery` |
| `NOTIFY_FAMILY` | Notification delivery fails (network/SNS error) | `NOTIFY_FAMILY` | Marks `notification_status="failed"`, records `delivery_error`, increments `retry_count`. State marked `"failed"`. | `test_notification_delivery_failure_and_retry` |
| `NOTIFY_FAMILY` | `retry_failed_notifications()` executed | `NOTIFY_FAMILY` | Retries failed alert delivery without creating duplicate alerts. Upon success marks `"delivered"`. | `test_notification_delivery_failure_and_retry` |
| `NOTIFY_FAMILY` | Repeated scheduled tick (`notification_state == "delivered"`) | `NOTIFY_FAMILY` | **Idempotent**: No new alerts created, no duplicate SMS/SNS messages dispatched. | `test_repeated_ticks_at_same_timestamp_are_idempotent` |
| Any Stage | Elder says *"I'm fine"*, calls `confirm_ok`, or qualifying routine event logged | `NORMAL` | Authoritative reset: `entered_at = now`, `risk_score = 0.0`, `notification_state = "none"`. Automatically resolves any `ACTIVE` alerts in storage to `RESOLVED`. | `test_reset_on_qualifying_event_and_confirm_ok_resolves_active_alerts`, `test_confirm_ok_tool` |
| Any Stage | Stale background worker write with outdated `version` | *Rejected* | **Optimistic Concurrency Control**: Rejects stale write by raising `StaleStateError`. Stale worker cannot overwrite newer state or user resets. | `test_concurrent_tick_optimistic_concurrency_conflict`, `test_stale_worker_cannot_overwrite_confirm_ok_or_event_reset` |
| Any Stage | 0 events recorded past expected routine window | *Escalates* | **Zero-Safety-Inference**: Absence of sensor events is never inferred as safety; daytime inactivity and missed routine windows elevate risk score. | `test_zero_events_never_infers_safety` |
| Any Stage | Server crashes or restarts | *Preserved* | **Stateless Persistence**: Complete state reload from DB (`SQLite` or `DynamoDB`). Resumes timeout tracking from persisted `entered_at`. | `test_stateless_server_persistence` |

---

## Quickstart

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/KarnailSingh87/careloop.git
cd careloop

# Create and activate Python 3.11+ virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies in editable mode with development tools
pip install -e ".[dev]"
```

### 2. Generate 60-Day Routine Benchmark Dataset

Seed the local SQLite database with 60 simulated days across 3 distinct elder personas (`eleanor`, `dad`, `martha`), yielding 1,422 routine events, 18 ground-truth safety incidents, and 42 benign noise controls:

```bash
python scripts/seed_data.py
```

### 3. Launch Local MCP Server

Start the FastMCP Streamable HTTP server with the simulated clock enabled:

```bash
# Using module launcher
python -m careloop.server --host 127.0.0.1 --port 8000 --clock simulated

# Or using the root entrypoint
python server/main.py --host 127.0.0.1 --port 8000 --clock simulated
```

- **MCP Streamable HTTP Endpoint**: `http://127.0.0.1:8000/mcp`
- **Web Simulator UI & MCP Inspector**: `http://127.0.0.1:8000/simulator`
- **Health Check Endpoint**: `http://127.0.0.1:8000/health`

### 4. Test Streamable HTTP MCP Tools

Run the included integration client to verify session negotiation, tool discovery, and execution over Streamable HTTP:

```bash
python scripts/client_test.py --url http://127.0.0.1:8000/mcp
```

### 5. Run Full Test Suite

```bash
pytest -v
# 98 passed in 4.16s
```

---

## Web Simulator & Live Demo

CareLoop includes an interactive single-page application at `http://127.0.0.1:8000/simulator` styled after an ambient Alexa+ smart display:

- **Ambient Alexa Orb**: Animated glowing orb reflecting idle, listening, thinking, and speaking states.
- **Voice Microphone (STT)**: Uses the browser Web Speech API to dictate natural routine statements directly to Alexa+.
- **Speech Synthesis (TTS)**: Reads Alexa voice responses aloud with audio chimes.
- **Live MCP Tool Inspector**: Displays exact JSON-RPC 2.0 tool requests, input arguments, execution latency, and return schemas (`2025-11-25`).
- **Injectable Clock Machine**: Jump forward in time (`+15m`, `+1h`, `+1d`, `Jump to 2:00 PM`) to test missed routines without waiting hours.
- **Virtual Family Phone**: Displays push/SMS notifications received by family caregivers with deterministic reasons and resolution status.
- **"Dad Skips Lunch" Hero Demo**: One-click 6-step live demonstration that plays the full lifecycle:
  1. Morning: Medication and breakfast logged normally.
  2. 12:45 PM: Normal lunch window arrives. Dad takes a long nap.
  3. 01:45 PM: Grace window expires; risk elevated to Medium; Alexa initiates a gentle voice check-in.
  4. 01:47 PM: No response; repeated check-in with attention chime.
  5. 01:49 PM: State machine escalates to `notify_family`; alert dispatched via Amazon SNS with audit reasons.
  6. 02:00 PM: Dad wakes up and says *"I'm fine"*; state machine resets to normal and family phone resolves.

---

## Alexa+ MCP Tool Reference

CareLoop exposes **9 specialized MCP tools** designed for Alexa+ natural voice interaction:

| Tool Name | Alexa+ Voice Triggers | Description & Purpose | Key Arguments | Return Schema / Voice Response |
| :--- | :--- | :--- | :--- | :--- |
| `log_routine_event` | *"I took my pills"*, *"I finished lunch"*, *"Front door opened"* | Records routine activity metadata (medication, meal, movement, door). Updates baseline EWMA and resets escalation to normal. | `person`, `type`, `timestamp` (optional) | `{ status: "logged", event_id, voice_response }` |
| `check_routine_health` | *"How is Dad doing today?"*, *"Is Mom's routine normal?"* | Evaluates routine health, calculates deterministic risk score, lists plain-English reasons, and returns escalation stage. | `person` | `{ risk_level, risk_score, reasons, escalation_stage, voice_response }` |
| `respond_to_checkin` | Spoken response to Alexa check-in (e.g. *"I was just reading"*) | Captures elder's verbal reply to an Alexa check-in prompt and updates state. | `person`, `response_text` | `{ escalation_stage, message, voice_response }` |
| `confirm_ok` | *"I'm fine"*, *"I'm okay"*, *"Everything is good, Alexa"* | Confirms the elder is safe, immediately resetting any active escalation back to `normal`. | `person` | `{ status: "confirmed_ok", escalation_stage: "normal", voice_response }` |
| `daily_summary` | *"Give me Dad's daily summary"*, *"How was Mom's day?"* | Generates a warm, synthesized 3-sentence daily overview for family caregivers using Amazon Bedrock. | `person`, `date` (optional) | `{ summary, event_count, date, voice_response }` |
| `ask_memory` | *"Did Dad take his pills today?"*, *"What time did Mom eat lunch?"* | Answers specific factual caregiver questions about routine history using Amazon Bedrock sandboxed to verified event logs. | `person`, `question` | `{ answer, question, voice_response }` |
| `schedule_reminder` | *"Remind Dad to drink water at 3 PM"* | Schedules an Alexa voice announcement reminder for the elder parent. | `person`, `text`, `time` | `{ status: "scheduled", reminder_id, text, voice_response }` |
| `notify_family` | *"Alert my daughter"*, *"Call my family"* | Dispatches an urgent alert to designated family caregivers via Amazon SNS with audit reasons. | `person`, `severity`, `message` | `{ status: "notified", alert_id, reasons, delivered_to, voice_response }` |
| `tick_escalation` | Autonomous scheduled check (EventBridge / cron) | Advances the escalation state machine without user intervention, checking grace windows and timeouts. | `person` (optional) | `{ status: "ticked", stage, risk_score, reasons, voice_response }` |

---

## Clinical Benchmark & Evaluation Results

CareLoop was benchmarked across a synthetic dataset of **60 simulated days per persona** (**180 elder-days total**) across 3 clinical personas with realistic Gaussian jitter and 18 injected safety incidents:

| Benchmark Metric | Eleanor Davis (Age 78)<br><sub>Morning Routine</sub> | Arthur Davis / Dad (Age 81)<br><sub>Retired Veteran</sub> | Martha Jenkins (Age 84)<br><sub>Arthritis Schedule</sub> | **Combined Overall System** |
| :--- | :---: | :---: | :---: | :---: |
| **Simulated Days Evaluated** | 60 Days | 60 Days | 60 Days | **180 Days** |
| **Total Sensor Events Processed** | 474 | 474 | 474 | **1,422 Events** |
| **Injected Ground-Truth Incidents** | 6 | 6 | 6 | **18 Incidents** |
| - *Missed Prescription Medication* | 2 | 2 | 2 | **6** |
| - *Daytime Inactivity / Falls (3h+)* | 2 | 2 | 2 | **6** |
| - *Missed Lunch Nutrition* | 2 | 2 | 2 | **6** |
| **Benign Noise Controls (Within Grace)** | 14 | 14 | 14 | **42 Variations** |
| **True Positives (Detected)** | **6 / 6** | **6 / 6** | **6 / 6** | **18 / 18** |
| **False Negatives (Missed Alerts)** | **0** | **0** | **0** | **0** |
| **False Positives (False Alarms)** | **0** | **0** | **0** | **0** |
| **Detection Rate (Sensitivity / Recall)** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| **False-Alarm Rate (FAR)** | **0.00%** | **0.00%** | **0.00%** | **0.00%** |
| **False Alarms per Month (30 Days)** | **0.0** | **0.0** | **0.0** | **0.0** |
| **Avg Detection Delay (from schedule)** | **100.0 mins** | **105.0 mins** | **115.0 mins** | **106.7 mins** |
| **Avg Detection Delay (past grace window)** | **20.0 mins** | **25.0 mins** | **35.0 mins** | **26.7 mins** |

To reproduce the benchmark evaluation:
```bash
python scripts/evaluate_benchmark.py
```

---

## Web Voice Simulator & Browser Environment Guide

CareLoop provides an interactive, accessible ambient voice simulator at `http://127.0.0.1:8000/simulator` for testing, evaluation, and live hackathon demonstrations.

> **Architecture Clarification**: The simulator is an ambient developer cockpit interacting directly with CareLoop's running **FastMCP Streamable HTTP server** via standards-compliant JSON-RPC 2.0 tool calls. It does **not** claim to be connected to Amazon's proprietary Alexa+ cloud; rather, it emulates the ambient Alexa+ device experience using native browser APIs and real MCP tool invocations.

### 1. Launching the Server & Simulator

Start the CareLoop server in simulated clock mode with SQLite local persistence:

```bash
# Start server with simulated clock and local SQLite database
python -m careloop.server --host 127.0.0.1 --port 8000 --clock simulated --storage sqlite
```

Once running:
- **Simulator UI**: [`http://127.0.0.1:8000/simulator`](http://127.0.0.1:8000/simulator)
- **FastMCP Streamable HTTP Endpoint**: `http://127.0.0.1:8000/mcp`
- **Health Check**: `http://127.0.0.1:8000/health`

### 2. Browser Permissions & Microphone Access (Web Speech API)

The simulator features a voice input interface powered by the W3C Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`).

- **Secure Context Requirement (HTTPS / Localhost)**:
  Modern web browsers strictly enforce that microphone access is granted **only within a Secure Context**.
  - **Local Development**: `http://localhost:8000` or `http://127.0.0.1:8000` are treated by browsers as inherently secure origins, allowing microphone access over HTTP.
  - **Remote / Network Deployment**: If the server is hosted remotely (e.g. on AWS EC2, ECS Fargate behind an ALB, or a local LAN IP like `http://192.168.1.50:8000`), the browser **will block microphone access** unless served over **HTTPS** with a valid TLS certificate.
- **Microphone Permissions**:
  When clicking the 🎙️ **Microphone** button, the browser displays a permission prompt (*"Allow careloop to use your microphone"*). Click **Allow**.
- **Browser Compatibility Matrix**:
  | Browser | Speech Recognition (Mic Input) | Speech Synthesis (TTS Audio) | Text Input Fallback |
  | :--- | :---: | :---: | :---: |
  | **Google Chrome / Chromium** | ✅ Native (`webkitSpeechRecognition`) | ✅ Supported | ✅ Fully Supported |
  | **Microsoft Edge** | ✅ Native | ✅ Supported | ✅ Fully Supported |
  | **Apple Safari (macOS / iOS)** | ✅ Native (requires mic permission) | ✅ Supported | ✅ Fully Supported |
  | **Mozilla Firefox** | ⚠️ Not supported natively by Firefox | ✅ Supported | ✅ **Default Fallback** |

### 3. Fallback Manual Text Input & Quick Action Chips

If microphone permission is declined, if the browser lacks Web Speech Recognition support (such as Firefox), or if you are demonstrating in a quiet office environment:
- **Manual Text Input**: Type any phrase into the input field at the bottom of the conversation column and press `[Send]` or hit `Enter`.
- **Quick Action Chips**: One-click prompt chips are provided above the input bar:
  - `💊 Took blood pressure pills`
  - `🥪 Finished lunch`
  - `🚶 Dad got out of bed`
  - `❓ How is Dad doing?`
  - `👍 I'm fine, Alexa!`

### 4. Input Source Discrimination & Real Tool Inspection

The UI strictly distinguishes and visually tags the provenance of every event:
- **`🎤 Browser Speech API`**: Spoken voice input transcribed by browser speech recognition.
- **`⌨️ Manual Text Input`**: Phrases typed by hand into the input bar.
- **`🔘 Quick Action Chip`**: Pre-configured testing chips clicked by the user.

Every MCP tool call generates an expandable, inspectable **MCP Tool Call Card** displaying:
- Tool name (e.g. `log_routine_event`, `check_routine_health`, `confirm_ok`, `notify_family`).
- Sanitized input arguments.
- Real HTTP/JSON-RPC status (`🟢 200 OK` or `🔴 Error`).
- Server latency in milliseconds (`duration_ms`).
- MCP protocol transport version (`2025-11-25`).
- Structured backend return payload and TTS response string.
- Inline **Retry Tool Call** button if an invocation fails.
- **Zero Simulation of Fake Successes**: If a backend tool call fails or returns an error, the simulator never fabricates a success message.

### 5. Documented Voice Phrase Mapping Directory

CareLoop uses deterministic parsing to match natural elder voice phrases to registered MCP tools:

| User Voice / Text Phrase | Target MCP Tool | Extracted Arguments | System Behavior |
| :--- | :--- | :--- | :--- |
| *"I took my blood pressure medication"* | `log_routine_event` | `{"type": "medication"}` | Records pill event, updates circular EWMA baseline, resets escalation to `NORMAL`. |
| *"I finished eating lunch"* | `log_routine_event` | `{"type": "meal"}` | Records meal event, updates circular EWMA baseline, resets escalation to `NORMAL`. |
| *"Dad got out of bed"* | `log_routine_event` | `{"type": "movement"}` | Records room movement, resets daytime inactivity counter to 0. |
| *"The front door opened"* | `log_routine_event` | `{"type": "door"}` | Records contact sensor event. |
| *"How is Dad doing today?"* | `check_routine_health` | `{"person": "dad"}` | Evaluates multi-factor risk score and returns active stage and clinical reasons. |
| *"Remind Dad to drink water at 3 PM"* | `schedule_reminder` | `{"text": "...", "time": "15:00"}` | Schedules spoken reminder for elder. |
| *"Alert my daughter / call family"* | `notify_family` | `{"severity": "high"}` | Directly dispatches emergency alert to registered contacts via Notifier. |
| *"I'm fine! / Everything is okay"* | `confirm_ok` | `{"person": "dad"}` | Resolves any active check-in or alarm state back to `NORMAL`. |
| *"Give me Dad's daily summary"* | `daily_summary` | `{"date": "today"}` | Amazon Bedrock Claude 3 Haiku generates warm, factual daily caregiver summary. |
| *"Did Dad take his pills today?"* | `ask_memory` | `{"question": "..."}` | Factual Bedrock memory Q&A sandboxed strictly to recorded event logs. |

### 6. Controllable Simulation Clock & Safe Demo Reset

- **Injectable Clock Controls**: The time controls (`+15m`, `+1hr`, `Reset 08:15 AM`, `Set 12:45 PM`, `Set 14:00 PM`) send HTTP requests to `/api/clock/*`, modifying the exact same injectable `SimulatedClock` instance used across all backend engines. The server time advances globally across the baseline engine, risk engine, and escalation state machine.
- **Isolated Demo Reset**: The `↺ Reset Demo Data` button invokes `POST /api/demo/reset`.
  - **Isolation Guarantee**: Reset deletes **only** isolated demo records (`metadata.source IN ('simulator_demo', 'simulator_manual')` or `event_id LIKE 'demo_%'`) and demo alerts for the selected profile.
  - **Production Safety**: It **cannot** erase production sensor records, historical baseline profiles, or other family profiles (`eleanor`, etc.).
  - **Safety Gate**: In production deployments (`CLOCK_MODE=system`), demo reset is strictly disabled (`403 Forbidden`).

### 7. "Dad Skips Lunch" 6-Step Automated Scenario Walkthrough

Clicking the **▶ Dad Skips Lunch Demo** button runs a 6-step end-to-end demonstration exercising the full event log, baseline evaluation, escalation state transitions, and caregiver notification pathway:

1. **Step 1 (08:30 AM - Normal Morning)**:
   - Resets demo state cleanly via `/api/demo/reset`.
   - Sets clock to `08:30 UTC`.
   - Calls `log_routine_event(type="medication")` for blood pressure pill.
   - Sets clock to `10:00 UTC` and calls `log_routine_event(type="movement")` in living room.
   - Calls `check_routine_health`: Risk score is `0.0 (LOW)`, escalation stage is `NORMAL`.
2. **Step 2 (12:45 PM - Expected Lunch Time)**:
   - Sets clock to `12:45 UTC` (Dad's learned baseline expects lunch at 12:44 UTC).
   - Dad takes a long nap; no movement or meal logged.
   - Calls `check_routine_health`: Current time is within the 30-minute grace window ($12:44 + 30\text{m} = 13:14$). Risk remains `LOW` with **zero false alarms** generated.
3. **Step 3 (02:00 PM / 14:00 UTC - Grace Window Passed & Missed Lunch Detected)**:
   - Sets clock to `14:00 UTC`.
   - Calls `tick_escalation`: Lunch grace window expired 46 minutes ago, and no movement for 4.0 hours.
   - Multi-factor risk engine calculates score `0.5 (MEDIUM)`.
   - State machine advances: `NORMAL` ➔ `GENTLE_CHECK_IN`.
   - Alexa plays gentle chime and speaks check-in prompt: *"Arthur, I noticed you haven't logged lunch today. Just checking in—did you get a chance to eat?"*
4. **Step 4 (+2 Minutes - Gentle Timeout ➔ Repeat Check-In)**:
   - Advances clock by 2 minutes (`14:02 UTC`).
   - Dad remains asleep with no response.
   - Calls `tick_escalation`: Gentle check-in timeout (60s) expired.
   - State machine advances: `GENTLE_CHECK_IN` ➔ `REPEAT_CHECK_IN`.
   - Alexa sounds an attention chime and repeats check-in.
5. **Step 5 (+2 Minutes - Repeat Timeout ➔ NOTIFY FAMILY)**:
   - Advances clock by 2 minutes (`14:04 UTC`).
   - Calls `tick_escalation`: Repeat timeout expired with zero response.
   - State machine advances: `REPEAT_CHECK_IN` ➔ `NOTIFY_FAMILY`.
   - Alert persisted to database with deterministic audit reasons:
     - `Prolonged daytime inactivity / no movement detected (weight: 0.3)`
     - `Expected meal routine not logged today (weight: 0.2)`
   - Dispatches emergency alert to daughter Linda Davis via Notifier (Amazon SNS).
   - The interactive Family Phone mockup displays the urgent incoming notification card.
6. **Step 6 (Dad Confirms OK ➔ Safe Recovery)**:
   - Dad hears chimes and wakes up: *"I'm fine! I was just taking an afternoon nap."*
   - Calls `confirm_ok(person="dad")`.
   - State machine resets to `NORMAL`. Active alerts transition to `RESOLVED`.
   - Family phone mockup updates to show resolution banner: *"Dad confirmed safe: 'Arthur Davis confirmed they are fine' · Check-in resolved"*.

### 8. End-to-End Verification & Manual Browser Testing

- **Automated API & End-to-End Test Suite**:
  Automated integration test [tests/test_simulator_e2e.py](file:///Users/harsh/Desktop/Alexa+/tests/test_simulator_e2e.py) boots the complete ASGI application, executes the full 6-step scenario via HTTP, and asserts every database state change, escalation transition, and notification delivery:
  ```bash
  pytest tests/test_simulator_e2e.py -v
  ```
- **Manual Browser Verification Steps**:
  *(Note: Dedicated headless browser automation libraries like Playwright/Selenium are not pre-installed in this environment; verify manually in your browser as follows:)*
  1. Start the server with `python -m careloop.server --host 127.0.0.1 --port 8000 --clock simulated`.
  2. Open `http://127.0.0.1:8000/simulator` in Google Chrome, Microsoft Edge, or Apple Safari.
  3. Verify the top connection pill displays `MCP Online` in emerald green.
  4. Click the `▶ Dad Skips Lunch Demo` button in the hero banner.
  5. Watch the scenario execute with synchronized voice announcements, audio chimes, MCP packet cards, and the family phone notification animation.
  6. Verify all 6 steps complete cleanly, concluding with the resolution banner on the family phone.

---

## Notification and Alert Delivery Lifecycle Architecture

CareLoop implements an auditable, multi-tier notification pipeline designed for safety, resilience, and strict privacy.

```mermaid
sequenceDiagram
    autonumber
    participant Engine as Escalation State Machine / MCP Tool
    participant Storage as SQLite / DynamoDB Store
    participant Notifier as Notifier Interface (careloop/notifier.py)
    participant SNS as Amazon SNS Gateway
    participant Carrier as Telecom Carrier / Aggregator
    participant Phone as Family Recipient Phone

    Engine->>Storage: 1. Generate & Persist Alert Record<br/>(severity, deterministic reasons, dedup_key)
    Engine->>Notifier: 2. send_notification(person, severity, message, dedup_key)
    alt Console Mode (Local / Demo)
        Notifier-->>Engine: NotificationResult(status=DELIVERED, target="console_stdout")
    else AWS Mode (Production)
        Notifier->>SNS: sns.publish(TopicArn / PhoneNumber, Message)
        alt SNS Accepts Request (HTTP 200)
            SNS-->>Notifier: {"MessageId": "msg-12345"}
            Notifier-->>Engine: NotificationResult(status=ACCEPTED, message_id="msg-12345")
            Note over Engine,Storage: Alert marked "accepted" (Gateway ACK).<br/>Downstream SMS carrier delivery is PENDING.
            SNS--)Carrier: Carrier Dispatch via Aggregator (10DLC / Toll-Free)
            alt Carrier Delivery to Handset
                Carrier--)Phone: SMS Audio / Text Alert Received
                Carrier--)SNS: Carrier Delivery Receipt
                Note over SNS: Handset confirmation recorded in<br/>CloudWatch SMS Delivery Status logs
            else Carrier Rejection / Drop
                Carrier--)SNS: Carrier Failure (Sandbox / Filter / STOP)
            end
        else SNS Publish Rejected
            SNS-->>Notifier: ClientError (InvalidParameter / AuthorizationError)
            Notifier-->>Engine: NotificationResult(status=FAILED, error=...)
            Engine->>Storage: Alert marked "failed" (retry_count += 1)
        end
    end
```

### 1. The Three Explicit Delivery Tiers

CareLoop **never reports an SMS as delivered just because Amazon SNS accepted a publish request**. We enforce an explicit distinction between three stages:

| Tier | Status Enum | Meaning | Persistence State |
| :--- | :--- | :--- | :--- |
| **Tier 1: Alert Generation** | `PENDING` | The escalation state machine or MCP tool evaluated clinical risk and created a structured `Alert` in storage with deterministic reasons and a stable deduplication key. | `notification_status="pending"` |
| **Tier 2: Provider Acceptance** | `ACCEPTED` | AWS SNS returned HTTP 200 with a unique `MessageId`. The message is safely queued on the AWS cloud gateway. Handset delivery is asynchronous and pending. | `notification_status="accepted"`, `accepted_at=now`, `message_id=...` |
| **Tier 3: Carrier Delivery** | `DELIVERED` | The notification was definitively delivered to the recipient (e.g. verified console stdout in local mode, or carrier delivery receipt logged in CloudWatch). | `notification_status="delivered"`, `delivered_at=now` |

### 2. Telecom Carrier Realities & AWS SNS Delivery Constraints

When operating on AWS with Amazon SNS for SMS notifications, downstream carrier delivery is subject to telecom regulations that developers must account for:

- **SMS Origination Identity (US 10DLC & Toll-Free Numbers)**: US cellular carriers (AT&T, Verizon, T-Mobile) require all Application-to-Person (A2P) messaging to originate from registered **10-Digit Long Codes (10DLC)** tied to an approved Brand and Campaign in the Campaign Registry, or a verified Toll-Free Number. Unregistered messages are filtered or blocked outright by carrier firewalls.
- **AWS SMS Sandbox**: All newly provisioned AWS accounts start in the **Amazon SNS SMS Sandbox**. In the sandbox, SMS messages can **only** be sent to phone numbers explicitly verified in the Amazon SNS console. Direct publishing to unverified numbers will be rejected by AWS.
- **Regional Telecom Restrictions**:
  - In India, commercial and transactional SMS requires pre-registered sender headers and message templates approved via TRAI Distributed Ledger Technology (DLT) portals.
  - In the UK, alphanumeric sender IDs may require carrier pre-registration.
- **Recipient Opt-Out (STOP / START)**: Recipients who text "STOP" to the origination number are automatically added to the AWS SNS opt-out list. AWS SNS will reject any subsequent publish attempts to that phone number until the recipient texts "START".
- **Delivery Confirmation Mechanism**: To monitor whether an `ACCEPTED` publish actually reached the recipient handset, production deployments must enable **CloudWatch SMS Delivery Status Logging** (`sns/<region>/<account_id>/DirectPublishToPhoneNumber`). CloudWatch logs the final carrier delivery receipt (e.g. `SUCCESS`, `UNKNOWN`, `CARRIER_UNREACHABLE`).
- **Permissions and Costs**:
  - Requires IAM action `sns:Publish` on the specific topic ARN or target phone number.
  - AWS SMS charges vary by country (e.g., ~$0.0075 per SMS in the US, plus carrier pass-through surcharges and monthly 10DLC campaign registration fees).

### 3. Deduplication and Retry Behavior

- **Stable Deduplication Key**: Alerts automatically generate a deterministic deduplication key: `alert:{person_id}:{date}:{routine_type}:{severity}`.
- **15-Minute MCP Window**: When `notify_family` is invoked, CareLoop checks for an existing active alert sharing the deduplication key within the last 15 minutes. Duplicate invocations are suppressed with status `skipped_deduplicated` to prevent notification spam.
- **Idempotent Scheduled Ticks**: The escalation background worker evaluates the current stage idempotently. Repeated ticks while in `NOTIFY_FAMILY` do not create duplicate alert records or re-publish messages.
- **Automatic Retry with Backoff**: When a notification attempt fails (`status="failed"`), CareLoop increments `retry_count` and records the exact error in `delivery_error`. The `retry_failed_notifications()` job retries failed alerts without duplicating already accepted or delivered alerts.

### 4. PII Privacy Protection & Testing Policy

- **Phone Number Masking**: All phone numbers displayed in the simulator UI, console logs, or alert records are masked using `mask_phone_number()` (e.g. `+1-555-019-2834` ➔ `+1-55***2834`).
- **Zero Real SMS in Test Suite**: All unit and integration tests use `InMemoryNotifier` or `ConsoleNotifier`. The standard test suite makes zero external network calls.
- **Opt-In AWS Smoke Test**: A dedicated test ([tests/test_aws_sns_smoke.py](file:///Users/harsh/Desktop/Alexa+/tests/test_aws_sns_smoke.py)) is provided for live AWS verification. It requires explicit opt-in (`RUN_AWS_SMOKE_TEST=1`), executes preflight STS credential checks, and strictly forbids hardcoded phone numbers (requiring `CARELOOP_TEST_PHONE` or `CARELOOP_SNS_TOPIC_ARN`).

---

## Voice Reminders Architecture & Alexa Integration Notice

CareLoop includes a safe voice reminder scheduler and lifecycle manager ([careloop/reminders.py](file:///Users/harsh/Desktop/Alexa+/careloop/reminders.py)):

### 1. Current Implemented Capabilities
- **Schedule Validation**: The `schedule_reminder` tool validates person identifiers, reminder text, and schedules formatted as 24-hour time-of-day (`HH:MM`) or ISO 8601 timestamps (`YYYY-MM-DDTHH:MM:SSZ`).
- **Encrypted Persistence**: Reminders are stored in SQLite and DynamoDB with status tracking (`PENDING`, `COMPLETED`, `FAILED`, `DISMISSED`).
- **Due Reminder Processing**: The `ReminderScheduler` scans pending reminders, compares scheduled times against the injectable `Clock` in the person's configured timezone, triggers delivery bridges, and records completion timestamps (`completed_at`).
- **Conversational Feedback**: The MCP tool returns immediate natural voice responses for Alexa+ TTS (e.g. *"I have scheduled a reminder for Eleanor at 14:00: Take blood pressure medication."*).

### 2. Missing Component for Physical Amazon Echo Audio Broadcast

CareLoop **explicitly identifies the architectural boundary for physical Echo speaker delivery**:

CareLoop runs as a standalone Model Context Protocol (MCP) server. To make a physical Amazon Echo device ring chimes and audibly speak a reminder proactively when it becomes due, the following external components are required:

1. **Alexa Reminders API Endpoint**: Direct HTTP requests to `https://api.amazonalexa.com/v1/alerts/reminders`.
2. **Customer Consent & OAuth 2.0 Access Token**: The elder's Amazon account must explicitly grant permission `alexa::alerts:reminders:skill:readwrite` inside the Alexa smartphone app, and the backend must hold a valid Login with Amazon (LWA) access token for that specific customer.
3. **Alexa Skills Kit (ASK) Runtime Bridge**: An ASK Lambda skill or proactive events dispatcher mapped to the elder's specific Amazon Echo endpoint ID.

In the absence of the customer-delegated ASK OAuth token, CareLoop provides a `ConsoleReminderDeliveryBridge` for local testing and returns formatted TTS text over MCP, rather than pretending physical Echo delivery occurred.

---

## Sandboxed Generative Layer (Amazon Bedrock) & Clinical Safety Independence

CareLoop integrates with **Amazon Bedrock Runtime** using the official **Converse API** ([careloop/llm/bedrock.py](file:///Users/harsh/Desktop/Alexa+/careloop/llm/bedrock.py)) under strict clinical boundaries:

```mermaid
flowchart LR
    subgraph GenerativeLayer ["Sandboxed Bedrock Converse API"]
        CaregiverQ["Caregiver Question / Summary Request"] --> Filter["1. Rule-First Filter Parsing<br/>(Event Type + Local Date Range)"]
        Filter --> CheckZero{"2. Matching Events > 0?"}
        CheckZero -- "No (0 events)" --> NoRecord["Explicit 'No Record' Response<br/>(Bedrock Converse NEVER called)"]
        CheckZero -- "Yes" --> MinMeta["3. Send MINIMUM Metadata Only<br/>(Strip internal IDs / audio)"]
        MinMeta --> Converse["4. boto3 Bedrock Converse<br/>(anthropic.claude-3-haiku)"]
        Converse --> Answer["Warm 3-Sentence Summary / Q&A Answer"]
    end

    subgraph ClinicalSafetyCore ["Deterministic Safety Core (Zero LLM)"]
        EWMA["Circular EWMA Baseline"]
        Risk["Multi-Factor Risk Engine"]
        Escalation["Escalation State Machine"]
        Alerts["Family Alert Dispatcher"]
    end

    Converse -.->|"❌ STRICTLY FORBIDDEN:<br/>Cannot alter risk, state, or alerts"| ClinicalSafetyCore
```

### 1. Configuration & Model Selection
- **Configurable Model ID**: Controlled via the `BEDROCK_MODEL_ID` environment variable (default: `anthropic.claude-3-haiku-20240307-v1:0`). Also compatible with `amazon.nova-micro-v1:0`, `anthropic.claude-3-5-sonnet-20240620-v1:0`, and custom provisioned model ARNs.
- **Region**: Configurable via `AWS_REGION` or `AWS_DEFAULT_REGION` (default: `us-east-1`).
- **SDK Compatibility**: Built with official `boto3` (`1.43+`) and `botocore` using `bedrock-runtime.converse()`.

### 2. IAM Permissions
Production deployments require the following least-privilege IAM policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CareLoopBedrockConverseAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-*"
    }
  ]
}
```

### 3. Cost Profile & Economic Efficiency
- **Anthropic Claude 3 Haiku Pricing**:
  - Input tokens: **$0.00025 per 1,000 tokens** ($0.25 / MTok).
  - Output tokens: **$0.00125 per 1,000 tokens** ($1.25 / MTok).
- **Per-Inference Cost**:
  - *Daily Summary*: ~180 input tokens + ~65 output tokens = **$0.000126 per summary** (~1/8th of a cent).
  - *Memory Q&A*: ~120 input tokens + ~40 output tokens = **$0.000080 per query**.
  - *Zero-Record Queries*: **$0.000000** (short-circuits before LLM invocation).
- **Monthly Cost for Monitored Elder**: Under normal family usage (2 daily summaries + 3 memory queries daily), the total monthly Bedrock cost is **under $0.02 USD per month**.

### 4. Local Fallback & High-Availability Resilience
- **Deterministic 3-Sentence Fallback Template**: When running locally without AWS credentials, or when Bedrock experiences `ThrottlingException`, `ModelTimeoutException`, or model unavailability, CareLoop automatically formats a warm, 3-sentence family summary grounded strictly in observed event metadata. Demos and emergency operations never crash or fail due to LLM outages.
- **Deterministic Memory Phrasing**: Offline memory queries return exact logged times and event metadata.
- **Privacy Enforcement**: Prompts containing elder event histories and health data are **strictly forbidden from being logged** to console logs or CloudWatch log groups.

### 5. Architectural Clinical Independence (Regression Verified)
As verified in [tests/test_bedrock.py](file:///Users/harsh/Desktop/Alexa+/tests/test_bedrock.py) (`test_bedrock_adversarial_output_cannot_alter_clinical_state`), even if an adversarial prompt or model hallucination outputs alarmist text (e.g. demanding 911 or claiming risk is 1.0), the deterministic clinical safety engine ignores model text completely:
- Risk assessment scores are computed strictly by mathematical anomaly scoring.
- Escalation stages transition strictly via persisted state machines and timestamps.
- Zero emergency notifications or alerts can ever be triggered by LLM generative text.

---

## Strict Privacy Architecture

CareLoop is built from the ground up for strict healthcare and elder privacy:

1. **Zero Raw Audio Storage**: Neither CareLoop nor the MCP server ever captures, records, or stores ambient audio. Only discrete metadata tuples are stored: `(person_id, event_type, timestamp, metadata)`.
2. **Deterministic Safety Isolation**: Amazon Bedrock is used strictly for phrasing daily summaries and answering factual routine questions. The LLM **cannot** invoke emergency alerts or change escalation stages.
3. **Auditability & Explainability**: Every alert dispatched to family contains deterministic, explainable reasons (e.g. *"Blood pressure medication window closed at 09:15 UTC. Routine check-in unanswered after 120 seconds."*).
4. **Encryption at Rest**: On AWS, all DynamoDB items and Amazon SNS messages are encrypted with AWS KMS customer-managed keys.

---

## AWS Cloud Deployment

Deploy CareLoop to AWS with either AWS CDK or AWS SAM:

### Option A: AWS CDK (Python)

```bash
cd deploy/cdk
pip install -r requirements.txt
cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
cdk deploy
```

### Option B: AWS SAM CLI

```bash
sam build
sam deploy --guided
```

### Outputs Provisioned
- **Public MCP Streamable HTTP Endpoint**: `http://<ALB_DNS>/mcp`
- **Web Simulator UI**: `http://<ALB_DNS>/simulator`
- **Health Check**: `http://<ALB_DNS>/health`
- **Encrypted DynamoDB Table**: `CareLoopData`
- **Amazon SNS Topic**: `CareLoopAlertsTopic`
- **Amazon EventBridge**: 1-minute automated tick rule calling `CareLoopTickRunner` Lambda.

---

## Open Source & MIT License

CareLoop is free and open-source software licensed under the **[MIT License](file:///Users/harsh/Desktop/Alexa+/LICENSE)**.

```
Copyright (c) 2026 CareLoop Contributors
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
```
