# Phase 9 — AutoResearch 自主研究框架

**日期**：2026-03-21
**PM**：Claude Code
**基礎**：Phase 8a 完成（135 tests）
**目標**：讓 claw-python 具備「自主研究複雜問題」的能力——問題分解、試錯迭代、結果保留、自主終止

---

## 設計理念

借鑑 Karpathy autoresearch 的核心精神（封閉迴圈試錯、keep/discard、持續循環），
但移除 ML 訓練專用部分，改為通用的問題研究框架：

```
複雜問題輸入
  → Planner 分解成多個可驗證子假設
  → ResearchLoop 逐一執行實驗（工具呼叫 / web_fetch / bash / multi-agent）
  → 三層終止判斷：用戶標準 → 量化指標 → AI 自判
  → 實驗台帳持久化（SQLite research_experiments）
  → keep 有效路徑 / discard 無效路徑
  → 自主迭代直到解題或達到停止條件
```

---

## 終止條件優先鏈（三層降級）

```
1. A — 用戶明確指定 success_criteria（字串）
        → LLM 判斷當前結果是否滿足該標準
        → 滿足即停止

2. C — 用戶提供 eval_cmd（bash 命令）
        → 執行後取 exit code（0=成功）或 stdout 數值（越低越好）
        → 達標即停止

3. B — 兜底：LLM 自判
        → Agent 判斷是否已得到足夠有效的解答
        → 設定 max_experiments 上限防止無限迴圈（預設 20）
```

---

## 新增元件

### 新建檔案

| 檔案 | 功能 |
|---|---|
| `claw/research/__init__.py` | 模組入口 |
| `claw/research/experiment.py` | ExperimentResult dataclass + ExperimentStatus enum |
| `claw/research/ledger.py` | ResearchLedger：SQLite research_experiments 讀寫 |
| `claw/research/planner.py` | ResearchPlanner：任務分解 + 下一假設生成 |
| `claw/research/loop.py` | ResearchLoop：主迴圈協調器 |
| `claw/tools/research_tools.py` | research_start / experiment_record / research_status tools |
| `claw/skills/autoresearch/SKILL.md` | Agent 操作指令（對應 autoresearch 的 program.md） |

### 修改檔案

| 檔案 | 修改內容 |
|---|---|
| `claw/core/storage.py` | SCHEMA_SQL 加入 `research_experiments` 和 `research_tasks` 表 |
| `claw/tools/__init__.py` | import research_tools |

---

## 資料模型

### SQLite 新增表

```sql
CREATE TABLE IF NOT EXISTS research_tasks (
    task_id     TEXT PRIMARY KEY,          -- uuid
    question    TEXT NOT NULL,             -- 原始研究問題
    criteria    TEXT,                      -- 用戶指定的成功標準（A層）
    eval_cmd    TEXT,                      -- 量化指令（C層）
    status      TEXT NOT NULL DEFAULT 'running',  -- running|completed|stopped
    max_exp     INTEGER NOT NULL DEFAULT 20,
    created_at  TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS research_experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL REFERENCES research_tasks(task_id),
    hypothesis  TEXT NOT NULL,             -- 這次嘗試的假設
    approach    TEXT NOT NULL,             -- 具體執行的方法
    output      TEXT,                      -- 執行結果摘要（最多 1000 chars）
    metric      REAL,                      -- 量化指標（C層 eval_cmd 的結果）
    status      TEXT NOT NULL,             -- keep|discard|crash
    reasoning   TEXT,                      -- AI 判斷理由
    ts          TEXT NOT NULL
);
```

### ExperimentResult dataclass

```python
@dataclass
class ExperimentResult:
    task_id: str
    hypothesis: str
    approach: str
    output: str
    metric: float | None      # C層 eval_cmd 結果，None = 未提供
    status: ExperimentStatus  # KEEP | DISCARD | CRASH
    reasoning: str
    ts: str
```

---

## 核心流程設計

### ResearchLoop.run() 主迴圈

```python
async def run(
    self,
    question: str,
    success_criteria: str | None = None,   # A層
    eval_cmd: str | None = None,           # C層
    max_experiments: int = 20,
    session_id: str = "agent:main",
) -> AsyncIterator[ResearchEvent]:

    # 1. 建立 task 記錄
    task_id = create_task(question, criteria, eval_cmd, max_experiments)

    # 2. Planner 初始化：分解問題成 3-5 個初始假設
    hypotheses = await planner.decompose(question, agent_loop)

    kept_results = []
    for exp_num in range(max_experiments):

        # 3. 生成下一個假設（基於歷史結果）
        hypothesis = await planner.next_hypothesis(question, kept_results, agent_loop)

        # 4. 執行實驗（透過 AgentLoop 呼叫工具）
        output = await _execute_experiment(hypothesis, session_id)

        # 5. 量化評估（C層：執行 eval_cmd）
        metric = await _run_eval_cmd(eval_cmd) if eval_cmd else None

        # 6. 三層終止判斷
        verdict, reasoning = await _evaluate(
            output, metric, success_criteria, eval_cmd, kept_results, agent_loop
        )

        # 7. 記錄結果
        result = ExperimentResult(...)
        await ledger.record(result)
        yield ExperimentCompleted(result)

        if verdict == KEEP:
            kept_results.append(result)

        # 8. 終止條件檢查
        if await _should_terminate(verdict, reasoning, success_criteria, eval_cmd, kept_results):
            yield ResearchCompleted(task_id, kept_results)
            return

    yield ResearchExhausted(task_id, kept_results)  # 達到 max_experiments
```

