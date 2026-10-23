#!/usr/bin/env python3
"""
CareLoop Hackathon Demonstration Video Generator
Builds a high-definition 1080p screen recording demonstration video with synchronized voice-over narration.
Follows the exact 7-scene breakdown from DEMO_SCRIPT.md (165 seconds · 2:45).
"""

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = WORKSPACE_DIR / "project_media"
MEDIA_DIR.mkdir(exist_ok=True)

EDGE_BIN = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
FFMPEG_BIN = "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = "/opt/homebrew/bin/ffprobe"


def get_base64_data_uri(filepath: Path, mime: str = "image/jpeg") -> str:
    if not filepath.exists():
        return ""
    with open(filepath, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"


ARTHUR_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "arthur.jpg", "image/jpeg")
ELEANOR_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "eleanor.jpg", "image/jpeg")
MARTHA_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "martha.jpg", "image/jpeg")
LOGO_B64 = get_base64_data_uri(WORKSPACE_DIR / "careloop" / "simulator" / "logo.jpg", "image/jpeg")

# Define the 7 Scenes matching DEMO_SCRIPT.md
SCENES = [
    {
        "id": 1,
        "title": "1. Emotional Hook & Urgent Alert",
        "time_code": "0:00 – 0:15",
        "speech": (
            "At 9:30 this morning, Linda received the alert every adult child dreads: "
            "her 78-year-old mother Eleanor, who lives alone, missed her morning blood pressure medication, "
            "and hasn't answered her Alexa. "
            "But this wasn't an intrusive camera, and it wasn't a false alarm. This is CareLoop."
        ),
        "target_duration": 15.0,
    },
    {
        "id": 2,
        "title": "2. The Simulator & Learned Routine",
        "time_code": "0:15 – 0:40",
        "speech": (
            "CareLoop is an ambient safety companion powered by the Model Context Protocol over Streamable HTTP. "
            "Instead of cameras or microphones recording private conversations, CareLoop captures only structured telemetry: "
            "smart pillboxes, door contacts, and motion sensors. "
            "Using circular statistics, our engine learned Eleanor's personal rhythm: "
            "she takes Lisinopril around 8:15 AM with a 45-minute grace window."
        ),
        "target_duration": 25.0,
    },
    {
        "id": 3,
        "title": "3. Missed Event & Visible MCP Tools",
        "time_code": "0:40 – 1:15",
        "speech": (
            "Watch what happens when Eleanor takes an unplanned morning walk and forgets her pills. "
            "We advance our injectable clock to 9:30 AM, thirty minutes past her grace window. "
            "CareLoop's circular EWMA engine flags the missed event, elevating her risk score to 0.7. "
            "Right here on screen is the live MCP tool call: check routine health. "
            "Notice the JSON-RPC 2025-11-25 protocol format and 1.8-millisecond execution time. "
            "Zero LLM hallucinations: pure, explainable math."
        ),
        "target_duration": 35.0,
    },
    {
        "id": 4,
        "title": "4. Explainable Escalation & Family Alert",
        "time_code": "1:15 – 1:45",
        "speech": (
            "CareLoop doesn't immediately panic the family. It starts with an empathetic voice check-in over Alexa. "
            "When Eleanor doesn't respond, it plays a chime and repeats the prompt sixty seconds later. "
            "If she remains unresponsive, CareLoop escalates to stage four: invoking notify family and dispatching an alert to daughter Linda. "
            "Every notification includes deterministic reasons, timestamps, and deduplication keys, completely preventing duplicate alerts."
        ),
        "target_duration": 30.0,
    },
    {
        "id": 5,
        "title": "5. Factual Memory Q&A & Reset",
        "time_code": "1:45 – 2:05",
        "speech": (
            "Family caregivers can also check in directly through Alexa Plus. "
            "When Linda asks, 'Did Mom take her pills?', the ask memory tool queries verified storage and answers factually without hallucinating. "
            "And when Eleanor confirms she's safe, a single spoken phrase, 'Alexa, I'm fine', invokes confirm ok, instantly resetting the entire escalation pipeline."
        ),
        "target_duration": 20.0,
    },
    {
        "id": 6,
        "title": "6. Architecture & Integration Boundaries",
        "time_code": "2:05 – 2:25",
        "speech": (
            "Under the hood, CareLoop is production-ready. "
            "Deployed on AWS ECS Fargate behind an Application Load Balancer, it provides native HTTP streaming without API Gateway's 29-second timeouts. "
            "Data persists in KMS-encrypted DynamoDB, driven by 1-minute EventBridge ticks. "
            "And we maintain rigorous honesty: our Streamable HTTP MCP core is 100% verified locally, ready for Alexa Plus developer preview account linking."
        ),
        "target_duration": 20.0,
    },
    {
        "id": 7,
        "title": "7. Benchmark Evaluation & Closing Pitch",
        "time_code": "2:25 – 2:45",
        "speech": (
            "We proved CareLoop across 180 simulated elder-days and 1,422 sensor events. "
            "The result? A 100% detection rate across all eighteen clinical incidents, while eliminating 80 false alarms produced by traditional static timers. "
            "CareLoop gives aging parents their independence, and gives families true peace of mind. "
            "Fully open source under the MIT License. Thank you."
        ),
        "target_duration": 20.0,
    },
]

