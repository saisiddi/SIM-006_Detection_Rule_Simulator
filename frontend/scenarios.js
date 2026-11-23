// Demo scenarios. Each builds a request with a fresh timestamp at click time so R-01
// (replay window of +/-30 s) does not fire by accident. Profiles mirror sim_006/simulator.py.
// `expect` is what each scenario is designed to produce; the UI compares it with the API's answer.

const isoNow = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

const baseEvent = () => ({
  event_type: "telemetry",
  timestamp: isoNow(),
  voltage_v: 48.0,
  temperature_c: 25.0,
  soc_percent: 50.0,
  sequence_number: 101,
  open_incident: false,
  prior_soc_percent: 49.0,
  charging_source_present: true,
});

const request = (battery_id, event) => ({ battery_id, event, rule_ids: "all" });

export const SCENARIOS = [
  {
    id: "clean",
    label: "Clean pass",
    expect: "PASS",
    build: () => request("SIM-BATTERY-001", baseEvent()),
  },
  {
    id: "voltage-warning",
    label: "Voltage warning",
    expect: "WARN",
    // 58 V sits inside the 56-61.6 V WARN band (see tests/fixtures/event_voltage_warn.json).
    build: () => request("SIM-BATTERY-002", { ...baseEvent(), voltage_v: 58.0 }),
  },
  {
    id: "replay",
    label: "Replay attack",
    expect: "HARD_FAIL",
    build: () =>
      request("SIM-BATTERY-003", {
        ...baseEvent(),
        sequence_number: 100,
        last_seen_sequence_number: 100,
      }),
  },
  {
    id: "missing-timestamp",
    label: "Missing timestamp",
    expect: "HARD_FAIL",
    build: () => {
      const event = baseEvent();
      delete event.timestamp;
      return request("SIM-BATTERY-004", event);
    },
  },
  {
    id: "firmware",
    label: "Firmware tampering",
    expect: "HARD_FAIL",
    build: () =>
      request("SIM-BATTERY-005", {
        ...baseEvent(),
        event_type: "firmware",
        firmware_hash: "observed-hash",
        expected_firmware_hash: "expected-hash",
      }),
  },
  {
    id: "impossible-soc",
    label: "Impossible SOC",
    expect: "HARD_FAIL",
    build: () =>
      request("SIM-BATTERY-006", {
        ...baseEvent(),
        soc_percent: 80.0,
        prior_soc_percent: 50.0,
        charging_source_present: false,
      }),
  },
];
