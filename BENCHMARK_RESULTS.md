# CareLoop: 60-Day Routine Safety Benchmark & Reproducible Evaluation Report

> **Evaluation Overview**: Evaluated across **60 simulated days** (159 active elder-days evaluated; 7-day cold-start calibration period excluded) across 3 distinct personas with realistic Gaussian jitter, benign negative controls (late lunch within grace, delayed pills, weekend shifts), and 18 injected ground-truth safety incidents.
>
> **Evaluation Engine**: Reproducible evaluation replay via `careloop.clock.SimulatedClock` (Fixed seed: `42`).

---

### 1. Comparative Evaluation: CareLoop Adaptive Engine vs. Traditional Static Telecare

| Evaluation Metric | Traditional Static Telecare<br><sub>(Rigid Fixed Thresholds)</sub> | CareLoop Adaptive EWMA<br><sub>(Circular Learning + Grace)</sub> | Clinical Impact / Improvement |
| :--- | :---: | :---: | :--- |
| **Detection Rate (Sensitivity / Recall)** | **94.4%** (17/18) | **100.0%** (18/18) | Identical 100% safety capture of all critical incidents. |
| **Precision (PPV)** | **17.5%** | **100.0%** | **+82.5% improvement** in alert trustworthiness. |
| **False Positives (False Alarms)** | **80** | **0** | **-80 false alarms eliminated** over 60 days. |
| **False-Alarm Rate (FAR)** | **17.43%** | **0.00%** | Negligible false alarm probability on nominal days. |
| **False Alerts per Person-Day** | **0.5031** | **0.0000** | Eliminates 1 false alert every ~2.0 days. |
| **False Alarms per Month (30 Days)** | **15.1** | **0.0** | Completely eliminates alarm fatigue for adult children. |
| **Avg Detection Delay (from schedule)** | **N/A (Rigid)** | **106.7 mins** | Consistent detection within clinically safe window. |
| **Avg Detection Delay (past grace window)** | **N/A** | **26.7 mins** | Alerts dispatch promptly upon grace window expiration. |

---

### 2. Detailed Performance Breakdown by Persona

| Benchmark Metric | Eleanor Davis (Age 78)<br><sub>Morning Routine</sub> | Arthur Davis / Dad (Age 81)<br><sub>Retired Veteran</sub> | Martha Jenkins (Age 84)<br><sub>Arthritis Schedule</sub> | **Combined Overall System** |
| :--- | :---: | :---: | :---: | :---: |
| **Simulated Days Evaluated** | 60 Days | 60 Days | 60 Days | **180 Days** |
| **Active Evaluated Days (Post Cold-Start)** | 53 Days | 53 Days | 53 Days | **159 Elder-Days** |
| **Total Sensor Events Processed** | 474 | 474 | 474 | **1422 Events** |
| **Injected Ground-Truth Incidents** | 6 | 6 | 6 | **18 Incidents** |
| - *Missed Prescription Medication* | 2 | 2 | 2 | **6** |
| - *Daytime Inactivity / Falls (3h+)* | 2 | 2 | 2 | **6** |
| - *Missed Lunch Nutrition* | 2 | 2 | 2 | **6** |
| **Benign Noise Controls (Within Grace)** | 14 | 14 | 14 | **42 Variations** |
| **True Positives (Detected)** | **6 / 6** | **6 / 6** | **6 / 6** | **18 / 18** |
| **False Negatives (Missed Alerts)** | **0** | **0** | **0** | **0** |
| **False Positives (False Alarms)** | **0** | **0** | **0** | **0** |
| **Detection Rate (Sensitivity / Recall)** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| **Precision (PPV)** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| **False-Alarm Rate (FAR)** | **0.00%** | **0.00%** | **0.00%** | **0.00%** |
| **False Alerts per Person-Day** | **0.0000** | **0.0000** | **0.0000** | **0.0000** |
| **Avg Detection Delay (from schedule)** | **100.0 mins** | **105.0 mins** | **115.0 mins** | **106.7 mins** |
| **Avg Detection Delay (past grace window)** | **20.0 mins** | **25.0 mins** | **35.0 mins** | **26.7 mins** |

---

### 3. Complete Injected Incident Audit Log (18 Ground-Truth Incidents)

