import { useState, useCallback } from "react";
import { tripApi } from "../api/tripApi";
import { useRecentTrips } from "./useRecentTrips";

const INITIAL_FORM = {
  current_location: "",
  pickup_location: "",
  dropoff_location: "",
  current_cycle_used_hours: "",
  // FMCSA RODS header fields (49 CFR 395.8)
  driver_name: "",
  carrier_name: "",
  main_office_address: "",
  vehicle_numbers: "",
  co_driver_name: "",
  shipper_and_commodity: "",
};

// ── Quick test scenarios ──────────────────────────────────────────────────────
// Realistic inputs that exercise distinct HOS code paths.
// Values chosen so each scenario reliably triggers its named behaviour.

export const PRESETS = [
  {
    id: "short",
    label: "Short Haul",
    description: "~180 mi · same-day · no breaks needed",
    form: {
      current_location:         "Columbus, OH",
      pickup_location:          "Pittsburgh, PA",
      dropoff_location:         "Philadelphia, PA",
      current_cycle_used_hours: "10",
      driver_name:              "James R. Mitchell",
      carrier_name:             "Midwest Freight Solutions LLC",
      main_office_address:      "Columbus, OH",
      vehicle_numbers:          "TRK-4821 / TRL-9034",
      co_driver_name:           "",
      shipper_and_commodity:    "Acme Paper Co. — Paper Products",
    },
  },
  {
    id: "break",
    label: "Break Required",
    description: "~520 mi · triggers 30-min mandatory break",
    form: {
      current_location:         "Chicago, IL",
      pickup_location:          "St. Louis, MO",
      dropoff_location:         "Nashville, TN",
      current_cycle_used_hours: "20",
      driver_name:              "Sandra L. Torres",
      carrier_name:             "Central States Transport Inc.",
      main_office_address:      "Chicago, IL",
      vehicle_numbers:          "TRK-7703 / TRL-1122",
      co_driver_name:           "",
      shipper_and_commodity:    "Riverside Foods — Packaged Goods",
    },
  },
  {
    id: "fuel",
    label: "Fuel Stop",
    description: "~1,100 mi · forces mid-route fuel stop",
    form: {
      current_location:         "Los Angeles, CA",
      pickup_location:          "Phoenix, AZ",
      dropoff_location:         "Dallas, TX",
      current_cycle_used_hours: "5",
      driver_name:              "Robert D. Nguyen",
      carrier_name:             "Southwest Long Haul Carriers",
      main_office_address:      "Phoenix, AZ",
      vehicle_numbers:          "TRK-2290 / TRL-5567",
      co_driver_name:           "",
      shipper_and_commodity:    "Desert Electronics — Consumer Electronics",
    },
  },
  {
    id: "cycle",
    label: "Cycle Exhausted",
    description: "70h used · shows cycle-limit warning",
    form: {
      current_location:         "Atlanta, GA",
      pickup_location:          "Charlotte, NC",
      dropoff_location:         "Washington, DC",
      current_cycle_used_hours: "70",
      driver_name:              "Marcus T. Williams",
      carrier_name:             "Southeast Express Logistics",
      main_office_address:      "Atlanta, GA",
      vehicle_numbers:          "TRK-6614 / TRL-3381",
      co_driver_name:           "",
      shipper_and_commodity:    "AutoParts Direct — Automotive Components",
    },
  },
];

export function useTripPlanner() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);       // { message, status }
  const [activeTab, setActiveTab] = useState("summary");
  const { trips: recentTrips, saveTrip, clearTrips, removeTrip } = useRecentTrips();

  const handleChange = useCallback((e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }, []);

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    setActiveTab("summary");

    try {
      const data = await tripApi.planTrip({
        ...form,
        current_cycle_used_hours: parseFloat(form.current_cycle_used_hours),
      });
      setResult(data);
      saveTrip(form, data);          // persist to recent trips
    } catch (err) {
      setResult(null);
      setError({ message: err.message, status: err.status ?? null });
    } finally {
      setLoading(false);
    }
  }, [form, saveTrip]);

  const reset = useCallback(() => {
    setForm(INITIAL_FORM);
    setResult(null);
    setError(null);
  }, []);

  const loadPreset = useCallback((preset) => {
    setForm(preset.form);
    setResult(null);
    setError(null);
  }, []);

  // Load a recent trip — populates the form and clears the current result
  const loadRecentTrip = useCallback((trip) => {
    setForm(trip.form);
    setResult(null);
    setError(null);
  }, []);

  return {
    form, result, loading, error, activeTab, setActiveTab,
    handleChange, handleSubmit, reset, loadPreset,
    recentTrips, loadRecentTrip, clearTrips, removeTrip,
  };
}
