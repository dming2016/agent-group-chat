# Changelog

## [2.1.0] - 2026-05-24

### Added
- `AGENT_GUIDE.md` — integration guide for AI agents (polling, encoding, behavior rules)
- Agent name → role ID resolution in `@mentions` (type `@执行员` or `@designer1`, both work)
- Non-agent `@mentions` (e.g. `@import`) are now silently ignored
- Cursor-tracked agents appear in member list even without sending messages

### Fixed
- Agent names cleaned up: unified Chinese-only format, removed `(Codex)` suffix
- UTF-8 BOM in `agents.json` caused zero agents loaded → fixed
- Role preview no longer updates AI read cursors (client-side filtering)
- Infinite recursion when `lastAuthor` matched empty-string role
- Compact messages now show @mention tags and have proper bubble spacing
- Avatars now derived from agent role, not per-message field (consistent across old/new messages)

### Changed
- `.gitignore` expanded to cover temp/debug files (`_*.py`, `_*.json`, `_*.txt`)

## [2.0.0] - 2026-05-22

### Added
- Multi-group chat with SSE real-time push
- @mention-based message filtering
- Agent identity enforcement (`agents.json`)
- File-based persistence (one JSON file per group)
- Cursor-based read tracking
- `CharsetFixASGI` middleware for non-UTF-8 encoding repair
- Frontend with role switching, member list, compact messages
- `monitor.py` polling script for external watchers
- Docker support
