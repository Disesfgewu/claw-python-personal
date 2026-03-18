# Phase 2.5 實作計劃書

> **目標：** 完成 Skills 層的完整重構——著作權清理、架構對齊、loader 功能補完，
> 以及 Phase 2 Codex 回報中留下的未竟事項。
>
> **前提：** Phase 2 全部 52 tests 通過。本 Phase 不新增 agent 功能，
> 只處理 skills 目錄與 loader 的品質問題。

---

## 一、Phase 2 遺留問題（先修）

### P2.5-0　SkillManifest.openclaw_extras 型別補強

Codex Phase 2 bonus 實作了 `SkillManifest.openclaw_extras`，但未在 `base.py` 正式宣告型別，
`install` 欄位也可能被解析成 `str`（原始格式為 `list[dict]`）。

**需修改：**

`claw/skills/base.py`
```python
@dataclass
class SkillManifest:
    name: str
    description: str = ""
    version: str = "1.0"
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    openclaw_extras: dict = field(default_factory=dict)
    # openclaw_extras 結構：
    # {
    #   "emoji": str,
    #   "install": list[dict],   # [{id, kind, formula/package, bins, label}]
    #   "homepage": str,
    # }
```

`claw/skills/manifest.py`：確認 `install` 讀成 `list`（若原始值是 `str` 或 `[]` 一律轉成 `list`）：
```python
raw_install = openclaw_meta.get("install", [])
install = raw_install if isinstance(raw_install, list) else []
openclaw_extras = {
    "emoji": openclaw_meta.get("emoji", ""),
    "install": install,
    "homepage": meta.get("homepage", ""),
}
```

---

### P2.5-1　Loader 實作 `{baseDir}` 替換

部分 skill 的 body 使用 `{baseDir}` 指向 skill 目錄內的腳本：
```bash
python3 {baseDir}/scripts/model_usage.py
```

`{baseDir}` 應在載入時替換為 skill 目錄的**絕對路徑**。

**需修改：`claw/skills/loader.py`，`_load_md_skill()` 函數**

```python
def _load_md_skill(path: str, name: str, registry: SkillRegistry) -> None:
    ...
    base_dir = os.path.abspath(os.path.dirname(path))
    prompt = parsed.prompt.replace("{baseDir}", base_dir)
    skill = _PromptSkill(parsed.manifest, prompt)
    ...
```

`_PromptSkill` 使用替換後的 `prompt`（已含正確路徑），不需要額外修改。

**新增測試 `tests/test_skills.py`：**
```python
def test_basedir_substitution(tmp_path):
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: my_skill
        description: test
        ---
        Run: python3 {baseDir}/scripts/run.py
    """))
    reg = load_skills(str(tmp_path))
    skill = reg.get("my_skill")
    assert skill is not None
    assert str(skill_dir) in skill.system_prompt
    assert "{baseDir}" not in skill.system_prompt
```

---

## 二、Skills 目錄重構

### 2-A　刪除（6 個）

| 資料夾 | 刪除原因 |
|---|---|
| `openai-image-gen` | 直接要求 `OPENAI_API_KEY`，違反零廠商 key 設計；著作權 |
| `openai-whisper-api` | 同上，直接要求 `OPENAI_API_KEY` |
| `clawhub` | 允許 agent 從 clawhub.com 動態安裝 skill，供應鏈風險 |
| `canvas` | 依賴 OpenClaw 專屬 Canvas/Node Bridge 基礎設施，claw-python 無此機制 |
| `voice-call` | 依賴 OpenClaw voice-call plugin，claw-python 無此機制 |
| `node-connect` | 針對 OpenClaw companion app 的配對除錯，claw-python 無 companion app |

---

### 2-B　合併（3 對 → 3 個新資料夾）

#### `github` + `gh-issues` → `github/`

兩者都使用 `gh` binary，功能重疊度高：
- `github`：一般 GitHub 操作（issues、PR、CI、API）
- `gh-issues`：抓取 issues、spawn sub-agent 實作修復並開 PR