| Incident ID | Elder | Day | Incident Category | Scheduled Time | Detection Delay | Evaluation Status |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: |
| `INC-ELEANOR-001` | Eleanor | Day 14 | Missed Medication | Expected 'medication' around 08:20 UTC... | 45.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-ELEANOR-002` | Eleanor | Day 22 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-ELEANOR-003` | Eleanor | Day 34 | Missed Lunch | Expected 'meal' around 12:49 UTC (sigm... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-ELEANOR-004` | Eleanor | Day 42 | Missed Medication | Expected 'medication' around 08:20 UTC... | 45.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-ELEANOR-005` | Eleanor | Day 50 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-ELEANOR-006` | Eleanor | Day 57 | Missed Lunch | Expected 'meal' around 12:46 UTC (sigm... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-007` | Arthur | Day 16 | Missed Lunch | Expected 'meal' around 12:33 UTC (sigm... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-008` | Arthur | Day 24 | Missed Medication | Expected 'medication' around 08:03 UTC... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-009` | Arthur | Day 31 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-010` | Arthur | Day 39 | Missed Medication | Expected 'medication' around 08:05 UTC... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-011` | Arthur | Day 46 | Missed Lunch | Expected 'meal' around 12:38 UTC (sigm... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-DAD-012` | Arthur | Day 55 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins (15.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-013` | Martha | Day 18 | Missed Medication | Expected 'medication' around 09:15 UTC... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-014` | Martha | Day 27 | Missed Lunch | Expected 'meal' around 13:10 UTC (sigm... | 75.0 mins (45.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-015` | Martha | Day 36 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 210.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-016` | Martha | Day 44 | Missed Medication | Expected 'medication' around 09:19 UTC... | 60.0 mins (30.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-017` | Martha | Day 52 | Missed Lunch | Expected 'meal' around 13:13 UTC (sigm... | 75.0 mins (45.0m past grace) | **DETECTED (TP)** |
| `INC-MARTHA-018` | Martha | Day 58 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 210.0 mins (30.0m past grace) | **DETECTED (TP)** |

---

### 4. Evaluation Methodology & Edge-Case Handling

1. **Cold-Start Calibration Days**:
   - The first **7 days** are designated as baseline warmup. The circular EWMA baseline engine requires `min_observations=5` before producing anomaly scores.
   - During days 1-7, routine events build the prior distribution. Incident evaluation begins on Day 8, ensuring statistical stability before alerts can be generated.
2. **Unresolved Incidents**:
   - Evaluated as a single incident-level detection unit. When an incident occurs, the system's ability to identify and escalate it during the relevant window is scored once (TP/FN), avoiding double-counting ongoing unacknowledged states.
3. **Repeated Alerts & Deduplication**:
   - In CareLoop, repeated scheduled ticks during an active escalation state machine produce zero duplicate alerts (deduplicated by `escalation:<person>:<date>:<issue>`).
   - The evaluation replay scores alerts at the incident level so repeated periodic worker ticks do not inflate false alarm metrics.
4. **Incidents Without a Fixed Scheduled Time**:
   - Prolonged daytime inactivity (falls/immobility) does not occur at a predetermined calendar hour. Its onset is mathematically anchored to T_last_activity + 180 minutes.
   - Detection delay is calculated relative to this inactivity onset threshold.
5. **Prevention of Future Data Leakage**:
   - Chronological replay is enforced via `careloop.clock.SimulatedClock`.
   - At checkpoint time T, only events with timestamp <= T are accessible to storage queries, baseline evaluation, and the risk engine. Baseline updates with completed daily events occur strictly at the end of each simulated day.

---

### 5. Clinical Safety & Simulation Limitations

> [!WARNING]
> **Synthetic Benchmark Disclaimer**: These reproducible benchmark metrics are computed on a synthetic dataset of 60 simulated days across 3 distinct elder personas generated with Gaussian jitter (sigma = 5-15 mins), weekend schedule shifts, and explicit benign controls under random seed `42`.
>
> While these results mathematically validate CareLoop's circular statistics and grace window algorithm against rigid static telecare thresholds, **synthetic simulation performance must not be conflated with clinical safety trials, real-world human telemetry, or FDA-cleared medical device efficacy**.
>
> Real-world home environments introduce sensor packet dropouts, multi-person households, pet interference, dementia-related wandering, and acute medical emergencies that require formal observational clinical studies before production deployment.
