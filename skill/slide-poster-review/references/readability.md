# Readability: sources for the RD items

Compiled 2026-11-25 (QUEUE task 24). Items marked *unverified* were seen only in secondary sources.

## RD-1 Vocabulary level

**Word lists** (in `assets/cefr/`, unchanged from Open Language Profiles,
https://github.com/openlanguageprofiles/olp-en-cefrj):
- *CEFR-J Wordlist Version 1.5*, compiled by Yukio Tono, Tokyo University of Foreign Studies.
  About 7,800 entries, A1–B2. Free for research and commercial use with citation.
- *Octanove Vocabulary Profile C1/C2, version 1.0*, Octanove Labs. About 2,100 entries, C1–C2.
  CC BY-SA 4.0.

The English Vocabulary Profile (Cambridge) and the Oxford 3000/5000 have levels for more words,
but they can't be redistributed.

**Coverage thresholds.** Coverage is the share of running words a reader knows.
- Laufer (1989): about 95% coverage for reasonable comprehension.
- Hu & Nation (2000), *Reading in a Foreign Language* 13(1): about 98% for adequate unassisted
  comprehension of fiction.
- Laufer & Ravenhorst-Kalovski (2010), *Reading in a Foreign Language* 22(1): 95% is a
  "minimal" and 98% an "optimal" threshold.
- Schmitt, Jiang & Grabe (2011), *Modern Language Journal* 95(1): comprehension rises steadily
  with coverage, with no sharp threshold. So the bounds are points on a slope, not cliffs.

The levels use 98 / 95 / 90%. The 90% bound has no direct source: it marks text where readers
miss about one word in ten.

**Audience → target level.** A general audience is rated at B2 ("independent user"), readers of
English as a second language at B1, and experts at C2, so only words in neither list count.
These are defaults, not research findings; validation (QUEUE 29) should test them.

**Limits.**
- The lists hold about 10,000 headwords. Common academic words such as *framework*,
  *variable*, and *equivalent* are in neither list, so they count as above every level.
  Academic decks therefore score somewhat low. Findings say "Technical terms the audience
  knows, or that are defined, are fine", and the agent's judgment (RD-4) covers this.
- Inflections are removed by rule, not with a dictionary, so a few forms are missed.
- Names are skipped only when a word is capitalized in the middle of an ordinary sentence, or in
  Title Case text. A name that only starts sentences counts as a rare word.

## RD-2 Sentence length

Plain-language guides recommend an average of 15–20 words per sentence (Cutts, *Oxford Guide to
Plain English*; *unverified*: the exact figure varies by edition). The US Federal Plain Language
Guidelines (2011) advise short sentences with one idea each, without a fixed number. Slides should
be shorter than prose, so Level 4 is 15 words or fewer and Level 3 is 20. The 30-word bound for
Level 2 is a judgment call. Revisit after validation (29).

## RD-3 Acronyms

WCAG 2.x success criterion 3.1.4 *Abbreviations* (Level AAA) asks for a way to find the expanded
form. Plain-language guides ask for acronyms to be spelled out at first use. The script counts an
acronym as defined if it is spelled out anywhere in the shown text.

## Secondary signals: Flesch and Flesch-Kincaid

- Flesch Reading Ease (Flesch 1948): 206.835 − 1.015 × words/sentence − 84.6 × syllables/word.
- Flesch-Kincaid grade (Kincaid et al. 1975): 0.39 × words/sentence + 11.8 × syllables/word − 15.59.
- Adaptations of Flesch Reading Ease, using constants as in textstat 0.7.13 (*unverified* against
  the original papers): German (Amstad 1978), Spanish (Fernández Huerta 1959), French (Kandel &
  Moles 1958), Italian (Flesch-Vacca), Dutch (Douma 1960), and Russian. Flesch-Kincaid has no
  adaptations.

These formulas are calibrated on running prose. Slides are mostly fragments, which makes them
read as easier than they are. That's why they are reported but not scored.

## What `textstat` covers (checked 2026-11-25, version 0.7.13, MIT license)

- **Formulas:** Flesch Reading Ease, Flesch-Kincaid grade, SMOG, Coleman-Liau, ARI, Dale-Chall
  (two versions), Gunning Fog, Linsear Write, Spache, McAlpine EFLAW, LIX, RIX, reading time,
  `text_standard` (a consensus grade).
- **Language-specific formulas:** Spanish (Fernández Huerta, Szigriszt-Pazos, Gutiérrez de
  Polini, Crawford), Italian (Gulpease), German (Wiener Sachtextformel), Arabic (Osman).
- **Languages:** `set_lang` changes the Flesch Reading Ease constants for de, es, fr, it, nl,
  and ru, and the "long word" syllable threshold for pl and hu. Flesch-Kincaid ignores the
  language. Easy-word lists (Dale-Chall, Spache, difficult words) exist only for English and
  Spanish.
- **Syllables:** English uses the CMU Pronouncing Dictionary through `nltk`, which downloads it
  on first use (needs network). Other languages use `pyphen` hyphenation, which undercounts.

**Decision.** The skill doesn't depend on textstat. It needs only two formulas, and textstat
would add `nltk` plus a runtime download. `readability.py` computes the formulas itself and
counts syllables as vowel groups. That is accurate enough for a secondary signal.
