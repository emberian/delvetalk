/- Tongues: the languages the town answers in (docs/VOICE.md "Tongues"). A resident's words reach hob in any
   language; a reply's paint and telling, and hob's own lines, are in the language the resident spoke: the one
   their avatar states (`delvetalk me set / tongue: ja`), else the one their words are written in (`detect`),
   else English. A paint is checked in its language by that language's table (`Tongue`): the words a clause
   reads, its numerals, the words for each field and unit; a language with no table here is not painted (the
   exact card stands) and hob speaks English in it. Cards are data: the exact card is never translated, nor is
   a resident's line, an id, a handle or a spell. -/
import Delvetalk.Host.Store

namespace Delvetalk.Host.Tongue
open Delvetalk.Host
open Delvetalk.Theory.ObjectiveBendDemandData (Data)

/-! ## Scripts and numerals -/

/-- What a character is written in, as far as the town reads it. -/
inductive Script where
  | latin | cyrillic | arabic | kana | han | other
  deriving BEq

def scriptOf (c : Char) : Script :=
  let n := c.toNat
  if (0x41 ≤ n && n ≤ 0x5A) || (0x61 ≤ n && n ≤ 0x7A) || (0xC0 ≤ n && n ≤ 0x24F && n != 0xD7 && n != 0xF7) then .latin
  else if 0x400 ≤ n && n ≤ 0x52F then .cyrillic
  else if (0x620 ≤ n && n ≤ 0x64A) || (0x66E ≤ n && n ≤ 0x6D3) || (0xFB50 ≤ n && n ≤ 0xFDFF) || (0xFE70 ≤ n && n ≤ 0xFEFF) then .arabic
  else if (0x3041 ≤ n && n ≤ 0x309F) || (0x30A0 ≤ n && n ≤ 0x30FF && n != 0x30FB) || (0x31F0 ≤ n && n ≤ 0x31FF) || (0xFF66 ≤ n && n ≤ 0xFF9F) then .kana
  else if (0x4E00 ≤ n && n ≤ 0x9FFF) || (0x3400 ≤ n && n ≤ 0x4DBF) || (0xF900 ≤ n && n ≤ 0xFAFF) || n == 0x3005 || n == 0x3007 then .han
  else .other

/-- A script written without spaces between words: kana and han. -/
def unspacedChar (c : Char) : Bool := let s := scriptOf c; s == .kana || s == .han

/-- The CJK and full-width marks: each stands alone between words, as a space would. -/
def cjkMark (c : Char) : Bool := "「」『』（）【】《》〈〉〔〕［］｛｝、。，．！？：；・…‥～".toList.contains c

/-- A digit in any numerals the town reads: ASCII, full-width, Arabic-Indic and extended Arabic-Indic. -/
def digitOf (c : Char) : Option Nat :=
  let n := c.toNat
  if 0x30 ≤ n && n ≤ 0x39 then some (n - 0x30)
  else if 0xFF10 ≤ n && n ≤ 0xFF19 then some (n - 0xFF10)
  else if 0x660 ≤ n && n ≤ 0x669 then some (n - 0x660)
  else if 0x6F0 ≤ n && n ≤ 0x6F9 then some (n - 0x6F0)
  else none

/-- A text with every digit written as an ASCII one. -/
def asciiDigits (t : String) : String :=
  String.ofList (t.toList.map fun c => match digitOf c with
    | some d => Char.ofNat (0x30 + d)
    | none => c)

/-- A han numeral's digit (〇 零 一 二 两 兩 三 … 九). -/
def hanDigit (c : Char) : Option Nat :=
  match c with
  | '〇' | '零' => some 0 | '一' => some 1 | '二' | '两' | '兩' => some 2 | '三' => some 3 | '四' => some 4
  | '五' => some 5 | '六' => some 6 | '七' => some 7 | '八' => some 8 | '九' => some 9 | _ => none

/-- A han numeral's place (十 百 千 万 萬). -/
def hanPlace (c : Char) : Option Nat :=
  match c with
  | '十' => some 10 | '百' => some 100 | '千' => some 1000 | '万' | '萬' => some 10000 | _ => none

def numeralChar (c : Char) : Bool := (digitOf c).isSome || (hanDigit c).isSome || (hanPlace c).isSome

/-- The value of a run of numerals: digits (`７`, `٧`, `二〇二六`) read place by place, han places (`二十一`) summed. -/
def numeralValue (cs : List Char) : Nat := Id.run do
  let mut total := 0
  let mut group := 0
  let mut cur := 0
  let mut digits := false
  for c in cs do
    match digitOf c <|> hanDigit c with
    | some d =>
      cur := if digits then cur * 10 + d else d
      digits := true
    | none =>
      digits := false
      match hanPlace c with
      | some 10000 =>
        total := (total + group + cur) * 10000
        group := 0
        cur := 0
      | some p =>
        group := group + (if cur == 0 then 1 else cur) * p
        cur := 0
      | none => pure ()
  return total + group + cur

#guard numeralValue "七".toList == 7
#guard numeralValue "二十一".toList == 21
#guard numeralValue "十二".toList == 12
#guard numeralValue "１４４０".toList == 1440
#guard numeralValue "٤".toList == 4
#guard numeralValue "三百".toList == 300

/-! ## Folding words -/

