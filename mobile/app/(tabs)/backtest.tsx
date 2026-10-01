import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const ACCENT = "#5CE1B8";
const pipelines = [
  { id: "mt5", title: "MetaTrader 5 Strategy Tester", detail: "اجرای بک‌تست MQL5 روی ترمینال VPS" },
  { id: "python", title: "Python research", detail: "تحلیل داده تاریخی در محیط Python" },
  { id: "walk", title: "Walk-forward / Monte Carlo", detail: "اعتبارسنجی پس از راه‌اندازی موتور آزمایش" },
];

export default function BacktestScreen() {
  const colors = useColors();
  const [selected, setSelected] = useState("mt5");
  const [showRequirements, setShowRequirements] = useState(false);

  const inspectRequirements = async () => {
    if (process.env.EXPO_OS !== "web") await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    setShowRequirements(true);
  };

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View>
          <Text style={[styles.eyebrow, { color: colors.muted }]}>BUILD & RESEARCH</Text>
          <Text style={[styles.title, { color: colors.foreground }]}>آزمایش</Text>
          <Text style={[styles.subtitle, { color: colors.muted }]}>برای اجرای واقعی بک‌تست باید موتور، داده و ترمینال روی VPS پیکربندی شوند.</Text>
        </View>

        <View style={[styles.statusCard, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
          <View style={styles.statusIcon}><IconSymbol name="server.rack" size={21} color={ACCENT} /></View>
          <View style={{ flex: 1 }}><Text style={[styles.statusTitle, { color: "#D8F4EA" }]}>VPS متصل نیست</Text><Text style={[styles.statusText, { color: "#A9C0BA" }]}>هیچ بک‌تستی از این صفحه اجرا نشده است.</Text></View>
          <View style={styles.offlineDot} />
        </View>

        <View style={styles.stepHeader}><Text style={[styles.sectionTitle, { color: colors.foreground }]}>موتور آزمایش</Text><Text style={[styles.stepMeta, { color: colors.muted }]}>یکی را انتخاب کنید</Text></View>
        <View style={styles.pipelineList}>
          {pipelines.map((pipeline) => {
            const active = selected === pipeline.id;
            return (
              <Pressable key={pipeline.id} onPress={() => setSelected(pipeline.id)} style={({ pressed }) => [styles.pipelineRow, { backgroundColor: active ? "#182A27" : colors.surface, borderColor: active ? ACCENT : colors.border }, pressed && styles.pressed]}>
                <View style={[styles.radio, { borderColor: active ? ACCENT : colors.border }]}>{active && <View style={styles.radioInner} />}</View>
                <View style={styles.pipelineCopy}><Text style={[styles.pipelineTitle, { color: colors.foreground }]}>{pipeline.title}</Text><Text style={[styles.pipelineDetail, { color: colors.muted }]}>{pipeline.detail}</Text></View>
                <IconSymbol name="chevron.right" size={18} color={colors.muted} />
              </Pressable>
            );
          })}
        </View>

        <View style={styles.stepHeader}><Text style={[styles.sectionTitle, { color: colors.foreground }]}>پیش‌نیازها</Text><Text style={[styles.stepMeta, { color: colors.muted }]}>هنوز تنظیم نشده</Text></View>
        <View style={[styles.requirementsCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          {["اتصال امن به VPS ویندوز", "پروژه MQL5 یا اسکریپت Python", "داده تاریخی معتبر و تنظیمات آزمایش"].map((requirement) => <View key={requirement} style={styles.requirementRow}><View style={styles.requirementDot} /><Text style={[styles.requirementText, { color: colors.muted }]}>{requirement}</Text></View>)}
        </View>

        {showRequirements && <View style={[styles.resultCard, { backgroundColor: "#32291D", borderColor: "#624B2D" }]}><IconSymbol name="info.circle.fill" size={20} color="#E8B86D" /><View style={{ flex: 1 }}><Text style={[styles.resultTitle, { color: "#FFE1AE" }]}>سرور آماده نیست</Text><Text style={[styles.resultText, { color: "#D8C6AA" }]}>این MVP هنوز API یا اتصال VPS ندارد؛ نتایج و شاخص‌های ساختگی نمایش داده نمی‌شوند.</Text></View></View>}

        <Pressable onPress={inspectRequirements} style={({ pressed }) => [styles.runButton, pressed && styles.pressed]}><IconSymbol name="checkmark.shield.fill" size={18} color="#0B1513" /><Text style={styles.runText}>بررسی پیش‌نیازها</Text></Pressable>
        <Text style={[styles.disclaimer, { color: colors.muted }]}>حتی نتایج بک‌تست نیز عملکرد آینده را تضمین نمی‌کنند.</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 15 },
  eyebrow: { fontSize: 10, letterSpacing: 1.7, fontWeight: "800" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  subtitle: { fontSize: 11, lineHeight: 18, marginTop: 7, maxWidth: 320 },
  statusCard: { borderRadius: 16, borderWidth: 1, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  statusIcon: { width: 39, height: 39, borderRadius: 13, backgroundColor: "#234A40", alignItems: "center", justifyContent: "center" },
  statusTitle: { fontSize: 12, fontWeight: "800" },
  statusText: { fontSize: 9, lineHeight: 15, marginTop: 4 },
  offlineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#E8B86D" },
  stepHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 3 },
  sectionTitle: { fontSize: 15, fontWeight: "800" },
  stepMeta: { fontSize: 9 },
  pipelineList: { gap: 8 },
  pipelineRow: { borderWidth: 1, borderRadius: 15, padding: 12, flexDirection: "row", alignItems: "center" },
  radio: { width: 19, height: 19, borderRadius: 10, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  radioInner: { width: 9, height: 9, borderRadius: 5, backgroundColor: ACCENT },
  pipelineCopy: { flex: 1, marginHorizontal: 10 },
  pipelineTitle: { fontSize: 11, fontWeight: "800" },
  pipelineDetail: { fontSize: 9, lineHeight: 14, marginTop: 4 },
  requirementsCard: { borderRadius: 16, borderWidth: 1, padding: 13, gap: 12 },
  requirementRow: { flexDirection: "row", alignItems: "center", gap: 9 },
  requirementDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#E8B86D" },
  requirementText: { fontSize: 10, lineHeight: 16 },
  resultCard: { borderRadius: 15, borderWidth: 1, padding: 13, flexDirection: "row", gap: 10, alignItems: "flex-start" },
  resultTitle: { fontSize: 12, fontWeight: "800" },
  resultText: { fontSize: 9, lineHeight: 16, marginTop: 4 },
  runButton: { backgroundColor: ACCENT, borderRadius: 15, minHeight: 52, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 8, marginTop: 2 },
  runText: { color: "#0B1513", fontSize: 12, fontWeight: "800" },
  pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  disclaimer: { fontSize: 9, textAlign: "center", lineHeight: 15 },
});
