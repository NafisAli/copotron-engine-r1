# Implant attachments as a tenth Core Field

Memories attach Implants through a new `implants` Core Field: a list of Implant Instructions memory identifiers that the indexer propagates down the Memory DAG as the union-valued Inherited Implants, alongside `inherited_persona`. We promoted it to a Core Field instead of leaving it in the Open Tail because propagation needs the engine to validate and process it, and Open Tail is defined as keys the engine preserves without structural interpretation. Special-casing one Open Tail key would have blurred that boundary. Attachments reference memory identifiers rather than implant names, so renaming an Implant (its title, folder, or CLI name) never breaks a link.

## Consequences

- The Core Fields grow from nine to ten. The schema, the indexer, the SQLite columns and the glossary's Core Fields entry all change together.
- Inherited Implants is a union, not a nearest-ancestor override, so it cannot reuse persona propagation as is.
- Identifiers that don't resolve to Implant Instructions are reported by the audit as dangling implant links and left out of inheritance, never fatal.
- Implant Instructions never have children. Insertion owns them and Implant Removal deletes them, so a child would be orphaned or silently moved. Write paths refuse them as a parent, and the audit reports a child a hand edit left behind.
