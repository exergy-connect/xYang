import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { parseYangFile, parseYangString, YangModule } from "../src";

const IETF_ALARMS = join(
  __dirname,
  "../../examples/ietf-yang-push/modules/ietf-alarms@2019-09-11.yang"
);

function findListAlarm(mod: YangModule) {
  const alarms = mod.findStatement("alarms");
  expect(alarms).toBeDefined();
  const alarmList = alarms?.statements.find((s) => s.name === "alarm-list");
  expect(alarmList).toBeDefined();
  const alarm = alarmList?.statements.find((s) => s.keyword === "list" && s.name === "alarm");
  expect(alarm).toBeDefined();
  return alarm!;
}

describe("notification under list (RFC 7950 YANG 1.1)", () => {
  it("parses notification under list", () => {
    const mod = parseYangString(`
module m {
  yang-version 1.1;
  namespace "urn:example:m";
  prefix m;
  grouping g { leaf x { type string; } }
  list alarm {
    key "id";
    leaf id { type string; }
    notification operator-action { uses g; }
  }
}
`);
    const alarm = mod.findStatement("alarm");
    const notif = alarm?.statements.find((s) => s.keyword === "notification" && s.name === "operator-action");
    expect(notif?.name).toBe("operator-action");
  });

  it("parses ietf-alarms operator-action notification without skip warning", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const mod = parseYangFile(IETF_ALARMS);
      const alarm = findListAlarm(mod);
      const notif = alarm.statements.find((s) => s.keyword === "notification" && s.name === "operator-action");
      expect(notif?.name).toBe("operator-action");
      const notifWarnings = warnSpy.mock.calls
        .map((c) => String(c[0]))
        .filter((m) => m.includes("notification") && m.includes("alarm"));
      expect(notifWarnings).toEqual([]);
    } finally {
      warnSpy.mockRestore();
    }
  });
});
