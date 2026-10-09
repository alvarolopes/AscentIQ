---
name: issue-workflow
description: Work a GitHub issue end to end - plan with tests, post plan as comment, implement, verify, commit referencing the issue
argument-hint: "<issue-number>"
allowed-tools:
  - read
  - grep
  - glob
  - exec
permissions:
  allow:
    - Exec(gh issue view)
    - Exec(gh issue comment)
    - Exec(git status)
    - Exec(git diff)
    - Exec(git log)
---

Work the GitHub issue the user named, following these stages in order. Do not skip a stage.

## 1. Understand
- `gh issue view <n>` and read the body and existing comments.
- Read every file the issue names, plus their callers (`grep` for the symbol). Do not plan from the issue text alone.
- If the issue is ambiguous or you find the premise is wrong, stop and tell the user before planning.

## 2. Plan (before any code)
Write a plan with these sections and post it with `gh issue comment <n> --body-file <plan.md>`:
- **Contexto verificado**: what the code actually does today, with file:line references.
- **Mudanças**: ordered list; for each, the file and the exact interface (signature, types, data shape).
- **Testes**: concrete test cases (name, setup, assertion) written *before* the implementation. Name the test file.
- **Riscos e rollback**: what could break, how to detect it, how to undo.
- **Fora de escopo**: what this issue deliberately does not change.
The plan is in Brazilian Portuguese, like the issues.

## 3. Implement
- Write the failing tests first, run them, confirm they fail for the right reason.
- Implement the smallest change that makes them pass. Follow existing style (compact Python, no new comments unless asked, error messages in pt-BR).
- Keep the public API and the invariants listed in the `backend-check` skill.

## 4. Verify
- Run `/backend-check`. Everything must pass, not only the new tests.
- If the change touches the frontend contract, also run `npm run typecheck` and `npm test` in `dashboard/web`.

## 5. Land
- Commit on the current branch with a message that explains *why*, ending with `Refs #<n>`.
- Post a closing comment on the issue summarizing what changed, test evidence (counts), and anything left for follow-up.
- Do not push and do not close the issue unless the user asked for it.
