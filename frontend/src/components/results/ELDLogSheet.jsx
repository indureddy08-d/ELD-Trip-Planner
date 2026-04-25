import { Printer, Info } from "lucide-react";
import { STATUS_META, formatHours, formatMiles } from "../../utils/formatters";

// FMCSA logbook row order: Off Duty → Sleeper Berth → Driving → On Duty ND
const ROW_ORDER = ["OFF", "SB", "D", "ON"];

const ROW_LABELS = {
  OFF: "1. Off Duty",
  SB:  "2. Sleeper Berth",
  D:   "3. Driving",
  ON:  "4. On Duty\n(Not Driving)",
};

const HOUR_LABELS = [
  "12 AM","1","2","3","4","5","6","7","8","9","10","11",
  "12 PM","1","2","3","4","5","6","7","8","9","10","11","12 AM",
];

const MAJOR_COLS = new Set([0, 12, 24]);

function fmtHourToTime(h) {
  const totalMin = Math.round(h * 60);
  const hh = Math.floor(totalMin / 60) % 24;
  const mm = totalMin % 60;
  const period = hh < 12 ? "AM" : "PM";
  const h12 = hh === 0 ? 12 : hh > 12 ? hh - 12 : hh;
  return `${h12}:${String(mm).padStart(2, "0")} ${period}`;
}

// ── Duty Grid ─────────────────────────────────────────────────────────────────

function DutyGrid({ timeline }) {
  const rowBlocks = {};
  ROW_ORDER.forEach((s) => { rowBlocks[s] = []; });
  timeline.forEach((seg) => {
    if (rowBlocks[seg.status]) rowBlocks[seg.status].push(seg);
  });

  const transitionPoints = new Set();
  timeline.forEach((seg) => {
    transitionPoints.add(seg.start);
    transitionPoints.add(seg.end);
  });
  const transitions = [...transitionPoints];

  return (
    <div className="eld-form-grid">

      <div className="eld-form-header-row">
        <div className="eld-form-row-label" />
        <div className="eld-form-track-area">
          {HOUR_LABELS.map((label, i) => (
            <div
              key={i}
              className={`eld-form-hour-col ${MAJOR_COLS.has(i) ? "eld-form-hour-col-major" : ""}`}
            >
              <span className="eld-form-hour-label">{label}</span>
            </div>
          ))}
        </div>
        <div className="eld-form-total-col eld-form-total-heading">Total</div>
      </div>

      <div className="eld-form-ampm-row">
        <div className="eld-form-row-label" />
        <div className="eld-form-track-area eld-form-ampm-track">
          <span className="eld-form-ampm-label" style={{ left: "25%" }}>AM</span>
          <span className="eld-form-ampm-label" style={{ left: "75%" }}>PM</span>
          <div className="eld-form-noon-line" style={{ left: "50%" }} />
        </div>
        <div className="eld-form-total-col" />
      </div>

      {ROW_ORDER.map((status) => {
        const meta   = STATUS_META[status];
        const blocks = rowBlocks[status];
        const total  = blocks.reduce((sum, b) => sum + (b.end - b.start), 0);

        return (
          <div key={status} className="eld-form-duty-row">
            <div className="eld-form-row-label">
              {ROW_LABELS[status].split("\n").map((line, i) => (
                <span key={i} className="eld-form-label-line">{line}</span>
              ))}
            </div>

            <div className="eld-form-track-area eld-form-track-ruled">
              {Array.from({ length: 25 }, (_, i) => (
                <div
                  key={i}
                  className={`eld-form-col-line ${MAJOR_COLS.has(i) ? "eld-form-col-line-major" : ""}`}
                  style={{ left: `${(i / 24) * 100}%` }}
                />
              ))}
              {Array.from({ length: 48 }, (_, i) => (
                i % 2 !== 0 && (
                  <div
                    key={i}
                    className="eld-form-halfhour-tick"
                    style={{ left: `${(i / 48) * 100}%` }}
                  />
                )
              ))}
              {blocks.map((b, i) => {
                const left  = (b.start / 24) * 100;
                const width = ((b.end - b.start) / 24) * 100;
                return (
                  <div
                    key={i}
                    className="eld-form-line-h"
                    style={{ left: `${left}%`, width: `${width}%`, borderColor: meta.color }}
                    title={`${b.label}: ${fmtHourToTime(b.start)} – ${fmtHourToTime(b.end)}`}
                  />
                );
              })}
              {transitions.map((pt) => (
                <div
                  key={pt}
                  className="eld-form-line-v"
                  style={{ left: `${(pt / 24) * 100}%` }}
                />
              ))}
            </div>

            <div className="eld-form-total-col">
              {total > 0
                ? <span className="eld-form-total-value">{formatHours(total)}</span>
                : <span className="eld-form-total-zero">—</span>}
            </div>
          </div>
        );
      })}

    </div>
  );
}

