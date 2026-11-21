# Eight-character hex identifiers for memories

Memories are uniquely identified across the vault by an 8-character lowercase hexadecimal string, matching their filename prefix (`{id}-{slug}.md`). We chose fixed short hex strings (with `00000000` reserved for the Root) over UUIDs or semantic slugs because they produce concise, collision-resistant references for humans and LLM context windows while allowing titles and file slugs to be renamed without breaking graph links or body references.
