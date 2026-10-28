/**
 * Display translations for the API's data-contract strings (U1).
 *
 * The backend speaks English on the wire — `practice_family`, indicator keys,
 * AEZ belts, crop groups and the 100 frozen `CSA_practices` names are a data
 * contract and never change (CLAUDE.md doctrine 4). This module translates
 * them for DISPLAY only. Every Amharic and Afaan Oromoo string here is a
 * machine draft awaiting native review (docs/i18n/TRANSLATION_STATUS.md).
 *
 * Practice names are composed from their atomic COMPONENTS: the frozen
 * `CSA_practices` string "Biochar-Inorganic Fertilizer" splits on "-" into
 * two components, each translated, then joined with a localised joiner. The
 * split rule and the alias table mirror `rag/graph/practice_components.py`
 * (a Python test asserts the two component lists stay identical).
 */
import type { Locale } from "./routing";

type Tri = Record<Locale, string>;

// ---------------------------------------------------------------- families
export const FAMILIES: Record<string, Tri> = {
  "Crop production and management": {
    en: "Crop production and management",
    am: "የሰብል ምርትና አያያዝ",
    om: "Oomisha fi bulchiinsa midhaanii",
  },
  "Livestock production and management": {
    en: "Livestock production and management",
    am: "የእንስሳት እርባታና አያያዝ",
    om: "Oomisha fi bulchiinsa horii",
  },
  "Integrated soil fertility management": {
    en: "Integrated soil fertility management",
    am: "የተቀናጀ የአፈር ለምነት አያያዝ",
    om: "Bulchiinsa gabbina biyyee walitti hidhame",
  },
  "Erosion control and water management": {
    en: "Erosion control and water management",
    am: "የአፈር መሸርሸር መከላከልና የውሃ አያያዝ",
    om: "To'annoo dhiqama biyyee fi bulchiinsa bishaanii",
  },
  "Agro-forestry and forest management": {
    en: "Agro-forestry and forest management",
    am: "አግሮ-ፎረስትሪና የደን አያያዝ",
    om: "Agroo-forestrii fi bulchiinsa bosonaa",
  },
};

/** Short family names for chips and the summary rail. */
export const FAMILIES_SHORT: Record<string, Tri> = {
  "Crop production and management": { en: "Crop production", am: "የሰብል ምርት", om: "Oomisha midhaanii" },
  "Livestock production and management": { en: "Livestock", am: "እንስሳት", om: "Horii" },
  "Integrated soil fertility management": { en: "Soil fertility", am: "የአፈር ለምነት", om: "Gabbina biyyee" },
  "Erosion control and water management": { en: "Erosion & water", am: "መሸርሸርና ውሃ", om: "Dhiqama fi bishaan" },
  "Agro-forestry and forest management": { en: "Agro-forestry", am: "አግሮ-ፎረስትሪ", om: "Agroo-forestrii" },
};

/** One-line descriptions for the challenge cards. */
export const FAMILIES_BLURB: Record<string, Tri> = {
  "Crop production and management": {
    en: "Varieties, planting, residues and in-field crop management.",
    am: "ዝርያዎች፣ ተከላ፣ የሰብል ተረፈ ምርትና የማሳ ውስጥ አያያዝ።",
    om: "Sanyiiwwan, dhaabuu, hafteewwan fi bulchiinsa midhaanii dirree keessaa.",
  },
  "Livestock production and management": {
    en: "Feed, fodder and grazing practices that fit local systems.",
    am: "ለአካባቢው ሥርዓት የሚስማሙ የመኖ፣ የግጦሽና የእንስሳት አመጋገብ ልማዶች።",
    om: "Gochaalee nyaata horii, marga fi dheedaa sirna naannootiin walsiman.",
  },
  "Integrated soil fertility management": {
    en: "Organic and mineral fertility for lasting soil health.",
    am: "ለዘላቂ የአፈር ጤና ኦርጋኒክና ማዕድናዊ ለምነት።",
    om: "Gabbina orgaanikii fi albuudaa fayyaa biyyee itti fufiinsa qabuuf.",
  },
  "Erosion control and water management": {
    en: "Bunds, mulch and harvesting that keep soil and water on the farm.",
    am: "አፈርንና ውሃን በእርሻ ላይ የሚያቆዩ እርከኖች፣ ገለባና ውሃ ማሰባሰብ።",
    om: "Daangaa, haftee fi bishaan walitti qabuu biyyee fi bishaan qonna irratti tursiisan.",
  },
  "Agro-forestry and forest management": {
    en: "Trees with crops and landscapes that buffer climate risk.",
    am: "ከሰብል ጋር ዛፎችና የአየር ንብረት አደጋን የሚቀንሱ መልክዓ ምድሮች።",
    om: "Mukkeen midhaan waliin fi lafa balaa haala qilleensaa hir'isan.",
  },
};

