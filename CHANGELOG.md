# Changelog

TeleRelay 的版本变更记录，按版本倒序排列。

Release history for TeleRelay, newest first. Each version lists its summary and every
commit it contains.

版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## v1.3.0 — 2026-09-11

预览：支持发送纯文本消息，可直接播放视频、浏览图片相册，图片和视频的查看体验也更顺手  
统计：可以按小时查看转发情况，旧数据会自动补齐  
队列：待发送任务能随时暂停或一键清空，可以翻页查看、删除单条；发送失败最多重试 3 次，之后自动跳过  
规则：可以把常用的聊天存成一组，在规则里直接引用；也可以只转发带媒体的消息  
导出：重启后未完成的导出会自动继续，计划任务可以随时修改或临时关闭  
登录：除了手机号，现在也可以用二维码登录

Preview: send plain-text messages, play videos right in the browser, and browse photo albums, with a smoother image and video viewer  
Statistics: view forwarding activity by hour, with older data filled in automatically  
Queue: pause or clear the pending list at any time, page through it, and delete single items; failed sends retry up to three times and are then skipped  
Rules: save frequently used chats as a group and reference it from a rule, and forward media-only messages  
Export: unfinished exports continue after a restart, and scheduled tasks can be edited or turned off  
Sign-in: QR code login in addition to phone number

共 45 个提交 / 45 commits

