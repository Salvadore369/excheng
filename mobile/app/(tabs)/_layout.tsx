import { Tabs } from "expo-router";
import { Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { HapticTab } from "@/components/haptic-tab";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

export default function TabLayout() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const bottomPadding = Platform.OS === "web" ? 10 : Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: "#5CE1B8",
        tabBarInactiveTintColor: colors.muted,
        tabBarButton: HapticTab,
        tabBarStyle: {
          height: 62 + bottomPadding,
          paddingTop: 8,
          paddingBottom: bottomPadding,
          backgroundColor: colors.background,
          borderTopColor: colors.border,
          borderTopWidth: 0.5,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: "700" },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "خانه", tabBarIcon: ({ color }) => <IconSymbol name="house.fill" size={22} color={color} /> }} />
      <Tabs.Screen name="markets" options={{ title: "بازار", tabBarIcon: ({ color }) => <IconSymbol name="chart.bar.fill" size={22} color={color} /> }} />
      <Tabs.Screen name="backtest" options={{ title: "بک‌تست", tabBarIcon: ({ color }) => <IconSymbol name="clock.arrow.circlepath" size={22} color={color} /> }} />
      <Tabs.Screen name="settings" options={{ title: "تنظیمات", tabBarIcon: ({ color }) => <IconSymbol name="gearshape.fill" size={22} color={color} /> }} />
    </Tabs>
  );
}
