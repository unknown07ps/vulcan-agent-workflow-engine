# Multi-Agent Workflow Engine

Specialized agents (Planner → Researcher → Critic → Formatter) collaborate via a LangGraph
state machine to generate reports/code reviews. Exposed via FastAPI, state in Redis, agent
traces returned to the caller.

## Build Stages

This project is built incrementally across stages. Each stage is a separate git commit/push.

- [x] **Stage 1**: Project scaffolding, config, Docker/Compose, requirements
- [ ] **Stage 2**: Core state schema + LangGraph state machine (agents as nodes)
- [ ] **Stage 3**: Agent implementations (Planner, Researcher, Critic, Formatter) + LLM client
- [ ] **Stage 4**: Redis-backed state persistence + trace logging
- [ ] **Stage 5**: FastAPI REST layer (submit task, poll status, get trace)
- [ ] **Stage 6**: Tests, docs, polish, run scripts

## Quick Start (after all stages)

```bash
docker compose up --build
curl -X POST http://localhost:8000/tasks -H "Content-Type: application/json" \
  -d '{"task": "Write a report on renewable energy trends"}'
curl http://localhost:8000/tasks/<task_id>
curl http://localhost:8000/tasks/<task_id>/trace
```

## Architecture

```
Client --> FastAPI --> LangGraph StateGraph --> Redis (state + trace)
                          |
              Planner -> Researcher -> Critic -> Formatter
                              ^___________|  (revision loop)
```

## Environment Variables

See `.env.example`. Requires `ANTHROPIC_API_KEY` (or OpenAI key, configurable).
