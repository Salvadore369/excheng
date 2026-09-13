import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const accent = "#5CE1B8";

function formatPrice(value: string | null) {
  return value ?? "—";
}

export default function HomeScreen() {
  const colors = useColors();
  const [connected, setConnected] = useState(false);
  const [paperArmed, setPaperArmed] = useState(false);

  const statusText = useMemo(() => {
    if (connected) return "داده بازار متصل است";
    return "در انتظار اتصال داده بازار";
  }, [connected]);

  const tap = async () => {
    if (process.env.EXPO_OS !== "web") {
      await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
  };

  return (
    <ScreenContainer containerClassName="bg-background" className="px-5">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={[styles.eyebrow, { color: colors.muted }]}>CODعX / WORKSPACE</Text>
            <Text style={[styles.title, { color: colors.foreground }]}>سلام، معامله‌گر</Text>
          </View>
          <View style={[styles.statusDot, { backgroundColor: connected ? accent : colors.warning }]} />
        </View>

        <View style={[styles.modeCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.modeTopline}>
            <View style={styles.modeLabelRow}>
              <View style={[styles.pulse, { backgroundColor: paperArmed ? accent : colors.warning }]} />
              <Text style={[styles.modeLabel, { color: colors.foreground }]}>PAPER MODE</Text>
            </View>
            <Text style={[styles.modeHint, { color: colors.muted }]}>بدون سفارش واقعی</Text>
          </View>
          <Text style={[styles.balanceLabel, { color: colors.muted }]}>ارزش حساب</Text>
          <Text style={[styles.balance, { color: colors.foreground }]}>—</Text>
          <View style={styles.divider} />
          <View style={styles.metricRow}>
            <View>
              <Text style={[styles.metricLabel, { color: colors.muted }]}>بازده امروز</Text>
              <Text style={[styles.metricValue, { color: colors.muted }]}>داده‌ای موجود نیست</Text>
            </View>
            <View style={styles.metricRight}>
              <Text style={[styles.metricLabel, { color: colors.muted }]}>ریسک هر معامله</Text>
              <Text style={[styles.metricValue, { color: accent }]}>۰.۵٪ پیش‌فرض</Text>
            </View>
          </View>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>بازار تحت نظر</Text>
          <Text style={[styles.sectionMeta, { color: colors.muted }]}>{statusText}</Text>
        </View>
        <View style={[styles.marketCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.marketIcon}>
            <IconSymbol name="chart.bar.fill" size={20} color={accent} />
          </View>
          <View style={styles.marketInfo}>
            <Text style={[styles.marketSymbol, { color: colors.foreground }]}>BTCUSDT</Text>
            <Text style={[styles.marketSub, { color: colors.muted }]}>Bitunix Perpetual · 5m</Text>
          </View>
          <View style={styles.marketPrice}>
            <Text style={[styles.price, { color: colors.foreground }]}>{formatPrice(null)}</Text>
            <Text style={[styles.priceChange, { color: colors.muted }]}>اتصال لازم است</Text>
          </View>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>اقدام سریع</Text>
        </View>
        <View style={styles.actionsGrid}>
          <Pressable
            onPress={async () => {
              await tap();
              setPaperArmed((value) => !value);
            }}
            style={({ pressed }) => [styles.actionCard, { backgroundColor: paperArmed ? "#173B35" : colors.surface, borderColor: paperArmed ? accent : colors.border }, pressed && styles.pressed]}
          >
            <IconSymbol name="shield.fill" size={21} color={paperArmed ? accent : colors.foreground} />
            <Text style={[styles.actionTitle, { color: colors.foreground }]}>{paperArmed ? "PAPER فعال" : "فعال‌سازی PAPER"}</Text>
            <Text style={[styles.actionSub, { color: colors.muted }]}>اجرای محلی و بدون ریسک</Text>
          </Pressable>
          <Pressable
            onPress={async () => {
              await tap();
              setConnected((value) => !value);
            }}
            style={({ pressed }) => [styles.actionCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}
          >
            <IconSymbol name="arrow.triangle.2.circlepath" size={21} color={colors.foreground} />
            <Text style={[styles.actionTitle, { color: colors.foreground }]}>{connected ? "قطع داده بازار" : "بررسی اتصال"}</Text>
            <Text style={[styles.actionSub, { color: colors.muted }]}>فقط داده عمومی بازار</Text>
          </Pressable>
        </View>

        <View style={[styles.notice, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
          <IconSymbol name="exclamationmark.triangle.fill" size={18} color={colors.warning} />
          <Text style={[styles.noticeText, { color: "#D8F4EA" }]}>معامله زنده از این نسخه موبایل غیرفعال است. قبل از هر تصمیم، داده و استراتژی را شخصاً اعتبارسنجی کنید.</Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 32, gap: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  eyebrow: { fontSize: 11, letterSpacing: 1.8, fontWeight: "700" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  statusDot: { width: 12, height: 12, borderRadius: 6, marginRight: 4 },
  modeCard: { borderWidth: 1, borderRadius: 24, padding: 20 },
  modeTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  modeLabelRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  pulse: { width: 8, height: 8, borderRadius: 4 },
  modeLabel: { fontSize: 12, fontWeight: "800", letterSpacing: 1.4 },
  modeHint: { fontSize: 11 },
  balanceLabel: { fontSize: 12, marginTop: 28 },
  balance: { fontSize: 38, fontWeight: "800", marginTop: 4 },
  divider: { height: 1, backgroundColor: "#29413B", marginVertical: 18 },
  metricRow: { flexDirection: "row", justifyContent: "space-between" },
  metricRight: { alignItems: "flex-end" },
  metricLabel: { fontSize: 11 },
  metricValue: { fontSize: 13, fontWeight: "700", marginTop: 5 },
  sectionHeader: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", marginTop: 4 },
  sectionTitle: { fontSize: 17, fontWeight: "800" },
  sectionMeta: { fontSize: 11 },
  marketCard: { borderWidth: 1, borderRadius: 18, padding: 15, flexDirection: "row", alignItems: "center" },
  marketIcon: { width: 42, height: 42, borderRadius: 14, backgroundColor: "#173B35", alignItems: "center", justifyContent: "center" },
  marketInfo: { marginLeft: 12, flex: 1 },
  marketSymbol: { fontSize: 15, fontWeight: "800" },
  marketSub: { fontSize: 11, marginTop: 4 },
  marketPrice: { alignItems: "flex-end" },
  price: { fontSize: 16, fontWeight: "800" },
  priceChange: { fontSize: 10, marginTop: 4 },
  actionsGrid: { flexDirection: "row", gap: 10 },
  actionCard: { flex: 1, borderRadius: 18, borderWidth: 1, padding: 15, minHeight: 125 },
  actionTitle: { fontSize: 13, fontWeight: "800", marginTop: 18 },
  actionSub: { fontSize: 10, lineHeight: 16, marginTop: 5 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
  notice: { borderRadius: 16, borderWidth: 1, padding: 14, flexDirection: "row", gap: 10, alignItems: "flex-start" },
  noticeText: { flex: 1, fontSize: 11, lineHeight: 18 },
});