/-- Lower case for the scripts the town reads: ASCII, Latin-1 and Latin Extended-A capitals, Cyrillic. -/
def lowerChar (c : Char) : Char :=
  let n := c.toNat
  if (0x41 ≤ n && n ≤ 0x5A) || (0xC0 ≤ n && n ≤ 0xDE && n != 0xD7) || (0x410 ≤ n && n ≤ 0x42F) then Char.ofNat (n + 0x20)
  else if 0x400 ≤ n && n ≤ 0x40F then Char.ofNat (n + 0x50)
  else if 0x100 ≤ n && n ≤ 0x17F && n % 2 == 0 then Char.ofNat (n + 1)
  else c

def lower (t : String) : String := String.ofList (t.toList.map lowerChar)

/-- A word as compared: lower case, Spanish accents and Russian ё plain, Arabic vowel marks and tatweel dropped,
    its alefs one alef, its alif maqsura a ya and its ta marbuta a ha. -/
def fold (t : String) : String :=
  String.ofList ((t.toList.map lowerChar).filterMap fun c =>
    let n := c.toNat
    if (0x64B ≤ n && n ≤ 0x652) || n == 0x670 || n == 0x640 then none
    else some (match c with
      | 'á' => 'a' | 'é' => 'e' | 'í' => 'i' | 'ó' => 'o' | 'ú' | 'ü' => 'u' | 'ё' => 'е'
      | 'أ' | 'إ' | 'آ' | 'ٱ' => 'ا' | 'ى' => 'ي' | 'ة' => 'ه' | c => c))

def endsIn (cs : List Char) (suffix : String) : Bool :=
  cs.length > suffix.length && cs.drop (cs.length - suffix.length) == suffix.toList

/-- A unit word reduced so its English forms meet: rains, rained, raining → rain; minutes → minut. -/
def englishStem (w : String) : String :=
  let cs := (lower w).toList
  let cs := if cs.length > 3 && cs.getLast? == some 's' && cs.reverse[1]? != some 's' then cs.dropLast else cs
  let ends := fun (suffix : String) => cs.length > suffix.length + 2 && cs.drop (cs.length - suffix.length) == suffix.toList
  String.ofList <| if ends "ing" then cs.take (cs.length - 3) else if ends "ed" then cs.take (cs.length - 2)
    else if ends "e" then cs.dropLast else cs

/-- A word with the first of `endings` it ends in dropped, `keep` characters at least left. -/
def stripEnding (endings : List String) (keep : Nat) (w : String) : String :=
  let cs := (fold w).toList
  match endings.find? fun e => endsIn cs e && cs.length - e.length ≥ keep with
  | some e => String.ofList (cs.take (cs.length - e.length))
  | none => String.ofList cs

/-- A Spanish word without its plural s and its final e, so visitante and visitantes, clase and clases, carácter and
    caracteres meet. -/
def spanishStem (w : String) : String :=
  let cs := (stripEnding ["s"] 3 w).toList
  String.ofList (if cs.length > 4 && cs.getLast? == some 'e' then cs.dropLast else cs)

#guard spanishStem "visitantes" == spanishStem "visitante"
#guard spanishStem "clases" == spanishStem "clase"
#guard spanishStem (fold "caracteres") == spanishStem (fold "carácter")

def russianStem : String → String :=
  stripEnding ["ями", "ами", "его", "ого", "ему", "ому", "ыми", "ими", "иях", "ах", "ях", "ей", "ой", "ий", "ый", "ая", "яя", "ое",
    "ее", "ые", "ие", "ов", "ев", "ам", "ям", "ом", "ем", "ую", "юю", "а", "я", "ы", "и", "у", "ю", "о", "е", "ь", "й"] 3

/-- An Arabic word without its clitic prefix (و, ف, ب, ل, the article) and its plural or feminine ending. -/
def arabicStem (w : String) : String :=
  let cs := (fold w).toList
  let pre := ["وال", "فال", "بال", "لل", "ال", "و", "ف", "ب", "ل"].find? fun p =>
    cs.length > p.length + 1 && cs.take p.length == p.toList
  let cs := match pre with | some p => cs.drop p.length | none => cs
  stripEnding ["ات", "ان", "ين", "ون", "ها", "ه", "ة"] 2 (String.ofList cs)

/-! ## A tongue -/

/-- A language the town paints, checks and speaks hob's lines in. `spaced`: its words stand between spaces
    (English, Spanish, Russian, Arabic), else a phrase is read as characters (Japanese, Chinese). The lists are
    the words each clause of `Enchant.verify` reads (a spaced tongue's by word, folded; an unspaced one's as
    substrings). `lexicon` names each stroke field and unit, keyed by its English word, by the words this tongue
    says it with, its first the one the painter is given; a field's words are what a negation stands near. -/