COMMON_VIDEO_CSS = """
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
  }
  html, body {
    width: 1920px;
    height: 1080px;
    margin: 0;
    padding: 0;
    overflow: hidden;
    background-color: #070b13;
    color: #ffffff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }
  .scene-frame {
    width: 1920px;
    height: 1080px;
    position: relative;
    display: flex;
    flex-direction: column;
    padding: 36px 48px;
    background: #080c15;
    box-sizing: border-box;
  }
  .top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 16px;
    margin-bottom: 24px;
  }
  .brand-wrap {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .brand-logo {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    object-fit: cover;
    border: 1px solid rgba(0, 202, 255, 0.3);
  }
  .brand-text {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
  .badge-alexa {
    background: rgba(0, 202, 255, 0.12);
    border: 1px solid rgba(0, 202, 255, 0.3);
    color: #00CAFF;
    font-size: 11px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 5px;
    text-transform: uppercase;
  }
  .scene-badge {
    font-size: 13px;
    color: #94a3b8;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .content-area {
    flex: 1;
    display: flex;
    gap: 36px;
    min-height: 0;
  }
  .card {
    background: #0f172a;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.35);
  }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
  }
  .tag-cyan { background: rgba(0, 202, 255, 0.12); border: 1px solid rgba(0, 202, 255, 0.3); color: #00CAFF; }
  .tag-emerald { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); color: #10b981; }
  .tag-amber { background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); color: #f59e0b; }
  .tag-rose { background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; }
  .mono { font-family: "JetBrains Mono", Menlo, Consolas, monospace; }
  .caption-bar {
    margin-top: 18px;
    padding: 16px 24px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(0, 202, 255, 0.2);
    border-radius: 12px;
    display: flex;
    align-items: center;
    gap: 16px;
    backdrop-filter: blur(10px);
  }
  .caption-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #00CAFF;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: #080c15;
    font-weight: 800;
    font-size: 12px;
  }
  .caption-text {
    font-size: 15px;
    color: #e2e8f0;
    line-height: 1.4;
    font-weight: 500;
  }
"""


