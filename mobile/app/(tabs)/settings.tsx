import { useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

const SETTINGS_KEY = "codexbot-mobile-settings";

type Settings = { paperOnly: boolean; notifications: boolean; riskGuard: boolean };
const defaultSettings: Settings = { paperOnly: true, notifications: false, riskGuard: true };

export default function SettingsScreen() {
  const colors = useColors();
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(SETTINGS_KEY).then((value) => {
      if (!value) return;
      try { setSettings({ ...defaultSettings, ...JSON.parse(value) }); } catch { /* keep safe defaults */ }
    });
  }, []);

  const update = async (key: keyof Settings, value: boolean) => {
    if (process.env.EXPO_OS !== "web") await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const next = { ...settings, [key]: value };
    setSettings(next);
    await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    setSaved(true);
    setTimeout(() => setSaved(false), 1600);
  };

  const showLiveInfo = () => Alert.alert("معامله زنده غیرفعال است", "این نسخه موبایل فقط برای پایش، تحقیق و PAPER طراحی شده است. برای اجرای زنده از برنامه دسکتاپ پس از بررسی کامل کد و حساب استفاده کنید.");

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View>
          <Text style={[styles.eyebrow, { color: colors.muted }]}>CONTROL CENTER</Text>
          <Text style={[styles.title, { color: colors.foreground }]}>تنظیمات</Text>
          <Text style={[styles.subtitle, { color: colors.muted }]}>کنترل‌های ایمنی روی همین دستگاه ذخیره می‌شوند.</Text>
        </View>

        <View style={[styles.safeCard, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
          <View style={styles.safeIcon}><IconSymbol name="lock.shield.fill" size={22} color="#5CE1B8" /></View>
          <View style={{ flex: 1 }}>
            <Text style={[styles.safeTitle, { color: "#D8F4EA" }]}>محیط ایمن فعال است</Text>
            <Text style={[styles.safeText, { color: "#A9C0BA" }]}>کلید API در این اپ ذخیره یا درخواست نمی‌شود.</Text>
          </View>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.foreground }]}>حفاظت معامله</Text>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <SettingRow icon="shield.fill" title="فقط PAPER" description="ارسال سفارش واقعی همیشه مسدود باشد" value={settings.paperOnly} onChange={(value) => update("paperOnly", value)} colors={colors} locked />
          <SettingRow icon="checkmark.shield.fill" title="گارد ریسک" description="پیش از هر اقدام، ریسک را بررسی کن" value={settings.riskGuard} onChange={(value) => update("riskGuard", value)} colors={colors} />
          <SettingRow icon="bell.fill" title="یادآوری‌های تحقیق" description="یادآوری برای بررسی بک‌تست و داده" value={settings.notifications} onChange={(value) => update("notifications", value)} colors={colors} last />
        </View>

        <Text style={[styles.sectionTitle, { color: colors.foreground }]}>دسترسی‌ها</Text>
        <Pressable onPress={showLiveInfo} style={({ pressed }) => [styles.disabledRow, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
          <View style={[styles.disabledIcon, { backgroundColor: colors.background }]}><IconSymbol name="bolt.fill" size={19} color={colors.muted} /></View>
          <View style={{ flex: 1 }}><Text style={[styles.disabledTitle, { color: colors.muted }]}>اتصال معامله زنده</Text><Text style={[styles.disabledText, { color: colors.muted }]}>در نسخه موبایل غیرفعال است</Text></View>
          <Text style={[styles.locked, { color: colors.warning }]}>قفل</Text>
        </Pressable>

        <View style={styles.footer}>
          <Text style={[styles.version, { color: colors.muted }]}>CodexBot Mobile · نسخه ۰.۱</Text>
          {saved && <Text style={[styles.saved, { color: "#5CE1B8" }]}>ذخیره شد</Text>}
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

function SettingRow({ icon, title, description, value, onChange, colors, locked, last }: { icon: any; title: string; description: string; value: boolean; onChange: (value: boolean) => void; colors: any; locked?: boolean; last?: boolean }) {
  return (
    <View style={[styles.settingRow, !last && { borderBottomWidth: 1, borderBottomColor: "#29413B" }]}>
      <View style={styles.settingIcon}><IconSymbol name={icon} size={18} color={value ? "#5CE1B8" : colors.muted} /></View>
      <View style={styles.settingCopy}><Text style={[styles.settingTitle, { color: colors.foreground }]}>{title}</Text><Text style={[styles.settingDescription, { color: colors.muted }]}>{description}</Text></View>
      <Switch value={value} onValueChange={onChange} disabled={locked} trackColor={{ false: "#34433F", true: "#2B8D74" }} thumbColor={value ? "#5CE1B8" : "#9BA1A6"} />
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 15 },
  eyebrow: { fontSize: 11, letterSpacing: 1.8, fontWeight: "700" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  subtitle: { fontSize: 12, lineHeight: 19, marginTop: 7 },
  safeCard: { borderRadius: 18, borderWidth: 1, padding: 14, flexDirection: "row", alignItems: "center", gap: 11 },
  safeIcon: { width: 40, height: 40, borderRadius: 13, backgroundColor: "#234A40", alignItems: "center", justifyContent: "center" },
  safeTitle: { fontSize: 13, fontWeight: "800" },
  safeText: { fontSize: 10, marginTop: 4 },
  sectionTitle: { fontSize: 16, fontWeight: "800", marginTop: 4 },
  card: { borderWidth: 1, borderRadius: 18, paddingHorizontal: 14 },
  settingRow: { minHeight: 70, flexDirection: "row", alignItems: "center", paddingVertical: 10 },
  settingIcon: { width: 30, alignItems: "flex-start" },
  settingCopy: { flex: 1, paddingRight: 8 },
  settingTitle: { fontSize: 13, fontWeight: "800" },
  settingDescription: { fontSize: 10, marginTop: 4, lineHeight: 15 },
  disabledRow: { borderWidth: 1, borderRadius: 17, padding: 13, flexDirection: "row", alignItems: "center" },
  disabledIcon: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  disabledTitle: { fontSize: 13, fontWeight: "800" },
  disabledText: { fontSize: 10, marginTop: 4 },
  locked: { fontSize: 10, fontWeight: "800" },
  pressed: { opacity: 0.75 },
  footer: { alignItems: "center", gap: 8, marginTop: 4 },
  version: { fontSize: 10 },
  saved: { fontSize: 11, fontWeight: "800" },
});