structure Tongue where
  code : String
  /-- Its own name, and its English one. -/
  name : String
  english : String
  spaced : Bool := true
  /-- The quotation marks a paint in it writes, as the contract names them. -/
  quotes : String
  forbidden : List String
  secondPerson : List String
  negators : List String
  wanting : List String
  /-- Filler a want may be of: someone, something, a hand. -/
  vague : List String
  /-- Words that are never a unit or a want's object. -/
  small : List String := []
  /-- The words that cut a phrase, beside commas, colons and dashes. -/
  conjunctions : List String := []
  /-- Number words (folded) and what they count; ordinals the nth. -/
  cardinals : List (String × Nat) := []
  ordinals : List (String × Nat) := []
  /-- What may follow a digit to make it an ordinal (`7th`, `7.ª`, `7-й`). -/
  ordinalMarks : List String := []
  /-- Number words left free: one, first, once are as often not counts. -/
  free : List String := []
  stem : String → String := fold
  lexicon : List (String × List String)
  /-- The words that name the maker, the coiner and the town (the world's own principal, `the town` in its clauses) as
      the one whose words a quotation is. -/
  roles : List (String × List String) := []
  /-- hob's lines (`say`), and the frames the host sets above a telling. -/
  hob : List (String × String)

/-- Does word `w` say `form`? By stem in a spaced tongue (English's is the lower-cased word itself), as a
    substring in an unspaced one. -/
def Tongue.matches (t : Tongue) (w form : String) : Bool :=
  if t.spaced then t.stem w == t.stem form else !form.isEmpty && ((fold w).splitOn (fold form)).length > 1

/-- How a want's words and a paint's are met: English by `englishStem` (rains, rained → rain), else the tongue's stem. -/
def Tongue.wantStem (t : Tongue) (w : String) : String := if t.code == "en" then englishStem w else t.stem w

/-- The number a spaced tongue's token says, and whether as an ordinal: digits in any numerals (`7`, `7th`, `٧`,
    `7.ª`), else a number word, an Arabic one with its clitic prefix dropped. -/
def Tongue.wordNumber (t : Tongue) (token : String) : Option (Nat × Bool) :=
  let w := fold (asciiDigits token)
  if w.any Char.isDigit then
    let cs := w.toList
    let ds := cs.takeWhile Char.isDigit
    let suffix := String.ofList (cs.drop ds.length)
    if ds.isEmpty || (!suffix.isEmpty && !t.ordinalMarks.contains suffix) then none
    else (String.ofList ds).toNat?.map (·, !suffix.isEmpty)
  else
    let look := fun (x : String) => match t.cardinals.lookup x, t.ordinals.lookup x with
      | some n, _ => some (n, false)
      | _, some n => some (n, true)
      | none, none => none
    (look w).orElse fun _ => if t.code != "ar" then none else
      (["و", "ف", "ب", "ل"].find? (w.startsWith ·)).bind fun p => look (String.ofList (w.toList.drop p.length))

/-! ### English -/

def englishCardinals : List (String × Nat) :=
  [("zero", 0), ("two", 2), ("three", 3), ("four", 4), ("five", 5), ("six", 6), ("seven", 7), ("eight", 8), ("nine", 9),
   ("ten", 10), ("eleven", 11), ("twelve", 12), ("thirteen", 13), ("fourteen", 14), ("fifteen", 15), ("sixteen", 16),
   ("seventeen", 17), ("eighteen", 18), ("nineteen", 19), ("twenty", 20), ("thirty", 30), ("forty", 40), ("fifty", 50),
   ("sixty", 60), ("seventy", 70), ("eighty", 80), ("ninety", 90), ("hundred", 100), ("thousand", 1000),
   ("twice", 2), ("thrice", 3), ("dozen", 12), ("couple", 2), ("pair", 2)]

def englishOrdinals : List (String × Nat) :=
  [("second", 2), ("third", 3), ("fourth", 4), ("fifth", 5), ("sixth", 6), ("seventh", 7), ("eighth", 8), ("ninth", 9),
   ("tenth", 10), ("eleventh", 11), ("twelfth", 12), ("thirteenth", 13), ("fourteenth", 14), ("fifteenth", 15),
   ("sixteenth", 16), ("seventeenth", 17), ("eighteenth", 18), ("nineteenth", 19), ("twentieth", 20), ("thirtieth", 30),
   ("fortieth", 40), ("fiftieth", 50), ("hundredth", 100)]

/-- The ones a compound ("forty-one", "twenty-first") ends in. -/
def englishOnes : List (String × Nat) := [("one", 1), ("first", 1)] ++ englishCardinals.take 9 ++ englishOrdinals.take 8

/-- An English token's number: a spaced tongue's, or a compound ("forty-one", "twenty-first"). -/
def englishNumber (t : Tongue) (token : String) : Option (Nat × Bool) :=
  (t.wordNumber token).orElse fun _ =>
    match (lower token).splitOn "-" with
    | [a, b] => match englishCardinals.lookup a, englishOnes.lookup b with
      | some x, some y => if x ≥ 20 then some (x + y, englishOrdinals.any (·.1 == b) || b == "first") else none
      | _, _ => none
    | _ => none

def english : Tongue :=
  { code := "en", name := "English", english := "English", quotes := "“ ”",
    forbidden := ["i", "i'm", "i've", "i'll", "i'd", "me", "my", "myself", "thanks", "thank", "sorry", "welcome", "please"],
    secondPerson := ["you", "your", "yours", "you're", "you've", "you'll", "you'd", "yourself", "yourselves", "y'all"],
    negators := ["no", "not", "never", "nothing", "none", "nobody", "nowhere", "neither", "nor", "cannot"],
    wanting := ["want", "wants", "wanting", "needs", "need", "lacks"],
    vague := ["someone", "somebody", "something", "anyone", "anything", "hand", "hands", "what", "who", "whom", "one",
              "more", "some", "own", "here", "there", "now", "again", "yet"],
    small := ["a", "an", "the", "of", "to", "at", "in", "on", "by", "for", "with", "from", "and", "or", "its", "it", "than",
              "is", "are", "has", "have", "this", "that", "as", "into", "over", "under", "every", "each", "all", "more", "fewer", "less",
              "within", "while", "about", "after", "before", "since", "until", "near", "beside", "upon", "onto", "only",
              "just", "still", "yet", "so", "far", "times"],
    conjunctions := ["and", "but", "while", "yet"],
    cardinals := englishCardinals, ordinals := englishOrdinals, ordinalMarks := ["st", "nd", "rd", "th"],
    free := ["one", "first", "once"], stem := lower,
    lexicon :=
      [("keeper", ["keeper", "keepers", "keep", "keeps", "kept", "keeping"]),
       ("maker", ["maker", "makers", "made", "make", "makes", "making"]),
       ("owner", ["owner", "owners", "owned", "owns"]),
       ("rung", ["rung", "rang", "ring", "rings", "ringing"]),
       ("tended", ["tended", "tend", "tends", "tending"]),
       ("lines", ["line", "lines", "written", "wrote"]),
       ("doors", ["door", "doors"]),
       ("wants", ["want", "wants", "wanting", "wanted", "lacks", "needs"]),
       ("came", ["came", "come", "comes", "coming", "visited", "visitor", "visitors", "entered", "arrived"])],
    roles := [("maker", ["maker"]), ("coiner", ["coiner"])],
    hob := [("asksFirst", "hob: that asks first; send it filled:"),
            ("needs", "hob: that still needs {fields}; send it filled:"),
            ("noneTakes", "hob: none of {card}'s spells takes that; its spells: delvetalk {card} ?"),
            ("usage", "hob: how a spell is read: delvetalk library read / page: spells"),
            ("heard", "hob: the town heard you. A spell acts here: delvetalk guide shows how, delvetalk commonplace ? lists what it takes."),
            ("hint", "hob: the page on this: delvetalk library read / page: spells"),
            ("away", "While you were away"), ("before", "Before you arrived")] }

/-! ### Japanese and Chinese: read as characters -/

/-- The units and fields as CJK writes them, shared where the two agree. -/
def japanese : Tongue :=
  { code := "ja", name := "日本語", english := "Japanese", spaced := false, quotes := "「 」",
    forbidden := ["私", "わたし", "僕", "ぼく", "俺", "おれ", "あたし", "ありがとう", "すみません", "ごめん", "ようこそ", "ください", "どうぞ", "感謝"],
    secondPerson := ["あなた", "貴方", "君", "きみ", "お前", "おまえ", "貴様"],
    negators := ["ない", "なかった", "ません", "無い", "無し", "なし", "未"],
    wanting := ["欲し", "求め", "望ん", "望む", "必要", "欠け", "欠いて"],
    vague := ["誰か", "何か", "手", "誰"],
    cardinals := [("ふたつ", 2), ("みっつ", 3), ("よっつ", 4), ("いつつ", 5), ("むっつ", 6), ("ななつ", 7), ("やっつ", 8), ("ここのつ", 9), ("ふたり", 2)],
    free := ["一"],
    lexicon :=
      [("keeper", ["番人", "守り手", "管理人", "世話役"]),
       ("maker", ["作り手", "作者", "製作者", "作った", "作られ", "作り"]),
       ("owner", ["持ち主", "所有者"]),
       ("rung", ["鳴っ", "鳴ら", "鳴り", "鳴る", "響"]),
       ("tended", ["手入れ", "世話"]),
       ("lines", ["書き込", "書か", "書い", "書き"]),
       ("doors", ["扉", "ドア", "戸口"]),
       ("wants", ["欲し", "求め", "望み", "望ん"]),
       ("came", ["来た", "来て", "訪れ", "訪問", "来訪", "訪ね"]),
       ("rain", ["雨"]), ("line", ["行", "書き込み", "言葉"]), ("door", ["扉", "ドア"]),
       ("visitor", ["訪問者", "来訪者", "客", "人"]), ("visit", ["訪問", "来訪", "回"]), ("thing", ["もの", "物", "品"]),
       ("act", ["行い", "行為"]), ("refusal", ["拒否", "却下"]), ("hand", ["手"]), ("minute", ["分"]),
       ("character", ["文字", "字"]), ("bell", ["鐘", "ベル"]), ("kind", ["種類"]), ("time", ["回", "度"]),
       ("ring", ["鳴"]), ("water", ["水"]), ("here", ["いる", "ここに"])],
    roles := [("maker", ["作り手", "作者", "製作者"]), ("coiner", ["名付け親", "造語者"]), ("town", ["町", "街"])],
    hob := [("asksFirst", "hob: それは先に訊く。埋めて送って:"),
            ("needs", "hob: まだ {fields} が要る。埋めて送って:"),
            ("noneTakes", "hob: {card} のどの呪文もそれを取らない。呪文は: delvetalk {card} ?"),
            ("usage", "hob: 呪文の読み方: delvetalk library read / page: spells"),
            ("hint", "hob: これについての頁: delvetalk library read / page: spells"),
            ("away", "留守のあいだに"), ("before", "あなたが来る前に")] }

def chinese : Tongue :=
  { code := "zh", name := "中文", english := "Chinese", spaced := false, quotes := "“ ”",
    forbidden := ["我", "谢谢", "感谢", "对不起", "抱歉", "欢迎", "请"],
    secondPerson := ["你", "您"],
    negators := ["不", "没", "沒", "无", "無", "未", "别", "非", "莫"],
    wanting := ["想要", "需要", "渴望", "缺", "盼", "要求"],
    vague := ["有人", "某人", "谁", "什么", "东西", "手"],
    free := ["一"],
    lexicon :=
      [("keeper", ["看守", "守护者", "管理者", "保管"]),
       ("maker", ["制作者", "作者", "创造者", "造它", "做的", "做了"]),
       ("owner", ["主人", "所有者", "拥有者"]),
       ("rung", ["响", "敲响", "鸣"]),
       ("tended", ["照料", "照看", "打理"]),
       ("lines", ["写下", "写了", "留言", "写过"]),
       ("doors", ["门"]),
       ("wants", ["想要", "需要", "缺"]),
       ("came", ["来过", "来了", "到访", "访客", "来访"]),
       ("rain", ["雨"]), ("line", ["行", "句", "条"]), ("door", ["门", "扇"]),
       ("visitor", ["访客", "来客", "客人", "位", "人"]), ("visit", ["次"]), ("thing", ["件", "东西", "物"]),
       ("act", ["举动", "行为"]), ("refusal", ["拒绝"]), ("hand", ["手"]), ("minute", ["分钟", "分"]),
       ("character", ["字"]), ("bell", ["钟", "铃"]), ("kind", ["种"]), ("time", ["次", "遍"]),
       ("ring", ["响"]), ("water", ["水"]), ("here", ["在这里", "在此"])],
    roles := [("maker", ["制作者", "作者", "创造者"]), ("coiner", ["命名者", "首创者"]), ("town", ["小镇", "城镇", "镇"])],
    hob := [("asksFirst", "hob: 这要先问；填好再发:"),
            ("needs", "hob: 还缺 {fields}；填好再发:"),
            ("noneTakes", "hob: {card} 的咒语都不接这个；它的咒语: delvetalk {card} ?"),
            ("usage", "hob: 咒语怎么读: delvetalk library read / page: spells"),
            ("hint", "hob: 讲这个的一页: delvetalk library read / page: spells"),
            ("away", "你不在的时候"), ("before", "在你到来之前")] }

/-! ### Spanish, Russian, Arabic: read by word -/

def spanish : Tongue :=
  { code := "es", name := "español", english := "Spanish", quotes := "« »",
    forbidden := ["yo", "me", "mi", "mis", "mio", "mia", "conmigo", "gracias", "perdon", "lo siento", "bienvenido", "bienvenida",
                  "bienvenidos", "bienvenidas", "por favor"],
    secondPerson := ["tu", "tus", "usted", "ustedes", "vosotros", "vosotras", "vuestro", "vuestra", "te", "ti", "contigo", "os"],
    negators := ["no", "nunca", "nadie", "nada", "ningun", "ninguna", "ninguno", "ni", "jamas", "sin", "tampoco"],
    wanting := ["quiere", "quieren", "necesita", "necesitan", "desea", "desean", "falta", "faltan", "carece", "anhela", "pide", "piden"],
    vague := ["alguien", "algo", "mano", "manos", "alguno", "alguna", "quien", "mas", "aqui", "ahora", "otra", "vez"],
    small := ["el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "con", "por", "para", "y", "o",
              "que", "su", "sus", "es", "son", "se", "lo", "le", "les", "ya", "aun", "todavia", "mas", "sobre", "entre", "como",
              "veces", "vez"],
    conjunctions := ["y", "pero", "mientras", "aunque"],
    cardinals := [("cero", 0), ("dos", 2), ("tres", 3), ("cuatro", 4), ("cinco", 5), ("seis", 6), ("siete", 7), ("ocho", 8),
                  ("nueve", 9), ("diez", 10), ("once", 11), ("doce", 12), ("trece", 13), ("catorce", 14), ("quince", 15),
                  ("veinte", 20), ("treinta", 30), ("cuarenta", 40), ("cincuenta", 50), ("cien", 100), ("ciento", 100),
                  ("mil", 1000), ("docena", 12), ("par", 2)],
    ordinals := [("segundo", 2), ("segunda", 2), ("tercero", 3), ("tercera", 3), ("tercer", 3), ("cuarto", 4), ("cuarta", 4),
                 ("quinto", 5), ("quinta", 5), ("sexto", 6), ("sexta", 6), ("septimo", 7), ("septima", 7), ("octavo", 8),
                 ("octava", 8), ("noveno", 9), ("novena", 9), ("decimo", 10), ("decima", 10)],
    ordinalMarks := ["º", "ª", ".º", ".ª", "o", "a"],
    free := ["uno", "una", "un", "primero", "primera", "primer"], stem := spanishStem,
    lexicon :=
      [("keeper", ["guardian", "guardiana", "guarda", "custodio", "custodia", "cuidador", "cuidadora"]),
       ("maker", ["creador", "creadora", "hacedor", "autor", "autora", "hizo", "hecho", "hecha", "creo", "creado", "creada"]),
       ("owner", ["dueño", "dueña", "propietario", "propietaria"]),
       ("rung", ["sonado", "sono", "sonar", "suena", "tañido", "repicado", "repico", "tocado", "toco", "tañida"]),
       ("tended", ["cuidado", "cuidada", "atendido", "atendida", "cuidar", "cuido"]),
       ("lines", ["linea", "verso", "escrito", "escrita", "escribio", "palabra"]),
       ("doors", ["puerta"]),
       ("wants", ["quiere", "quieren", "necesita", "necesitan", "desea", "falta", "carece"]),
       ("came", ["vino", "vinieron", "llego", "llegaron", "visitante", "visito", "visitaron", "entro", "entraron"]),
       ("rain", ["lluvia", "llovizna"]), ("line", ["línea", "verso"]), ("door", ["puerta"]),
       ("visitor", ["visitante", "huésped"]), ("visit", ["visita"]), ("thing", ["cosa", "objeto"]),
       ("act", ["acto", "acción"]), ("refusal", ["rechazo", "negativa"]), ("hand", ["mano"]), ("minute", ["minuto"]),
       ("character", ["carácter", "caracteres", "letra"]), ("bell", ["campana"]), ("kind", ["clase", "tipo"]),
       ("time", ["vez", "veces"]), ("ring", ["toque", "campanada", "repique"]), ("water", ["riego", "agua"]),
       ("here", ["aquí"])],
    roles := [("maker", ["creador", "creadora", "hacedor", "autor", "autora"]), ("coiner", ["acuñador", "acuñadora"]), ("town", ["pueblo", "ciudad"])],
    hob := [("asksFirst", "hob: eso pregunta antes; envíalo relleno:"),
            ("needs", "hob: aún falta {fields}; envíalo relleno:"),
            ("noneTakes", "hob: ningún hechizo de {card} toma eso; sus hechizos: delvetalk {card} ?"),
            ("usage", "hob: cómo se lee un hechizo: delvetalk library read / page: spells"),
            ("hint", "hob: la página sobre esto: delvetalk library read / page: spells"),
            ("away", "Mientras no estabas"), ("before", "Antes de que llegaras")] }

/-- Russian ordinals by their stems: второй, седьмого, седьмом … -/
def russianOrdinals : List (String × Nat) :=
  let endings := ["ой", "ый", "ий", "ая", "ое", "ого", "ому", "ом", "ую", "ые", "ых", "ым", "ей", "ья", "ье", "ьего", "ьей", "ьем"]
  ([("втор", 2), ("трет", 3), ("четверт", 4), ("пят", 5), ("шест", 6), ("седьм", 7), ("восьм", 8), ("девят", 9), ("десят", 10)].flatMap
    fun (s, n) => endings.map fun e => (s ++ e, n))

def russian : Tongue :=
  { code := "ru", name := "русский", english := "Russian", quotes := "« »",
    forbidden := ["я", "меня", "мне", "мной", "мой", "моя", "мое", "мои", "моего", "моей", "спасибо", "извините", "простите",
                  "добро пожаловать", "пожалуйста"],
    secondPerson := ["ты", "тебя", "тебе", "тобой", "твой", "твоя", "твое", "твои", "вы", "вас", "вам", "вами", "ваш", "ваша",
                     "ваше", "ваши"],
    negators := ["не", "нет", "ни", "никогда", "никто", "ничего", "ничто", "нигде", "без", "нету", "никого"],
    wanting := ["хочет", "хотят", "нужен", "нужна", "нужно", "нужны", "нуждается", "просит", "просят", "желает", "требует",
                "недостает"],
    vague := ["кто-нибудь", "кто-то", "что-то", "что-нибудь", "рука", "руки", "руку", "рук", "кого-нибудь", "чья-нибудь", "еще"],
    small := ["в", "во", "на", "и", "а", "с", "со", "к", "ко", "у", "о", "об", "от", "до", "по", "за", "из", "что", "его", "ее",
              "их", "это", "этот", "эта", "еще", "уже", "все", "как", "раз", "раза"],
    conjunctions := ["и", "но", "а", "пока", "хотя"],
    cardinals := [("ноль", 0), ("два", 2), ("две", 2), ("двух", 2), ("двум", 2), ("двумя", 2), ("три", 3), ("трех", 3),
                  ("трем", 3), ("тремя", 3), ("четыре", 4), ("четырех", 4), ("четырем", 4), ("пять", 5), ("пяти", 5),
                  ("шесть", 6), ("шести", 6), ("семь", 7), ("семи", 7), ("восемь", 8), ("восьми", 8), ("девять", 9),
                  ("девяти", 9), ("десять", 10), ("десяти", 10), ("двадцать", 20), ("тридцать", 30), ("сорок", 40),
                  ("сто", 100), ("тысяча", 1000), ("дважды", 2), ("трижды", 3), ("пара", 2)],
    ordinals := russianOrdinals,
    ordinalMarks := ["-й", "-я", "-е", "-го", "-му", "-м", "-ой", "-ая", "-ое"],
    free := ["один", "одна", "одно", "одного", "одной", "первый", "первая", "первое", "первого", "первом", "однажды", "раз"],
    stem := russianStem,
    lexicon :=
      [("keeper", ["хранитель", "хранительница", "смотритель", "страж"]),
       ("maker", ["создатель", "создательница", "автор", "создал", "создала", "создано", "сделал", "сделала"]),
       ("owner", ["владелец", "владелица", "хозяин", "хозяйка"]),
       ("rung", ["звонил", "звонила", "звонили", "звонило", "зазвонил", "прозвенел", "прозвонил", "звенел", "звенит", "звон",
                 "звонить", "звенеть"]),
       ("tended", ["ухаживал", "ухаживали", "присматривал", "уход", "ухаживать", "присмотр"]),
       ("lines", ["строка", "строчка", "написал", "написала", "написали", "записал", "записала"]),
       ("doors", ["дверь", "двери", "дверей", "дверью"]),
       ("wants", ["хочет", "хотят", "нужна", "нужен", "нужно", "нужны", "нуждается"]),
       ("came", ["пришел", "пришла", "пришли", "приходил", "приходила", "приходили", "заходил", "заходила", "заходили",
                 "гость", "посетитель", "побывал", "побывала", "побывали"]),
       ("rain", ["дождь", "ливень"]), ("line", ["строка", "строчка"]), ("door", ["дверь", "двери", "дверей"]),
       ("visitor", ["посетитель", "гость"]), ("visit", ["визит", "посещение"]), ("thing", ["вещь", "предмет"]),
       ("act", ["действие", "поступок"]), ("refusal", ["отказ"]), ("hand", ["рука"]), ("minute", ["минута", "минут"]),
       ("character", ["символ", "знак", "буква"]), ("bell", ["колокол", "колокольчик"]), ("kind", ["вид", "род"]),
       ("time", ["раз"]), ("ring", ["звон"]), ("water", ["полив", "вода"]), ("here", ["здесь"])],
    roles := [("maker", ["создатель", "создательница", "автор"]), ("coiner", ["автор слова"]), ("town", ["город", "городок"])],
    hob := [("asksFirst", "hob: это сперва спрашивают; пришли заполненным:"),
            ("needs", "hob: ещё нужно {fields}; пришли заполненным:"),
            ("noneTakes", "hob: ни одно заклинание {card} этого не берёт; его заклинания: delvetalk {card} ?"),
            ("usage", "hob: как читается заклинание: delvetalk library read / page: spells"),
            ("hint", "hob: страница об этом: delvetalk library read / page: spells"),
            ("away", "Пока тебя не было"), ("before", "До твоего прихода")] }

def arabic : Tongue :=
  { code := "ar", name := "العربية", english := "Arabic", quotes := "« »",
    forbidden := ["انا", "لي", "شكرا", "عفوا", "اسف", "اسفه", "مرحبا", "اهلا", "رجاء", "فضلك"],
    secondPerson := ["انت", "انتم", "انتن", "لك", "لكم", "اليك", "عليك"],
    negators := ["لا", "لم", "لن", "ليس", "ليست", "غير", "بلا", "دون", "ابدا"],
    wanting := ["يريد", "تريد", "يريدون", "يحتاج", "تحتاج", "ينقص", "تنقص", "ينقصه", "ينقصها", "يفتقر", "تفتقر", "يطلب",
                "تطلب", "يرغب", "ترغب"],
    vague := ["احد", "شيء", "يد", "يدا", "من"],
    small := ["في", "على", "من", "الي", "عن", "مع", "او", "هذا", "هذه", "ذلك", "تلك", "قد", "كان", "كانت", "التي", "الذي",
              "ثم", "حتي", "عند", "و", "مرة", "مرات"],
    conjunctions := ["لكن", "بينما", "ثم", "و"],
    cardinals := [("صفر", 0), ("اثنان", 2), ("اثنين", 2), ("اثنتان", 2), ("اثنتين", 2), ("ثلاث", 3), ("ثلاثه", 3),
                  ("اربع", 4), ("اربعه", 4), ("خمس", 5), ("خمسه", 5), ("ست", 6), ("سته", 6), ("سبع", 7), ("سبعه", 7),
                  ("ثماني", 8), ("ثمانيه", 8), ("ثمان", 8), ("تسع", 9), ("تسعه", 9), ("عشر", 10), ("عشره", 10),
                  ("عشرون", 20), ("عشرين", 20), ("مئه", 100), ("مائه", 100), ("الف", 1000), ("مرتين", 2), ("مرتان", 2)],
    ordinals := [("الثاني", 2), ("الثانيه", 2), ("ثاني", 2), ("ثانيه", 2), ("الثالث", 3), ("الثالثه", 3), ("ثالث", 3),
                 ("الرابع", 4), ("الرابعه", 4), ("رابع", 4), ("الخامس", 5), ("الخامسه", 5), ("خامس", 5), ("السادس", 6),
                 ("السادسه", 6), ("سادس", 6), ("السابع", 7), ("السابعه", 7), ("سابع", 7), ("سابعه", 7), ("الثامن", 8),
                 ("الثامنه", 8), ("ثامن", 8), ("التاسع", 9), ("التاسعه", 9), ("تاسع", 9), ("العاشر", 10), ("العاشره", 10), ("عاشر", 10)],
    free := ["واحد", "واحده", "اول", "الاول", "الاولي", "مره"], stem := arabicStem,
    lexicon :=
      [("keeper", ["حارس", "حارسه", "امين", "قيم", "راع"]),
       ("maker", ["صانع", "صنعه", "صنعها", "صنع", "خالق", "مبدع"]),
       ("owner", ["مالك", "صاحب"]),
       ("rung", ["رن", "يرن", "دق", "قرع", "رنين", "قرعه"]),
       ("tended", ["رعايه", "اعتني", "رعي", "يعتني", "عنايه"]),
       ("lines", ["سطر", "اسطر", "سطور", "كتب", "كتبت", "كتابه"]),
       ("doors", ["باب", "ابواب"]),
       ("wants", ["يريد", "تريد", "يحتاج", "تحتاج", "ينقص", "تنقص"]),
       ("came", ["جاء", "جاءت", "اتي", "اتت", "زار", "زارت", "زائر", "زوار", "دخل", "دخلت"]),
       ("rain", ["مطر", "امطار", "زخه"]), ("line", ["سطر", "اسطر"]), ("door", ["باب", "ابواب"]),
       ("visitor", ["زائر", "زوار"]), ("visit", ["زيارة"]), ("thing", ["شيء", "اشياء"]),
       ("act", ["فعل", "افعال"]), ("refusal", ["رفض"]), ("hand", ["يد"]), ("minute", ["دقيقة", "دقائق"]),
       ("character", ["حرف", "حروف"]), ("bell", ["جرس", "اجراس"]), ("kind", ["نوع"]), ("time", ["مرة", "مرات"]),
       ("ring", ["رنين"]), ("water", ["سقي", "ماء"]), ("here", ["هنا"])],
    roles := [("maker", ["صانع", "صانعه", "صانعها", "مبدع"]), ("coiner", ["صائغ"]), ("town", ["البلده", "المدينه", "بلده", "مدينه"])],
    hob := [("asksFirst", "hob: هذا يُسأل عنه أولًا؛ أرسله مملوءًا:"),
            ("needs", "hob: ما زال ينقصه {fields}؛ أرسله مملوءًا:"),
            ("noneTakes", "hob: لا تعويذة من تعاويذ {card} تأخذ هذا؛ تعاويذه: delvetalk {card} ?"),
            ("usage", "hob: كيف تُقرأ التعويذة: delvetalk library read / page: spells"),
            ("hint", "hob: الصفحة عن هذا: delvetalk library read / page: spells"),
            ("away", "بينما كنت غائبًا"), ("before", "قبل أن تصل")] }

/-- Every tongue the town paints, checks and speaks hob's lines in. -/
def tongues : List Tongue := [english, japanese, chinese, spanish, russian, arabic]

/-- A stated or detected language code as the town keys it: `ja-JP` and `JA` are `ja`. -/
def codeOf (given : String) : String :=
  lower (String.ofList ((given.trimAscii.toString.toList).takeWhile fun c => c != '-' && c != '_'))

def find? (code : String) : Option Tongue := tongues.find? (·.code == codeOf code)

def Tongue.number (t : Tongue) (token : String) : Option (Nat × Bool) :=
  if t.code == "en" then englishNumber t token else t.wordNumber token

/-- The words this tongue says the field or unit `key` (an English word, any form) with: the lexicon's entry
    whose key meets it. -/
def Tongue.wordsFor (t : Tongue) (key : String) : List String :=
  ((t.lexicon.find? fun (k, _) => englishStem k == englishStem key).map (·.2)).getD []

/-- The unit word the painter is given for `unit` in this tongue, when it has one. -/
def Tongue.unitWord (t : Tongue) (unit : String) : Option String := (t.wordsFor unit).head?

/-- The English stems of the fields and units a word of this tongue says: "lluvias" is rain, "дверей" door. -/
def Tongue.concepts (t : Tongue) (w : String) : List String :=
  (t.lexicon.filter fun (_, forms) => forms.any (t.matches w ·)).map (englishStem ·.1)

/-! ## Which tongue -/

def spanishWords : List String :=
  ["el", "los", "las", "del", "que", "una", "unos", "por", "para", "con", "sin", "esta", "es", "muy", "pero", "como", "sobre",
   "su", "sus", "se", "lo", "ya", "aqui", "quien", "cuando", "donde", "este", "ese", "esa", "y", "la", "de", "en", "un",
   "ha", "han", "hay", "nadie", "nunca", "todavia", "tambien", "aun", "fue", "era", "estaba", "hasta", "desde", "entre",
   "cada", "otra", "otro", "solo", "dijo", "espera", "sigue"]

def englishWords : List String :=
  ["the", "and", "of", "to", "is", "it", "on", "in", "for", "with", "this", "that", "was", "are", "my", "i", "you", "at",
   "by", "be", "an"]

/-- The language words are written in: the script most of their letters are in beyond Latin (kana with or without
    han is Japanese, han alone Chinese, Cyrillic Russian, Arabic Arabic), else Spanish by ñ ¿ ¡, or by its small
    words and accented vowels outnumbering English's small words, else English. A spell's ASCII in the words does not outvote two letters of another
    script. -/
def detect (text : String) : String := Id.run do
  let cs := text.toList
  let count := fun (s : Script) => (cs.filter (scriptOf · == s)).length
  let (kana, han, cyr, arab) := (count .kana, count .han, count .cyrillic, count .arabic)
  let cjk := kana + han
  let best := max cjk (max cyr arab)
  if best ≥ 2 then
    return if cjk == best then (if kana > 0 then "ja" else "zh") else if cyr == best then "ru" else "ar"
  if "ñ¿¡".toList.any cs.contains then return "es"
  let ws := ((text.split fun c => c.isWhitespace || ",.;:!?()\"“”«»".toList.contains c).map fun w => fold w.toString)
  let es := (ws.filter spanishWords.contains).length + (cs.filter "áéíóú".toList.contains).length
  let en := (ws.filter englishWords.contains).length
  return if es ≥ 2 && es > en then "es" else "en"

#guard detect "冷蔵庫の奥は星屑の氷で満ちている" == "ja"
#guard detect "给钟下一场雨" == "zh"
#guard detect "Пусть на колокол прольётся дождь" == "ru"
#guard detect "أمطر على الجرس" == "ar"
#guard detect "llueve sobre la campana para quien llega tarde" == "es"
#guard detect "rain on the bell for whoever comes late" == "en"
#guard detect "Nadie ha traído lluvia a la campana todavía." == "es"
#guard detect "delvetalk garden/bell/1 rain / text: 遅れて来る人のために" == "ja"
#guard detect "" == "en"

/-- The tongue the avatar of `principal` states (`delvetalk me set / tongue: ja`), if any. -/
def preferred (w : World) (principal : String) : Option String := do
  let o ← w.objects[principal]?
  let .record fs := o.state | none
  let some (.label t) := fs.lookup "tongue" | none
  let t := codeOf t
  if t.isEmpty then none else some t

/-- The tongue to answer `principal` in: the one they state, else the one `words` are written in, else English. -/
def choose (w : World) (principal words : String) : String :=
  (preferred w principal).getD (detect words)

/-- hob's line `name` (and a telling's frames) in the tongue `code`, its `{key}`s filled; English for a tongue the
    town has no lines in. -/
def say (code name : String) (args : List (String × String) := []) : String :=
  let line := (((find? code).getD english).hob.lookup name).getD ((english.hob.lookup name).getD "")
  args.foldl (fun l (k, v) => l.replace ("{" ++ k ++ "}") v) line

#guard say "ja" "needs" [("fields", "text")] == "hob: まだ text が要る。埋めて送って:"
#guard say "fr" "asksFirst" == "hob: that asks first; send it filled:"

end Delvetalk.Host.Tongue
