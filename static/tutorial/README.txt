This Is Fast — tutorial walkthrough media
=========================================

The onboarding dialog shown on -3M / This Is Fast products contains a media
slot for a short looping walkthrough of the configurator workflow:

    Upload Artwork → Position/Scale → Select PMS Color → See Mockup Update
    → Review Finished Configuration

The walkthrough in this folder is a screen recording of the real configurator
performing that workflow — a genuine upload, genuine positioning, a genuine PMS
selection and the live mockup responding. Only the step captions and the pointer
were overlaid. Nothing in it is a mock-up, so customers are never shown behavior
the application does not have.

    this-is-fast-walkthrough.gif   860x484, ~16s, 284 KB  (in use)
    this-is-fast-walkthrough.mp4   900x506, ~16s, 195 KB  (same recording)

TUTORIAL_MEDIA in configurator.html is set to the GIF. To serve the MP4 instead,
set type to "video" and point src at the .mp4 — nothing else changes.

RE-RECORDING AFTER UI CHANGES
The recording will drift as the interface evolves. Re-record it by driving the
running app and capturing frames, then encode with ffmpeg's palette pipeline:

    ffmpeg -framerate 16 -i frames/f%04d.png \
      -vf "fps=12,scale=860:-2:flags=lanczos,palettegen=max_colors=112:stats_mode=diff" pal.png
    ffmpeg -framerate 16 -i frames/f%04d.png -i pal.png \
      -lavfi "fps=12,scale=860:-2:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
      -loop 0 this-is-fast-walkthrough.gif

The diff_mode/stats_mode flags matter: a naive GIF export of the same frames
came out at 14 MB because the photographic mockup defeats plain quantization.


To drop in the finished asset
-----------------------------

1. Save the recording into this folder, e.g.

       static/tutorial/this-is-fast-walkthrough.gif

2. Open static/configurator.html and find TUTORIAL_MEDIA near the top of the
   script block (search for "TUTORIAL_MEDIA"). Change:

       const TUTORIAL_MEDIA = {
         type: "placeholder",
         src:  "/static/tutorial/this-is-fast-walkthrough.gif",
         ...
       };

   to:

       const TUTORIAL_MEDIA = {
         type: "gif",
         src:  "/static/tutorial/this-is-fast-walkthrough.gif",
         alt:  "Upload artwork, position it, choose a PMS ink, preview the product",
       };

   That is the only change required — the tutorial UI itself does not need to
   be touched.

3. For an MP4 instead of a GIF, use:

       const TUTORIAL_MEDIA = {
         type:   "video",
         src:    "/static/tutorial/this-is-fast-walkthrough.mp4",
         poster: "/static/tutorial/this-is-fast-poster.jpg",   // optional
         alt:    "…",
       };

   Video is rendered muted, looping, autoplaying and inline, with controls.


Notes
-----

* The media area is 16:9 and caps at 280px tall. Record at 16:9 (1280×720 is
  plenty) and keep the file small — a GIF over ~5 MB will feel slow on mobile.
* Keep it short and focused on the five steps. It should demonstrate the
  workflow, not explain every control.
* If the configured file is missing at runtime, the dialog falls back to the
  labeled placeholder rather than showing the customer a broken image.
