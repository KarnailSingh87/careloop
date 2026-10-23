#!/usr/bin/env python3
"""
CareLoop Hackathon Project Media Generator
Generates:
1. 12 High-Definition 3:2 Ratio Image Gallery assets (PNG & JPG, < 5MB) for Devpost.
2. Complete Publication-Grade 3:2 Ratio Presentation PDF (CareLoop_Project_Media.pdf).
Features REAL photography, real dashboard captures, real architecture, and mathematical diagrams.
"""

import base64
import shutil
import subprocess
from pathlib import Path
from PIL import Image

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = WORKSPACE_DIR / "project_media"
MEDIA_DIR.mkdir(exist_ok=True)

EDGE_BIN = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"


def get_base64_data_uri(filepath: Path, mime: str = "image/jpeg") -> str:
    if not filepath.exists():
        print(f"Warning: File {filepath} not found for base64 encoding.")
        return ""
    with open(filepath, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{encoded}"


# Load real project images as base64
ARTHUR_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "arthur.jpg", "image/jpeg")
ELEANOR_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "eleanor.jpg", "image/jpeg")
MARTHA_B64 = get_base64_data_uri(WORKSPACE_DIR / "public" / "portraits" / "martha.jpg", "image/jpeg")
LOGO_B64 = get_base64_data_uri(WORKSPACE_DIR / "careloop" / "simulator" / "logo.jpg", "image/jpeg")
REACT_APP_B64 = get_base64_data_uri(WORKSPACE_DIR / "test_captures" / "react_app.png", "image/png")
SIMULATOR_B64 = get_base64_data_uri(WORKSPACE_DIR / "test_captures" / "simulator.png", "image/png")

# Common CSS styles for slides (1800 x 1200 px = exact 3:2 aspect ratio)
COMMON_CSS = """
  @page {
    size: 1800px 1200px;
    margin: 0;
  }
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
  }
  html, body {
    width: 1800px;
    height: 1200px;
    margin: 0;
    padding: 0;
    background-color: #070b13;
    color: #ffffff;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }
  .slide-container {
    width: 1800px;
    height: 1200px;
    max-height: 1200px;
    position: relative;
    overflow: hidden;
    background: #080c15;
    page-break-after: always;
    page-break-inside: avoid;
    break-after: page;
    break-inside: avoid;
    display: flex;
    flex-direction: column;
    padding: 44px 52px;
    box-sizing: border-box;
    border-bottom: none;
  }
  .slide-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 24px;
    margin-bottom: 32px;
  }
  .brand-group {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .brand-logo {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    object-fit: cover;
    border: 1px solid rgba(0, 202, 255, 0.3);
  }
  .brand-title {
    font-size: 24px;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #ffffff;
  }
  .brand-pill {
    background: rgba(0, 202, 255, 0.12);
    border: 1px solid rgba(0, 202, 255, 0.3);
    color: #00CAFF;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 6px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .slide-category {
    font-size: 14px;
    color: #94a3b8;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .slide-title-wrap {
    margin-bottom: 32px;
  }
  .slide-title {
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -0.02em;
    color: #ffffff;
    line-height: 1.2;
    margin-bottom: 8px;
  }
  .slide-subtitle {
    font-size: 18px;
    color: #94a3b8;
    font-weight: 400;
    line-height: 1.5;
  }
  .slide-body {
    flex: 1;
    display: flex;
    gap: 36px;
    min-height: 0;
  }
  .slide-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 20px;
    margin-top: 24px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    font-size: 13px;
    color: #64748b;
    font-weight: 500;
  }
  .card-panel {
    background: #0f172a;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 28px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
  }
  .tag {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
  }
  .tag-cyan { background: rgba(0, 202, 255, 0.12); border: 1px solid rgba(0, 202, 255, 0.3); color: #00CAFF; }
  .tag-emerald { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); color: #10b981; }
  .tag-amber { background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.3); color: #f59e0b; }
  .tag-rose { background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; }
  .mono { font-family: "JetBrains Mono", Menlo, Consolas, monospace; }
"""


