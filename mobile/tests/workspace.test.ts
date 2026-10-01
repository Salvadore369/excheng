import { describe, expect, it } from "vitest";
import { createWorkspaceProject, PROJECT_TEMPLATES } from "../lib/workspace";

describe("MTFlow local workspace", () => {
  it("creates a project from the selected safe template", () => {
    const project = createWorkspaceProject("  EURUSD EA  ", "EA");

    expect(project.name).toBe("EURUSD EA");
    expect(project.kind).toBe("EA");
    expect(project.code).toContain("initialized in safe mode");
    expect(project.code).not.toContain("OrderSend(");
  });

  it("provides MQL5 indicator and Python research starters", () => {
    expect(PROJECT_TEMPLATES.Indicator.code).toContain("OnCalculate");
    expect(PROJECT_TEMPLATES.Python.code).toContain("csv.DictReader");
    expect(PROJECT_TEMPLATES.Python.code).not.toContain("requests.post");
  });
});