// --------------------------------------------------------------- indicators
/** Plain-language objective labels ("what you want"), per indicator key. */
export const INDICATORS: Record<string, Tri> = {
  yield: { en: "Increase crop yield", am: "የሰብል ምርትን መጨመር", om: "Oomisha midhaanii dabaluu" },
  "biomass yield": { en: "Increase biomass / fodder", am: "ባዮማስ / መኖን መጨመር", om: "Baayoomaasii / marga dabaluu" },
  income: { en: "Increase income", am: "ገቢን መጨመር", om: "Galii dabaluu" },
  "water use efficiency": {
    en: "Improve water-use efficiency",
    am: "የውሃ አጠቃቀም ቅልጥፍናን ማሻሻል",
    om: "Bu'a qabeessummaa itti fayyadama bishaanii fooyyessuu",
  },
  "SOM content": { en: "Improve soil organic matter", am: "የአፈር ኦርጋኒክ ቁስን ማሻሻል", om: "Qabiyyee orgaanikii biyyee fooyyessuu" },
  "soil loss": { en: "Reduce soil loss / erosion", am: "የአፈር መሸርሸርን መቀነስ", om: "Dhiqama biyyee hir'isuu" },
  runoff: { en: "Reduce runoff", am: "የውሃ ፍሳሽን መቀነስ", om: "Yaa'insa bishaanii hir'isuu" },
};

/** The bare indicator noun, for sentences like "effect on {indicator}". */
export const INDICATOR_NOUNS: Record<string, Tri> = {
  yield: { en: "yield", am: "ምርት", om: "oomisha" },
  "biomass yield": { en: "biomass yield", am: "የባዮማስ ምርት", om: "oomisha baayoomaasii" },
  income: { en: "income", am: "ገቢ", om: "galii" },
  "water use efficiency": {
    en: "water use efficiency",
    am: "የውሃ አጠቃቀም ቅልጥፍና",
    om: "bu'a qabeessummaa itti fayyadama bishaanii",
  },
  "SOM content": { en: "SOM content", am: "የአፈር ኦርጋኒክ ቁስ", om: "qabiyyee orgaanikii biyyee" },
  "soil loss": { en: "soil loss", am: "የአፈር መሸርሸር", om: "dhiqama biyyee" },
  runoff: { en: "runoff", am: "የውሃ ፍሳሽ", om: "yaa'insa bishaanii" },
};

// ---------------------------------------------------------------- AEZ belts
export const AEZ_BELTS: Record<string, Tri> = {
  "Dry Dega": { en: "Dry Dega", am: "ደረቅ ደጋ", om: "Baddaa gogaa" },
  "Dry Kolla": { en: "Dry Kolla", am: "ደረቅ ቆላ", om: "Gammoojjii gogaa" },
  "Dry Weyna Dega": { en: "Dry Weyna Dega", am: "ደረቅ ወይና ደጋ", om: "Badda-daree gogaa" },
  "Moist Berha": { en: "Moist Berha", am: "እርጥብ በረሃ", om: "Gammoojjii ho'aa jiidhaa" },
  "Moist Dega": { en: "Moist Dega", am: "እርጥብ ደጋ", om: "Baddaa jiidhaa" },
  "Moist High Dega": { en: "Moist High Dega", am: "እርጥብ ከፍተኛ ደጋ", om: "Baddaa ol'aanaa jiidhaa" },
  "Moist Kolla": { en: "Moist Kolla", am: "እርጥብ ቆላ", om: "Gammoojjii jiidhaa" },
  "Moist Weyna Dega": { en: "Moist Weyna Dega", am: "እርጥብ ወይና ደጋ", om: "Badda-daree jiidhaa" },
  "Wet Dega": { en: "Wet Dega", am: "ዝናባማ ደጋ", om: "Baddaa roobaa" },
  "Wet Kolla": { en: "Wet Kolla", am: "ዝናባማ ቆላ", om: "Gammoojjii roobaa" },
  "Wet Weyna Dega": { en: "Wet Weyna Dega", am: "ዝናባማ ወይና ደጋ", om: "Badda-daree roobaa" },
  "Wet Wurch": { en: "Wet Wurch", am: "ዝናባማ ውርጭ", om: "Baddaa qorraa roobaa" },
};

