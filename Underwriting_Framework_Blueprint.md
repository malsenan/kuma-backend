# Kumã SEE — Underwriting Framework Blueprint

**Status:** Production Locked · **Version:** 1.6 (The Complete Structured Funnel)

A standardized, portable framework for evaluating informal entrepreneurs using bank statements, transaction histories, and application data.

---

## PART 1: THE FOUR QUALITATIVE VALUATION PILLARS

Each pillar is scored 1–5 against fixed anchors based on 90 days of transaction history.

### Pillar 1 — Cash-Flow Rhythm & Strength

- **5 — Structured Cadence:** Consistent, recurring inflows matching a logical business cycle. Smooth weekly velocity showing liquid capital is reliably present.  
- **4 — Consistent with Minor Gaps:** Regular weekly inflow patterns, but displays 1–2 notable dry spells over the 90-day period.  
- **3 — Lumpy/Unpredictable:** Revenue is present but erratic: gaps of a week or more with no clear operational pattern.  
- **2 — Mostly Stagnant:** The account is heavily inactive, showing only occasional small sales with no reliable weekly rhythm.  
- **1 — Stagnant:** Long stretches of zero activity, then a sudden random lump sum immediately drained.

*Modifiers (Shift base score by max \+/- 1 point):*

- Momentum: Clearly declining volume trajectory pulls the score down 1 point; growing trajectory lifts it 1 point.  
- Concentration: Reliance on 1–2 dominant inflow sources pulls down 1 point; diverse independent sources lifts 1 point.

*Reported Separately:* Gross Verified Inflow (GVI) monthly volume and monthly transaction counts.

### Pillar 2 — Outflow Character & Patterns

- **5 — Operational Patterning:** Highly structured outgoing expenses: repeating amounts or specific-day transfers aligned with clear business restocking cycles.  
- **4 — Predominantly Commercial:** Spending is heavily driven by business operations, showing minor personal usage leakage.  
- **3 — Mixed/Ambiguous:** Some repeating commercial patterns, heavily diluted by erratic personal consumption or unvouched P2P transfers.  
- **2 — High Personal Leakage:** Outflows show isolated business repeating patterns buried inside an overwhelming majority of personal or consumer spending.  
- **1 — Pure Consumption:** Outflows entirely random personal retail, entertainment, or fragmented transfers with zero recurring commercial logic.

### Pillar 3 — Operational Reality (Tools of the Trade)

- **5 — Tools of the Trade:** Undeniable physical/photographic proof of active operations (e.g., salon chairs, inventory racks, commercial stoves, street stalls).  
- **4 — Established Setup:** Clear operational setup with real workspace and core tools, but working at a highly restricted or partial scale.  
- **3 — Minimalist/Ambiguous:** A few products on a household table; no dedicated workspace or tools. Plausible, but easily mistaken for personal use.  
- **2 — Fragmented Evidence:** A single uncontextualized product photo or low-effort image that fails to prove an active trade.  
- **1 — Ghost Operation:** Purely personal selfies, generic downloaded images, or zero workspace/inventory visibility.

*Note on Current State:* While photos remain uncollected, Pillar 3 is uncounted, and its weight is redistributed. Reinstated instantly upon image upload.

### Pillar 4 — Truth & Intent (The Anchor)

- **5 — Flawless Alignment:** Self-reported revenue, business type, and operational history perfectly match statement realities.  
- **4 — High Accuracy:** Minor structural variations in timing, with actual revenue matching within an acceptable 10–20% variance.  
- **3 — Minor Discrepancy:** Business type matches, but income or transaction frequency was exaggerated within a 20–30% variance.  
- **2 — Moderate Discrepancy:** Notable mismatch between stated income and reality (30–50% variance), borderlining on systemic exaggeration.  
- **1 — Material Misrepresentation:** Explicit fabrication regarding the existence, nature, or type of trade. Triggers an automatic Fraud Knockout.

---

## PART 2: THE THREE-PHASE UNDERWRITING ENGINE

### PHASE 1: ACCREDITATION & INTENT SCREENING (Eligibility Gate)

Before financial analysis, the applicant must clear two qualitative vectors to generate the Accreditation Score (S\_acc):