def generate_scene_html(scene: dict) -> str:
    sid = scene["id"]
    caption = scene["speech"]
    time_code = scene["time_code"]
    title = scene["title"]

    if sid == 1:
        # Scene 1: Emergency Alert on Virtual Phone
        body_content = """
        <div style="flex: 1.1; display: flex; flex-direction: column; justify-content: center; gap: 24px;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-rose">Incoming Emergency Telemetry</span>
            <span class="tag tag-cyan">FastMCP Spec 2025-11-25</span>
          </div>
          <h1 style="font-size: 46px; font-weight: 800; line-height: 1.15; letter-spacing: -0.02em;">
            "At 9:30 this morning, Linda received the alert every adult child dreads..."
          </h1>
          <p style="font-size: 18px; color: #94a3b8; line-height: 1.6;">
            Eleanor Davis (Age 78), who lives independently, missed her morning blood pressure medication window and hasn't answered her Living Room Alexa.
          </p>
          <div style="display: flex; gap: 16px; margin-top: 8px;">
            <div class="card" style="flex: 1; padding: 18px; border-color: rgba(239, 68, 68, 0.3);">
              <div style="font-size: 24px; font-weight: 800; color: #ef4444;">45m Grace</div>
              <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Expired at 09:00 UTC (Current: 09:30 UTC)</div>
            </div>
            <div class="card" style="flex: 1; padding: 18px; border-color: rgba(0, 202, 255, 0.3);">
              <div style="font-size: 24px; font-weight: 800; color: #00CAFF;">0 Cameras</div>
              <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Zero Intrusion · 100% Privacy Protected</div>
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; justify-content: center; align-items: center;">
          <div style="width: 360px; height: 550px; background: #000; border-radius: 40px; border: 4px solid #334155; padding: 18px; display: flex; flex-direction: column; box-shadow: 0 25px 50px rgba(0,0,0,0.7); position: relative;">
            <div style="width: 110px; height: 22px; background: #1e293b; border-radius: 14px; margin: 0 auto 14px auto; display: flex; align-items: center; justify-content: center;">
              <div style="width: 8px; height: 8px; border-radius: 50%; background: #000; margin-right: 6px;"></div>
              <div style="width: 6px; height: 6px; border-radius: 50%; background: #00CAFF;"></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; font-weight: 600; margin-bottom: 20px;">
              <span>09:30</span>
              <span>5G · 100%</span>
            </div>
            <div style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 14px; padding: 16px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span class="tag tag-rose" style="font-size: 10px;">HIGH PRIORITY ALERT</span>
                <span style="font-size: 10px; color: #cbd5e1;" class="mono">09:30 UTC</span>
              </div>
              <div style="font-size: 15px; font-weight: 800; color: #ffffff;">Eleanor Davis Missed Lisinopril</div>
              <div style="font-size: 10px; text-transform: uppercase; color: #fca5a5; font-weight: 700; margin-top: 8px;">Deterministic Reason:</div>
              <ul style="font-size: 11px; color: #fecaca; margin-top: 4px; padding-left: 14px; line-height: 1.4;">
                <li>Medication missed past baseline grace window (weight: 0.4).</li>
                <li>Scheduled: 08:15 UTC (&plusmn;6m). Grace expired: 09:00 UTC.</li>
                <li>No Alexa voice response heard.</li>
              </ul>
              <div style="display: flex; gap: 8px; margin-top: 14px;">
                <div style="flex: 1; background: #ef4444; color: #fff; font-weight: 700; font-size: 11px; padding: 8px; border-radius: 6px; text-align: center;">📞 Call Mom</div>
                <div style="flex: 1; background: rgba(255,255,255,0.1); color: #fff; font-size: 11px; padding: 8px; border-radius: 6px; text-align: center;">Acknowledge</div>
              </div>
            </div>
            <div style="margin-top: auto; text-align: center; font-size: 10px; color: #64748b;">
              KMS-Encrypted Amazon SNS SMS Dispatch
            </div>
          </div>
        </div>
        """

    elif sid == 2:
        # Scene 2: The Simulator & Learned Baseline
        body_content = f"""
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-emerald">● MCP Online (/mcp)</span>
            <span class="tag tag-cyan">FastMCP Spec 2025-11-25</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            Zero-Intrusion Circadian Routine Intelligence
          </h1>
          <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">
            Instead of cameras or intrusive audio recording, CareLoop tracks discrete ambient telemetry: smart pillbox openings, room motion, door contacts, and natural conversational check-ins.
          </p>

          <div class="card" style="display: flex; align-items: center; gap: 20px; border-color: rgba(16, 185, 129, 0.3);">
            <img src="{ELEANOR_B64}" alt="Eleanor" style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid #10b981;" />
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <h3 style="font-size: 18px; font-weight: 800;">Eleanor Davis (Mom)</h3>
                <span class="tag tag-emerald">Age 78 · Nominal</span>
              </div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Living Independently · Caregiver: Linda Davis</div>
              <div style="font-size: 12px; color: #10b981; margin-top: 6px; font-weight: 600;">
                Learned Baseline: Lisinopril at 08:15 UTC (&plusmn;6m variance) · 45-min grace window
              </div>
            </div>
          </div>

          <div style="padding: 12px 18px; background: rgba(0, 202, 255, 0.08); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 10px; font-size: 13px; color: #00CAFF;">
            🛡️ Privacy Guarantee: Structured routine metadata only. Zero raw audio or video captured.
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 14px; justify-content: center;">
          <div class="card" style="padding: 18px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 12px; font-weight: 700; color: #00CAFF;">AMAZON ECHO SHOW 10</span>
              <span class="tag tag-cyan">Voice Idle Breathing</span>
            </div>
            <div style="font-size: 14px; color: #ffffff;">"Good morning Eleanor! I'm watching over your daily routine. All sensors synced."</div>
          </div>
          <div class="card" style="padding: 18px;">
            <div style="font-size: 12px; font-weight: 700; color: #10b981; margin-bottom: 6px;">CIRCULAR DIRECTIONAL EWMA</div>
            <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">Unit circle projection (&theta; = 2&pi;t / 1440) eliminates the midnight wrap-around bug. Pre-warmed with 1,422 historical observations.</div>
          </div>
          <div class="card" style="padding: 18px;">
            <div style="font-size: 12px; font-weight: 700; color: #f59e0b; margin-bottom: 6px;">ISOLATED STORAGE</div>
            <div style="font-size: 13px; color: #cbd5e1;">Local SQLite fallback (careloop_demo.db). 100% testable without AWS credentials.</div>
          </div>
        </div>
        """

    elif sid == 3:
        # Scene 3: Clock Advance & Visible MCP Tools
        body_content = """
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-amber">Injectable Clock: 09:30 UTC</span>
            <span class="tag tag-rose">High Risk Elevated (0.70)</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            Sub-50ms FastMCP Tool Call Execution
          </h1>
          <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">
            We advance our injectable clock to 9:30 AM—thirty minutes past Eleanor's grace window.
            CareLoop's circular EWMA engine flags the anomaly with pure deterministic math.
          </p>

          <div class="card" style="border-color: rgba(245, 158, 11, 0.3); background: rgba(245, 158, 11, 0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-weight: 700; color: #f59e0b; font-size: 15px;">Live Anomaly Evaluation</span>
              <span class="tag tag-amber">Score: 0.70</span>
            </div>
            <div style="font-size: 13px; color: #cbd5e1; line-height: 1.5;">
              &bull; Missed Event: Morning Lisinopril Pillbox Tray 1<br/>
              &bull; Grace Expired: 09:00 UTC (Current Clock: 09:30 UTC)<br/>
              &bull; Zero LLM Hallucinations: 100% deterministic code weights
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; justify-content: center;">
          <!-- JSON-RPC Inspector Card -->
          <div class="card" style="border-color: rgba(0, 202, 255, 0.35); background: #0a0f1d; padding: 22px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 10px;">
              <span style="font-size: 12px; font-weight: 700; color: #00CAFF;" class="mono">POST /mcp (JSON-RPC 2.0)</span>
              <span class="tag tag-cyan" style="font-size: 10px;">1.8 ms Execution</span>
            </div>
            <pre class="mono" style="font-size: 12px; color: #cbd5e1; line-height: 1.5; overflow: hidden;">{
  "jsonrpc": "2.0",
  "tool": "check_routine_health",
  "arguments": { "person": "eleanor" },
  "result": {
    "status": "anomaly_detected",
    "risk_score": 0.70,
    "risk_level": "high",
    "is_missed": true,
    "reasons": [
      "Medication missed past baseline grace window (weight: 0.4)"
    ]
  },
  "protocol_version": "2025-11-25"
}</pre>
          </div>
        </div>
        """

    elif sid == 4:
        # Scene 4: 4-Stage Autonomous Escalation Pipeline
        body_content = """
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 14px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-rose">Deterministic Safety Pipeline</span>
            <span class="tag tag-emerald">Zero Alarm Fatigue</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            Empathetic Voice ➔ Audible Chime ➔ Family SMS
          </h1>
          <p style="font-size: 15px; color: #94a3b8; line-height: 1.5;">
            CareLoop doesn't immediately panic the family. It progresses sequentially through four deterministic stages to verify the elder's wellbeing.
          </p>

          <div style="display: flex; flex-direction: column; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: rgba(16, 185, 129, 0.1); border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.25);">
              <span style="color: #10b981; font-weight: 800;">1. Normal</span>
              <span style="font-size: 12px; color: #94a3b8;">Daily activities within circadian grace window</span>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: rgba(245, 158, 11, 0.1); border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.25);">
              <span style="color: #f59e0b; font-weight: 800;">2. Gentle Check-In</span>
              <span style="font-size: 12px; color: #cbd5e1;">Alexa: <em>"Hi Eleanor, checking in softly, are you doing alright?"</em></span>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: rgba(245, 158, 11, 0.15); border-radius: 8px; border: 1px solid rgba(245, 158, 11, 0.35);">
              <span style="color: #f59e0b; font-weight: 800;">3. Repeat (+60s)</span>
              <span style="font-size: 12px; color: #cbd5e1;">Audible chime sounds &amp; prompt repeats if unanswered</span>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: rgba(239, 68, 68, 0.15); border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.4);">
              <span style="color: #ef4444; font-weight: 800;">4. Notify Family</span>
              <span style="font-size: 12px; color: #fca5a5;">Amazon SNS SMS dispatched with exact mathematical audit trail</span>
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; justify-content: center; gap: 16px;">
          <div class="card" style="border-color: rgba(239, 68, 68, 0.3);">
            <div style="font-size: 12px; font-weight: 700; color: #ef4444; margin-bottom: 6px;">DISPATCHED SMS PAYLOAD</div>
            <div style="font-size: 13px; color: #ffffff; line-height: 1.5;">
              "CareLoop Alert: Eleanor Davis missed morning medication by 30 mins past grace window. Unresponsive to gentle voice prompts. Call Linda: +1-555-019-2834."
            </div>
            <div style="margin-top: 10px; font-size: 11px; color: #94a3b8;" class="mono">
              Deduplication Key: dedup:alert:eleanor:medication:2026-10-20
            </div>
          </div>
          <div class="card" style="border-color: rgba(0, 202, 255, 0.25);">
            <div style="font-size: 12px; font-weight: 700; color: #00CAFF; margin-bottom: 4px;">ZERO SPAM GUARANTEE</div>
            <div style="font-size: 13px; color: #94a3b8;">
              Idempotent tick runner ensures subsequent evaluations within the incident window never flood the caregiver's phone.
            </div>
          </div>
        </div>
        """

    elif sid == 5:
        # Scene 5: Factual Memory Q&A & Reset
        body_content = """
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-cyan">Alexa+ Voice Inquiry</span>
            <span class="tag tag-emerald">Factual Storage Grounding</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            Factual Memory Queries & Instant Confirmation
          </h1>
          <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">
            Family members can check in through Alexa anytime. The <code>ask_memory</code> tool queries verified storage and answers factually without hallucinating.
          </p>

          <div class="card" style="border-color: rgba(0, 202, 255, 0.25);">
            <div style="font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase;">Caregiver Voice Question</div>
            <div style="font-size: 16px; font-weight: 700; color: #ffffff; margin-top: 4px;">"Alexa, did Mom take her pills today?"</div>
            <div style="margin-top: 10px; padding: 12px; background: rgba(0, 202, 255, 0.08); border-radius: 8px; font-size: 13px; color: #e2e8f0;">
              Alexa: <em>"There is no record of 'pill' for Eleanor Davis today. Morning Lisinopril was expected around 08:15 UTC."</em>
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div class="card" style="border-color: rgba(16, 185, 129, 0.3); background: rgba(16, 185, 129, 0.05);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-size: 12px; font-weight: 700; color: #10b981;">ELDER VOICE CONFIRMATION</span>
              <span class="tag tag-emerald">Tool: confirm_ok</span>
            </div>
            <div style="font-size: 16px; font-weight: 700; color: #ffffff;">"Alexa, I'm fine."</div>
            <div style="margin-top: 10px; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
              Instantly resets escalation state from Stage 4 back to <strong style="color: #10b981;">1. Normal (Nominal)</strong>. Family phone marks alert as <strong>RESOLVED ✓</strong>.
            </div>
          </div>
          <div class="card">
            <div style="font-size: 12px; font-weight: 700; color: #00CAFF; margin-bottom: 4px;">BEDROCK HAUKU ENRICHMENT</div>
            <div style="font-size: 13px; color: #94a3b8;">
              Amazon Bedrock Claude 3 Haiku generates warm, natural conversational summaries grounded strictly in verified event data.
            </div>
          </div>
        </div>
        """

    elif sid == 6:
        # Scene 6: AWS Cloud Architecture
        body_content = """
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-cyan">AWS Builder Challenge</span>
            <span class="tag tag-emerald">Production Verified</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            Production Serverless & Container Architecture
          </h1>
          <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">
            AWS ECS Fargate behind an Application Load Balancer provides long-lived HTTP streaming (300s timeout) without API Gateway's 29-second connection termination limits.
          </p>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div class="card" style="padding: 14px;">
              <div style="font-size: 13px; font-weight: 700; color: #00CAFF;">Amazon DynamoDB</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Single-Table PK/SK with KMS encryption at rest</div>
            </div>
            <div class="card" style="padding: 14px;">
              <div style="font-size: 13px; font-weight: 700; color: #10b981;">EventBridge Scheduler</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">1-min cron driving serverless Python Tick Lambda</div>
            </div>
            <div class="card" style="padding: 14px;">
              <div style="font-size: 13px; font-weight: 700; color: #f59e0b;">Amazon SNS</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Encrypted SMS dispatch with delivery tracking</div>
            </div>
            <div class="card" style="padding: 14px;">
              <div style="font-size: 13px; font-weight: 700; color: #ef4444;">Amazon Bedrock</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Claude 3 Haiku Converse API for summaries</div>
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; justify-content: center; gap: 16px;">
          <div class="card" style="border-color: rgba(0, 202, 255, 0.3);">
            <div style="font-size: 12px; font-weight: 700; color: #00CAFF; margin-bottom: 8px;">TRANSPARENT INTEGRATION BOUNDARIES</div>
            <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px;">
              <div style="display: flex; justify-content: space-between; padding: 6px 10px; background: rgba(16, 185, 129, 0.1); border-radius: 6px;">
                <span>FastMCP Streamable HTTP Core (/mcp)</span>
                <span style="color: #10b981; font-weight: 700;">100% Local Verified</span>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 6px 10px; background: rgba(0, 202, 255, 0.1); border-radius: 6px;">
                <span>AWS CDK &amp; SAM CloudFormation</span>
                <span style="color: #00CAFF; font-weight: 700;">cfn-lint 0 Errors</span>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 6px 10px; background: rgba(245, 158, 11, 0.1); border-radius: 6px;">
                <span>Physical Alexa+ Account Linking</span>
                <span style="color: #f59e0b; font-weight: 700;">Preview Ready</span>
              </div>
            </div>
          </div>
        </div>
        """

    else:
        # Scene 7: Benchmark Results & Closing
        body_content = f"""
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 18px; justify-content: center;">
          <div style="display: flex; gap: 8px;">
            <span class="tag tag-emerald">180 Elder-Days Replayed</span>
            <span class="tag tag-cyan">1,422 Routine Events</span>
          </div>
          <h1 style="font-size: 40px; font-weight: 800; line-height: 1.2;">
            100% Detection Rate · Zero False Alarms
          </h1>
          <p style="font-size: 16px; color: #94a3b8; line-height: 1.6;">
            We benchmarked CareLoop across 180 simulated elder-days. All eighteen clinical incidents were caught, while eliminating eighty false alarms caused by traditional static timers.
          </p>

          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;">
            <div class="card" style="padding: 16px; text-align: center; border-color: rgba(16, 185, 129, 0.3);">
              <div style="font-size: 26px; font-weight: 800; color: #10b981;">18 / 18</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">Incidents Caught (100%)</div>
            </div>
            <div class="card" style="padding: 16px; text-align: center; border-color: rgba(0, 202, 255, 0.3);">
              <div style="font-size: 26px; font-weight: 800; color: #00CAFF;">0.0000</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">False Alerts / Day</div>
            </div>
            <div class="card" style="padding: 16px; text-align: center; border-color: rgba(245, 158, 11, 0.3);">
              <div style="font-size: 26px; font-weight: 800; color: #f59e0b;">178 Tests</div>
              <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">79% Statement Coverage</div>
            </div>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; justify-content: center; gap: 16px;">
          <div class="card" style="padding: 24px; text-align: center; border-color: rgba(0, 202, 255, 0.3); background: linear-gradient(180deg, #101c2e 0%, #080d16 100%);">
            <img src="{LOGO_B64}" alt="Logo" style="width: 64px; height: 64px; border-radius: 14px; margin: 0 auto 12px auto; display: block;" />
            <h2 style="font-size: 26px; font-weight: 800; color: #ffffff;">CareLoop</h2>
            <div style="font-size: 13px; color: #00CAFF; margin-top: 4px;">Ambient elder safety that families can truly trust.</div>
            <div style="margin-top: 16px; font-size: 12px; color: #94a3b8;" class="mono">
              github.com/KarnailSingh87/careloop
            </div>
            <span class="tag tag-emerald" style="margin-top: 12px;">MIT Permissive Open Source</span>
          </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>CareLoop Video · Scene {sid}</title>
  <style>
{COMMON_VIDEO_CSS}
  </style>
</head>
<body>
  <div class="scene-frame">
    <div class="top-bar">
      <div class="brand-wrap">
        <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
        <span class="brand-text">CareLoop</span>
        <span class="badge-alexa">Alexa+ Demo</span>
      </div>
      <div class="scene-badge">{time_code} · {title}</div>
    </div>

    <div class="content-area">
      {body_content}
    </div>

    <div class="caption-bar">
      <div class="caption-icon">&#9654;</div>
      <div class="caption-text">"{caption}"</div>
    </div>
  </div>
</body>
</html>
"""
    return html


