import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const symbols = [
  { symbol: "BTCUSDT", name: "Bitcoin Perpetual", timeframe: "5m" },
  { symbol: "ETHUSDT", name: "Ethereum Perpetual", timeframe: "15m" },
  { symbol: "SOLUSDT", name: "Solana Perpetual", timeframe: "1h" },
];

export default function MarketsScreen() {
  const colors = useColors();
  const [selected, setSelected] = useState("BTCUSDT");
  const [watching, setWatching] = useState<string[]>(["BTCUSDT"]);

  const toggleWatch = async (symbol: string) => {
    if (process.env.EXPO_OS !== "web") await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setWatching((current) => current.includes(symbol) ? current.filter((item) => item !== symbol) : [...current, symbol]);
  };

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View>
            <Text style={[styles.eyebrow, { color: colors.muted }]}>MARKET DATA</Text>
            <Text style={[styles.title, { color: colors.foreground }]}>بازارها</Text>
          </View>
          <View style={[styles.connection, { borderColor: colors.border }]}>
            <View style={[styles.connectionDot, { backgroundColor: colors.warning }]} />
            <Text style={[styles.connectionText, { color: colors.muted }]}>آفلاین</Text>
          </View>
        </View>

        <View style={[styles.chartCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.chartHead}>
            <View>
              <Text style={[styles.symbol, { color: colors.foreground }]}>{selected}</Text>
              <Text style={[styles.subtle, { color: colors.muted }]}>داده عمومی Bitunix · برای مشاهده نمودار متصل شوید</Text>
            </View>
            <IconSymbol name="waveform.path.ecg" size={24} color="#5CE1B8" />
          </View>
          <View style={styles.emptyChart}>
            <View style={styles.chartLine} />
            <Text style={[styles.emptyTitle, { color: colors.foreground }]}>داده‌ای دریافت نشده</Text>
            <Text style={[styles.emptySub, { color: colors.muted }]}>کلاینت بازار بعدی می‌تواند این بخش را پر کند</Text>
          </View>
          <View style={styles.timeframes}>
            {["1m", "5m", "15m", "1h", "4h"].map((timeframe) => (
              <View key={timeframe} style={[styles.timeframe, { backgroundColor: timeframe === "5m" ? "#173B35" : "transparent" }]}>
                <Text style={[styles.timeframeText, { color: timeframe === "5m" ? "#5CE1B8" : colors.muted }]}>{timeframe}</Text>
              </View>
            ))}
          </View>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.foreground }]}>واچ‌لیست</Text>
        <View style={styles.list}>
          {symbols.map((item) => {
            const isSelected = item.symbol === selected;
            const isWatching = watching.includes(item.symbol);
            return (
              <Pressable
                key={item.symbol}
                onPress={() => setSelected(item.symbol)}
                style={({ pressed }) => [styles.row, { backgroundColor: isSelected ? "#182A27" : colors.surface, borderColor: isSelected ? "#2B5349" : colors.border }, pressed && styles.pressed]}
              >
                <View style={[styles.coin, { backgroundColor: isSelected ? "#234A40" : colors.background }]}>
                  <Text style={[styles.coinText, { color: isSelected ? "#5CE1B8" : colors.muted }]}>{item.symbol.slice(0, 1)}</Text>
                </View>
                <View style={styles.rowInfo}>
                  <Text style={[styles.rowSymbol, { color: colors.foreground }]}>{item.symbol}</Text>
                  <Text style={[styles.rowSub, { color: colors.muted }]}>{item.name} · {item.timeframe}</Text>
                </View>
                <View style={styles.rowRight}>
                  <Text style={[styles.rowValue, { color: colors.muted }]}>—</Text>
                  <Pressable onPress={() => toggleWatch(item.symbol)} hitSlop={10} style={({ pressed }) => [styles.star, pressed && { opacity: 0.6 }]}>
                    <IconSymbol name={isWatching ? "star.fill" : "star"} size={18} color={isWatching ? "#FBBF24" : colors.muted} />
                  </Pressable>
                </View>
              </Pressable>
            );
          })}
        </View>

        <View style={[styles.info, { borderColor: colors.border }]}>
          <IconSymbol name="info.circle.fill" size={17} color={colors.muted} />
          <Text style={[styles.infoText, { color: colors.muted }]}>داده قیمت و کندل فقط پس از اتصال به منبع عمومی بازار نمایش داده می‌شود؛ این صفحه هیچ سفارش واقعی ارسال نمی‌کند.</Text>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 6 },
  eyebrow: { fontSize: 11, letterSpacing: 1.8, fontWeight: "700" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  connection: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 11, paddingVertical: 7, flexDirection: "row", gap: 6, alignItems: "center" },
  connectionDot: { width: 7, height: 7, borderRadius: 4 },
  connectionText: { fontSize: 11, fontWeight: "700" },
  chartCard: { borderWidth: 1, borderRadius: 22, padding: 17, minHeight: 300 },
  chartHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  symbol: { fontSize: 19, fontWeight: "800" },
  subtle: { fontSize: 10, marginTop: 5 },
  emptyChart: { flex: 1, minHeight: 190, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  chartLine: { position: "absolute", width: "130%", height: 1, backgroundColor: "#2B5349", transform: [{ rotate: "-8deg" }] },
  emptyTitle: { fontSize: 14, fontWeight: "700" },
  emptySub: { fontSize: 10, marginTop: 7 },
  timeframes: { flexDirection: "row", justifyContent: "space-between", backgroundColor: "#151F1D", borderRadius: 12, padding: 4 },
  timeframe: { paddingHorizontal: 11, paddingVertical: 7, borderRadius: 9 },
  timeframeText: { fontSize: 11, fontWeight: "700" },
  sectionTitle: { fontSize: 17, fontWeight: "800", marginTop: 5 },
  list: { gap: 9 },
  row: { borderRadius: 17, borderWidth: 1, padding: 12, flexDirection: "row", alignItems: "center" },
  coin: { width: 38, height: 38, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  coinText: { fontSize: 16, fontWeight: "800" },
  rowInfo: { flex: 1, marginLeft: 11 },
  rowSymbol: { fontSize: 14, fontWeight: "800" },
  rowSub: { fontSize: 10, marginTop: 4 },
  rowRight: { alignItems: "flex-end", gap: 6 },
  rowValue: { fontSize: 15, fontWeight: "800" },
  star: { padding: 2 },
  pressed: { opacity: 0.76 },
  info: { borderWidth: 1, borderRadius: 15, padding: 13, flexDirection: "row", gap: 9, alignItems: "flex-start" },
  infoText: { flex: 1, fontSize: 10, lineHeight: 17 },
});