合併後 `github` 涵蓋兩者功能。**刪除 `gh-issues/` 資料夾。**

```
skills/github/SKILL.md   ← 整合後重寫
```

---

#### `imsg` + `bluebubbles` → `imessage/`

兩者都是 iMessage 整合，後端不同：
- `imsg`：macOS imsg CLI，直接存取 Messages.app（darwin-only）
- `bluebubbles`：透過 BlueBubbles server（跨平台）

合併為 `imessage`，body 中說明兩種後端的路由邏輯。
**刪除 `imsg/` 和 `bluebubbles/` 資料夾。**

```
skills/imessage/SKILL.md   ← 整合後重寫
```

frontmatter requires：
```yaml
metadata:
  openclaw:
    emoji: "💬"
    os: ["darwin"]
    requires:
      anyBins: ["imsg", "bluebubbles"]
```

---

#### `sag` + `sherpa-onnx-tts` → `tts/`

兩者都是 TTS（文字轉語音），來源不同：
- `sag`：ElevenLabs 雲端 TTS（需 `ELEVENLABS_API_KEY`）
- `sherpa-onnx-tts`：本機離線 TTS（需 `SHERPA_ONNX_*` 環境變數）

合併為 `tts`，body 說明優先使用本機（`sherpa-onnx`），可選雲端（`sag`）。
**刪除 `sag/` 和 `sherpa-onnx-tts/` 資料夾；`sherpa-onnx-tts/bin/` 內容移至 `tts/bin/`。**

```
skills/tts/
├── SKILL.md
└── bin/   ← 從 sherpa-onnx-tts/bin/ 移入
```

frontmatter requires（anyBins：有一個就夠）：
```yaml
metadata:
  openclaw:
    emoji: "🔊"
    os: ["darwin", "linux"]
    requires:
      anyBins: ["sag", "sherpa-onnx-tts"]
```

---

### 2-C　重新命名（1 個）

| 舊名稱 | 新名稱 | 原因 |
|---|---|---|
| `model-usage` | `usage` | 原名稱過度綁定 OpenClaw/Codex 生態；`usage` 更通用 |

---

### 2-D　著作權重寫（全部保留的 skill）

**所有保留的 skill 的 SKILL.md body 必須完整重寫為原創文字。**
不得保留原始 OpenClaw body 的任何段落或句子。
Frontmatter（name、description、metadata）保留結構，description 可更新措辭。

**重寫規格：**

每個 SKILL.md body 必須包含以下結構（根據 skill 複雜度調整詳略）：

```markdown
# <Skill Name>

<1–2 句說明此 skill 提供什麼能力。>

## When to use

- <條件 1>
- <條件 2>

## Usage

<簡要操作說明，包含關鍵 CLI 指令或用法範例。>

## Examples

<1–3 個具體範例。>
```

**需特別處理的 skill（路徑 / 品牌名稱替換）：**

| Skill | 需替換內容 |
|---|---|
| `session-logs` | `~/.openclaw/` → `~/.claw/`；`~/.clawdbot/` → `~/.claw/` |
| `healthcheck` | 移除「OpenClaw deployments」字樣，改為「claw-python 部署環境」 |
| `skill-creator` | 更新 SKILL.md 格式範例為 claw-python 的格式（`metadata.openclaw.*`） |
| `coding-agent` | 更新 agent spawn 指令說明（claude/codex/opencode/pi 任一） |
| `model-usage` (→ `usage`) | 移除 codexbar 特定路徑，改為通用說明 |

---

### 2-E　最終 Skills 目錄結構

完成後 `skills/` 應包含以下 **44 個資料夾**：

