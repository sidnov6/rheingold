# RHEINGOLD — Explainer Video Production Script

**For:** Claude Design (motion graphics, title cards, animated diagrams) + Cowork (screen capture of the live app, voiceover, edit & assembly)
**Deliverables:** one **20-second hero cut** (social / README GIF) and one **~2:40 full walkthrough** (portfolio / LinkedIn). Both cut from the same capture session and asset pack.
**Tagline / end card:** *RHEINGOLD — Wind. Underwritten.* · Substack hook: *"Das neue Rheingold ist Wind."*

---

## 0. Before you shoot — environment & brand lock

**Live URLs**
- Local: web `http://localhost:3000`, API `http://localhost:8000` (`make dev`).
- Deployed: `https://sidnov6-rheingold.hf.space` (Hugging Face Space — use this if the local engine is asleep; showcase farms work even with the API cold).

**Capture settings (Cowork)**
- 1920×1080, 60 fps, dark-room display (the app is obsidian `#0B0B0E` — kill any OS light-mode chrome, hide the macOS dock and menu bar, full-screen the browser).
- Cursor: enable a subtle cursor highlight for the walkthrough; hide it for the 20s hero cut (motion should feel autonomous).
- Record **clean plates** (no cursor) of: the map fade-in, one slider drag, the memo stream. You'll want them cursor-free for the hero.

**Brand palette — Claude Design must use these exact tokens (from `apps/web/app/globals.css`, design system "Nachtgold"):**
| Token | Hex | Meaning — use only for this |
|---|---|---|
| `--bg-0` | `#0B0B0E` | app background (obsidian) |
| `--bg-1` | `#121217` | panels |
| `--bg-2` | `#1A1B21` | raised cards |
| `--border` | `#26262E` | 1px hairlines (never shadows) |
| `--gold-500` | `#C9A227` | **DATA ONLY** — turbines, key numbers, citations, one CTA |
| `--gold-300` | `#F0D06A` | selected-turbine pulse / accent |
| `--rhine-500` | `#3E7C9B` | debt / liabilities / water / secondary series |
| `--text-hi` | `#F2EFE6` | warm off-white body |
| `--paper` | `#F4EFE2` | the IC-memo paper panel |
| `--ink` | `#1E1B14` | memo ink |
| `--stamp-proceed` | `#2E6E4E` | verdict stamp (approve) |

**Type:** Newsreader (display / memo / titles), IBM Plex Sans (UI labels), IBM Plex Mono (**every number** — always tabular). Title cards in Newsreader; any on-screen figure in Plex Mono.

**The one aesthetic rule that sells it:** *gold is never decoration — it is reserved for data.* Titles and chrome stay in warm off-white on obsidian; the gold only ever lands on a real number, a turbine point, or a citation seal. Claude Design: if a title card has a gold element, it must be a datum (e.g. "29.333 turbines"), never ornament.

**Numbers are German-formatted** on screen (de-DE: `29.333`, `1,32×`, `8,4 %`). Keep VO in English; keep on-screen figures as the app renders them.

---

## 1. The 20-second hero cut (shot list)

Mirrors the build spec's storyboard (§1). No VO, or a single spoken line at the end. Music: low, patient, one swell at the stamp. Each beat is a locked capture + a Claude Design motion layer.

| t | On screen (Cowork capture) | Claude Design motion layer | Audio |
|---|---|---|---|
| **0–3s** | `/` map, cold load. ~11.000 gold farm points fade in over Germany on the dark basemap. | Barely-visible radial gold glow behind the map (already in-app as `.map-glow` — enhance in post). Fine grain, no bloom. | Low drone begins. |
| **3–6s** | Camera eases toward a northern cluster (Schleswig-Holstein coast). Points resolve; a farm label appears. | Thin gold reticle draws around the target farm; a hairline callout with its name types in (Plex Mono). | Single soft pulse tone as the reticle locks. |
| **6–10s** | Click → dossier slides in from the right. KPI cards count up: **P50 309,4 GWh**, **Min DSCR 2,04×**, **Equity IRR 25,6 %**. | Count-up is native (600 ms) — Claude Design adds a faint gold underline that wipes left→right beneath each figure as it settles. | Rising tone tracks the count-up. |
| **10–15s** | Scenarios tab. Drag the **power-price −40 %** slider. Waterfall, DSCR bars, verdict chip re-price live. | A "−40 %" gold chip flies from the slider thumb to the KPI row; the DSCR bar dips toward the 1,20× covenant line (which glows rhine-blue). | Bass drops with the price. |
| **15–20s** | "Generate IC Memo" → the warm **paper memo** streams onto the dark desk; gold **citation seals** attach; ink stamp lands: **PROCEED WITH CONDITIONS** (rotate −3°, single settle). | Typewriter reveal of the first two memo lines; each `◉ E-…` seal pops with a tiny gold spark; the stamp drops with a 250 ms scale+rotate and a dust puff. Cut to black. | Music swell → thump on the stamp → silence. |
| **end card** | Black. | Newsreader, centered: **RHEINGOLD** / rule / *Wind. Underwritten.* The R is warm off-white; a single gold turbine point sits above it. | Optional single VO line: *"Any wind farm in Germany. A full underwrite. In about two minutes."* |

