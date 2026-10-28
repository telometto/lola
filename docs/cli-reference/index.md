# CLI Reference

Complete command reference for the Lola CLI. Use `lola --help` or `lola <command> --help` for detailed usage.

## Module Management (`lola mod`)

| Command                                              | Description                                    |
| ---------------------------------------------------- | ---------------------------------------------- |
| `lola mod add <source>`                              | Add a module from git, folder, zip, or tar     |
| `lola mod add <source> --ref <ref>`                  | Add from a specific git branch, tag, or SHA    |
| `lola mod ls`                                        | List registered modules                        |
| `lola mod info <name>`                               | Show module details                            |
| `lola mod init [name]`                               | Initialize an Agent Plugins package            |
| `lola mod init [name] --format lola`                 | Initialize a legacy Lola module                |
| `lola mod update [name]`                             | Update module(s) from source                   |
| `lola mod rm <name>`                                 | Remove a module                                |

## Marketplace Management (`lola market`)

| Command                                      | Description                                   |
| -------------------------------------------- | --------------------------------------------- |
| `lola market add <name> <url>`               | Register a marketplace                        |
| `lola market ls`                             | List registered marketplaces                  |
| `lola market update [name]`                  | Update marketplace cache                      |
| `lola market set --enable <name>`            | Enable a marketplace                          |
| `lola market set --disable <name>`           | Disable a marketplace                         |
| `lola market rm <name>`                      | Remove a marketplace                          |

## Search

| Command                          | Description                                                       |
| -------------------------------- | ----------------------------------------------------------------- |
| `lola search <query>`            | Search the local registry and enabled marketplaces                |
| `lola search <query> --mod`      | Search only the local module registry                             |
| `lola search <query> --market`   | Search only enabled marketplaces                                  |
| `lola mod search <query>`        | Deprecated alias for `lola search <query> --mod`                  |

## Installation

| Command                                             | Description                                   |
| --------------------------------------------------- | --------------------------------------------- |
| `lola install <module>`                             | Install to all detected assistants             |
| `lola install <module> -a <assistant>`              | Install to specific assistant                 |
| `lola install <module>@<ref>`                       | Install at a specific git ref                 |
| `lola install @<marketplace>/<module>`              | Install from a specific marketplace           |
| `lola install @<marketplace>/<module>@<ref>`        | Install from a marketplace at a specific ref  |
| `lola install <module> --append-context <path>`     | Append context reference                      |
| `lola uninstall <module>`                           | Uninstall module                              |
| `lola list`                                         | List all installations (shows version and ref when set) |
| `lola update`                                       | Regenerate assistant files                    |
| `lola sync`                                         | Install modules from `.lola-req`              |

### Codex CLI

Select `codex` to manage native skills in either scope:

```bash
lola install my-module -a codex
lola install my-module -a codex --scope user
lola update my-module -a codex
lola uninstall my-module -a codex --scope project
lola uninstall my-module -a codex --scope user
```

Project installs use `.agents/skills/<skill>/SKILL.md`. User installs use
`~/.agents/skills/<skill>/SKILL.md`, independently of `CODEX_HOME`.
Updates refresh all recorded installations matching the module and
assistant, including supporting files, and remove obsolete skills.

To sync only Codex from a `.lola-req` file, run `lola sync -a codex` or
select the assistant per entry:

```text
my-module#assistant=codex
```

Codex is included when no assistant is selected in noninteractive installs
or syncs. Lola copies the complete skill directory, including scripts,
references, assets, and optional `agents/openai.yaml`. The installed
frontmatter `name` follows the effective install name, including conflict
renames; legacy skills without `name` receive one. Source files are
unchanged. A nonempty string `description` is required.

This target supports skills only. Commands, agents, MCP configuration,
and module instructions are skipped; project `AGENTS.md` and Codex
configuration are preserved.

See [OpenAI's skill documentation](https://learn.chatgpt.com/docs/build-skills)
for Codex's discovery paths and skill format.
