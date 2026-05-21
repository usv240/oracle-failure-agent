"""
Board deck export — Gemini 3 Flash structures analysis into presentation-ready content.
Returns a self-contained HTML slide deck the user can download and present.
"""
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional
from backend.services import gemini

logger = logging.getLogger(__name__)
router = APIRouter()


class SlideExportRequest(BaseModel):
    startup_name: str = Field(..., max_length=100)
    pattern_name: str = Field(..., max_length=200)
    confidence: float = Field(..., ge=0, le=1)
    days_to_crisis: int = Field(..., ge=0)
    survival_rate: float = Field(..., ge=0, le=1)
    narrative: str = Field(..., max_length=2000)
    warning_signals: list[str] = Field(default_factory=list, max_length=20)
    survival_playbook: list[str] = Field(default_factory=list, max_length=20)
    famous_failures: list[dict] = Field(default_factory=list, max_length=10)
    match_reasoning: Optional[str] = None


async def _generate_deck_content(req: SlideExportRequest) -> dict:
    """Ask Gemini 3 to generate polished slide content for each section."""
    pct = int(req.confidence * 100)
    surv_pct = int(req.survival_rate * 100)
    fail_pct = 100 - surv_pct
    signals_text = "\n".join(f"- {s}" for s in req.warning_signals[:8])
    playbook_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(req.survival_playbook[:8]))

    prompt = f"""You are preparing a board deck for a startup that has triggered a critical pattern alert.
Generate concise, board-ready slide content. Be direct and data-driven.

ANALYSIS:
- Company: {req.startup_name}
- Pattern Detected: {req.pattern_name} ({pct}% match)
- Days to potential crisis: {req.days_to_crisis}
- Historical survival rate for this pattern: {surv_pct}%
- Investigator's reasoning: {req.match_reasoning or 'See full analysis'}
- Warning signals present: {signals_text}
- Survival playbook: {playbook_text}

Generate JSON with these exact slides:
{{
  "executive_summary": {{
    "headline": "<7 words max — the single most important thing the board needs to know>",
    "bullets": ["<3 key findings, each under 12 words>", "...", "..."]
  }},
  "risk_assessment": {{
    "headline": "<the pattern name and its severity in one line>",
    "bullets": ["<3 specific metrics or signals driving this alert>", "...", "..."]
  }},
  "historical_context": {{
    "headline": "What happened to other companies here",
    "bullets": [
      "<bullet citing the {fail_pct}% failure stat with context>",
      "<bullet about the {surv_pct}% who survived and what they did differently>",
      "<bullet about timeline — when crises typically become irreversible>"
    ]
  }},
  "recommended_actions": {{
    "headline": "Board-Mandated Actions (Next 30 Days)",
    "bullets": ["<3 specific, actionable steps the board should require — based on the survival playbook>", "...", "..."]
  }},
  "closing_call_to_action": {{
    "headline": "<A single urgent, board-appropriate call to action>",
    "sub": "<One sentence on why acting now vs later matters — cite the {req.days_to_crisis}-day window>"
  }}
}}

Be direct, not corporate. Write as if you're presenting to a board that needs to decide today.
"""
    try:
        raw = await gemini.generate_json(prompt)
        return json.loads(raw)
    except Exception as e:
        logger.warning("Gemini deck generation failed, using fallback: %s", e)
        pct_str = f"{pct}%"
        return {
            "executive_summary": {
                "headline": f"{req.startup_name} has matched a critical failure pattern",
                "bullets": [
                    f"Pattern: {req.pattern_name} — {pct_str} match confidence",
                    f"Historical survival rate: {surv_pct}% — {fail_pct}% of companies failed",
                    f"Estimated days to crisis if no action: {req.days_to_crisis}"
                ]
            },
            "risk_assessment": {
                "headline": f"{req.pattern_name} — {pct_str} Match",
                "bullets": req.warning_signals[:3] or ["See full analysis"]
            },
            "historical_context": {
                "headline": "What happened to other companies here",
                "bullets": [
                    f"{fail_pct}% of companies in this pattern failed to recover",
                    f"{surv_pct}% survived — all took immediate corrective action",
                    f"Crisis becomes irreversible within {req.days_to_crisis} days on average"
                ]
            },
            "recommended_actions": {
                "headline": "Board-Mandated Actions (Next 30 Days)",
                "bullets": (req.survival_playbook[:3] or ["Review and act on Oracle analysis"])
            },
            "closing_call_to_action": {
                "headline": "Act within the window",
                "sub": f"The {req.days_to_crisis}-day window is your margin. Companies that acted at this stage survived. Those that waited did not."
            }
        }


