# codedoc: Architecture समजून घेऊया (मराठीत)

हा document code वाचताना सोबत ठेवा. प्रत्येक file **का** आहे आणि कुठला GenAI concept शिकवते, ते इथे दिलं आहे.

---

## १. मोठं चित्र

```
User ──► codedoc (CLI)
           │
           ├── wizard.py   → प्रश्न विचारतो (कोणते documents? API key की Claude Code? कोणता LLM? models? output?)
           ├── config.py   → उत्तरं ~/.codedoc/config.json मध्ये save करतो
           ├── llm.py      → settings वरून योग्य LLM object बनवतो
           ├── doctypes.py → कोणते documents बनवता येतात (SRS, User Manual, API, Technical, Design)
           └── api.py      → generate_docs() → LangGraph graph चालवतो → निवडलेले documents लिहितो
```

**महत्त्वाचा नियम:** फक्त `llm.py` ला माहीत असतं की कोणता provider वापरला जातोय. बाकी सगळा code फक्त `BaseChatModel` ओळखतो.

---

## २. LangGraph workflow (`graph.py`)

```
START
  → scan                  (LLM नाही)  repo मधल्या files शोधतो, secrets वगळतो
  → summarize_file × N    (fast model, parallel)   ← MAP
  → group_modules         (LLM नाही)  folder नुसार गट करतो
  → summarize_module × M  (fast model, parallel)   ← REDUCE (पहिला टप्पा)
  → plan_documents        (LLM नाही)  join point
  → write_document × K    (smart model, parallel)  ← निवडलेल्या प्रत्येक document साठी एक branch
                          (+ LLM नाही: Markdown render)
END
```

Repo **एकदाच** वाचली आणि summarise केली जाते; SRS, User Manual, API Doc, Technical Doc आणि
Design Doc हे सगळे त्याच module summaries वरून लिहिले जातात. एखादा document fail झाला तरी
बाकीचे लिहिले जातात.

नवीन document type जोडायचा असेल तर: `schemas.py` मध्ये schema, `prompts.py` मध्ये prompt,
`render.py` मध्ये renderer आणि `doctypes.py` मध्ये एक `DocType(...)` entry.

### शिकण्यासारखे concepts

| Concept | कुठे | सोप्या भाषेत |
|---|---|---|
| **State + Reducer** | `state.py` | `Annotated[list, operator.add]` असल्यामुळे parallel branches चे results overwrite न होता list मध्ये जोडले जातात. |
| **Send API (fan-out)** | `fan_out_files()` | प्रत्येक file साठी एक `Send(...)`. LangGraph ते parallel मध्ये चालवतो, आणि `max_concurrency` एका वेळी किती चालतील ते ठरवतो. |
| **Node input_schema** | `add_node(..., input_schema=FileTask)` | Send ने आलेला छोटा payload (एक file) node ला मिळतो, पूर्ण state नाही. |
| **Map-Reduce** | file → module → system | मोठी repo एका context window मध्ये बसत नाही, म्हणून ती टप्प्याटप्प्याने लहान करायची. |
| **Dependency Injection** | `AgentDeps` | LLMs आणि cache बाहेरून दिले जातात, त्यामुळे tests मध्ये fake LLM वापरता येतो. |
| **Deterministic steps** | `scan`, `render.py` | जे काम साधं Python करू शकतं ते LLM कडून करून घेऊ नका. ते स्वस्त, जलद आणि अचूक असतं. |

---

## ३. सगळ्या LLMs साठी एकच code (`llm.py`, `providers.py`)

- `init_chat_model(model, model_provider="xai")` हे LangChain चं universal function आहे. Grok, GPT, Claude, Gemini, Groq, Ollama सगळ्यांसाठी एकच call.
- नवीन provider जोडायचा असेल तर `providers.py` मध्ये एक `Provider(...)` entry टाका. बाकी code बदलायची गरज नाही.
- `compat` provider म्हणजे कुठलाही OpenAI-compatible API (OpenRouter, LM Studio, vLLM). फक्त `base_url` बदलायचा.

### Claude Code adapter (`llm_claude_cli.py`)

`claude -p` (headless mode) ला `BaseChatModel` मध्ये wrap केलं आहे. हा **Adapter pattern** आहे, म्हणजे graph साठी Claude Code हा इतर कुठल्याही model सारखाच दिसतो.

- `--tools ""` मुळे Claude Code कुठलेही tools (files वाचणं, commands चालवणं) वापरत नाही. तो फक्त उत्तर देतो.
- तो एका रिकाम्या temp folder मध्ये चालतो, त्यामुळे इतर files कडे जाण्याचा प्रश्नच नाही.
- जुन्या CLI version मध्ये नवीन flags नसतील तर तो आपोआप जुन्या पद्धतीने retry करतो.

---

## ४. Structured output सगळ्या providers वर (`structured.py`)

`with_structured_output()` (tool calling) प्रत्येक model support करत नाही. म्हणून ही पद्धत वापरली आहे:

1. Prompt मध्ये JSON schema देतो.
2. उत्तरातून JSON काढतो (```json fences किंवा जास्तीचा मजकूर असला तरी चालतो).
3. Pydantic ने validate करतो.
4. Fail झालं तर error सांगून एकदा "fix this JSON" असा retry करतो.

---

## ५. Cost आणि speed

- **दोन models:** fast model प्रत्येक file साठी (खूप calls, म्हणून स्वस्त model), आणि smart model शेवटी एकदाच (म्हणून strong model).
- **Cache (`cache.py`):** file चा hash (content + model + prompt version) काढला जातो. File बदलली नसेल तर पुढच्या run मध्ये LLM call होत नाही.
- **एकाच file चा module:** merge करायला काही नाही, त्यामुळे तिथे LLM call skip होतो.
- **`--max-files`:** मोठ्या repo मध्ये फक्त सर्वात महत्त्वाच्या N files घेतल्या जातात (README, routes, models, services आधी आणि tests नंतर).

---

## ६. Security

- `.env`, `*.pem`, `*secret*`, `*credential*` अशा files कधीच LLM कडे पाठवल्या जात नाहीत.
- API key फक्त user ने "हो" म्हटलं तरच save होते. नाहीतर environment variable किंवा `.env` वापरा.

---

## ७. पुढे काय शिकू शकता (roadmap)

1. **LangGraph Studio:** `langgraph dev` वापरून graph visually debug करा.
2. **Human-in-the-loop:** `write_document` नंतर `interrupt()` टाका, म्हणजे review करून मगच document save होईल.
3. **Critic node:** smart model कडून SRS तपासून घ्या (missing requirements, duplicates) आणि loop करा.
4. **FastAPI service:** `generate_docs()` ला REST endpoint मागे ठेवा.
5. **GitHub Action:** प्रत्येक merge नंतर `codedoc generate . --doc all -o docs` आपोआप चालेल.
6. **Output formats:** Markdown वरून `.docx` किंवा PDF export.