// ── Log Card ──────────────────────────────────────────────────────────────────

function LogCard({ log, driverInfo = {} }) {
  const {
    driver_name           = "",
    carrier_name          = "",
    main_office_address   = "",
    vehicle_numbers       = "",
    co_driver_name        = "",
    shipper_and_commodity = "",
  } = driverInfo;

  return (
    <div className="eld-form-card">

      {/* ── Document header ── */}
      <div className="eld-form-card-header">
        <div className="eld-form-header-day">
          <span className="eld-form-day-label">Day</span>
          <span className="eld-form-day-num">{log.day_number}</span>
          <span className="eld-form-day-date">{log.log_date}</span>
        </div>
        <div className="eld-form-header-center">
          <span className="eld-form-header-reg">
            Driver's Daily Log · 49 CFR Part 395
          </span>
          <span className="eld-form-header-cycle">
            Property-carrying · 70h/8-day cycle
          </span>
        </div>
        <div className="eld-form-header-right">
          <div className="eld-form-header-field">
            <span className="eld-form-field-label">Miles Today</span>
            <span className="eld-form-field-value eld-form-miles-val">{formatMiles(log.total_miles)}</span>
          </div>
        </div>
      </div>

      {/* ── FMCSA RODS metadata fields (49 CFR 395.8) ── */}
      <div className="eld-rods-meta">
        {/* Show helper text when no driver info is provided */}
        {!driver_name && !carrier_name && !vehicle_numbers && !shipper_and_commodity && (
          <div className="eld-rods-helper">
            <Info size={13} />
            <span>
              Optional: Fill in driver & log info in the trip form to personalize these log sheets.
            </span>
          </div>
        )}
        
        <div className="eld-rods-row">
          <div className="eld-rods-cell eld-rods-cell-wide">
            <span className="eld-rods-label">Driver's Name</span>
            <span className={`eld-rods-value ${!driver_name ? "eld-rods-empty" : ""}`}>
              {driver_name || "—"}
            </span>
          </div>
          <div className="eld-rods-cell">
            <span className="eld-rods-label">Co-Driver</span>
            <span className={`eld-rods-value ${!co_driver_name ? "eld-rods-empty" : ""}`}>
              {co_driver_name || "N/A"}
            </span>
          </div>
        </div>
        <div className="eld-rods-row">
          <div className="eld-rods-cell eld-rods-cell-wide">
            <span className="eld-rods-label">Carrier Name</span>
            <span className={`eld-rods-value ${!carrier_name ? "eld-rods-empty" : ""}`}>
              {carrier_name || "—"}
            </span>
          </div>
          <div className="eld-rods-cell">
            <span className="eld-rods-label">Main Office Address</span>
            <span className={`eld-rods-value ${!main_office_address ? "eld-rods-empty" : ""}`}>
              {main_office_address || "—"}
            </span>
          </div>
        </div>
        <div className="eld-rods-row">
          <div className="eld-rods-cell eld-rods-cell-wide">
            <span className="eld-rods-label">Truck / Tractor & Trailer Numbers</span>
            <span className={`eld-rods-value ${!vehicle_numbers ? "eld-rods-empty" : ""}`}>
              {vehicle_numbers || "—"}
            </span>
          </div>
          <div className="eld-rods-cell">
            <span className="eld-rods-label">Shipper & Commodity</span>
            <span className={`eld-rods-value ${!shipper_and_commodity ? "eld-rods-empty" : ""}`}>
              {shipper_and_commodity || "—"}
            </span>
          </div>
        </div>
      </div>

      {/* ── 24-hour duty grid ── */}
      <DutyGrid timeline={log.timeline} />

      {/* ── Hours summary ── */}
      <div className="eld-form-summary">
        <div className="eld-form-summary-grid">
          {[
            { status: "D",   label: "Driving",      value: log.driving_hours },
            { status: "ON",  label: "On Duty (ND)",  value: log.on_duty_not_driving_hours },
            { status: "SB",  label: "Sleeper Berth", value: log.sleeper_berth_hours },
            { status: "OFF", label: "Off Duty",      value: log.off_duty_hours },
          ].map(({ status, label, value }) => {
            const color = STATUS_META[status].color;
            return (
              <div key={status} className="eld-form-summary-cell">
                <span className="eld-form-summary-swatch" style={{ background: color }} />
                <span className="eld-form-summary-name">{label}</span>
                <span className="eld-form-summary-val">{formatHours(value)}</span>
              </div>
            );
          })}
          <div className="eld-form-summary-cell eld-form-summary-total">
            <span className="eld-form-summary-swatch" />
            <span className="eld-form-summary-name">Total On-Duty</span>
            <span className="eld-form-summary-val">
              {formatHours(log.driving_hours + log.on_duty_not_driving_hours)}
            </span>
          </div>
        </div>
      </div>

      {/* ── Remarks ── */}
      {log.remarks && (
        <div className="eld-form-remarks">
          <span className="eld-form-remarks-label">Remarks / Exceptions</span>
          <div className="eld-form-remarks-entries">
            {log.remarks.split("; ").map((r, i) => (
              <div key={i} className="eld-form-remark-row">
                <span className="eld-form-remark-num">{i + 1}</span>
                <span className="eld-form-remark-text">{r}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Certification footer — required by 49 CFR 395.8 ── */}
      {/* Driver name auto-filled from the form input.          */}
      <div className="eld-certification">

        {/* Row 1: signature + date fields */}
        <div className="eld-cert-row">

          {/* Signature block */}
          <div className="eld-cert-sig-block">
            <span className="eld-cert-field-label">Driver's Signature</span>
            <span className="eld-cert-line" />
            <span className="eld-cert-name">
              {driver_name || <span className="eld-cert-name-empty">Print name</span>}
            </span>
          </div>

          {/* Date block */}
          <div className="eld-cert-date-block">
            <span className="eld-cert-field-label">Date</span>
            <span className="eld-cert-line" />
            <span className="eld-cert-date-value">{log.log_date}</span>
          </div>

        </div>

        {/* Row 2: legal certification statement */}
        <p className="eld-cert-statement">
          I certify that my duty status entries for this 24-hour period are true and correct.
        </p>

      </div>

    </div>
  );
}

// ── Print toolbar ─────────────────────────────────────────────────────────────

function PrintToolbar({ logCount }) {
  return (
    <div className="eld-print-toolbar">
      <span className="eld-print-info">
        {logCount} day{logCount !== 1 ? "s" : ""} · 49 CFR Part 395
      </span>
      <button
        type="button"
        className="eld-print-btn"
        onClick={() => window.print()}
      >
        <Printer size={14} strokeWidth={2} />
        Print / Save as PDF
      </button>
    </div>
  );
}

// ── Export ────────────────────────────────────────────────────────────────────

export default function ELDLogSheet({ logs, driverInfo, totalDistanceMiles }) {
  if (!logs?.length) {
    return (
      <div className="eld-empty">
        Plan a trip to generate ELD log sheets here.
      </div>
    );
  }

  // Use the summary's authoritative total_distance_miles to avoid rounding
  // discrepancies between the route-API distance (summary) and the
  // simulation-derived distance (ELD generator: hours × 55 mph).
  //
  // For a single-day trip: the one log gets the full summary distance.
  // For multi-day trips: distribute proportionally by each day's raw miles
  // so the per-day values still add up to the correct total.
  const rawTotal = logs.reduce((sum, log) => sum + (log.total_miles || 0), 0);
  const authoritative = totalDistanceMiles != null ? totalDistanceMiles : rawTotal;

  const correctedLogs = logs.map((log) => {
    if (rawTotal === 0) return log;
    const share = (log.total_miles || 0) / rawTotal;
    return { ...log, total_miles: authoritative * share };
  });

  return (
    <div className="eld-logs" data-print-target="eld">
      <PrintToolbar logCount={logs.length} />
      {correctedLogs.map((log) => (
        <LogCard key={log.day_number} log={log} driverInfo={driverInfo} />
      ))}
    </div>
  );
}
