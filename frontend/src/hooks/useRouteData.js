import { useState, useEffect } from "react";
import { tripApi } from "../api/tripApi";

/**
 * Fetches route data (distance, duration, legs, coordinates) whenever
 * the three location fields are all populated.
 *
 * Debounced by 600ms so we don't fire on every keystroke.
 */
export function useRouteData(form) {
  const [routeData, setRouteData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const { current_location, pickup_location, dropoff_location } = form;
  const ready = current_location.trim() && pickup_location.trim() && dropoff_location.trim();

  useEffect(() => {
    if (!ready) {
      setRouteData(null);
      setError(null);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await tripApi.getRoute({
          current_location,
          pickup_location,
          dropoff_location,
        });
        setRouteData(data);
      } catch (err) {
        setError(err.message);
        setRouteData(null);
      } finally {
        setLoading(false);
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [current_location, pickup_location, dropoff_location, ready]);

  return { routeData, loading, error };
}
