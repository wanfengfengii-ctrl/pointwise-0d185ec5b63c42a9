# 涂层试验室复测交班台账

收样员登记检验轮，测量员冻结两片试片的偏差，分析员核对原读和勘误，质控员签发该轮唯一正式判定。复测班按轮领取，凭固定的试片出处核账。

## 运行

要求 Python 3.11，使用标准库。回归和演示均使用各自的临时目录。

```text
python3 -B check_project.py
python3 -B demo.py
```

## 数据库和入口

创建两个独立的 `sqlite3.Connection`，分别连接分析库和签发库文件。每次连接或重开后，在空闲连接上调用 `analysis.initialize_analysis(source)`，以及 `issuance.initialize_issuance(desk)` 和 `handover.initialize_handover(desk)`。同一连接上的入口由调用者串行使用，独立工作者使用各自的连接。写入入口各自管理本地事务。初始化保留已有轮次、修订、报告、续办和领用记录。分析端离线时向 `sign` 显式传入 `None`，`claim` 和 `review_claim` 只需要签发库。

| 操作 | Python 入口 | 持久业务结果 |
| --- | --- | --- |
| 开轮 | `rounds.open_round(source, round_id, first_specimen, second_specimen, rule_name, threshold, unit='μm')` | 固定登记顺序、两片身份和具名规程。 |
| 冻结 | `measurements.freeze_revision(source, round_id, revision_id, readings, *, parent_revision=None)` | 保存完整读数对及出处。勘误指定同轮父修订。返回 `FrozenRevision`。 |
| 预览 | `analysis.inspect_revision(source, round_id, revision_id)` | 返回固定 `FrozenAnalysis`，其中包含读数对、规程、分数均值和判定。 |
| 启用勘误 | `analysis.correct_revision(source, round_id, revision_id)` | 返回 `CorrectionResult`，状态为 `active`、`view_only` 或 `pending`。 |
| 首签及续办 | `issuance.sign(source, desk, round_id, revision_id, request_id, *, progress=None)` | 返回 `SignResult`，状态为 `issued`、`stale` 或 `pending`。`issued` 带正式报告及原请求号。 |
| 领用 | `handover.claim(desk, round_id)` | 返回 `ClaimResult` 或 `None`。已领轮次重复调用读回同一领用记录。 |
| 核账 | `handover.review_claim(desk, round_id, report_id)` | 返回既有领用及固定报告，轮号、报告号或领用记录不匹配时返回 `None`。 |

轮号、片号、规程名、修订号和请求号是非空白的字符串。修订名的作用域为同一轮。读数使用 `Reading(round_id, specimen_id, deviation, origin)`，其中 `deviation` 是整数 μm。使用 `bind_read_origin(specimen_id, record_id, location)` 固定原读，再用 `inherit_read_origin(origin)` 沿用原记录，或用 `record_corrected_origin(origin, record_id, location)` 登记不同的勘误出处。位置是仪器记录或试验单中可定位的非空文本。勘误保持父件逐片的最初原读关联。试片和出处始终成对保存和显示。

复测线接受非负 `int` 或 `Fraction`。偏差可以为负。两片等权取精确算术均值，达到线判 `retest`，低于线判 `release`。判定和报告均保留分数及单位。开轮或冻结参数不合法时抛出 `ValueError`，缺少指定轮或冻结件时抛出 `LookupError`。非法冻结保持原有资料完整。重复登记轮、重复冻结同名修订及同号异参签发均抛出 `ValueError`。

冻结原测确立初始候选。后续冻结可以独立预览。在首签以前，`correct_revision` 每次成功启用其显式指定的合法勘误，成为该轮当前版。首签裁决成立后调用勘误返回 `view_only`，原报告依据保持固定。错过资格的请求返回 `stale`。另一请求已经取得首签时，用原请求号续办或按轮领取。签发库一旦登记请求号就固定轮和修订。暂不能确认时返回 `pending`，可用原参继续。正式报告和成功回执在签发库同次提交。

`progress(stage, detail)` 是调用方可选的进度回调。`candidate_saved` 提供当时观察到的当前修订，`decided` 提供已持久化的首签裁决，`confirmed` 提供已提交的报告。前两阶段返回 `False` 可暂缓交付，后续使用原请求续办。回调在事务外运行，回调抛出的异常由调用方接收。正式确认后即使调用方未收到回包，原号仍可重领。

演示用两轮相同清册和复测线。首轮更正先生效，班组领到 R2 的 9 μm 放行。次轮首签先成立，正式报告提交后的回包中断，班组断源后领取 R1 的 10 μm 复测。演示还核对签发前的待核，以及按两片对应的原读出处复核。
