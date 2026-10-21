# AI 漫劇／短劇產線：外接 TTS 旁白方案技術評估報告

> 評估日期：2026-10-19　│　目標機器：Windows 11 / NVIDIA RTX 4060 Ti 8GB / 16GB RAM / 本機 ComfyUI 於 `E:\Comfy-Desktop\ComfyUI-Shared`
> 產線前提：影片由 **MiniMax H3**（本機 ComfyUI / FreeVideo）生成；**旁白與配音改由外部 TTS 服務產生，再以 ffmpeg 混流（mux）進畫面**。因此 H3 影片 prompt **不得**要求角色說出台詞，prompt 內的 `overall_soundscape` 只留環境音／非敘事性音樂。

> **標籤約定**：【官方】= 官方文件／官方 repo／官方 model card；【社群實測】= 部落格、PR、Issue、Reddit 等第一手實測；【推測】= 本報告之推論，未經一手驗證。

---

## 0. 執行摘要（TL;DR）

1. **本專案的「已知可用、即插即用」首選是 MiniMax `speech-2.8-hd`**，不是因為它最好，而是因為它是**唯一同時滿足四項條件**的雲端方案：① 已有 MiniMax 帳號即可用（同供應商、同一把 key）；② **回傳內建字幕時間戳**（`subtitle_enable` + `subtitle_type: "word"`），**完全不需要再做一次 ASR 對軸**；③ 支援 `<#x#>` 停頓標記與 `(laughs)` 類語氣標記，可控制旁白節奏；④ 官方 `runtime/python/fastapi` 已有現成 server 可自架。同時它是**中文旁白**品質與成本最平衡的選項（$100／百萬字元）。

2. **「自帶 API（bring your own API）」的介面基座應定為 OpenAI 相容的 `POST {base_url}/v1/audio/speech`**，欄位為 `model` / `input` / `voice` / `response_format` / `speed` / `instructions` / `stream_format`，加上自訂 headers。這一組介面可**同時**打中：OpenAI 官方、Irodori-TTS-Server（自架日語）、Local-TTS-Service、GPT-SoVITS-API、Silero/Piper 閘道、Cloudflare AI Gateway、OpenRouter。MiniMax 與 Gemini 因 API 形狀不同，應各做一個**專屬 adapter**，不要硬塞進 OpenAI 相容格式。

3. **日語線的最優解是 `Irodori-TTS` + `Irodori-TTS-Server`**：程式碼 MIT、權重開放、**專為日語訓練**（DACVAE 日本語 codec、48kHz、AquesTalk 式重音＋Emoji 風格控制），且已經提供 **OpenAI 相容的 `POST /v1/audio/speech`**。這是全報告中「授權最乾淨 + API 形狀最對得上 + 日文品質最專精」三者唯一同時成立的方案。

4. **8GB VRAM 本機 TTS 首選是 GPT-SoVITS**（MIT 授權、**官方在 4060Ti 上實測 RTF 0.028**、中文日文粵韓皆可），其次是 `Fun-CosyVoice3-0.5B-2512`（0.5B、9 語含中日韓、Apache-2.0、含 FastAPI server）。**F5-TTS 權重是 CC-BY-NC，不可商用**——這點常被誤植，務必避開。**Fish Speech 的授權是 Fish Audio Community License：年營收 < US$500,000 可商用，但「以託管服務形式提供 TTS」一律需要另外簽約**，若本專案未來要開 API 對外收費，必須注意。

5. **時間軸對齊的最省事路徑是「讓 TTS 服務直接吐時間戳」**：MiniMax `subtitle_type: "word"`（首選）、Azure 的 `mstts:audioduration`（可強制旁白**剛好等於**目標秒數，0.5×–2× 範圍）＋ SDK 的 `WordBoundary` 事件（次選）、ElevenLabs Forced Alignment API（第三選）。**只有在三者都不可用時**，才在本機跑 WhisperX / whisper-timestamped 做 forced alignment——注意 WhisperX 對 zh/ja 需要另外指定對齊模型，維護成本高。

6. **Lip-sync 選 MuseTalk 1.5**：程式碼 MIT、**模型權重明文允許商用**、**官方在 4GB 顯存的 Windows 筆電上實測過**（fp16 產 8 秒影片約 5 分鐘），且有官方認可的 ComfyUI 節點 `chaojie/ComfyUI-MuseTalk`。LatentSync 1.6 需 18GB VRAM，**在這台機器上只能用 1.5**（剛好 8GB）。**Wav2Lip 不可用於商業**（README 明文：因 LRS2 資料集，任何商業用途被嚴格禁止）。

7. **⛔ Edge-TTS 不可用**（2026-10-19 現況）：自 **2026-10-10** 起 Microsoft Edge read-aloud 的 WebSocket 全面回 403，非官方服務、無商業授權、且 custom SSML 已被移除。詳見 §A.4。

8. **時間軸「鎖片長」用 Azure 的 `mstts:audioduration`**：H3 每段片長固定，與其讓旁白去配合畫面，不如直接命令 TTS 產出**剛好 N 秒**的音訊（0.5×–2× 區間內可調，上限 300 秒）。這是 MiniMax 與 Gemini 都做不到的能力。

---

## A. 雲端 TTS API

### A.1 比較總表

| 服務／模型 | 端點 & 認證 | 語言（zh-CN / zh-TW / ja-JP） | 音色複製 | 情緒／風格控制 | 停頓控制 | 串流 | 字幕／時間戳 | 定價 | 授權 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|
| **MiniMax `speech-2.8-hd` / `-turbo`**【官方】 | `POST https://api.minimax.io/v1/t2a_v2`（中國站 `api.minimax.cn`）；`Authorization: Bearer <key>` | zh-CN ✅／zh-TW ✅（走 `language_boost:"Chinese"`）／ja-JP ✅（`language_boost:"Japanese"`）。全模型共 **40 語**（`language_boost` enum 共 39 個值，含 `Chinese`、`Chinese,Yue`、`Japanese`、`Korean`、`auto`；**沒有單獨的 zh-TW 值**） | ✅ `POST /v1/voice_clone`（10s–5min，mp3/m4a/wav，≤20MB，7 天未用即刪）；另有 `POST /v1/voice_design`（文字描述生音色） | ✅ `voice_setting.emotion`＝**9 值** `happy`/`sad`/`angry`/`fearful`/`disgusted`/`surprised`/`calm`/`fluent`/`whisper`（`fluent`、`whisper` 僅 `speech-2.6-hd`/`-turbo` 支援，2.8 不支援 `whisper`）；`speed` 0.5–2、`vol` (0,10]、`pitch` −12–12；`voice_modify` 另有一組 −100–100 的 `pitch`/`intensity`/`timbre` ＋ `sound_effects`；**`(laughs)` `(sighs)` `(breath)`… 20 種語氣標籤（僅 2.8）** | ✅ `<#0.5#>`，範圍 0.01–99.99 秒 | ✅ HTTP chunked；另有 WSS 單向／雙向流式 | ✅✅ **`subtitle_enable` + `subtitle_type: "sentence"｜"word"｜"word_streaming"`**；非串流回 `data.subtitle_file`（**JSON 檔、毫秒**），串流回 `data.subtitle` / `data.subtitles` | HD **$100／百萬字元**、Turbo **$60／百萬字元**；音色複刻與音色設計另計費 | 商用條款依 platform.minimax.io/protocol/terms-of-service | **無 OpenAI 相容端點**（TTS 僅原生 `t2a_v2`）；速率限制 60 RPM；`text` < 10,000 字元，>3,000 建議走串流 |
| **Google Gemini `gemini-3.8-flash-tts`**【官方】 | `POST https://generativelanguage.googleapis.com/v1beta/interactions`；`x-goog-api-key` | ✅ 自動偵測，**支援 130+ 語**（Flash-Lite 101 語），含 zh/zh-TW/ja | ✅ `POST /v1beta/voices`，`type:"replicated"`，需 **來源音檔 + 同意書音檔**；`store:true`→`voice_…`（專案上限 200 個、TTL 1 年），`store:false`→`voicekey_…`（TTL 7 天） | ✅ `annotations: [{type:"speech_metadata", style:"…"}]` 逐輪指定；行內事件用 `<laugh> <sigh> <short pause>` 等角括號 | ✅ `<short pause>` 等行內標籤 | ✅ | ❌ **無時間戳輸出**（須自行對軸） | 約 **$9／百萬 audio token**，約 $0.81／小時【社群實測】 | Gemini API Terms of Service | 3.8 TTS 一律回 **`audio/wav`（含 RIFF 頭）**；若要 raw PCM 需顯式設 `response_format.mime_type:"audio/l16"` |
| **Google Gemini `gemini-3.8-flash-lite-tts`**【官方】 | 同上 | 101 語 | 同上 | 同上 | 同上 | ✅ | ❌ | 較便宜（lite 層） | 同上 | 高量產／即時代理用 |
| **ElevenLabs**【官方】 | `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`；`xi-api-key` | ✅ 70+ 語（`model_id: eleven_multilingual_v2`／v3） | ✅ Instant Voice Clone / Professional Voice Clone | ✅ `voice_settings`：`stability`（低=情緒範圍大）、`similarity_boost`、`style`、`use_speaker_boost`、`speed` | ✅ 直接在文字中用標點與描述性文字（如 "she said excitedly"） | ✅ chunked，`output_format` 可設 `opus_48000_128` 等 | ⚠️ 需另呼叫 **Forced Alignment API**（`POST /v1/forced-alignment`）取得字／詞時間戳 | Multilingual v2/v3/v4 **$0.08／千字**；Flash/Turbo/v4 Turbo **$0.04／千字**【社群實測，2026-10-15 實測值】 | 依 ElevenLabs 服務條款 | 支援 `previous_text`/`next_text`/`previous_request_ids` 拼接長文；`apply_language_text_normalization` 目前**僅支援日語** |
| **Azure AI Speech**【官方】 | `POST https://{region}.tts.speech.microsoft.com/cognitiveservices/v1`（SSML）；`Ocp-Apim-Subscription-Key` 或 `Authorization: Bearer` | ✅ `zh-CN`／`zh-TW`／`ja-JP` 原生音色；多語音色 `en-US-AvaMultilingualNeural` 等支援 **77 種**語言自動偵測（含 zh-CN／zh-HK／zh-TW／ja-JP） | ✅ Custom Voice（自訂訓練）＋ Personal Voice（`mstts:ttsembedding` + `speakerProfileId`） | ✅✅ **最細**：`mstts:express-as style="…"`（30+ style）、`styledegree` 0.01–2、`role`（8 種年齡／性別角色）、DragonHD 系列另有 60+ style 與 7 種副語音 | ✅ SSML `<break time="500ms"/>` | ✅ | ✅ **SDK `SpeechSynthesisWordBoundaryEventArgs`（offset/duration）**；另有 `mstts:audioduration value="20s"` 可**強制輸出時長** | Azure Neural TTS 依字數計價（區域不同） | Microsoft Azure 條款 | `mstts:viseme type="FacialExpression"` 支援 **zh-CN**；`mstts:backgroundaudio` 可直接混 BGM（單檔、會自動 loop、淡入淡出）——**本專案混音可考慮直接用 SSML 一次搞定** |
| **OpenAI `gpt-4o-mini-tts`**【官方】 | `POST https://api.openai.com/v1/audio/speech`；`Authorization: Bearer` | ✅ 中文、日語（語言支援沿用 Whisper 清單）；但**音色本身為英文最佳** | ⚠️ 需申請 Custom Voice（speaker consent 錄音審核） | ✅ `instructions` 自由文字（口音、情緒範圍、語調、語速、氣音…） | ⚠️ 只能靠標點與文字描述 | ✅ chunked，`response_format` 可為 `wav`/`pcm`/`opus`/`aac`/`flac` | ❌ | 依 OpenAI 平台計價 | OpenAI Usage Policies | **OpenAI 條款要求必須向終端使用者揭露「此為 AI 生成的語音」**；語音清單 13 個（`marin`/`cedar` 品質最佳） |
| **自架 OpenAI 相容閘道**（Irodori-TTS-Server / Local-TTS-Service / GPT-SoVITS-API / Silero+Piper） | `POST {base_url}/v1/audio/speech` | 取決於後端 | 取決於後端 | 取決於後端 | 取決於後端 | 部分支援 SSE 分塊 | 取決於後端 | 免費（算力自付） | 見各專案 | **「自帶 API」功能直接對接此介面** |

