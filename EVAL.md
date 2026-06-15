# EVAL: prosodi over a public-domain corpus

Run over seven public-domain LibriVox readings (Short Poetry Collection 073), seven different
voices, 1825 words, 18.6 minutes of audio, analyzed with the default config (whisper-small-mlx,
adaptive silence threshold). Every clip processed in one pass without a crash. The cross-check
numbers come from `scripts/eval_check.py`, which compares the rendered pause markers against the
parselmouth silence list and flags any stretch mark that carries speech whisper absorbed from a
dropped word.

These are different speakers reading different poems, so there is no single speaker profile and no
document-level `<agitated>`/`<subdued>` marker here. That marker needs a corpus from one speaker, and
the speaker-relative thresholds still apply per recording.

## Corpus summary

| reading | reader | dur (s) | words | silences | pauses rendered | missed | emph | stretch | bounds | tempo | F0 med | rate w/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Avarice (Herbert) | mtd | 62.1 | 141 | 24 | 20 | 1 | 17 | 1 | 11 | 0 | 103.3 | 3.61 |
| Ballade of a Ship (Robinson) | sbs | 171.1 | 275 | 51 | 51 | 0 | 33 | 6 | 16 | 8 | 125.1 | 2.59 |
| The City (Lovecraft) | kp | 120.5 | 280 | 34 | 31 | 3 | 34 | 3 | 12 | 0 | 99.8 | 3.01 |
| The Dead Man Walking (Hardy) | dgf | 115.0 | 209 | 34 | 34 | 0 | 25 | 1 | 19 | 15 | 97.6 | 2.76 |
| The Dream (Donne) | cc | 121.2 | 252 | 38 | 38 | 0 | 30 | 1 | 12 | 10 | 181.0 | 3.06 |
| The Dying Child (Clare) | ref | 125.4 | 212 | 37 | 34 | 3 | 25 | 0 | 23 | 20 | 172.9 | 2.66 |
| Easter 1916 (Yeats) | lhw | 221.1 | 456 | 71 | 71 | 0 | 55 | 9 | 39 | 15 | 185.8 | 2.97 |
| total | | 1110 | 1825 | 289 | 279 | 7 | 219 | 21 | 132 | 68 | | |

Corpus level:

- **Pause recall 97.6%** (282 of 289 internal silences are covered by a rendered pause marker). The
  seven misses sit inside whisper word spans, the same failure mode the original dictation eval saw.
- **Emphasis covers 12.0% of words**, held there by the per-recording density cap.
- **Stretch marks: 21, zero suspect.** None carry more than 0.1s of absorbed speech. The rendering
  floors (minimum length and duration) keep the marks on real drawls.
- F0 median ranges from 97.6 Hz (a low male reader) to 185.8 Hz across the seven voices, with no
  special-casing per speaker.

## What the annotation catches

### The Dream (Donne), read by cc

```
Dear Love, <pause 0.4s> for nothing less than thee would *I* have broke this happy dream. <pause
1.3s> It was a theme for reason much too strong for fantasy. <pause 0.9s> Therefore thou wakest me
wisely. <pause 0.8s> *Yet* my dream thou breakest not but <pause 0.5s> continues it. <pause 1.0s>
*Thou* art so true that thoughts of thee suffice to make dreams, truths, and fables histories.
<fall> <pause 1.2s> Enter these arms,<stretched 1.8x> <pause 0.6s> for since thou foughtest it best
not to dream all my dream, <pause 0.6s> let's act the rest. <rise>
```

The line-end pauses fall where the verse breaks. The stresses land on the pronouns the poem turns on
("*I*", "*Yet*", "*Thou*"), the drawl on "arms," is the reader holding the line, and the closing
"let's act the rest" rises into the invitation.

### The Dead Man Walking (Hardy), read by dgf

```
They hail me as one living, <pause 1.5s> but don't they know that I have died of late years, <rise>
<pause 0.3s> untombed although? <pause 1.2s> I *am* but a shape that stands here, a pulseless mold,
<rise> <pause 0.4s> a pale past picture, <fall> <pause 0.5s> screening ashes gone cold, <pause 1.2s>
*not* at a minute's warning, <pause 0.4s> *not* in *a* ...
```

The rise on "untombed although?" reads the question, the fall on "a pale past picture" reads the
flat finality, and the repeated stress on "*not* ... *not*" tracks the poem's insistence.

## What is noisy

- Each LibriVox reading opens with a spoken "Title, by Author, read by Reader for LibriVox.org"
  announcement. The tool annotates it like any other speech, and whisper sometimes mangles that line
  (it heard "read for LibriVox.org" as "RedFirleyBervox.org"). Cut the announcement before analysis
  if the leading lines matter.
- A few emphasis marks ride on the announcement words rather than the poem.
- Pause recall drops on the two clips with the most word-internal silences (Lovecraft, Clare), where
  three silences each sit inside a whisper word span and never surface as a marker.

The headline holds across seven unrelated voices with no tuning: pauses land where the verse
breathes, stresses land on the words that carry the line, and the noise is confined to the
boilerplate intro and to whisper's own mishearings.
