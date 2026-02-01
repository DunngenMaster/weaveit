# WeaveIt

A smart AI assistant that remembers your work context and learns the best way to help you over time.

## What it does

WeaveIt is an Electron app that works alongside your browser. When you're chatting with AI assistants like ChatGPT or Claude, it watches what you're working on and builds a memory of your context. Then when you ask questions, it automatically includes relevant information from your recent work so you get better, more personalized answers.

The system learns from every interaction. It tracks which strategies work best for different types of tasks and automatically adapts to give you better results over time.

## Getting started

You'll need Python 3.8 or higher and Node.js installed.

### 1. Set up the backend

Open a terminal and navigate to the backend folder:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy the `.env.example` file to `.env` and add your API keys:
- Redis URL and API key (for memory storage)
- Weaviate URL and API key (for vector search)
- Gemini API key (for AI features)
- BrowserBase credentials (optional, for browser automation)

Start the backend server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Set up the Electron app

Open a new terminal and navigate to the electron folder:

```bash
cd electron
npm install
```

Start the Vite development server:

```bash
cd vite
npm run dev
```

In another terminal, start the Electron app:

```bash
cd electron
npx electron .
```

## How it works

The system has three main parts:

**Backend API** - A FastAPI server that handles memory storage, context building, and learning. It runs on port 8000.

**Electron App** - A desktop application that captures your browsing activity and sends it to the backend. It connects to your local Vite dev server.

**Learning Engine** - A background worker that processes events and uses a multi-armed bandit algorithm to learn which strategies work best for different situations.

## What's the learning about?

The system tracks four different strategies for helping you:
- Clarify First: Ask questions to understand what you need
- Three Variants: Generate multiple options to choose from
- Template First: Start with a proven template
- Stepwise: Break tasks into smaller steps

It measures which strategy gives the best results for each type of task you do, then automatically picks the winning approach next time.

## Project structure

- `backend/` - Python FastAPI server and learning engine
- `electron/` - Electron desktop app
- `electron/vite/` - React frontend
- `Notebook/` - Jupyter notebooks for experiments

## Common issues

**Backend won't start**: Make sure you've activated the virtual environment and installed all requirements. Check that your `.env` file has all the required API keys.

**Electron can't connect**: The Electron app needs the Vite dev server running first. Make sure you see "Local: http://127.0.0.1:5174" in the Vite terminal before starting Electron.

**Windows environment errors**: If you see "NODE_ENV is not recognized", use PowerShell and set environment variables like this: `$env:NODE_ENV="development"`

## Contributing

The codebase follows a streams-based architecture where all events flow through Redis Streams. The stream consumer handles business logic asynchronously with automatic retries and dead letter queue support.

When adding new features, follow the existing patterns in the events and stream_consumer modules.
