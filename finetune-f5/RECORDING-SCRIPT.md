# Recording your voice for a clean f5 fine-tune

The public-YouTube fine-tune proved the recipe but stayed lo-fi because the training
audio was lossy. A clean fine-tune of your own voice is the run that should actually
beat zero-shot. This is what to record and how.

## How to record (the short version)

Record it **raw**. No compression, no EQ coloring, no reverb, no limiting, no de-essing.
A clone inherits whatever you bake in, and compression specifically flattens the
loudness dynamics prosodi exists to measure - so processed audio trains a flatter,
less expressive clone and degrades capture later. Save the production chain for tracks.

- **Neutral mic model** on the Sphere (flat, not a colored vintage voicing).
- **Dry, quiet room.** Reverb is the one unremovable mistake - f5 bakes room sound into
  the voice. Treated space, ~15-20 cm, pop filter.
- **Levels with headroom:** peaks around -12 to -6 dBFS, never clipping. 24-bit, 48 kHz
  (the pipeline downsamples to 24 kHz itself, so give it good source).
- **The only processing that's fine:** a gentle high-pass around 70-80 Hz to kill rumble.
- **Consistency beats gear.** Same distance, level, room, and energy across every take.
  The model learns from consistency; drifting mic placement confuses it.

## How much

Quality and variety beat raw minutes. Targets:

- **Minimum useful:** ~15 minutes of clean, varied speech.
- **Good target:** ~30 minutes. This is the sweet spot - enough coverage without the run
  dragging, and well inside an hour on a cloud GPU.
- **Diminishing returns past ~45-60 min** unless it adds genuine variety. The public run
  used 65 min and the bottleneck was source quality, not quantity.

What matters more than the count: **phonetic coverage** (hit the range of English sounds),
**prosodic variety** (statements, questions, exclamations, hesitation, fast and slow,
emphasis), and **your natural delivery** (read some of it like you'd actually say it, not
in a flat audiobook voice). A monotone 30 minutes trains a monotone clone.

## The script

Read top to bottom. Re-take any line you flub - clean takes only, a fumbled take in the
data teaches the fumble. Leave a beat of silence between sections (you'll trim later).
Read the **expressive** sections the way you'd really talk, not like you're reading.

### 0. Level set (don't keep this take, it's for gain)

> Testing one two. This is a level check. I'm setting the gain so nothing clips. One, two, three.

### 1. The Rainbow Passage (phonetically rich, the classic)

> When the sunlight strikes raindrops in the air, they act as a prism and form a rainbow.
> The rainbow is a division of white light into many beautiful colors. These take the shape
> of a long round arch, with its path high above, and its two ends apparently beyond the
> horizon. There is, according to legend, a boiling pot of gold at one end. People look, but
> no one ever finds it. When a man looks for something beyond his reach, his friends say he is
> looking for the pot of gold at the end of the rainbow.

### 2. Phonetic spread (varied sounds, read at a steady, neutral pace)

> The quick brown fox jumps over the lazy dog.
> She sells sea shells by the shore, and the shells she sells are surely sea shells.
> Six thick thistle sticks. The thirty-three thieves thought they thrilled the throne.
> A jug of fresh judgment, a badge of orange and beige.
> Vivid azure visions of a measured pleasure.
> Whether the weather is cold or whether the weather is hot, we weather the weather whatever
> the weather, whether we like it or not.
> Crisp crusts crackle and crunch. Plush brushes push through.
> The fifth sixth seventh eighth. Truths, depths, lengths, twelfths.
> Bright moonlight, warm firelight, a low hum and a sharp click.

### 3. Numbers, dates, and the awkward bits (TTS struggles here, give it real examples)

> It costs nineteen euros and ninety-nine cents. Call me at half past seven.
> On the third of March, twenty twenty-six, we drove four hundred and twelve kilometers.
> My address is twenty-two B. The score was three to one. Chapter fourteen, page two hundred.
> Email me at hello, at, example, dot com. The Wi-Fi password is all lowercase, no spaces.

### 4. Questions, exclamations, and emphasis (the prosody the flat reads miss)

> Wait - you actually did it? How did that even work?
> No way. Absolutely not. That is the worst idea I have ever heard.
> Listen to me. This matters. Are you paying attention, or not?
> Of course it works. It always works. Why would it not work?
> Honestly? I have no idea. None. Your guess is as good as mine.
> Stop. Just... stop for a second. Let me think.

### 5. Natural narrative (read this like you're telling a story, not reciting)

> I almost didn't go. It was late, the rain hadn't let up, and every reasonable part of me
> wanted to stay home. But there's a particular kind of regret that only shows up when you
> talk yourself out of something, and I had felt it enough times to recognize the shape of it
> coming. So I grabbed my coat off the back of the chair, found my keys where I always lose
> them, and went anyway. Most of the time, the thing you talk yourself out of is the thing you
> remember. The easy night in, the one where nothing happens, that one disappears. The night
> you almost skipped is the one that sticks.

> Here's what nobody tells you about building something. The first version is always wrong,
> and that's fine, because the first version isn't the product, it's the question. You build
> it to find out what you actually meant. Then you throw most of it away and build the second
> one, which is also wrong, but wrong in a smaller, more interesting way. You're not failing.
> You're narrowing.

### 6. Conversational, your real register (talk, don't read)

> So, okay, here's the thing I keep coming back to.
> I mean, look - it's not perfect, but it works, and right now that's what counts.
> Yeah, no, I get it. I do. I just think we're solving the wrong problem.
> Give me like five minutes and I'll have an answer. Maybe ten. Probably ten.
> That's actually kind of brilliant. Annoying, but brilliant.

### 7. A long, calm read (steady tone, for clean sustained voice)

> The river moved slowly that morning, the way water does when there's nowhere it needs to be.
> Light came in low and flat across the surface, and for a while nothing happened at all, which
> was exactly the point. Some things are only visible when you stop expecting them to do
> anything. You sit, you wait, you let the noise settle, and slowly the smaller signals come
> up out of the quiet - a bird, a current, the particular sound your own thinking makes when
> you finally stop talking over it.

## Want more material?

The above runs roughly 20-25 minutes with re-takes and gaps. If you want more coverage or
a more formal phonetic balance, read from any of these (all free to use):

- **Harvard Sentences** (IEEE phonetically balanced lists, ~720 short sentences):
  https://www.cs.columbia.edu/~hgs/audio/harvard.html
- **CMU Arctic prompts** (~1132 sentences, the standard voice-recording corpus):
  http://festvox.org/cmu_arctic/cmuarctic.data
- **Project Gutenberg** (public-domain books) - pick a chapter of prose you enjoy reading and
  read it naturally. Conversational fiction beats dense technical text for prosody.

## After recording

1. Drop the recording into the prosodi web app under **Capture** or save it as a **voice**
   (Voices tab) - scrub a clean ~10-12 s window for the reference, audition it, save.
2. For the fine-tune itself: replace `sources.txt` with your own clip(s), or point
   `prepare.py` at your recording, then run the cloud pipeline in `HANDOFF.md` (RunPod,
   ~30-45 min on an Ampere/Ada card). Training stays a cloud job; inference runs local.
3. Bank the checkpoint, drop it in `finetune-f5/ckpts/<name>/`, tick **fine-tuned f5** in
   Reconstruct, and A/B it against zero-shot. Clean source is the variable that should
   finally push it past zero-shot.
