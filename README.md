# MaNA v4 — Multi-Agent Narrative Architecture

Python port of the Rain project's core LLM narrative pipeline, originally written in GDScript for Godot 4.x.

Source of Inspiration:
https://toonflow.net/#/
|
https://github.com/HBAI-Ltd/Toonflow-app

## Architecture

```mermaid
flowchart TD
    subgraph "L0: Context"
        CB[ContextBuilder]
    end

    subgraph "L1: Director v4"
        SD[SceneDirector]
        B3[Best-of-3 Scorer]
        MV[Multi-View Synthesizer]
    end

    subgraph "L2: Character Engines N-parallel"
        ME[MotivationEngine × N]
        DW[DialogueWeaver × N]
        AD[ActionDirector × N]
    end

    subgraph "L3: Composition v4"
        SC[SceneComposer]
        RF[Refinement Loop<br/>Composer⇄Auditor]
    end

    subgraph "L3b∥L4a: Parallel"
        CA[ConsistencyAuditor]
        SE[StateExtractor]
    end

    subgraph "L4b"
        TM[ThreadManager]
    end

    subgraph "L5: Conditional"
        RO[ReflectionOracle<br/>every 5 beats]
    end

    subgraph "v4: Per-beat"
        MO[MicroOracle]
    end

    CB --> SD --> B3 --> MV
    MV --> ME --> DW & AD
    DW & AD --> SC --> RF
    RF --> CA & SE
    CA & SE --> TM
    TM -.-> RO
    SC -.-> MO