// --------------------------------------------------------------- crop groups
export const CROP_GROUPS: Record<string, Tri> = {
  Cereal: { en: "Cereal", am: "እህል", om: "Midhaan" },
  "Cereal-Legume": { en: "Cereal–legume", am: "እህል–ጥራጥሬ", om: "Midhaan–dirribaa" },
  Cropland: { en: "Cropland", am: "የሰብል መሬት", om: "Lafa qonnaa" },
  Forage: { en: "Forage", am: "መኖ", om: "Marga horii" },
  "Forest-Woody": { en: "Forest / woody", am: "ደን / እንጨታማ", om: "Bosona / muka" },
  Fruit: { en: "Fruit", am: "ፍራፍሬ", om: "Fuduraa" },
  "Grassland-Rangeland": { en: "Grassland / rangeland", am: "የሣር መሬት / ግጦሽ", om: "Lafa margaa / dheedaa" },
  Livestock: { en: "Livestock", am: "እንስሳት", om: "Horii" },
  "Mixed cropping": { en: "Mixed cropping", am: "ድብልቅ ሰብል", om: "Qonna makaa" },
  Oilseed: { en: "Oilseed", am: "የዘይት እህል", om: "Sanyii zayitaa" },
  "Perennial-Cash": { en: "Perennial / cash crop", am: "ቋሚ / የገንዘብ ሰብል", om: "Midhaan waggaa dheeraa / gatii" },
  Pulse: { en: "Pulse", am: "ጥራጥሬ", om: "Dirribaa" },
  "Root & tuber": { en: "Root & tuber", am: "ሥርና ሀረግ", om: "Hundee fi tuubarii" },
  Vegetable: { en: "Vegetable", am: "አትክልት", om: "Kuduraa" },
};

// ------------------------------------------------------------------ labels
export type ConfidenceKey = "high" | "medium" | "low";
export type TierKey = "evidence" | "guidance" | "practice";
export type SourceMode = "model" | "hybrid" | "documented";

export const CONFIDENCE: Record<ConfidenceKey, Tri> = {
  high: { en: "High confidence", am: "ከፍተኛ እምነት", om: "Amantaa olaanaa" },
  medium: { en: "Medium confidence", am: "መካከለኛ እምነት", om: "Amantaa giddugaleessaa" },
  // Honest-display rule: low is "thin evidence", never danger.
  low: { en: "Thin evidence", am: "ቀጭን ማስረጃ", om: "Ragaa qal'aa" },
};

export const CONFIDENCE_MEANING: Record<ConfidenceKey, Tri> = {
  high: {
    en: "Well supported by field trials in settings like this one.",
    am: "እንደዚህ ባሉ ሁኔታዎች በመስክ ሙከራዎች በደንብ የተደገፈ።",
    om: "Haalawwan kana fakkaatan keessatti yaaliiwwan dirreetiin sirriitti deeggarame.",
  },
  medium: {
    en: "Reasonable evidence for this objective; treat the order as the signal.",
    am: "ለዚህ ዓላማ በቂ ማስረጃ አለ፤ ቅደም ተከተሉን እንደ ምልክት ይውሰዱ።",
    om: "Kaayyoo kanaaf ragaa gahaa; tartiiba akka mallattootti fudhadhaa.",
  },
  low: {
    en: "Few field observations for this objective here — a starting point, not a forecast.",
    am: "እዚህ ለዚህ ዓላማ ጥቂት የመስክ ምልከታዎች ብቻ — መነሻ ነጥብ እንጂ ትንበያ አይደለም።",
    om: "Kaayyoo kanaaf daawwannaa dirree muraasa qofa — qabxii jalqabaa malee raaga miti.",
  },
};

export const TIERS: Record<TierKey, Tri> = {
  evidence: { en: "Field evidence", am: "የመስክ ማስረጃ", om: "Ragaa dirree" },
  guidance: { en: "Implementation guidance", am: "የአተገባበር መመሪያ", om: "Qajeelfama hojiirra oolmaa" },
  practice: { en: "Practice record", am: "የልማድ መዝገብ", om: "Galmee gochaa" },
};

