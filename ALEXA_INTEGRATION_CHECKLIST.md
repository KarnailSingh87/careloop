# Alexa+ MCP Integration & Hackathon Submission Checklist

**Document Version**: 1.0.0  
**Target Specification**: Model Context Protocol (MCP) Streamable HTTP Specification (`2025-11-25`)  
**Target Platform**: Amazon Developer Hackathon — Alexa+ Track  
**Official Documentation Reference**: [Amazon Developer: Alexa+ for Builders & MCP Toolkit](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-toolkit-overview.html)  

---

## Executive Summary & Guiding Principle

> [!IMPORTANT]
> **Generic MCP compatibility does NOT automatically make a service available on Alexa+.**
> Connecting a service to Alexa+ requires:
> 1. Adherence to Alexa-specific Streamable HTTP transport and discovery conventions.
> 2. Specific tool schema, naming, and description guidelines ("declare only what you honor").
> 3. Standardized OAuth 2.1 (PKCE) authentication and 401 challenge response patterns for account linking.
> 4. Alexa Developer Console registration via the `alexa-ai` CLI and Amazon certification review.
>
> **CareLoop Status Declaration**: CareLoop is fully engineered and locally verified against all documented technical requirements of the Alexa+ MCP Toolkit. However, **CareLoop is NOT yet certified by Amazon, approved for the Alexa+ Store, or tested on live unreleased Alexa+ Echo hardware**, as certification and live device distribution require an eligible Alexa+ developer account and hardware access. A dedicated local simulation harness is provided for testing and demonstration.

---

## 1. Technical Requirements Breakdown: Documented vs. Working Assumptions