### A.2 前 2 名雲端選擇：精確 API 範例

#### ① MiniMax `speech-2.8-hd`（本專案「已知可用」首選）

**最小可用請求**（回傳 JSON，`data.audio` 為 hex 字串，`output_format: "hex"`）：

```bash
curl -X POST "https://api.minimax.io/v1/t2a_v2" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "speech-2.8-hd",
    "text": "他推開門，<#0.5#>屋裡沒有一個人。(sighs)只有窗外的雨聲。",
    "stream": false,
    "language_boost": "Chinese",
    "output_format": "hex",
    "voice_setting": {
      "voice_id": "male-qn-qingse",
      "speed": 1.0,
      "vol": 1.0,
      "pitch": 0,
      "emotion": "sad"
    },
    "audio_setting": {
      "sample_rate": 32000,
      "bitrate": 128000,
      "format": "mp3",
      "channel": 1
    },
    "subtitle_enable": true,
    "subtitle_type": "word"
  }'
```

**關鍵 request 欄位**【官方】（[同步语音合成](https://platform.minimax.io/docs/api-reference/speech-t2a-http) / [中文版](https://platform.minimax.cn/docs/api-reference/speech-t2a-http) / [OpenAPI 規格 JSON](https://platform.minimax.io/docs/api-reference/speech/t2a/api/openapi.json)）：

| 欄位 | 型別 / enum | 說明 |
|---|---|---|
| `model` | `speech-2.8-hd`｜`speech-2.8-turbo`｜`speech-2.6-hd`｜`speech-2.6-turbo`｜`speech-02-hd`｜`speech-02-turbo`｜`speech-01-hd`｜`speech-01-turbo` | 舊版仍可用，但**語氣標籤僅 2.8 支援**。⚠️ 官方更新日志提到部分模型將於 **2026-11-18 退役**，本專案應直接鎖 2.8 |
| `text` | string | < 10,000 字元；> 3,000 建議 `stream:true`；段落以換行分隔 |
| `stream` | bool | 是否 chunked 串流（預設 false） |
| `stream_options.exclude_aggregated_audio` | bool | 預設 false（最後一包含完整音訊）；設 true 可省頻寬 |
| `language_boost` | enum 39 值：`Chinese`｜`Chinese,Yue`｜`English`｜`Japanese`｜`Korean`｜`Arabic`｜`Russian`｜`Spanish`｜`French`｜`Portuguese`｜`German`｜`Turkish`｜`Dutch`｜`Ukrainian`｜`Vietnamese`｜`Indonesian`｜`Italian`｜`Thai`｜`Polish`｜`Romanian`｜`Greek`｜`Czech`｜`Finnish`｜`Hindi`｜`Bulgarian`｜`Danish`｜`Hebrew`｜`Malay`｜`Persian`｜`Slovak`｜`Swedish`｜`Croatian`｜`Filipino`｜`Hungarian`｜`Norwegian`｜`Slovenian`｜`Catalan`｜`Nynorsk`｜`Tamil`｜`Afrikaans`｜`auto` | 預設 `null`（=不強制）；未知語言請用 `auto`。**繁體中文沒有獨立值**，走 `Chinese` |
| `output_format` | `hex`（預設）｜`url` | `url` 回傳的連結**有效期 24 小時**，僅非串流有效 |
| `text_normalization_mode` | `basic`｜`quality` | `quality` 為 LLM＋規則混合正規化，品質較佳但延遲較高；**僅非串流 + `speech-2.8-hd`/`-turbo`/`2.6-hd`/`-turbo` 有效**；設定時 `voice_setting.text_normalization` 會被忽略 |
| `voice_setting.voice_id` | string | 系統音色／複刻音色／AI 生成音色皆可。**使用 `timbre_weights` 時此欄留空** |
| `voice_setting.speed` | number 0.5–2.0（預設 1.0） | 越大越快 |
| `voice_setting.vol` | number (0, 10]（預設 1.0） | 音量 |
| `voice_setting.pitch` | **integer** −12–12（預設 0） | 音高（±1–12 半音） |
| `voice_setting.emotion` | enum：`happy`｜`sad`｜`angry`｜`fearful`｜`disgusted`｜`surprised`｜`calm`｜`fluent`｜`whisper` | **預設由模型依文字自動挑最自然的情緒**，官方建議僅在必要時手動指定。`fluent`/`whisper` 僅 2.6-hd/turbo；**2.8 不支援 `whisper`** |
| `voice_setting.text_normalization` | bool（**已 deprecated**） | 改用頂層 `text_normalization_mode` |
| `voice_setting.latex_read` | bool（預設 false） | **LaTeX 公式朗讀，僅支援中文**；公式需用 `$$...$$` 包起來，設定後 `language_boost` 會被強制設為 `Chinese` |
| `timbre_weights` | `[{voice_id, weight}]`，weight 1–100，**最多混 4 個音色** | **多角色混合配音**（例如旁白 70% + 角色 30%）。必須搭配 `voice_setting.voice_id` 留空 |
| `pronunciation_dict.tone` | string[] | 格式 `原文/替換`。替換可以是：英文 IPA、中文帶調號拼音、**日文平假名／片假名／羅馬字**、純文字。官方例：`"处理/(chu3)(li3)"`、`"20日/はつか"`、`"東京/トウキョウ"`、`"の/no"`、`"omg/oh my god"` |
| `voice_modify.pitch` | integer −100–100 | 深沉↔明亮 |
| `voice_modify.intensity` | integer −100–100 | 強弱 |
| `voice_modify.timbre` | integer −100–100 | 鼻音↔清脆 |
| `voice_modify.sound_effects` | `spacious_echo`｜`auditorium_echo`｜`lofi_telephone`｜`robotic`（一次只能一個） | 支援格式：非串流 mp3/wav/flac、串流 mp3 |
| `audio_setting.sample_rate` | `8000`｜`16000`｜`22050`｜`24000`｜`32000`｜`44100` | 預設 32000 |
| `audio_setting.bitrate` | `32000`｜`64000`｜`128000`｜`256000` | **僅 mp3 適用** |
| `audio_setting.format` | `mp3`（預設）｜`pcm`｜`flac`｜`wav`｜`pcmu_raw`｜`pcmu_wav`｜`opus` | `pcmu_raw`／`pcmu_wav` 為 G.711 μ-law（8kHz）；`opus` 為 Ogg/Opus |
| `audio_setting.channel` | `1`（預設，單聲道）｜`2` | |
| `audio_setting.force_cbr` | bool | **僅串流 + mp3 生效** |
| `subtitle_enable` | bool（預設 false） | 全部 speech 模型皆支援 |
| `subtitle_type` | `sentence`（預設）｜`word`｜`word_streaming` | 見下方 §A.2.1 |
| `stream_format` | string | 串流時可用（僅 mp3） |

**`text` 內可直接寫的標記**（官方 spec 明列）：

| 標記 | 說明 |
|---|---|
| `<#x#>` | 停頓，`x` 為秒數，範圍 `[0.01, 99.99]`（最多兩位小數）。**必須夾在可朗讀文字之間，不可連續使用** |
| `(he2)平` | **行內拼音覆寫**（中文多音字，括號內帶調號 1–5） |
| `(sung3)` | **粵語 Jyutping 覆寫**（調號 1–6） |
| `(lɪv)` | **IPA 覆寫**（英文多音字） |
| `(laughs)` `(chuckle)` `(coughs)` `(clear-throat)` `(groans)` `(breath)` `(pant)` `(inhale)` `(exhale)` `(gasps)` `(sniffs)` `(sighs)` `(snorts)` `(burps)` `(lip-smacking)` `(humming)` `(hissing)` `(emm)` `(sneezes)` | **語氣／副語音標籤，僅 `speech-2.8-hd` 與 `speech-2.8-turbo` 支援** |

**系統音色 ID 實例**【官方】（完整清單見 `/faq/system-voice-id` 或用 Get Voice API 取得）：

- 中文：`Chinese (Mandarin)_Lyrical_Voice`、`Chinese (Mandarin)_HK_Flight_Attendant`、`moss_audio_ce44fc67-7ce3-11f0-8de5-96e35d26fb85`、`moss_audio_aaa1346a-7ce7-11f0-8e61-2e6e3c7ee85d`
- 粵語（`language_boost:"Chinese,Yue"`）：`Cantonese_GentleLady`、`Cantonese_podacast_host_1`
- 英文：`English_Graceful_Lady`、`English_Insightful_Speaker`、`English_radiant_girl`、`English_Persuasive_Man`、`English_Lucky_Robot`
- 日文：`Japanese_Whisper_Belle`、`moss_audio_24875c4a-7be4-11f0-9359-4e72c55db738`、`moss_audio_7f4ee608-78ea-11f0-bb73-1e2a4cfcd245`、`moss_audio_c1a6a3ac-7be6-11f0-8e8e-36b92fbb4f95`

**回應**（`T2aV2Resp`）：

```
data.audio          : hex 編碼音訊（需自行 decode）
data.subtitle_file  : 非串流時的字幕檔下載連結（JSON 格式，句 ≤ 50 字，毫秒）
data.subtitle       : 串流時隨音訊分片送出的當前段落字幕（T2ASubtitle）
data.subtitles      : 串流時最後一包（status=2）彙總本請求所有段落字幕
data.status         : 1=合成中 2=合成完成
extra_info.audio_length / audio_sample_rate / audio_size / bitrate /
          audio_format / audio_channel / usage_characters / usage_voice_count /
          word_count / norm_text_char_count / invisible_character_ratio
trace_id            : 追蹤 ID
base_resp.status_code : 0=成功 1000=未知錯 1001=逾時 1002=速率限制 1004=認證失敗
                       1039=TPM 限制 1042=無效字元 >10% 2013=參數錯誤
```

> 💡 **計費提示**：`extra_info.usage_characters` 才是**計費字元數**；`word_count` 只是參考、不用於計費。`usage_voice_count` 為該次請求計費的音色數（音色**首次使用**才收費）。`invisible_character_ratio` > 10% 會直接報錯 1042。

### A.2.1 MiniMax 字幕時間戳 schema（**本專案對軸的關鍵**）

【官方】（[OpenAPI 規格](https://platform.minimax.io/docs/api-reference/speech/t2a/api/openapi.json)）`T2ASubtitle` / `T2ASubtitleWord`：

```jsonc
{
  "text": "他推開門，屋裡沒有一個人。",   // 段落文字
  "text_begin": 0,                       // 該段在「原始輸入文字」中的起始字元索引（含）
  "text_end": 13,                        // 結束字元索引（不含）
  "time_begin": 0,                       // 起始時間（毫秒，相對於合成音訊起點）
  "time_end": 2450,                      // 結束時間（毫秒）
  "timestamped_words": [                // 僅 subtitle_type = word / word_streaming 時才有；sentence 時為 null
    { "word": "他", "word_begin": 0, "word_end": 1, "time_begin": 0,   "time_end": 180 },
    { "word": "推開", "word_begin": 1, "word_end": 3, "time_begin": 180, "time_end": 420 }
  ]
}
```

**為什麼這對本專案是決定性的**：

1. `text_begin` / `text_end` 是**原始輸入文字的字元索引**。管線只要在送 TTS 前把「每一行台詞」在整份文字中的起訖 offset 記下來，就能**精確**把每個字幕段落映射回它對應的劇本台詞行 → **行邊界不需要猜、不需要 ASR**。
2. `time_begin` / `time_end` 是**毫秒**，可直接寫入 SRT/VTT 或 ffmpeg 的 `adelay`/`atrim` 參數。
3. `timestamped_words` 給到**字級**，可直接產生卡拉 OK 式逐字字幕。
4. 串流模式下 `subtitle_type:"word_streaming"` 會**每個音訊分片都重送**目前段落（`timestamped_words` 與 `time_end` 持續增長），**必須用最新一次覆蓋前一次**；`text_begin` 改變代表進入新段落。

**串流模式的取得方式**（非串流只給 `subtitle_file` 連結）：

```python
import json, requests

def tts_with_word_timestamps(text: str, *, api_key: str, voice_id: str,
                              model: str = "speech-2.8-hd",
                              language_boost: str = "Chinese",
                              emotion: str | None = None) -> tuple[bytes, list[dict]]:
    body = {
        "model": model, "text": text, "stream": False,
        "language_boost": language_boost, "output_format": "hex",
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        "subtitle_enable": True, "subtitle_type": "word",
    }
    if emotion:
        body["voice_setting"]["emotion"] = emotion

    r = requests.post("https://api.minimax.io/v1/t2a_v2",
                      headers={"Authorization": f"Bearer {api_key}",
                               "Content-Type": "application/json"},
                      json=body, timeout=180)
    r.raise_for_status()
    data = r.json()
    if data["base_resp"]["status_code"] != 0:
        raise RuntimeError(data["base_resp"])

    audio = bytes.fromhex(data["data"]["audio"])

    # 非串流：字幕是一個 JSON 檔的連結，需另外下載
    subtitles: list[dict] = []
    url = data["data"].get("subtitle_file")
    if url:
        subtitles = requests.get(url, timeout=60).json()   # 內容為 T2ASubtitle 陣列
    return audio, subtitles
```

> ⚠️ `subtitle_file` 的內容是 **JSON**（不是 SRT），所以要自己轉成 SRT/VTT。官方描述：「Subtitles are aligned to sentences (≤ 50 characters), timestamped in milliseconds, returned in JSON format」。



**音色複刻**：

```bash
# 1) 先上傳參考音檔（≥10s，mp3/m4a/wav，≤20MB）
curl -X POST "https://api.minimax.io/v1/files/upload" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -F "purpose=voice_clone" \
  -F "file=@reference.wav"

# 2) 建立音色
curl -X POST "https://api.minimax.io/v1/voice_clone" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": 123456789,
    "voice_id": "my_narrator_z01",
    "clone_prompt": { "prompt_audio": 987654321, "prompt_text": "This voice sounds natural and pleasant." },
    "text": "A gentle breeze sweeps across the soft grass(breath).",
    "model": "speech-2.8-hd",
    "text_validation": "This voice sounds natural and pleasant.",
    "accuracy": 0.7,
    "need_noise_reduction": false,
    "need_volume_normalization": false,
    "aigc_watermark": false
  }'
```

**音色設計（Voice Design）**：

```bash
curl -X POST "https://api.minimax.io/v1/voice_design" \
  -H "Authorization: Bearer $MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "沉穩的華語男性旁白，語速偏慢，帶電影感，尾音略帶鼻音。",
    "preview_text": "在城市熄燈之後，真相才開始說話。"
  }'
```

> ⚠️ **注意**：`voice_clone` 建立後若 7 天內未被使用，系統會自動刪除【官方】。`voice_design` 亦有 168 小時的啟用期限【社群實測】。本專案若要長期固定旁白音色，**建議在第一次用掉的當下就把音色 ID 寫進設定檔並立即產出一支測試片**。

#### ② Google Gemini `gemini-3.8-flash-tts`

**單人旁白（Interactions API）**：

```bash
curl -X POST "https://generativelanguage.googleapis.com/v1beta/interactions" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.8-flash-tts",
    "input": [{
      "type": "user_input",
      "content": [{
        "type": "text",
        "text": "他推開門，屋裡沒有一個人。<short pause>只有窗外的雨聲。",
        "annotations": [{ "type": "speech_metadata", "style": "沉穩、壓低音量、帶懸疑感的電影旁白" }]
      }]
    }],
    "response_format": { "type": "audio" },
    "generation_config": { "speech_config": [ { "voice": "Kore" } ] }
  }' --output response.json
# 音檔在 steps[].content[].data（base64 WAV）；SDK 用 interaction.output_audio.data
```

**多角色對話**：

```bash
  "generation_config": {
    "speech_config": {
      "speakers": [
        { "voice": "Kore",  "name": "旁白" },
        { "voice": "Puck",  "name": "阿明" }
      ],
      "mode": "conversational"
    }
  }
```

**語音複製（需同意書）**：

```bash
curl -X POST "https://generativelanguage.googleapis.com/v1beta/voices" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "store": true,
    "voice": {
      "model": "gemini-3.8-flash-tts",
      "type": "replicated",
      "display_name": "我的旁白",
      "replicated": {
        "source_audio": { "mime_type": "audio/wav",  "data": "$SOURCE_B64" },
        "consent_audio": { "mime_type": "audio/wav", "data": "$CONSENT_B64" }
      }
    }
  }'
```

**Python SDK（`google-genai >= 2.25.0`）**：

```python
import base64
from google import genai

client = genai.Client()
interaction = client.interactions.create(
    model="gemini-3.8-flash-tts",
    input=[{"type": "user_input", "content": [{
        "type": "text",
        "text": "他推開門，屋裡沒有一個人。",
        "annotations": [{"type": "speech_metadata", "style": "沉穩、有壓力的旁白"}],
    }]}],
    response_format={"type": "audio"},
    generation_config={"speech_config": [{"voice": "Kore"}]},
)
open("vo.wav", "wb").write(base64.b64decode(interaction.output_audio.data))
```

> ⚠️ **遷移陷阱**：舊的 `gemini-2.5-flash-preview-tts` 與 `gemini-3.1-flash-tts-preview` 已被 `gemini-3.8-flash-tts` 取代【官方】。新模型**把輸入文字嚴格視為逐字稿**——`"Say cheerfully: Hello!"` 會被唸出來。風格必須放進 `speech_metadata.style`，只有瞬間性語音事件（`<laugh> <sigh> <cough> <breath> <short pause>`）可留在行內。

### A.3 自架／OpenAI 相容閘道（供「自帶 API」功能指向）

| 專案 | 授權 | 端點 | 備註 |
|---|---|---|---|
| **Irodori-TTS-Server**（[Aratako/Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)） | MIT【官方】 | `POST /v1/audio/speech` | **最推薦**：日語專用、支援 voice cloning、Voice Design（`irodori.caption`）、`response_format` wav/mp3/flac/opus/aac/pcm、`speed` 0.25–4.0、SSE 分塊。預設 port 8088，model id `irodori-tts` |
| **Local-TTS-Service**（[samni728/Local-TTS-Service](https://github.com/samni728/Local-TTS-Service)） | 見 repo | `POST /v1/audio/speech` | OpenAI API 完全相容，可直接插進 Dify / LobeChat / LM Studio / Jan |
| **GPT-SoVITS-API**（[easeaico/GPT-SoVITS-API](https://github.com/easeaico/GPT-SoVITS-API)） | 見 repo | REST | 內建中日英交叉語推理、WebUI 工具（人聲分離、ASR 自動標註） |
| **Silero + Piper 閘道**（[ginto-sakata/local-openai-tts-server](https://github.com/ginto-sakata/local-openai-tts-server)） | 見 repo | `POST /v1/audio/speech` | Silero + Piper，CPU 也能跑，離線免費 |
| **Xinference**（[Xinference](https://github.com/xorbitsai/inference)） | Apache-2.0 | OpenAI 相容 REST | 支援 TTS 模型的統一部署 |
| **RedwindA/GPT-sovits-2-OpenAI**（[repo](https://github.com/RedwindA/GPT-sovits-2-OpenAI)） | 見 repo | OpenAI 相容 | 把 GPT-SoVITS 轉成 OpenAI TTS 格式 |
| **Cloudflare AI Gateway**（[developers.cloudflare.com/ai/models/minimax/speech-2.8-hd](https://developers.cloudflare.com/ai/models/minimax/speech-2.8-hd/)） | 託管 | OpenAI 相容轉接 | 官方文件中即以 MiniMax Speech 2.8 為範例；可統一收單一 base_url |

---

## A.4 Edge-TTS（Microsoft Edge 免費雲端 TTS）現況：**不建議使用**

| 面向 | 現況 | 來源 |
|---|---|---|
| **可用性** | ⛔ **自 2026-10-10 起全站 403**。Microsoft Edge read-aloud 的 WebSocket 只接受 **v2 `Sec-MS-GEC` token**；edge-tts 最新發行版 7.2.8 仍送 v1 token，因此每次合成都拋 `aiohttp.client_exceptions.WSServerHandshakeError: 403, message='Invalid response status'`。**語音清單仍可列出**（`--list-voices` 正常），所以看起來「連得上」，但合成全掛，會留下 0-byte 音檔 | 【社群】[rany2/edge-tts#490](https://github.com/rany2/edge-tts/issues/490)、[hass-edge-tts#78](https://github.com/hasscc/hass-edge-tts/issues/78)、[gist 實測紀錄](https://gist.github.com/veyselsahin/e16b4d9f27ea53428800b1169180f772) |
| **修復狀態** | 有社群提到 v7.3.0 已加入 v2 token 支援【社群】，但上游 issue #490 仍開啟中，**務必自行實測確認** | 【社群】同上 |
| **授權** | ❌ **不適合商用**。edge-tts 是**非官方**第三方 Python wrapper（LGPL-3.0 授權的是**程式碼**，不是 Microsoft 的語音服務），呼叫的是 Edge「閱讀 aloud」端點，不在 Azure 商業授權範圍。Microsoft 官方 Q&A 明確表示：要合法提供 TTS 服務請改用 **Azure AI Speech** | 【官方】[Microsoft Q&A：Are Opensource Edge-TTS free for commercial use?](https://learn.microsoft.com/en-us/answers/questions/2088770/are-opensource-edge-tts-free-for-commercial-use)；另見 [Commercial use rights for Microsoft Edge Read Aloud voices](https://learn.microsoft.com/en-us/answers/questions/6032190/commercial-use-rights-for-microsoft-edge-read-alou) |
| **功能限制** | ⚠️ **custom SSML 已被移除**（Microsoft 禁止 Edge 本身無法產生的 SSML），因此 edge-tts **無法**使用 `mstts:express-as` 情緒 style、**無法** `mstts:audioduration` 鎖定片長，只能有單一 `<voice>` ＋單一 `<prosody>`（rate / volume / pitch） | 【官方】[edge-tts README](https://github.com/rany2/edge-tts) |
| **唯一優點** | 原生支援 `--write-subtitles` 產 SRT（逐句時間戳），以及 `--rate/--volume/--pitch` | 【官方】同上 |

**結論**：Edge-TTS 曾在 2024–2025 是「免費中文旁白」的常見答案，但在 (a) 服務 2026-10-10 起失效、(b) 商用授權不成立、(c) 無情緒 style、無鎖片長 三重問題下，**本專案應直接排除**。要免費且合法的中文/日文旁白，請改用 §B 的本機模型（GPT-SoVITS / CosyVoice3 / Irodori-TTS）；要雲端且要商用，請用 MiniMax 或 Azure AI Speech。

---

## B. 本機 TTS（8GB VRAM 內）

### B.1 比較總表

| 名稱 | 授權 | VRAM | 中文 | 日文 | 情緒控制 | 零樣本克隆 | 安裝難度 | 適合本專案的哪一段 |
|---|---|---|---|---|---|---|---|---|
| **GPT-SoVITS v2ProPlus / v5**（[RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)） | **MIT**（code + 權重）【官方】 | 極低；官方在 **4060Ti 上實測 RTF 0.028**（4090 為 0.014，M4 CPU 為 0.526）【官方】 | ✅ 強（G2PW 多音字前端） | ✅ 支援（日/英/韓/粵/中交叉語） | ⚠️ 弱（原生情緒控制列為待辦【官方】） | ✅ 5 秒零樣本；1 分鐘微調 | **低**：Windows 有整合包 `.7z` 雙擊 `_go-webui.bat`；或 `pwsh -F install.ps1 --Device CU128 --Source HF-Mirror`（Python 3.10 / Torch 2.5.1 / CUDA 12.4） | **本機旁白主力**。RTF 0.028 代表整支短劇旁白可秒級出，迭代成本幾乎為零 |
| **Fun-CosyVoice3-0.5B-2512**（[QwenAudio/CosyVoice](https://github.com/QwenAudio/CosyVoice)，原 FunAudioLLM） | 程式碼 **Apache-2.0**【官方】；權重授權需查 model card | 低（0.5B）；官方 RTF 優化（kv cache + sdpa）【官方】 | ✅✅ 最強：18+ 方言（粵/閩/川/東北/陝西/上海…）+ 中文拼音發音修補 | ✅ 支援（日語列於 9 語之中；1.5B 版在 CV3-Eval 有 ja 欄位） | ✅ **Instruct 支援**：語言、方言、情緒、語速、音量 | ✅ 跨語種零樣本 | **中**：`conda create -n cosyvoice python=3.10` + `pip install -r requirements.txt`；**官方附 FastAPI / gRPC server**（`runtime/python/fastapi`），另有 vLLM 0.9.0 / 0.11.x 路徑 | **本機旁白＋角色多樣化**。FastAPI server 讓它能直接當「自帶 API」的後端 |
| **Irodori-TTS v4.1-Small**（[Aratako/Irodori-TTS](https://github.com/Aratako/Irodori-TTS)） | 程式碼 **MIT**；權重依 model card【官方】 | 中低；**有官方量化版** `int8-weight-only` / `int4-weight-only` / `float8`；MeanFlow 版只需 4 步採樣 | ❌ 純日語模型 | ✅✅ **日語專精**（DACVAE 日本語 codec、48kHz） | ✅✅ **Emoji 風格控制** ＋ `caption` VoiceDesign（可描述「落ち着いた低めの女性の声」等日語特徵） | ✅ 零樣本，參考音檔可串接至 **120 秒** | **中**：`uv sync --extra cu128`（Windows/Linux 皆可）；有 `Irodori-TTS-Server` 提供 OpenAI 相容 API | **日語配音線主幹**。也是「自帶 API」預設範例 |
| **IndexTTS-2.5**（[index-tts/index-tts](https://github.com/index-tts/index-tts)） | **bilibili Model Use License Agreement**（非 MIT；商業合作需洽 `indexspeech@bilibili.com`）【官方】 | 中（0.8B）；官方提供 **BF16 模式**省 VRAM | ✅✅ 極強（CV3-Eval zh WER 3.93 / SS 77.92，開源最佳之一） | ✅✅ 支援 **Japanese Kana 讀音控制**（`<上手|じょうず>`） | ✅✅ **最細**：`emo_alpha`（0–1）、`emo_vector`（8 維：happy/angry/sad/afraid/disgusted/melancholic/surprised/calm）、`emo_text`、`use_emo_text` | ✅ | **中**：`pip install -U uv` → `uv sync --all-extras`（Windows 上建議跳過 deepspeed）；需 CUDA Toolkit 12.8+ | **角色台詞（需要情緒與語速控制）**。`duration_factor` 0.5–2.0 可精準對齊片長。**但授權是本表最大的商業風險點** |
| **Fish Audio S2-Pro**（[fishaudio/fish-speech](https://github.com/fishaudio/fish-speech)） | **Fish Audio Community License**：年營收 < **US$500,000** 可商用；**「託管服務」一律需另簽**【官方】 | 中（S2-Pro 4B，「small enough to deploy on a consumer GPU」）；Drama 3 為 35B-A3B MoE，**8GB 跑不動** | ✅✅ 最強之一（Seed-TTS WER 0.54%） | ✅（CV3-Eval ja WER 5.15 / SS 66.15） | ✅✅ 行內標籤 `[whisper]` `[angry]` `[laughing]` `[pause]`；Drama 3 另有「多輪導演修訂」 | ✅ 10–30 秒 | **高**：官方建議 **SGLang-Omni** 或 vLLM-Omni；需 `speech.fish.audio` 安裝指南 | **角色多場景戲**（Drama 3 的多角色 scene-style 演出）。但授權與 8GB 算力是兩道門檻 |
| **Fish Audio Drama 3**（同上，2026 新旗艦） | 同上 | 35B-A3B（每 token 啟用 3B）→ **8GB 不可行** | ✅ | ✅ | ✅✅ 最強 | ✅ | 高 | 暫不適合本機；可評估雲端 API |
| **VoxCPM 0.5B / VoxCPM2**（[OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)） | **Apache-2.0**【官方】 | 極低（約 1.6GB @ FP16）【社群實測】 | ✅✅（CV3-Eval zh WER 3.88；CosyVoice 官方評測表中 VoxCPM SS 77.2 為最佳之一） | ✅（VoxCPM2 ja WER 6.69 / SS 72.90） | ⚠️ 有限 | ✅ | 低（`pip install voxcpm`） | **快速草稿／量產初稿**。性價比最高的商用許可中文方案 |
| **F5-TTS / E2-TTS**（[SWivid/F5-TTS](https://github.com/SWivid/F5-TTS)） | ⚠️ **程式碼 MIT，但預訓練權重為 CC-BY-NC**（因 Emilia 資料集）【官方】 | 低 | ✅ | ⚠️ 需自行找 JA 權重（HF 上有第三方 Japanese 權重，標 cc-by-nc-4.0） | ⚠️ 有限 | ✅ | 低（`pip install f5-tts`，另有 Docker） | **⚠️ 僅限非商用／內部測試**。商業短劇不要用 |
| **Kokoro 82M**（[hexgrad/kokoro](https://github.com/hexgrad/kokoro)） | **Apache-2.0 權重**【官方】 | 極低（82M） | ✅（`lang_code='z'`，需 `misaki[zh]`） | ✅（`lang_code='j'`，需 `misaki[ja]`） | ❌ | ❌ | 低（Windows 需另裝 espeak-ng `.msi`） | **佔位／預覽／批次預覽用**。品質不足以當最終旁白，但可當「快速 audition」工具 |
| **Chatterbox Multilingual V3**（[resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox)） | **MIT**【官方】 | 低（0.5B） | ✅ | ✅（多語系） | ✅（emotion exaggeration 參數） | ✅ | 低 | **多語系快速旁白**，MIT 授權乾淨，可作 fallback |
| **Qwen3-TTS 1.7B**（[QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)） | 見 repo LICENSE | 中高（1.7B）→ 8GB 需量化 | ✅✅（CV3-Eval zh WER 3.27，最佳） | ✅（ja WER 5.89） | ✅ | ✅ | 中 | 潛力高，但 1.7B 在 8GB 上偏緊 |
| **VibeVoice-1.5B / VibeVoice-Realtime-0.5B**（[microsoft/VibeVoice](https://github.com/microsoft/VibeVoice)） | 見 repo（Microsoft，2025-12 開源 Reatime 0.5B） | 低（0.5B 版） | ✅ | ⚠️ 需確認 | ✅ | ✅ | 中 | **長篇多人對白 podcast 式**。Realtime 0.5B 適合 8GB |
| **Spark-TTS 0.5B**（[SparkAudio/Spark-TTS](https://github.com/SparkAudio/Spark-TTS)） | 見 repo | 低（0.5B） | ✅（CER 1.2 / SS 66.0，SS 偏低） | ⚠️ 未確認 | ✅ | ✅ | 低 | 品質落後 CosyVoice，暫不建議 |
| **Zonos v0.1**（[Zyphra/Zonos](https://github.com/Zyphra/Zonos)） | 見 repo LICENSE | 低 | ✅ | ✅ | ✅ 情緒向量 | ✅ | 低 | 200k+ 小時多語訓練；可作備案 |
| **MegaTTS3**（[bytedance/MegaTTS3](https://github.com/bytedance/MegaTTS3)） | **Apache-2.0**【社群實測／DeepWiki】 | 低 | ✅ | ⚠️ 未明確 | ✅ | ✅ | 中 | 含 **forced-align 版本**，與本專案對軸需求契合，值得實測 |
| **HiggsAudio-v2 3B**（[bosonai/higgs-audio-v2-generation-3B-base](https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base)） | 見 model card | 高（3B）→ 8GB 不適合 | ✅ | ✅ | ✅ | ✅（多角色 `[SPEAKER*]` 標籤） | 中 | 3B 在 8GB 偏重，除非量化 |
| **VoxCPM2 2B**（[OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM)） | Apache-2.0 | 中高 | ✅✅ | ✅ | ✅ | ✅ | 中 | 2B 版品質高於 0.5B 但吃 VRAM |

### B.2 日語專用深挖

| 方案 | 授權 | 語言覆蓋 | 情感控制 | 介面 | 8GB 可行性 | 結論 |
|---|---|---|---|---|---|---|
| **Irodori-TTS v4.1-Small**【官方】 | 程式碼 MIT；權重見 [model card](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small) | **純日語** | ✅✅ Emoji 風格 + caption VoiceDesign + Speaker Inversion（可學出可重用 speaker embedding token） | ✅ `Irodori-TTS-Server`（OpenAI 相容）＋ CLI ＋ Gradio | ✅ 有 int8/int4/float8 量化版；MeanFlow 版 4 步 | **日語首選**。48kHz、AquesTalk 式重音由 `text_normalization.py` 處理，母語級細節 |
| **VOICEVOX ENGINE**【官方】 | **LGPL v3 ＋ 另有多餘授權**（可另行取得商業授權） | 純日語 | ✅✅ 逐詞 **accent_type**（重音核）+ `speedScale` + `pitchScale` + `volumeScale` + `/synthesis_morphing`（兩角色音色混合）＋ `/preset` | ⚠️ **不是 OpenAI 相容**，是兩段式：`POST /audio_query?speaker=N` → `POST /synthesis?speaker=N`；另有 `/streaming_synthesis`（`segment_length`）、`/cancellable_synthesis`、使用者辭典 `/user_dict`、`/accent_phrases` | ✅ CPU/GPU 都可，Docker `voicevox/voicevox_engine:nvidia-latest`，port 50021 | **日語「穩定 × 大量 × 角色多樣」的工業選擇**。重音控制是其他方案沒有的；但 API 形狀特殊，**需要寫專屬 adapter**（本報告的 BYO adapter 建議預留「VOICEVOX 模式」） |
| **Cotoha** | 商用（需洽 Cotoha） | 純日語 | ✅ | 商用 API | — | 商業授權取得麻煩，【推測】不適合開源管線 |
| **GPT-SoVITS ＋ 日語模型** | MIT（引擎）＋ 各自模型授權 | 中英日韓粵 | ⚠️ | WebUI ＋ REST | ✅ | 中文最佳引擎也能做日語，但**需自行訓練／找日語權重**；日語起步點是 `docs/ja/README.md` 與日語微調流程 |
| **Fish Speech S2-Pro** | Fish Audio Community License | ~100 語含日 | ✅ | API server / vLLM-Omni | ✅（4B） | 跨語克隆強，但日語 SS 66.15 落後 CosyVoice3 / IndexTTS2.5 |
| **Kokoro `lang_code='j'`** | Apache-2.0 | 日 | ❌ | Python | ✅✅ | 品質僅供預覽 |
| **VOICEVOX Nemo / AivisSpeech** | 開源系 | 日 | ✅ | OpenAI 相容（部分） | ✅ | 若要走 OpenAI 相容介面，**這兩者可作為日語的 BYO 預設後端**【推測，需實測確認相容度】 |
| **2026 主流開源日語** | — | 2026 年主流開源 TTS（CosyVoice3、IndexTTS-2.5、Irodori、Fish S2-Pro／Drama 3）**皆已把日語列為一等支援語言** | — | — | — | 【官方】IndexTTS-2.5 的 CV3-Eval 有獨立 `ja` 欄位；CosyVoice3 有 CosyVoice3-1.5B 的 ja WER 7.57 |

### B.3 本機 ComfyUI 整合

ComfyUI 端點：`E:\Comfy-Desktop\ComfyUI-Shared\custom_nodes\`。

| 節點包 | 對應模型 | Windows 安裝摩擦 | 備註 |
|---|---|---|---|
| **[AIFSH/CosyVoice-ComfyUI](https://github.com/AIFSH/CosyVoice-ComfyUI)**【官方】 | CosyVoice | 中：需 ffmpeg（Windows 用 [WingetUI](https://github.com/marticliment/WingetUI) 裝）、`pip install -r requirements.txt`；權重由 modelscope 自動下載 | **支援 SRT 輸入做多角色配音**（`tts_srt` / `prompt_wav` / `prompt_srt`），有 `base tts` / `3s clone` / `cross lingual` / `instruct` 四種模式。README 測試環境為 2080Ti 11GB／torch 2.3.0+cu121／Python 3.10.8【社群實測】 |
| **[AIFSH/ComfyUI-GPT_SoVITS](https://github.com/AIFSH/ComfyUI-GPT_SoVITS)**【官方】 | GPT-SoVITS | 中 | voice cloning + TTS |
| **[xiaozhuguang/Comfyui-indextts25-xzg](https://github.com/xiaozhuguang/Comfyui-indextts25-xzg)**【社群實測】 | IndexTTS 2.5 | 中 | 零樣本克隆 + 情緒控制；**Windows 友善度看起來比原生 uv 流程好**【推測】 |
| **[chenpipi0807/ComfyUI-Index-TTS](https://github.com/chenpipi0807/ComfyUI-Index-TTS)**【社群實測】 | IndexTTS 1.5 | 低 | 附音色音檔庫（`TimbreModel`） |
| **[chaojie/ComfyUI-MuseTalk](https://github.com/chaojie/ComfyUI-MuseTalk)**【官方（MuseTalk 官方 README 明列）】 | MuseTalk 1.5 / 1.0 | **高**：`pip install -r requirements.txt` ＋ `mim install mmengine / "mmcv>=2.0.1" / "mmdet>=3.1.0" / "mmpose>=1.1.0"`（mmcv 在 Windows 常需 Visual Studio Build Tools） | 權重放 `ComfyUI/models/diffusers/TMElyralab/MuseTalk/`（musetalk / dwpose / face-parse-bisent / sd-vae / whisper） |
| **[jiafuzeng/comfyui-LatentSync](https://github.com/jiafuzeng/comfyui-LatentSync)**、[iVideoGameBoss/ComfyUI-LatentSync-Node](https://github.com/iVideoGameBoss/ComfyUI-LatentSync-Node)**【社群實測】 | LatentSync | 中 | **本機 8GB 只能跑 1.5**（1.6 需 18GB） |
| **[lum3on/ComfyUI_AudioTools](https://github.com/lum3on/ComfyUI_AudioTools)**【社群實測】 | OS TTS / Whisper | 低 | 內建 **Speech-to-Text + SRT (Whisper)** 節點（`generate_srt` / `srt_max_line_len` / `srt_max_lines` / `srt_max_duration_sec`）、Trim / Pad / Mix / Loudness Meter (LUFS) 等。**注意它的 TTS 節點只調 OS 內建引擎（pyttsx3），品質不可用於正式旁白**【官方 README 明示】 |
| **kijai/ComfyUI-KJNodes** | — | 低 | 通用節點庫，非 TTS 專門 |

> **建議**：ComfyUI 端**不放 TTS 重量模型**。把 TTS 放在「雲端 adapter」或「獨立本機 API server（CosyVoice FastAPI / Irodori-TTS-Server）」，ComfyUI 只用節點呼叫 HTTP，再把音檔拉回來混流。理由：ComfyUI-Desktop 的 Python 環境與 TTS 套件的 torch/CUDA 版本衝突機率高（尤其 mmcv、deepspeed、flash-attn），而本機 server 只需跑在一個乾淨 venv。

---

## C. 混音與時間軸對齊（D）

### C.1 取得每行／每字時間戳的方案比較

| 方法 | 精度 | 是否需額外 ASR | 中文／日文 | 成本 | 來源 |
|---|---|---|---|---|---|
| **MiniMax `subtitle_type: "word"`** | **逐字**，且含**原始文字字元索引**（`text_begin`/`text_end`）與毫秒時間 | **不需要**（TTS 端直接產） | 中 ✅／日 ✅ | 隨 TTS 字元計費 | 【官方】[OpenAPI 規格](https://platform.minimax.io/docs/api-reference/speech/t2a/api/openapi.json) §T2ASubtitle / §T2ASubtitleWord；[同步语音合成](https://platform.minimax.io/docs/api-reference/speech-t2a-http) |
| **MiniMax 非串流 `data.subtitle_file`** | 句／詞 | 不需要 | 中 ✅／日 ✅ | 同上 | 【官方】同上 |
| **Azure `mstts:audioduration value="20s"`** | **不產時間戳，但直接強制時長** | 不需要 | 中 ✅／日 ✅ | Azure 字數計價 | 【官方】[SSML](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice) |
| **Azure SDK `SpeechSynthesisWordBoundaryEventArgs`** | 逐詞（`offset`／`duration`） | 不需要 | 中 ✅／日 ✅ | 同上 | 【官方】[SDK 類別](https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechsynthesiswordboundaryeventargs?view=azure-python) |
| **ElevenLabs Forced Alignment API** | 逐字／逐詞 | 不需要（但要多花一次 API 費） | 多語 | 另計 | 【官方】[Create Forced Alignment](https://elevenlabs.io/docs/api-reference/forced-alignment/create) |
| **WhisperX** | 逐詞（wav2vec2 forced alignment） | 是（本機跑） | ⚠️ 內建對齊模型僅 `{en,fr,de,es,it}`，**zh/ja 需自行指定 HF 模型** | 免費（GPU） | 【官方】[WhisperX README](https://github.com/m-bain/whisperX) |
| **whisper-timestamped** | 逐詞 + 信賴度（用 cross-attention，無需 wav2vec2） | 是 | 需確認中/日覆蓋 | 免費 | 【官方】[linto-ai/whisper-timestamped](https://github.com/linto-ai/whisper-timestamped) |
| **aeneas** | 句／片段 | 是（再做 TTS） | 歐語系較準，中日較弱 | 免費 | 【官方】[readbeyond/aeneas](https://github.com/readbeyond/aeneas) |
| **MiniMax 社群實證** | — | — | — | — | 【社群實測】[OpenVideoHarness PR #69](https://github.com/ZLHad/OpenVideoHarness/pull/69) 明言：整份劇本**一次請求**送出（避免分段合成造成音色漂移），而請求自帶的 `subtitle_type: word` **直接給出每個字的時間**，「行邊界與逐字字幕都不需要再做一次 ASR」 |

### C.2 推薦路徑（中文管線最省事）

**首選：MiniMax `subtitle_type: "word"` → 直接產生 SRT/字級時間軸 → ffmpeg 混流。**
理由：(1) 零額外成本、零額外模型、零對齊失敗率；(2) TTS 與時間戳來自同一次推論，**保證音訊與字幕完全一致**（ASR 反而會有辨識誤差）；(3) 一次送出整份旁白稿 → 音色零漂移【社群實測】。

**關鍵實作細節（靠 `text_begin`/`text_end` 做「台詞行 → 時間軸」的精確映射）**【官方】：

```python
# 送 TTS 前，先把整份旁白稿拼成單一字串並記錄每一行的字元區間
lines = ["他推開門，屋裡沒有一個人。", "只有窗外的雨聲。"]
offsets, pos = [], 0
for ln in lines:
    offsets.append((pos, pos + len(ln)))   # (text_begin, text_end)
    pos += len(ln) + 1                    # +1 = 換行符
full_text = "\n".join(lines)

audio, subtitles = tts_with_word_timestamps(full_text, api_key=..., voice_id=...)

# 每個字幕段落都帶 text_begin/text_end，直接二分回它對應的台詞行
for sub in subtitles:
    line_idx = next(i for i, (b, e) in enumerate(offsets) if b <= sub["text_begin"] < e)
    print(line_idx, sub["time_begin"], sub["time_end"], sub["text"])
```

如此一來：**每一行台詞都有精確的起訖毫秒數**，ffmpeg 可用 `adelay`/`atrim` 精準貼合，或直接轉 SRT。

**次選（需要「音訊精準填滿片段」時）：Azure SSML `mstts:audioduration`。** 例如旁白要剛好佔 12.0 秒：

```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">
  <voice name="zh-CN-XiaoxiaoNeural">
    <mstts:express-as style="narration-professional" styledegree="1.2">
      <mstts:audioduration value="12s"/>
      他推開門，屋裡沒有一個人。只有窗外的雨聲。
    </mstts:express-as>
  </voice>
</speak>
```

`mstts:audioduration` 可把輸出時長壓在原音的 **0.5×–2×** 區間內，上限 300 秒【官方】。這對「H3 生成的每段片長是固定的」這件事極度關鍵：**旁白長度由片子決定，而不是由文字決定。**

**第三選：ElevenLabs Forced Alignment**（已在 ElevenLabs 帳號、且希望用 ElevenLabs 的音色時）。

**最後手段：WhisperX**（只用於「音源來自非 TTS」的情境，例如使用者上傳的真人錄音）。注意 WhisperX 對中文與日語需另指定 `DEFAULT_ALIGN_MODELS_HF` 之外的對齊模型【官方】。

### C.3 ffmpeg 混流

旁白 + 環境音 + BGM 三軌合成（示意）：

```bash
# 1) 旁白單軌
ffmpeg -i narration.mp3 -i env.wav -i bgm.mp3 \
  -filter_complex \
    "[1:a]volume=0.35[env];[2:a]volume=0.12,afade=t=in:d=2,afade=t=out:st=13:d=2[bgm];\
     [0:a]aresample=48000,apad=pad_dur=15[vo];\
     [env][bgm][vo]amix=inputs=3:duration=first:dropout_transition=0[mix]" \
  -map "[mix]" -c:a aac -b:a 192k -ar 48000 final.m4a

# 2) 貼到影片（H3 產出的 mp4）
ffmpeg -i h3_clip.mp4 -i final.m4a -c:v copy -c:a copy -shortest final.mp4
```

要點：`-ar 48000` 統一採樣率（避免 AAC 聲道數／採樣率不符報錯）；`-shortest` 避免音訊拖長；`apad=pad_dur` 讓旁白音軌長度足以容納畫面。

---

## D. Lip-sync（8GB GPU 可用者）

| 名稱 | 授權 | 8GB 可行？ | 輸入音訊 | 解析度 | 備註 |
|---|---|---|---|---|---|
| **MuseTalk 1.5**（[TMElyralab/MuseTalk](https://github.com/TMElyralab/MuseTalk)） | ✅ **程式碼 MIT**；✅ **模型權重「available for any purpose, even commercially」**；⚠️ 內部依賴（whisper、ft-mse-vae、dwpose、S3FD）各自授權；測試資料僅供非商用研究【官方】 | ✅ **官方在 Windows + RTX 3050 Ti Laptop 4GB 上實測**：fp16 產 8 秒影片約 **5 分鐘** | ✅ 外部音訊（`audio_path`） | 人臉區 **256×256**（需另接超分如 GFPGAN） | **本專案首選**。支援中文／英文／日文音訊；`bbox_shift` 可調嘴部張開程度；官方認可 ComfyUI 節點 `chaojie/ComfyUI-MuseTalk` |
| **LatentSync 1.5**（[bytedance/LatentSync](https://github.com/bytedance/LatentSync)） | 見 repo（開源計畫含 inference + training code）【官方】 | ✅ **官方明載：推論最低 8GB（1.5）** | ✅ 外部音訊 | 256×256（1.5） | 時間一致性較佳、**中文影片表現有改善**（1.5 變更重點） |
| **LatentSync 1.6** | 同上 | ❌ **需 18GB VRAM** | ✅ | **512×512**（緩解模糊） | 這台機器**不可用**，若要 512 需雲端 GPU |
| **Wav2Lip**（[Rudrabha/Wav2Lip](https://github.com/Rudrabha/Wav2Lip)） | ❌ **僅個人／研究／非商用**；README 明文：因 LRS2 資料集，**任何商業用途被嚴格禁止**；商業需洽 `rudrabha@synclabs.so` | ✅ | ✅ | 192×288 | **商業短劇不可用**。若要走 Wav2Lip 路徑，官方已轉向付費 sync.so API |
| **LatentSync 2.0（POC）**（[Shazinho10/LatentSync2.0](https://github.com/Shazinho10/LatentSync2.0)） | 見 repo | 待驗 | ✅ | 待驗 | 【社群實測】為 LatentSync 的改進 POC，非官方 |
| **Sonic / Ditto / EchoMimic / EchoMimicV2 / Hallo2 / V-Express / HunyuanVideo-Avatar** | 各異 | ⚠️ 多數 > 8GB 或非「外部音訊驅動既有影片」模型 | 部分是「單張圖＋音訊→影片」，與本專案的「H3 已生成影片→改嘴型」需求不同 | — | 【推測】本專案是「已有影片 + 外部 TTS 音訊」的場景，**MuseTalk / LatentSync 1.5 才是對的工具**；Hallo2、EchoMimic 等屬「重新生成角色表演」，不適合「已定稿分鏡 + 外部旁白」的工作流 |
| **Azure `mstts:viseme type="FacialExpression"`** | Azure 條款 | — | — | — | 【官方】可由 TTS 直接輸出 **blend shapes**（zh-CN 支援），若日後走 3D 角色（Live2D / Unity / UE）而非 2D 影片，這是最直接的 lip-sync 路徑 |

---

## E. 「自帶 API」Adapter 規格（管線 UI 該暴露哪些欄位）

### E.1 建議的 UI 欄位（`provider = "custom"`）

| UI 欄位 | 對應 JSON 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|---|
| **Base URL** | `base_url` | string | ✅ | 例 `https://api.minimax.io`、`https://api.openai.com`、`http://127.0.0.1:8088`。**內部一律 `POST {base_url}/v1/audio/speech`；若使用者填了含 `/v1` 的完整路徑，要做正規化避免 `/v1/v1`** |
| **API Key** | `api_key` | string | ✅ | 以 `Authorization: Bearer {api_key}` 送出；**不寫入版本控制，存 OS 憑證管理員或環境變數** |
| **Model** | `model` | string | ✅ | 例 `gpt-4o-mini-tts`、`tts-1-hd`、`irodori-tts`、`eleven_multilingual_v2` |
| **Voice** | `voice` | string | ✅ | 例 `coral`、`marin`、`Kore`、`Puck`、`male-qn-qingse`、自訂 `voice_…`／`voicekey_…` |
| **Response Format** | `response_format` | enum | ✅ | `mp3` / `wav` / `pcm` / `opus` / `aac` / `flac` / `webm`（後段用 ffmpeg 統一轉 wav） |
| **Speed** | `speed` | float | ⬜ | 0.5–2.0（OpenAI 相容常見範圍；Irodori 支援 0.25–4.0） |
| **Instructions** | `instructions` | string | ⬜ | 風格／情緒描述（OpenAI `gpt-4o-mini-tts` 專用） |
| **Custom Headers** | — | object（key→value） | ⬜ | 例 `{"xi-api-key": "..."}`（ElevenLabs 不用 Bearer）、`{"X-API-Key": "..."}`、`{"anthropic-version": "..."}` |
| **Auth Header 名稱** | — | string | ⬜ | 預設 `Authorization`，可改成 `X-API-Key` |
| **Auth Header 前綴** | — | string | ⬜ | 預設 `Bearer `（ElevenLabs 為空字串） |
| **Extra Body（進階）** | — | object | ⬜ | 整包 JSON 直併進 request body，覆寫任何預設值 |
| **Stream** | `stream` / `stream_format` | bool / string | ⬜ | OpenAI 相容用 chunked；Irodori 用 `stream_format: "sse"` |

### E.2 實作注意（決定相容性成敗的細節）

1. **認證雙軌制**：OpenAI / MiniMax / Irodori 用 `Authorization: Bearer`；ElevenLabs 用 `xi-api-key`；部分自架服務接受 `api_key` 查詢參數。因此 **Auth Header 名稱與前綴必須可設定**。
2. **端點後綴正規化**：接受 `base_url` 帶或不帶 `/v1`，輸出端點一律正規化為 `{base_url}/v1/audio/speech`。
3. **回應形狀**：OpenAI 相容回傳**純音訊 bytes**；MiniMax 回傳 **JSON**（音訊在 `data.audio` hex 或 `data.subtitle_file`）；Gemini 回傳 **JSON**（音訊在 `steps[].content[].data` base64）。**因此 adapter 必須有「回應解析器」開關：`binary` | `json_audio_field` | `gemini_steps`**。
4. **時間戳回傳**：新增 `return_timestamps` 布林值。開啟時，adapter 盡量向服務索取（MiniMax `subtitle_enable`／`subtitle_type`、ElevenLabs forced-alignment、Azure word boundary）；服務不支援時**明確回報「此後端無時間戳」**，由管線決定是否 fallback 到本機 WhisperX。
5. **長文分塊與音色一致性**：若後端支援 `previous_text` / `next_text`（OpenAI 類）或 MiniMax 的「一次送出整份稿」（≤10,000 字元），**優先一次送出**，避免分段合成造成音色漂移【社群實測】。
6. **錯誤處理**：所有雲端 TTS 都會回 4xx/5xx JSON（`{"error": {...}}` 或 `{"base_resp": {...}}`），adapter 必須把 body 原樣帶回，不要只丟 HTTP code。
7. **音訊正規化**：統一轉 **48kHz / 單聲道 / PCM wav** 後才進 ffmpeg，避免 AAC 混流時的採樣率與聲道數不符。

### E.3 對接既有管線的最小程式碼骨架

```python
# tts/providers/openai_compatible.py  （「自帶 API」模式）
import base64, json, requests

def synthesize(text: str, *, base_url: str, api_key: str, model: str, voice: str,
               response_format: str = "wav", speed: float = 1.0,
               instructions: str | None = None, extra_headers: dict | None = None,
               auth_header: str = "Authorization", auth_prefix: str = "Bearer ") -> bytes:
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    headers = {"Content-Type": "application/json"}
    if auth_prefix:
        headers[auth_header] = f"{auth_prefix}{api_key}"
    else:
        headers[auth_header] = api_key
    headers.update(extra_headers or {})

    body = {"model": model, "input": text, "voice": voice, "response_format": response_format}
    if speed != 1.0:
        body["speed"] = speed
    if instructions:
        body["instructions"] = instructions

    r = requests.post(f"{url}/audio/speech", headers=headers, json=body, timeout=180)
    r.raise_for_status()
    ctype = r.headers.get("Content-Type", "")
    if ctype.startswith("application/json"):          # 相容層可能回 JSON
        data = r.json()
        if "data" in data and isinstance(data["data"], dict):   # MiniMax 風格
            hexstr = data["data"].get("audio")
            if hexstr:
                return bytes.fromhex(hexstr)
            url_ = data["data"].get("audio") or data.get("audio")
            if isinstance(url_, str) and url_.startswith("http"):
                return requests.get(url_, timeout=180).content
        raise RuntimeError(f"unexpected JSON payload: {data}")
    return r.content
```

```python
# tts/providers/minimax.py  （專屬 adapter：唯一能拿到內建時間戳的雲端）
# 欄位名依官方 OpenAPI：https://platform.minimax.io/docs/api-reference/speech/t2a/api/openapi.json
import requests

EMOTIONS = ["happy", "sad", "angry", "fearful", "disgusted", "surprised",
            "calm", "fluent", "whisper"]          # fluent/whisper 僅 speech-2.6-*；2.8 不支援 whisper
AUDIO_FORMATS = ["mp3", "pcm", "flac", "wav", "pcmu_raw", "pcmu_wav", "opus"]
SAMPLE_RATES = [8000, 16000, 22050, 24000, 32000, 44100]
BITRATES = [32000, 64000, 128000, 256000]

def synthesize_with_timestamps(text, *, api_key, model="speech-2.8-hd", voice_id,
                               emotion=None, subtitle_type="word", audio_format="mp3",
                               language_boost="Chinese", base="https://api.minimax.io"):
    body = {
        "model": model,
        "text": text,
        "stream": False,
        "language_boost": language_boost,
        "output_format": "hex",
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000,
                          "format": audio_format, "channel": 1},
        "subtitle_enable": True,
        "subtitle_type": subtitle_type,     # sentence | word | word_streaming
    }
    if emotion:
        body["voice_setting"]["emotion"] = emotion
    # 其他可選：text_normalization_mode="quality" / voice_setting.latex_read=True
    #           / voice_setting.timbre_weights=[{"voice_id":..,"weight":70}, ...]（最多 4 個）

    r = requests.post(f"{base}/v1/t2a_v2",
                      headers={"Authorization": f"Bearer {api_key}",
                               "Content-Type": "application/json"},
                      json=body, timeout=180)
    r.raise_for_status()
    data = r.json()
    if data["base_resp"]["status_code"] != 0:
        raise RuntimeError(data["base_resp"])       # 1002=速率限制 1004=認證失敗 1042=無效字元>10% ...

    audio = bytes.fromhex(data["data"]["audio"])
    # 非串流：字幕檔（JSON 格式、毫秒、含 text_begin/text_end 字元索引）
    subtitles = []
    if url := data["data"].get("subtitle_file"):
        subtitles = requests.get(url, timeout=60).json()
    return audio, subtitles, data.get("extra_info", {})
```

---

## F. 落地建議（給本專案的具體決策）

### F.1 最終推薦組合

| 產線段落 | 建議方案 | 理由 |
|---|---|---|
| **中文旁白（主力）** | **雲端 MiniMax `speech-2.8-hd`**（已知可用） | 同供應商即用、內建 word 級時間戳、`<#x#>` 停頓 + 語氣標籤、$100/百萬字元 |
| **中文旁白（離線/成本 backup）** | **本機 GPT-SoVITS v2ProPlus**（MIT，4060Ti RTF 0.028） | 零成本、零網路、迭代快；情緒控制弱，故只做「草稿與 fallback」 |
| **中文旁白（本機進階）** | **Fun-CosyVoice3-0.5B-2512**（Apache-2.0，含 FastAPI server） | 方言、拼音發音修補、Instruct 情緒；且有 server 可當 BYO 後端 |
| **日語配音** | **本機 Irodori-TTS v4.1-Small + Irodori-TTS-Server**（OpenAI 相容）＋ 商用前確認權重授權 | 日語母語級、MIT 程式碼、API 形狀直接對上 BYO 介面 |
| **日語大量角色** | **VOICEVOX ENGINE**（需寫專屬 adapter） | 重音控制與角色數是同類最強；授權為 LGPL＋另購 |
| **語氣精細的角色台詞** | **IndexTTS-2.5**（`emo_vector` / `emo_alpha` / `duration_factor`） | 但**授權是 bilibili 專屬，商業前必須確認** |
| **時間軸對齊** | MiniMax `subtitle_type:"word"` → SRT；**需要「旁白剛好等於片長」時改用 Azure `mstts:audioduration value="12s"`** | 不做第二次 ASR，音字保證一致；Azure 的 audioduration 可把音訊鎖死在指定秒數 |
| **Lip-sync** | **MuseTalk 1.5**（MIT + 商用權重，4GB 實測過） | 唯一在 8GB 上有官方實測、授權允許商用、又吃外部音訊的方案 |
| **BYO API** | OpenAI 相容 `POST {base_url}/v1/audio/speech` + 可設定 auth header／前綴／額外 headers | 同時打中 OpenAI、Irodori-Server、Local-TTS-Service、GPT-SoVITS-API、Cloudflare Gateway |

### F.2 四個必須避開的坑

1. **Edge-TTS 當「免費已知可用」** → 自 2026-10-10 起全站 403，且無商業授權、無情緒 style、無鎖片長（見 §A.4）。
2. **H3 影片 prompt 仍要求角色說話** → 會與外部旁白疊音。若 H3 仍須輸出對白，就必須**分軌**：H3 音軌靜音或降低、或在 ffmpeg 層做 ducking，且 H3 prompt 中的 `overall_soundscape` 應明寫「no dialogue, no narration, only ambience」。
3. **F5-TTS 權重是 CC-BY-NC**（README 明確寫「pre-trained models are licensed under the CC-BY-NC license due to the training data Emilia」）→ 不可用於商業短劇。
4. **Fish Speech 的託管條款** → 內部使用 OK（營收 < $500k），但**把 TTS 做成對外服務必須另簽**；若本專案規劃把配音能力包進 SaaS，這是合約層級的阻斷點。

### F.3 待實測（本報告未能一手驗證的項目）

- 【推測】`voice_setting.emotion` 的 7 個值在**繁體中文（zh-TW）**下的表現；MiniMax 官方列 40 語但未逐語列舉方言覆蓋。
- 【推測】CosyVoice3 **權重**（非程式碼）的授權細節——程式碼 LICENSE 檔為 Apache-2.0，但 README 另有一句「for academic purposes only」的免責語，**投產前務必讀 HuggingFace model card 的 license 欄**。
- 【社群實測】IndexTTS-2.5 與 CosyVoice3-1.5B 在 8GB VRAM 上的實際峰值顯存（官方 RTF 皆在 RTX 4090 上測得）。
- 【推測】`Irodori-TTS-Server` 的 `speed` 0.25–4.0 與中文輸入的相容性（模型為純日語）。
- 【推測】WhisperX 在中文／日文的對齊模型選擇（`DEFAULT_ALIGN_MODELS_HF` 之外的 HF 對應模型）。

---

## 附錄：主要來源索引

**雲端 API**
- MiniMax 同步語音合成：https://platform.minimax.io/docs/api-reference/speech-t2a-http　｜中文版：https://platform.minimax.cn/docs/api-reference/speech-t2a-http
- MiniMax WSS 語音合成：https://platform.minimax.io/docs/api-reference/speech-t2a-websocket
- MiniMax 音色複刻：https://platform.minimax.io/docs/api-reference/voice-cloning-clone
- MiniMax 音色設計：https://platform.minimax.io/docs/api-reference/voice-design-design
- MiniMax 定價：https://platform.minimax.io/docs/pricing/overview
- MiniMax Speech 2.8 說明（社群）：https://minimax-ai.chat/models/minimax-speech-2-8/
- Gemini 語音生成：https://ai.google.dev/gemini-api/docs/speech-generation
- Gemini 3.8 Flash TTS：https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts
- Gemini 音色設計：https://ai.google.dev/gemini-api/docs/voice-design　｜音色複製：https://ai.google.dev/gemini-api/docs/voice-replication
- ElevenLabs 建立語音：https://elevenlabs.io/docs/api-reference/text-to-speech/convert　｜強制對齊：https://elevenlabs.io/docs/api-reference/forced-alignment/create
- Azure SSML：https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice
- Azure WordBoundary 事件：https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.speechsynthesiswordboundaryeventargs?view=azure-python
- OpenAI 文字轉語音：https://developers.openai.com/api/docs/guides/text-to-speech

**本機 TTS**
- CosyVoice（QwenAudio）：https://github.com/QwenAudio/CosyVoice　｜論文：https://arxiv.org/abs/2505.17589
- GPT-SoVITS：https://github.com/RVC-Boss/GPT-SoVITS
- Irodori-TTS：https://github.com/Aratako/Irodori-TTS　｜Server：https://github.com/Aratako/Irodori-TTS-Server
- IndexTTS：https://github.com/index-tts/index-tts　｜論文：https://arxiv.org/abs/2601.03888
- Fish Speech：https://github.com/fishaudio/fish-speech　｜S2 報告：https://arxiv.org/abs/2603.08823　｜Drama 3 報告：https://arxiv.org/abs/2610.18010
- F5-TTS：https://github.com/SWivid/F5-TTS
- Kokoro：https://github.com/hexgrad/kokoro
- VoxCPM：https://github.com/OpenBMB/VoxCPM
- Qwen3-TTS：https://github.com/QwenLM/Qwen3-TTS
- VibeVoice：https://github.com/microsoft/VibeVoice
- Spark-TTS：https://github.com/SparkAudio/Spark-TTS
- Zonos：https://github.com/Zyphra/Zonos
- MegaTTS3：https://github.com/bytedance/MegaTTS3
- VOICEVOX ENGINE：https://github.com/voicevox/voicevox_engine
- Chatterbox：https://github.com/resemble-ai/chatterbox

**ComfyUI / Lipsync / 對齊**
- ComfyUI-MuseTalk：https://github.com/chaojie/ComfyUI-MuseTalk
- CosyVoice-ComfyUI：https://github.com/AIFSH/CosyVoice-ComfyUI
- ComfyUI-GPT_SoVITS：https://github.com/AIFSH/ComfyUI-GPT_SoVITS
- ComfyUI AudioTools：https://github.com/lum3on/ComfyUI_AudioTools
- LatentSync：https://github.com/bytedance/LatentSync
- MuseTalk：https://github.com/TMElyralab/MuseTalk
- Wav2Lip：https://github.com/Rudrabha/Wav2Lip
- WhisperX：https://github.com/m-bain/whisperX
- whisper-timestamped：https://github.com/linto-ai/whisper-timestamped
- aeneas：https://github.com/readbeyond/aeneas
- MiniMax 社群實測（整稿一次請求 + 內建字幕時間軸）：https://github.com/ZLHad/OpenVideoHarness/pull/69
- Edge-TTS repo：https://github.com/rany2/edge-tts　｜403 issue：https://github.com/rany2/edge-tts/issues/490
- Microsoft Q&A（Edge-TTS 商用授權）：https://learn.microsoft.com/en-us/answers/questions/2088770/are-opensource-edge-tts-free-for-commercial-use
- Edge read-aloud 商用權利 Q&A：https://learn.microsoft.com/en-us/answers/questions/6032190/commercial-use-rights-for-microsoft-edge-read-alou
