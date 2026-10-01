import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const ACCENT = "#5CE1B8";
const symbols = [
  { symbol: "EURUSD", name: "Euro / US Dollar", timeframe: "15m" },
  { symbol: "GBPUSD", name: "British Pound / US Dollar", timeframe: "1h" },
  { symbol: "XAUUSD", name: "Gold / US Dollar", timeframe: "4h" },
  { symbol: "BTCUSD", name: "Bitcoin / US Dollar", timeframe: "1h" },
];

export default function MarketsScreen() {
  const colors = useColors();
  const [selected, setSelected] = useState("EURUSD");
  const [watching, setWatching] = useState<string[]>(["EURUSD", "XAUUSD"]);

  const toggleWatch = async (symbol: string) => {
    if (process.env.EXPO_OS !== "web") await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setWatching((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]);
  };

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View><Text style={[styles.eyebrow, { color: colors.muted }]}>MT5 MARKET DATA</Text><Text style={[styles.title, { color: colors.foreground }]}>بازارها</Text></View>
          <View style={[styles.connection, { borderColor: colors.border }]}><View style={styles.offlineDot} /><Text style={[styles.connectionText, { color: colors.muted }]}>آفلاین</Text></View>
        </View>

        <View style={[styles.chartCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.chartHead}>
            <View><Text style={[styles.symbol, { color: colors.foreground }]}>{selected}</Text><Text style={[styles.subtle, { color: colors.muted }]}>MetaTrader 5 · منبع داده متصل نشده</Text></View>
            <IconSymbol name="waveform.path.ecg" size={23} color={ACCENT} />
          </View>
          <View style={styles.emptyChart}>
            <View style={styles.chartLine} />
            <View style={styles.emptyIcon}><IconSymbol name="chart.bar.fill" size={22} color={ACCENT} /></View>
            <Text style={[styles.emptyTitle, { color: colors.foreground }]}>نمودار در انتظار داده است</Text>
            <Text style={[styles.emptySub, { color: colors.muted }]}>بعد از اتصال VPS و ترمینال MT5 نمایش داده می‌شود.</Text>
          </View>
          <View style={styles.timeframes}>{["1m", "5m", "15m", "1h", "4h"].map((timeframe) => <View key={timeframe} style={[styles.timeframe, { backgroundColor: timeframe === "15m" ? "#173B35" : "transparent" }]}><Text style={[styles.timeframeText, { color: timeframe === "15m" ? ACCENT : colors.muted }]}>{timeframe}</Text></View>)}</View>
        </View>

        <View style={styles.listHeading}><Text style={[styles.sectionTitle, { color: colors.foreground }]}>واچ‌لیست</Text><Text style={[styles.sectionMeta, { color: colors.muted }]}>قیمت پس از اتصال نمایش داده می‌شود</Text></View>
        <View style={styles.list}>
          {symbols.map((item) => {
            const isSelected = item.symbol === selected;
            const isWatching = watching.includes(item.symbol);
            return (
              <Pressable key={item.symbol} onPress={() => setSelected(item.symbol)} style={({ pressed }) => [styles.row, { backgroundColor: isSelected ? "#182A27" : colors.surface, borderColor: isSelected ? "#2B5349" : colors.border }, pressed && styles.pressed]}>
                <View style={[styles.coin, { backgroundColor: isSelected ? "#234A40" : colors.background }]}><Text style={[styles.coinText, { color: isSelected ? ACCENT : colors.muted }]}>{item.symbol.slice(0, 1)}</Text></View>
                <View style={styles.rowInfo}><Text style={[styles.rowSymbol, { color: colors.foreground }]}>{item.symbol}</Text><Text style={[styles.rowSub, { color: colors.muted }]}>{item.name} · {item.timeframe}</Text></View>
                <View style={styles.rowRight}><Text style={[styles.rowValue, { color: colors.muted }]}>—</Text><Pressable onPress={() => toggleWatch(item.symbol)} hitSlop={10} style={({ pressed }) => [styles.star, pressed && { opacity: 0.6 }]}><IconSymbol name={isWatching ? "star.fill" : "star"} size={18} color={isWatching ? "#FBBF24" : colors.muted} /></Pressable></View>
              </Pressable>
            );
          })}
        </View>

        <View style={[styles.info, { borderColor: colors.border }]}><IconSymbol name="info.circle.fill" size={17} color={colors.muted} /><Text style={[styles.infoText, { color: colors.muted }]}>نمادها فقط نمونه‌اند. این صفحه هنوز به بروکر، ترمینال یا فید عمومی بازار وصل نیست و قیمت ساختگی نشان نمی‌دهد.</Text></View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 15 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 5 },
  eyebrow: { fontSize: 10, letterSpacing: 1.6, fontWeight: "800" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  connection: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 7, flexDirection: "row", gap: 6, alignItems: "center" },
  offlineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#E8B86D" },
  connectionText: { fontSize: 10, fontWeight: "700" },
  chartCard: { borderWidth: 1, borderRadius: 20, padding: 15, minHeight: 285 },
  chartHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  symbol: { fontSize: 18, fontWeight: "800" },
  subtle: { fontSize: 9, marginTop: 5 },
  emptyChart: { flex: 1, minHeight: 184, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  chartLine: { position: "absolute", width: "130%", height: 1, backgroundColor: "#2B5349", transform: [{ rotate: "-8deg" }] },
  emptyIcon: { width: 44, height: 44, borderRadius: 14, backgroundColor: "#173B35", alignItems: "center", justifyContent: "center", marginBottom: 10 },
  emptyTitle: { fontSize: 13, fontWeight: "700" },
  emptySub: { fontSize: 9, lineHeight: 15, marginTop: 6, textAlign: "center" },
  timeframes: { flexDirection: "row", justifyContent: "space-between", backgroundColor: "#151F1D", borderRadius: 12, padding: 4 },
  timeframe: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 9 },
  timeframeText: { fontSize: 10, fontWeight: "700" },
  listHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: "800" },
  sectionMeta: { fontSize: 8 },
  list: { gap: 8 },
  row: { borderRadius: 16, borderWidth: 1, padding: 11, flexDirection: "row", alignItems: "center" },
  coin: { width: 37, height: 37, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  coinText: { fontSize: 15, fontWeight: "800" },
  rowInfo: { flex: 1, marginLeft: 10 },
  rowSymbol: { fontSize: 13, fontWeight: "800" },
  rowSub: { fontSize: 9, marginTop: 4 },
  rowRight: { alignItems: "flex-end", gap: 5 },
  rowValue: { fontSize: 14, fontWeight: "800" },
  star: { padding: 2 },
  pressed: { opacity: 0.76 },
  info: { borderWidth: 1, borderRadius: 14, padding: 12, flexDirection: "row", gap: 8, alignItems: "flex-start" },
  infoText: { flex: 1, fontSize: 9, lineHeight: 16 },
});
