import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("F14 operations UI", () => {
  it("não apresenta uptime artificial e usa a autoridade operacional governada", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/app/dashboard/operations/page.tsx"),
      "utf8",
    );
    expect(source).toContain("Health pontual não é uptime");
    expect(source).toContain("Disponibilidade só aparece");
    expect(source).toContain("OperationalHealthService");
    expect(source).toContain("PostgresOperationalHealthRepository");
    expect(source).toContain("Status dos Serviços");
    expect(source).toContain("Saúde técnica da plataforma");
    expect(source).toContain("Diagnósticos de infraestrutura pertencem ao FM Command");
    expect(source).toContain("Health contract");
    expect(source).toContain("Readiness contract");
    expect(source).toContain("Escopo governado por organização e papel");
    expect(source).toContain("Stale é tratado como desconhecido");
    expect(source).toContain("Nenhum serviço monitorado.");
    expect(source).not.toContain("99.9%");
    expect(source).not.toContain("Math.random");
  });
});