### 三層評估邏輯

```python
async def _evaluate(output, metric, criteria, eval_cmd, history, agent_loop):
    # A層：用戶明確標準
    if criteria:
        verdict = await agent_loop.ask_yes_no(
            f"Does this result satisfy: '{criteria}'?\nResult: {output[:500]}"
        )
        return (KEEP if verdict else DISCARD), "criteria check"

    # C層：量化指標
    if eval_cmd and metric is not None:
        best_metric = min(r.metric for r in history if r.metric is not None) if history else float('inf')
        if metric < best_metric:
            return KEEP, f"metric improved: {metric:.4f} < {best_metric:.4f}"
        return DISCARD, f"metric not improved: {metric:.4f} >= {best_metric:.4f}"

    # B層：LLM 自判
    verdict = await agent_loop.ask_yes_no(
        f"Is this result useful/valid for the research goal?\nGoal: {criteria or 'solve the problem'}\nResult: {output[:500]}"
    )
    return (KEEP if verdict else DISCARD), "llm self-evaluation"
```

---

## Tools

### research_start
```
觸發一個 AutoResearch 任務。
參數：question (str), criteria (str|null), eval_cmd (str|null), max_experiments (int)
回傳：task_id
requires_main=True（只有 main session 可發起研究任務）
```

### experiment_record
```
記錄一個實驗結果（供 agent 在研究迴圈中呼叫）。
參數：task_id, hypothesis, approach, output, status, reasoning
requires_main=False
```

### research_status
```
查看研究任務的當前狀態和歷史實驗。
參數：task_id (optional，省略時列出所有 running tasks)
requires_main=True
```

---

## AutoResearch Skill

`claw/skills/autoresearch/SKILL.md` 對應 autoresearch 的 `program.md`：

```markdown
---
name: autoresearch
description: Autonomous research loop for complex problems
metadata:
  openclaw:
    requires:
      config: []
---

# AutoResearch

你是一個自主研究 agent。收到複雜問題時：

1. **分解問題**：把問題分解成 3-5 個可獨立驗證的子假設
2. **逐一實驗**：每次只驗證一個假設，使用工具執行
3. **記錄結果**：每次實驗後立即呼叫 experiment_record
4. **learn from failure**：失敗的方法記入歷史，不重複嘗試
5. **持續迭代**：直到成功標準達成或達到實驗上限

規則：
- 每次實驗必須有明確的假設和可觀察的結果
- KEEP = 有效發現，延伸這個方向
- DISCARD = 無效，轉換策略
- 不要在沒有新假設的情況下重複相同方法
- NEVER STOP until termination condition is met
```

---

## 測試計畫

| 測試檔案 | 測試項目 | 數量 |
|---|---|---|
| `tests/test_research_ledger.py` | create_task, record_experiment, list_experiments, get_task | 4 |
| `tests/test_research_loop.py` | A層終止（criteria met）, C層終止（metric improved）, B層終止（LLM判定）, max_experiments 上限 | 4 |
| `tests/test_research_tools.py` | research_start, research_status, experiment_record | 2 |

**預估測試數：+10 → 135 → 145 tests**

---

## 實作順序

1. `claw/research/experiment.py` — dataclass, enum（無依賴）
2. `claw/core/storage.py` — 加兩張表（research_tasks, research_experiments）
3. `claw/research/ledger.py` — SQLite 讀寫
4. `claw/research/planner.py` — 問題分解（依賴 AgentLoop）
5. `claw/research/loop.py` — 主迴圈（依賴 ledger + planner）
6. `claw/tools/research_tools.py` — tool 介面（依賴 loop）
7. `claw/skills/autoresearch/SKILL.md` — skill 定義
8. `claw/tools/__init__.py` — 加 import
9. 測試

---

## 與 autoresearch 的對照

| autoresearch | claw Phase 9 | 說明 |
|---|---|---|
| train.py（可編輯目標） | 任意工具呼叫序列 | 通用化，不限於訓練腳本 |
| val_bpb 指標 | eval_cmd 輸出 / A層標準 / B層自判 | 三層降級 |
| results.tsv | research_experiments SQLite 表 | 持久化 + 可查詢 |
| git keep/discard | status = KEEP/DISCARD + memory 更新 | 邏輯等效 |
| program.md | autoresearch SKILL.md | skill 系統載入 |
| 永不停止 | max_experiments 上限 + 三層終止 | 有管控的持續迭代 |
| CUDA / PyTorch | 無（通用工具框架）| 不採用 ML 訓練部分 |
