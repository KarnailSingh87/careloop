# CareLoop Hackathon Friction Log

A transparent record of engineering obstacles, unexpected behaviors, and developer friction encountered while building **CareLoop** for the Amazon Developer Hackathon (Alexa+ Track, AWS Builder, and Open Source Mini-Challenges).

---

## Format Reference
Each entry details:
- **Task Attempted**: The specific feature or integration being built.
- **Steps Taken**: Concrete actions executed.
- **Expected vs. Actual**: The discrepancy observed.
- **Severity**: Low, Medium, High, or Critical.
- **Workaround**: Immediate solution adopted in the repository.
- **Suggestion**: Recommendations for SDK maintainers or AWS platform teams.

---

## Entries

### 1. FastMCP Streamable HTTP Session Task Group Requires Lifespan Context

- **Task Attempted**: Expose CareLoop MCP tools over the official `streamable-http` transport using FastMCP and Starlette ASGI.
- **Steps Taken**: Initialized `server = FastMCP("CareLoop")`, called `app = server.streamable_http_app()`, mounted custom routes (`/simulator`, `/health`), and launched Uvicorn.
- **Expected vs. Actual**: Expected incoming HTTP connections to `/mcp` to initialize session streams immediately; instead, requests crashed with:
  ```
  RuntimeError: Task group is not initialized. Ensure app is run within lifespan context.
  ```
- **Severity**: High (blocked all Streamable HTTP client connections).
- **Workaround**: Explicitly wrapped Starlette's `app.router.lifespan_context` in an `@asynccontextmanager` function (`lifespan_wrapper`) so FastMCP's internal anyio/asyncio task group is cleanly started during server boot and torn down on shutdown.
- **Suggestion**: The FastMCP Python SDK documentation should explicitly highlight that `streamable_http_app()` must run within an active ASGI lifespan context, or FastMCP should lazily initialize an internal task group when invoked outside a full lifespan harness.

---

### 2. Circular EWMA Baseline Cold-Start Suppression Across Server Restarts

- **Task Attempted**: Evaluate routine health and detect anomalies immediately upon server startup using historical event logs.
- **Steps Taken**: Started the server with an empty in-memory `BaselineEngine` and issued `check_routine_health("dad")` when Dad had 60 days of prior events in SQLite.
- **Expected vs. Actual**: Expected the server to flag a skipped lunch; instead, the cold-start rule ($N < 5$ observations) suppressed all anomalies, returning `risk_score = 0.0`.
- **Severity**: Medium (caused false negatives on fresh server restarts).
- **Workaround**: Implemented `BaselineEngine.load_from_storage(storage)` in `careloop/server/main.py`. On startup, the server replays all historical routine logs, pre-warming EWMA time-of-day and variance statistics so cold-start suppression is bypassed immediately for known elders.
- **Suggestion**: State-dependent AI agents using MCP should incorporate an explicit startup lifecycle hook (e.g., `prewarm_hook` / `on_session_start`) to hydrate statistical baseline engines from pluggable storage layers.

---

### 3. Multi-Event Category Collision in Routine Window Matching

- **Task Attempted**: Detect missed lunch when both breakfast and lunch share the event category `meal`.
- **Steps Taken**: Filtered current day events by `event_type == "meal"` and checked if `len(meals_today) == 0`.
- **Expected vs. Actual**: Expected lunch to be flagged as missed at 1:45 PM; instead, Dad eating breakfast at 8:30 AM caused `len(meals_today) > 0`, falsely satisfying the daily meal routine and masking the missed lunch incident.
- **Severity**: High (clinical risk: suppressed nutritional neglect alerts).
- **Workaround**: Implemented routine window proximity matching in `BaselineEngine.check_missed_event()`. Instead of checking whole-day counts, the engine compares event timestamps against the expected time $\mu$ ($|\text{time} - \mu| \le \text{grace}$), ensuring an early breakfast cannot satisfy a midday lunch schedule.
- **Suggestion**: Smart home routine schemas should support structured sub-tags or dose indexes (e.g., `meal:breakfast`, `meal:lunch`, `medication:morning_dose`) rather than flat category strings alone.

---

### 4. Python Reserved Keyword `lambda` in Directory Paths

- **Task Attempted**: Package the EventBridge scheduled tick runner Lambda code under `deploy/lambda/tick_handler.py` and write unit tests in `tests/test_deployment.py`.
- **Steps Taken**: Created directory `deploy/lambda/` and wrote `from deploy.lambda.tick_handler import handler`.
- **Expected vs. Actual**: Expected pytest to collect and run tests; instead, pytest collection crashed with:
  ```
  SyntaxError: invalid syntax on line 11: from deploy.lambda.tick_handler import handler
  ```
