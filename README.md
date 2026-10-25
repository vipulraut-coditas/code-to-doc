# codedoc: AI documentation agent for any codebase

`codedoc` reads a code repository once and writes the standard software documents you choose:

| Document | id | File |
|---|---|---|
| Software Requirements Specification (SRS) | `srs` | `SRS` |
| User Manual | `user_manual` | `USER_MANUAL` |
| API Documentation | `api` | `API` |
| Technical / Developer Documentation | `technical` | `TECHNICAL` |
| Software Design Document (SDD) | `design` | `DESIGN` |

in the formats you choose:

| Format | id | Result |
|---|---|---|
| Markdown | `md` | `<name>.md` in the output folder |
| Word | `docx` | `<name>.docx` in the output folder |
| Google Docs | `gdoc` | a Google Doc in your Drive (link printed at the end), see [Google Docs setup](#google-docs-setup) |

Every document is written once and then converted, so extra formats cost no extra LLM calls.

It is built with **LangGraph** and is **LLM-agnostic**. It works with:

- an **API key** from Anthropic, OpenAI, xAI (Grok), Google (Gemini), Groq, DeepSeek, Mistral, or any OpenAI-compatible endpoint (OpenRouter, LM Studio, vLLM, Together and others)
- a **local model** through Ollama (free, no key)
- the **Claude Code CLI** you already have installed (uses your Claude Code login, no API key)

```
codedoc
? Which document do you want to generate?
    Software Requirements Specification (SRS)  -  features, functional & non-functional requirements, ...
    User Manual  -  step-by-step guide for end users: getting started, tasks, FAQ, troubleshooting
  > API Documentation  -  endpoints, parameters, request/response models, authentication, errors
    Technical / Developer Documentation  -  code structure, components, setup, configuration, conventions
    Software Design Document (SDD)  -  architecture, components, data flow, data design, design decisions
    All documents
    Several documents (choose with a checkbox) ...
v Will generate: API Documentation
? In which format should the documents be created?
    Markdown (.md)  -  plain text, great for Git repos and wikis
  > Word document (.docx)  -  open and edit in Microsoft Word / LibreOffice
    Google Docs  -  uploaded to your Google Drive (Google sign-in needed)
    All formats
    Several formats (choose with a checkbox) ...
v Format: Word document (.docx)
? Which project should I document? (folder path or git URL)  C:\work\my-app
? How do you want to connect to an LLM?
  > I have an API key (Anthropic, OpenAI, Grok, Gemini, Groq, ...)
    Use Claude Code already installed on this computer (no API key)
    Use a local model with Ollama (free, no API key)
...
Documents ready!
v API Documentation
    .docx        API.docx
Folder: C:\work\my-app\docs
```

## Install

```bash
# from GitHub (install the extra for your provider, or [all])
pip install "codedoc-agent[anthropic] @ git+https://github.com/<your-user>/code-to-srs-agent.git"

# for local development
git clone https://github.com/<your-user>/code-to-srs-agent.git
cd code-to-srs-agent
pip install -e ".[all,dev]"
```

Available extras: `anthropic`, `openai`, `xai`, `google`, `groq`, `deepseek`, `mistral`, `ollama`, `gdocs` (Google Docs output), `all`.
If you skip the extra, the setup wizard offers to `pip install` the right package for you.

## Usage

| Command | What it does |
|---|---|
| `codedoc` | Interactive. First asks which document(s) and which format(s) to generate (one, all, or several via a checkbox), then the project, the LLM settings and the output folder. |
| `codedoc setup` | Configure only the LLM (backend, provider, API key, fast and smart model) and save it. |
| `codedoc generate <repo> [--doc srs,api] [--format md,docx,gdoc] [-o out-dir]` | Runs without questions, using saved settings or environment variables. Good for CI. |
| `codedoc doctor` | Shows the current settings and tests the LLM connection. |
| `python -m codedoc` | Same as `codedoc`. |

`generate` options: `--doc` (comma-separated document ids from the table above, or `all`; default `srs`), `-f/--format` (comma-separated format ids, or `all`; default `md`), `-o/--output-dir` for `.md`/`.docx` files (default `<repo>/docs`), `--gdrive-folder` (Drive folder id for Google Docs; default My Drive), `--backend api\|claude-code`, `--provider`, `--fast-model`, `--smart-model`, `--max-files` (default 300), `--concurrency`, `--no-cache`, `--plain` (log lines only, no live bar; also enabled automatically when output is piped, or with `CODEDOC_PLAIN=1`).

`<repo>` can be a local folder or a git URL. A URL is shallow-cloned to a temp folder and deleted afterwards.

### Use it from Python

```python
from codedoc import generate_docs, Settings

settings = Settings(backend="api", provider="openai", fast_model="gpt-5-mini", smart_model="gpt-5.5")
result = generate_docs("path/to/repo", ["srs", "api", "user_manual"], "docs", settings, formats=["md", "docx"])
for doc in result.documents:
    print(doc.label, doc.outputs if doc.ok else f"failed: {doc.error}")  # {"md": path, "docx": path}
```

### Google Docs setup

Google Docs output uploads each document to your Google Drive, where Google converts it to a native Google Doc. It needs a one-time setup:

1. Install the extra: `pip install "codedoc-agent[gdocs]"` (the wizard offers to do this for you).
2. In the [Google Cloud console](https://console.cloud.google.com/), create or pick a project and enable the **Google Drive API**.
3. Under **OAuth consent screen**, choose *External* and add your Google account as a test user.
4. Under **Credentials**, create an **OAuth client ID** of type **Desktop app** and download the JSON.
5. Save it as `~/.codedoc/google_credentials.json`, or set `CODEDOC_GOOGLE_CREDENTIALS` to its path. The wizard can copy it there for you.

The first run opens your browser to sign in. The token is saved to `~/.codedoc/google_token.json` (delete it to sign out). codedoc only asks for the `drive.file` scope, so it can only see files it created itself. Sign-in happens **before** the analysis starts, so a setup problem shows up immediately, not after a long run. If an upload fails, the Markdown/Word files are still written.

## Configuration

Settings are saved to `~/.codedoc/config.json` (on Windows: `C:\Users\<you>\.codedoc\config.json`).
API keys are **not** saved unless you explicitly agree. The recommended approach is to put the key in an environment variable or in a `.env` file in the folder where you run `codedoc`:

| Provider | Key variable |
|---|---|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| xAI (Grok) | `XAI_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` |
| Groq | `GROQ_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| OpenAI-compatible | `CODEDOC_COMPAT_API_KEY` (+ base URL) |

Environment overrides: `CODEDOC_BACKEND`, `CODEDOC_PROVIDER`, `CODEDOC_FAST_MODEL`, `CODEDOC_SMART_MODEL`, `CODEDOC_BASE_URL`, `CODEDOC_HOME`.

**Two models?** The *fast* model summarises every file, so it makes many calls and should be a cheap model. The *smart* model reasons over the whole system once per document, so it should be your strongest model. You can use the same model for both.

## How it works

```
START → scan → summarize_file ×N → group_modules → summarize_module ×M → plan_documents → write_document ×K → END
        (no LLM)  (parallel, fast,     (no LLM)       (parallel, fast)        (no LLM)        (parallel, smart model,
                   cached)                                                                    one per chosen document)
```

1. **scan** walks the repo, respects `.gitignore`, skips `node_modules`, builds, lock files and binaries, and **never reads secrets** (`.env`, keys, credentials). It detects the tech stack and ranks files by business value (README, routes, models and services before tests).
2. **summarize_file** runs in parallel with LangGraph `Send` (map step). Results are cached by file hash, so a re-run only pays for changed files.
3. **summarize_module** merges file summaries into feature areas (reduce step).
4. **write_document** runs once per chosen document, in parallel, with a document-specific prompt and schema (the SRS gets actors, FR/NFR with priority, confidence and sources; the API doc gets endpoints, parameters and data models; and so on). The structured result is rendered to Markdown deterministically, without an LLM. If one document fails, the others are still written.

Summaries capture both the business view and technical facts (endpoints, public interfaces, configuration, dependencies), so every document type is written from the same single pass over the code.

Structured output uses JSON-in-prompt plus Pydantic validation with one automatic repair retry. This works on **every** provider, including models without tool calling and the Claude Code CLI.

An example output is in [`docs/example-SRS-library-app.md`](docs/example-SRS-library-app.md).
See [`docs/ARCHITECTURE_mr.md`](docs/ARCHITECTURE_mr.md) for a detailed walkthrough (in Marathi).

## Project layout

```
src/codedoc/
  cli.py              commands
  progress_ui.py      step-by-step log of every file/module + live progress bar
  wizard.py           interactive questions
  config.py           settings file and env overrides
  providers.py        provider registry (add a provider here)
  llm.py              LLM factory: the only provider-aware code
  llm_claude_cli.py   Claude Code CLI wrapped as a LangChain chat model
  scanner.py          repo walk, filtering, ranking (no LLM)
  graph.py            LangGraph workflow and nodes
  prompts.py          all prompts
  schemas.py          Pydantic output schemas
  structured.py       provider-independent JSON output
  doctypes.py         document-type registry (add a document type here)
  formats.py          output formats: Markdown, Word (.docx), Google Docs upload
  render.py           Markdown renderers, one per document type
  cache.py            file-summary cache
  api.py              generate_docs() public API
tests/                pytest suite (uses a fake LLM, no network)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Privacy

File contents are sent to the LLM you choose. Secret-looking files are skipped, but review what your repository contains before using a third-party API on confidential code. For fully local processing, use Ollama.

## License

MIT
