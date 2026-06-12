# production_tool_v2 変更点

2026-06-12 の障害(Proxmox/HA再起動後、拠点A・拠点Bとも電力取得が停止し、Cube本体の電源オフオンまで復旧しなかった)を受けた自己復旧版です。`production_tool/` は変更せず、本フォルダを別バージョンとして管理します。

変更ファイルは `mqtt_bridge.py` のみです。それ以外(インストーラ、rcファイル、設定)は `production_tool/` と同一です。

## 障害の根本原因(推定)

旧版の `mqtt_bridge.py` には以下の欠陥がありました。

1. **ERXUDP連続タイムアウトで再joinしない**: MQTTブローカー停止中は `_reconnect()` がメインループをブロックし、その間にPANAセッションが失効する。ブローカー復帰後にポーリングは再開するが、タイムアウト分岐は診断を送るだけで再joinせず、`wisun_status: timeout` を刻みながら永遠に停止する。
2. **再join失敗後にポーリングへ戻る**: 例外経路の再joinが1回失敗すると、死んだセッションへのポーリングに戻ってしまう。
3. **PANA関連イベント(EVENT 24/29)を無視**: ポーリング中のセッション失効・認証失敗を検知しない。

## v2 の自己復旧ロジック(段階式)

1. **ERXUDP無応答が3回連続**(`TIMEOUT_REJOIN_THRESHOLD`)→ ポーリングをやめてWi-SUN再joinへ移行。
2. **再joinはバックオフ付きで成功まで継続**: 30秒から開始し失敗ごとに2倍、最大300秒(`REJOIN_BACKOFF_INITIAL` / `REJOIN_BACKOFF_MAX`)。死んだセッションへのポーリングには戻らない。リトライ中も `reconnect_failed` を毎回publishし、MQTT pingで接続を維持する。
3. **join/再join失敗が5回連続するたび**(`SERIAL_REOPEN_AFTER`)→ シリアルポート(`/dev/ttyS1`)を閉じて開き直す(モジュール通信路のリセット)。
4. ポーリング中の **EVENT 24**(PANA認証失敗)は即座に再joinへ移行。**EVENT 29**(セッション失効)はモジュールの自動再認証を待ち、失敗すればEVENT 24か連続タイムアウト経由で再joinに落ちる。

Cube本体の再起動(段階3)は本バージョンには含めません。ブリッジ自身がハングするケースには別プロセスのwatchdogが必要なため、今後の課題とします。

無限再起動ループの懸念について: 本バージョンの復旧アクションは「再join」と「シリアル開き直し」のみで、本体再起動を行わないため再起動ループは発生しません。再joinリトライはバックオフ最大300秒で頭打ちのため、スマートメーター側への過負荷もありません。

## 導入方法

USBの自動実行はフォルダ名 `production_tool` を前提とするため、**USBメモリへコピーする際にフォルダ名を `production_tool` に変更**してください。

1. `config.json` と `wpa_supplicant.conf` を対象宅向けに設定(`config.site_a.example.json` / `config.site_b.example.json` 参照)。
2. FAT32のUSBメモリ直下に `CubeJMTS.txt` と、本フォルダを `production_tool` という名前でコピー。
3. Cube J1に挿して電源投入。LED白点滅10回で完了。

## 検証手順

導入後に確認すること:

- HAで瞬時電力と最終取得時刻が更新される(平常運転)。
- `wisun_status` が `timeout` を3回刻んだ後に `reconnecting` → `connected` へ自己復旧すること(機会があれば。強制的に試すならスマートメーターから離れた場所で起動するなど)。
- まず片方の宅(拠点B推奨)で数日安定稼働を確認してから、もう片方へ展開する。

旧版に戻す場合は `production_tool/` を同じ手順でUSBへコピーして再導入します。