**Hero cut editing notes:** keep every transition ≤200 ms ease-out (matches the app's motion language). No zoom-blur, no parallax except the map. The register shift from dark terminal → warm paper at 15s **is** the payoff — hold the paper a beat longer than feels comfortable.

---

## 2. The full walkthrough (~2:40) — scene-by-scene with VO

Narrated, screen-driven. VO is written to be read at a calm pace; adjust to taste. `[CAP]` = Cowork screen capture, `[GFX]` = Claude Design overlay/insert.

### Scene 1 — Cold open (0:00–0:18)
`[CAP]` The map, full-bleed, points shimmering in.
`[GFX]` Title lower-third fades: **RHEINGOLD** · *German renewable-energy project-finance intelligence.*
> **VO:** "This is every onshore wind turbine registered in Germany — twenty-nine thousand of them, seventy gigawatts, pulled straight from the federal registry. Pick any one, and RHEINGOLD underwrites it like a project-finance desk would: valuation, debt capacity, stress tests — every number cited to a real source."

`[GFX]` As VO says the figures, three gold stat chips tick up in the top-right (these are real, from the app's fleet strip): **29.333 units · 70,1 GW · 11.107 farms**.

### Scene 2 — The fleet is real (0:18–0:38)
`[CAP]` Open the filter panel. Select manufacturer **ENERCON** → the map thins, the count updates to **4.769 farms**. Then filter by commissioning year to the 2000s; then clear.
> **VO:** "Nothing here is mocked. Filter by manufacturer, by vintage, by state — it's the live Marktstammdatenregister, grouped into eleven thousand farms, rendering client-side at sixty frames a second. The data vintage is stamped right on the screen."
`[GFX]` Circle the "MaStR vintage 2026-07-11" chip briefly.

### Scene 3 — Opening a dossier (0:38–1:05)
`[CAP]` Click a strong northern farm (e.g. **Windpark Lensahner Berg**, Schleswig-Holstein, 78,4 MW, Vestas V162). Dossier slides in. Land on the **Overview** tab; let the six KPI cards count up.
> **VO:** "Click a farm and the deterministic engine prices the whole deal in about fourteen milliseconds. P50 energy with a full uncertainty stack. A sculpted debt schedule solved to a target coverage ratio. Levered equity IRR. Break-even bid. And a levelised cost of energy — all from one pure, auditable finance core with no randomness in it."
`[CAP]` Tab through **Energy** (uncertainty-stack table + P90/P75/P50 distribution) and **Debt** (the dense mono debt schedule + DSCR bars against the 1,20× covenant line).
`[GFX]` When the debt schedule shows, briefly highlight the DSCR column in gold and the covenant line in rhine-blue; caption: *"sculpted to 1,30× — constant coverage by design."*

### Scene 4 — Stress it live (1:05–1:35)
`[CAP]` **Scenarios** tab. Drag **power price −40 %**; then click the **"2020 Price Crash"** preset chip; then **"Rate Shock."** Every chart and the verdict chip re-price within the debounce.
> **VO:** "This is where it earns its keep. Drag any driver — price, production, interest rates, capex, availability, curtailment — and the engine re-prices everything in under two seconds. Or fire a preset: a low-wind year, a price crash, a two-hundred-basis-point rate shock. Watch the coverage ratio walk toward the covenant."
`[GFX]` As DSCR approaches 1,20×, the covenant line pulses rhine-blue and the verdict chip flips from PROCEED to PROCEED-WITH-CONDITIONS. Caption the shock vector as a small gold chip stack.

### Scene 5 — The memo, and why it's trustworthy (1:35–2:10)
`[CAP]` **IC Memo** tab → "Generate IC Memo." The **AgentDebatePanel** streams claims from three critics (Resource / Revenue / Credit), severity-tinted; then the **paper memo** streams in with gold **citation seals**. Hover one seal → the evidence card shows the underlying JSON (id, value, formula ref, source). The verdict **stamp** lands.
> **VO:** "The memo is written by agents — a resource critic, a revenue critic, a credit critic — that argue over the evidence, then a narrator drafts the recommendation. But here's the discipline: the agents never compute and never fetch. They can only cite numbers the engine already produced. A validator checks every figure in the memo against its evidence to within half a percent — and hover any gold seal to see the exact source. If a number can't be traced, the memo is rejected. Honesty is enforced in code, not asked for in a prompt."
`[GFX]` When hovering the seal, zoom the evidence card. Lower-third caption: *"every number → a source, or the memo doesn't ship."*

### Scene 6 — The falsifiable claim (2:10–2:32)
`[CAP]` Navigate to **/backtest**. The hero chart: model break-even band (gold) vs actual BNetzA award prices (off-white line), 2017–2024, Höchstwert cap dashed. Show the **MAE 1,10 ct/kWh** stat and scroll the caveats section.
> **VO:** "And it's testable. Run the engine's break-even bid against nine years of real German auction results and the median tracks the award trajectory to about one point one cents per kilowatt-hour. Where it misses — the undersubscribed rounds that cleared at the price cap, the crisis years that don't price under a flat forward — the page says so, out loud. A backtest that hides its failures isn't a backtest."

### Scene 7 — Close (2:32–2:40)
`[CAP]` Quick pull-back to the full map.
`[GFX]` End card: **RHEINGOLD** / *Wind. Underwritten.* Small print underneath: *Real data: MaStR · SMARD · BNetzA · Netztransparenz · Global Wind Atlas.* Then the author line.
> **VO:** "Real data. A deterministic core. Agents that can only tell the truth. That's RHEINGOLD."
`[GFX]` Final beat — a single line in italic Newsreader: *Das neue Rheingold ist Wind.*

---

## 3. Asset pack Claude Design should produce

1. **Title system:** intro lower-third, six section captions, end card — all Newsreader on obsidian, gold reserved for figures only.
2. **Animated architecture diagram** (optional insert for Scene 5 or a pause): reproduce `docs/architecture.mmd` as a motion graphic — data sources → pipelines → DuckDB mart → engine → EvidenceStore → (compliance gate ∥ 3 critics) → narrator → citation validator → UI, with the validator's pass/fail branch emphasized. Nodes in `--bg-2`, edges hairline `--border`, the EvidenceStore and validator glowing gold.
3. **Seal pop + stamp drop** motion presets (reusable for the hero and the walkthrough).
4. **Number ticker** style frames matching the app's 600 ms count-up, so inserted stats match captured ones.
5. **Lower-third "source" chips**: DL-DE/BY-2.0 (MaStR), CC BY 4.0 (SMARD, GWA), attribution (Netztransparenz) — tiny, bottom-left, for the "real data" claims. Keep license text legible but unobtrusive.

## 4. Cowork capture checklist

- [ ] `make dev` up, or point at the HF Space. Confirm `/api/health` shows real vintages before recording.
- [ ] Pre-warm each farm (click once so the engine result is cached → the on-camera click is instant).
- [ ] Record the map fade-in **twice**: once cursor-free (hero), once with cursor (walkthrough).
- [ ] Capture the memo stream at full length, then speed-ramp in the edit — don't fake the streaming, it's real and it reads as authentic.
- [ ] Grab the `/backtest` chart at rest AND mid-scroll through caveats.
- [ ] Export master at ProRes/1080p60; derive the 20s hero and a looping GIF (≤10 MB, ~12 fps) for the README hero slot.

## 5. Facts to keep accurate on screen (do not round these away)
- Fleet: **29.333 units · 70,1 GW · 11.107 farms**, MaStR snapshot **2026-07-11**.
- Warm underwrite latency: **~14 ms** (well under the 300 ms budget — safe to say "milliseconds").
- Backtest: **MAE ≈ 1,10 ct/kWh** over **22** priceable rounds **2017–2024**, hit-rate 55 %.
- Memo validation tolerance: **0,5 %** relative; **3 critics** + narrator; verdict ∈ {PROCEED, PROCEED WITH CONDITIONS, DECLINE}.
- Data sources (say at least MaStR + one price source): MaStR (DL-DE/BY-2.0), SMARD (CC BY 4.0), BNetzA auctions, Netztransparenz Marktwerte, Global Wind Atlas (CC BY 4.0). renewables.ninja is **CC BY-NC** — if mentioned, note non-commercial.
- Author line: *Siddharth Jain — two years of manufacturing data systems across 10+ wind plants at Suzlon; now the systems that finance them.*
