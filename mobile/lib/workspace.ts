import AsyncStorage from "@react-native-async-storage/async-storage";

export type ProjectKind = "EA" | "Indicator" | "Python";

export type WorkspaceProject = {
  id: string;
  name: string;
  kind: ProjectKind;
  updatedAt: string;
  code: string;
};

export const WORKSPACE_STORAGE_KEY = "mtflow-workspace-projects-v1";

export const PROJECT_TEMPLATES: Record<ProjectKind, { label: string; extension: string; description: string; code: string }> = {
  EA: {
    label: "Expert Advisor",
    extension: ".mq5",
    description: "اسکلت امن EA برای ثبت رویداد؛ بدون ارسال سفارش",
    code: `// MTFlow Expert Advisor template
#property version   "1.00"
#property description "Safe starter — logging only"

int OnInit()
  {
   Print("MTFlow EA initialized in safe mode");
   return(INIT_SUCCEEDED);
  }

void OnTick()
  {
   // Add reviewed signal logic here.
   // This starter intentionally sends no orders.
  }
`,
  },
  Indicator: {
    label: "Custom Indicator",
    extension: ".mq5",
    description: "قالب اندیکاتور سفارشی MQL5",
    code: `// MTFlow custom indicator template
#property indicator_chart_window
#property indicator_buffers 1
#property indicator_plots   1
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrMediumSeaGreen
#property indicator_label1  "MTFlow sample"

double SampleBuffer[];

int OnInit()
  {
   SetIndexBuffer(0, SampleBuffer, INDICATOR_DATA);
   return(INIT_SUCCEEDED);
  }

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   return(rates_total);
  }
`,
  },
  Python: {
    label: "Python research",
    extension: ".py",
    description: "قالب تحلیل پژوهشی محلی و فقط خواندنی",
    code: `"""MTFlow research starter — local analysis only."""
from pathlib import Path
import csv


def load_bars(path: str) -> list[dict[str, str]]:
    """Read an exported OHLC CSV without connecting to a broker."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    print("Import an OHLC CSV to begin local research.")
`,
  },
};

export async function loadWorkspaceProjects(): Promise<WorkspaceProject[]> {
  const raw = await AsyncStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isWorkspaceProject);
  } catch {
    return [];
  }
}

export async function saveWorkspaceProjects(projects: WorkspaceProject[]): Promise<void> {
  await AsyncStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(projects));
}

export function createWorkspaceProject(name: string, kind: ProjectKind): WorkspaceProject {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: name.trim(),
    kind,
    updatedAt: new Date().toISOString(),
    code: PROJECT_TEMPLATES[kind].code,
  };
}

function isWorkspaceProject(value: unknown): value is WorkspaceProject {
  if (!value || typeof value !== "object") return false;
  const project = value as Partial<WorkspaceProject>;
  return typeof project.id === "string"
    && typeof project.name === "string"
    && (project.kind === "EA" || project.kind === "Indicator" || project.kind === "Python")
    && typeof project.updatedAt === "string"
    && typeof project.code === "string";
}
