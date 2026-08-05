# Monster Band Studio 🎸

A little band of fuzzy monsters that performs any MP3 you give it — inspired by AI monster-band accounts on TikTok.

**Open `index.html` in any modern browser (Chrome recommended). No install, no server, no upload — everything runs locally.**

## What it does

- **Load an MP3** (or M4A/WAV/OGG) by dragging it onto the stage or using the Load button — or hit **Try demo song** to hear a built-in tune.
- The app analyzes the audio live with the Web Audio API:
  - the **lead singer's mouth** syncs to vocal-range energy,
  - the **drummer** hits on detected beats (bass-energy beat detection),
  - the **guitarist strums**, the **keyboardist plays**, dancers bounce, confetti flies, the crowd bops.
- **🎲 New band** generates a fresh set of monsters (colors, fur, eyes, horns) and a band name; type your own name and it appears on stage.
- **Stage themes**: Neon Club, Sunset Fest, Cozy Basement.
- **● Record performance** captures the whole show — vertical 1080×1920 (9:16) with sound — and gives you an MP4/WebM file ready to post to TikTok.

## Notes

- Recording uses `MediaRecorder`; Chrome exports MP4, other browsers may export WebM (TikTok and most editors accept both).
- Only use music you have the rights to post.