/** Result-set source badge (P9 reserves hybrid / documented). */
export const SOURCE_MODES: Record<SourceMode, Tri> = {
  model: { en: "Field-trial model", am: "የመስክ ሙከራ ሞዴል", om: "Moodeela yaalii dirree" },
  hybrid: { en: "Hybrid", am: "ድብልቅ", om: "Makaa" },
  documented: { en: "Documented practice", am: "የተመዘገበ ልማድ", om: "Gocha galmaa'e" },
};

export const SOURCE_MODES_TOOLTIP: Record<SourceMode, Tri> = {
  model: {
    en: "Ranked by a model trained on paired field trials; every number comes from that model.",
    am: "በተጣመሩ የመስክ ሙከራዎች በሰለጠነ ሞዴል ደረጃ የተሰጠው፤ እያንዳንዱ ቁጥር ከዚያ ሞዴል ነው።",
    om: "Moodeela yaaliiwwan dirree cimdii irratti leenji'een sadarkeeffame; lakkoofsi hundi moodeela sana irraa dhufa.",
  },
  hybrid: {
    en: "Field-trial evidence is thin here, so documented practices from similar contexts are shown alongside — clearly labelled, never with invented numbers.",
    am: "እዚህ የመስክ ሙከራ ማስረጃ ቀጭን ነው፣ ስለዚህ ከተመሳሳይ አውዶች የተመዘገቡ ልማዶች ጎን ለጎን ይታያሉ — በግልጽ ተለይተው፣ ያለ ፈጠራ ቁጥር።",
    om: "Ragaan yaalii dirree asitti qal'aa dha, kanaaf gochaaleen galmaa'an haalawwan walfakkaatan irraa cinaatti agarsiifamu — ifatti mallatteeffamanii, lakkoofsa uumameen miti.",
  },
  documented: {
    en: "No field-trial evidence for this request; these are documented practices from similar contexts with their provenance, and no effect numbers.",
    am: "ለዚህ ጥያቄ የመስክ ሙከራ ማስረጃ የለም፤ እነዚህ ከተመሳሳይ አውዶች የተመዘገቡ ልማዶች ከምንጫቸው ጋር ናቸው፣ ያለ የውጤት ቁጥር።",
    om: "Gaaffii kanaaf ragaan yaalii dirree hin jiru; kunneen gochaalee galmaa'an haalawwan walfakkaatan irraa madda isaanii waliin, lakkoofsa bu'aa malee.",
  },
};

// ------------------------------------------------- practice components (44)
/** Frozen label fragments that contain the split character themselves. */
const PROTECTED_COMPONENTS = ["In-situ water harvesting"];

/** raw component (lower-cased) → canonical component label. Mirrors
 * `rag/graph/practice_components.py::ALIASES` exactly. */
export const COMPONENT_ALIASES: Record<string, string> = {
  "agroforestry fallow": "Agroforestry Fallow",
  "agroforestry pruning": "Agroforestry Pruning",
  alleycropping: "Alleycropping",
  biochar: "Biochar",
  "crop residue incorporation": "Crop Residue Incorporation",
  "crop rotation": "Crop Rotation",
  exclosure: "Exclosure",
  "feed addition": "Feed Addition",
  "feed processing": "Feed Processing",
  "feed substitution": "Feed Substitution",
  "improved fallow": "Improved Fallow",
  "improved varieties": "Improved Varieties",
  "inorganic fertilizer": "Inorganic Fertilizer",
  "inorganic fertilizer reduction": "Inorganic Fertilizer Reduction",
  intercropping: "Intercropping",
  "intercropping or rotation": "Intercropping or Rotation",
  mulch: "Mulch",
  "multistrata agroforestry": "Multistrata Agroforestry",
  "organic fertilizer": "Organic Fertilizer",
  "other agroforestry": "Other Agroforestry",
  parklands: "Parklands",
  "pasture management": "Pasture Management",
  "reduced tillage": "Reduced Tillage",
  "supplemental irrigation": "Supplemental Irrigation",
  "water harvesting": "Water Harvesting",
  "ph control": "pH Control",
  "deficit irrigation": "Deficit Irrigation",
  "animal feed management": "Animal Feed Management",
  "biological swc practices": "Biological SWC Practices",
  "conservation tillage": "Conservation Tillage",
  "drip irrigation": "Drip Irrigation",
  "furrow irrigation": "Furrow Irrigation",
  "grazing management": "Grazing Management",
  "in-situ water harvesting": "In-situ Water Harvesting",
  isfm: "ISFM",
  iwm: "IWM",
  "physical swc measures": "Physical SWC Measures",
  "physical + biological swc practices": "Physical + Biological SWC Practices",
  weeding: "Weeding",
  "drought tolerrant crops": "Drought Tolerant Crops",
  "organic amedements": "Organic Amendments",
  "agronomic/biological swcp": "Agronomic/Biological SWC Practices",
  "furrow irrigation_alternate": "Alternate Furrow Irrigation",
  "overhead irrigation with mulching": "Overhead Irrigation with Mulching",
};

