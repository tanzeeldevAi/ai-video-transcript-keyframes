<div align="center">

# Video Ref — Make AI Actually Understand Any Video

**Paste a video link. Get back a folder that Claude, ChatGPT or Cursor can read like a document.**

AI models cannot watch video. This turns any video — YouTube, Facebook, TikTok, Instagram,
Vimeo, or a file on your disk — into the two things they *can* read: a **timestamped transcript**
and **labelled keyframe contact sheets**. Then you can say *"build me something in this video's style"*
and the model is working from real reference material instead of guessing.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Windows%20%C2%B7%20macOS%20%C2%B7%20Linux-555)](#requirements)
[![Developed by Tanzeel](https://img.shields.io/badge/Developed%20by-Tanzeel-6C3EF5)](https://github.com/tanzeeldevAi)
[![Forked by notxcharles](https://img.shields.io/badge/Forked%20%26%20modified%20by-notxcharles-0A7EA4)](https://github.com/notxcharles)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

</div>

---

## What is this?

You find a video you love — a landing page walkthrough, a viral reel, a UI demo, a lecture — and
you want an AI to help you build something like it.

So you paste the link into Claude or ChatGPT. And it can't see it. It reads the title, guesses,
and gives you something generic.

**Video Ref fixes that.** Run one command:

```bash
python vref.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

…and about a minute later you have a folder like this:

```
library/how-i-built-my-landing-page/
  REFERENCE.md     <- start here, point your AI at this file
  transcript.md    <- every word, with timestamps
  transcript.txt   <- the same thing as plain text
  meta.json        <- title, channel, duration, description, URL
  sheets/          <- 3x3 grids of keyframes, each tile stamped with its timestamp
  frames/          <- every keyframe as a full-size image
```

Now you say:

> *"Read REFERENCE.md and the contact sheets, then build me a landing page in this style"*

and the model has the actual words **and** the actual visuals, tied together by timestamp.

```
Video URL  ──►  download  ──►  transcript  ──┐
                                             ├──►  REFERENCE.md  ──►  your AI
                └──►  keyframes  ──►  sheets ──┘
```

> **Nothing is uploaded anywhere.** The video is downloaded, processed on your machine, and
> deleted again. No account, no API key, no cloud service.

---

## What it gives you

| | |
|---|---|
| 📝 **Timestamped transcript** | Uses the platform's own captions when they exist — instant and exact |
| 🎙️ **Transcribes when there are none** | Falls back to `faster-whisper` locally, so silent-caption videos still work |
| 🖼️ **Labelled contact sheets** | Keyframes tiled 3x3, every tile stamped with its frame number and timestamp |
| 🎯 **Smart frame picking** | Samples across the whole video instead of grabbing the first N seconds |
| 🌍 **Works with most sites** | YouTube, Facebook, TikTok, Instagram, Vimeo, Twitter/X, direct MP4 links |
| 📁 **Local files too** | Pass a path instead of a URL and it works the same way |
| 🔒 **Login-walled videos** | Point it at an exported `cookies.txt` for private or age-gated content |
| 📋 **Queue a batch** | List several videos in a text file and let them run one after another while you do something else |
| 🧹 **Cleans up after itself** | The source video is deleted unless you ask to keep it |

---

## Requirements

Before you start, make sure you have:

- **[Python 3.9 or newer](https://python.org/downloads)** — while installing on Windows, tick
  **"Add Python to PATH"**
- **FFmpeg** — this is what cuts the frames. Install instructions are in Step 2 below.

That's it. There is no API key and no account to create.

> **Optional:** transcription of caption-less videos needs `faster-whisper`, which is in
> `requirements.txt`. The first time it runs it downloads a speech model (about 150 MB for
> `base`), then it is fast forever after.

---

## Install — step by step

It takes about **5 minutes**.

### Step 1 — Download

```bash
git clone https://github.com/notxcharles/ai-video-transcript-keyframes.git
```

No git? Click the green **Code** button above → **Download ZIP** → unzip it somewhere like
`D:\video-ref`.

### Step 2 — Install FFmpeg

This is the only step that isn't `pip install`. Pick your system:

**Windows** — open PowerShell and run:
```powershell
winget install Gyan.FFmpeg
```
Then **close and reopen** your terminal so it picks up the new PATH.

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg
```

Check it worked:
```bash
ffmpeg -version
```

If that prints a version number, you're good. If it says "not found", FFmpeg isn't on your PATH yet.

### Step 3 — Install the Python packages

From inside the project folder:

```bash
pip install -r requirements.txt
```

### Step 4 — Run it

```bash
python vref.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

Always put the URL **in quotes** — video links contain `&` and `?`, which your terminal will
otherwise try to interpret.

When it finishes it prints the path to your `REFERENCE.md`. Open that folder, drag it into Claude
Code or attach the sheets in the chat window, and you're done.

**That's it — you're running.** 🎉

---

## Options

| Option                 | What it does                                                                                                                                                                    |
|------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--name my-slug`       | Name the output folder yourself instead of using the video title                                                                                                                |
| `--frames 60`          | How many keyframes to pull (default `36`). More frames = more visual detail                                                                                                     |
| `--model small`        | Whisper model for videos with no captions: `tiny` · `base` · `small` · `medium`                                                                                                 |
| `--quality 1080`       | Max video height to download (default `720`). Raise it for UI detail, lower it for speed                                                                                        |
| `--keep-video`         | Keep the downloaded video file instead of deleting it                                                                                                                           |
| `--no-transcribe`      | Skip transcription entirely — visuals only, much faster                                                                                                                         |
| `--cookies-file path`  | Use an exported `cookies.txt` for login-walled videos                                                                                                                           |
| `--cookies chrome`     | Pull cookies straight from your browser (often blocked on Windows — see below)                                                                                                  |
| `--language fr`        | The language the video is spoken in. Only captions in that language are used; if the platform has none, Whisper transcribes in that language. [Language codes](#language-codes) |
| `--require-transcript` | Fail instead of carrying on when no transcript can be produced — useful for lectures                                                                                            |
| `--queue queue.txt`    | Run a list of vref commands one after another — see [Queue](#queue)                                                                                                             |

Examples:

```bash
# A design reference - lots of frames, skip the words
python vref.py "https://www.tiktok.com/@user/video/123" --frames 60 --no-transcribe

# A lecture - accurate words, few frames, and fail if there are no words
python vref.py "https://youtu.be/XXXXXXXXXXX" --frames 12 --model small --require-transcript

# A local file already on your disk
python vref.py "C:\Users\me\Videos\client-demo.mp4"
```

---

## Queue

Got a stack of videos? Put one vref command per line in a text file, for example `queue.txt` in
the project folder:

```
python vref.py "C:\Users\me\Lectures\Week 1.mp4" --model medium --language en --require-transcript

python vref.py "C:\Users\me\Lectures\Week 2.mp4" --model medium --language en --require-transcript
```

then start it and walk away:

```bash
python vref.py --queue queue.txt
```

Each line is written exactly as you'd type it in the terminal, so you can test a command on its
own first and then paste it in. The leading `python vref.py` is optional.

When it's finished you get a summary:

```
[queue] finished: 5 done, 1 failed (commented out in queue.txt), 0 left
```

How it behaves:

- **Checks first.** Before anything runs, every line is checked: options are spelled right,
  local files exist, FFmpeg and `faster-whisper` are installed, and no two lines would write to
  the same output folder. Any problems are listed and you choose whether to run the rest.
- **Done lines disappear.** Each command is removed from the file once it succeeds, so you can
  stop at any point (Ctrl+C) and run the queue again later to pick up where it left off.
- **Failed lines are commented out** with the reason, and the queue moves on:
  ```
  # FAILED 2026-10-08 14:32 - video file not found: C:\Users\me\Lectures\Week 3.mp4
  # python vref.py "C:\Users\me\Lectures\Week 3.mp4" --model medium
  ```
  Fix the line, remove the `# ` and run the queue again. The full output of every run is saved
  in `library/_logs/`.
- **Edit while it runs.** The file is re-read before each video, so you can add or reorder lines
  at any time.
- Blank lines and lines starting with `#` are ignored.
- `queue.txt` is in `.gitignore`, so your list of files never gets committed.

> **Tip:** the output folder is named after the video's file name (or title), and a new run
> replaces an existing folder with the same name. If different courses use the same file
> names — `Week 1.mp4` in two modules, say — give each line its own `--name`, like
> `--name ml-week-1`.

---

## Private or login-walled videos

Facebook reels, private YouTube videos and most Instagram content require a logged-in session.

Reading cookies straight out of Chrome (`--cookies chrome`) is blocked on modern Windows, so use
an exported cookie file instead:

1. Install the **"Get cookies.txt LOCALLY"** extension in your browser
2. Open the site you're logged into (facebook.com, youtube.com…) and export `cookies.txt`
3. Save it into the `cookies/` folder, named after the site: `facebook.txt`, `youtube.txt`,
   `instagram.txt`, or `default.txt`

The script picks the right file for the URL automatically. You never pass a flag.

If a download with a cookies.txt file fails, the script automatically retries **without** cookies. Sites
like YouTube rotate login cookies while the browser tab stays open, so an exported file can go
stale quickly (YouTube then says "The page needs to be reloaded"). 

If the retry works, you'll see `worked without cookies - your cookies file is probably stale`. 
You can usually just delete that file, because most public videos don't need cookies at all. 
If you do need them, export from a private/incognito window and close it straight afterwards, 
so the site doesn't rotate them.

> ⚠️ **A `cookies.txt` file is a live login to your account.** Anyone who gets it is logged in
> as you. The `cookies/` folder is already in `.gitignore` — keep it that way, and never share
> those files.

---

## Troubleshooting

<details>
<summary><b>"ffmpeg not found on PATH"</b></summary>

FFmpeg isn't installed, or your terminal was open before you installed it. Do Step 2, then
**close and reopen the terminal**. This causes most first-run problems.
</details>

<details>
<summary><b>The transcript is empty</b></summary>

The video had no captions and `faster-whisper` isn't installed. Run
`pip install faster-whisper`. If the video genuinely has no speech, this is correct behaviour —
you'll still get all the keyframes.

If a transcript matters (lectures, talks), add `--require-transcript`. The run then stops with
an error that says why, instead of quietly producing a folder with no words in it.
</details>

<details>
<summary><b>A queue line was commented out as FAILED</b></summary>

The comment above it says why, for example `video file not found` or an `unrecognized arguments`
typo. For the full output, open the matching file in `library/_logs/` (named by time and output
folder). Fix the command, remove the `# ` from the start of the line, delete the `# FAILED`
comment, and run `python vref.py --queue queue.txt` again.
</details>

<details>
<summary><b>"yt-dlp failed" / "Sign in to confirm you're not a bot"</b></summary>

The site wants a logged-in session. Export a `cookies.txt` and drop it in `cookies/` — see the
section above.

If you see *"The page needs to be reloaded"*, it's the opposite problem: your cookies file is stale.
The script already retries without cookies, and if that retry fails too, delete the file or
re-export it from a private window.
</details>

<details>
<summary><b>It's very slow on a long video</b></summary>

Transcription is the slow part. Three ways to speed it up:
`--no-transcribe` (skip it), `--model tiny` (faster, less accurate), or `--quality 480`
(smaller download). A 10-minute video with captions already available takes well under a minute.
</details>

<details>
<summary><b>Only part of the video got processed</b></summary>

Raise `--frames`. The default of 36 spreads across the whole video, so a 2-hour recording gets
one frame per ~3 minutes. For long content try `--frames 100`.
</details>

<details>
<summary><b>The URL didn't work in my terminal</b></summary>

Wrap it in quotes: `python vref.py "https://..."`. Without quotes, the `&` in most video URLs
cuts the command in half.
</details>

---

## Language Codes

| Code | Language         |
|---|------------------|
| af | Afrikaans        |
| am | Amharic          |
| ar | Arabic           |
| as | Assamese         |
| az | Azerbaijani      |
| ba | Bashkir          |
| be | Belarusian       |
| bg | Bulgarian        |
| bn | Bengali          |
| bo | Tibetan          |
| br | Breton           |
| bs | Bosnian          |
| ca | Catalan          |
| cs | Czech            |
| cy | Welsh            |
| da | Danish           |
| de | German           |
| el | Greek            |
| en | English          |
| es | Spanish          |
| et | Estonian         |
| eu | Basque           |
| fa | Persian          |
| fi | Finnish          |
| fo | Faroese          |
| fr | French           |
| gl | Galician         |
| gu | Gujarati         |
| ha | Hausa            |
| haw | Hawaiian         |
| he | Hebrew           |
| hi | Hindi            |
| hr | Croatian         |
| ht | Haitian Creole   |
| hu | Hungarian        |
| hy | Armenian         |
| id | Indonesian       |
| is | Icelandic        |
| it | Italian          |
| ja | Japanese         |
| jw | Javanese         |
| ka | Georgian         |
| kk | Kazakh           |
| km | Khmer            |
| kn | Kannada          |
| ko | Korean           |
| la | Latin            |
| lb | Luxembourgish    |
| ln | Lingala          |
| lo | Lao              |
| lt | Lithuanian       |
| lv | Latvian          |
| mg | Malagasy         |
| mi | Maori            |
| mk | Macedonian       |
| ml | Malayalam        |
| mn | Mongolian        |
| mr | Marathi          |
| ms | Malay            |
| mt | Maltese          |
| my | Myanmar (Burmese) |
| ne | Nepali           |
| nl | Dutch            |
| nn | Nynorsk          |
| no | Norwegian        |
| oc | Occitan          |
| pa | Punjabi          |
| pl | Polish           |
| ps | Pashto           |
| pt | Portuguese       |
| ro | Romanian         |
| ru | Russian          |
| sa | Sanskrit         |
| sd | Sindhi           |
| si | Sinhala          |
| sk | Slovak           |
| sl | Slovenian        |
| sn | Shona            |
| so | Somali           |
| sq | Albanian         |
| sr | Serbian          |
| su | Sundanese        |
| sv | Swedish          |
| sw | Swahili          |
| ta | Tamil            |
| te | Telugu           |
| tg | Tajik            |
| th | Thai             |
| tk | Turkmen          |
| tl | Tagalog          |
| tr | Turkish          |
| tt | Tatar            |
| uk | Ukrainian        |
| ur | Urdu             |
| uz | Uzbek            |
| vi | Vietnamese       |
| yi | Yiddish          |
| yo | Yoruba           |
| zh | Chinese          |
| yue | Cantonese       |

---

## How it works

1. **`yt-dlp`** downloads the video and any subtitle track the platform already has.
2. If subtitles exist they're parsed into timestamped segments — instant, and exactly what the
   creator wrote.
3. If they don't, **`faster-whisper`** transcribes the audio locally on your CPU.
4. **FFmpeg** pulls keyframes spread evenly across the full duration.
5. **Pillow** tiles them into 3x3 contact sheets and stamps each tile with its frame number and
   timestamp — that stamp is what lets the model line a visual up against a line of the transcript.
6. Everything is written into `REFERENCE.md`, which is the single file you point your AI at.

The whole thing is one Python file, `vref.py`, with no framework and no config. If you want to
change how frames are picked or how the sheets look, it's all in there.

---

## Contributing

Issues and pull requests are welcome — especially more site support, better frame selection
(scene-change detection instead of even sampling), and speed improvements.

## Acknowledgements

This project relies on **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** for downloading videos,
metadata and subtitle tracks from YouTube, Facebook, TikTok and the many other sites it supports.
`vref.py` runs it as a separate program, and all site support comes from yt-dlp. If a site stops
working, updating yt-dlp (`pip install -U yt-dlp`) is usually the fix. yt-dlp is released under
[the Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE).

## License

[MIT](LICENSE) — free to use, change and share. If it helps you, a ⭐ on the repo is appreciated.

---

<div align="center">

**Originally built by [@tanzeeldevAi](https://github.com/tanzeeldevAi) · Forked and modified by [@notxcharles](https://github.com/notxcharles)**

This is a fork of [tanzeeldevAi/ai-video-transcript-keyframes](https://github.com/tanzeeldevAi/ai-video-transcript-keyframes).

*video transcript · youtube transcript extractor · keyframe extraction · video to text · video summarizer
AI video analysis · video context for LLM · Claude video · ChatGPT video · yt-dlp · faster-whisper · ffmpeg
contact sheet generator · video reference · design reference from video · Python CLI*

</div>
