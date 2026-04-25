import { ArrowRight, Loader2, ChevronDown, ChevronUp, FileText } from "lucide-react";
import { useState } from "react";
import { PRESETS } from "../hooks/useTripPlanner";

// ── Field definitions ─────────────────────────────────────────────────────────

const LOCATION_FIELDS = [
  {
    name: "current_location",
    label: "Current Location",
    placeholder: "City, State",
    role: "origin",
  },
  {
    name: "pickup_location",
    label: "Pickup",
    placeholder: "City, State",
    role: "waypoint",
  },
  {
    name: "dropoff_location",
    label: "Dropoff",
    placeholder: "City, State",
    role: "destination",
  },
];

// ── Route fields — sequential location inputs with a connecting rail ──────────

function RouteFields({ form, onChange }) {
  return (
    <div className="route-fields">
      {LOCATION_FIELDS.map(({ name, label, placeholder, role }, idx) => {
        const isLast = idx === LOCATION_FIELDS.length - 1;
        return (
          <div key={name} className="route-field-row">
            {/* Rail: dot + connecting line */}
            <div className="route-rail">
              <div className={`route-dot route-dot-${role}`} />
              {!isLast && <div className="route-line" />}
            </div>

            {/* Field */}
            <div className="route-field">
              <label className="route-field-label" htmlFor={name}>{label}</label>
              <input
                id={name}
                className="field-input"
                type="text"
                name={name}
                value={form[name]}
                onChange={onChange}
                placeholder={placeholder}
                required
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Cycle field — compliance input, visually distinct ─────────────────────────
// Tinted block signals this is a different kind of input — compliance, not location.

function CycleField({ value, onChange }) {
  return (
    <div className="cycle-field">
      <div className="cycle-field-header">
        <label className="cycle-field-label" htmlFor="current_cycle_used_hours">
          Cycle Hours Used
        </label>
        <span className="cycle-field-cap">of 70h</span>
      </div>
      <div className="cycle-input-wrap">
        <input
          id="current_cycle_used_hours"
          className="field-input cycle-input"
          type="number"
          name="current_cycle_used_hours"
          value={value}
          onChange={onChange}
          placeholder="0"
          min={0}
          max={70}
          step="0.5"
          required
        />
        <span className="cycle-input-suffix">h</span>
      </div>
      <p className="cycle-field-hint">
        Hours used in the current 70h/8-day cycle
      </p>
    </div>
  );
}

// ── FMCSA RODS fields — collapsible section ───────────────────────────────────
// These fields are required on the official FMCSA Driver's Daily Log (49 CFR 395.8).
// Collapsed by default so the form stays clean for quick trips.
// Single-column layout — sidebar is 340px, not wide enough for two columns.

const RODS_FIELDS = [
  { name: "driver_name",           label: "Driver Name",          placeholder: "Full legal name" },
  { name: "co_driver_name",        label: "Co-Driver Name",       placeholder: "N/A if solo" },
  { name: "carrier_name",          label: "Carrier Name",         placeholder: "Motor carrier name" },
  { name: "main_office_address",   label: "Main Office Address",  placeholder: "City, State" },
  { name: "vehicle_numbers",       label: "Truck / Trailer #",    placeholder: "Unit numbers or license plate" },
  { name: "shipper_and_commodity", label: "Shipper & Commodity",  placeholder: "Shipper name — cargo type" },
];

function RODSFields({ form, onChange }) {
  const [open, setOpen] = useState(false);

  const filled = RODS_FIELDS.filter(f => form[f.name]?.trim()).length;
  const allFilled = filled === RODS_FIELDS.length;

  return (
    <div className="rods-section">
      <button
        type="button"
        className={`rods-toggle ${open ? "rods-toggle-open" : ""}`}
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
      >
        {/* Left: stacked title + subtitle */}
        <span className="rods-toggle-left">
          <FileText size={11} strokeWidth={1.5} className="rods-toggle-icon" />
          <span className="rods-toggle-text">
            <span className="rods-toggle-label">Driver &amp; Log Info</span>
            <span className="rods-toggle-sub">Name, carrier, vehicle · for the log sheet</span>
          </span>
        </span>

        {/* Right: completion pill + chevron */}
        <span className="rods-toggle-right">
          {filled > 0 && (
            <span className={`rods-filled-badge ${allFilled ? "rods-filled-badge-complete" : ""}`}>
              {allFilled ? "Complete" : `${filled} of ${RODS_FIELDS.length}`}
            </span>
          )}
          {open ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
        </span>
      </button>

      {open && (
        <div className="rods-fields">
          {RODS_FIELDS.map(({ name, label, placeholder }) => (
            <div key={name} className="rods-field-row">
              <label className="rods-field-label" htmlFor={name}>{label}</label>
              <input
                id={name}
                className="field-input rods-input"
                type="text"
                name={name}
                value={form[name] || ""}
                onChange={onChange}
                placeholder={placeholder}
              />
            </div>
          ))}
          <p className="rods-hint">
            These details print on the ELD log sheet. All optional.
          </p>
        </div>
      )}
    </div>
  );
}

// ── Demo scenarios — moved below the submit button ───────────────────────────
// Secondary feature. Positioned after the primary action so it reads as
// "optional shortcut", not the main way to use the form.

function DemoScenarios({ activePresetId, onLoad }) {
  return (
    <div className="demo-root">
      <div className="demo-header">
        <span className="demo-label">Demo scenarios</span>
        <span className="demo-hint">Load sample data</span>
      </div>
      <div className="demo-buttons">
        {PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className={`demo-btn ${activePresetId === preset.id ? "demo-btn-active" : ""}`}
            onClick={() => onLoad(preset)}
            title={preset.description}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function TripForm({ form, onChange, onSubmit, onLoadPreset, activePresetId, loading }) {
  return (
    <form onSubmit={onSubmit} className="trip-form">

      {/* Panel identity — gives the sidebar context */}
      <div className="form-heading">
        <span className="form-heading-title">Plan a Trip</span>
        <span className="form-heading-sub">HOS-compliant · 70h/8-day cycle</span>
      </div>

      {/* Route — sequential location fields */}
      <RouteFields form={form} onChange={onChange} />

      {/* Cycle — compliance input in a tinted block */}
      <CycleField value={form.current_cycle_used_hours} onChange={onChange} />

      {/* FMCSA RODS header fields — collapsible */}
      <RODSFields form={form} onChange={onChange} />

      {/* Submit */}
      <button type="submit" className="btn-dispatch" disabled={loading}>
        {loading ? (
          <>
            <Loader2 size={15} className="spin" />
            <span>Planning…</span>
          </>
        ) : (
          <>
            <span>Plan Trip</span>
            <ArrowRight size={15} />
          </>
        )}
      </button>

      {/* Demo scenarios — secondary, below the primary action */}
      <DemoScenarios activePresetId={activePresetId} onLoad={onLoadPreset} />

    </form>
  );
}
