import { describe, expect, it } from "vitest";
import { checkConfig } from "../src/config.ts";

type Env = Record<string, string | undefined>;

const SECRETS: Env = {
  GULGRIR_SECRET_KEY: "k".repeat(64),
  GULGRIR_DB_PASSWORD: "db-password",
};

const run = (env: Env = {}) => checkConfig({ ...SECRETS, ...env });

const COLUMNS = ["SETTING", "DEFAULT", "OVERRIDE", "IN EFFECT", "NOTE"] as const;
type Column = (typeof COLUMNS)[number];

const SETTINGS = [
  "GULGRIR_SECRET_KEY",
  "GULGRIR_DB_PASSWORD",
  "GULGRIR_DB_USER",
  "GULGRIR_DB_NAME",
  "GULGRIR_DB_HOST",
  "GULGRIR_DB_PORT",
  "GULGRIR_DEBUG",
  "GULGRIR_ENV",
  "GULGRIR_ALLOWED_HOSTS",
  "GULGRIR_CSRF_TRUSTED_ORIGINS",
  "GULGRIR_BEHIND_HTTPS_PROXY",
  "GULGRIR_ADMIN_USER",
  "GULGRIR_ADMIN_PASSWORD",
  "GULGRIR_PORT",
  "GULGRIR_VERSION",
];

// [new name, old name, a value, another value]
const RENAMED = [
  ["GULGRIR_SECRET_KEY", "DJANGO_SECRET_KEY", "a".repeat(64), "b".repeat(64)],
  ["GULGRIR_DB_PASSWORD", "POSTGRES_PASSWORD", "pw-new", "pw-old"],
  ["GULGRIR_DB_USER", "POSTGRES_USER", "user-new", "user-old"],
  ["GULGRIR_DB_NAME", "POSTGRES_DB", "name-new", "name-old"],
  ["GULGRIR_DB_HOST", "POSTGRES_HOST", "host-new", "host-old"],
  ["GULGRIR_DB_PORT", "POSTGRES_PORT", "6543", "7654"],
  ["GULGRIR_DEBUG", "DJANGO_DEBUG", "false", "true"],
  ["GULGRIR_ALLOWED_HOSTS", "DJANGO_ALLOWED_HOSTS", "new.example", "old.example"],
  [
    "GULGRIR_CSRF_TRUSTED_ORIGINS",
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "https://new.example",
    "https://old.example",
  ],
  ["GULGRIR_BEHIND_HTTPS_PROXY", "DJANGO_SECURE_PROXY_SSL_HEADER", "false", "true"],
  ["GULGRIR_ADMIN_USER", "DJANGO_ADMIN_USER", "admin-new", "admin-old"],
  ["GULGRIR_ADMIN_PASSWORD", "DJANGO_ADMIN_PASS", "apw-new", "apw-old"],
] as const;

function headerIndex(report: string[]): number {
  const index = report.findIndex((line) => line.startsWith("SETTING"));
  expect(index, "report has a header line").toBeGreaterThanOrEqual(0);
  return index;
}

// Cells are read by the header's column positions, so empty cells survive.
function cell(report: string[], setting: string, column: Column): string {
  const start = headerIndex(report);
  const header = report[start]!;
  const line = report.slice(start + 1).find((l) => l.split(/\s+/)[0] === setting);
  expect(line, `report has a row for ${setting}`).toBeDefined();
  const k = COLUMNS.indexOf(column);
  const from = header.indexOf(column);
  const to = k + 1 < COLUMNS.length ? header.indexOf(COLUMNS[k + 1]!) : undefined;
  return line!.slice(from, to).trim();
}

