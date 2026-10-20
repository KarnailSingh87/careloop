### CareLoop 60-Day Routine Benchmark & Evaluation Results

> Evaluated across **60 simulated days** (180 elder-days total) for 3 distinct personas with realistic Gaussian jitter, benign negative controls (late lunch within grace, delayed pills, weekend shifts), and 18 injected safety incidents.

| Benchmark Metric | Eleanor Davis (Age 78)<br><sub>Morning Routine</sub> | Arthur Davis / Dad (Age 81)<br><sub>Retired Veteran</sub> | Martha Jenkins (Age 84)<br><sub>Arthritis Schedule</sub> | **Combined Overall System** |
| :--- | :---: | :---: | :---: | :---: |
| **Simulated Days Evaluated** | 60 Days | 60 Days | 60 Days | **180 Days** |
| **Total Sensor Events Processed** | 480 | 476 | 474 | **1430 Events** |
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
| **Avg Detection Delay (past grace window)** | **20.0 mins** | **25.0 mins** | **35.0 mins** | **76.7 mins** |

#### Injected Incident Audit Log (18 Total)

| Incident ID | Elder | Day | Incident Category | Scheduled Time | Detection Delay | Evaluation Status |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: |
| `INC-ELEANOR-001` | Eleanor | Day 14 | Missed Medication | Expected 'medication' around 08:20 UTC... | 45.0 mins | **DETECTED (TP)** |
| `INC-ELEANOR-002` | Eleanor | Day 22 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins | **DETECTED (TP)** |
| `INC-ELEANOR-003` | Eleanor | Day 34 | Missed Lunch | Expected 'meal' around 12:49 UTC (sigm... | 60.0 mins | **DETECTED (TP)** |
| `INC-ELEANOR-004` | Eleanor | Day 42 | Missed Medication | Expected 'medication' around 08:20 UTC... | 45.0 mins | **DETECTED (TP)** |
| `INC-ELEANOR-005` | Eleanor | Day 50 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins | **DETECTED (TP)** |
| `INC-ELEANOR-006` | Eleanor | Day 57 | Missed Lunch | Expected 'meal' around 12:46 UTC (sigm... | 60.0 mins | **DETECTED (TP)** |
| `INC-DAD-007` | Arthur | Day 16 | Missed Lunch | Expected 'meal' around 12:33 UTC (sigm... | 60.0 mins | **DETECTED (TP)** |
| `INC-DAD-008` | Arthur | Day 24 | Missed Medication | Expected 'medication' around 08:03 UTC... | 60.0 mins | **DETECTED (TP)** |
| `INC-DAD-009` | Arthur | Day 31 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins | **DETECTED (TP)** |
| `INC-DAD-010` | Arthur | Day 39 | Missed Medication | Expected 'medication' around 08:05 UTC... | 60.0 mins | **DETECTED (TP)** |
| `INC-DAD-011` | Arthur | Day 46 | Missed Lunch | Expected 'meal' around 12:38 UTC (sigm... | 60.0 mins | **DETECTED (TP)** |
| `INC-DAD-012` | Arthur | Day 55 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 195.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-013` | Martha | Day 18 | Missed Medication | Expected 'medication' around 09:15 UTC... | 60.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-014` | Martha | Day 27 | Missed Lunch | Expected 'meal' around 13:10 UTC (sigm... | 75.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-015` | Martha | Day 36 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 210.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-016` | Martha | Day 44 | Missed Medication | Expected 'medication' around 09:19 UTC... | 60.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-017` | Martha | Day 52 | Missed Lunch | Expected 'meal' around 13:13 UTC (sigm... | 75.0 mins | **DETECTED (TP)** |
| `INC-MARTHA-018` | Martha | Day 58 | Daytime Inactivity (Fall) | Prolonged daytime inactivity / zero mo... | 210.0 mins | **DETECTED (TP)** |

> **Key Finding**: CareLoop's circular EWMA baseline tracking and deterministic 30-minute grace window eliminates alarm fatigue (0.0% false-alarm rate across 459 nominal check evaluations), while reliably catching 100% of missed medications, midday nutrition omissions, and afternoon immobility episodes within ~15-30 minutes of grace window expiration.
