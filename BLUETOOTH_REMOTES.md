# Xiaomi Bluetooth remote proof of concept

Requested hardware: Xiaomi Bluetooth handheld remote; exact model unknown.
Current Google TV phone pairing uses a network protocol, not Bluetooth. The
v0.4.7 adds a bottom-of-page Bluetooth scan and Pair with Pi action through
host BlueZ D-Bus access. The Pi retains Bluetooth bonds; the app's phone trust
store remains separate. No-PIN pairing is implemented, but has not yet been
verified with the physical Xiaomi. Bluetooth input forwarding is not enabled.

## Busy pairing recovery

If **Pair with Pi** reports `org.bluez.Error.InProgress`, BlueZ already has a
pairing or connection attempt for that remote. Wait for it to finish before
trying again; do not keep pressing Pair or remove existing Bluetooth devices.
In v0.4.9 the relay reports this as busy and leaves the existing attempt alone.
The Web UI device list shows whether the Pi has subsequently paired it.

If it is still unpaired, put the remote back in pairing mode, scan again, and
select Pair once. Record the operation-specific error and Xiaomi model code
if it remains busy. A successful bond does not enable Bluetooth button input.

## Hardware evidence needed before implementation

1. Read the Xiaomi model code under the battery cover (often an XMRM code).
2. Inspect the Pi's Bluetooth adapter and Home Assistant OS capabilities without
   changing existing Bluetooth devices or pairing the remote away from its TV.
3. On the agreed test host, pair the remote and record whether Linux exposes
   standard HID input events or a model-specific BLE service. Verify button
   codes for directions, Select, Back, Home, and Power. Some models may send
   Power through infrared rather than Bluetooth.
4. Choose the smallest supported input bridge. Confirm Home Assistant OS can
   expose the required input to an add-on before adding runtime dependencies or
   hardware permissions. Keep Bluetooth input optional and disabled by default.
5. Forward an explicit device allow-list through the existing Apple TV command
   queue. Drop key releases/repeats as appropriate to prevent duplicate actions.
6. Test reconnect after sleep, add-on restart, OS restart, multiple remotes,
   revocation, and coexistence with phone remotes. Keep pairing data protected.

Do not advertise Xiaomi remote compatibility until real button capture and
Apple TV forwarding have passed on the user's hardware. Voice, vendor app
shortcuts, and infrared are outside this first proof of concept.

Reference: [Xiaomi Bluetooth remote pairing](https://www.mi.com/global/support/faq/details/KA-06361/).