describe("defaults (CFG-V7)", () => {
  it("starts with only the required secrets set, every other setting at its default", () => {
    const { ok, report, djangoEnv } = run();

    expect(ok).toBe(true);
    const defaults = {
      GULGRIR_DB_USER: "gulgrir",
      GULGRIR_DB_NAME: "gulgrir",
      GULGRIR_DB_HOST: "db",
      GULGRIR_DB_PORT: "5432",
      GULGRIR_DEBUG: "false",
      GULGRIR_ENV: "dev",
      GULGRIR_BEHIND_HTTPS_PROXY: "false",
      GULGRIR_PORT: "8765",
    };
    for (const [setting, value] of Object.entries(defaults)) {
      expect(cell(report, setting, "DEFAULT"), setting).toBe(value);
      expect(cell(report, setting, "OVERRIDE"), setting).toBe("");
      expect(cell(report, setting, "IN EFFECT"), setting).toBe(value);
    }
    expect(djangoEnv).toMatchObject({
      GULGRIR_DB_USER: "gulgrir",
      GULGRIR_DB_NAME: "gulgrir",
      GULGRIR_DB_HOST: "db",
      GULGRIR_DB_PORT: "5432",
      GULGRIR_DEBUG: "false",
      GULGRIR_ENV: "dev",
      GULGRIR_BEHIND_HTTPS_PROXY: "false",
    });
  });

  it("has no default admin credentials, and their absence does not stop start-up", () => {
    const { ok, report, djangoEnv } = run();

    expect(ok).toBe(true);
    expect(cell(report, "GULGRIR_ADMIN_USER", "DEFAULT")).toBe("(none)");
    expect(cell(report, "GULGRIR_ADMIN_USER", "OVERRIDE")).toBe("");
    expect(cell(report, "GULGRIR_ADMIN_PASSWORD", "DEFAULT")).toBe("(none)");
    expect(cell(report, "GULGRIR_ADMIN_PASSWORD", "OVERRIDE")).toBe("(missing)");
    expect(djangoEnv.GULGRIR_ADMIN_USER).toBeUndefined();
    expect(djangoEnv.GULGRIR_ADMIN_PASSWORD).toBeUndefined();
  });
});

describe("renamed settings (CFG-V3)", () => {
  it.each(RENAMED)(
    "%s still works under its old name %s, and the note names both",
    (name, old, value) => {
      const { ok, report, djangoEnv } = run({ [name]: undefined, [old]: value });

      expect(ok).toBe(true);
      expect(djangoEnv[name]).toBe(value);
      const note = cell(report, name, "NOTE");
      expect(note).toContain(old);
      expect(note).toContain(name);
    },
  );

  it.each(RENAMED)(
    "%s wins over %s when both are set, and the note names the old one",
    (name, old, value, other) => {
      const { ok, report, djangoEnv } = run({ [name]: value, [old]: other });

      expect(ok).toBe(true);
      expect(djangoEnv[name]).toBe(value);
      const note = cell(report, name, "NOTE");
      expect(note).toContain(old);
    },
  );

  it("falls back to the old name when the new one is empty", () => {
    const old = "c".repeat(64);
    const { ok, report, djangoEnv } = run({ GULGRIR_SECRET_KEY: "", DJANGO_SECRET_KEY: old });

    expect(ok).toBe(true);
    expect(djangoEnv.GULGRIR_SECRET_KEY).toBe(old);
    expect(cell(report, "GULGRIR_SECRET_KEY", "NOTE")).toContain("DJANGO_SECRET_KEY");
  });
});