- **Severity**: Medium (broke automated test suite collection).
- **Workaround**: Renamed the directory from `deploy/lambda/` to `deploy/tick_lambda/`.
- **Suggestion**: Avoid using programming language reserved keywords (`lambda`, `class`, `import`, `def`) as directory names in cross-language repositories.

---

### 5. AWS API Gateway 29-Second Hard Limit Incompatible with Streamable HTTP

- **Task Attempted**: Evaluate serverless deployment (AWS Lambda behind API Gateway HTTP API) for the CareLoop Streamable HTTP MCP server.
- **Steps Taken**: Benchmarked persistent streaming connections over API Gateway with Mangum ASGI adapter.
- **Expected vs. Actual**: Expected long-lived SSE / chunked transfer connections to stay open for continuous Alexa+ monitoring; instead, API Gateway buffers responses and enforces an unconfigurable 29-second maximum integration timeout, severing persistent MCP sessions.
- **Severity**: High (architectural failure for Streamable HTTP).
- **Workaround**: Deployed the containerized FastMCP server onto AWS ECS Fargate behind an Application Load Balancer (ALB). Configured the ALB idle timeout to 300 seconds, enabling persistent streaming without connection termination.
- **Suggestion**: AWS API Gateway should introduce opt-in streaming response timeouts for long-lived protocol connections (SSE / MCP / WebSockets), or AWS documentation should explicitly guide MCP developers toward ECS Fargate and AWS App Runner.

---

### 6. W3C CORS Specification: Credentialed Origin Reflection

- **Task Attempted**: Enable permissive CORS on the MCP server so browser-based tools and the Web Simulator can connect from any origin.
- **Steps Taken**: Configured Starlette's `CORSMiddleware` with `allow_origins=["*"]` and `allow_credentials=True`.
- **Expected vs. Actual**: Expected response header `Access-Control-Allow-Origin: *`; instead, Starlette dynamically reflected the exact requesting origin (e.g. `http://localhost:3000`).
- **Severity**: Low (unit test assertion failure).
- **Workaround**: Updated test assertions in `tests/test_auth.py` to assert that the reflected origin matches the incoming `Origin` header when credentials are permitted.
- **Suggestion**: Document that under the W3C CORS specification, wildcard `*` is prohibited when credentials (`allow_credentials=True`) are enabled, causing compliant middleware to echo the client's origin.

---

### 7. Storage Backend Decoupling in CLI Launcher

- **Task Attempted**: Launch CareLoop in a production AWS container using `STORAGE_BACKEND=dynamodb`.
- **Steps Taken**: Executed `python -m careloop.server` with environment variables `STORAGE_BACKEND=dynamodb` and `DYNAMODB_TABLE_NAME=CareLoopData`.
- **Expected vs. Actual**: Expected `DynamoDBStorage` to be instantiated; instead, `main()` had hardcoded `storage = SQLiteStorage(db_path=args.db)`.
- **Severity**: Medium (cloud deployment defaulted to local SQLite).
- **Workaround**: Added `--storage` and `--dynamo-table` command-line arguments to `careloop/server/main.py`, defaulting to environment variables `STORAGE_BACKEND` and `DYNAMODB_TABLE_NAME`.
- **Suggestion**: Always centralize backend factory resolution in `create_app()` / `create_server()` and avoid hardcoding fallback implementations inside the CLI argument parser.

---

### 8. Benchmark Fall/Inactivity Scheduling Overlap

- **Task Attempted**: Generate a synthetic 60-day dataset across 3 personas to benchmark incident detection.
- **Steps Taken**: Injected daytime fall events (`no_movement`) spanning 11:00 AM to 5:00 PM on incident test days.
- **Expected vs. Actual**: Expected to test fall detection independently; instead, the inactivity window overlapped with the 12:45 PM lunch schedule, triggering a secondary missed-lunch alert and confounding isolated false-positive metrics.
- **Severity**: Medium (benchmark metric ambiguity).
- **Workaround**: Decoupled incident test cases in `scripts/seed_data.py`. On fall incident days, morning lunch was completed normally, and inactivity onset was scheduled starting at 1:00 PM (13:00 to 18:00), cleanly isolating fall detection from meal anomalies while preserving clinical realism.
- **Suggestion**: When designing clinical synthetic benchmarks, structure negative controls and incident scenarios with orthogonal physiological windows to enable clean ablation studies.
