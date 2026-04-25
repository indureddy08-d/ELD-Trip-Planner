// ── Instruction type classification ──────────────────────────────────────────

function classifyInstruction(instruction) {
  const t = instruction.toLowerCase();
  if (t.includes("pre-trip") || t.includes("inspection"))                     return "service";
  if (t.includes("depart"))                                                    return "transit";
  if (t.includes("arrive at pickup") || (t.includes("depart") && t.includes("loaded"))) return "transit";
  if (t.includes("pickup"))                                                    return "pickup";
  if (t.includes("dropoff"))                                                   return "dropoff";
  if (t.includes("sleeper"))                                                   return "sleeper";
  if (t.includes("break") || t.includes("off-duty"))                          return "rest";
  if (t.includes("fuel"))                                                      return "fuel";
  return "transit";
}

const CATEGORY_COLOR = {
  transit:  "var(--c-muted)",
  pickup:   "#4f8ef7",
  dropoff:  "#10b981",
  sleeper:  "#8b5cf6",
  rest:     "#e8960a",
  fuel:     "#ef4444",
  service:  "#6366f1",
};

// Categories that get a left accent bar — compliance-critical stops
const ACCENT_CATEGORIES = new Set(["rest", "sleeper", "fuel"]);

// ── Detail token parser ───────────────────────────────────────────────────────

function parseDetailTokens(details) {
  if (!details) return { prose: details || "", tokens: [] };

  const tokens = [];

  // Day/time: "Day 2, 00:00"
  const daytimeRe = /Day\s+\d+,\s+\d{2}:\d{2}/g;
  let m;
  while ((m = daytimeRe.exec(details)) !== null) {
    tokens.push({ type: "daytime", value: m[0] });
  }

  // Duration: "16h 44m" or "30m" or "1h" — but not inside distance values
  const durationRe = /\b(\d+h(?:\s+\d+m)?|\d+m)(?!\s*i)/g;
  while ((m = durationRe.exec(details)) !== null) {
    tokens.push({ type: "duration", value: m[1] });
  }

  // Distance: "1,234 mi" or "920.0 mi"
  const distanceRe = /[\d,]+(?:\.\d+)?\s+mi\b/g;
  while ((m = distanceRe.exec(details)) !== null) {
    tokens.push({ type: "distance", value: m[0] });
  }

  return { prose: details, tokens };
}

// ── Single instruction row ────────────────────────────────────────────────────

function InstructionRow({ item }) {
  const category   = classifyInstruction(item.instruction);
  const color      = CATEGORY_COLOR[category];
  const hasAccent  = ACCENT_CATEGORIES.has(category);
  const { prose, tokens } = parseDetailTokens(item.details);

  const daytimes  = tokens.filter((t) => t.type === "daytime");
  const durations = tokens.filter((t) => t.type === "duration");
  const distances = tokens.filter((t) => t.type === "distance");

  // Show prose for compliance-critical steps (rest/sleeper/fuel) even when
  // tokens exist — the CFR citation and context matter for those steps.
  // Suppress prose for transit/pickup/dropoff/service steps where tokens
  // already carry all the useful information.
  const showProse = prose && (tokens.length === 0 || hasAccent);

  // Extract CFR reference if present for special treatment
  const cfrMatch = prose?.match(/\(49 CFR [^)]+\)/);
  const cfrRef = cfrMatch ? cfrMatch[0] : null;
  const proseWithoutCFR = cfrRef ? prose.replace(cfrRef, "").trim() : prose;

  return (
    <div className={`ri-row ${hasAccent ? "ri-row-accent" : ""}`}
         style={hasAccent ? { "--ri-accent": color } : undefined}>

      {/* Step number — colored by category */}
      <div className="ri-step" style={{ color }}>
        {item.step}
      </div>

      {/* Content */}
      <div className="ri-body">

        {/* Primary action */}
        <div className="ri-title">{item.instruction}</div>

        {/* Structured data row */}
        {tokens.length > 0 && (
          <div className="ri-data">
            {daytimes.map((t, i) => (
              <span key={`dt-${i}`} className="ri-data-time" style={{ color }}>
                {t.value}
              </span>
            ))}
            {distances.map((t, i) => (
              <span key={`di-${i}`} className="ri-data-num">{t.value}</span>
            ))}
            {durations.map((t, i) => (
              <span key={`du-${i}`} className="ri-data-num">{t.value}</span>
            ))}
          </div>
        )}

        {/* Prose — shown for compliance steps and when no tokens exist */}
        {showProse && (
          <div className="ri-prose">
            {proseWithoutCFR}
            {cfrRef && <span className="ri-cfr">{cfrRef}</span>}
          </div>
        )}

      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RouteInstructions({ instructions }) {
  if (!instructions?.length) {
    return (
      <div className="timeline-empty">
        Plan a trip to see step-by-step driving instructions here.
      </div>
    );
  }

  return (
    <div className="ri-list">
      {instructions.map((item) => (
        <InstructionRow key={item.step} item={item} />
      ))}
    </div>
  );
}