/** Canonical component → display name in the three languages. */
export const COMPONENTS: Record<string, Tri> = {
  "Agroforestry Fallow": { en: "Agroforestry fallow", am: "የአግሮ-ፎረስትሪ ጦም መሬት", om: "Lafa boqonnaa agroo-forestrii" },
  "Agroforestry Pruning": { en: "Agroforestry pruning", am: "የአግሮ-ፎረስትሪ መግረዝ", om: "Muruu agroo-forestrii" },
  "Agronomic/Biological SWC Practices": {
    en: "Agronomic / biological soil & water conservation",
    am: "አግሮኖሚያዊ / ባዮሎጂያዊ የአፈርና ውሃ ጥበቃ",
    om: "Eegumsa biyyee fi bishaanii agronomii / baayoloojii",
  },
  Alleycropping: { en: "Alley cropping", am: "የመስመር ሰብል (አሊ ክሮፒንግ)", om: "Qonna daandii gidduu (alley cropping)" },
  "Alternate Furrow Irrigation": { en: "Alternate-furrow irrigation", am: "ተለዋጭ የቦይ መስኖ", om: "Jallisii boo'oo wal-jijjiiraa" },
  "Animal Feed Management": { en: "Animal feed management", am: "የእንስሳት መኖ አያያዝ", om: "Bulchiinsa nyaata horii" },
  Biochar: { en: "Biochar", am: "ባዮቻር", om: "Baayoochaarii" },
  "Biological SWC Practices": {
    en: "Biological soil & water conservation",
    am: "ባዮሎጂያዊ የአፈርና ውሃ ጥበቃ",
    om: "Eegumsa biyyee fi bishaanii baayoloojii",
  },
  "Conservation Tillage": { en: "Conservation tillage", am: "ጥበቃዊ እርሻ", om: "Qotiinsa eegumsaa" },
  "Crop Residue Incorporation": { en: "Crop residue incorporation", am: "የሰብል ተረፈ ምርት ማካተት", om: "Haftee midhaanii biyyee keessa galchuu" },
  "Crop Rotation": { en: "Crop rotation", am: "የሰብል ፈረቃ", om: "Jijjiirraa midhaanii" },
  "Deficit Irrigation": { en: "Deficit irrigation", am: "የተቀነሰ መስኖ", om: "Jallisii hir'ataa" },
  "Drip Irrigation": { en: "Drip irrigation", am: "የጠብታ መስኖ", om: "Jallisii copha" },
  "Drought Tolerant Crops": { en: "Drought-tolerant crops", am: "ድርቅን የሚቋቋሙ ሰብሎች", om: "Midhaan hongee dandamatu" },
  Exclosure: { en: "Area exclosure", am: "ክልል ማድረግ (ከግጦሽ መከልከል)", om: "Lafa daangeffame (kutaa eegumsaa)" },
  "Feed Addition": { en: "Feed addition", am: "መኖ መጨመር", om: "Nyaata horii dabaluu" },
  "Feed Processing": { en: "Feed processing", am: "መኖ ማዘጋጀት", om: "Qophii nyaata horii" },
  "Feed Substitution": { en: "Feed substitution", am: "መኖ መተካት", om: "Bakka buusuu nyaata horii" },
  "Furrow Irrigation": { en: "Furrow irrigation", am: "የቦይ መስኖ", om: "Jallisii boo'oo" },
  "Grazing Management": { en: "Grazing management", am: "የግጦሽ አያያዝ", om: "Bulchiinsa dheedaa" },
  ISFM: {
    en: "Integrated soil fertility management",
    am: "የተቀናጀ የአፈር ለምነት አያያዝ",
    om: "Bulchiinsa gabbina biyyee walitti hidhame",
  },
  IWM: {
    en: "Integrated watershed management",
    am: "የተቀናጀ የተፋሰስ አያያዝ",
    om: "Bulchiinsa sulula bishaanii walitti hidhame",
  },
  "Improved Fallow": { en: "Improved fallow", am: "የተሻሻለ ጦም መሬት", om: "Lafa boqonnaa fooyya'e" },
  "Improved Varieties": { en: "Improved varieties", am: "የተሻሻሉ ዝርያዎች", om: "Sanyiiwwan fooyya'an" },
  "In-situ Water Harvesting": { en: "In-field water harvesting", am: "በማሳ ውስጥ ውሃ ማሰባሰብ", om: "Bishaan dirree keessatti walitti qabuu" },
  "Inorganic Fertilizer": { en: "Inorganic fertilizer", am: "ኬሚካል ማዳበሪያ", om: "Xaa'oo keemikaalaa" },
  "Inorganic Fertilizer Reduction": { en: "Reduced inorganic fertilizer", am: "የተቀነሰ ኬሚካል ማዳበሪያ", om: "Xaa'oo keemikaalaa hir'ifame" },
  Intercropping: { en: "Intercropping", am: "ድብልቅ ሰብል", om: "Qonna makaa" },
  "Intercropping or Rotation": { en: "Intercropping or rotation", am: "ድብልቅ ሰብል ወይም ፈረቃ", om: "Qonna makaa ykn jijjiirraa" },
  Mulch: { en: "Mulch", am: "ገለባ ሽፋን (ማልች)", om: "Haftee uwwisuu (malchii)" },
  "Multistrata Agroforestry": { en: "Multi-storey agroforestry", am: "ባለ ብዙ ደረጃ አግሮ-ፎረስትሪ", om: "Agroo-forestrii sadarkaa baay'ee" },
  "Organic Amendments": { en: "Organic amendments", am: "ኦርጋኒክ ማሻሻያዎች", om: "Fooyya'iinsa orgaanikii" },
  "Organic Fertilizer": { en: "Organic fertilizer", am: "ኦርጋኒክ ማዳበሪያ", om: "Xaa'oo orgaanikii" },
  "Other Agroforestry": { en: "Other agroforestry", am: "ሌላ አግሮ-ፎረስትሪ", om: "Agroo-forestrii biroo" },
  "Overhead Irrigation with Mulching": {
    en: "Overhead irrigation with mulching",
    am: "ከላይ የሚረጭ መስኖ ከገለባ ሽፋን ጋር",
    om: "Jallisii gubbaa haftee uwwisuu waliin",
  },
  Parklands: { en: "Parkland trees", am: "የፓርክላንድ ዛፎች", om: "Mukkeen paarkilaandii" },
  "Pasture Management": { en: "Pasture management", am: "የግጦሽ መሬት አያያዝ", om: "Bulchiinsa lafa margaa" },
  "Physical + Biological SWC Practices": {
    en: "Physical + biological soil & water conservation",
    am: "አካላዊ + ባዮሎጂያዊ የአፈርና ውሃ ጥበቃ",
    om: "Eegumsa biyyee fi bishaanii fiizikaalaa + baayoloojii",
  },
  "Physical SWC Measures": {
    en: "Physical soil & water conservation",
    am: "አካላዊ የአፈርና ውሃ ጥበቃ",
    om: "Eegumsa biyyee fi bishaanii fiizikaalaa",
  },
  "Reduced Tillage": { en: "Reduced tillage", am: "የተቀነሰ እርሻ", om: "Qotiinsa hir'ataa" },
  "Supplemental Irrigation": { en: "Supplemental irrigation", am: "ተጨማሪ መስኖ", om: "Jallisii dabalataa" },
  "Water Harvesting": { en: "Water harvesting", am: "ውሃ ማሰባሰብ", om: "Bishaan walitti qabuu" },
  Weeding: { en: "Weeding", am: "አረም ማረም", om: "Aramaa" },
  "pH Control": { en: "Soil pH control (liming)", am: "የአፈር ፒኤች ቁጥጥር (ኖራ)", om: "To'annoo pH biyyee (noora)" },
};

