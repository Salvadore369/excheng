import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const strategies = [
  { id: "trend", title: "EMA Trend Pullback", detail: "15m / 1h · long / short" },
  { id: "sp2l", title: "SP2L", detail: "1m / 5m · limit ladder" },
  { id: "grid", title: "Grid Strategy", detail: "15m / 4h · bounded grid" },
];

export default function BacktestScreen() {
  const colors = useColors();
  const [selected, setSelected] = useState("sp2l");
  const [ran, setRan] = useState(false);

  const runBacktest = async () => {
    if (process.env.EXPO_OS !== "web") await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setRan(true);
  };

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View>
          <Text style={[styles.eyebrow, { color: colors.muted }]}>RESEARCH LAB</Text>
          <Text style={[styles.title, { color: colors.foreground }]}>بک‌تست</Text>
          <Text style={[styles.subtitle, { color: colors.muted }]}>قبل از هر تصمیم، استراتژی را روی داده تاریخی بسنجید.</Text>
        </View>

        <View style={styles.stepHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>۱. انتخاب استراتژی</Text>
          <Text style={[styles.stepMeta, { color: colors.muted }]}>یکی را انتخاب کنید</Text>
        </View>
        <View style={styles.strategyList}>
          {strategies.map((strategy) => {
            const active = selected === strategy.id;
            return (
              <Pressable
                key={strategy.id}
                onPress={() => setSelected(strategy.id)}
                style={({ pressed }) => [styles.strategyRow, { backgroundColor: active ? "#182A27" : colors.surface, borderColor: active ? "#5CE1B8" : colors.border }, pressed && styles.pressed]}
              >
                <View style={[styles.radio, { borderColor: active ? "#5CE1B8" : colors.border }]}>
                  {active && <View style={styles.radioInner} />}
                </View>
                <View style={styles.strategyCopy}>
                  <Text style={[styles.strategyTitle, { color: colors.foreground }]}>{strategy.title}</Text>
                  <Text style={[styles.strategyDetail, { color: colors.muted }]}>{strategy.detail}</Text>
                </View>
                <IconSymbol name="chevron.right" size={18} color={colors.muted} />
              </Pressable>
            );
          })}
        </View>

        <View style={styles.stepHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>۲. تنظیمات آزمایش</Text>
          <Text style={[styles.stepMeta, { color: colors.muted }]}>محلی روی دستگاه</Text>
        </View>
        <View style={[styles.settingsCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.settingRow}><Text style={[styles.settingName, { color: colors.muted }]}>نماد</Text><Text style={[styles.settingValue, { color: colors.foreground }]}>BTCUSDT</Text></View>
          <View style={styles.settingRow}><Text style={[styles.settingName, { color: colors.muted }]}>بازه داده</Text><Text style={[styles.settingValue, { color: colors.foreground }]}>داده‌ای انتخاب نشده</Text></View>
          <View style={styles.settingRow}><Text style={[styles.settingName, { color: colors.muted }]}>ریسک هر معامله</Text><Text style={[styles.settingValue, { color: "#5CE1B8" }]}>۰.۵٪</Text></View>
          <View style={[styles.settingRow, { borderBottomWidth: 0 }]}><Text style={[styles.settingName, { color: colors.muted }]}>کارمزد / لغزش</Text><Text style={[styles.settingValue, { color: colors.foreground }]}>پیش‌فرض پروژه</Text></View>
        </View>

        {ran && (
          <View style={[styles.resultCard, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
            <IconSymbol name="checkmark.seal.fill" size={22} color="#5CE1B8" />
            <View style={{ flex: 1 }}>
              <Text style={[styles.resultTitle, { color: "#D8F4EA" }]}>آماده اجرای بک‌تست</Text>
              <Text style={[styles.resultText, { color: "#A9C0BA" }]}>برای نتیجه واقعی، داده تاریخی را از کلاینت اصلی یا API داده وارد کنید. عدد ساختگی نمایش داده نمی‌شود.</Text>
            </View>
          </View>
        )}

        <Pressable onPress={runBacktest} style={({ pressed }) => [styles.runButton, pressed && styles.pressed]}>
          <IconSymbol name="play.fill" size={18} color="#0B1513" />
          <Text style={styles.runText}>{ran ? "آماده بررسی داده" : "آماده‌سازی بک‌تست"}</Text>
        </Pressable>
        <Text style={[styles.disclaimer, { color: colors.muted }]}>نتایج بک‌تست گذشته تضمین‌کننده عملکرد آینده نیستند.</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 15 },
  eyebrow: { fontSize: 11, letterSpacing: 1.8, fontWeight: "700" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  subtitle: { fontSize: 12, lineHeight: 19, marginTop: 7, maxWidth: 320 },
  stepHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 6 },
  sectionTitle: { fontSize: 16, fontWeight: "800" },
  stepMeta: { fontSize: 10 },
  strategyList: { gap: 8 },
  strategyRow: { borderWidth: 1, borderRadius: 17, padding: 14, flexDirection: "row", alignItems: "center" },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  radioInner: { width: 10, height: 10, borderRadius: 5, backgroundColor: "#5CE1B8" },
  strategyCopy: { flex: 1, marginHorizontal: 11 },
  strategyTitle: { fontSize: 13, fontWeight: "800" },
  strategyDetail: { fontSize: 10, marginTop: 4 },
  settingsCard: { borderRadius: 18, borderWidth: 1, paddingHorizontal: 15 },
  settingRow: { minHeight: 47, borderBottomWidth: 1, borderBottomColor: "#29413B", flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  settingName: { fontSize: 11 },
  settingValue: { fontSize: 12, fontWeight: "700" },
  resultCard: { borderRadius: 17, borderWidth: 1, padding: 15, flexDirection: "row", gap: 11, alignItems: "flex-start" },
  resultTitle: { fontSize: 13, fontWeight: "800" },
  resultText: { fontSize: 10, lineHeight: 17, marginTop: 5 },
  runButton: { backgroundColor: "#5CE1B8", borderRadius: 16, minHeight: 54, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 9, marginTop: 4 },
  runText: { color: "#0B1513", fontSize: 14, fontWeight: "800" },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
  disclaimer: { fontSize: 10, textAlign: "center", lineHeight: 16 },
});
