# Decision records

These are the method and architecture decisions of the project, in [MADR](https://adr.github.io/madr/) format (see ADR-0000). To add one, copy [adr-template.md](adr-template.md) to the next free number.

Statuses:

- **accepted**: the decision is in use.
- **proposed**: considered but not implemented yet.
- **superseded by ADR-NNNN**: replaced by a later decision; the record is kept for history.

| ADR | Decision | Status |
|---|---|---|
| [0000](0000-use-markdown-architectural-decision-records.md) | Record decisions as MADR files in docs/decisions | accepted |
| [0001](0001-store-everything-in-one-sqlite-file.md) | One SQLite file, idempotent pipeline, IPA cache | accepted |
| [0002](0002-use-espeak-ng-for-ipa.md) | IPA from eSpeak NG; WikiPron only as cross-check | accepted |
| [0003](0003-data-sources-and-normalization.md) | Data sources, scope, normalization and script filter | accepted |
| [0004](0004-align-letters-with-espeak-rule-trace.md) | Letter↔sound alignment from `espeak-ng -X`, Viterbi fallback | accepted |
| [0005](0005-use-final-pronunciation-as-sound-unit.md) | "Sound" = eSpeak's final pronunciation, not the raw rule output | accepted |
| [0006](0006-generate-variants-from-sound-spelling-table.md) | Variants by beam search over the sound→spelling table, verified by eSpeak | accepted |
| [0007](0007-measure-sound-similarity-with-panphon.md) | "Sounds similar" = PanPhon feature distance; two neighbour buckets | accepted |
| [0008](0008-handle-russian-stress-by-vowel-rule.md) | Russian: unstressed-vowel rule instead of eSpeak's stress guess | accepted |
| [0009](0009-rank-attested-spellings-higher.md) | Real spellings (names-dataset) as ranking bonus, not filter | accepted |
| [0010](0010-drop-diacritics-as-own-variant-kind.md) | Dropped diacritics as a variant kind (key for Turkish) | accepted |
| [0011](0011-defer-listener-confusion-matrices.md) | Weight sound changes by listener confusion data | proposed (deferred) |
