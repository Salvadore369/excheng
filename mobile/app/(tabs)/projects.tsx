import { useEffect, useMemo, useState } from "react";
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { createWorkspaceProject, loadWorkspaceProjects, PROJECT_TEMPLATES, ProjectKind, saveWorkspaceProjects, WorkspaceProject } from "@/lib/workspace";

const ACCENT = "#5CE1B8";
const KINDS: ProjectKind[] = ["EA", "Indicator", "Python"];

export default function ProjectsScreen() {
  const colors = useColors();
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<WorkspaceProject | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectKind, setProjectKind] = useState<ProjectKind>("EA");
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadWorkspaceProjects()
      .then(setProjects)
      .catch(() => setMessage("فضای کار محلی در دسترس نیست."))
      .finally(() => setLoading(false));
  }, []);

  const orderedProjects = useMemo(() => [...projects].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)), [projects]);

  const createProject = async () => {
    const cleanName = projectName.trim();
    if (!cleanName) {
      setMessage("برای پروژه یک نام وارد کنید.");
      return;
    }
    const created = createWorkspaceProject(cleanName, projectKind);
    const next = [created, ...projects];
    try {
      await saveWorkspaceProjects(next);
      setProjects(next);
      setShowCreate(false);
      setProjectName("");
      setMessage("پروژه فقط روی همین دستگاه ساخته شد.");
      openEditor(created);
    } catch {
      setMessage("ذخیره‌سازی محلی انجام نشد. فضای دستگاه را بررسی کنید.");
    }
  };

  const openEditor = (project: WorkspaceProject) => {
    setEditing(project);
    setDraft(project.code);
    setMessage("");
  };

  const saveCode = async () => {
    if (!editing) return;
    setSaving(true);
    const updated = { ...editing, code: draft, updatedAt: new Date().toISOString() };
    const next = projects.map((project) => project.id === editing.id ? updated : project);
    try {
      await saveWorkspaceProjects(next);
      setProjects(next);
      setEditing(updated);
      setMessage("تغییرات روی همین دستگاه ذخیره شد.");
      if (Platform.OS !== "web") await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      setMessage("ذخیره کد انجام نشد.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScreenContainer className="px-5" containerClassName="bg-background">
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={[styles.eyebrow, { color: colors.muted }]}>LOCAL WORKSPACE</Text>
            <Text style={[styles.title, { color: colors.foreground }]}>پروژه‌ها</Text>
            <Text style={[styles.subtitle, { color: colors.muted }]}>قالب‌های MQL5 و Python؛ فایل‌ها فعلاً فقط روی این دستگاه نگهداری می‌شوند.</Text>
          </View>
          <View style={[styles.headerIcon, { backgroundColor: "#173B35" }]}><IconSymbol name="folder.fill" size={22} color={ACCENT} /></View>
        </View>

        <View style={[styles.notice, { backgroundColor: "#182A27", borderColor: "#2B5349" }]}>
          <IconSymbol name="lock.shield.fill" size={19} color={ACCENT} />
          <Text style={[styles.noticeText, { color: "#D8F4EA" }]}>این ویرایشگر به VPS یا MetaTrader متصل نیست و هیچ Build یا سفارشی اجرا نمی‌کند.</Text>
        </View>

        <View style={styles.listHeading}>
          <Text style={[styles.sectionTitle, { color: colors.foreground }]}>فضای کار شما</Text>
          <Text style={[styles.count, { color: colors.muted }]}>{projects.length} پروژه</Text>
        </View>

        {!loading && orderedProjects.length === 0 && (
          <View style={[styles.emptyCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={[styles.emptyIcon, { backgroundColor: colors.background }]}><IconSymbol name="code" size={22} color={ACCENT} /></View>
            <Text style={[styles.emptyTitle, { color: colors.foreground }]}>هنوز پروژه‌ای ندارید</Text>
            <Text style={[styles.emptyText, { color: colors.muted }]}>یک قالب امن بسازید و کد را محلی ویرایش کنید.</Text>
          </View>
        )}

        {loading && <Text style={[styles.emptyText, { color: colors.muted }]}>در حال خواندن فضای کار…</Text>}

        <View style={styles.projectList}>
          {orderedProjects.map((project) => {
            const template = PROJECT_TEMPLATES[project.kind];
            return (
              <Pressable key={project.id} onPress={() => openEditor(project)} style={({ pressed }) => [styles.projectCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}>
                <View style={[styles.projectIcon, { backgroundColor: "#173B35" }]}><IconSymbol name={project.kind === "Python" ? "terminal.fill" : "code"} size={20} color={ACCENT} /></View>
                <View style={styles.projectCopy}>
                  <Text numberOfLines={1} style={[styles.projectName, { color: colors.foreground }]}>{project.name}</Text>
                  <Text style={[styles.projectMeta, { color: colors.muted }]}>{template.label} · {template.extension}</Text>
                </View>
                <IconSymbol name="chevron.right" size={19} color={colors.muted} />
              </Pressable>
            );
          })}
        </View>

        <Pressable onPress={() => { setMessage(""); setShowCreate(true); }} style={({ pressed }) => [styles.createButton, pressed && styles.pressed]}>
          <IconSymbol name="plus" size={20} color="#0B1513" />
          <Text style={styles.createButtonText}>پروژه جدید</Text>
        </Pressable>
        {message ? <Text accessibilityLiveRegion="polite" style={[styles.feedback, { color: ACCENT }]}>{message}</Text> : null}
      </ScrollView>

      <Modal visible={showCreate} animationType="slide" presentationStyle="pageSheet" onRequestClose={() => setShowCreate(false)}>
        <SafeAreaView style={[styles.modalRoot, { backgroundColor: colors.background }]}>
          <View style={styles.modalHeader}>
            <Text style={[styles.modalTitle, { color: colors.foreground }]}>ساخت پروژه</Text>
            <Pressable onPress={() => setShowCreate(false)} accessibilityRole="button" accessibilityLabel="بستن" style={styles.closeButton}><IconSymbol name="xmark" size={22} color={colors.muted} /></Pressable>
          </View>
          <Text style={[styles.fieldLabel, { color: colors.muted }]}>نام پروژه</Text>
          <TextInput value={projectName} onChangeText={setProjectName} placeholder="مثلاً EURUSD Session EA" placeholderTextColor={colors.muted} style={[styles.nameInput, { color: colors.foreground, backgroundColor: colors.surface, borderColor: colors.border }]} returnKeyType="done" maxLength={48} />
          <Text style={[styles.fieldLabel, { color: colors.muted }]}>قالب شروع</Text>
          <View style={styles.templateList}>
            {KINDS.map((kind) => {
              const template = PROJECT_TEMPLATES[kind];
              const active = kind === projectKind;
              return (
                <Pressable key={kind} onPress={() => setProjectKind(kind)} style={[styles.templateCard, { backgroundColor: active ? "#182A27" : colors.surface, borderColor: active ? ACCENT : colors.border }]}>
                  <Text style={[styles.templateName, { color: colors.foreground }]}>{template.label}</Text>
                  <Text style={[styles.templateDescription, { color: colors.muted }]}>{template.description}</Text>
                </Pressable>
              );
            })}
          </View>
          <Pressable onPress={createProject} style={({ pressed }) => [styles.createButton, styles.modalAction, pressed && styles.pressed]}><IconSymbol name="plus" size={19} color="#0B1513" /><Text style={styles.createButtonText}>ساخت در این دستگاه</Text></Pressable>
          {message ? <Text style={[styles.feedback, { color: colors.warning }]}>{message}</Text> : null}
        </SafeAreaView>
      </Modal>

      <Modal visible={editing !== null} animationType="slide" presentationStyle="fullScreen" onRequestClose={() => setEditing(null)}>
        <SafeAreaView style={[styles.editorRoot, { backgroundColor: colors.background }]}>
          <View style={styles.modalHeader}>
            <View style={styles.editorHeading}>
              <Text numberOfLines={1} style={[styles.modalTitle, { color: colors.foreground }]}>{editing?.name}</Text>
              <Text style={[styles.editorFile, { color: colors.muted }]}>{editing ? PROJECT_TEMPLATES[editing.kind].extension : ""} · ذخیره محلی</Text>
            </View>
            <Pressable onPress={() => setEditing(null)} accessibilityRole="button" accessibilityLabel="بستن ویرایشگر" style={styles.closeButton}><IconSymbol name="xmark" size={22} color={colors.muted} /></Pressable>
          </View>
          <KeyboardAvoidingView style={styles.editorBody} behavior={Platform.OS === "ios" ? "padding" : undefined}>
            <TextInput value={draft} onChangeText={setDraft} multiline textAlignVertical="top" autoCapitalize="none" autoCorrect={false} spellCheck={false} selectionColor={ACCENT} style={[styles.codeInput, { backgroundColor: colors.surface, color: colors.foreground, borderColor: colors.border }]} accessibilityLabel="کد منبع پروژه" />
            <Pressable onPress={saveCode} disabled={saving} style={({ pressed }) => [styles.createButton, styles.saveButton, saving && { opacity: 0.6 }, pressed && styles.pressed]}><IconSymbol name="square.and.arrow.down" size={19} color="#0B1513" /><Text style={styles.createButtonText}>{saving ? "در حال ذخیره…" : "ذخیره تغییرات"}</Text></Pressable>
            {message ? <Text accessibilityLiveRegion="polite" style={[styles.feedback, { color: ACCENT }]}>{message}</Text> : null}
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingTop: 12, paddingBottom: 34, gap: 16 },
  header: { flexDirection: "row", alignItems: "center", gap: 12 },
  headerCopy: { flex: 1 },
  eyebrow: { fontSize: 10, letterSpacing: 1.7, fontWeight: "800" },
  title: { fontSize: 28, fontWeight: "800", marginTop: 5 },
  subtitle: { fontSize: 11, lineHeight: 18, marginTop: 6 },
  headerIcon: { width: 46, height: 46, borderRadius: 15, alignItems: "center", justifyContent: "center" },
  notice: { borderRadius: 16, borderWidth: 1, padding: 13, flexDirection: "row", alignItems: "flex-start", gap: 9 },
  noticeText: { flex: 1, fontSize: 10, lineHeight: 17 },
  listHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: "800" },
  count: { fontSize: 11 },
  emptyCard: { borderWidth: 1, borderRadius: 18, padding: 22, alignItems: "center" },
  emptyIcon: { width: 46, height: 46, borderRadius: 15, alignItems: "center", justifyContent: "center", marginBottom: 11 },
  emptyTitle: { fontSize: 14, fontWeight: "800" },
  emptyText: { fontSize: 10, lineHeight: 16, textAlign: "center", marginTop: 6 },
  projectList: { gap: 9 },
  projectCard: { minHeight: 70, borderRadius: 17, borderWidth: 1, padding: 12, flexDirection: "row", alignItems: "center" },
  projectIcon: { width: 42, height: 42, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  projectCopy: { flex: 1, marginHorizontal: 11 },
  projectName: { fontSize: 13, fontWeight: "800" },
  projectMeta: { fontSize: 10, marginTop: 4 },
  createButton: { minHeight: 52, borderRadius: 15, backgroundColor: ACCENT, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 8 },
  createButtonText: { color: "#0B1513", fontSize: 13, fontWeight: "800" },
  feedback: { textAlign: "center", fontSize: 10, lineHeight: 16 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  modalRoot: { flex: 1, padding: 20, paddingTop: 14 },
  editorRoot: { flex: 1, padding: 16, paddingTop: 10 },
  modalHeader: { minHeight: 52, flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14 },
  modalTitle: { fontSize: 18, fontWeight: "800", flex: 1 },
  closeButton: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(130,150,145,0.10)" },
  fieldLabel: { fontSize: 11, fontWeight: "700", marginBottom: 8, marginTop: 4 },
  nameInput: { minHeight: 48, borderWidth: 1, borderRadius: 13, paddingHorizontal: 13, fontSize: 13, marginBottom: 16 },
  templateList: { gap: 9 },
  templateCard: { borderWidth: 1, borderRadius: 15, padding: 13 },
  templateName: { fontSize: 12, fontWeight: "800" },
  templateDescription: { fontSize: 10, marginTop: 4, lineHeight: 16 },
  modalAction: { marginTop: 20 },
  editorHeading: { flex: 1, paddingRight: 12 },
  editorFile: { fontSize: 10, marginTop: 4 },
  editorBody: { flex: 1, gap: 12 },
  codeInput: { flex: 1, borderWidth: 1, borderRadius: 15, padding: 14, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", fontSize: 12, lineHeight: 19, textAlign: "left" },
  saveButton: { flexShrink: 0 },
});
