import { useEffect, useRef, useMemo } from "react";
import { MapPin, Navigation, Flag, Clock, Route, AlertCircle, Loader2 } from "lucide-react";
import { formatMiles, formatHours } from "../../utils/formatters";

// Leaflet is loaded lazily to avoid SSR issues and keep the initial bundle lean.
// We import it inside useEffect so Vite doesn't try to tree-shake the CSS.

const LEG_COLORS = ["#4f8ef7", "#10b981", "#f59e0b"];

const LEG_META = [
  { icon: Navigation, label: "Current → Pickup",  colorIdx: 0 },
  { icon: Route,      label: "Pickup → Dropoff",  colorIdx: 1 },
];

function MapContainer({ legs }) {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);

  // Flatten all coordinates from all legs
  const allCoords = useMemo(() => {
    return legs.flatMap((leg) =>
      (leg.coordinates || []).map((c) => [c.lat, c.lng])
    );
  }, [legs]);

  const hasCoords = allCoords.length > 0;

  useEffect(() => {
    if (!hasCoords || !mapRef.current) return;

    // Dynamically import Leaflet to avoid SSR/bundle issues
    import("leaflet").then((L) => {
      import("leaflet/dist/leaflet.css");

      // Fix default marker icon paths broken by Vite bundling
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      // Destroy previous instance if re-rendering
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }

      const map = L.map(mapRef.current, { zoomControl: true, scrollWheelZoom: true });
      mapInstanceRef.current = map;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 18,
      }).addTo(map);

      // Draw each leg as a coloured polyline
      legs.forEach((leg, i) => {
        const coords = (leg.coordinates || []).map((c) => [c.lat, c.lng]);
        if (coords.length < 2) return;

        L.polyline(coords, {
          color: LEG_COLORS[i % LEG_COLORS.length],
          weight: 4,
          opacity: 0.85,
        }).addTo(map);
      });

      // Place markers at each waypoint
      const waypoints = legs.map((l) => l.coordinates?.[0]).filter(Boolean);
      const lastLeg = legs[legs.length - 1];
      const lastCoord = lastLeg?.coordinates?.[lastLeg.coordinates.length - 1];
      if (lastCoord) waypoints.push(lastCoord);

      const markerLabels = [
        legs[0]?.from_label,
        ...legs.slice(0, -1).map((l) => l.to_label),
        lastLeg?.to_label,
      ];

      waypoints.forEach((coord, i) => {
        if (!coord) return;
        L.marker([coord.lat, coord.lng])
          .addTo(map)
          .bindPopup(`<strong>${markerLabels[i] || ""}</strong>`);
      });

      // Fit map to route bounds
      if (allCoords.length > 0) {
        map.fitBounds(allCoords, { padding: [32, 32] });
      }
    });

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [allCoords, legs, hasCoords]);

  if (!hasCoords) {
    return (
      <div className="map-no-coords">
        <AlertCircle size={20} />
        <span>
          Live route map requires an ORS API key.
          Add <code>ORS_API_KEY</code> to <code>backend/.env</code> to enable
          real coordinates and polyline rendering. Distance and timing data
          above are still accurate — they use a lookup table fallback.
        </span>
      </div>
    );
  }

  return <div ref={mapRef} className="leaflet-map" />;
}

export default function RouteMap({ routeData, loading, error }) {
  if (loading) {
    return (
      <div className="route-map-loading">
        <Loader2 size={24} className="spin" />
        <span>Resolving route…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="route-map-error">
        <AlertCircle size={18} />
        <div>
          <strong>Route Error</strong>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!routeData) return null;

  const { legs, total_distance_miles, total_duration_hours, provider, from_cache } = routeData;

  return (
    <div className="route-map-wrap">
      {/* Provider badge */}
      <div className="route-provider-row">
        <span className={`provider-badge ${from_cache ? "fallback" : "live"}`}>
          {from_cache ? "Lookup Table" : "Live Route Data"}
        </span>
        <span className="route-totals">
          <Route size={13} /> {formatMiles(total_distance_miles)}
          <Clock size={13} style={{ marginLeft: 12 }} /> {formatHours(total_duration_hours)} est. drive time
        </span>
      </div>

      {/* Map */}
      <MapContainer legs={legs} />

      {/* Leg breakdown — inline row, not cards */}
      <div className="legs-row">
        {legs.map((leg, i) => {
          const meta = LEG_META[i] || { icon: MapPin, label: `Leg ${i + 1}`, colorIdx: i % LEG_COLORS.length };
          const Icon = meta.icon;
          const color = LEG_COLORS[meta.colorIdx];
          return (
            <div key={i} className="leg-inline">
              <span className="leg-inline-badge" style={{ color }}>
                <Icon size={11} /> Leg {i + 1}
              </span>
              <span className="leg-inline-route">
                {leg.from_label} → {leg.to_label}
              </span>
              <span className="leg-inline-stats">
                {formatMiles(leg.distance_miles)} · {formatHours(leg.duration_hours)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
