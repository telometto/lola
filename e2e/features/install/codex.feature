Feature: Codex CLI skills
  As a Codex user, I want Lola to manage native skills
  in project and user scopes.

  Scenario: Install and uninstall native project skills
    Given a module "my-module" with skills, commands, and agents
    And the module "my-module" is registered
    When I run lola "install my-module -a codex"
    Then the exit code should be 0
    And the file "{project}/.agents/skills/skill1/SKILL.md" should exist
    And the output should contain "codex"
    When I run lola "uninstall my-module -a codex --force"
    Then the exit code should be 0
    And the directory "{project}/.agents/skills/skill1" should not exist

  Scenario: User skills are isolated from the real account
    Given a module "my-module" with skills, commands, and agents
    And the module "my-module" is registered
    When I run lola "install my-module -a codex --scope user"
    Then the exit code should be 0
    And the file "{tmp}/home/.agents/skills/skill1/SKILL.md" should exist
    And the directory "{project}/.agents/skills" should not exist
    When I run lola "uninstall my-module -a codex --scope user --force"
    Then the exit code should be 0
    And the directory "{tmp}/home/.agents/skills/skill1" should not exist

  Scenario: Update a skill and its supporting files
    Given a module "tools" with skills, commands, and agents
    And a file "{module_path}/skills/skill1/notes.md" containing:
      """
      Original supporting file
      """
    And the module "tools" is registered
    When I run lola "install tools -a codex"
    Then the exit code should be 0
    And the file "{project}/.agents/skills/skill1/SKILL.md" should contain:
      """
      name: skill1
      """
    Given a file "{lola_home}/modules/tools/skills/skill1/notes.md" containing:
      """
      Updated supporting file
      """
    When I run lola "update tools -a codex"
    Then the exit code should be 0
    And the file "{project}/.agents/skills/skill1/notes.md" should contain:
      """
      Updated supporting file
      """

  Scenario: Sync a declarative Codex selection
    Given a module "my-module" with skills, commands, and agents
    And the module "my-module" is registered
    And a file "{project}/.lola-req" containing:
      """
      my-module#assistant=codex
      """
    When I run lola "sync"
    Then the exit code should be 0
    And the file "{project}/.agents/skills/skill1/SKILL.md" should exist
    And the directory "{project}/.claude" should not exist
