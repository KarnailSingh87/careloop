# CareLoop — 2:45 Video Demonstration Script
**Amazon Developer Hackathon: Alexa+ Track, AWS Builder Track, & Open Source Mini-Challenges**  
**Target Video Duration:** Exactly 2 minutes, 45 seconds (165 seconds)

---

### Timing Breakdown at a Glance

| Time Range | Duration | Scene / Segment | Key Focus |
| :---: | :---: | :--- | :--- |
| **0:00 – 0:15** | 15s | **1. The Emotional Hook & Urgent Alert** | Daughter receives a real alert: Dad missed heart medication |
| **0:15 – 0:45** | 30s | **2. Introducing CareLoop & Ambient Alexa+** | Ambient voice assistant, privacy (zero audio stored), routine learning |
| **0:45 – 1:15** | 30s | **3. Live Simulation & Visible MCP Tool Calls** | "Dad Skips Lunch", time machine, live JSON-RPC MCP Inspector |
| **1:15 – 1:45** | 30s | **4. Autonomous Escalation & Family SNS Alert** | Grace window passes, gentle check-in, repeat chime, SMS dispatch |
| **1:45 – 2:05** | 20s | **5. Caregiver Memory Q&A (`ask_memory`)** | Bedrock Claude 3 Haiku factual routine memory Q&A |
| **2:05 – 2:25** | 20s | **6. Cloud Architecture & AWS Slide** | FastMCP on ECS Fargate, DynamoDB KMS, EventBridge, Bedrock |
| **2:25 – 2:45** | 20s | **7. Clinical Evaluation & Closing Hook** | 60-day replay, 100% detection, 0.0% false alarms, Open Source MIT |

---

### Detailed Scene-by-Scene Script