```
skills/
├── 1password/
├── apple-notes/
├── apple-reminders/
├── bear-notes/
├── blogwatcher/
├── blucli/
├── camsnap/
├── coding-agent/
├── discord/
├── eightctl/
├── gemini/
├── gifgrep/
├── github/          ← 合併自 github + gh-issues
├── gog/
├── goplaces/
├── healthcheck/
├── himalaya/
├── imessage/        ← 合併自 imsg + bluebubbles
├── mcporter/
├── nano-pdf/
├── notion/
├── obsidian/
├── openai-whisper/  ← 保留（本機 Whisper，不需 API key）
├── openhue/
├── oracle/
├── ordercli/
├── peekaboo/
├── search/          ← 我們自己的 search skill（已重寫）
├── session-logs/
├── skill-creator/
├── slack/
├── songsee/
├── sonoscli/
├── spotify-player/
├── summarize/
├── things-mac/
├── tmux/
├── trello/
├── tts/             ← 合併自 sag + sherpa-onnx-tts
├── usage/           ← 重新命名自 model-usage
├── video-frames/
├── wacli/
├── weather/
└── xurl/
```

---

## 三、驗收標準

```bash
python -m pytest tests/ -v
```

預期 tests 全部通過，包含：
- `test_basedir_substitution`（新增）
- 所有既有 52 tests

---

## 四、Codex 執行 Prompt

---

### Codex Prompt — Phase 2.5

**目標：** Skills 目錄重構 + Loader 功能補完 + 著作權清理

請依序執行以下步驟。每個步驟完成後繼續下一步，不要等待確認。

---

#### Step 1：修正 SkillManifest 型別

**`claw/skills/base.py`**

在 `SkillManifest` dataclass 中，確認 `openclaw_extras: dict` 欄位已宣告（若 Codex Phase 2 bonus 已加入則確認型別正確）。

**`claw/skills/manifest.py`**

修正 `openclaw_extras` 的 `install` 欄位，確保永遠為 `list`：
```python
raw_install = openclaw_meta.get("install", [])
install = raw_install if isinstance(raw_install, list) else []
openclaw_extras = {
    "emoji": openclaw_meta.get("emoji", ""),
    "install": install,
    "homepage": meta.get("homepage", ""),
}
```

---

#### Step 2：實作 `{baseDir}` 替換

**`claw/skills/loader.py`**，在 `_load_md_skill()` 中，解析完 `prompt` 後、建立 `_PromptSkill` 之前，加入：

```python
base_dir = os.path.abspath(os.path.dirname(path))
prompt = parsed.prompt.replace("{baseDir}", base_dir)
```

**`tests/test_skills.py`**，新增測試：

```python
def test_basedir_substitution(tmp_path):
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: my_skill
        description: test
        ---
        Run: python3 {baseDir}/scripts/run.py
    """))
    reg = load_skills(str(tmp_path))
    skill = reg.get("my_skill")
    assert skill is not None
    assert str(skill_dir) in skill.system_prompt
    assert "{baseDir}" not in skill.system_prompt
```

---

#### Step 3：刪除 6 個 skills 資料夾

```bash
rm -rf skills/openai-image-gen
rm -rf skills/openai-whisper-api
rm -rf skills/clawhub
rm -rf skills/canvas
rm -rf skills/voice-call
rm -rf skills/node-connect
```

---

#### Step 4：合併 skills

**4-A：`gh-issues` 合併進 `github`**

閱讀 `skills/github/SKILL.md` 和 `skills/gh-issues/SKILL.md` 的功能描述，
然後重寫 `skills/github/SKILL.md`，涵蓋兩者功能（一般 GitHub 操作 + issue 修復 sub-agent 流程）。
完成後刪除 `skills/gh-issues/`。

**4-B：`imsg` + `bluebubbles` → `imessage`**

新建 `skills/imessage/` 目錄，撰寫 `skills/imessage/SKILL.md`：
- description 說明兩種後端：`imsg`（macOS 直連）和 BlueBubbles server（跨平台）
- body 說明路由邏輯：優先 imsg（darwin）、備用 bluebubbles
- frontmatter：
  ```yaml
  metadata:
    openclaw:
      emoji: "💬"
      os: ["darwin"]
      requires:
        anyBins: ["imsg", "bluebubbles"]
  ```