def _build_html_deck(req: SlideExportRequest, content: dict) -> str:
    pct = int(req.confidence * 100)
    surv_pct = int(req.survival_rate * 100)
    fail_pct = 100 - surv_pct
    risk_color = "#ef4444" if pct >= 88 else "#f97316" if pct >= 75 else "#f59e0b"
    risk_label = "CRITICAL" if pct >= 88 else "HIGH RISK" if pct >= 75 else "MODERATE RISK"

    def _failure_row(f: dict) -> str:
        color = "#ef4444" if f.get("outcome") == "Failed" else "#10b981"
        return (
            f"<tr><td>{f.get('company','')}</td>"
            f"<td style='color:{color}'>{f.get('outcome','')}</td>"
            f"<td style='color:#94a3b8;font-size:0.82em'>{f.get('detail','')}</td></tr>"
        )

    famous = "".join(_failure_row(f) for f in req.famous_failures[:5])
    famous_slide = f"""
    <div class="slide" id="slide-5">
      <div class="slide-tag">PATTERN EVIDENCE</div>
      <h2>Companies That Matched This Pattern</h2>
      <table class="cases-table">
        <thead><tr><th>Company</th><th>Outcome</th><th>Detail</th></tr></thead>
        <tbody>{famous}</tbody>
      </table>
    </div>""" if famous else ""

    exec_bullets = "".join(f"<li>{b}</li>" for b in content.get("executive_summary", {}).get("bullets", []))
    risk_bullets  = "".join(f"<li>{b}</li>" for b in content.get("risk_assessment", {}).get("bullets", []))
    hist_bullets  = "".join(f"<li>{b}</li>" for b in content.get("historical_context", {}).get("bullets", []))
    action_bullets = "".join(f"<li class='action-item'>{b}</li>" for b in content.get("recommended_actions", {}).get("bullets", []))
    cta = content.get("closing_call_to_action", {})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Oracle Board Deck — {req.startup_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; overflow: hidden; }}
  .deck {{ width: 100vw; height: 100vh; position: relative; }}
  .slide {{ display: none; width: 100%; height: 100%; padding: 4rem 5rem; flex-direction: column; justify-content: center; position: absolute; top:0; left:0; background: #0f172a; animation: fadeIn 0.35s ease; }}
  .slide.active {{ display: flex; }}
  @keyframes fadeIn {{ from {{ opacity:0; transform:translateY(12px) }} to {{ opacity:1; transform:none }} }}
  .slide-tag {{ font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #64748b; margin-bottom: 1rem; }}
  h1 {{ font-size: clamp(2rem, 4vw, 3.2rem); font-weight: 800; line-height: 1.15; }}
  h2 {{ font-size: clamp(1.4rem, 2.8vw, 2.2rem); font-weight: 700; line-height: 1.25; margin-bottom: 1.5rem; }}
  .risk-chip {{ display: inline-block; padding: 0.3rem 1rem; border-radius: 20px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.1em; background: {risk_color}22; color: {risk_color}; border: 1px solid {risk_color}55; margin-bottom: 1.5rem; }}
  .metric-row {{ display: flex; gap: 2rem; margin: 1.5rem 0; flex-wrap: wrap; }}
  .metric {{ text-align: center; }}
  .metric-val {{ font-size: 2.8rem; font-weight: 900; line-height: 1; }}
  .metric-label {{ font-size: 0.72rem; color: #64748b; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  ul {{ list-style: none; padding: 0; }}
  ul li {{ padding: 0.65rem 0 0.65rem 1.5rem; border-bottom: 1px solid #1e293b; font-size: 1.05rem; line-height: 1.5; position: relative; color: #cbd5e1; }}
  ul li::before {{ content: "→"; position: absolute; left: 0; color: #3b82f6; font-weight: 700; }}
  ul li.action-item::before {{ color: #10b981; }}
  .cases-table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  .cases-table th {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; color: #64748b; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.07em; }}
  .cases-table td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid #1e293b; }}
  .cta-box {{ margin-top: 1.5rem; padding: 1.5rem 2rem; background: {risk_color}15; border: 1px solid {risk_color}40; border-radius: 12px; }}
  .cta-headline {{ font-size: 1.5rem; font-weight: 800; color: {risk_color}; margin-bottom: 0.5rem; }}
  .cta-sub {{ font-size: 1rem; color: #94a3b8; line-height: 1.5; }}
  .nav {{ position: fixed; bottom: 1.5rem; right: 2rem; display: flex; gap: 0.5rem; z-index: 100; }}
  .nav-btn {{ padding: 0.5rem 1rem; background: #1e293b; border: 1px solid #334155; color: #e2e8f0; border-radius: 6px; cursor: pointer; font-size: 0.85rem; transition: background 0.15s; }}
  .nav-btn:hover {{ background: #334155; }}
  .slide-counter {{ position: fixed; bottom: 1.5rem; left: 2rem; font-size: 0.75rem; color: #475569; }}
  .branding {{ position: fixed; top: 1.2rem; right: 2rem; font-size: 0.7rem; color: #334155; font-weight: 600; letter-spacing: 0.08em; }}
  .sub-text {{ font-size: 1.05rem; color: #94a3b8; margin-top: 0.75rem; line-height: 1.6; max-width: 700px; }}
</style>
</head>
<body>
<div class="deck">
  <div class="branding">THE FAILURE ORACLE</div>

  <!-- Slide 1: Title -->
  <div class="slide active" id="slide-1">
    <div class="slide-tag">BOARD PRESENTATION · CONFIDENTIAL</div>
    <span class="risk-chip">{risk_label}</span>
    <h1>{req.startup_name}</h1>
    <h1 style="color:{risk_color}">{req.pattern_name}</h1>
    <p class="sub-text">{content.get("executive_summary",{}).get("headline","Oracle Analysis Report")}</p>
    <div class="metric-row" style="margin-top:2.5rem">
      <div class="metric"><div class="metric-val" style="color:{risk_color}">{pct}%</div><div class="metric-label">Pattern Match</div></div>
      <div class="metric"><div class="metric-val" style="color:#f59e0b">{req.days_to_crisis}</div><div class="metric-label">Days to Crisis</div></div>
      <div class="metric"><div class="metric-val" style="color:#ef4444">{fail_pct}%</div><div class="metric-label">Hist. Failure Rate</div></div>
      <div class="metric"><div class="metric-val" style="color:#10b981">{surv_pct}%</div><div class="metric-label">Survival Rate</div></div>
    </div>
  </div>

  <!-- Slide 2: Executive Summary -->
  <div class="slide" id="slide-2">
    <div class="slide-tag">EXECUTIVE SUMMARY</div>
    <h2>{content.get("executive_summary",{}).get("headline","Key Findings")}</h2>
    <ul>{exec_bullets}</ul>
    {f'<p class="sub-text" style="margin-top:1.5rem;font-style:italic">{req.match_reasoning}</p>' if req.match_reasoning else ''}
  </div>

  <!-- Slide 3: Risk Assessment -->
  <div class="slide" id="slide-3">
    <div class="slide-tag">RISK ASSESSMENT</div>
    <h2>{content.get("risk_assessment",{}).get("headline","Warning Signals Present")}</h2>
    <ul>{risk_bullets}</ul>
  </div>

  <!-- Slide 4: Historical Context -->
  <div class="slide" id="slide-4">
    <div class="slide-tag">HISTORICAL CONTEXT</div>
    <h2>{content.get("historical_context",{}).get("headline","What Happened to Others")}</h2>
    <ul>{hist_bullets}</ul>
    <div class="metric-row" style="margin-top:2rem">
      <div class="metric"><div class="metric-val" style="color:#ef4444">{fail_pct}%</div><div class="metric-label">Failed Without Action</div></div>
      <div class="metric"><div class="metric-val" style="color:#10b981">{surv_pct}%</div><div class="metric-label">Survived With Playbook</div></div>
    </div>
  </div>

  {famous_slide}

  <!-- Slide 5/6: Recommended Actions -->
  <div class="slide" id="slide-{6 if famous else 5}">
    <div class="slide-tag">RECOMMENDED ACTIONS</div>
    <h2>{content.get("recommended_actions",{}).get("headline","Board-Mandated Actions")}</h2>
    <ul>{action_bullets}</ul>
  </div>

  <!-- Slide 6/7: Closing CTA -->
  <div class="slide" id="slide-{7 if famous else 6}">
    <div class="slide-tag">CALL TO ACTION</div>
    <div class="cta-box">
      <div class="cta-headline">{cta.get("headline","Act within the window")}</div>
      <div class="cta-sub">{cta.get("sub","")}</div>
    </div>
    <p class="sub-text" style="margin-top:2rem;font-size:0.85rem;color:#475569">
      Generated by The Failure Oracle · Powered by Gemini 3 Flash + MongoDB Atlas Vector Search<br>
      Pattern: {req.pattern_name} · {pct}% match confidence · {req.days_to_crisis} days to projected crisis
    </p>
  </div>
</div>

<div class="slide-counter" id="counter">1 / <span id="total"></span></div>
<div class="nav">
  <button class="nav-btn" onclick="prev()">← Prev</button>
  <button class="nav-btn" onclick="next()">Next →</button>
</div>

<script>
  const slides = document.querySelectorAll('.slide');
  let current = 0;
  document.getElementById('total').textContent = slides.length;
  function show(n) {{
    slides[current].classList.remove('active');
    current = (n + slides.length) % slides.length;
    slides[current].classList.add('active');
    document.getElementById('counter').innerHTML = (current+1) + ' / ' + slides.length;
  }}
  function next() {{ show(current + 1); }}
  function prev() {{ show(current - 1); }}
  document.addEventListener('keydown', e => {{
    if (e.key === 'ArrowRight' || e.key === ' ') next();
    if (e.key === 'ArrowLeft') prev();
  }});
</script>
</body>
</html>"""


@router.post("/slides")
async def export_slides(req: SlideExportRequest):
    """
    Generate a board-ready slide deck from an Oracle analysis.
    Returns a self-contained HTML presentation.
    """
    try:
        content = await _generate_deck_content(req)
        html = _build_html_deck(req, content)
        safe_name = req.startup_name.replace(" ", "-").replace("/", "-").lower()
        return HTMLResponse(
            content=html,
            headers={
                "Content-Disposition": f'attachment; filename="oracle-board-deck-{safe_name}.html"',
                "Content-Type": "text/html; charset=utf-8",
            }
        )
    except Exception as e:
        logger.exception("Slides export failed")
        raise HTTPException(status_code=500, detail=str(e))