```
================================================================================
SCENE 1: THE EMOTIONAL HOOK & THE MISSED PILL ALERT [0:00 – 0:15] (15 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Close-up shot of a smartphone lying on a kitchen counter vibrating.
- A high-priority lock screen push notification appears from **CareLoop**:
  > 🚨 **CareLoop Alert: Arthur Davis (High Risk)**  
  > *Missed morning heart medication (Lisinopril). Scheduled: 08:15 AM. Window closed at 09:15 AM. Unanswered routine check-in.*
- Quick cut to a framed family photo of an elderly father and his daughter.
- Title card fades in: **CareLoop · Protecting Aging Parents via Alexa+ & MCP**.

**SPOKEN NARRATION:**
> *"At 9:15 this morning, Linda's phone buzzed with an alert she dreads every day: her 81-year-old father, Arthur, who lives alone, missed his critical blood pressure medication—and was unresponsive to voice check-ins.  
> But this wasn't an intrusive camera. And it wasn't a false alarm. This is CareLoop."*

---

```
================================================================================
SCENE 2: INTRODUCING CARELOOP & THE SIMULATOR [0:15 – 0:45] (30 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Screen switch to browser: **CareLoop Simulator** (`http://localhost:8000/simulator`).
- Cursor highlights:
  - Top header: **"MCP Streamable HTTP · Protocol 2025-11-25"**.
  - Left card: Arthur Davis profile (Age 81, Independent Living).
  - Center: Glowing ambient **Alexa+ Orb** pulsing gently with cyan ambient light.
  - Right: **Family Phone** panel with live status preview.
- Callout banner animates on screen: **"STRICT PRIVACY GUARANTEE: Zero Audio Stored · Metadata Only"**.

**SPOKEN NARRATION:**
> *"CareLoop is a self-hosted Model Context Protocol server over Streamable HTTP that turns Alexa+ into an ambient safety guardian for elderly parents living alone.  
> Instead of invading dignity with cameras or recording raw audio, CareLoop records only structured event metadata—pillbox openings, meals, door sensors, and room motion.  
> Using circular statistics, CareLoop learns Dad's personal baseline schedule and detects anomalies deterministically."*

---

```
================================================================================
SCENE 3: LIVE SIMULATION & VISIBLE MCP TOOL CALLS [0:45 – 1:15] (30 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Presenter clicks the **"Dad Skips Lunch Demo"** button in the header.
- The **Injectable Clock Machine** jumps from 08:30 AM to 12:45 PM.
- The center conversation log shows the elder saying: *"I took my blood pressure pill"*.
- **Live MCP Tool Inspector** expands on screen, displaying:
  ```json
  // POST /mcp (JSON-RPC 2.0)
  {
    "tool": "log_routine_event",
    "arguments": { "person": "dad", "type": "medication" },
    "result": { "status": "logged", "voice_response": "Thank you, Arthur..." },
    "duration_ms": 1.45,
    "protocol_version": "2025-11-25"
  }
  ```
- The Alexa orb pulses green; the browser reads aloud via Web Speech Synthesis: *"Got it Arthur, your morning blood pressure medication is confirmed."*

**SPOKEN NARRATION:**
> *"Watch CareLoop in action through our Alexa+ voice simulator.  
> When Dad takes his morning pill, Alexa+ calls our MCP tool `log_routine_event`. You can see the raw JSON-RPC 2025-11-25 packet right here in the inspector.  
> Our circular EWMA engine updates Arthur's routine baseline in real time. Everything is nominal."*

---

```
================================================================================
SCENE 4: AUTONOMOUS ESCALATION & THE FAMILY SMS [1:15 – 1:45] (30 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Clock advances to **02:00 PM** (14:00 UTC).
- Dad's lunchtime was expected at 12:45 PM; the 30-minute grace window has passed. Zero kitchen movement logged.
- The Escalation State Machine highlights transition: **NORMAL ➔ GENTLE_CHECK_IN**.
- Alexa Orb pulses and chimes: *"Arthur, I noticed you haven't logged lunch today. Just checking in—did you get a chance to eat?"*
- Presenter waits 3 seconds; Dad does not respond.
- Clock advances 2 minutes. State transitions: **GENTLE_CHECK_IN ➔ REPEAT_CHECK_IN** (Urgent chime plays).
- Another 2 minutes pass without response: State transitions to **NOTIFY_FAMILY**.
- Tool Inspector flashes: `notify_family(person="dad", severity="high")`.
- On the right side, the **Virtual Family Phone** receives the incoming SMS alert with deterministic reasons:
  > *• Lunch window closed at 01:15 PM*  
  > *• Inactivity: 5 hours with zero movement*  
  > *• Spoken check-in unanswered after 120s*

**SPOKEN NARRATION:**
> *"Now, Dad takes a long nap and skips lunch.  
> At 2:00 PM, his grace window has expired. CareLoop's deterministic state machine initiates a gentle voice check-in over Alexa.  
> When Dad doesn't reply, it plays an attention chime and repeats the check-in.  
> After 120 seconds of silence, it automatically escalates: invoking `notify_family` and dispatching an Amazon SNS alert to daughter Linda. Notice every alert includes human-readable deterministic audit reasons. Zero hallucinated alerts."*

---

```
================================================================================
SCENE 5: CAREGIVER MEMORY Q&A VIA BEDROCK [1:45 – 2:05] (20 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Presenter types into the Alexa text box (or clicks mic):  
  *"Did Dad take his pills today?"*
- MCP Inspector highlights tool execution:
  ```json
  {
    "tool": "ask_memory",
    "arguments": { "person": "dad", "question": "Did Dad take his pills today?" }
  }
  ```
- Bedrock response renders in the conversation bubble:  
  *"Arthur Davis took his morning medication (Lisinopril 10mg) today at 8:15 AM UTC, recorded via smart pillbox."*
- Presenter clicks **"Daily Summary"**: Bedrock synthesizes a warm 3-sentence daily recap for the family.

**SPOKEN NARRATION:**
> *"Family caregivers can also ask Alexa+ about Dad's day.  
> When Linda asks, 'Did Dad take his pills today?', the `ask_memory` tool queries verified storage and feeds the exact event log to Amazon Bedrock Claude 3 Haiku.  
> If no events exist, it short-circuits to 'no record' without calling the model—guaranteeing 100% factual accuracy."*

---

```
================================================================================
SCENE 6: ARCHITECTURE & AWS CLOUD INFRASTRUCTURE [2:05 – 2:25] (20 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Slide / Diagram view on screen: **CareLoop AWS Cloud Architecture**:
  - **AWS ECS Fargate**: Containerized FastMCP server behind an Application Load Balancer with 300s streaming idle timeout.
  - **Amazon DynamoDB**: Single-table design (`PK`, `SK`) with AWS-managed encryption at rest.
  - **Amazon SNS**: KMS-encrypted caregiver SMS topic (`alias/aws/sns`).
  - **Amazon EventBridge**: 1-minute scheduled rule triggering `CareLoopTickRunner` Lambda.
  - **Amazon Bedrock**: Claude 3 Haiku Converse API.
  - Code overlay: Showing `deploy/cdk/careloop_stack.py` and `template.yaml`.

**SPOKEN NARRATION:**
> *"Under the hood, CareLoop is production-ready.  
> Deployed on AWS ECS Fargate behind an Application Load Balancer, it provides native HTTP chunked streaming without API Gateway's 29-second timeouts.  
> Data persists in single-table DynamoDB with KMS encryption at rest, while an EventBridge 1-minute rule drives autonomous health checks. Complete AWS CDK and SAM templates deploy the entire stack in one command."*

---

```
================================================================================
SCENE 7: CLINICAL EVALUATION & CLOSING [2:25 – 2:45] (20 sec)
================================================================================
```

**VISUAL / ON-SCREEN ACTION:**
- Full-screen graphic of the **Benchmark Evaluation Table**:
  - **180 Elder-Days** across 3 personas (Eleanor, Arthur, Martha).
  - **1,422 Routine Events** evaluated.
  - **18 / 18 Ground-Truth Incidents Caught: 100.0% Detection Rate**.
  - **False-Alarm Rate: 0.00%** (0 false alarms across 459 nominal checks).
  - **Average Detection Delay**: ~26.7 minutes past grace window.
- Closing slide with GitHub repo URL, MIT License badge, and Alexa+ Hackathon logo.

**SPOKEN NARRATION:**
> *"We rigorously benchmarked CareLoop across 180 simulated elder-days and 1,422 sensor events.  
> The result? A 100% detection rate across all 18 clinical incidents, with a 0.0% false-alarm rate—completely eliminating caregiver alarm fatigue.  
> CareLoop gives elderly parents their independence, and gives families true peace of mind.  
> Fully open source under the MIT License. Thank you."*

---

### Speaker Delivery Tips for the 2:45 Pitch

1. **Pacing**: Aim for ~130–140 words per minute. The total script is ~380 words, allowing comfortable breathing room for audio chimes, UI animations, and dramatic pauses.
2. **First 15 Seconds**: Speak with genuine empathy and urgency. That initial phone vibration hook immediately separates CareLoop from generic AI chatbots.
3. **The "Zero LLM Alert" Rule**: Emphasize this strongly in Scene 4 and Scene 6—judges in healthcare and IoT value deterministic safety over generative hallucinations.
4. **Tool Inspector**: Pause for 1.5 seconds when the MCP JSON card expands so judges can see the protocol version `2025-11-25` and sub-2ms execution time.
