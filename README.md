# Voice AI Phone System

A small voice-call pipeline split across two Python processes: an asyncio bridge that handles live call audio, and a FastAPI server that holds the AI agent. Asterisk connects them to a SIP phone.

```
Phone (SIP ext 101) ⇄ Asterisk ⇄ AudioSocket TCP :9093 ⇄ bridge ──HTTP──▶ ai-server /chat ──▶ Gemini + memory
                                                          │
                                                          └─ Deepgram (STT over WebSocket, TTS over HTTP)
```

## 1. Starting a call

There are two ways in:

- **Dial 200 from the phone.** `extensions.conf` answers and runs `AudioSocket(<uuid>, localhost:9093)`. Asterisk then opens a TCP connection to the bridge.
- **Agent-triggered.** `voice_mcp.py` (`call_me`, `call_extension`) sends `POST /trigger/call` to the ai-server with an API key. `triggers.py` logs into Asterisk's AMI socket and sends an `Originate` action. It rings `PJSIP/<ext>` and, when answered, runs the same `AudioSocket` application. So outbound calls end up in the same bridge.

## 2. The bridge (`bridge/`)

`__main__.py` runs an asyncio TCP server on port 9093. It creates one `CallSession` per connection, and exits at startup if `DEEPGRAM_API_KEY` is missing.

**Wire protocol (`protocol.py`)**
- Each frame is `[type 1B][length 2B][payload]`.
- The types are UUID `0x01`, AUDIO `0x10`, HANGUP `0x00` and ERROR `0xFF`.
- Audio is 8 kHz, 16-bit mono PCM. Each frame is 320 bytes, which is 20 ms.

**Session (`session.py`)**
- The first frame must be the call UUID, which becomes the `session_id`.
- Three tasks then run concurrently, and whichever finishes first ends the call:
  - `_rx_loop` reads frames from Asterisk. The first audio frame opens the Deepgram STT connection and starts the greeting. After that, audio frames go into a queue.
  - `_stt_loop` drains that queue and forwards the audio to Deepgram.
  - `_idle_watchdog` hangs up after 20 seconds with no activity.
- The state machine is `IDLE → LISTENING → PROCESSING → SPEAKING → LISTENING`, plus a `BARGE_IN` state.

**Speech-to-text (`stt.py`)**
- It streams audio to Deepgram's `nova-3` model.
- A turn ends when Deepgram sends `speech_final`. A fallback `UtteranceEnd` fires after 1 second of silence.
- Both call `_on_utterance_end`. The session ignores any second firing while it's already processing.

**Responding**
- `_respond` calls the ai-server with `POST /chat {text, session_id, channel: "phone"}`.
- It then sends the reply text to Deepgram TTS (`aura-asteria-en`), which returns raw 8 kHz PCM.
- `_play_text` cuts that PCM into 320-byte frames and writes them back through the socket.

**Barge-in**
If Deepgram signals speech start while the bot is in `SPEAKING`, the session cancels the speak task. TTS stops and it goes back to listening.

**Greeting**
On connect, the bridge sends the text `[call_connected]` to the brain. The brain swaps it for "Please greet me warmly…" and the reply is spoken.

## 3. The brain (`ai-server/`)

`routers/chat.py` exposes `POST /chat`, and `brain/agent.py` handles each turn. Each turn runs in this order:

1. Search Mem0 long-term memory for relevant facts.
2. Load the last 12 messages for that session from SQLite.
3. Build a system prompt that includes the memories. On the phone channel it asks for one or two short sentences with no formatting.
4. Call the LLM with a tool schema. The tools create and search notes. It loops up to 5 times while the LLM keeps requesting tools.
5. Save the user and assistant messages to SQLite.
6. Send the exchange to Mem0 in the background.

## Known limitations

Things that are incomplete or unverified:

- **Responses are not streamed.** The bridge waits for the full LLM reply before starting TTS, so per-turn latency is LLM time plus TTS time. Sentence-by-sentence streaming is planned (`_SENTENCE_END` in `session.py` is a placeholder for it).
- **Barge-in is unreliable.** `_rx_loop` only forwards audio to Deepgram while the state is `LISTENING` or `BARGE_IN`, so Deepgram may never hear the caller interrupt during `SPEAKING`. The cancel logic exists but the audio path to trigger it likely needs fixing.
- **TTS playback is not paced.** Frames are written to Asterisk as fast as Deepgram returns them, with no 20 ms timing.
- **Greeting state edge case.** If the greeting is interrupted, the session state can stay in `PROCESSING` until the next turn resets it.
- **No scheduled wakeup calls.** The earlier scheduler and wakeup agent were removed in the move from Docker/AGI to the bridge. Calls are triggered on demand only.
- **Legacy code.** `routers/converse.py` (the old HTTP STT-then-TTS path) is still registered but unused by the bridge, and `config.py` still has settings from the old design (Ollama, Whisper, VM/SSH).
- **No automated tests.**
- **Single user.** Memory uses one default `user_id`, and the SIP/AMI setup assumes a single extension.

## Setup

Secrets live in a `.env` file (gitignored):

| Variable | Used by | Purpose |
|---|---|---|
| `DEEPGRAM_API_KEY` | bridge, ai-server | STT and TTS |
| `GEMINI_API_KEY` | ai-server | LLM and Mem0 embeddings |
| `AI_SERVER_API_KEY` | ai-server | auth for `/trigger/call` |
| `AMI_HOST`, `AMI_USER`, `AMI_SECRET` | ai-server | Asterisk Manager login |
| `BRAIN_URL` | bridge | ai-server address (default `http://localhost:8000`) |
| `VOICE_BRIDGE_URL`, `VOICE_BRIDGE_API_KEY`, `VOICE_EXTENSION` | `voice_mcp.py` | MCP client settings |

## Asterisk config

`asterisk/etc/pjsip.conf` and `manager.conf` hold SIP passwords and the server IP, so they are gitignored. Copy `pjsip.conf.example` and `manager.conf.example` to those names and fill in real values; `deploy.sh` syncs them to the VPS.

## Deploy

`deploy/setup_vps.sh` provisions the VPS. `deploy/deploy.sh [bridge|ai-server|asterisk|all]` rsyncs the code and restarts the systemd services (`bridge.service`, `ai-server.service`).