1. **Vector A (Account Maturity & Typology):** Score 1–5. Evaluated purely on history depth and transaction clarity. Central Bank-regulated digital statements (Nubank, PagBank, etc.) must never be penalized for institutional type (Neobank-Fairness Rule). Thin files (under 3 months of history) automatically anchor Vector A to a score of 2\. Missing metadata holds a sub-metric neutral at 3\.  
2. **Vector B (Use-Case Credibility):** Score 1–5. Evaluates the intent of the capital. Stated inventory/equipment capex is anchored at a baseline score of 2\.  
3. **The Red Flag Hard Gate:** A stated intent of using loan proceeds to pay off personal consumption bills or existing non-commercial debt triggers an automatic Vector B score of 1\. This acts as an absolute knockout that halts the file immediately and routes the applicant directly to a Manual KYC Hold / Decline.

*Accreditation Score Formula:* `S_acc = (Vector A + Vector B) / 2`

### PHASE 2: SYSTEMIC CASH-FLOW & PRICING ENGINE

If Phase 1 is cleared, the engine processes the transaction log to discover true Free Cash Flow, calculate the Financial Score (S\_fin), and derive the precise risk-adjusted monthly interest rate (i).

1. **High-Frequency Payee Rule (Informal Payroll & Supplier Filter):** Any single individual payee (CPF) receiving \> 4 transfers in a single month, or \> 12 transfers across the total 90-day window, is classified programmatically as an Informal Operational Cost. These are recognized as vital operational dependencies, are subtracted *before* loan service calculations, and cannot be added back to cash flow.  
2. **Low-Frequency Draw Rule:** Individual transfers occurring 4 or fewer times per month (and 12 or fewer across 90 days), self-transfers, and personal consumer retail are treated as Discretionary Personal Draws (owner's salary) and added back into the monthly cash flow baseline.  
3. **High-Value Anomaly Gate:** Any individual or ambiguous entity payee whose single transfer value exceeds 15% of the applicant's median monthly GVI must be flagged for manual spot-verification before a borrower can transition to Tier 2\. For Tier 1 pricing, these may be provisionally added back only if the starter tranche is capped conservatively at a fund-to-need level.  
4. **Financial Score Formula (Current State \- Photos Uncollected):** `S_fin = (Pill1 * 0.50) + (Pill2 * 0.25) + (Pill4 * 0.25)`

*Core Pricing Equations:*

- `Adjusted FCF = (median monthly GVI - median monthly business OUT) * (1 - h)`  
- Volatility Haircut: `h = min(0.40 * CV_w, 0.50)`, derived from the weekly coefficient of variation.  
- Maximum Monthly Debt Capacity: `M_max = 0.35 * Adjusted FCF` (Enforcing a strict 35% Productive Asset Ceiling Boost).  
- **Maturity Compression Law:** To maximize capital velocity and minimize default exposure, the standard pilot loan maturity (n) must be structurally compressed to a short-term velocity cycle of exactly 3 months, executed as a weekly collection cycle.  
- **Dynamic Pricing Rate Formula:** `i = i_floor + a*(5 - S_fin) + b*(5 - S_acc)` *(Pilot Constants: Base i\_floor \= 2.0%, risk coefficient a \= 0.5pp, intent coefficient b \= 0.4pp).*

### PHASE 3: OPERATIONAL DISBURSEMENT & COLLECTION GOVERNANCE

1. **The Split-Disbursement Activation Hold:** Loans must never be disbursed 100% upfront. An initial "Activation Tranche" capped at exactly R$100.00 is released first. The remaining balance of the approved principal is strictly held until the borrower configures a "Pix Agendado" (Scheduled Pix) recurring sequence inside their banking app matching their chosen timeline, and submits a verified receipt screenshot.  
2. **Omnichannel Term Selection Matrix:** Every approved term sheet must generate an easily digestible, scannable menu presenting three distinct repayment velocities (6-week Compressed, 9-week Accelerated, and 12-week Standard), all safely bound under the 35% Adjusted FCF dynamic ceiling.  
3. **Day-of-Week Liquidity Maximizer:** The weekly collection day must be programmatically derived via a 3-step sequence case-by-case:  
   - Step 1: Aggregate total gross cash inflow volume by individual day of the week across the 90-day statement window.  
   - Step 2: Identify the single day holding the highest absolute volume of cash clearings (Day\_peak).  
   - Step 3: Anchor the Scheduled Collection Day exactly 1 business day after Day\_peak to ensure collection occurs precisely when the borrower's liquid cash balance hits its statistical maximum.  
4. **Late Policy:** To account for informal card machine settlement delays, a rolling 24-hour interest-free grace window is programmatically applied. A payment cleared within the grace window following its scheduled collection day maintains perfect Tier 2 escalation status.