[`0ffa5cb`](https://github.com/journey-ad/telerelay/commit/0ffa5cb294068cf58b982f1eb67974c38e98d06e) fix: render rule group references with the chat group picker  
[`88d82c8`](https://github.com/journey-ad/telerelay/commit/88d82c86cd6053a6d25ad332edd4b303154cbbd3) fix: drop the chat group enable switch and use the chat selector  
[`4eb2675`](https://github.com/journey-ad/telerelay/commit/4eb267588ed30530e9f3bf19e916c4a4e1cc8655) feat: recover exports interrupted by a restart  
[`c8e70eb`](https://github.com/journey-ad/telerelay/commit/c8e70eba6a08b7cd24a8f2aa8d85ea45d6363df0) feat: notify the console when a scheduled export starts  
[`6501a8e`](https://github.com/journey-ad/telerelay/commit/6501a8e4cb20cad7aa246ee5644c9f6933241395) feat: publish a running export's message count  
[`6967155`](https://github.com/journey-ad/telerelay/commit/6967155fc2c5cb02cb14b58471bcc9951852bc5d) perf: stream export reads and bound the per-chat archive cache  
[`48852dd`](https://github.com/journey-ad/telerelay/commit/48852dd9b94dc9180160d8a69cffaf3aaeec7272) fix: correct and stabilize the trend's dashed estimate segment  
[`b165f36`](https://github.com/journey-ad/telerelay/commit/b165f3682ea15d3657c5a03183fa65ab663b5216) fix: mark banned or deleted chats Telegram drops from the dialog list  
[`6801069`](https://github.com/journey-ad/telerelay/commit/6801069f02558bb5c0c24fbd3aef986571ccce75) fix: keep the trend sweep continuous and the running bucket dashed  
[`2942d68`](https://github.com/journey-ad/telerelay/commit/2942d6804aafee9928d148967d355761554e0105) feat: project the running bucket in the throughput trend  
[`eed53d3`](https://github.com/journey-ad/telerelay/commit/eed53d36868dd88bd1a33dc72386266be9064282) refactor: drop the account column from the queue preview  
[`dada996`](https://github.com/journey-ad/telerelay/commit/dada9968927a44dd41f975a80e6446e50c1560bd) feat: flag unusable chats in the chat pickers  
[`d08b1d2`](https://github.com/journey-ad/telerelay/commit/d08b1d2d24f22942fcbd106bc2b59b11c85c225f) feat: edit and toggle scheduled export tasks  
[`1f73a8a`](https://github.com/journey-ad/telerelay/commit/1f73a8aaceda002c2caa6bab8a783fb4799ed1a3) fix: cap queue retries at three and skip permanently failing targets  
[`260e77d`](https://github.com/journey-ad/telerelay/commit/260e77d7b48716af6624a8b736045dd82d8367ee) feat: add queue clear and pause controls  
[`5c639a9`](https://github.com/journey-ad/telerelay/commit/5c639a96eb1d318eb8586caaba47341bbe8eea4d) feat: add media-only filter mode for forwarding rules  
[`6a3ea65`](https://github.com/journey-ad/telerelay/commit/6a3ea654a9aaed40d8733df8471bd26c23756005) fix: stretch live events panel  
[`bfd48e1`](https://github.com/journey-ad/telerelay/commit/bfd48e1bddba4d26731cceafc0647e234f76dab6) fix: generalize dashboard trend empty state  
[`35cf7eb`](https://github.com/journey-ad/telerelay/commit/35cf7eb91ed8fe6e1f7397dfc4b3f331d5eee49b) feat: add reusable chat groups for forwarding rules  
[`f73386b`](https://github.com/journey-ad/telerelay/commit/f73386b6499325182fedabf5ae4ff5018e872e27) fix: include media stats in daily reports  
[`4ef420d`](https://github.com/journey-ad/telerelay/commit/4ef420dd01f538f0b6f33547d98a8af0bf5763a5) refactor: migrate persistence to SQLAlchemy ORM  
[`4a7115f`](https://github.com/journey-ad/telerelay/commit/4a7115f37c727e22fca81b244f9dc2308ecb3b25) refactor: simplify queue and stats persistence  
[`3f76da6`](https://github.com/journey-ad/telerelay/commit/3f76da6ac4aa4510fca6d1f1509ffc634e4b0826) refactor: simplify queue and stats control flow  
[`729b247`](https://github.com/journey-ad/telerelay/commit/729b247845e202a65c64f97b2a4c700b6d623bd4) feat(queue): schedule forwarding fairly per rule  
[`f94f369`](https://github.com/journey-ad/telerelay/commit/f94f36915405e34871bd7fa2f136cd2e9dc074bd) feat(stats): add one-day hourly trend  
[`8d453a8`](https://github.com/journey-ad/telerelay/commit/8d453a8b255a1131228c44b400ac25fc0cabfe18) feat(queue): paginate backlog preview  
[`78fb117`](https://github.com/journey-ad/telerelay/commit/78fb117059782886418579a9f3401744865e1232) fix(dashboard): plot failures from zero baseline  
[`5d7af04`](https://github.com/journey-ad/telerelay/commit/5d7af04d2a6d393953eab193e9b719a29c9c1cff) fix(forward): respect disabled force upload  
[`fd3fbf5`](https://github.com/journey-ad/telerelay/commit/fd3fbf55926d84ba547c84b154e8638307a62f97) fix(stats): backfill legacy data into hourly metrics  
[`a1ebf78`](https://github.com/journey-ad/telerelay/commit/a1ebf78c84d9bfb7a495f54a67488fc0c3e7744f) feat(stats): add hourly throughput insights  
[`57562b2`](https://github.com/journey-ad/telerelay/commit/57562b24626e0e75d01033be3e2169e8d6649320) feat(queue): allow deleting backlog tasks  
[`e29e8d7`](https://github.com/journey-ad/telerelay/commit/e29e8d7b1d12aa090fc6b2b22829a6f63842e118) feat(automation): support bot start links  
[`ce16184`](https://github.com/journey-ad/telerelay/commit/ce161844fbb835655031f46d591116c431759918) feat(auth): add QR code login alongside phone login  
[`8228a65`](https://github.com/journey-ad/telerelay/commit/8228a65b0c53d9d48ed33d26c7408dd19b78748d) feat(frontend): improve media cache diagnostics  
[`f72ede2`](https://github.com/journey-ad/telerelay/commit/f72ede2270c8d258644d1b9ac792d2b5f518806a) fix(stats): make history ordering deterministic for same-ms inserts  
[`cdc18dc`](https://github.com/journey-ad/telerelay/commit/cdc18dcd4ca2da9109adf72d3d978826e728b3b1) refactor(preview): serve media browser-direct with pooled DC sessions  
[`9b1a9b0`](https://github.com/journey-ad/telerelay/commit/9b1a9b03e76e2acb373f5f8ead0005ce0f9bfc98) refactor(preview): extract resolve_active_account and clean up dead code  
[`b068aee`](https://github.com/journey-ad/telerelay/commit/b068aeea3191a62605964529ffcee8b520d26ea9) feat(preview): fit lightbox images to viewport on open  
[`2311647`](https://github.com/journey-ad/telerelay/commit/2311647b0d25a29300b9bf4e5e9ab4e220132e96) fix(preview): recover disconnected Telegram sessions  
[`37aba8e`](https://github.com/journey-ad/telerelay/commit/37aba8eca83307c2e3f5b9dd1ca9bd9f017cd282) fix(preview): stabilize browser-direct Telegram video  
[`ebed6dd`](https://github.com/journey-ad/telerelay/commit/ebed6ddff566bc07109c9f0f1c3c49471d609896) feat(preview): improve Telegram image albums and lightbox  
[`216d582`](https://github.com/journey-ad/telerelay/commit/216d5826b74f138ffeee99a16201d95ae83fb667) feat(preview): add direct Telegram video playback  
[`585e206`](https://github.com/journey-ad/telerelay/commit/585e206712b8b79af5eda9621027305a298ecc16) feat(preview): add link and video cards  
[`a908b5f`](https://github.com/journey-ad/telerelay/commit/a908b5f39dc47f979125abf23d439b2cda7b9bd1) feat(preview): add media viewer interactions  
[`907ac84`](https://github.com/journey-ad/telerelay/commit/907ac8421beb5a31ca104a328082e416756bba2e) feat(preview): send plain-text messages with live updates

**完整变更 / Full changelog**: [v1.2.0...v1.3.0](https://github.com/journey-ad/telerelay/compare/v1.2.0...v1.3.0)
---

## v1.2.0 — 2026-08-03

Bot：可以开关命令菜单，新增推送订阅命令与订阅者控制台  
设置：表单按配置项自动生成，日志可以只看某个账号的  
预览：链接按 Telegram 返回的数据渲染，系统消息显示为可读文字  
预览：图片和视频边看边加载，并缓存最近看过的内容  
修复：Bot 模式转发媒体组时不再漏消息

Bot: toggle the command menu, with new subscription commands and a subscriber console  
Settings: the form is generated from the configuration itself, and logs can be filtered to a single account  
Preview: links are rendered from Telegram's own data, and system messages show readable text  
Preview: images and videos load as you browse, with recently viewed items cached  
Fixes: media groups are no longer partially forwarded in bot mode

共 11 个提交 / 11 commits

[`ea61e46`](https://github.com/journey-ad/telerelay/commit/ea61e4656245abc94ae0278576e1ff09887db5bf) feat(bot): add command menu toggle  
[`e65f281`](https://github.com/journey-ad/telerelay/commit/e65f28118e46c3ef93354fffbae3cea1959e512d) feat(logs): filter runtime logs by account  
[`e4f26e4`](https://github.com/journey-ad/telerelay/commit/e4f26e42328a9ee2caca04291733a2744fef7681) feat(settings): add schema-driven config form  
[`80a5e14`](https://github.com/journey-ad/telerelay/commit/80a5e14d3c6504baaf7bfdcaef2e1592169cacc4) fix(forwarder): forward complete media groups for bot sessions  
[`fd21983`](https://github.com/journey-ad/telerelay/commit/fd21983ba98f9f3092167c06e3afa6781a01a32d) style(frontend): reformat rules stats memo  
[`f31f3e5`](https://github.com/journey-ad/telerelay/commit/f31f3e509fb55b65d7beef7fc0190632bb06c50d) refactor(frontend): use hash-based routing  
[`7af88a5`](https://github.com/journey-ad/telerelay/commit/7af88a5c12f289e8f25ee483966d577c7f249b2d) feat(bot): add push subscription commands and subscriber console  
[`c37612e`](https://github.com/journey-ad/telerelay/commit/c37612e971c013d0ec3ce886da59f385dd817a89) feat(preview): render links from Telegram entities, drop linkifyjs  
[`c29ea58`](https://github.com/journey-ad/telerelay/commit/c29ea5807ccc5ef51cc630c947af8503741d7734) feat(preview): show readable text for service messages  
[`69393a5`](https://github.com/journey-ad/telerelay/commit/69393a58b476d2eb4c4e9f5ed25a41b345e9a36a) feat(preview): progressive media loading with LRU blob cache  
[`40f92af`](https://github.com/journey-ad/telerelay/commit/40f92aff258aabd6c1bd4f283510cd5dd59adef0) feat(frontend): add favicon matching sidebar brand

**完整变更 / Full changelog**: [v1.1.0...v1.2.0](https://github.com/journey-ad/telerelay/compare/v1.1.0...v1.2.0)
---

## v1.1.0 — 2026-08-03

多账号：可以同时运行多个账号，各自的配置和数据分开存放，互不影响  
账号切换：切换账号时聊天列表和预览会自动刷新  
规则：每条规则可以单独启用或停用，列表中能看到触发次数；转发时可以选择不带上媒体说明文字  
仪表盘：流量强度图更直观，导出预览支持翻页  
其他：聊天搜索支持用户名、ID 或 @handle，手机端底部导航文案更短

Multiple accounts: run several accounts at once, each with its own settings and data  
Account switching: the chat list and preview refresh automatically when you switch  
Rules: enable or disable each rule, see how many times it fired, and forward without media captions  
Dashboard: a clearer traffic intensity chart, and a paginated export preview  
Other: search chats by username, ID, or @handle, and shorter labels in the mobile bottom navigation

共 14 个提交 / 14 commits

[`1a6235a`](https://github.com/journey-ad/telerelay/commit/1a6235a814555457956c6ad849885733ee26a965) feat: show fixed 60 bars for all-time traffic intensity  
[`cb68c91`](https://github.com/journey-ad/telerelay/commit/cb68c91006bdc1ab3beb385b0e5c4eb3edddbb1c) fix: match chat username and id with @handle search  
[`5380262`](https://github.com/journey-ad/telerelay/commit/53802620e1cfe2e2360a916b3a3129666461febb) feat: add hide media caption forwarding option  
[`877b95d`](https://github.com/journey-ad/telerelay/commit/877b95d0c22e2cdc7a5394914f83ae926dd1aaa0) feat: show rule trigger counts in lists  
[`0ea21d0`](https://github.com/journey-ad/telerelay/commit/0ea21d05a50599b1eadc796997ef2e1d96bc34d6) feat: improve dashboard intensity and export preview/pagination  
[`36d6ff6`](https://github.com/journey-ad/telerelay/commit/36d6ff61d0972ffc8e64dc3c8d2f2e6d7860473d) feat: hide docs in production and polish logs/settings UI  
[`f52b65d`](https://github.com/journey-ad/telerelay/commit/f52b65d4f5370f0df29b0c1b1749b5979fe61983) feat: add account refresh sync and polish preview UI  
[`6b3b452`](https://github.com/journey-ad/telerelay/commit/6b3b452e2acd3a5c44b44e813b6bcbb2b0493e08) feat: add multi-account bot support  
[`4d7f19f`](https://github.com/journey-ad/telerelay/commit/4d7f19f0d96aaa1975816a6f9007b68ada27549b) feat: isolate account data and improve session selectors  
[`1db47d8`](https://github.com/journey-ad/telerelay/commit/1db47d84aefbc51e0422788add42c99a4e2661ca) feat: add rule enable controls  
[`ccf81ee`](https://github.com/journey-ad/telerelay/commit/ccf81ee58debddd927e9b71befa3f2ea0c813955) feat: isolate Telegram account data and config  
[`b87cf5c`](https://github.com/journey-ad/telerelay/commit/b87cf5cafdff9451d436077bb2feab36bcc07508) fix: shorten mobile bottom navigation labels  
[`b7f52f2`](https://github.com/journey-ad/telerelay/commit/b7f52f2d4754db1172cecbf75de29fd4abfe4e9c) fix: localize mobile bottom nav and log level labels  
[`a4e5079`](https://github.com/journey-ad/telerelay/commit/a4e50795d228c9e50f8b3877b115f47990855409) feat: expose release commit in update-check

**完整变更 / Full changelog**: [v1.0.0...v1.1.0](https://github.com/journey-ad/telerelay/compare/v1.0.0...v1.1.0)
---

## v1.0.0 — 2026-07-31

转发：一条规则可以转发到多个目标，支持强制转发、成组转发媒体、隐藏发送者，以及按关键词过滤  
队列：转发遇到限流会自动排队重试，服务重启后任务不会丢  
导出：把聊天记录导出成可离线打开的 HTML，也能按群组导出  
统计：转发记录与统计保存在本地数据库，仪表盘报表更完整  
控制台：界面重写为 React，支持中英文、访问密码与版本更新检查

Forwarding: one rule can target several chats, with force forward, media groups, hidden senders, and keyword filters  
Queue: rate-limited sends queue up and retry automatically, and tasks survive a restart  
Export: save chat history as HTML you can open offline, including per-group exports  
Statistics: forwarding history and stats are stored in a local database, with fuller dashboard reports  
Console: the UI is rewritten in React, with Chinese and English, an access password, and update checks

共 87 个提交 / 87 commits

[`79d1700`](https://github.com/journey-ad/telerelay/commit/79d1700f44868c787a9db5462bf45d066dd94057) ci: upgrade GitHub Actions to Node 24 runtimes  
[`cb0ce28`](https://github.com/journey-ad/telerelay/commit/cb0ce2899a0bec4e1b1872a989af522c2643fc46) feat: inject build-time version resolved from git tags  
[`0ee6741`](https://github.com/journey-ad/telerelay/commit/0ee674131b7dd3e6a1510d3d7f2b9c80d430ccfa) fix: localize dashboard live events and surface account context  
[`0725271`](https://github.com/journey-ad/telerelay/commit/072527140827d97c2a7417cceae6b57e0691d738) feat: support export run deletion and polish history table  
[`d36da40`](https://github.com/journey-ad/telerelay/commit/d36da402b3c5936414858ed4a5d6f9e3c0871449) feat: add online HTML archive preview and export progress polish  
[`056c3fa`](https://github.com/journey-ad/telerelay/commit/056c3fa1f31ce3e3864d27b918fa592b5ef64184) feat: add version info, update check, and SSE-driven state sync  
[`b47c825`](https://github.com/journey-ad/telerelay/commit/b47c825bf650d78412209337162391b2a03e29c6) build: unify development workflow  
[`97e4110`](https://github.com/journey-ad/telerelay/commit/97e411008d81d861dc3941fecf183720622576ef) refactor: improve i18n locale tooling  
[`68bdb55`](https://github.com/journey-ad/telerelay/commit/68bdb55dab630aea8d389530dc8618a52b3ced1a) feat: hot reload forwarding rules  
[`f2b524e`](https://github.com/journey-ad/telerelay/commit/f2b524e7290eddbf85af642c06a093f20110dd6a) feat: preview queue and expand dashboard events  
[`9af20d5`](https://github.com/journey-ad/telerelay/commit/9af20d5010b0d23c41197e45b21b2c3dbdf275f4) refactor: extract shared TelegramChatService from export subsystem  
[`5eb9a3a`](https://github.com/journey-ad/telerelay/commit/5eb9a3adbd58a03ce062a194d85040f7591f715d) chore: complete backend log i18n coverage and update readme  
[`8e2ce66`](https://github.com/journey-ad/telerelay/commit/8e2ce6659b12457c70eb6d58e37ba1bcd2e62845) feat: auto-load older messages on scroll with reply-jump suppression  
[`49cd97b`](https://github.com/journey-ad/telerelay/commit/49cd97b816f9d6f1864008ca9eb3b7e71ad267d9) feat: add linkifyjs for clickable links in message preview and history  
[`f1d4f50`](https://github.com/journey-ad/telerelay/commit/f1d4f504a65c1a3ba7b4b499ddc25ff433799c2c) refactor: introduce parallel per-account runtime registry  
[`d7d71d2`](https://github.com/journey-ad/telerelay/commit/d7d71d2d4b75086c023f2f25e178c582e743687b) refactor: extract avatar utility and improve color contrast helpers  
[`073e840`](https://github.com/journey-ad/telerelay/commit/073e8401fcc28fc9765f02e187d4b88c60dac338) refactor: streamline preview rendering and clean up i18n usage  
[`a40765e`](https://github.com/journey-ad/telerelay/commit/a40765ef9e4a0ab5c7cbcad1973ed380e0ab8f98) feat: add i18n support with Chinese and English locales  
[`f982099`](https://github.com/journey-ad/telerelay/commit/f982099bc6903ceca90e72fa1c933b6734a75a3d) feat: secure Telegram preview media cache  
[`146cdf5`](https://github.com/journey-ad/telerelay/commit/146cdf52ae5916a382acd43cbaab490fa8c833ea) feat: enhance dashboard reporting and add confirm dialog component  
[`d95f470`](https://github.com/journey-ad/telerelay/commit/d95f470ae4422bf28ed1885b289aa96d606c014f) feat: add Telegram message preview with authenticated media proxying  
[`b2a919a`](https://github.com/journey-ad/telerelay/commit/b2a919a62cd80d3e33b634e56bc43a5f1de7c337) feat: add multi Telegram account management  
[`e5433d2`](https://github.com/journey-ad/telerelay/commit/e5433d27689ea581946ef90700ff72d72da81060) build: disable pnpm minimumReleaseAge check  
[`f670dae`](https://github.com/journey-ad/telerelay/commit/f670daeff49e2cb78c9604835e71d9848826f4c4) build: move pnpm config into package manifest  
[`3ca6e3b`](https://github.com/journey-ad/telerelay/commit/3ca6e3b8c731e5b0bcac1f7ea90a573c6b0d5bdc) feat: expand dashboard reporting  
[`cf97fc6`](https://github.com/journey-ad/telerelay/commit/cf97fc620c83ebe62a958e8513fb1d440d3eea2a) feat: refine rule editing and export controls  
[`90c65da`](https://github.com/journey-ad/telerelay/commit/90c65da71115c66c0f4177b997293aae4dcff410) refactor: migrate frontend from Vue to React with Radix UI  
[`14dbb38`](https://github.com/journey-ad/telerelay/commit/14dbb381d49d2881c2270f57bed8ec9ca7be7c71) feat: add React admin console  
[`e7865bc`](https://github.com/journey-ad/telerelay/commit/e7865bcfc3e2bc5ced7a1ae35a845888e1331e14) refactor: replace gradio with fastapi and vue  
[`c331cb3`](https://github.com/journey-ad/telerelay/commit/c331cb3b1b97702564c9b2d89edae72ab1cff193) feat: persist message exports in sqlite  
[`dc848e8`](https://github.com/journey-ad/telerelay/commit/dc848e873b0389bdbb395d9682f1d175038a48b6) feat: support clicking all matching buttons  
[`2f5f8bc`](https://github.com/journey-ad/telerelay/commit/2f5f8bca2d87071b65a24d6e617962f3c71bb801) refactor: streamline operational logging  
[`3d52289`](https://github.com/journey-ad/telerelay/commit/3d522890e72c9fb196a413f15219714d04186000) feat: add message callback button handling  
[`ac2a522`](https://github.com/journey-ad/telerelay/commit/ac2a5227e3aaf1fb8c83e905a6bce8bc58b98625) feat: add persistent forwarding queue  
[`2f4d864`](https://github.com/journey-ad/telerelay/commit/2f4d8642a7400702da0d172839aa6e23a20b3ad1) wip: add html export reply list  
[`bf7d6ca`](https://github.com/journey-ad/telerelay/commit/bf7d6ca343ec2f8f477659b366cccebf63cbf62c) wip: export chunk html  
[`76d58e5`](https://github.com/journey-ad/telerelay/commit/76d58e52fae0e9dbaf6b9c7a53cd94f58e05e2b6) wip: add group export  
[`cfe6949`](https://github.com/journey-ad/telerelay/commit/cfe6949ccc752746bfdb246544acdae63668179a) fix: retry target on FloodWait and skip dedup on retry  
[`bb0a9e0`](https://github.com/journey-ad/telerelay/commit/bb0a9e02f974c206141ad5f8a1ba683cfc58966e) fix: prevent tmp dir disk exhaustion from force-forward  
[`05b80a2`](https://github.com/journey-ad/telerelay/commit/05b80a213c92cf5f552885077e56177b21d9fd6d) wip: add stats report  
[`72e9c89`](https://github.com/journey-ad/telerelay/commit/72e9c894030a7c2f94c41d28db656cdb56b252f1) feat: persist forward stats via SQLite  
[`b20eaf6`](https://github.com/journey-ad/telerelay/commit/b20eaf66f5127ce0e0f263012b8ca21aad9cfdf9) refactor: change log rotation to daily  
[`011d307`](https://github.com/journey-ad/telerelay/commit/011d307f3dc61a368dd3fa32b941a8f76e65767b) refactor: rename session dir to data  
[`fe1ba2d`](https://github.com/journey-ad/telerelay/commit/fe1ba2d6b61fa617e371870487a5a682d36bfc14) feat: integrate Telegram Mini App for WebUI configuration  
[`e90d98b`](https://github.com/journey-ad/telerelay/commit/e90d98b39c873a3d17bf645f8de2bda3798f31db) feat: add admin bot for managing rules  
[`8da7adc`](https://github.com/journey-ad/telerelay/commit/8da7adc8de2e60a6b6fb3a4a06bc67a5a28a146e) fix: handle webpage preview in forwarding  
[`0ea70f1`](https://github.com/journey-ad/telerelay/commit/0ea70f16b013bc033bfa34c107f8f4d19d67c98c) fix: preserve message formatting when forwarding  
[`d522b38`](https://github.com/journey-ad/telerelay/commit/d522b381e1d5d46d7b838b43484dd8e52e84a594) feat: support hide sender  
[`af771ae`](https://github.com/journey-ad/telerelay/commit/af771ae6c798d9c7b3e3c47967c8c5c7c34d7ad0) docs: update README  
[`fb512d8`](https://github.com/journey-ad/telerelay/commit/fb512d80525da25c8bc05c55d7c8dc8647f70caa) feat: new rule auto disabled  
[`c8745f3`](https://github.com/journey-ad/telerelay/commit/c8745f3806817cab74e11f65f0d348174d24b07b) fix: fix wrong i18n key and add checker script  
[`124449f`](https://github.com/journey-ad/telerelay/commit/124449fb58c21b4477352f1cd343f49964d92d59) chore: add .dockerignore  
[`2fccf14`](https://github.com/journey-ad/telerelay/commit/2fccf14222ada1844d96c626f737c0034c4f9237) chore: remove language switcher from UI and simplify language config  
[`427fe73`](https://github.com/journey-ad/telerelay/commit/427fe734454de8d3d80e889bc1c5b87abd87218c) docs: update README  
[`d7d0909`](https://github.com/journey-ad/telerelay/commit/d7d090907d114946a3d7b8ab13d88ccf1214a35c) refactor: rename project to TeleRelay and unify all references  
[`14dea26`](https://github.com/journey-ad/telerelay/commit/14dea2648696076e576d037bd0176b1032777915) feat: add i18n support with Chinese and English language switching  
[`26b32e8`](https://github.com/journey-ad/telerelay/commit/26b32e8910c6356757518a3c7d16dc9b3becff5e) refactor: refactor forwarder module and fix duplicate download issue  
[`6ee3986`](https://github.com/journey-ad/telerelay/commit/6ee3986448db7fcadd196f602771d64e2a7a4bca) refactor: optimize UI polling frequency and merge timers  
[`9e0cceb`](https://github.com/journey-ad/telerelay/commit/9e0ccebb645cc11e780add8e52cfa8f4133f69c6) refactor: refactor forwarder and optimize log output, support session auto-login  
[`2df16ab`](https://github.com/journey-ad/telerelay/commit/2df16ab6e7de8d9164b5ef92a3e4174e2882f5bf) fix: fix media group forwarding issue and support complete media group handling  
[`0fca571`](https://github.com/journey-ad/telerelay/commit/0fca5713dedfcb917827b286f88cac6f6168cbda) feat: add force forward feature to bypass noforwards restriction  
[`8a75a67`](https://github.com/journey-ad/telerelay/commit/8a75a672e01c21023b63f383bc13bfcc2c4c9fbc) ci: add Docker image build for dev branch  
[`7988819`](https://github.com/journey-ad/telerelay/commit/798881935a1f17354d8b5fee6b8c7c3b5a686d6f) feat: add multi-rule management feature and related UI improvements  
[`d34a0c3`](https://github.com/journey-ad/telerelay/commit/d34a0c33905333229c4070d58745180bb5e25e60) feat(ui): add click to expand/collapse for configuration groups  
[`3b04ab6`](https://github.com/journey-ad/telerelay/commit/3b04ab6daa4c0e270bb3c13eb0227bf2f7cb70ea) feat: add WebUI authentication for User mode  
[`824ef14`](https://github.com/journey-ad/telerelay/commit/824ef14d7bb175f46099b3c8b44d12661aa125d6) fix: fix WebUI placeholder escape characters and optimize config file structure  
[`66583ad`](https://github.com/journey-ad/telerelay/commit/66583ad41f76dcd4b0e7cf2f763c8189ba0a6c03) docs: update README.md  
[`768ffaa`](https://github.com/journey-ad/telerelay/commit/768ffaa7024d772e64463fbf9684f58142d62e46) docs: add CLAUDE.md and FEATURE_REQUEST.md  
[`7271a0d`](https://github.com/journey-ad/telerelay/commit/7271a0d7bdb8c2b5883372246ddc3c212582f9f0) refactor: refactor WebUI to modular structure and improve thread safety  
[`94ac26d`](https://github.com/journey-ad/telerelay/commit/94ac26d6a58dcb46e5116289d5a5ca961d83b775) feat: add user and keyword ignore list feature and refactor configuration  
[`70e2240`](https://github.com/journey-ad/telerelay/commit/70e22408cd51b768a2389f2e32aa146c3493c44a) fix: fix Dockerfile build issue  
[`5748c80`](https://github.com/journey-ad/telerelay/commit/5748c80c306cf76c9181f8b4088fa155ae52d147) feat: add HTTP Basic Auth authentication  
[`84d2fca`](https://github.com/journey-ad/telerelay/commit/84d2fcabdb35c677f314abbcb9ba46ae32118053) feat: smart Bot restart after configuration save  
[`211468c`](https://github.com/journey-ad/telerelay/commit/211468c90bf10a64937a3d3d753352fc965a6e9c) refactor: optimize log output and UI update timing  
[`bac67dc`](https://github.com/journey-ad/telerelay/commit/bac67dcac3a15c51a77d5c851418863e70b63518) feat: auto trigger UI update on Bot start/stop  
[`414986d`](https://github.com/journey-ad/telerelay/commit/414986d9678ef5dd2917f85eb73d1486df4b7e30) feat: add auto status refresh feature  
[`6896a8e`](https://github.com/journey-ad/telerelay/commit/6896a8eaa50f2fa2e998842ecb4c81fbb8a3f2fc) feat: add status refresh button and enhance forwarding logs  
[`cc8b3d9`](https://github.com/journey-ad/telerelay/commit/cc8b3d9c9109ab94980b5f269a7cec2fbbf0b453) fix: update requirements.txt to add required Gradio dependencies  
[`d8743cb`](https://github.com/journey-ad/telerelay/commit/d8743cb569375c4efc0519ad8e5c4a81a9452495) feat: migrate to Gradio WebUI  
[`6ff6a3e`](https://github.com/journey-ad/telerelay/commit/6ff6a3e42d69b0fc5cd3c66fd4edcdb7359e7d61) feat: implement multi-target forwarding feature  
[`860adf8`](https://github.com/journey-ad/telerelay/commit/860adf8e46c265675b7ddba22802c3b50c105a3f) fix: fix Docker config file mount issue  
[`6caad29`](https://github.com/journey-ad/telerelay/commit/6caad2981f9c2f265b1617a52ffdf3c56c9275aa) fix: modify Dockerfile to run as root user  
[`b31a936`](https://github.com/journey-ad/telerelay/commit/b31a936c728c11acf7849909a847d9f7e2a9c62b) feat: add GitHub Actions for automatic Docker image building  
[`79427ff`](https://github.com/journey-ad/telerelay/commit/79427ffe9439adad21cb7a0e1eb32ea42d42a867) ci: add docker-publish.yml for ghcr  
[`abfd8c8`](https://github.com/journey-ad/telerelay/commit/abfd8c835372c19d4f524ecdf2e8fe0b2903a3d7) feat: add proxy support  
[`1995a83`](https://github.com/journey-ad/telerelay/commit/1995a83018404604cc9975d226ad092403b700d3) feat: initialize Telegram message forwarding tool project  
[`240ce63`](https://github.com/journey-ad/telerelay/commit/240ce63c3b3b11424d6a3b122081d1230e4ca4ff) Create LICENSE

**完整变更 / Full changelog**: [240ce63...v1.0.0](https://github.com/journey-ad/telerelay/compare/240ce63...v1.0.0)
