"""All tunable thresholds in one place.

Every threshold that decides whether an annotation fires lives here, with the
reasoning next to it. Annotation thresholds are relative to the utterance's own
baseline (the speaker's own median F0, own mean intensity, own speaking rate),
never absolute, because recording level and voice differ wildly across files
(see TOOLING.md: 48 dB vs 71 dB mean intensity on two samples of the same speaker).
"""

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Config:
    # --- word alignment (mlx-whisper) ---
    model: str = "mlx-community/whisper-small-mlx"
    # Words below this whisper alignment confidence carry timestamps too shaky
    # to hang prosody on. They still appear in the text, unannotated.
    min_word_prob: float = 0.30

    # --- pitch extraction (praat) ---
    pitch_floor_hz: float = 75.0
    pitch_ceiling_hz: float = 500.0

    # --- silence detection (praat To TextGrid (silences)) ---
    # Praat takes this threshold relative to the file's maximum intensity, and a
    # single loud transient (a plosive pop, a bump) pushes it above real speech.
    # So prosodi anchors it to the 98th intensity percentile (the speech mass)
    # instead of the max, and never lets it sink below the file's own noise
    # floor (p10) plus a margin, or noisy recordings would yield zero silences.
    silence_threshold_db: float = -25.0
    noise_floor_margin_db: float = 3.0
    min_pause_s: float = 0.30
    min_sounding_s: float = 0.10

    # --- pause rendering ---
    # A gap between words is rendered as <pause Xs> only when at least this much
    # of it overlaps a detected silence. A long gap with little silence inside it
    # is usually a disfluency whisper dropped, which is audible speech, no pause.
    render_min_pause_s: float = 0.30

    # --- emphasis (vs the utterance's own baseline) ---
    # A word is emphasized when its median F0 sits this many semitones above the
    # utterance median F0, OR its mean intensity sits this many dB above the
    # utterance's mean intensity over speech frames. Pitch accents land around
    # 2-4 st, so 3.0 catches the deliberate ones and skips natural wobble.
    emphasis_f0_st: float = 3.0
    emphasis_db: float = 5.0
    # The F0 route only counts when the word is not much quieter than baseline.
    # A pitch peak on a fading or creaky word is usually an octave-jump artifact
    # of the tracker, never a perceived emphasis.
    emphasis_f0_min_db: float = -3.0
    # F0 stats on fewer voiced frames than this are noise, skip the word.
    min_voiced_frames: int = 3
    # Per-recording density cap. On agitated files most words clear the
    # absolute thresholds (30% of words on the rant sample) and the marker
    # stops scanning. Candidates that pass the thresholds are ranked by
    # combined salience (semitones above the F0 trend plus dB above the
    # word-median intensity, negatives clamped to zero) and at most this
    # percent of the recording's words keep the star. Files already under the
    # cap are untouched. The raw threshold pass stays in the JSON as
    # emphasis_candidate.
    emphasis_max_word_pct: float = 12.0

    # --- stretch (lengthened words) ---
    # Expected word duration comes from the utterance's own characters-per-second
    # rate over non-pause time, so it needs no lexicon and works for Russian.
    stretch_threshold: float = 1.8
    # A fixed articulation overhead added to every word's character count before
    # dividing by the rate, so one-letter words don't get absurd stretch factors.
    word_overhead_chars: float = 1.0
    # Floor on the expected duration, same reason.
    min_expected_s: float = 0.12
    # A word must actually be this long (after pause exclusion) to count as
    # stretched, regardless of the ratio.
    min_stretched_s: float = 0.35
    # Rendering floors. Whisper's word boundaries are loose on short function
    # words ("I", "a", "to") and about a third of v0 stretch marks were
    # boundary slop there. A rendered stretch mark now requires at least this
    # many alphanumeric characters and at least stretch_min_abs_s of effective
    # duration. The raw stretch_factor stays in the JSON for every word
    # regardless, only the marker is gated.
    stretch_min_chars: int = 4
    # At the defaults this is subsumed by min_stretched_s (0.35 > 0.25). Kept
    # as an explicit independent floor so lowering min_stretched_s never lets
    # sub-syllable blips through.
    stretch_min_abs_s: float = 0.25

    # --- F0 movement (per word) and boundary tones (clause end) ---
    # Movement compares the mean F0 of the word's last voiced third against its
    # first voiced third, in semitones. Beyond +/- this delta it is rise/fall.
    movement_st: float = 1.5

    # --- tempo windows ---
    # Local rate over a centered window of words, in chars/sec over effective
    # (pause-free) time, against the utterance's own rate. A run of at least
    # tempo_min_run flagged words becomes a <faster>/<slower> span.
    tempo_window_words: int = 5
    tempo_faster_ratio: float = 1.35
    tempo_slower_ratio: float = 0.70
    tempo_min_run: int = 3

    # --- speaker profile comparison (analyze --profile) ---
    # The per-recording baseline cannot see global agitation: a file dictated
    # fast end to end has a "normal" local rate. With a speaker profile
    # (prosodi profile <dir>) the recording's words-per-second over speaking
    # time is compared to the speaker's corpus median, and a document-level
    # marker renders when the ratio passes these bounds.
    profile_agitated_rate_ratio: float = 1.30
    profile_subdued_rate_ratio: float = 0.70

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = Config()
