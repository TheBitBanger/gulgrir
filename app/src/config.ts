// Settings, their defaults and readings: docs/operations/configuration.md.
export type Env = Record<string, string | undefined>;

type Kind = "text" | "flag" | "env" | "port";

interface Setting {
  name: string;
  old?: string;
  default?: string;
  secret?: boolean;
  required?: boolean;
  kind?: Kind;
}

const SETTINGS: Setting[] = [
  { name: "GULGRIR_SECRET_KEY", old: "DJANGO_SECRET_KEY", secret: true, required: true },
  { name: "GULGRIR_DB_PASSWORD", old: "POSTGRES_PASSWORD", secret: true, required: true },
  { name: "GULGRIR_DB_USER", old: "POSTGRES_USER", default: "gulgrir" },
  { name: "GULGRIR_DB_NAME", old: "POSTGRES_DB", default: "gulgrir" },
  { name: "GULGRIR_DB_HOST", old: "POSTGRES_HOST", default: "db" },
  { name: "GULGRIR_DB_PORT", old: "POSTGRES_PORT", default: "5432", kind: "port" },
  { name: "GULGRIR_DEBUG", old: "DJANGO_DEBUG", default: "false", kind: "flag" },
  { name: "GULGRIR_ENV", default: "dev", kind: "env" },
  { name: "GULGRIR_ALLOWED_HOSTS", old: "DJANGO_ALLOWED_HOSTS", default: "" },
  { name: "GULGRIR_CSRF_TRUSTED_ORIGINS", old: "DJANGO_CSRF_TRUSTED_ORIGINS", default: "" },
  {
    name: "GULGRIR_BEHIND_HTTPS_PROXY",
    old: "DJANGO_SECURE_PROXY_SSL_HEADER",
    default: "false",
    kind: "flag",
  },
  { name: "GULGRIR_ADMIN_USER", old: "DJANGO_ADMIN_USER" },
  { name: "GULGRIR_ADMIN_PASSWORD", old: "DJANGO_ADMIN_PASS", secret: true },
  { name: "GULGRIR_PORT", default: "8765" },
  { name: "GULGRIR_VERSION", default: "dev" },
];

const ENV_ALIASES: Record<string, string[]> = {
  production: ["prod", "production", "live"],
  staging: ["staging", "stage", "preprod", "qa"],
};

const COLUMNS = ["SETTING", "DEFAULT", "OVERRIDE", "IN EFFECT", "NOTE"];

const SECRET_COMMAND = `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`;

// The same readings as src/gulgrir/settings.py; a note when the written form isn't listed.
function read(kind: Kind, value: string): { reading: string; note?: string } {
  if (kind === "flag") {
    const lower = value.toLowerCase();
    const reading = lower === "true" ? "true" : "false";
    return lower === "true" || lower === "false"
      ? { reading }
      : { reading, note: `"${value}" read as ${reading}` };
  }
  if (kind === "env") {
    const raw = value.trim().toLowerCase();
    for (const [reading, aliases] of Object.entries(ENV_ALIASES)) {
      if (aliases.includes(raw)) return { reading };
    }
    return raw === "dev" ? { reading: "dev" } : { reading: "dev", note: `"${value}" read as dev` };
  }
  return { reading: value };
}

function isPort(value: string): boolean {
  return /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 65535;
}

// Levenshtein distance, to suggest the setting an unknown variable was meant to be.
function distance(a: string, b: string): number {
  let row = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const next = [i];
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      next[j] = Math.min((row[j] ?? 0) + 1, (next[j - 1] ?? 0) + 1, (row[j - 1] ?? 0) + cost);
    }
    row = next;
  }
  return row[b.length] ?? 0;
}

function table(rows: string[][]): string[] {
  const widths = COLUMNS.map((_, k) => Math.max(...rows.map((r) => r[k]?.length ?? 0)));
  return rows.map((r) =>
    r
      .map((c, k) => c.padEnd(widths[k] ?? 0))
      .join("  ")
      .trimEnd(),
  );
}

export function checkConfig(env: Env): {
  ok: boolean;
  report: string[];
  djangoEnv: Record<string, string>;
} {
  const given = (key: string | undefined) => (key && env[key]) || undefined;
  const rows = [COLUMNS];
  const faults: string[] = [];
  const djangoEnv: Record<string, string> = {};
  let secretMissing = false;

  for (const s of SETTINGS) {
    const fresh = given(s.name);
    const old = given(s.old);
    const override = fresh ?? old;
    const value = override ?? s.default;
    const notes: string[] = [];
    if (fresh && old) notes.push(`both names set; ${s.old} is ignored, delete it`);
    else if (old) notes.push(`${s.old} is deprecated; rename it to ${s.name}`);

    let reading = value;
    if (value !== undefined) {
      const result = read(s.kind ?? "text", value);
      reading = result.reading;
      if (override !== undefined && result.note) notes.push(result.note);
      djangoEnv[s.name] = reading;
    }
    if (s.kind === "port" && !isPort(value ?? "")) {
      faults.push(`${s.name} is not a whole number from 1 to 65535`);
      notes.push("not a port number");
    }
    if (s.required && override === undefined) {
      faults.push(`${s.name} is missing`);
      secretMissing = true;
    }

    rows.push(
      s.secret
        ? [s.name, "(none)", override ? "(set)" : "(missing)", "(redacted)", notes.join("; ")]
        : [s.name, s.default ?? "(none)", override ?? "", reading ?? "", notes.join("; ")],
    );
  }

  const report = table(rows);
  const known = SETTINGS.map((s) => s.name);
  for (const key of Object.keys(env)) {
    if (!key.startsWith("GULGRIR_") || env[key] === undefined || known.includes(key)) continue;
    const near = known
      .filter((name) => distance(key, name) <= 2)
      .sort((a, b) => distance(key, a) - distance(key, b))[0];
    report.push(
      `${key} is not a known setting and is ignored${near ? `; did you mean ${near}?` : ""}`,
    );
  }
  if (faults.length > 0) {
    const hint = secretMissing ? `. Generate a secret with: ${SECRET_COMMAND}` : "";
    report.push(`Start-up stopped: ${faults.join("; ")}${hint}`);
  }
  return { ok: faults.length === 0, report, djangoEnv };
}

// The entrypoint evaluates stdout as shell exports; the report goes to the log on stderr.
if (import.meta.main) {
  const { ok, report, djangoEnv } = checkConfig(process.env);
  console.error(report.join("\n"));
  if (!ok) process.exit(1);
  for (const [key, value] of Object.entries(djangoEnv)) {
    console.log(`export ${key}='${value.replaceAll("'", `'\\''`)}'`);
  }
}
