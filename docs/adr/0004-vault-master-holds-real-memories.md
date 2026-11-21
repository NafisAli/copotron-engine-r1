# The vault's `master` holds the real memories, and `develop` is a disposable mirror

The vault repo has two long-lived branches with unequal roles. `master` is the real vault: every memory meant to last lands there, and it is the branch checked out for everyday use. `develop` mirrors `master` and is a playground for trying engine behaviour on real data. It is reset to `master` whenever it drifts and is never merged into it. A memory worth keeping from an experiment reaches `master` by cherry-pick; everything else is thrown away with the reset. We chose this over the engine's Gitflow, where `develop` integrates into `main`, because a vault has no releases. Merging the playground up would carry every experiment into the real vault.

## Consequences

- After dogfooding, agents return the vault to `master`. Work done while `develop` or a `dogfood/*` branch is checked out writes to the playground, and a memory written there is lost at the next reset unless it is cherry-picked.
- `dogfood/<topic>` branches fork from a fresh `develop`, so separate experiments stay apart. Like `develop`, they are never merged into `master`.
- Resetting `develop` discards its commits, so cherry-pick anything worth keeping before the reset.
