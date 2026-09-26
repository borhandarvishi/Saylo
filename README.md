# Saylo

A Telegram bot that reads a short message aloud.

1. Choose **English** or **Spanish**.
2. For English, choose **American** or **British**.
3. Choose **Translate & speak**.
4. Send up to 500 characters, in any language.

[Jev](https://openrouter.ai/typesafe/jev-1.13) checks whether the text is already fully in that language. If it is, [Kokoro](https://github.com/hexgrad/kokoro) reads it. If Jev says `other`, [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash) translates it first. Kokoro runs on your machine and costs nothing. **Usage** shows the Jev and translation spend so far.

## Run

Python 3.10, 3.11, or 3.12. Kokoro does not install on 3.13 or newer. `ffmpeg` turns the audio into a Telegram voice message. Without it, the bot sends a wav file instead.

```bash
brew install ffmpeg
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the two keys
python -m saylo
```

The first spoken message downloads Kokoro. Later messages reuse it.

## Change

| What | Where |
| --- | --- |
| Voices, models, 500-character limit | `saylo/config.py` |
| Jev's one-line question | `saylo/decide.py` |
| Buttons and chat flow | `saylo/bot.py` |

`/usage` is the same panel as the Usage button. Costs are stored in `data/usage.json`.