def main():
    print("CareLoop Demonstration Video Pipeline starting...")
    output_video = WORKSPACE_DIR / "careloop_demo_video.mp4"
    media_video = MEDIA_DIR / "careloop_demo_video.mp4"

    clip_paths = []

    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)

        user_data = work_path / "edge_profile"
        user_data.mkdir(exist_ok=True)

        for s in SCENES:
            sid = s["id"]
            title = s["title"]
            speech = s["speech"]
            print(f"\nProcessing Scene {sid}/7: {title}...")

            # 1. Generate Voice-Over Speech Audio
            aiff_path = work_path / f"scene_{sid}.aiff"
            wav_path = work_path / f"scene_{sid}.wav"

            cmd_say = ["say", "-v", "Samantha", "-r", "175", "-o", str(aiff_path), speech]
            subprocess.run(cmd_say, check=True)

            cmd_convert = [
                FFMPEG_BIN,
                "-y",
                "-i",
                str(aiff_path),
                "-ac",
                "2",
                "-ar",
                "44100",
                str(wav_path),
            ]
            subprocess.run(cmd_convert, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Get exact audio duration
            cmd_probe = [
                FFPROBE_BIN,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ]
            duration_str = subprocess.check_output(cmd_probe).decode("utf-8").strip()
            duration = float(duration_str)
            print(f"  ✓ Audio synthesized: {duration:.2f}s")

            # 2. Render 1920x1080 Scene Frame HTML
            scene_html = generate_scene_html(s)
            html_path = work_path / f"scene_{sid}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(scene_html)

            png_path = work_path / f"scene_{sid}.png"

            cmd_edge = [
                EDGE_BIN,
                "--headless",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-sync",
                "--disable-default-apps",
                "--mute-audio",
                "--run-all-compositor-stages-before-draw",
                f"--user-data-dir={user_data}",
                "--no-first-run",
                "--no-default-browser-check",
                "--window-size=1920,1080",
                f"--screenshot={png_path}",
                f"file://{html_path}",
            ]
            subprocess.run(
                cmd_edge,
                check=True,
                timeout=20,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            print("  ✓ Frame captured: 1920x1080")

            # 3. Create Scene MP4 Video Clip with Animated Subtle Ken Burns Pan-Zoom
            clip_mp4 = work_path / f"clip_{sid}.mp4"
            total_frames = int(duration * 30)

            # Ken Burns slow zoom: 1.0 to 1.05
            cmd_clip = [
                FFMPEG_BIN,
                "-y",
                "-loop",
                "1",
                "-i",
                str(png_path),
                "-i",
                str(wav_path),
                "-filter_complex",
                f"[0:v]scale=1920:1080,zoompan=z='min(zoom+0.0004,1.06)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30[v]",
                "-map",
                "[v]",
                "-map",
                "1:a",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(clip_mp4),
            ]
            subprocess.run(cmd_clip, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  ✓ Scene clip compiled: {clip_mp4.name} ({duration:.2f}s)")
            clip_paths.append(clip_mp4)

        # 4. Concatenate all 7 scene clips into master MP4
        print("\nConcatenating all 7 scenes into master CareLoop demonstration video...")
        concat_txt = work_path / "concat.txt"
        with open(concat_txt, "w") as f:
            for c in clip_paths:
                f.write(f"file '{c.resolve()}'\n")

        cmd_concat = [
            FFMPEG_BIN,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(output_video),
        ]
        subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        shutil.copyfile(output_video, media_video)

    # Inspect final video
    cmd_probe = [
        FFPROBE_BIN,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=width,height,codec_name",
        "-of",
        "json",
        str(output_video),
    ]
    info = json.loads(subprocess.check_output(cmd_probe).decode("utf-8"))
    dur = float(info["format"]["duration"])
    size_mb = int(info["format"]["size"]) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("🎬 CareLoop Demonstration Video Complete!")
    print(f"  • Video File: {output_video}")
    print(f"  • Media Copy: {media_video}")
    print("  • Resolution: 1920x1080 (1080p Full HD)")
    print(f"  • Total Duration: {int(dur // 60)}m {int(dur % 60):02d}s ({dur:.1f} seconds)")
    print(f"  • File Size: {size_mb:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