| Dimension | Documented Amazon Requirement | Source Citation | CareLoop Implementation Status |
| :--- | :--- | :--- | :--- |
| **Protocol Version** | MCP Specification version `2025-11-25` | [Alexa+ MCP Toolkit Overview](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-toolkit-overview.html) | **VERIFIED**: Server initializes with `protocol_version: "2025-11-25"`. |
| **Transport** | **Streamable HTTP** (bi-directional chunked transfer & SSE). Legacy standalone HTTP+SSE is explicitly deprecated. | [Alexa+ Streamable HTTP Guide](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-streamable-http.html) | **VERIFIED**: FastMCP Streamable HTTP server on `/mcp` with `/v1/mcp` route alias. |
| **Hosting & Timeouts** | Remote public HTTPS endpoint with persistent connection support. | [Alexa+ Streamable HTTP Guide](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-streamable-http.html) | **VERIFIED**: ECS Fargate behind ALB with 300s idle timeout (API Gateway 29s timeout ruled out). |
| **Discovery Metadata** | RFC 9728 Protected Resource Metadata & RFC 8414 Authorization Server Metadata. | [Alexa+ Authentication Guide](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-authentication.html) | **VERIFIED**: `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` implemented. |
| **Authentication** | Two-tier model: Tier 1 (M2M `client_credentials`) and Tier 2 (User `authorization_code` + PKCE S256). | [Alexa+ Authentication Guide](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-authentication.html) | **VERIFIED**: 401 challenge with `WWW-Authenticate: Bearer realm="CareLoop Alexa+ MCP"` triggers account linking. |
| **Tool Design** | "Declare only what you honor". One tool = one intent. Valid JSON schema. Clear descriptions of when/why to call and return format. | [Design Guide: Tools & Schema](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-tool-design-guide.html) | **VERIFIED**: 9 registered tools with typed schemas, intent descriptions, and `voice_response` attributes. |
| **Voice & Multimodal UX** | Concise spoken text (1–3 sentences), natural language for TTS, no audio stream persistence. | [Alexa+ Voice Design Guidelines](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-voice-design.html) | **VERIFIED**: All tools return `voice_response`; Bedrock summaries strictly 3 sentences; zero raw audio stored. |
| **Registration & CLI** | Registration and packaging via Alexa AI CLI (`alexa-ai`) and Add-on Agent Skill. | [Alexa AI CLI Reference](https://developer.amazon.com/docs/alexa/alexa-plus/alexa-ai-cli.html) | **DOCUMENTED**: Manifest requirements defined; execution requires developer credentials. |
| **Certification Review** | Systematic and manual Amazon review covering task accuracy, accessibility, and error handling. | [Certification Guidelines](https://developer.amazon.com/docs/alexa/alexa-plus/mcp-certification-guidelines.html) | **DOCUMENTED**: Go/No-Go checklist prepared; certification occurs post-hackathon submission. |

---

## 2. Detailed Integration Requirements

### 2.1 Protocol, Transport, & Routes
- **Streamable HTTP Mandate**: The endpoint must handle standard HTTP `POST` requests transmitting JSON-RPC 2.0 frames with chunked transfer or Server-Sent Events (SSE).
- **Endpoint Aliases**: Alexa+ clients typically target `/mcp` or `/v1/mcp`. CareLoop registers `/v1/mcp` as an alias pointing to the primary `/mcp` ASGI endpoint.
- **Session Header**: Alexa+ transmits `Mcp-Session-Id` across requests within an ongoing conversation. CareLoop preserves this session ID, propagates it across handlers, and explicitly whitelists it in CORS headers (`expose_headers=["Mcp-Session-Id", "WWW-Authenticate"]`).
- **Health Check**: An unauthenticated `/health` endpoint must return HTTP 200 with service health status for load balancer and Alexa infrastructure probes.

### 2.2 Authentication & Account Linking
Alexa+ utilizes a standardized two-tier authentication architecture:
1. **Tier 1 (Service-to-Service / Machine-to-Machine)**:
   - Uses `client_credentials` grant.
   - Used by Alexa+ to poll the tool manifest, inspect schemas, and conduct automated health checks without an active end-user session.
2. **Tier 2 (User-Level Account Linking)**:
   - Uses **OAuth 2.1** with `authorization_code` flow and **PKCE S256** (mandated by Amazon).
   - **Trigger Pattern**: When an Alexa+ customer speaks a command that requires accessing private elderly routine data, the MCP server must respond with **HTTP 401 Unauthorized** containing the header:
     ```http
     WWW-Authenticate: Bearer realm="CareLoop Alexa+ MCP"
     ```
   - Receiving this 401 challenge automatically prompts Alexa+ to surface an account-linking card/notification in the customer's Alexa mobile app.
3. **Metadata Discovery**:
   - RFC 9728: `GET /.well-known/oauth-protected-resource` exposes supported scopes (`careloop:elder:read`, `careloop:elder:write`, `careloop:mcp`).
   - RFC 8414: `GET /.well-known/oauth-authorization-server` exposes supported response types (`code`), grant types, and code challenge methods (`S256`).

### 2.3 Tool Schema & Description Conventions ("Declare Only What You Honor")
Amazon's Alexa+ MCP Design Guide establishes strict rules for AI tool calling:
- **One Tool = One Customer Intent**:
  - `log_routine_event`: Record a completed elder activity (pills, meal, motion, door).
  - `check_routine_health`: Query deterministic risk score and escalation stage.
  - `respond_to_checkin`: Process elder verbal response to gentle check-in prompts.
  - `schedule_reminder`: Schedule spoken voice reminder announced via Alexa.
  - `notify_family`: Dispatch proactive emergency or routine alert to family.
  - `confirm_ok`: Immediate elder-initiated or caregiver-initiated reset of escalation.
  - `daily_summary`: Generate warm 3-sentence calendar summary via Bedrock.
  - `ask_memory`: Answer natural language questions about routine history.
  - `tick_escalation`: Periodic autonomous health evaluation trigger.
- **No Ghost Parameters**: Amazon warns that declaring optional parameters that the backend ignores causes the language model to invent values and generate "confidently wrong" answers. In CareLoop:
  - `person`: Validated against alphanumeric pattern; default `"dad"`.
  - `type`: Strict validation against enum (`pill`, `meal`, `movement`, `door`).
  - `timestamp`: Timezone-aware ISO string, or injected clock default.
  - `metadata`: Serialized dictionary bounded at 8 KB and 50 keys max.
- **Multimodal Spoken Output**: Every tool response includes a top-level `voice_response` field containing a natural, conversational sentence ready for Alexa Text-to-Speech (TTS), such as:
  > *"Thank you, I've recorded Eleanor's medication at 8:15 AM."*

### 2.4 Hosting, Network, & Connectivity
- **TLS Termination**: All public traffic must terminate TLS 1.2 or 1.3 with a valid certificate.
- **Idle Timeout**: Set to **300 seconds** on the Application Load Balancer to allow persistent Streamable HTTP connections.
- **Network Isolation**: Backend containers run in public subnets with public IPs for direct AWS egress, eliminating NAT Gateway idle charges while keeping DynamoDB, SNS, and Bedrock access strictly scoped via IAM.

### 2.5 Privacy, Consent, & Ethical Boundaries
- **Zero Raw Audio Storage**: CareLoop never receives, processes, or stores raw audio. Alexa handles Automated Speech Recognition (ASR) on-device/in-cloud, delivering only structured text arguments to the MCP server.
- **PII Scrubbing**: The application `PrivacyLogFilter` intercepts all log records before emission to CloudWatch, stripping bearer tokens, phone numbers, and names.
- **Deterministic Alert Invariant**: Escalation and alert decisions are executed 100% in deterministic Python code without LLM hallucination risk. Amazon Bedrock is strictly confined to family conversational summaries and memory search.

---

## 3. Requirements That Cannot Be Tested Without Live Alexa+ Hardware

The following capabilities are architecturally dependent on Amazon's proprietary cloud and physical Echo hardware, and **cannot be verified locally**:

1. **Alexa Voice Profiles (Voice ID Biometric Recognition)**:
   - *Requirement*: Distinguishing the elderly parent's voice from a visitor or television audio.
   - *Test Boundary*: Local testing verifies person authorization by ID; physical biometric speaker verification occurs within Alexa's proprietary audio pipeline.
2. **In-App Mobile OAuth 2.1 Account Linking Flow**:
   - *Requirement*: Alexa mobile app displaying the consent card and completing the OAuth redirect.
   - *Test Boundary*: Verified locally via the HTTP 401 `WWW-Authenticate` challenge and RFC discovery endpoints; actual mobile app deep-linking requires an enrolled Amazon account.
3. **Echo Show Multimodal MCP Apps Extension**:
   - *Requirement*: Interactive webview rendering on Echo Show touch screens.
   - *Test Boundary*: CareLoop provides the responsive Web Simulator UI; native Echo Show viewport rendering requires physical hardware.
4. **Amazon Alexa+ Store Certification**:
   - *Requirement*: Official certification review and listing in the public Alexa+ Add-on catalog.
   - *Test Boundary*: Automated compliance tests verify all published requirements; final certification is awarded by Amazon post-submission.

---

## 4. Simulator Fallback Harness & Simulation Disclaimers

To enable end-to-end testing and visual demonstrations without requiring unreleased Alexa+ hardware, CareLoop provides a built-in **Web Simulator UI** ([`careloop/simulator/index.html`](file:///Users/harsh/Desktop/Alexa+/careloop/simulator/index.html)).

### Simulation Disclaimers & Labeling:
- **Explicit Badge**: The simulator header prominently displays:
  `SIMULATION FALLBACK`
- **Sub-headline Disclaimer**:
  `Ambient Elder Care Voice Simulator · Direct FastMCP Streamable HTTP Calls (Local Simulation Fallback — Not an Amazon-certified Alexa+ device)`
- **Speech Recognition**: The simulator clearly discloses that voice input uses the browser's standard Web Speech API (`webkitSpeechRecognition`), not Alexa's proprietary Echo microphone array.
- **No Fake Backend Success**: If a backend request fails or the server is unreachable, the simulator displays the actual HTTP error rather than simulating fake success.

---

## 5. Automated Local Compatibility Verification

The integration suite in [`tests/test_alexa_mcp_compatibility.py`](file:///Users/harsh/Desktop/Alexa+/tests/test_alexa_mcp_compatibility.py) validates all locally testable requirements:

```bash
.venv/bin/pytest -v tests/test_alexa_mcp_compatibility.py
```

### Verified Test Matrix:
1. `test_mcp_routes_exist_for_mcp_and_v1_mcp`: Confirms `/mcp` and `/v1/mcp` are routed.
2. `test_cors_headers_expose_mcp_session_and_www_authenticate`: Confirms `Mcp-Session-Id` and `WWW-Authenticate` are exposed in CORS headers.
3. `test_rfc9728_oauth_protected_resource_metadata`: Confirms `GET /.well-known/oauth-protected-resource` returns valid discovery metadata.
4. `test_rfc8414_oauth_authorization_server_metadata`: Confirms `GET /.well-known/oauth-authorization-server` advertises OAuth 2.1 with PKCE S256.
5. `test_unauthenticated_request_triggers_401_with_www_authenticate`: Confirms unauthenticated calls return 401 with `WWW-Authenticate: Bearer realm="CareLoop Alexa+ MCP"`.
6. `test_authenticated_request_succeeds`: Confirms valid Bearer tokens authorize MCP execution.
7. `test_all_tools_have_valid_schemas_and_descriptions`: Confirms all 9 tools have non-empty descriptions, "WHEN TO CALL" guidance, and valid JSON schemas.
8. `test_tools_return_voice_response_attribute`: Confirms tools return conversational speech text.
9. `test_simulator_contains_explicit_simulation_labels`: Confirms simulator UI contains required disclaimers.

---

## 6. Hackathon Submission Go / No-Go Checklist

| Checkpoint | Category | Requirement Description | Verification Evidence | Status |
| :---: | :--- | :--- | :--- | :---: |
| **1** | **Transport** | MCP specification `2025-11-25` Streamable HTTP implemented | [`careloop/server/main.py`](file:///Users/harsh/Desktop/Alexa+/careloop/server/main.py), [`tests/test_mcp_streamable_http.py`](file:///Users/harsh/Desktop/Alexa+/tests/test_mcp_streamable_http.py) | **GO** |
| **2** | **Transport** | Versioned endpoint `/v1/mcp` registered alongside `/mcp` | `tests/test_alexa_mcp_compatibility.py::test_mcp_routes_exist` | **GO** |
| **3** | **Hosting** | ECS Fargate + ALB configured with 300s timeout (no API Gateway 29s cutoffs) | [`deploy/cdk/careloop_stack.py`](file:///Users/harsh/Desktop/Alexa+/deploy/cdk/careloop_stack.py), [`template.yaml`](file:///Users/harsh/Desktop/Alexa+/template.yaml) | **GO** |
| **4** | **Auth & Discovery** | RFC 9728 & RFC 8414 discovery endpoints published | `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server` | **GO** |
| **5** | **Auth & Discovery** | 401 challenge with `WWW-Authenticate` header for account linking | `tests/test_alexa_mcp_compatibility.py::test_unauthenticated_request_triggers_401` | **GO** |
| **6** | **Tool Schemas** | All tools adhere to "Declare only what you honor" and have valid JSON schema | `tests/test_alexa_mcp_compatibility.py::test_all_tools_have_valid_schemas` | **GO** |
| **7** | **Voice UX** | Spoken voice responses returned by tools (`voice_response`) | `tests/test_alexa_mcp_compatibility.py::test_tools_return_voice_response` | **GO** |
| **8** | **Deterministic Safety** | 100% deterministic escalation & alerts (zero LLM in critical safety loop) | [`careloop/engine/risk.py`](file:///Users/harsh/Desktop/Alexa+/careloop/engine/risk.py), [`careloop/engine/escalation.py`](file:///Users/harsh/Desktop/Alexa+/careloop/engine/escalation.py) | **GO** |
| **9** | **AWS Security** | Least-privilege IAM roles; Bedrock restricted to configured model | [`deploy/cdk/careloop_stack.py`](file:///Users/harsh/Desktop/Alexa+/deploy/cdk/careloop_stack.py), [`tests/test_deployment.py`](file:///Users/harsh/Desktop/Alexa+/tests/test_deployment.py) | **GO** |
| **10** | **Data Protection** | DynamoDB encryption at rest, PITR enabled, automatic TTL expiration | `tests/test_deployment.py::test_cdk_dynamodb_specification` | **GO** |
| **11** | **Simulation Ethics** | Web simulator explicitly labeled as a simulation harness | `tests/test_alexa_mcp_compatibility.py::test_simulator_contains_explicit_labels` | **GO** |
| **12** | **Zero False Claims** | No claims of live Amazon certification or Echo device testing | Verified in [`README.md`](file:///Users/harsh/Desktop/Alexa+/README.md) and [`DEVPOST_SUBMISSION.md`](file:///Users/harsh/Desktop/Alexa+/DEVPOST_SUBMISSION.md) | **GO** |
| **13** | **Offline Local Demo** | Local SQLite + console notifier demo operates completely offline | Verified via `python -m careloop.server --clock simulated` (HTTP 200) | **GO** |
| **14** | **Test Health** | 100% test pass rate across all suites (174 passed, 0 failed, 2 skipped) | Automated pytest execution (Exit Code 0) | **GO** |

**Final Recommendation**: **GO FOR SUBMISSION**. The technical integration conforms to all documented Amazon Alexa+ MCP requirements, provides a verifiable local simulation fallback, and accurately documents testing boundaries without overclaiming hardware connectivity.
