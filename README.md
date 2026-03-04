<img width="1115" height="276" alt="image" src="https://github.com/user-attachments/assets/54c8a3a2-2be6-4d96-93c1-b792216e1c0c" />

<img width="1115" height="261" alt="image" src="https://github.com/user-attachments/assets/136fa17a-3ad1-4f8b-8fa0-8b415db75191" />

## Setup

### Prerequisites

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **Claude Code CLI** installed and on PATH

### Windows

```bash
git clone <repo-url> && cd voice-input
setup.bat
```

Or manually: `python install_plugin.py`

### macOS / Linux

```bash
git clone <repo-url> && cd voice-input
chmod +x setup.sh && ./setup.sh
```

Or manually: `python3 install_plugin.py`

#### Platform notes

| Platform | Hotkey daemon | Notes |
|----------|--------------|-------|
| Windows  | Full support | Works out of the box |
| Linux    | Requires root | `keyboard` library needs root for global hotkeys. Use `/voice` command as alternative |
| macOS    | Not supported | Use `/voice` command instead |

### After install

1. **Restart Claude Code** to activate the plugin
2. Press `Alt+Q` to start recording (Windows), or type `/voice` in Claude Code

## Usage

| Action | Description |
|--------|-------------|
| `Alt+Q` | Toggle recording on/off (hotkey) |
| `/voice` | Record via Claude (all platforms) |
| `/voice start` | Start the hotkey daemon |
| `/voice restart` | Restart the hotkey daemon |
| `/voice kill` | Stop all voice processes |

## Configuration

Edit `config.json` in the plugin directory to change:

- **Hotkey binding** — `hotkey.binding` (default: `alt+q`)
- **Transcription backend** — `transcriber.backend` (`faster_whisper` or `openai_api`)
- **Model size** — `transcriber.faster_whisper.model_size` (default: `base`)
- **Auto-send keywords** — `hotkey.auto_send_keywords`
- **Auto-stop on silence** — `recording.auto_stop_on_silence`
