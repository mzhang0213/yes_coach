# Yes Coach!
Welcome to your new LOL coach - a real-time AI assistant that watches your game and gives you game advice on the fly!

The backbone of the app runs in Python using the Riot Live Client API for real-time game state and PyQt6 for the overlay UI all powered by Gemini for coaching intelligence. It gets live champion stats, KDA, gold, game time >> feeds it to Gemini for instant macro-level coaching advice.

## Quickstart

Install dependencies:
```bash
pip install -r requirements.txt
pip install -q -U google-genai
```

Set your Gemini API key:
```bash
export GEMINI_API_KEY=your_key_here
```

Run the app:
```bash
python -m server.main
```

On launch, a dimmed screen overlay appears with a crosshair - click to place the "Ask Coach!!" button wherever you want on screen.

## How It Works

1. **Button Placement** - on startup, pick where you want the coaching button on your screen
2. **Hover to Activate** - hover over the "Ask Coach!!" button to trigger a radial bloom animation; hold until it fills
3. **Side Tabs Unfurl** - once triggered, three suggestion tabs appear on the left and a custom prompt tab on the right
4. **Live Coaching** - the app pulls your live game state from the Riot Client API, compresses it, and sends it to Gemini for instant advice
5. **Session Memory** - the coach remembers your last game and carries context across sessions

## Configure Gemini

The app uses Google's Gemini API for coaching intelligence. You will need a Gemini API key.

1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **Create API Key** and select a project
3. Copy the key and set it as an environment variable or add it to a `.env` file:
```bash
GEMINI_API_KEY=your_key_here
```

> The default model is `gemini-2.0-flash` for fast, cheap live polling. You can swap models in `server/resources/gemini.py` for stronger reasoning at higher cost.

## Requirements

- Python 3.10+
- League of Legends running (the Riot Live Client API is only available during an active game)
- Gemini API key
- macOS (PyQt6 overlay is tuned for macOS screen capture)