完成後刪除 `skills/imsg/` 和 `skills/bluebubbles/`。

**4-C：`sag` + `sherpa-onnx-tts` → `tts`**

新建 `skills/tts/` 目錄。
若 `skills/sherpa-onnx-tts/bin/` 存在，將其移至 `skills/tts/bin/`。
撰寫 `skills/tts/SKILL.md`：
- description 說明本機（sherpa-onnx）與雲端（sag/ElevenLabs）TTS
- body 說明優先使用本機 TTS，ElevenLabs 為備選
- frontmatter：
  ```yaml
  metadata:
    openclaw:
      emoji: "🔊"
      os: ["darwin", "linux"]
      requires:
        anyBins: ["sag", "sherpa-onnx-tts"]
        env: []
  ```
完成後刪除 `skills/sag/` 和 `skills/sherpa-onnx-tts/`。

---

#### Step 5：重新命名

```bash
mv skills/model-usage skills/usage
```

更新 `skills/usage/SKILL.md` 的 frontmatter `name` 欄位為 `usage`，
並更新 description 移除 codexbar 特定措辭，改為「查看 AI agent 的模型用量與費用摘要」。

---

#### Step 6：重寫所有 SKILL.md body（著作權清理）

**對以下每一個 skill**，完整重寫 SKILL.md 的 body（`---` 之後的 markdown 內容）為原創文字。
Frontmatter 保留原有結構，只更新 description 措辭使其原創。

**不得保留原始 body 的任何段落或句子。**

每個 body 的必要結構：
```
# <Skill Name>
<1-2 句功能說明>

## When to use
- <條件 1>
- <條件 2>
（視 skill 複雜度，可省略此節）

## Usage
<操作說明 + 關鍵指令範例>
```

需重寫的 skill 清單（共 38 個，依字母排序）：

`1password`, `apple-notes`, `apple-reminders`, `bear-notes`, `blogwatcher`,
`blucli`, `camsnap`, `coding-agent`, `discord`, `eightctl`, `gemini`,
`gifgrep`, `github`（合併後），`gog`, `goplaces`, `healthcheck`, `himalaya`,
`imessage`（合併後），`mcporter`, `nano-pdf`, `notion`, `obsidian`,
`openai-whisper`, `openhue`, `oracle`, `ordercli`, `peekaboo`,
`session-logs`, `skill-creator`, `slack`, `songsee`, `sonoscli`,
`spotify-player`, `summarize`, `things-mac`, `tmux`, `trello`,
`tts`（合併後）, `usage`（改名後）, `video-frames`, `wacli`, `weather`, `xurl`

**特別注意（路徑 / 品牌名稱）：**

| Skill | 必要替換 |
|---|---|
| `session-logs` | `~/.openclaw/` 和 `~/.clawdbot/` → `~/.claw/` |
| `healthcheck` | 「OpenClaw」→「claw-python」 |
| `skill-creator` | SKILL.md 格式範例更新為 claw-python 的 `metadata.openclaw.*` 格式 |
| `coding-agent` | 移除對 OpenClaw 特定 workspace 的假設 |

---

#### Step 7：確認 `search` skill 不需重寫

`skills/search/SKILL.md` 已是我們自己撰寫的版本，跳過此 skill。

---

#### Step 8：執行測試

```bash
python -m pytest tests/ -v
```

預期全部 pass（含新增的 `test_basedir_substitution`）。

---

### 回報格式

```
✅ Step 1 SkillManifest install fix：done
✅ Step 2 {baseDir} substitution：done / test added
✅ Step 3 刪除 6 skills：done
✅ Step 4A github 合併：done
✅ Step 4B imessage 合併：done
✅ Step 4C tts 合併：done
✅ Step 5 usage 改名：done
✅ Step 6 重寫完成：N skills rewritten
✅ Step 7 search 跳過：confirmed
✅ Step 8 pytest：X passed
```