def generate_slides_html() -> str:
    slides = []

    # -------------------------------------------------------------
    # SLIDE 1: Cover & Project Overview
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container" style="background: radial-gradient(circle at 85% 15%, rgba(0, 202, 255, 0.08) 0%, transparent 60%), #080c15;">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Alexa+ Elder Care Companion</span>
        </div>
        <div class="slide-category">Amazon Developer Hackathon Submission · 2026</div>
      </div>

      <div class="slide-body" style="align-items: center; gap: 48px;">
        <!-- Left: Pitch & Value Prop -->
        <div style="flex: 1.2; display: flex; flex-direction: column; gap: 24px;">
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <span class="tag tag-cyan">★ Alexa+ Voice Companion</span>
            <span class="tag tag-emerald">★ FastMCP Spec 2025-11-25</span>
            <span class="tag tag-cyan">★ AWS Builder Challenge</span>
            <span class="tag tag-emerald">★ Permissive MIT Open Source</span>
          </div>

          <h1 style="font-size: 52px; font-weight: 800; line-height: 1.15; letter-spacing: -0.03em;">
            Autonomous Circadian Safety for Loved Ones Living Alone
          </h1>

          <p style="font-size: 21px; color: #94a3b8; line-height: 1.6; max-width: 820px;">
            CareLoop transforms Amazon Echo Show into an ambient, zero-intrusion elder guardian.
            Using <strong style="color: #00CAFF;">circular EWMA statistics</strong>, it learns personal daily routines from discrete sensors—smart pillboxes, door contacts, and natural voice check-ins—eliminating intrusive cameras and false alarm fatigue.
          </p>

          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 12px;">
            <div class="card-panel" style="padding: 20px;">
              <div style="font-size: 32px; font-weight: 800; color: #00CAFF;">9 Tools</div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">FastMCP Voice Tools for Alexa+</div>
            </div>
            <div class="card-panel" style="padding: 20px;">
              <div style="font-size: 32px; font-weight: 800; color: #10b981;">178 Tests</div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">79% Statement Coverage</div>
            </div>
            <div class="card-panel" style="padding: 20px;">
              <div style="font-size: 32px; font-weight: 800; color: #f59e0b;">0 Cameras</div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">100% Privacy-Preserving</div>
            </div>
          </div>
        </div>

        <!-- Right: Real Elder Arthur Profile Hero Card -->
        <div style="flex: 0.8; display: flex; justify-content: center;">
          <div class="card-panel" style="width: 100%; max-width: 480px; padding: 36px; text-align: center; border: 1px solid rgba(0, 202, 255, 0.25); background: linear-gradient(180deg, #101827 0%, #0c121e 100%);">
            <div style="position: relative; width: 160px; height: 160px; margin: 0 auto 24px auto;">
              <div style="position: absolute; inset: -8px; border-radius: 50%; background: linear-gradient(135deg, #00CAFF, #10b981); opacity: 0.6; filter: blur(10px);"></div>
              <img src="{ARTHUR_B64}" alt="Arthur Davis" style="position: relative; width: 160px; height: 160px; border-radius: 50%; object-fit: cover; border: 3px solid #ffffff;" />
              <div style="position: absolute; bottom: 4px; right: 8px; width: 28px; height: 28px; border-radius: 50%; background: #10b981; border: 3px solid #080c15; display: flex; align-items: center; justify-content: center; font-size: 14px;">✓</div>
            </div>

            <h2 style="font-size: 28px; font-weight: 800; color: #ffffff;">Arthur Davis</h2>
            <div style="font-size: 15px; color: #00CAFF; font-weight: 600; margin-top: 4px;">Age 81 · Living Independently</div>
            <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Daughter & Primary Caregiver: Linda Davis</div>

            <div style="margin-top: 24px; padding: 16px; border-radius: 12px; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); text-align: left;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-size: 12px; font-weight: 700; color: #10b981; text-transform: uppercase;">Current Routine Status</span>
                <span class="tag tag-emerald" style="padding: 2px 6px; font-size: 10px;">Nominal (0.0)</span>
              </div>
              <div style="font-size: 14px; color: #ffffff; font-weight: 600;">Arthur is Doing Well at Home</div>
              <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Metoprolol 25mg taken on schedule (07:55 AM). Kitchen refrigerator ping at 12:21 PM.</div>
            </div>

            <div style="margin-top: 16px; font-size: 12px; color: #64748b;">
              Connected: Living Room Amazon Echo Show 10
            </div>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop · Amazon Developer Hackathon Submission Package</div>
        <div>FastMCP Spec 2025-11-25 · AWS ECS Fargate · Amazon DynamoDB · Amazon EventBridge Scheduler · Amazon SNS</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 2: Ambient Hero Dashboard
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Ambient UI</span>
        </div>
        <div class="slide-category">01 · Ambient Hero Dashboard</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Elder Peace of Mind at a Single Glance</h1>
        <p class="slide-subtitle">Clean, human-engineered dashboard inspired by Apple Health & Amazon Echo Hub design systems.</p>
      </div>

      <div class="slide-body" style="gap: 32px;">
        <div style="flex: 1.4; display: flex; flex-direction: column; justify-content: center;">
          <div style="border-radius: 16px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.15); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);">
            <img src="{REACT_APP_B64}" alt="React Dashboard" style="width: 100%; height: auto; display: block;" />
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 16px; justify-content: center;">
          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-emerald">Live Telemetry</span>
              <h3 style="font-size: 18px; font-weight: 700;">Reassuring Status Hero</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Features Arthur Davis's photo with a dynamic breathing glow ring. Status indicator proves Arthur is nominal without needing noisy alarms or surveillance.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-cyan">4 Primary Actions</span>
              <h3 style="font-size: 18px; font-weight: 700;">One-Tap Care Directives</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Instantly check in via Alexa voice, mark medication taken, send motion sensor pings, or open the family emergency care circle with zero friction.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-amber">Circadian Baseline</span>
              <h3 style="font-size: 18px; font-weight: 700;">80% Daily Routines Recorded</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Metoprolol Tartrate confirmed taken at 7:55 AM. Living Room Echo Show 10 provides continuous camera-free ambient protection.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Ambient Dashboard · TypeScript + React 18 + Tailwind CSS + Lucide Icons</div>
        <div>Full Responsive & Dark / Warm Off-White Mode Supported</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 3: Natural Voice Companion & Alexa+ Console
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Alexa+ Voice Companion</span>
        </div>
        <div class="slide-category">02 · Natural Voice & FastMCP Spec 2025-11-25</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Ambient Alexa+ Console & Live MCP Tool Execution</h1>
        <p class="slide-subtitle">Natural voice queries mapped deterministically to FastMCP tools with sub-50ms execution times.</p>
      </div>

      <div class="slide-body" style="gap: 36px;">
        <!-- Left: Echo Show Interactive Device Mockup -->
        <div style="flex: 1.1; display: flex; flex-direction: column;">
          <div class="card-panel" style="flex: 1; border-color: rgba(0, 202, 255, 0.25); background: linear-gradient(180deg, #0e1726 0%, #090e18 100%); display: flex; flex-direction: column;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
              <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 14px; height: 14px; border-radius: 50%; background: #00CAFF; box-shadow: 0 0 12px #00CAFF;"></div>
                <span style="font-weight: 700; font-size: 15px; color: #00CAFF;">Amazon Echo Show 10 · Living Room</span>
              </div>
              <span class="tag tag-emerald">FastMCP Online (/mcp)</span>
            </div>

            <!-- Chat Transcript -->
            <div style="flex: 1; display: flex; flex-direction: column; gap: 14px; justify-content: center;">
              <div style="background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase;">Family Spoken Query</div>
                <div style="font-size: 16px; color: #ffffff; font-weight: 600; margin-top: 4px;">"Alexa, did Dad take his pills today?"</div>
              </div>

              <div style="background: rgba(0, 202, 255, 0.08); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 12px; padding: 16px 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="font-size: 11px; font-weight: 700; color: #00CAFF; text-transform: uppercase;">Alexa+ Ambient Response</span>
                  <span style="font-size: 11px; color: #94a3b8;" class="mono">08:00 AM · Audio Spoken Aloud</span>
                </div>
                <div style="font-size: 16px; color: #ffffff; line-height: 1.4;">
                  "Good morning! Arthur's morning routines are currently nominal. Metoprolol Tartrate 25mg was recorded at 07:55 AM from his smart pillbox."
                </div>
              </div>

              <div style="background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 14px 18px;">
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8; text-transform: uppercase;">Elder Voice Interaction</div>
                <div style="font-size: 16px; color: #ffffff; font-weight: 600; margin-top: 4px;">"Alexa, I'm having breakfast now."</div>
              </div>

              <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 12px; padding: 16px 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="font-size: 11px; font-weight: 700; color: #10b981; text-transform: uppercase;">Alexa+ Confirmation</span>
                  <span style="font-size: 11px; color: #94a3b8;" class="mono">Tool: log_routine_event</span>
                </div>
                <div style="font-size: 16px; color: #ffffff; line-height: 1.4;">
                  "Logged breakfast for Arthur. Enjoy your meal! Your daily schedule is on track."
                </div>
              </div>
            </div>

            <!-- Waveform Bar -->
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(255, 255, 255, 0.08);">
              <span style="font-size: 12px; color: #94a3b8;">Web Speech Audio:</span>
              <div style="display: flex; gap: 3px; align-items: center; flex: 1;">
                <div style="width: 4px; height: 12px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 24px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 18px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 32px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 20px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 14px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 26px; background: #00CAFF; border-radius: 2px;"></div>
                <div style="width: 4px; height: 8px; background: #00CAFF; border-radius: 2px;"></div>
              </div>
              <span class="tag tag-cyan" style="font-size: 11px;">Voice Audio: ON</span>
            </div>
          </div>
        </div>

        <!-- Right: FastMCP Inspection Cards -->
        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 16px; justify-content: center;">
          <div class="card-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="mono" style="color: #00CAFF; font-weight: 700;">ask_memory</span>
              <span class="tag tag-cyan">18ms</span>
            </div>
            <div class="mono" style="font-size: 12px; color: #cbd5e1; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px;">
              &#123; "person": "dad", "question": "Did Dad take his pills today?" &#125;
            </div>
            <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">
              Executes factual memory queries against DynamoDB single-table events with Bedrock Claude 3 Haiku summarization.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="mono" style="color: #10b981; font-weight: 700;">log_routine_event</span>
              <span class="tag tag-emerald">12ms</span>
            </div>
            <div class="mono" style="font-size: 12px; color: #cbd5e1; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px;">
              &#123; "person": "dad", "type": "meal", "metadata": &#123; "meal": "breakfast" &#125; &#125;
            </div>
            <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">
              Feeds new timestamp into Circular EWMA statistics engine and refreshes inactivity timeouts immediately.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="mono" style="color: #f59e0b; font-weight: 700;">check_routine_health</span>
              <span class="tag tag-amber">9ms</span>
            </div>
            <div class="mono" style="font-size: 12px; color: #cbd5e1; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px;">
              &#123; "status": "nominal", "risk_score": 0.0, "stage": "normal" &#125;
            </div>
            <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">
              Deterministic 4-stage health evaluator evaluating deviation against personal circular baseline windows.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>Model Context Protocol (MCP) Streamable HTTP Spec 2025-11-25 · Starlette ASGI Persistent Chunked Transfer</div>
        <div>Constant-Time Caller Authentication Enforced</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 4: Daily Routine & Circadian Schedule
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Telemetry Schedule</span>
        </div>
        <div class="slide-category">03 · Daily Routine Schedule</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Circadian Adherence & Medication Tracking</h1>
        <p class="slide-subtitle">Discrete ambient sensor telemetry tracking meals, motion, and medicine with personalized grace windows.</p>
      </div>

      <div class="slide-body" style="gap: 32px;">
        <div style="flex: 1.2; display: flex; flex-direction: column; gap: 14px; justify-content: center;">
          <!-- Item 1 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 18px 24px;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(0, 202, 255, 0.12); display: flex; align-items: center; justify-content: center; font-size: 20px;">👣</div>
              <div>
                <h4 style="font-size: 16px; font-weight: 700;">Morning Wake & Gentle Stretch</h4>
                <div style="font-size: 13px; color: #94a3b8;">Bedroom PIR Motion Sensor · Expected: 07:00 AM</div>
              </div>
            </div>
            <span class="tag tag-emerald">Done (06:55 AM)</span>
          </div>

          <!-- Item 2 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 18px 24px; border-color: rgba(16, 185, 129, 0.3);">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(16, 185, 129, 0.12); display: flex; align-items: center; justify-content: center; font-size: 20px;">💊</div>
              <div>
                <h4 style="font-size: 16px; font-weight: 700;">Prescription Heart Beta-Blocker</h4>
                <div style="font-size: 13px; color: #94a3b8;">Metoprolol Tartrate 25mg · Smart Pillbox Tray 1 · Expected: 08:00 AM</div>
              </div>
            </div>
            <span class="tag tag-emerald">Done (07:55 AM)</span>
          </div>

          <!-- Item 3 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 18px 24px;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(245, 158, 11, 0.12); display: flex; align-items: center; justify-content: center; font-size: 20px;">🚪</div>
              <div>
                <h4 style="font-size: 16px; font-weight: 700;">Patio Walk & Garden Check</h4>
                <div style="font-size: 13px; color: #94a3b8;">Patio Door Magnetic Contact Sensor · Expected: 11:15 AM</div>
              </div>
            </div>
            <span class="tag tag-emerald">Done (11:19 AM)</span>
          </div>

          <!-- Item 4 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 18px 24px;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(0, 202, 255, 0.12); display: flex; align-items: center; justify-content: center; font-size: 20px;">🍲</div>
              <div>
                <h4 style="font-size: 16px; font-weight: 700;">Midday Meal & Hydration</h4>
                <div style="font-size: 13px; color: #94a3b8;">Kitchen Refrigerator Door Sensor & Ambient PIR · Expected: 12:30 PM</div>
              </div>
            </div>
            <span class="tag tag-emerald">Done (12:21 PM)</span>
          </div>

          <!-- Item 5 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; padding: 18px 24px; opacity: 0.85;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(255, 255, 255, 0.08); display: flex; align-items: center; justify-content: center; font-size: 20px;">🌙</div>
              <div>
                <h4 style="font-size: 16px; font-weight: 700;">Evening Wind-Down & Voice Check-In</h4>
                <div style="font-size: 13px; color: #94a3b8;">Living Room Echo Show 10 · Expected: 07:30 PM</div>
              </div>
            </div>
            <span class="tag tag-cyan">Upcoming (Pending)</span>
          </div>
        </div>

        <!-- Right: Statistical Grace Window Feature -->
        <div style="flex: 0.8; display: flex; flex-direction: column; justify-content: center; gap: 20px;">
          <div class="card-panel" style="border-color: rgba(0, 202, 255, 0.25);">
            <span class="tag tag-cyan" style="margin-bottom: 12px;">Circadian Innovation</span>
            <h3 style="font-size: 22px; font-weight: 800; margin-bottom: 12px;">Dynamic Grace Windows</h3>
            <p style="font-size: 15px; color: #94a3b8; line-height: 1.6;">
              Traditional systems trigger alarms if a pill isn't taken at 8:00 AM sharp.
              CareLoop's circular EWMA engine computes each elder's personal routine variance (&sigma;).
            </p>
            <div style="margin-top: 16px; padding: 14px; background: rgba(0,0,0,0.3); border-radius: 10px;" class="mono">
              Grace Interval: [&mu; - 2&sigma;, &mu; + 2&sigma; + margin]<br/>
              Arthur Davis Morning Window: &plusmn;32 mins
            </div>
            <p style="font-size: 13px; color: #10b981; margin-top: 12px; font-weight: 600;">
              ✓ Eliminates alarm fatigue when Dad sleeps in on weekends.
            </p>
          </div>

          <div class="card-panel">
            <h4 style="font-size: 16px; font-weight: 700; margin-bottom: 8px;">Camera-Free Privacy Guarantee</h4>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              No continuous audio streaming, no intrusive video feeds, and no wearable buttons Arthur forgets to wear. Pure ambient metadata dignity.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Telemetry Checklist · Smart Pillbox + Door Contact + Passive PIR</div>
        <div>Deterministic Grace Margin: 30 minutes with multi-factor risk weighting</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 5: Family Care Circle & Caregiver Gateway
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Family Circle</span>
        </div>
        <div class="slide-category">04 · Family Care Circle & Direct Gateway</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Keeping Caregivers Connected Without Invasiveness</h1>
        <p class="slide-subtitle">Emergency contacts, direct ambient chime connect, and explainable SNS alert dispatches.</p>
      </div>

      <div class="slide-body" style="gap: 36px; align-items: center;">
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 20px;">
          <!-- Contact 1 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center; border-color: rgba(0, 202, 255, 0.25);">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 52px; height: 52px; border-radius: 50%; background: #00CAFF; color: #080c15; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800;">LD</div>
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <h3 style="font-size: 18px; font-weight: 700;">Linda Davis</h3>
                  <span class="tag tag-cyan">Primary Caregiver</span>
                </div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Daughter · +1 (555) 019-2834 · Verified Amazon SNS Mobile</div>
              </div>
            </div>
            <span class="tag tag-emerald">SMS & Push Active</span>
          </div>

          <!-- Contact 2 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 52px; height: 52px; border-radius: 50%; background: #10b981; color: #080c15; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800;">SJ</div>
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <h3 style="font-size: 18px; font-weight: 700;">Dr. Sarah Jenkins</h3>
                  <span class="tag tag-emerald">Cardiologist</span>
                </div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">St. Jude Medical Group · Protocol: Metoprolol Tartrate 25mg BID</div>
              </div>
            </div>
            <span class="tag tag-cyan">Escalation Stage 4 Only</span>
          </div>

          <!-- Contact 3 -->
          <div class="card-panel" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div style="width: 52px; height: 52px; border-radius: 50%; background: #f59e0b; color: #080c15; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800;">MD</div>
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <h3 style="font-size: 18px; font-weight: 700;">Mark Davis</h3>
                  <span class="tag tag-amber">Secondary Contact</span>
                </div>
                <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Son · +1 (555) 019-5847 · Notification Fallback</div>
              </div>
            </div>
            <span class="tag tag-cyan">Backup</span>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 20px;">
          <div class="card-panel" style="border-color: rgba(16, 185, 129, 0.3); background: linear-gradient(180deg, #101c2a 0%, #0a111a 100%);">
            <h3 style="font-size: 20px; font-weight: 800; margin-bottom: 12px; color: #10b981;">Direct Ambient Voice Connect</h3>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.6;">
              Family members can tap one button on their smartphone to send a gentle, soothing audio chime directly to Arthur's Echo Show 10 without needing an intrusive phone ring.
            </p>
            <div style="margin-top: 14px; padding: 12px; background: rgba(0,0,0,0.3); border-radius: 8px; font-size: 13px; color: #00CAFF;">
              "Hello Arthur, Linda is sending a soft check-in chime from work."
            </div>
          </div>

          <div class="card-panel" style="border-color: rgba(239, 68, 68, 0.25);">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
              <span class="tag tag-rose">KMS Encrypted</span>
              <h4 style="font-size: 16px; font-weight: 700;">Zero Surveillance Spam</h4>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Caregivers only receive phone notifications if the elder fails to respond to both Stage 2 gentle voice check-in and Stage 3 repeat chimes.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Family Circle Modal · Amazon SNS KMS Encrypted Dispatch</div>
        <div>Audit Trail Key: SHA-256 Deduplication Hash per Escalation Incident</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 6: Cockpit Simulator Overview
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Simulator Cockpit</span>
        </div>
        <div class="slide-category">05 · Zero-Configuration Cockpit Simulator</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Full Dual-Screen Simulator & Virtual Caregiver Phone</h1>
        <p class="slide-subtitle">Standalone browser interface (/simulator) pairing ambient Alexa Show with virtual caregiver phone.</p>
      </div>

      <div class="slide-body" style="gap: 32px;">
        <div style="flex: 1.4; display: flex; flex-direction: column; justify-content: center;">
          <div style="border-radius: 16px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.15); box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);">
            <img src="{SIMULATOR_B64}" alt="Simulator Cockpit" style="width: 100%; height: auto; display: block;" />
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 16px; justify-content: center;">
          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-cyan">Left Column</span>
              <h3 style="font-size: 18px; font-weight: 700;">Alexa+ Ambient Assistant</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Echo Show ambient screen with pulsing Alexa cyan orb, Web Speech API speech recognition, and mapped phrase directory.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-emerald">Center Column</span>
              <h3 style="font-size: 18px; font-weight: 700;">Elder Status & Escalation</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Arthur Davis profile card with real portrait, risk score badge, and real-time 4-stage escalation stepper.
            </p>
          </div>

          <div class="card-panel">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <span class="tag tag-rose">Right Column</span>
              <h3 style="font-size: 18px; font-weight: 700;">Virtual Family Phone</h3>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Caregiver iPhone with Dynamic Island, 5G status, and real-time Amazon SNS alert notifications with audit trails.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Simulator · careloop/simulator/index.html · 100% Offline with Local SQLite Database</div>
        <div>Injectable SimulatedClock Time Machine Controls Supported</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 7: Autonomous 4-Stage Escalation & Emergency Alert
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Safety State Machine</span>
        </div>
        <div class="slide-category">06 · 4-Stage Autonomous Escalation Pipeline</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Explainable 4-Stage Autonomous Voice Escalation</h1>
        <p class="slide-subtitle">Deterministic state machine transitions: Normal &rarr; Gentle Voice &rarr; Repeat Voice &rarr; Family SMS Alert.</p>
      </div>

      <div class="slide-body" style="gap: 36px; align-items: center;">
        <!-- Left: Escalation Flowchart -->
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 16px;">
          <!-- Stage 1 -->
          <div class="card-panel" style="display: flex; align-items: center; gap: 18px; padding: 20px 24px;">
            <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(16, 185, 129, 0.15); color: #10b981; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800;">1</div>
            <div style="flex: 1;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="font-size: 17px; font-weight: 700; color: #10b981;">Stage 1: NORMAL</h4>
                <span class="tag tag-emerald">Score: 0.0</span>
              </div>
              <p style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Daily activities within dynamic circadian grace window. Continuous passive telemetry.</p>
            </div>
          </div>

          <!-- Stage 2 -->
          <div class="card-panel" style="display: flex; align-items: center; gap: 18px; padding: 20px 24px;">
            <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(245, 158, 11, 0.15); color: #f59e0b; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800;">2</div>
            <div style="flex: 1;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="font-size: 17px; font-weight: 700; color: #f59e0b;">Stage 2: GENTLE_CHECK_IN</h4>
                <span class="tag tag-amber">Score: 0.4</span>
              </div>
              <p style="font-size: 13px; color: #94a3b8; margin-top: 2px;">Routine missed past grace window. Echo Show speaks softly: <em>"Arthur, just checking in softly."</em></p>
            </div>
          </div>

          <!-- Stage 3 -->
          <div class="card-panel" style="display: flex; align-items: center; gap: 18px; padding: 20px 24px;">
            <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(245, 158, 11, 0.25); color: #f59e0b; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800;">3</div>
            <div style="flex: 1;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="font-size: 17px; font-weight: 700; color: #f59e0b;">Stage 3: REPEAT_CHECK_IN</h4>
                <span class="tag tag-amber">Score: 0.6</span>
              </div>
              <p style="font-size: 13px; color: #94a3b8; margin-top: 2px;">No reply after 60 seconds. Audible chime sounds and voice prompt repeats with urgency.</p>
            </div>
          </div>

          <!-- Stage 4 -->
          <div class="card-panel" style="display: flex; align-items: center; gap: 18px; padding: 20px 24px; border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.05);">
            <div style="width: 44px; height: 44px; border-radius: 50%; background: rgba(239, 68, 68, 0.2); color: #ef4444; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800;">4</div>
            <div style="flex: 1;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="font-size: 17px; font-weight: 700; color: #ef4444;">Stage 4: NOTIFY_FAMILY</h4>
                <span class="tag tag-rose">Score: 0.85 &rarr; SMS</span>
              </div>
              <p style="font-size: 13px; color: #cbd5e1; margin-top: 2px;">Autonomous dispatch of KMS-encrypted Amazon SNS SMS to Linda Davis with full audit reason.</p>
            </div>
          </div>
        </div>

        <!-- Right: iPhone SMS Notification Mockup -->
        <div style="flex: 0.9; display: flex; justify-content: center;">
          <div style="width: 380px; height: 580px; background: #000000; border-radius: 44px; border: 4px solid #334155; padding: 20px; display: flex; flex-direction: column; box-shadow: 0 30px 60px rgba(0,0,0,0.6); position: relative;">
            <!-- Notch -->
            <div style="width: 120px; height: 26px; background: #1e293b; border-radius: 20px; margin: 0 auto 16px auto; display: flex; align-items: center; justify-content: center;">
              <div style="width: 10px; height: 10px; border-radius: 50%; background: #000; margin-right: 8px;"></div>
              <div style="width: 8px; height: 8px; border-radius: 50%; background: #00CAFF;"></div>
            </div>

            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; font-weight: 600; margin-bottom: 24px;">
              <span>14:02</span>
              <span>5G · 100%</span>
            </div>

            <!-- Emergency Push Alert Card -->
            <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 18px; padding: 18px; margin-top: 20px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span class="tag tag-rose" style="font-size: 10px;">URGENT FAMILY ALERT</span>
                <span style="font-size: 11px; color: #cbd5e1;" class="mono">14:02 UTC</span>
              </div>
              <div style="font-size: 15px; font-weight: 800; color: #ffffff;">Arthur Davis Missed Lunch Routine</div>
              <div style="font-size: 10px; text-transform: uppercase; color: #fca5a5; font-weight: 700; margin-top: 10px;">Deterministic Code Reasons:</div>
              <ul style="font-size: 12px; color: #fecaca; margin-top: 6px; padding-left: 16px; line-height: 1.4;">
                <li>72 mins past circular EWMA lunch window (&mu; = 12:30 PM).</li>
                <li>Zero room movement detected in kitchen or living room.</li>
                <li>Arthur did not respond to Stage 2 &amp; 3 voice prompts.</li>
              </ul>
              <div style="display: flex; gap: 8px; margin-top: 14px;">
                <div style="flex: 1; background: #ef4444; color: #fff; font-weight: 700; font-size: 12px; padding: 10px; border-radius: 8px; text-align: center;">📞 Call Dad</div>
                <div style="flex: 1; background: rgba(255,255,255,0.1); color: #fff; font-size: 12px; padding: 10px; border-radius: 8px; text-align: center;">Acknowledge</div>
              </div>
            </div>

            <div style="margin-top: auto; text-align: center; font-size: 11px; color: #64748b;">
              Amazon SNS KMS-Encrypted SMS Dispatch
            </div>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Deterministic Escalation Machine · careloop/engine/escalation.py</div>
        <div>Multi-Factor Weighted Risk Engine: Missed Meds (0.4) + Inactivity (0.3) + Missed Meals (0.2)</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 8: Circular EWMA Baseline Mathematics
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Clinical Innovation</span>
        </div>
        <div class="slide-category">07 · Directional Circular Statistics</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Circular EWMA Routine Learning Engine</h1>
        <p class="slide-subtitle">Trigonometric unit circle projection eliminating the catastrophic midnight wrap-around bug.</p>
      </div>

      <div class="slide-body" style="gap: 36px; align-items: center;">
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 20px;">
          <div class="card-panel" style="border-color: rgba(0, 202, 255, 0.25);">
            <h3 style="font-size: 20px; font-weight: 800; color: #00CAFF; margin-bottom: 12px;">The Midnight Wrap-Around Flaw</h3>
            <p style="font-size: 15px; color: #94a3b8; line-height: 1.6;">
              When elders take medication near midnight (e.g. 11:50 PM = 1430 mins and 12:10 AM = 10 mins), standard linear arithmetic averages them to <strong style="color: #ef4444;">12:00 PM (noon)</strong>—a 12-hour error that breaks traditional telecare alarm algorithms!
            </p>
          </div>

          <div class="card-panel">
            <h3 style="font-size: 20px; font-weight: 800; color: #10b981; margin-bottom: 12px;">CareLoop Trigonometric Unit Circle Solution</h3>
            <p style="font-size: 15px; color: #94a3b8; line-height: 1.6;">
              Projects every minute-of-day onto the 24-hour trigonometric circle (&theta; = 2&pi; &middot; t / 1440):
            </p>
            <div style="margin-top: 14px; padding: 14px; background: rgba(0,0,0,0.3); border-radius: 10px; font-size: 14px; line-height: 1.7;" class="mono">
              x&#772; = (1/N) &sum; cos(&theta;<sub>i</sub>), &nbsp; y&#772; = (1/N) &sum; sin(&theta;<sub>i</sub>)<br/>
              Resultant Vector: R = &radic;(x&#772;<sup>2</sup> + y&#772;<sup>2</sup>)<br/>
              Circular Mean: &mu; = atan2(y&#772;, x&#772;)<br/>
              Circular Variance: &sigma; = &radic;(-2 ln R)
            </div>
            <p style="font-size: 14px; color: #10b981; margin-top: 12px; font-weight: 600;">
              ✓ Accurately averages 11:50 PM and 12:10 AM to 12:00 Midnight with zero distortion.
            </p>
          </div>
        </div>

        <!-- Right: Unit Circle Diagram -->
        <div style="flex: 0.9; display: flex; justify-content: center;">
          <div class="card-panel" style="width: 100%; max-width: 460px; padding: 32px; text-align: center; border-color: rgba(0, 202, 255, 0.2);">
            <h4 style="font-size: 16px; font-weight: 700; color: #ffffff; margin-bottom: 20px;">24-Hour Trigonometric Routine Clock</h4>
            <div style="position: relative; width: 280px; height: 280px; margin: 0 auto; border: 2px dashed rgba(0, 202, 255, 0.3); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
              <!-- Clock Labels -->
              <div style="position: absolute; top: 10px; font-size: 12px; font-weight: 700; color: #00CAFF;">00:00 (Midnight)</div>
              <div style="position: absolute; right: 10px; font-size: 12px; font-weight: 700; color: #94a3b8;">06:00 (Wake)</div>
              <div style="position: absolute; bottom: 10px; font-size: 12px; font-weight: 700; color: #10b981;">12:00 (Lunch)</div>
              <div style="position: absolute; left: 10px; font-size: 12px; font-weight: 700; color: #94a3b8;">18:00 (Dinner)</div>

              <!-- Confidence Arc -->
              <div style="width: 140px; height: 140px; border-radius: 50%; border: 4px solid #10b981; background: rgba(16, 185, 129, 0.08); display: flex; flex-direction: column; align-items: center; justify-content: center;">
                <span style="font-size: 18px; font-weight: 800; color: #10b981;">&mu; &plusmn; 2&sigma;</span>
                <span style="font-size: 11px; color: #94a3b8;">Grace Window</span>
              </div>
            </div>

            <div style="margin-top: 24px; font-size: 13px; color: #cbd5e1; line-height: 1.5;">
              Pre-warmed with <strong style="color: #00CAFF;">1,422 historical telemetry pings</strong> to maintain continuous circadian stability.
            </div>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Baseline Statistics · careloop/engine/baseline.py</div>
        <div>Directional Circular EWMA with Decay Factor &alpha; = 0.15</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 9: AWS Production Cloud Architecture
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Cloud Infrastructure</span>
        </div>
        <div class="slide-category">08 · AWS Production Cloud Architecture</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Serverless & Containerized AWS Architecture</h1>
        <p class="slide-subtitle">High-availability deployment on AWS ECS Fargate, DynamoDB, EventBridge Scheduler, and Bedrock.</p>
      </div>

      <div class="slide-body" style="gap: 28px; flex-direction: column; justify-content: center;">
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;">
          <!-- Col 1 -->
          <div class="card-panel" style="border-top: 4px solid #00CAFF;">
            <span class="tag tag-cyan" style="margin-bottom: 8px;">1. Voice & Transport</span>
            <h3 style="font-size: 18px; font-weight: 700; margin-bottom: 10px;">Echo & FastMCP</h3>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
              Amazon Echo Show devices connect over Streamable HTTP (/mcp). Application Load Balancer supports 300s long-lived streaming connections.
            </p>
          </div>

          <!-- Col 2 -->
          <div class="card-panel" style="border-top: 4px solid #10b981;">
            <span class="tag tag-emerald" style="margin-bottom: 8px;">2. Compute Core</span>
            <h3 style="font-size: 18px; font-weight: 700; margin-bottom: 10px;">AWS ECS Fargate</h3>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
              Dockerized Python 3.11 ASGI service running Starlette + Uvicorn with auto-scaling, constant-time bearer auth, and zero EC2 management.
            </p>
          </div>

          <!-- Col 3 -->
          <div class="card-panel" style="border-top: 4px solid #f59e0b;">
            <span class="tag tag-amber" style="margin-bottom: 8px;">3. State & Scheduler</span>
            <h3 style="font-size: 18px; font-weight: 700; margin-bottom: 10px;">DynamoDB & EventBridge</h3>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
              Single-table design with KMS encryption at rest. EventBridge Scheduler (ScheduleV2) triggers serverless 60s background tick runner.
            </p>
          </div>

          <!-- Col 4 -->
          <div class="card-panel" style="border-top: 4px solid #ef4444;">
            <span class="tag tag-rose" style="margin-bottom: 8px;">4. Notification & AI</span>
            <h3 style="font-size: 18px; font-weight: 700; margin-bottom: 10px;">Amazon SNS & Bedrock</h3>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.5;">
              KMS-encrypted mobile SMS alert topic for emergency caregiver dispatch. Bedrock Claude 3 Haiku Converse API for routine Q&A and daily summaries.
            </p>
          </div>
        </div>

        <!-- Architecture Flow Diagram Card -->
        <div class="card-panel" style="padding: 24px 32px; background: rgba(0, 0, 0, 0.4);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
            <span style="font-size: 14px; font-weight: 700; color: #00CAFF;">PRODUCTION FLOW PIPELINE</span>
            <span style="font-size: 12px; color: #94a3b8;" class="mono">AWS CDK (deploy/cdk/) · SAM (template.yaml)</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 13px; font-weight: 600;">
            <div style="padding: 12px 18px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.3); border-radius: 8px; text-align: center;">Echo Show 10<br/><span style="font-size: 11px; color: #94a3b8;">Voice Utterance</span></div>
            <span style="color: #00CAFF;">&rarr;</span>
            <div style="padding: 12px 18px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.3); border-radius: 8px; text-align: center;">AWS ALB<br/><span style="font-size: 11px; color: #94a3b8;">300s Streaming Timeout</span></div>
            <span style="color: #00CAFF;">&rarr;</span>
            <div style="padding: 12px 18px; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; text-align: center;">ECS Fargate<br/><span style="font-size: 11px; color: #94a3b8;">FastMCP Core Engine</span></div>
            <span style="color: #10b981;">&rarr;</span>
            <div style="padding: 12px 18px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; text-align: center;">DynamoDB<br/><span style="font-size: 11px; color: #94a3b8;">Single-Table KMS PK/SK</span></div>
            <span style="color: #f59e0b;">&rarr;</span>
            <div style="padding: 12px 18px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; text-align: center;">Amazon SNS<br/><span style="font-size: 11px; color: #94a3b8;">KMS Encrypted Caregiver SMS</span></div>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Cloud Infrastructure · deploy/cdk/ & template.yaml · AWS Builder Challenge</div>
        <div>Serverless Tick Runner Lambda + Dead-Letter Queue (DLQ) Retry Policies</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 10: Multi-Persona Care Profiles
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Multi-Persona</span>
        </div>
        <div class="slide-category">09 · Diverse Elder Care Profiles</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Tailored Profiles for Diverse Clinical Needs</h1>
        <p class="slide-subtitle">Personalized circadian baselines, caregiver routing, and specialized medication schedules.</p>
      </div>

      <div class="slide-body" style="gap: 32px; align-items: center;">
        <!-- Persona 1: Arthur -->
        <div class="card-panel" style="flex: 1; text-align: center; border-color: rgba(0, 202, 255, 0.3); padding: 32px 24px;">
          <img src="{ARTHUR_B64}" alt="Arthur Davis" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid #00CAFF; margin: 0 auto 16px auto;" />
          <h3 style="font-size: 22px; font-weight: 800;">Arthur Davis (Dad)</h3>
          <div style="font-size: 14px; color: #00CAFF; font-weight: 600; margin-top: 2px;">Age 81 · Navy Veteran</div>
          <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">Living Independently in Single-Story Home</p>
          <div style="margin-top: 16px; text-align: left; background: rgba(0,0,0,0.3); padding: 14px; border-radius: 10px; font-size: 12px; line-height: 1.6;">
            <strong>Caregiver:</strong> Linda Davis (Daughter)<br/>
            <strong>Medication:</strong> Metoprolol Tartrate 25mg<br/>
            <strong>Sensors:</strong> Pillbox Tray 1, Living Room PIR<br/>
            <strong>Baseline Window:</strong> 08:00 AM &plusmn;30m
          </div>
          <span class="tag tag-emerald" style="margin-top: 16px;">Active · Nominal</span>
        </div>

        <!-- Persona 2: Eleanor -->
        <div class="card-panel" style="flex: 1; text-align: center; border-color: rgba(16, 185, 129, 0.3); padding: 32px 24px;">
          <img src="{ELEANOR_B64}" alt="Eleanor Vance" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid #10b981; margin: 0 auto 16px auto;" />
          <h3 style="font-size: 22px; font-weight: 800;">Eleanor Vance</h3>
          <div style="font-size: 14px; color: #10b981; font-weight: 600; margin-top: 2px;">Age 78 · Post-Op Recovery</div>
          <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">Assisted Walking & Physical Therapy</p>
          <div style="margin-top: 16px; text-align: left; background: rgba(0,0,0,0.3); padding: 14px; border-radius: 10px; font-size: 12px; line-height: 1.6;">
            <strong>Caregiver:</strong> Robert Vance (Son)<br/>
            <strong>Medication:</strong> Lisinopril 10mg + PT Walk<br/>
            <strong>Sensors:</strong> Hallway Motion, Bed Sensor<br/>
            <strong>Baseline Window:</strong> 09:00 AM &plusmn;45m
          </div>
          <span class="tag tag-emerald" style="margin-top: 16px;">Active · Post-Op Nominal</span>
        </div>

        <!-- Persona 3: Martha -->
        <div class="card-panel" style="flex: 1; text-align: center; border-color: rgba(245, 158, 11, 0.3); padding: 32px 24px;">
          <img src="{MARTHA_B64}" alt="Martha Higgins" style="width: 120px; height: 120px; border-radius: 50%; object-fit: cover; border: 3px solid #f59e0b; margin: 0 auto 16px auto;" />
          <h3 style="font-size: 22px; font-weight: 800;">Martha Higgins</h3>
          <div style="font-size: 14px; color: #f59e0b; font-weight: 600; margin-top: 2px;">Age 84 · Memory Assistance</div>
          <p style="font-size: 13px; color: #94a3b8; margin-top: 8px;">Condo Living with Frequent Hydration Checks</p>
          <div style="margin-top: 16px; text-align: left; background: rgba(0,0,0,0.3); padding: 14px; border-radius: 10px; font-size: 12px; line-height: 1.6;">
            <strong>Caregiver:</strong> Sarah Jenkins (Niece)<br/>
            <strong>Medication:</strong> Donepezil 5mg + Hydration<br/>
            <strong>Sensors:</strong> Refrigerator Contact, Door Sensor<br/>
            <strong>Baseline Window:</strong> 08:30 AM &plusmn;20m
          </div>
          <span class="tag tag-amber" style="margin-top: 16px;">Active · Memory Tracking</span>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Multi-Persona Engine · Switching via UI Dropdown or MCP Tool Call</div>
        <div>Isolated SQLite & DynamoDB Storage Partitioned by person_id PK</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 11: Testing Lab & Injectable Clock Time Machine
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Testing Lab</span>
        </div>
        <div class="slide-category">10 · Time Machine & Simulation Controls</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Injectable Clock Time Machine & Testing Cockpit</h1>
        <p class="slide-subtitle">Advance simulated clock and trigger emergency scenarios instantly without waiting real hours.</p>
      </div>

      <div class="slide-body" style="gap: 36px; align-items: center;">
        <div style="flex: 1.1; display: flex; flex-direction: column; gap: 20px;">
          <div class="card-panel" style="border-color: rgba(0, 202, 255, 0.25);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
              <h3 style="font-size: 20px; font-weight: 800; color: #00CAFF;">Injectable SimulatedClock</h3>
              <span class="tag tag-cyan">Deterministic Time Travel</span>
            </div>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.6;">
              Testing elder safety routines requires simulating the progression of an entire day.
              The backend <code>SimulatedClock</code> allows time-travel jumps with instantaneous escalation evaluations:
            </p>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 16px;">
              <div style="padding: 10px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 8px; text-align: center; font-size: 13px; font-weight: 700; color: #00CAFF;">+15 Mins</div>
              <div style="padding: 10px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 8px; text-align: center; font-size: 13px; font-weight: 700; color: #00CAFF;">+1 Hour</div>
              <div style="padding: 10px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 8px; text-align: center; font-size: 13px; font-weight: 700; color: #00CAFF;">+3 Hours</div>
              <div style="padding: 10px; background: rgba(0, 202, 255, 0.1); border: 1px solid rgba(0, 202, 255, 0.25); border-radius: 8px; text-align: center; font-size: 13px; font-weight: 700; color: #00CAFF;">↺ Reset (08:15)</div>
            </div>
          </div>

          <div class="card-panel" style="border-color: rgba(239, 68, 68, 0.25);">
            <h3 style="font-size: 18px; font-weight: 800; color: #ef4444; margin-bottom: 8px;">Automated Hackathon Demo Scenarios</h3>
            <p style="font-size: 14px; color: #94a3b8; line-height: 1.5;">
              Pre-programmed 1-click test suites simulate:
            </p>
            <ul style="font-size: 13px; color: #cbd5e1; margin-top: 8px; padding-left: 20px; line-height: 1.6;">
              <li><strong>"Dad Skips Lunch":</strong> Seeds morning routines, advances clock to 2:00 PM, triggers Stage 2 & 3 voice checks, and escalates to Stage 4 SNS alert.</li>
              <li><strong>"Missed Morning Beta-Blocker":</strong> Bypasses smart pillbox check, triggers high-priority medication reminder over Echo Show.</li>
            </ul>
          </div>
        </div>

        <div style="flex: 0.9; display: flex; flex-direction: column; gap: 20px;">
          <div class="card-panel" style="background: #0b111c; border-color: rgba(16, 185, 129, 0.3);">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
              <span class="tag tag-emerald">Zero-Config Offline</span>
              <h4 style="font-size: 16px; font-weight: 700;">100% Offline SQLite Fallback</h4>
            </div>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.6;">
              Hackathon judges and developers can test the entire pipeline locally without AWS account credentials.
              The server seamlessly falls back to <code>careloop_local.db</code> with pre-warmed circadian observations.
            </p>
          </div>

          <div class="card-panel" style="background: #0b111c;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
              <span class="tag tag-amber">Audit Security</span>
              <h4 style="font-size: 16px; font-weight: 700;">Time Manipulation Guardrails</h4>
            </div>
            <p style="font-size: 13px; color: #94a3b8; line-height: 1.6;">
              Clock manipulation endpoints (/api/clock/*) are automatically disabled in production (<code>ENV=production</code>) to guarantee audit integrity.
            </p>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop Simulation Engine · careloop/simulator/index.html & careloop/engine/clock.py</div>
        <div>Fast Timeouts Mode: 60s Gentle / 60s Repeat for Live Demonstrations</div>
      </div>
    </div>
    """)

    # -------------------------------------------------------------
    # SLIDE 12: Differentiation Matrix & Devpost Summary
    # -------------------------------------------------------------
    slides.append(f"""
    <div class="slide-container">
      <div class="slide-header">
        <div class="brand-group">
          <img src="{LOGO_B64}" class="brand-logo" alt="Logo" />
          <div class="brand-title">CareLoop</div>
          <span class="brand-pill">Competitive Edge</span>
        </div>
        <div class="slide-category">11 · Architectural Differentiation & Audit</div>
      </div>

      <div class="slide-title-wrap">
        <h1 class="slide-title">Architectural Differentiation & Quality Verification</h1>
        <p class="slide-subtitle">Proven clinical accuracy, rigorous automated testing, and permissive open source licensing.</p>
      </div>

      <div class="slide-body" style="gap: 28px; flex-direction: column; justify-content: center;">
        <!-- Comparison Table -->
        <table style="width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; background: #0f172a; border-radius: 12px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.08);">
          <thead>
            <tr style="background: rgba(255, 255, 255, 0.05); border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
              <th style="padding: 16px 20px; font-weight: 700; color: #94a3b8;">Architectural Dimension</th>
              <th style="padding: 16px 20px; font-weight: 700; color: #94a3b8;">Traditional Static Telecare</th>
              <th style="padding: 16px 20px; font-weight: 700; color: #94a3b8;">Generic LLM Chatbots</th>
              <th style="padding: 16px 20px; font-weight: 700; color: #00CAFF;">CareLoop (Alexa+ & FastMCP)</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
              <td style="padding: 14px 20px; font-weight: 700;">Alarm Decision Logic</td>
              <td style="padding: 14px 20px; color: #ef4444;">Rigid static timers ("alarm at 8:00 AM sharp")</td>
              <td style="padding: 14px 20px; color: #f59e0b;">Non-deterministic probabilistic LLM hallucinations</td>
              <td style="padding: 14px 20px; color: #10b981; font-weight: 700;">Deterministic Circular EWMA statistics with personal grace windows</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
              <td style="padding: 14px 20px; font-weight: 700;">Privacy & Surveillance</td>
              <td style="padding: 14px 20px; color: #ef4444;">Intrusive video cameras or wearable panic buttons</td>
              <td style="padding: 14px 20px; color: #f59e0b;">Transfers raw audio recordings to third-party APIs</td>
              <td style="padding: 14px 20px; color: #10b981; font-weight: 700;">Discrete sensor pings only. Zero raw audio or video captured.</td>
            </tr>
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
              <td style="padding: 14px 20px; font-weight: 700;">Escalation Architecture</td>
              <td style="padding: 14px 20px; color: #ef4444;">Binary sirens causing severe false alarm fatigue</td>
              <td style="padding: 14px 20px; color: #f59e0b;">Uncontrolled multi-turn conversational loops</td>
              <td style="padding: 14px 20px; color: #10b981; font-weight: 700;">Deterministic 4-stage state machine (Normal &rarr; Gentle &rarr; Repeat &rarr; SMS)</td>
            </tr>
            <tr>
              <td style="padding: 14px 20px; font-weight: 700;">Offline Reliability</td>
              <td style="padding: 14px 20px; color: #f59e0b;">Proprietary closed-source local hubs</td>
              <td style="padding: 14px 20px; color: #ef4444;">100% cloud dependent; offline failure</td>
              <td style="padding: 14px 20px; color: #10b981; font-weight: 700;">Dual-backend: AWS Cloud (DynamoDB+Fargate) or 100% Offline SQLite</td>
            </tr>
          </tbody>
        </table>

        <!-- Quality Metrics Grid -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;">
          <div class="card-panel" style="padding: 18px; text-align: center;">
            <div style="font-size: 28px; font-weight: 800; color: #00CAFF;">178 / 178</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Passing Unit & Integration Tests</div>
          </div>
          <div class="card-panel" style="padding: 18px; text-align: center;">
            <div style="font-size: 28px; font-weight: 800; color: #10b981;">79% Coverage</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Statement Code Coverage</div>
          </div>
          <div class="card-panel" style="padding: 18px; text-align: center;">
            <div style="font-size: 28px; font-weight: 800; color: #f59e0b;">0 Vulnerabilities</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Bandit + detect-secrets + pip-audit Clean</div>
          </div>
          <div class="card-panel" style="padding: 18px; text-align: center;">
            <div style="font-size: 28px; font-weight: 800; color: #a855f7;">MIT License</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Permissive Open Source Repository</div>
          </div>
        </div>
      </div>

      <div class="slide-footer">
        <div>CareLoop · Amazon Developer Hackathon Submission Package · MIT License</div>
        <div>Built with FastMCP, Starlette, React 18, Tailwind CSS, AWS CDK & Python 3.11</div>
      </div>
    </div>
    """)

    # Wrap in HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>CareLoop · Project Media Submission Package</title>
  <style>
{COMMON_CSS}
  </style>
</head>
<body>
{"".join(slides)}
</body>
</html>
"""
    return slides, html_content


def main():
    import tempfile

    print("Generating slides HTML...")
    slides, html_content = generate_slides_html()
    slides_file = MEDIA_DIR / "slides.html"
    with open(slides_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Written slides HTML to: {slides_file} ({len(html_content)} bytes)")

    # 1. Generate multi-page 3:2 PDF
    pdf_output = WORKSPACE_DIR / "CareLoop_Project_Media.pdf"
    media_pdf_output = MEDIA_DIR / "CareLoop_Project_Media.pdf"
    print(f"Generating 3:2 aspect ratio PDF: {pdf_output} ...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [
            EDGE_BIN,
            "--headless",
            "--disable-gpu",
            f"--user-data-dir={tmp_dir}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_output}",
            f"file://{slides_file}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"✓ PDF successfully generated at: {pdf_output}")
            shutil.copyfile(pdf_output, media_pdf_output)
        else:
            print(f"✗ Error generating PDF: {res.stderr}")

    # 2. Generate individual 3:2 slides for Devpost Image Gallery
    # Devpost specs: "JPG, PNG or GIF format, 5 MB max file size. For best results, use a 3:2 ratio. Up to 15 images."
    print("Generating individual 3:2 images for Devpost Image Gallery...")

    slide_names = [
        "01_careloop_hero_cover_3x2",
        "02_ambient_hero_dashboard_3x2",
        "03_alexa_ambient_voice_console_3x2",
        "04_daily_routine_schedule_3x2",
        "05_family_care_circle_gateway_3x2",
        "06_cockpit_simulator_overview_3x2",
        "07_autonomous_4stage_escalation_3x2",
        "08_circular_ewma_baseline_math_3x2",
        "09_aws_cloud_architecture_3x2",
        "10_multi_persona_profiles_3x2",
        "11_time_machine_simulation_lab_3x2",
        "12_differentiation_matrix_audit_3x2",
    ]

    for idx, (name, slide_html) in enumerate(zip(slide_names, slides, strict=False)):
        single_html_file = MEDIA_DIR / f"{name}.html"
        single_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
{COMMON_CSS}
  </style>
</head>
<body style="width: 1800px; height: 1200px; overflow: hidden; margin: 0; padding: 0;">
{slide_html}
</body>
</html>
"""
        with open(single_html_file, "w", encoding="utf-8") as f:
            f.write(single_html)

        png_output = MEDIA_DIR / f"{name}.png"
        jpg_output = MEDIA_DIR / f"{name}.jpg"

        print(f"Capturing slide {idx + 1}/{len(slide_names)}: {name}.png (1800x1200, 3:2 ratio)...")
        with tempfile.TemporaryDirectory() as tmp_dir:
            cap_cmd = [
                EDGE_BIN,
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={tmp_dir}",
                "--window-size=1800,1200",
                f"--screenshot={png_output}",
                f"file://{single_html_file}",
            ]
            cap_res = subprocess.run(cap_cmd, capture_output=True, text=True)
            if cap_res.returncode == 0 and png_output.exists():
                im = Image.open(png_output)
                rgb_im = im.convert("RGB")
                rgb_im.save(jpg_output, "JPEG", quality=92, optimize=True)
                png_size = png_output.stat().st_size / (1024 * 1024)
                jpg_size = jpg_output.stat().st_size / (1024 * 1024)
                print(f"  ✓ Saved PNG ({png_size:.2f} MB) and JPG ({jpg_size:.2f} MB)")
                single_html_file.unlink(missing_ok=True)
            else:
                print(f"  ✗ Failed to capture {name}: {cap_res.stderr}")

    print("\nAll Project Media generation complete!")
    print(f"PDF Location: {pdf_output}")
    print(f"Gallery Images Location: {MEDIA_DIR}")


if __name__ == "__main__":
    main()
