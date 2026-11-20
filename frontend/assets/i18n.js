/* InsaneVoice i18n — EN/বাংলা toggle. Partial coverage by design:
   core UI strings translate; long helper copy stays English. */

const DICT = {
  bn: {
    nav_overview: "সংক্ষিপ্ত", nav_create: "তৈরি করুন", nav_voices: "ভয়েস",
    nav_tools: "টুলস", nav_system: "সিস্টেম",
    title_dashboard: "ড্যাশবোর্ড", title_gallery: "গ্যালারি", title_studio: "স্টুডিও",
    title_director: "ডিরেক্টর স্টুডিও", title_batch: "ব্যাচ স্টুডিও",
    title_cartoon: "কার্টুন স্টুডিও", title_agent: "এজেন্ট স্টুডিও",
    title_dna: "ভয়েস ডিএনএ", title_recorder: "রেকর্ডার", title_library: "ভয়েস লাইব্রেরি",
    title_design: "ভয়েস ডিজাইন", title_changer: "ভয়েস চেঞ্জার",
    title_isolate: "ভয়েস আইসোলেটর", title_transcribe: "ট্রান্সক্রাইব",
    title_dubbing: "ডাবিং স্টুডিও", title_dubhub: "ডাবহাব",
    title_connections: "কানেকশন", title_admin: "অ্যাডমিন", title_history: "হিস্টোরি",
    title_settings: "সেটিংস", title_help: "সহায়িকা",
    dash_eyebrow: "InsaneVoice · লোকাল ক্লোনিং স্টুডিও",
    dash_sub: "আপনার ভয়েস কথা বলতে প্রস্তুত — সব এই মেশিনেই, অফলাইনে, ফ্রি।",
    btn_studio: "স্টুডিও খুলুন", btn_cartoon: "কার্টুন বানান", btn_clone: "ভয়েস ক্লোন",
    stat_voices: "লাইব্রেরিতে ভয়েস", stat_gens: "জেনারেশন", stat_audio: "অডিও রেন্ডার",
    stat_engine: "ইঞ্জিন · CPU",
    demos_h: "আপনার ডেমো।", demos_sub: "এই মেশিন থেকে নতুন রেন্ডার।",
    voices_h: "আপনার ভয়েস।", voices_sub: "ক্লোন হয়ে প্রস্তুত।",
    all_history: "সব হিস্টোরি", open_library: "লাইব্রেরি খুলুন",
    empty_demos_h: "এখনো কিছু রেন্ডার হয়নি", empty_demos_p: "ভয়েস বেছে নিয়ে লিখুন — আপনার প্রথম ডেমো এখানেই থাকবে।",
    btn_first_words: "প্রথম কথা লিখুন",
    empty_voices_h: "এখনো কোনো ভয়েস নেই", empty_voices_p: "১০ সেকেন্ডের রেকর্ডিং-ই যথেষ্ট।",
    btn_clone_voice: "ভয়েস ক্লোন করুন",
    ct_sub: "গল্পের idea লিখুন — সম্পূর্ণ কার্টুন (স্ক্রিপ্ট, দৃশ্য, কণ্ঠ, সংগীত) তৈরি হয়ে যাবে। দিনে একটা ফ্রি।",
    ct_idea_label: "গল্পের idea (ঐচ্ছিক — খালি রাখলে প্রতিবার নতুন গল্প)",
    ct_mode_motion: "✦ মোশন কার্টুন — অ্যানিমেটেড দৃশ্য", ct_mode_storybook: "▢ স্টোরিবুক — ছবি",
    ct_lang: "🌐 English", ct_go: "কার্টুন বানান",
    ct_today: "আজ:", ct_left: "বাকি", ct_used: "শেষ",
    ct_reroll: "দৃশ্য re-roll", ct_ep2: "পর্ব ২ (একই cast)",
    ct_download: "ডাউনলোড MP4", ct_shorts: "Shorts 9:16", ct_smooth: "Smooth 60fps", ct_thumb: "Thumbnail",
    gl_sub: "এই ইঞ্জিনে বানানো প্রতিটা কার্টুন — লিংক share করে সবাই দেখতে পারবে।",
    gl_empty_h: "এখনো কোনো কার্টুন নেই", gl_empty_p: "আপনার প্রথম কার্টুন এখানে দেখা যাবে।",
    gl_watch: "দেখুন", gl_share: "শেয়ার",
    lang_toggle_bn: "বাংলা", lang_toggle_en: "EN",
  },
  en: {},
};

export function lang() {
  try { return localStorage.getItem("ivLang") || "en"; } catch { return "en"; }
}

export function t(key) {
  const l = lang();
  if (l === "en") return null;                    // English = source strings
  return (DICT[l] && DICT[l][key]) || null;
}

export function toggle() {
  try { localStorage.setItem("ivLang", lang() === "bn" ? "en" : "bn"); } catch { /* */ }
  location.reload();
}
