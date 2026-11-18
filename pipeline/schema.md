# Lesson JSON format (v2)

One file per lesson: `course/nl/lessons/<id>.json`. All learner-facing explanations are in English,
all target language is standard Netherlands Dutch (not Flemish unless the lesson is about Flemish).

```ts
interface Lesson {
  id: string;                 // "u01-l01"
  title: string;              // Dutch title from the syllabus
  subtitle: string;           // English subtitle
  level: "A0" | "A1" | "A2" | "A2+";
  intro: string;              // 2-3 English sentences: what you will be able to do after this lesson
  words: Word[];              // 18-30 new words, in a sensible teaching order
  phrases: Phrase[];          // 6-10 useful chunks / whole expressions
  grammar: Grammar[];         // 1-3 short grammar notes
  dialogue: Dialogue;         // 8-14 lines, uses the lesson's words and grammar
  exercises: Exercise[];      // 18-24 items, ordered easy -> hard
  roleplay: Roleplay;         // 3-5 turns, the learner answers freely
  culture: { title: string; text: string };   // 2-4 sentences
  summary: string[];          // 3-5 short takeaways
}

interface Word {
  nl: string;                 // lemma without article: "huis", "goedemorgen", "wonen"
  en: string;                 // short English meaning
  pos: "noun"|"verb"|"adj"|"adv"|"pron"|"prep"|"conj"|"num"|"interj"|"phrase"|"other";
  article: "de"|"het"|null;   // nouns only; for plural-only nouns use "de"
  plural: string|null;        // nouns only, full plural form: "huizen"
  forms: string|null;         // verbs: "ik woon, jij woont, wij wonen" at A0/A1; from u07 add participle "(heeft gewoond)"; irregular adj/other forms if useful
  example: { nl: string; en: string };   // short natural sentence using the word
  note: string|null;          // optional, max 1 sentence (false friend, register, pronunciation)
}

interface Phrase { nl: string; en: string; note: string|null }

interface Grammar {
  title: string;
  explanation: string;        // 2-5 short sentences; Dutch words in **bold**
  table: { headers: string[]; rows: string[][] } | null;
  examples: { nl: string; en: string }[];   // 2-4
  tip: string|null;           // optional mnemonic or common mistake
}

interface Dialogue {
  title: string;
  setting: string;            // English, 1 sentence
  speakers: { name: string; gender: "f"|"m" }[];
  lines: { speaker: string; nl: string; en: string }[];
}

type Exercise =
  | { type: "match"; pairs: [string, string][] }                                   // 4-5 pairs nl -> en
  | { type: "choice"; prompt: string; nl: string|null; options: string[]; answer: number; explain: string }
  | { type: "article"; word: string; en: string; answer: "de"|"het" }
  | { type: "build"; en: string; answer: string; accept: string[]; extra: string[]; explain: string }  // tiles = words of answer + extra distractors
  | { type: "gap"; text: string; en: string; answers: string[]; hint: string; explain: string }     // text contains exactly one "___"
  | { type: "translate"; en: string; answers: string[]; focus: string; mistakes: Mistake[] }       // free typing, graded by Jev
  | { type: "listen"; nl: string; en: string }                                                    // learner types what they hear
  | { type: "reply"; context: string; say: { nl: string; en: string }; task: string; examples: string[]; mistakes: Mistake[] };

// The app has no tutor at runtime: a classifier (Jev) only picks which of these authored mistakes the learner made,
// so every explanation the learner sees must be written here, in the lesson.
interface Mistake {
  id: string;                 // "m1", "m2", ...
  pattern: string;            // for the grader: precise description of the wrong answer, with a wrong example
                              //   e.g. "Keeps subject before verb after 'Morgen' (Morgen ik ga naar...)"
  explain: string;            // for the learner: 1-2 short English sentences with the rule and the correct Dutch in quotes
}
// build.explain / gap.explain: one English sentence with the rule behind the right answer (shown when the learner is wrong).

interface Roleplay {
  title: string;
  setting: string;            // English: who the learner is talking to and why
  partner: { name: string; gender: "f"|"m"; role: string };
  turns: { say: { nl: string; en: string }; task: string; examples: string[]; mistakes: Mistake[] }[];
  closing: { nl: string; en: string };
}
```
