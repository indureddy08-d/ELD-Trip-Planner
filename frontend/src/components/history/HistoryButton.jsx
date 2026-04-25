import { useEffect, useRef, useState } from "react";
import { History } from "lucide-react";
import RecentTrips from "./RecentTrips";
import TripPreviewModal from "./TripPreviewModal";

export default function HistoryButton({ trips, onLoad, onClear, onRemove }) {
  const [open, setOpen]           = useState(false);
  const [preview, setPreview]     = useState(null); // trip being previewed
  const ref = useRef(null);

  // Close dropdown when clicking outside (but not when modal is open)
  useEffect(() => {
    function handleClick(e) {
      if (preview) return; // modal handles its own outside-click
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [preview]);

  function handleCardClick(trip) {
    setPreview(trip);   // open modal — dropdown stays open behind it
  }

  function handleModalLoad(trip) {
    onLoad(trip);
    setPreview(null);
    setOpen(false);
  }

  function handleModalClose() {
    setPreview(null);
  }

  if (!trips?.length) return null;

  return (
    <>
      <div className="hst-root" ref={ref}>

        {/* Trigger button */}
        <button
          type="button"
          className={`hst-btn ${open ? "hst-btn-open" : ""}`}
          onClick={() => setOpen((o) => !o)}
          aria-label="Trip history"
          title="Recent trips"
        >
          <History size={14} strokeWidth={2} />
          <span className="hst-count">{trips.length}</span>
        </button>

        {/* Dropdown panel */}
        {open && (
          <div className="hst-panel">
            <div className="hst-panel-header">
              <span className="hst-panel-title">Recent Trips</span>
              <span className="hst-panel-note">Click to preview</span>
            </div>
            <div className="hst-panel-body">
              <RecentTrips
                trips={trips}
                onLoad={handleCardClick}   // opens modal, not direct load
                onClear={() => { onClear(); setOpen(false); }}
                inline
              />
            </div>
          </div>
        )}

      </div>

      {/* Modal — rendered outside the dropdown so it's not clipped */}
      {preview && (
        <TripPreviewModal
          trip={preview}
          onLoad={handleModalLoad}
          onRemove={(id) => {
            onRemove(id);
            setPreview(null);
            // If this was the last trip, close the dropdown too
            if (trips.length === 1) setOpen(false);
          }}
          onClose={handleModalClose}
        />
      )}
    </>
  );
}
