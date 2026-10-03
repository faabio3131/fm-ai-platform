import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const manifestPath = resolve(root, ".github/security/web-dev-audit-exceptions.json");
const webDir = resolve(root, "web");
const evidenceDir = resolve(root, "evidence");
const evidencePath = resolve(evidenceDir, "web-dependency-security.json");

function runNpm(args) {
  const result = spawnSync("npm", args, {
    cwd: webDir,
    encoding: "utf8",
    env: { ...process.env, NO_COLOR: "1" },
  });
  return {
    status: result.status ?? 1,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? "",
  };
}

function parseJsonOutput(result, label) {
  try {
    return JSON.parse(result.stdout || "{}");
  } catch (error) {
    throw new Error(label + ": npm did not return valid JSON. stderr=" + result.stderr.slice(0, 1000));
  }
}

function severityRank(value) {
  return { low: 1, moderate: 2, high: 3, critical: 4 }[String(value || "").toLowerCase()] || 0;
}

function advisoryIdFromUrl(url) {
  const match = String(url || "").match(/GHSA-[0-9A-Za-z-]+/i);
  return match ? match[0].toUpperCase() : null;
}

function collectRootAdvisories(name, vulnerabilities, seen = new Set()) {
  if (seen.has(name)) return [];
  seen.add(name);
  const entry = vulnerabilities[name];
  if (!entry) return [];
  const roots = [];
  for (const via of entry.via || []) {
    if (typeof via === "string") {
      roots.push(...collectRootAdvisories(via, vulnerabilities, new Set(seen)));
    } else if (via && typeof via === "object") {
      roots.push({
        package: via.name || name,
        advisory_id: advisoryIdFromUrl(via.url),
        severity: String(via.severity || entry.severity || "").toLowerCase(),
        title: via.title || "",
        url: via.url || "",
      });
    }
  }
  return roots;
}

function containsDependency(node, target, seen = new Set()) {
  if (!node || typeof node !== "object" || seen.has(node)) return false;
  seen.add(node);
  const deps = node.dependencies || {};
  if (Object.prototype.hasOwnProperty.call(deps, target)) return true;
  return Object.values(deps).some((child) => containsDependency(child, target, seen));
}

const policy = JSON.parse(readFileSync(manifestPath, "utf8"));
const exceptions = policy.exceptions || [];
const today = new Date().toISOString().slice(0, 10);

for (const exception of exceptions) {
  if (!exception.review_deadline || today > exception.review_deadline) {
    throw new Error(
      "Security exception " + exception.id + " expired on " +
      (exception.review_deadline || "unknown") + "; re-evaluation is mandatory."
    );
  }
  if (exception.scope !== "development-only") {
    throw new Error("Security exception " + exception.id + " is not development-only.");
  }
}

const runtimeAuditResult = runNpm(["audit", "--omit=dev", "--audit-level=high", "--json"]);
const runtimeAudit = parseJsonOutput(runtimeAuditResult, "runtime audit");
const runtimeCounts = runtimeAudit.metadata?.vulnerabilities || {};
if ((runtimeCounts.high || 0) > 0 || (runtimeCounts.critical || 0) > 0 || runtimeAuditResult.status !== 0) {
  throw new Error(
    "Production dependency audit failed: high=" + (runtimeCounts.high || 0) +
    ", critical=" + (runtimeCounts.critical || 0) + "."
  );
}

const runtimeTreeResult = runNpm(["ls", "--omit=dev", "--all", "--json"]);
const runtimeTree = parseJsonOutput(runtimeTreeResult, "runtime dependency tree");
for (const exception of exceptions) {
  if (containsDependency(runtimeTree, exception.package)) {
    throw new Error(
      "Allowlisted development package " + exception.package +
      " is present in the production dependency tree."
    );
  }
}

const fullAuditResult = runNpm(["audit", "--json"]);
const fullAudit = parseJsonOutput(fullAuditResult, "full audit");
const vulnerabilities = fullAudit.vulnerabilities || {};
const highOrCritical = Object.entries(vulnerabilities).filter(([, entry]) =>
  severityRank(entry.severity) >= severityRank("high")
);

const accepted = [];
const rejected = [];

for (const [name, entry] of highOrCritical) {
  const roots = collectRootAdvisories(name, vulnerabilities);
  if (roots.length === 0) {
    rejected.push({ name, reason: "no root advisory could be resolved" });
    continue;
  }

  const unmatched = roots.filter((rootAdvisory) => {
    return !exceptions.some((exception) =>
      exception.package === rootAdvisory.package &&
      exception.advisory_id.toUpperCase() === String(rootAdvisory.advisory_id || "").toUpperCase() &&
      severityRank(rootAdvisory.severity) <= severityRank(exception.severity)
    );
  });

  if (unmatched.length > 0) {
    rejected.push({ name, unmatched });
  } else {
    accepted.push({
      name,
      severity: entry.severity,
      roots: roots.map((rootAdvisory) => ({
        package: rootAdvisory.package,
        advisory_id: rootAdvisory.advisory_id,
        severity: rootAdvisory.severity,
      })),
    });
  }
}

if (rejected.length > 0) {
  throw new Error(
    "Unapproved HIGH/CRITICAL development vulnerabilities detected: " +
    JSON.stringify(rejected)
  );
}

for (const exception of exceptions) {
  const stillObserved = accepted.some((item) =>
    item.roots.some((rootAdvisory) =>
      rootAdvisory.package === exception.package &&
      rootAdvisory.advisory_id === exception.advisory_id
    )
  );
  if (!stillObserved) {
    throw new Error(
      "Security exception " + exception.id +
      " is stale because its advisory is no longer present; remove the exception."
    );
  }
}

mkdirSync(evidenceDir, { recursive: true });
const evidence = {
  gate: "KORDENA_WEB_DEPENDENCY_SECURITY",
  generated_at: new Date().toISOString(),
  production: {
    audit_high: runtimeCounts.high || 0,
    audit_critical: runtimeCounts.critical || 0,
    allowlisted_packages_present: false,
    status: "PASS",
  },
  development: {
    high_or_critical_count: highOrCritical.length,
    accepted_exceptions: accepted,
    rejected_count: rejected.length,
    status: rejected.length === 0 ? "PASS_WITH_BOUNDED_EXCEPTION" : "FAIL",
  },
  exception_policy: exceptions.map((exception) => ({
    id: exception.id,
    advisory_id: exception.advisory_id,
    package: exception.package,
    review_deadline: exception.review_deadline,
  })),
};
writeFileSync(evidencePath, JSON.stringify(evidence, null, 2) + "\n");

console.log("Production dependency audit: PASS (0 HIGH, 0 CRITICAL)");
console.log("Production tree isolation: PASS (allowlisted dev package absent)");
console.log(
  "Development audit: PASS_WITH_BOUNDED_EXCEPTION (" + accepted.length +
  " affected dependency nodes; exact advisory allowlist only)"
);
console.log("Evidence: " + evidencePath);
