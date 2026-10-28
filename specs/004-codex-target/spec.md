# Codex CLI skill target

Implements [issue #132](https://github.com/LobsterTrap/lola/issues/132)
through the existing Python assistant target interface.

## Behavior

- Select Codex with `-a codex` or `#assistant=codex` in `.lola-req`.
  Include it when installing or syncing to all default assistants.
- Project skills live in `.agents/skills/<skill>/`. User skills live in
  `~/.agents/skills/<skill>/`, independently of `CODEX_HOME`.
- Copy the whole skill directory, including executable scripts,
  references, assets, and optional `agents/openai.yaml`.
- Set the installed `SKILL.md` frontmatter `name` to the effective install
  name. This supplies names for legacy Lola skills and keeps conflict
  renaming consistent with Codex discovery. Preserve other metadata and
  the source module. Require a nonempty string description.
- Reuse existing install records, update, uninstall, and sync behavior
  in both scopes. Updates refresh resources and remove obsolete skills.
- Replace destination skill symlinks without writing to their targets.
  Invalid source skills must leave existing destinations untouched.
- Commands, subagents, MCP configuration, and module instructions are
  outside this target's scope. Mixed modules must still install skills
  without creating unsupported output or changing `AGENTS.md`.

## Validation

Test the public CLI lifecycle and target interface using temporary
projects, homes, and registries. Extend shared destination symlink tests
and black-box BDD scenarios. Where available, use Codex's local discovery
interface without model calls or executing skill scripts.

## Reference

[OpenAI skill documentation](https://learn.chatgpt.com/docs/build-skills),
checked 2026-10-28, specifies `.agents/skills`, required `name` and
`description` metadata, and supporting skill resources.