describe("values handed to Django (CFG-V4)", () => {
  it("passes settings without fixed meanings exactly as written", () => {
    const written = {
      GULGRIR_SECRET_KEY: `a$b#c'd"e\\f ${"x".repeat(50)}`,
      GULGRIR_DB_PASSWORD: "p@ss w$rd#",
      GULGRIR_DB_USER: "Mixed Case",
      GULGRIR_DB_NAME: "name-with-dash",
      GULGRIR_DB_HOST: "db.internal",
      GULGRIR_DB_PORT: "6543",
      GULGRIR_ALLOWED_HOSTS: " a.example , b.example ",
      GULGRIR_CSRF_TRUSTED_ORIGINS: "https://a.example:8443,http://b.example",
      GULGRIR_ADMIN_USER: "Root",
      GULGRIR_ADMIN_PASSWORD: "  spaced  ",
    };

    const { djangoEnv } = run(written);

    expect(djangoEnv).toMatchObject({
      GULGRIR_SECRET_KEY: written.GULGRIR_SECRET_KEY,
      GULGRIR_DB_PASSWORD: written.GULGRIR_DB_PASSWORD,
      GULGRIR_DB_USER: written.GULGRIR_DB_USER,
      GULGRIR_DB_NAME: written.GULGRIR_DB_NAME,
      GULGRIR_DB_HOST: written.GULGRIR_DB_HOST,
      GULGRIR_DB_PORT: written.GULGRIR_DB_PORT,
      GULGRIR_ALLOWED_HOSTS: written.GULGRIR_ALLOWED_HOSTS,
      GULGRIR_CSRF_TRUSTED_ORIGINS: written.GULGRIR_CSRF_TRUSTED_ORIGINS,
      GULGRIR_ADMIN_USER: written.GULGRIR_ADMIN_USER,
      GULGRIR_ADMIN_PASSWORD: written.GULGRIR_ADMIN_PASSWORD,
    });
  });

  // [written, reading, noted]
  const FLAGS = [
    ["true", "true", false],
    ["TRUE", "true", false],
    ["True", "true", false],
    ["false", "false", false],
    ["yes", "false", true],
    ["1", "false", true],
    [" true", "false", true],
  ] as const;

  describe.each(["GULGRIR_DEBUG", "GULGRIR_BEHIND_HTTPS_PROXY"])("%s", (setting) => {
    it.each(FLAGS)("reads %j as %s", (written, reading, noted) => {
      const { ok, report, djangoEnv } = run({ [setting]: written });

      expect(ok).toBe(true);
      expect(djangoEnv[setting]).toBe(reading);
      expect(cell(report, setting, "IN EFFECT")).toBe(reading);
      const note = cell(report, setting, "NOTE");
      if (noted) {
        expect(note).toContain(written.trim());
        expect(note).toContain(reading);
      } else {
        expect(note).toBe("");
      }
    });
  });

  it.each([
    ["prod", "production", false],
    ["production", "production", false],
    ["live", "production", false],
    ["staging", "staging", false],
    ["stage", "staging", false],
    ["preprod", "staging", false],
    ["qa", "staging", false],
    ["dev", "dev", false],
    ["prd", "dev", true],
    ["test", "dev", true],
  ] as const)("reads GULGRIR_ENV %j as %s", (written, reading, noted) => {
    const { ok, report, djangoEnv } = run({ GULGRIR_ENV: written });

    expect(ok).toBe(true);
    expect(djangoEnv.GULGRIR_ENV).toBe(reading);
    expect(cell(report, "GULGRIR_ENV", "IN EFFECT")).toBe(reading);
    const note = cell(report, "GULGRIR_ENV", "NOTE");
    if (noted) {
      expect(note).toContain(written);
      expect(note).toContain(reading);
    } else {
      expect(note).toBe("");
    }
  });

  it.each([
    ["PROD", "production"],
    [" Live ", "production"],
  ])("reads GULGRIR_ENV %j as %s, as Django does", (written, reading) => {
    expect(run({ GULGRIR_ENV: written }).djangoEnv.GULGRIR_ENV).toBe(reading);
  });
});

describe("what stops start-up (CFG-V9)", () => {
  it.each([
    ["GULGRIR_SECRET_KEY", undefined],
    ["GULGRIR_SECRET_KEY", ""],
    ["GULGRIR_DB_PASSWORD", undefined],
    ["GULGRIR_DB_PASSWORD", ""],
  ])("a missing %s (%j) stops start-up, naming it and how to generate one", (setting, value) => {
    const { ok, report } = run({ [setting]: value });

    expect(ok).toBe(false);
    headerIndex(report);
    const last = report.at(-1)!;
    expect(last).toContain(setting);
    expect(last).toContain("secrets.token_urlsafe");
  });

  it("names every variable at fault on the last line", () => {
    const { ok, report } = checkConfig({ GULGRIR_DB_PORT: "abc" });

    expect(ok).toBe(false);
    const last = report.at(-1)!;
    expect(last).toContain("GULGRIR_SECRET_KEY");
    expect(last).toContain("GULGRIR_DB_PASSWORD");
    expect(last).toContain("GULGRIR_DB_PORT");
  });

  it.each(["abc", "0", "65536", "5432.5", "-1", " "])(
    "GULGRIR_DB_PORT %j stops start-up",
    (port) => {
      const { ok, report } = run({ GULGRIR_DB_PORT: port });

      expect(ok).toBe(false);
      expect(report.at(-1)).toContain("GULGRIR_DB_PORT");
    },
  );

  it.each(["1", "5432", "65535"])("GULGRIR_DB_PORT %j is accepted", (port) => {
    expect(run({ GULGRIR_DB_PORT: port }).ok).toBe(true);
  });
});

