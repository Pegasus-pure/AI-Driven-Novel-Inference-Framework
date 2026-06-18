# Round — AI-Driven Novel Inference Framework

<div align="center">

[![CN](https://img.shields.io/badge/简体中文-README-red)](README.md) [![EN](https://img.shields.io/badge/English-README-blue)](README_EN.md)

**Universal AI Novel Inference Framework — Import a completed novel, AI-driven dynamic narrative**

[![Godot](https://img.shields.io/badge/Godot-4.6-%23478cbf?style=flat&logo=godot-engine)](https://godotengine.org)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20%2F%20DeepSeek%20%2F%20OpenAI-orange)]()
[![MCP](https://img.shields.io/badge/MCP-38%20Tools-green)]()
[![MaNA](https://img.shields.io/badge/MaNA-v4-blue)]()

</div>

---

## Project Overview

**Round** is an AI-driven novel inference framework built on Godot 4.x.

Players can import any completed novel, and the system automatically extracts the world-setting, characters, and plot structure via LLM. The player then experiences the story as a "transmigrated background character" — revisiting classic canon scenes while also diverging from the main plot and exploring unknown side stories through choices.

The project is inspired by miHoYo's *Varsapura* (City of Rain), targeting two audiences: "Revisitors" and "Discoverers".

### Core Experience

- **Import & Play**: Drop in a completed novel text, AI automatically parses world-setting, characters, and plot
- **Background Character Perspective**: Player acts as an obscure background character, experiencing the unique "canon observer" viewpoint
- **Dynamic Narrative**: MaNA v4 multi-agent narrative engine, supporting Best-of-3 sampling, iterative refinement, and multi-view synthesis
- **Deviation System**: World deviation tracking measures the gap between player actions and canon, with 5 deviation levels mapping to different narrative strategies
- **Vector Memory**: Semantic memory retrieval based on Ollama Embedding, giving narrative long-term coherence
- **Terminal-Style UI**: Retro terminal interface, immersive text adventure experience

---

## Technical Architecture

### Tech Stack

| Layer | Technology | Description |
|------|-----------|-------------|
| Game Engine | Godot 4.6 | Terminal-style UI, scene system |
| Narrative Engine | MaNA v4 (Multi-Agent LLM Pipeline) | 5-layer pipeline + v4 enhancement features |
| LLM Integration | Provider Abstraction Layer | Unified Ollama / DeepSeek / OpenAI interface |
| Vector Memory | Ollama Embedding (qwen3-embedding:0.6b) | Semantic storage and retrieval |
| Communication Protocol | MCP (Model Context Protocol) | Godot Bridge MCP, 38 tools |
| Prompt Engineering | 15 professional prompt files | Multi-agent separation, JSON Schema output |

---

## MaNA v4 Architecture

MaNA (Multi-Agent Narrative Architecture) is the core narrative engine of the current project.

### New Features in v4 vs v3

> ⚠️ **Implementation Status Note**: Some v4 features have code written and integrated into the pipeline, but have not been fully tested in actual novel import scenarios due to being disabled by default. The Phase 1 import pipeline's 5-Pass process and manual correction UI have also not been implemented.

| Feature | Codename | Description | Default | Implementation Status |
|---------|-----------|-------------|---------|----------------------|
| Iterative Refinement Loop | `refinement` | Composer output → Auditor check → rewrite if unsatisfied | ✅ On | ⚠️ Integrated into pipeline, not fully tested |
| Multi-Sample Self-Consistency | `best_of_3` | Director runs 3 times in parallel, PlanScorer selects the best | ✅ On | ⚠️ Integrated into pipeline, not fully tested |
| Micro Oracle | `micro_oracle` | One-sentence quality feedback after each beat, injected into next beat's Director | ❌ Off | ⚠️ Code implemented and integrated, off by default, not tested |
| Dynamic Tier | `dynamic_tier` | Auto-adjust temperature / max_tokens based on scene complexity | ✅ On | ⚠️ Integrated into pipeline, not fully tested |
| Multi-View Synthesis | `multi_view` | plot-driven + character-driven dual-view fusion | ✅ On | ⚠️ Integrated into pipeline, not fully tested |
| Semantic Canon Selection | `semantic_selection` | LLM filters most relevant background info for current scene | ❌ Off | ⚠️ Code implemented and integrated, off by default, not tested |
| Character Anti-Rules | `anti_rules` | Counter-example rules to constrain character behavior, prevent drift | ❌ Off | ❌ Code framework exists, not integrated into pipeline |
| Vector Memory | `vector_memory` | Ollama Embedding semantic retrieval of historical scenes | ❌ Off | ⚠️ Code implemented and integrated, off by default, not tested |

> v4 master switch: When `[v4] enabled=false` in `manana_config.cfg`, fully fall back to v3 compatible path; each sub-feature can be independently toggled.

---

### Pipeline Overview

```
L0: ContextBuilder         → Build scene context (characters/threads/locations/history)
     ├─ [v4] CanonSelector    → Semantic filtering of most relevant Canon (optional)
     └─ [v4] VectorMemory    → Semantic retrieval of historical scenes (optional)
L1: SceneDirector           → Beat director, decides current beat direction
     ├─ [v4] Best-of-3      → Parallel sample 3 times, Scorer selects best (optional)
     └─ [v4] Multi-View     → plot + character dual-view fusion (optional)
L2R1: MotivationEngine     → Motivation analysis (N characters in parallel)
L2R2: DialogueWeaver       → Dialogue generation (N characters in parallel)
      ActionDirector         → Action choreography (N characters in parallel)
L3: SceneComposer          → Weave each Agent's output into complete narrative text
     └─ [v4] Refinement     → Auditor check → rewrite if unsatisfied (optional)
L3b∥L4a: ConsistencyAuditor → Consistency audit (character drift / factual contradiction / rule violation / continuity break)
          StateExtractor      → Extract world state changes from narrative text (parallel)
L4b: ThreadManager         → Manage narrative threads (create/advance/close)
L5: ReflectionOracle       → Global narrative health assessment every 5 beats
      [v4] MicroOracle      → One-sentence quality feedback per beat (optional)
```

### LLM Calls Per Beat

**v3 baseline**: 5 + 3N (N = number of appearing characters), 3 serial rounds

**After v4 enabled**:
- `best_of_3`: L1 call count ×3 (3 parallel samples)
- `multi_view`: L1 call count ×2 (plot + character dual views)
- `refinement`: L3 may trigger 1-2 rewrite loops
- Actual call count varies dynamically, can reach 3-4× the v3 baseline in complex scenes

---

### Three-Tier Model Allocation

| Tier | Temperature | max_tokens | Timeout | Assigned Agents |
|------|-------------|------------|---------|-----------------|
| **Strong** | 0.5 | 4096 | 120s | Director / Composer / Oracle / PlanSynthesizer |
| **Medium** | 0.7 | 2048 | 120s | Motivation / DialogueWeaver / Auditor / ThreadManager |
| **Light** | 0.8 | 512 | 60s | ActionDirector / StateExtractor / PlanScorer / MicroOracle / CanonSelector |

> Current model: qwen3.5:9b (Ollama), same model across all tiers, behavior differentiated via temperature / max_tokens

---

### v4 Key Designs

#### P0-1: Iterative Refinement Loop (`refinement`)

```
Composer output
    ↓
ConsistencyAuditor check
    ├─ PASS         →直接进入 L3b
    ├─ WARNING      → At most 1 minor adjustment (inject refinement_hints)
    └─ FAIL         → At most 2 rewrites (inject issues + fix_suggestion)
```

#### P0-2: Multi-Sample Self-Consistency (`best_of_3`)

```
Director × 3 (parallel, independent Providers)
    ↓
PlanScorer three-dimensional scoring (thread_progress / character_naturalness / causal_link)
    ↓
Highest total score wins (threshold 8/15, all re-run if below)
```

#### P1-1: Micro Oracle (`micro_oracle`)

After each beat, use light tier (temperature=0) to produce a one-sentence quality evaluation of the narrative, injected into the next beat's Director prompt, forming an iterative improvement loop.

#### P1-2: Dynamic Tier Upgrade (`dynamic_tier`)

Based on scene complexity (character count, thread count, interaction pair count), auto-adjust:
- Complexity < 0.3 → Some Agents downgraded to medium/light
- Complexity > 0.5 → Director/Composer upgraded to lower temperature (more deterministic)

#### P1-3: Multi-View Synthesis (`multi_view`)

```
Director(plot-driven)  ──→ PlanSynthesizer ──→ Fusion plan
Director(character-driven) ──→            ──→ Injected into L2R1/L2R2
```

#### P2-1: Semantic Canon Selection (`semantic_selection`)

Use CanonSelector (light tier) to select the Top-K most relevant items from candidate Canon, controlling the token budget injected into context (default 1200 tokens).

#### Vector Memory System (`vector_memory`)

Based on Ollama `/api/embed` endpoint + cosine similarity:
- Each beat stores narrative summary into vector store (MD5 deduplication cache)
- Next beat uses current context embed to retrieve most relevant historical scenes (top_k=3)
- Injected into ContextBuilder, enhancing long-term coherence

---

### File Structure

```
Round/
├── src/
│   ├── llm/
│   │   ├── manana/          # MaNA v4 narrative engine (22 files)
│   │   │   ├── manana_pipeline.gd          # Five-layer orchestrator (core scheduler)
│   │   │   ├── manana_config.gd           # v4 configuration reader
│   │   │   ├── manana_schema.gd           # JSON Schema definitions
│   │   │   ├── manana_logger.gd           # Agent call logging
│   │   │   ├── base_agent.gd              # Agent base class
│   │   │   ├── context_builder.gd         # L0 context builder
│   │   │   ├── scene_director.gd          # L1 beat director
│   │   │   ├── motivation_engine.gd       # L2R1 motivation analysis
│   │   │   ├── dialogue_weaver.gd        # L2R2 dialogue generation
│   │   │   ├── action_director.gd        # L2R2 action choreography
│   │   │   ├── scene_composer.gd         # L3 narrative weaving
│   │   │   ├── consistency_auditor.gd    # L3b consistency audit
│   │   │   ├── state_extractor.gd        # L4a state extraction
│   │   │   ├── thread_manager.gd         # L4b thread management
│   │   │   ├── reflection_oracle.gd      # L5 reflection oracle
│   │   │   ├── interaction_pair.gd       # Interaction pair data structure
│   │   │   │
│   │   │   │   # --- v4 new ---
│   │   │   ├── vector_memory.gd          # Vector memory system
│   │   │   ├── canon_selector.gd        # Semantic Canon selection
│   │   │   ├── plan_scorer.gd           # Best-of-3 scorer
│   │   │   ├── plan_synthesizer.gd      # Multi-view synthesizer
│   │   │   └── micro_oracle.gd         # Per-beat quality feedback
│   │   │
│   │   └── providers/       # LLM Provider abstraction layer (5 files)
│   │       ├── base_provider.gd
│   │       ├── ollama_provider.gd
│   │       ├── deepseek_provider.gd
│   │       ├── openai_provider.gd
│   │       └── provider_factory.gd
│   │
│   ├── autoload/           # Godot Autoload singletons (6 files)
│   │   ├── world_state.gd
│   │   ├── event_bus.gd
│   │   ├── provider_registry.gd
│   │   ├── canon_loader.gd
│   │   ├── novel_scanner.gd
│   │   └── canon_extractor.gd
│   └── ui/                 # Terminal-style UI scripts
│
├── prompts/                 # Prompt engineering (15 files)
│   ├── director.md          # L1 beat director (general)
│   ├── director_plot.md     # L1 plot view (v4 multi_view)
│   ├── director_char.md     # L1 character view (v4 multi_view)
│   ├── motivation.md       # L2R1 motivation analysis
│   ├── dialogue_weaver.md # L2R2 dialogue generation
│   ├── action_director.md  # L2R2 action choreography
│   ├── composer.md         # L3 narrative weaving
│   ├── auditor.md          # L3b consistency audit
│   ├── state_extractor.md  # L4a state extraction
│   ├── thread_manager.md   # L4b thread management
│   ├── oracle.md           # L5 reflection oracle
│   ├── canon_selector.md   # v4 semantic Canon selection
│   ├── scorer.md          # v4 Best-of-3 scoring
│   ├── synthesizer.md    # v4 multi-view fusion
│   └── micro_oracle.md    # v4 per-beat quality feedback
│
├── scenes/                  # Godot scene files
├── novel/                   # Test novel texts
├── addons/
│   └── godot_bridge_mcp/   # Godot Bridge MCP Server
├── manana_config.cfg        # MaNA v4 configuration file
└── project.godot            # Godot project configuration
```

---

## Models Used

### Current Configuration

| Tier | Model | Temperature | max_tokens | Timeout | Purpose |
|------|-------|-------------|------------|---------|---------|
| Strong | qwen3.5:9b (Ollama) | 0.5 | 4096 | 120s | Director / Composer / Oracle / PlanSynthesizer |
| Medium | qwen3.5:9b (Ollama) | 0.7 | 2048 | 120s | Motivation / Dialogue / Auditor / Thread |
| Light | qwen3.5:9b (Ollama) | 0.8 | 512 | 60s | Action / StateExtractor / Scorer / MicroOracle |

> Endpoint: `<Ollama endpoint, e.g. http://localhost:11434/api/chat>`
> Embedding model: `qwen3-embedding:0.6b` (for vector memory system, optional)

### Pre-Configured Providers

- **Ollama**: Currently active, qwen3.5:9b for all tiers
- **DeepSeek API**: Pre-configured, API Key TBD
- **OpenAI API**: Pre-configured, API Key TBD

### Known Issues

**qwen3.5:9b Thinking Mode Trap**:
- Symptom: Error "400 input length too long" (actual prompt only ~600-1000 chars)
- Root cause: Model enables thinking mode by default, thinking consumes entire max_tokens, content is empty
- Fix: Set `reasoning_effort="none"` or increase max_tokens to 2048

---

## MCP Design

### Godot Bridge MCP

The Round project integrates **Godot Bridge MCP**, a plugin based on the Model Context Protocol (MCP) that connects AI clients to the Godot 4 editor via WebSocket.

#### Architecture Design

```
AI Client (OpenCode / WorkBuddy)
        ↓ MCP Protocol (stdio)
Python MCP Server (FastMCP)
        ↓ WebSocket (port 4099)
Godot Editor (GodotBridgeWebSocket.gd)
```

**Dual-Channel Design**:
- **WebSocket Channel**: Real-time bidirectional communication, low latency (port 4099)
- **File-only Fallback**: File read/write fallback when WebSocket is unavailable

#### Tool List (38 tools)

| Category | Tool Count | Description |
|----------|-------------|-------------|
| Scene Management | 6 | get_scene_tree / add_node / delete_node / create_scene / save_scene / create_scene_from_script |
| Node Management | 4 | get_node_properties / set_node_property / get_selected_nodes / list_node_types |
| Script Management | 3 | execute_script / attach_script / get_script_info |
| Asset Management | 2 | list_assets / get_editor_info |
| Round-specific | 10 | list_canons / read_canon / list_novels / read_debug_json / read_save, etc. |
| Resources | 5 | Expose Godot project state to MCP clients |

#### Security Design

23 tools have security labels:
- `[READ-ONLY]`: Read-only operations, will not modify the project
- `[EDITOR]`: Will modify scenes or scripts
- `[DESTRUCTIVE]`: Dangerous operations, require user confirmation

#### Technical Implementation

- **Language**: TypeScript (Node 22.22.2) + Python (FastMCP)
- **Communication**: WebSocket (websockets library)
- **Protocol**: MCP (Model Context Protocol) stdout/stdin
- **Godot Plugin**: GodotBridgeWebSocket.gd (WebSocket server)

---

## Prompt Engineering

The prompt engineering for the Round project is an iterative process, with all prompts written, tested, and optimized by **WorkBuddy (AI assistant)**. The project author provides ideas and feedback.

### Prompt Files (15 files)

| File | Agent | Responsibility |
|------|-------|----------------|
| `director.md` | Scene Director | Beat director, decides next narrative beat direction (general) |
| `director_plot.md` | Scene Director (plot view) | v4 multi_view: plot-driven beat plan |
| `director_char.md` | Scene Director (character view) | v4 multi_view: character-driven beat plan |
| `motivation.md` | Motivation Engine | Analyze character inner world, motivation, attitude toward player |
| `dialogue_weaver.md` | Dialogue Weaver | Generate character dialogue, maintain character consistency |
| `action_director.md` | Action Director | Generate character actions and scene descriptions |
| `composer.md` | Scene Composer | Weave each Agent's output into complete narrative text |
| `auditor.md` | Consistency Auditor | Check narrative consistency (character drift / factual contradiction / rule violation / continuity break) |
| `state_extractor.md` | State Extractor | Extract world state changes from narrative text |
| `thread_manager.md` | Thread Manager | Manage narrative threads (create/advance/close) |
| `oracle.md` | Reflection Oracle | Global narrative health assessment every 5 beats |
| `canon_selector.md` | Canon Selector | v4: semantic filtering of most relevant background info |
| `scorer.md` | Plan Scorer | v4 Best-of-3: three-dimensional scoring of Director output |
| `synthesizer.md` | Plan Synthesizer | v4 multi_view: fuse dual-view beat plans |
| `micro_oracle.md` | Micro Oracle | v4: one-sentence quality feedback per beat |

### Prompt Optimization History

#### Phase 1: Prompt Slimming (2026-06-16)

- **System Prompt**: 1800 → 600 chars (removed verbose examples, merged duplicate rules)
- **Character Context**: 7 fields → 4 fields (personality/speaking style/motivation/attitude), 2000 → 1200 chars
- **Narrative History**: 3 entries → 2 entries
- **Estimated request size**: ~8000 → ~5600 bytes, ~30% reduction

#### Phase 2: JSON Schema Design

Early versions used HTML comment markers (e.g. `<!-- beat_id: xxx -->`) for structured output, which had problems:
- Unstable parsing, easily failed due to LLM output format deviations
- Could not leverage JSON's structured validation capabilities

**Solution**: Freshly designed JSON Schema, each Agent outputs strict JSON objects.

#### Phase 3: Multi-Agent Prompt Separation (v3)

Split monolithic LLM calls into multiple specialized Agents, each with independent:
- **Role Definition**: Clear responsibility boundaries for that Agent
- **Input Context**: Only pass relevant context, reduce token consumption
- **Output Format**: JSON Schema designed for that Agent's task
- **Quality Criteria**: Targeted evaluation standards

#### Phase 4: v4 Multi-View & Self-Consistency (2026-06-17~18)

- **Best-of-3**: Added `scorer.md` (three-dimensional scoring prompt) + `synthesizer.md` (fusion prompt)
- **Multi-View**: Added `director_plot.md` + `director_char.md` (dual-view Director prompts)
- **Micro-Oracle**: Added `micro_oracle.md` (one-sentence quality feedback prompt)
- **Canon Selector**: Added `canon_selector.md` (semantic filtering prompt)

#### Phase 5: Anti-Rules Guardrails (v4 design)

To prevent character behavior drift, define **Anti-Rules** (counter-example rules) for each character:
- Explicitly list what the character should **NOT** do
- Inject `anti_rules` field into Motivation Engine's prompt
- Auditor checks will reference these rules

---

## World Deviation System

The Round project implements a **World Deviation** mechanism, tracking the gap between player actions and canon:

### Calculation Formula

```
Deviation = closed_thread_count × 0.08 + avg_active_thread_progress × 0.1 + reputation_spread_abs × 0.15
```

### 5 Deviation Levels

| Level | Description | Narrative Strategy |
|-------|-------------|-------------------|
| 0 | Closely follows canon | Faithful to canon, minor adjustments |
| 1 | Local minor deviation | Allow local variations, maintain main plot |
| 2 | Significant deviation | Bold innovation, but maintain character consistency |
| 3 | Major deviation | Open narrative, characters may behave unexpectedly |
| 4 | Completely divergent | Fully free narrative, canon only as background |

### Trigger Timing

- Auto-recalculated after `adjust_player_reputation()`
- Auto-recalculated after `_close_thread()`

---

## Development History

The Round project is completed by **WorkBuddy (AI assistant)**, with the project author only responsible for providing ideas and concepts.

### Development Phases

| Phase | Date | Content | Status |
|-------|------|---------|--------|
| Phase 0 | 06-15 | Basic framework (Godot skeleton, terminal UI, Autoload) | ✅ Complete |
| Phase 1 | 06-15~16 | Import pipeline (Novel Scanner, Canon Extractor) | ⚠️ Partially complete |
| Phase 2 | 06-15~17 | Narrative engine (MaNA v0.1 → v3) | ✅ Complete |
| Phase 3 | 06-17~18 | Complete experience (F1-F5 panels, save/load system, ending system) | ✅ Complete |
| **Phase 4** | **06-18** | **MaNA v4 (8 enhancement features)** | **⚠️ Code complete, not fully tested** |
| Phase 5 | TBD | Polishing (multiple endings, relationship graph visualization, import guide) | ❌ Not started |

### Key Milestones

- **06-15**: Project launched, completed Phase 0 + partial Phase 1 + MaNA v0.1
- **06-16**: Prompt slimming, fixed qwen3.5:9b thinking mode trap
- **06-17**: MaNA v3 refactor, 5-layer multi-agent narrative pipeline
- **06-18**: MaNA v4 implementation, 8 enhancement features (refinement / best_of_3 / dynamic_tier / multi_view, etc.)

---

## Test Data

- **Test Novels**: *Becoming a Background Character in My Own Novel*, *The Demon King Goes to School*
- **Test Canon**: `novel/canon.json`
- **Test Logs**: 12 groups of v0.1 response logs + complete MaNA v4 trace in `debug/agent_traces/`

---

## ⚠️ Current Limitations & Unimplemented Features

### Phase 1 Import Pipeline (Partially Complete)

- ❌ **5-Pass Import Process** (Pass A-E) not implemented, currently only supports single Canon extraction
- ❌ **Manual Correction UI** not implemented, import results cannot be manually edited in-game

### v4 Feature Status

- ⚠️ Most v4 feature code has been implemented and integrated into the pipeline, but due to being disabled by default (`enabled=false` or independent sub-feature switches), **have not been fully tested in actual novel import scenarios**
- ❌ `anti_rules` (character guardrails): Code framework exists (`prompts/anti_rules.md` not yet created), not integrated into pipeline

### Phase 3 Incomplete Parts

- ❌ **Multiple ending condition refinement**: Currently only triggers endings based on deviation, conditions are rough
- ❌ **Character relationship graph visualization**: Currently text-only, visualization not implemented
- ❌ **Novel import guide flow**: First-time game entry guide UI not implemented

### Phase 5 Not Started

- ❌ All polishing phase features not started

---

## How to Run

### Prerequisites

1. **Godot 4.6**: [Download](https://godotengine.org/download)
2. **Ollama**: [Download](https://ollama.com), and pull models:
   ```bash
   ollama pull qwen3.5:9b
   # Optional for vector memory:
   ollama pull qwen3-embedding:0.6b
   ```
3. **(Optional) DeepSeek / OpenAI API Key**: Edit `manana_config.cfg`

### Running Steps

1. Open Godot 4.6, import the `Round` project
2. Run `scenes/main.tscn`
3. Enter novel text in the terminal UI or select a test novel
4. System automatically parses and launches the narrative engine

---

## Configuration

### MaNA v4 Configuration (`manana_config.cfg`)

```ini
[v4]
# v4 master switch: false = fully use v3 path
enabled=false

[refinement]
# Iterative refinement loop
enabled=true

[best_of_3]
# Multi-sample self-consistency
enabled=true
sample_count=3
scorer_min_total=8

[multi_view]
# Multi-view synthesis
enabled=true

[dynamic_tier]
# Dynamic tier upgrade
enabled=true

[memory]
# Vector memory
enable_vector_memory=false
embed_model="qwen3-embedding:0.6b"
vector_top_k=3
```

> After enabling `enabled=true`, each sub-feature takes effect independently per the switches above.

---

## Contributors

| Role | Name | Description |
|------|------|-------------|
| Idea Provider | Project Author | Provide project ideas, concepts, requirements, feedback |
| AI Development | WorkBuddy | Complete all code, prompts, documentation, architecture design |
| Testing | Project Author + WorkBuddy | Multiple rounds of QA testing, Bug fixes |

### About "Completed by WorkBuddy"

This project's architecture design, code implementation, prompt writing, and documentation generation are all completed by **WorkBuddy (AI assistant)** under the guidance of the project author's ideas. The project author is responsible for:
- Providing project creative ideas and core concepts
- Deciding technical direction and feature priorities
- Test feedback and Bug reports

WorkBuddy is responsible for:
- All GDScript code writing
- MaNA multi-agent architecture design
- 15 prompt file writing and optimization
- Godot Bridge MCP integration
- This document and all technical documentation

---

## Acknowledgments

- **miHoYo *Varsapura* (City of Rain)**: Project inspiration
- **Ollama**: Local LLM deployment solution
- **Godot Engine**: Open-source game engine
- **FastMCP**: MCP Server framework

---

## License

TBD

---

## Contact

- **GitHub**: (TBD)
- **Issues**: Bug reports and feature suggestions welcome

---

<div align="center">

**Round — Making the Novel World Within Reach**

</div>
