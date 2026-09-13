import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { ComponentProps } from "react";
import { OpaqueColorValue, type StyleProp, type TextStyle } from "react-native";

type MaterialIconName = ComponentProps<typeof MaterialIcons>["name"];
export type IconSymbolName =
  | "house.fill" | "chart.bar.fill" | "clock.arrow.circlepath" | "gearshape.fill"
  | "shield.fill" | "arrow.triangle.2.circlepath" | "exclamationmark.triangle.fill"
  | "waveform.path.ecg" | "star.fill" | "star" | "info.circle.fill" | "chevron.right"
  | "checkmark.seal.fill" | "play.fill" | "lock.shield.fill" | "checkmark.shield.fill"
  | "bell.fill" | "bolt.fill";

const MAPPING: Record<IconSymbolName, MaterialIconName> = {
  "house.fill": "home",
  "chart.bar.fill": "bar-chart",
  "clock.arrow.circlepath": "history",
  "gearshape.fill": "settings",
  "shield.fill": "security",
  "arrow.triangle.2.circlepath": "sync",
  "exclamationmark.triangle.fill": "warning",
  "waveform.path.ecg": "show-chart",
  "star.fill": "star",
  star: "star-border",
  "info.circle.fill": "info",
  "chevron.right": "chevron-right",
  "checkmark.seal.fill": "verified",
  "play.fill": "play-arrow",
  "lock.shield.fill": "gpp-good",
  "checkmark.shield.fill": "verified-user",
  "bell.fill": "notifications",
  "bolt.fill": "bolt",
};

export function IconSymbol({ name, size = 24, color, style }: { name: IconSymbolName; size?: number; color: string | OpaqueColorValue; style?: StyleProp<TextStyle>; weight?: string }) {
  return <MaterialIcons color={color} size={size} name={MAPPING[name]} style={style} />;
}
