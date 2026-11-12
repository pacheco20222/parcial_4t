# Project Brief — Second Partial Exam (Phase 1 of the Project)

> English translation of the professor's instructions (original in Spanish).
> Language rule: internal docs (between us) in **English**; deliverables for the professor (PDF report, oral defense material) in **Spanish**.

---

## Header

- **Badge:** SECOND PARTIAL EVALUATION — PHASE 1 OF THE PROJECT
- **Title:** DATA-DRIVEN 4.0 CHALLENGE: ALPHA PROTOTYPE (UNITS 3 AND 4)
- **Subtitle:** Functional Software, Operational Dashboard, Cybersecurity and Oral Presentation

## Introduction

Engineers, continuing with the real, unsolved problem you selected in the **Data-Driven 4.0 Challenge**, in this Second Partial evaluation we will not limit ourselves to theoretical design. Each team must present a **functional Alpha Prototype** that demonstrates the technical viability of the support systems, mobile computing, cloud architecture and cybersecurity hardening (Units 3 and 4) applied to their project.

## 🎯 Mandatory Requirement of the Alpha Prototype

The progress must consist of executable code and a live demonstration during your presentation in class. The evaluation consists of the **Technical Report**, the **Software Prototype Deployment** and the **Oral Defense**.

---

## 🛠️ Technical Components of the Deliverable

### 1. Backend and Cloud Connectivity (Topics 3.3 and 4.3)

- **Cloud Processing:** A Python script, API, or Node-RED flow that processes and stores simulated telemetry, emulating integration with an ERP or MES.
- **Infrastructure:** Technical justification of the cloud model (IaaS/PaaS) selected to host the core of the solution.

### 2. IT/OT Cybersecurity and SOC Design (Topic 3.5)

- **Zero Trust Architecture:** Network segmentation diagram (IDMZ) to protect the organization's assets.
- **SIEM Detection Rule:** Technical structure of a rule aimed at identifying anomalies or intrusion attempts in the project's systems.

### 3. Operational Dashboard and Mobile Computing (Topic 3.4)

- **Visual Interface:** Functional operational panel (web or mobile) that reflects key metrics in real time.
- **Decision Making:** Demonstration of how mobility enables remote supervision of the process.

### 4. Challenges and Business Vision (Topics 3.6 and 4.4)

- **Barrier Analysis:** Identification of technical challenges (*legacy* systems) and cultural challenges in the organization.
- **Connected Value:** How the proposed architecture enables a service with greater competitive value.

---

## 🎤 Delivery and Live Demonstration Requirements

- **Technical Document (PDF):** 4 to 5 pages long, with the description of the architecture and links to the functional code repository.
- **Functional Alpha Prototype:** Link to GitHub/GitLab with the executable code and active deployment of the dashboard and backend in the cloud.
- **Oral Presentation in Class:** 6 minutes per team demonstrating the software running live + 2 minutes of technical questions from the professor.

---

## ✅ Analytical Evaluation Rubric — Second Partial (10.0 Points)

Each criterion is evaluated independently according to the level of technical maturity demonstrated in the report, the repository and the live execution.

### Criterion 1 — Backend, Support Systems and Cloud (Topics 3.3, 4.3, 4.4 — 2.5 pts)

| Level | Points | Description |
|---|---|---|
| Excellent (100%) | 2.5 | The script (Python/API/Node-RED) ingests, processes and persists telemetry in the cloud without errors, accurately emulating ERP/MES logic. Rigorously justifies the chosen IaaS/PaaS model and identifies real technical (*legacy*) and cultural barriers. |
| Competent (80%) | 2.0 | The backend operates and stores data in the cloud with minor failures or controlled latency. The business emulation (ERP/MES) and the cloud model justification are adequate, but the analysis of *legacy* systems is superficial. |
| In Development (50%) | 1.25 | The code runs only in a local environment (*localhost*) without real cloud deployment, or uses static data without a continuous processing flow. Generic justification of the cloud infrastructure. |
| Insufficient (0%–20%) | 0.0–0.5 | Non-executable code, with critical syntax/connection errors, or absent from the repository. There is no business support logic nor cloud justification. |

### Criterion 2 — Dashboard and Mobile Computing (Topics 3.4, 3.6 — 2.5 pts)

| Level | Points | Description |
|---|---|---|
| Excellent (100%) | 2.5 | Responsive web/mobile interface that updates operational KPIs in real time from the backend. Tangibly demonstrates remote supervision and argues how connected data generate a measurable competitive advantage. |
| Competent (80%) | 2.0 | The dashboard visualizes relevant metrics and adapts to mobile screens, although it requires manual reload or presents minor usability details. Adequately explains the impact on decision making. |
| In Development (50%) | 1.25 | Merely aesthetic interface (*mockup* or *hardcoded* data) without a real connection to the telemetry flow, or a design not suitable for mobile devices. Weak argumentation about the business value. |
| Insufficient (0%–20%) | 0.0–0.5 | Does not present a functional interface or shows only static screenshots without interactivity or link to the project's problem. |

### Criterion 3 — IT/OT Cybersecurity and SOC Design (Topic 3.5 — 2.0 pts)

| Level | Points | Description |
|---|---|---|
| Excellent (100%) | 2.0 | Precise technical network segmentation diagram (IDMZ) under *Zero Trust* principles (microsegmentation, access control and port flow). Includes a structured SIEM rule (condition, threshold, severity and action) aligned to real threats of the project. |
| Competent (80%) | 1.6 | Clear network diagram that differentiates IT/OT zones with basic security controls. The SIEM rule is coherent with the scenario, but lacks specific technical parameters (e.g., thresholds, protocols or source logs). |
| In Development (50%) | 1.0 | Generic network diagram without clear delimitation of an IDMZ nor application of *Zero Trust*. The SIEM rule is written as a general textual recommendation and not as technical detection logic. |
| Insufficient (0%–20%) | 0.0–0.4 | Omits the segmentation diagram or the SIEM rule, or presents technically wrong concepts about critical infrastructure protection. |

### Criterion 4 — Technical Report, Live Demo and Defense (Deliverables and Oral — 3.0 pts)

| Level | Points | Description |
|---|---|---|
| Excellent (100%) | 3.0 | Impeccable technical PDF (4–5 pages) with active links to the functional repository. Fluent presentation within the 6 min with a successful live demo. All members respond with technical competence to the 2-min questioning. |
| Competent (80%) | 2.4 | Complete PDF with slight deviations in length or format; functional repository. Successful live demo with minor setbacks resolved on the spot. Correct but somewhat general answers to the professor's questions. |
| In Development (50%) | 1.5 | Incomplete report or broken links to the repository. The live demo partially fails (they resort to a recorded backup video) or they exceed the time limit. Evident imbalance in technical mastery among team members. |
| Insufficient (0%–20%) | 0.0–0.6 | They do not deliver the PDF report or the repository. They fail to execute the live demo or answer the fundamental technical questions about their own architecture. |

**Maximum Total Score — Second Partial: 10.0 Points**

---

## Quick Reference — Points Breakdown

| Criterion | Max |
|---|---|
| 1. Backend, Support Systems and Cloud | 2.5 |
| 2. Dashboard and Mobile Computing | 2.5 |
| 3. IT/OT Cybersecurity and SOC Design | 2.0 |
| 4. Technical Report, Live Demo and Defense | 3.0 |
| **Total** | **10.0** |