describe("unknown variables (CFG-V3)", () => {
  it("flags a misspelled setting and names the one it is close to, without its value", () => {
    const { ok, report } = run({ GULGRIR_DEBGU: "value-of-typo" });

    expect(ok).toBe(true);
    const text = report.join("\n");
    const line = report.find((l) => l.includes("GULGRIR_DEBGU"));
    expect(line).toBeDefined();
    expect(line).toContain("GULGRIR_DEBUG");
    expect(text).not.toContain("value-of-typo");
  });

  it("names the closest setting when several are a letter or two away", () => {
    const { report } = run({ GULGRIR_DPORT: "1" });

    const line = report.find((l) => l.includes("GULGRIR_DPORT"));
    expect(line).toContain("GULGRIR_PORT");
    expect(line).not.toContain("GULGRIR_DB_PORT");
  });

  it("flags an unknown setting with no suggestion when none is close", () => {
    const { ok, report } = run({ GULGRIR_FOO: "value-of-unknown" });

    expect(ok).toBe(true);
    const line = report.find((l) => l.includes("GULGRIR_FOO"));
    expect(line).toBeDefined();
    expect(line!.replace("GULGRIR_FOO", "")).not.toMatch(/GULGRIR_/);
    expect(report.join("\n")).not.toContain("value-of-unknown");
  });

  it("ignores variables outside GULGRIR_*", () => {
    const { ok, report } = run({ PATH: "/usr/bin", HOME: "/root", BACKUP_SCHEDULE: "0 5 * * *" });

    expect(ok).toBe(true);
    expect(report.join("\n")).not.toMatch(/PATH|HOME|BACKUP_SCHEDULE/);
  });
});

describe("secrets (CFG-V10)", () => {
  const MARKER = "s3cr3t-MARKER-value";

  it("never shows a secret's value, under any name", () => {
    const { ok, report } = checkConfig({
      GULGRIR_SECRET_KEY: `${MARKER}${"k".repeat(50)}`,
      DJANGO_SECRET_KEY: `${MARKER}old`,
      GULGRIR_DB_PASSWORD: MARKER,
      POSTGRES_PASSWORD: `${MARKER}old`,
      GULGRIR_ADMIN_PASSWORD: MARKER,
      DJANGO_ADMIN_PASS: `${MARKER}old`,
      GULGRIR_SECRT_KEY: `${MARKER}typo`,
    });

    expect(ok).toBe(true);
    expect(report.join("\n")).not.toContain(MARKER);
    for (const setting of ["GULGRIR_SECRET_KEY", "GULGRIR_DB_PASSWORD", "GULGRIR_ADMIN_PASSWORD"]) {
      expect(cell(report, setting, "DEFAULT"), setting).toBe("(none)");
      expect(cell(report, setting, "OVERRIDE"), setting).toBe("(set)");
      expect(cell(report, setting, "IN EFFECT"), setting).toBe("(redacted)");
    }
  });

  it("never shows a secret's value when start-up stops", () => {
    const { ok, report } = checkConfig({ GULGRIR_DB_PASSWORD: MARKER, GULGRIR_DB_PORT: "abc" });

    expect(ok).toBe(false);
    expect(report.join("\n")).not.toContain(MARKER);
    expect(cell(report, "GULGRIR_SECRET_KEY", "OVERRIDE")).toBe("(missing)");
  });
});

describe("report layout (CFG-V8)", () => {
  it("has the five columns and one row per setting, in the order of the settings list", () => {
    const { report } = run();

    const start = headerIndex(report);
    expect(report[start]!.trim().split(/\s{2,}/)).toEqual([...COLUMNS]);
    const rows = report
      .slice(start + 1)
      .map((line) => line.split(/\s+/)[0])
      .filter((first) => SETTINGS.includes(first!));
    expect(rows).toEqual(SETTINGS);
  });
});
