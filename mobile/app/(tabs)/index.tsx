import { useMemo } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const ACCENT = "#5CE1B8";

export default function HomeScreen() {
  const colors = useColors();
  const router = useRouter();
  const services = useMemo(() => [
    { label: "VPS ویندوز", status: "وصل نیست", icon: "server.rack" as const },
    { label: "MetaTrader 5", status: "وصل نیست", icon: "chart.bar.fill" as const },
    { label: "کامپایلر MQL5", status: "پیکربندی نشده", icon: "code" as const },
  ], []);

  const tap = async () => {
    if (process.env.EXPO_OS !== "web") await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const go = async (route: "/projects" | "/markets" | "/backtest") => {
    await tap();
    router.push(route);
  };

  return (
    <ScreenContainer containerClassName="bg-background" className="px-5">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={[styles.eyebrow, { color: colors.muted }]}>MTFLOW / MOBILE CONTROL</Text>
            <Text style={[styles.title, { color: colors.foreground }]}>میزکار شما</Text>
          </View>
          <View style={styles.brandMark}><Image source={require("@/assets/images/mtflow-mark.png")} style={styles.brandImage} resizeMode="contain" /></View>
        </View>

        <View style={[styles.heroCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.heroTopline}>
            <View style={styles.heroBadge}><View style={styles.statusDot} /><Text style={styles.heroBadgeText}>آفلاین</Text></View>
            <Text style={[styles.heroHint, { color: colors.muted }]}>نیازمند اتصال VPS</Text>
          </View>
          <Text style={[styles.heroTitle, { color: colors.foreground }]}>کنترل امن MT5</Text>
          <Text style={[styles.heroCopy, { color: colors.muted }]}>گوشی میزکار و مرکز کنترل است؛ اجرای MetaTrader و اکسپرت‌ها باید روی VPS ویندوز انجام شود.</Text>
          <View style={styles.paperRow}>
            <View style={styles.paperIcon}><IconSymbol name="lock.shield.fill" size={18} color={ACCENT} /></View>
            <View style={{ flex: 1 }}><Text style={[styles.paperTitle, { color: colors.foreground }]}>حالت ایمن · PAPER</Text><Text style={[styles.paperSub, { color: colors.muted }]}>هیچ سفارش واقعی از این اپ ارسال نمی‌شود.</Text></View>
            <View style={styles.lockPill}><Text style={styles.lockPillText}>قفل LIVE</Text></View>
          </View>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>وضعیت اجزا</Text>
          <Text style={[styles.sectionMeta, { color: colors.muted }]}>اتصال زنده برقرار نشده</Text>
        </View>
        <View style={styles.serviceList}>
          {services.map((service) => (
            <View key={service.label} style={[styles.serviceCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={styles.serviceIcon}><IconSymbol name={service.icon} size={19} color={ACCENT} /></View>
              <View style={styles.serviceCopy}><Text style={[styles.serviceName, { color: colors.foreground }]}>{service.label}</Text><Text style={[styles.serviceState, { color: colors.muted }]}>{service.status}</Text></View>
              <View style={styles.offlineDot} />
            </View>
          ))}
        </View>

        <View style={styles.sectionHeader}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>فضای توسعه</Text>
          <Text style={[styles.sectionMeta, { color: colors.muted }]}>محلی روی دستگاه</Text>
        </View>
        <View style={styles.actionsGrid}>
          <ActionCard icon="folder.fill" title="پروژه‌ها" description="قالب MQL5 و Python" colors={colors} onPress={() => go("/projects")} />
          <ActionCard icon="clock.arrow.circlepath" title="آزمایش" description="آماده‌سازی بک‌تست" colors={colors} onPress={() => go("/backtest")} />
        </View>
        <Pressable onPress={() => go("/markets")} style={({ pressed }) => [styles.marketLink, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
          <View style={styles.marketIcon}><IconSymbol name="chart.bar.fill" size={19} color={ACCENT} /></View>
          <View style={{ flex: 1 }}><Text style={[styles.actionTitle, { color: colors.foreground }]}>Market Data</Text><Text style={[styles.actionSub, { color: colors.muted }]}>واچ‌لیست نمادهای MT5 · بدون قیمت ساختگی</Text></View>
          <IconSymbol name="chevron.right" size={18} color={colors.muted} />
        </Pressable>

        <View style={[styles.notice, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
          <IconSymbol name="info.circle.fill" size={18} color={ACCENT} />
          <Text style={[styles.noticeText, { color: "#D8F4EA" }]}>نمونه اولیه هنوز به VPS، MetaTrader 5 یا منبع داده بازار متصل نیست. وضعیت‌ها عمداً آفلاین نمایش داده می‌شوند.</Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

function ActionCard({ icon, title, description, colors, onPress }: { icon: "folder.fill" | "clock.arrow.circlepath"; title: string; description: string; colors: ReturnType<typeof useColors>; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.actionCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
      <IconSymbol name={icon} size={20} color={ACCENT} />
      <Text style={[styles.actionTitle, { color: colors.foreground }]}>{title}</Text>
      <Text style={[styles.actionSub, { color: colors.muted }]}>{description}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 15 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 3 },
  eyebrow: { fontSize: 10, letterSpacing: 1.5, fontWeight: "800" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  brandMark: { width: 44, height: 44, borderRadius: 15, backgroundColor: "#173B35", alignItems: "center", justifyContent: "center" },
  brandImage: { width: 34, height: 34 },
  heroCard: { borderWidth: 1, borderRadius: 23, padding: 17 },
  heroTopline: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  heroBadge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20, backgroundColor: "#32291D" },
  statusDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#E8B86D" },
  heroBadgeText: { color: "#E8B86D", fontSize: 10, fontWeight: "800" },
  heroHint: { fontSize: 10 },
  heroTitle: { fontSize: 20, fontWeight: "800", marginTop: 19 },
  heroCopy: { fontSize: 11, lineHeight: 18, marginTop: 6 },
  paperRow: { borderTopWidth: 1, borderTopColor: "#29413B", marginTop: 15, paddingTop: 14, flexDirection: "row", alignItems: "center", gap: 9 },
  paperIcon: { width: 35, height: 35, borderRadius: 12, backgroundColor: "#234A40", alignItems: "center", justifyContent: "center" },
  paperTitle: { fontSize: 11, fontWeight: "800" },
  paperSub: { fontSize: 9, marginTop: 3 },
  lockPill: { backgroundColor: "#24302D", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 6 },
  lockPillText: { color: ACCENT, fontSize: 9, fontWeight: "800" },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 2 },
  sectionTitle: { fontSize: 15, fontWeight: "800" },
  sectionMeta: { fontSize: 9 },
  serviceList: { gap: 7 },
  serviceCard: { minHeight: 57, borderWidth: 1, borderRadius: 15, paddingHorizontal: 11, flexDirection: "row", alignItems: "center" },
  serviceIcon: { width: 34, height: 34, borderRadius: 11, backgroundColor: "#173B35", alignItems: "center", justifyContent: "center" },
  serviceCopy: { flex: 1, marginLeft: 10 },
  serviceName: { fontSize: 11, fontWeight: "800" },
  serviceState: { fontSize: 9, marginTop: 3 },
  offlineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#E8B86D" },
  actionsGrid: { flexDirection: "row", gap: 9 },
  actionCard: { flex: 1, borderRadius: 16, borderWidth: 1, padding: 13, minHeight: 105 },
  actionTitle: { fontSize: 12, fontWeight: "800", marginTop: 12 },
  actionSub: { fontSize: 9, lineHeight: 15, marginTop: 4 },
  marketLink: { borderWidth: 1, borderRadius: 16, padding: 12, flexDirection: "row", alignItems: "center", gap: 10 },
  marketIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: "#173B35", alignItems: "center", justifyContent: "center" },
  notice: { borderRadius: 15, borderWidth: 1, padding: 12, flexDirection: "row", gap: 9, alignItems: "flex-start" },
  noticeText: { flex: 1, fontSize: 9, lineHeight: 16 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
});
