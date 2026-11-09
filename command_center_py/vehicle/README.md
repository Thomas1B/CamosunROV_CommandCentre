# vehicle

Everything about talking to the ROV. No user interface code here.

| File | What it does |
|---|---|
| `link.py` | UDP link to the Raspberry Pi: sends the 16-byte command packet at `RATE_HZ` and receives JSON telemetry. The wire format is described at the top of the file. `DemoLink` is a simulated vehicle for DEMO MODE. |
| `mixer.py` | Stick shaping (deadzone and expo) and the thruster mix: turns stick and trigger values into a throttle of -100 % to +100 % for each of the six thrusters. Pure maths. |
| `reference.py` | Bar30 depth sensor reference values: surface pressure, water density and second-order calibration. |
| `profiles.py` | Saved vehicle profiles in `vehicle_profiles/` (name, IP address, ports and reference values). |

**Used by:** the CONNECT VEHICLE card (profiles, reference values, opening the link) and the console (link, mixer).

**Related settings in `config.py`:** `PI_HOST`, `CMD_PORT`, `TELEM_PORT`, `VIDEO_PORT`, `RATE_HZ`, `LINK_TIMEOUT_S`, `CONNECT_TIMEOUT_S`, `THRUSTERS`, `GAIN_STEPS`, `TILT_MIN`, `TILT_MAX`, `SURFACE_PRESSURE_HPA`, `WATER_DENSITY`, `SECOND_ORDER_CAL`, `DEMO_PACKET_LOSS`.
