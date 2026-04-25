import { useState } from "react";
import { Truck, RotateCcw, XCircle, CheckCircle, BedDouble, FileText, ArrowLeft } from "lucide-react";
import TripForm from "./components/TripForm";
import SummaryCard from "./components/results/SummaryCard";
import RouteTimeline from "./components/results/RouteTimeline";
import RouteInstructions from "./components/results/RouteInstructions";
import ELDLogSheet from "./components/results/ELDLogSheet";
import RouteMap from "./components/results/RouteMap";
import HeaderDutyControl from "./components/HeaderDutyControl";
import HistoryButton from "./components/history/HistoryButton";
import { useTripPlanner } from "./hooks/useTripPlanner";
import { useRouteData } from "./hooks/useRouteData";
import { useDutySession } from "./hooks/useDutySession";
import "./App.css";

const TABS = [
  { id: "summary",      label: "Summary" },
  { id: "map",          label: "Map & Route" },
  { id: "stops",        label: "Stops & Rests" },
  { id: "instructions", label: "Route Instructions" },
  { id: "eld",          label: "ELD Log Sheets" },
];

export default function App() {
  const { form, result, loading, error, activeTab, setActiveTab,
          handleChange, handleSubmit, reset, loadPreset,
          recentTrips, loadRecentTrip, clearTrips, removeTrip } = useTripPlanner();
  const { routeData, loading: routeLoading, error: routeError } = useRouteData(form);
  const dutySession = useDutySession(result);

  const [activePresetId, setActivePresetId] = useState(null);

  // Derive mobile view from loading/result/error state directly.
  // No useEffect needed — this is pure derivation from existing state.
  // On desktop (>960px) the mobile-hidden class has no effect (CSS only applies it at ≤960px).
  // On mobile: show results panel whenever loading, result, or error is active.
  const showingResults = loading || !!result || !!error;
  const mobileView = showingResults ? "results" : "form";

  function handleLoadPreset(preset) {
    loadPreset(preset);
    setActivePresetId(preset.id);
  }

  function handleChange_(e) {
    setActivePresetId(null);
    handleChange(e);
  }

  function handleDismissError() {
    reset();
    setActivePresetId(null);
  }

  function handleLoadRecentTrip(trip) {
    loadRecentTrip(trip);
    setActivePresetId(null);
  }

  function handleReset() {
    reset();
    setActivePresetId(null);
  }

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="header-inner">
          <div className="brand">
            <div className="brand-icon"><Truck size={15} strokeWidth={2.5} /></div>
            <div className="brand-text">
              <div className="brand-name">ELD Trip Planner</div>
              <div className="brand-sub">HOS-Compliant Route Planning</div>
            </div>
          </div>
          <div className="header-controls">
            <HistoryButton
              trips={recentTrips}
              onLoad={handleLoadRecentTrip}
              onClear={clearTrips}
              onRemove={removeTrip}
            />
            <HeaderDutyControl session={dutySession} />
          </div>
        </div>
      </header>

      <main className="app-main">
        {/* ── Form panel ──
            Desktop: always visible (left sidebar, CSS grid).
            Mobile:  hidden when mobileView === "results". */}
        <aside className={`form-panel ${mobileView === "results" ? "mobile-hidden" : ""}`}>
          <TripForm
            form={form}
            onChange={handleChange_}
            onSubmit={handleSubmit}
            onLoadPreset={handleLoadPreset}
            activePresetId={activePresetId}
            loading={loading}
          />
          {result && (
            <button className="btn-text-link" onClick={handleReset}>
              <RotateCcw size={12} /> Plan another trip
            </button>
          )}
        </aside>

        {/* ── Results panel ──
            Desktop: always visible (right panel, CSS grid).
            Mobile:  hidden when mobileView === "form". */}
        <section className={`results-panel ${mobileView === "form" ? "mobile-hidden" : ""}`}>

          {/* Back button — only rendered on mobile via CSS */}
          <button
            className="mobile-back-btn"
            onClick={handleReset}
            aria-label="Back to form"
          >
            <ArrowLeft size={14} />
            Back to form
          </button>

          {/* Priority 1: Error state */}
          {error && (
            <div className="results-content">
              <div className="error-banner">
                <XCircle size={18} />
                <div>
                  <strong>
                    {error.status === 422
                      ? "Trip Cannot Be Planned"
                      : error.status === 400
                      ? "Invalid Input"
                      : error.status === 0
                      ? "Connection Error"
                      : "Planning Error"}
                  </strong>
                  <p>{error.message}</p>
                </div>
                <button
                  className="error-dismiss"
                  onClick={handleDismissError}
                  aria-label="Dismiss error"
                  title="Dismiss"
                >
                  <XCircle size={14} />
                </button>
              </div>
            </div>
          )}

          {/* Priority 2: Loading state */}
          {!error && loading && (
            <div className="empty-state">
              <div className="loading-spinner" />
              <p>Calculating HOS-compliant route...</p>
            </div>
          )}

          {/* Priority 3: Success state with results */}
          {!error && !loading && result && (
            <div className="results-content">
              {/* Tab bar */}
              <div className="tab-bar">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    className={`tab-btn ${activeTab === tab.id ? "active" : ""}`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                    {tab.id === "map" && routeData && !routeData.from_cache && (
                      <span className="tab-badge live-badge">Live</span>
                    )}
                    {tab.id === "eld" && result.eld_logs.length > 0 && (
                      <span className="tab-badge">{result.eld_logs.length}</span>
                    )}
                    {tab.id === "stops" && result.stops.length > 0 && (
                      <span className="tab-badge">{result.stops.length}</span>
                    )}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="tab-content">
                {activeTab === "summary" && (
                  <SummaryCard
                    summary={result.summary}
                    warnings={result.warnings}
                    assumptions={result.assumptions}
                    stops={result.stops}
                  />
                )}
                {activeTab === "map" && (
                  <RouteMap
                    routeData={loading ? null : routeData}
                    loading={routeLoading || loading}
                    error={routeError}
                  />
                )}
                {activeTab === "stops" && (
                  <RouteTimeline stops={result.stops} />
                )}
                {activeTab === "instructions" && (
                  <RouteInstructions instructions={result.route_instructions} />
                )}
                {activeTab === "eld" && (
                  <ELDLogSheet
                    logs={result.eld_logs}
                    driverInfo={result.driver_info}
                    totalDistanceMiles={result.summary.total_distance_miles}
                  />
                )}
              </div>
            </div>
          )}

          {/* Priority 4: Empty state */}
          {!error && !loading && !result && (
            <div className="empty-state">
              <div className="empty-icon"><Truck size={44} /></div>
              <h3>Ready to Plan</h3>
              <p>Enter a route and cycle hours to generate a fully HOS-compliant trip plan with ELD log sheets.</p>
              <div className="empty-features">
                <span className="empty-feature">
                  <CheckCircle size={12} strokeWidth={2} />
                  HOS-compliant scheduling
                </span>
                <span className="empty-feature">
                  <BedDouble size={12} strokeWidth={2} />
                  Break &amp; sleeper insertion
                </span>
                <span className="empty-feature">
                  <FileText size={12} strokeWidth={2} />
                  Multi-day ELD log sheets
                </span>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