const JOINER: Tri = { en: " + ", am: " + ", om: " + " };

function clean(text: string): string {
  return text.trim().replace(/\s+/g, " ");
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Split a frozen practice label on "-", protecting hyphenated names. */
export function splitPractice(label: string): string[] {
  let text = clean(label);
  const placeholders: Array<[string, string]> = [];
  PROTECTED_COMPONENTS.forEach((protectedName, i) => {
    const token = ` ${i} `;
    const re = new RegExp(escapeRegExp(protectedName), "ig");
    if (re.test(text)) {
      text = text.replace(re, token);
      placeholders.push([token, protectedName]);
    }
  });
  return text
    .split("-")
    .map((part) => {
      let piece = clean(part);
      for (const [token, name] of placeholders) {
        piece = piece.split(token).join(name);
      }
      return piece;
    })
    .filter(Boolean);
}

/** Raw component string → canonical component (unknown passes through). */
export function canonicalComponent(raw: string): string {
  return COMPONENT_ALIASES[clean(raw).toLowerCase()] ?? clean(raw);
}

/** Canonical components of a frozen practice label, in order, de-duplicated. */
export function practiceComponents(label: string): string[] {
  const seen: string[] = [];
  for (const raw of splitPractice(label)) {
    const c = canonicalComponent(raw);
    if (!seen.includes(c)) seen.push(c);
  }
  return seen;
}

/** Localised display name of a frozen `CSA_practices` string. */
export function practiceName(label: string, locale: Locale): string {
  const parts = practiceComponents(label).map((c) => {
    const entry = COMPONENTS[c];
    if (!entry) return c; // unknown component: show the API's own text
    return entry[locale] ?? entry.en;
  });
  return parts.join(JOINER[locale]);
}

function lookup(table: Record<string, Tri>, key: string | null | undefined, locale: Locale): string {
  if (!key) return "";
  const entry = table[key];
  if (!entry) return key; // unknown data value: show as the API sent it
  return entry[locale] ?? entry.en;
}

export const familyName = (key: string | null | undefined, locale: Locale) => lookup(FAMILIES, key, locale);
export const familyShort = (key: string | null | undefined, locale: Locale) => lookup(FAMILIES_SHORT, key, locale);
export const familyBlurb = (key: string | null | undefined, locale: Locale) => lookup(FAMILIES_BLURB, key, locale);
export const indicatorLabel = (key: string | null | undefined, locale: Locale) => lookup(INDICATORS, key, locale);
export const indicatorNoun = (key: string | null | undefined, locale: Locale) => lookup(INDICATOR_NOUNS, key, locale);
export const aezName = (key: string | null | undefined, locale: Locale) => lookup(AEZ_BELTS, key, locale);
export const cropGroupName = (key: string | null | undefined, locale: Locale) => lookup(CROP_GROUPS, key, locale);
export const confidenceLabel = (key: ConfidenceKey, locale: Locale) => CONFIDENCE[key][locale];
export const confidenceMeaning = (key: ConfidenceKey, locale: Locale) => CONFIDENCE_MEANING[key][locale];
export const tierLabel = (key: TierKey, locale: Locale) => TIERS[key][locale];
export const sourceModeLabel = (key: SourceMode, locale: Locale) => SOURCE_MODES[key][locale];
export const sourceModeTooltip = (key: SourceMode, locale: Locale) => SOURCE_MODES_TOOLTIP[key][locale];

/**
 * Locale-aware effect sentence built ONLY from API numbers (pct_change,
 * goal_direction, indicator). For `en` it reproduces recommend.py's own
 * sentence ("~42% reduction in soil loss", "~12% increase in yield"); for
 * `am`/`om` it is the translation of that same sentence — the magnitude is
 * never recomputed, only rounded the way the engine rounds it. `goal_direction`
 * keeps the API values `reduce` / `increase`; only the wording differs.
 */
export function effectSentence(
  pctChange: number,
  goalDirection: string,
  indicatorKey: string,
  locale: Locale
): string {
  const magnitude = Math.abs(Math.round(pctChange));
  const reduce = goalDirection === "reduce";
  if (locale === "am") {
    const noun = indicatorNoun(indicatorKey, "am");
    return reduce ? `በ${noun} ~${magnitude}% ቅናሽ` : `በ${noun} ~${magnitude}% ጭማሪ`;
  }
  if (locale === "om") {
    const noun = indicatorNoun(indicatorKey, "om");
    return reduce ? `${noun} ~${magnitude}% hir'isuu` : `${noun} ~${magnitude}% dabaluu`;
  }
  return `~${magnitude}% ${reduce ? "reduction" : "increase"} in ${indicatorKey}`;
}
