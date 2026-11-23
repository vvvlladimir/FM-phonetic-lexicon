---
status: accepted
date: 2026-11-23
decision-makers: project author
---

# Record decisions as MADR files in docs/decisions

## Context and Problem Statement

This research project makes many method decisions, for example which IPA source to use, how letters are aligned to sounds, and what counts as "sounds the same". These decisions have to be explained in the project report and defended to the supervisor. Without a written record, the reasons and the alternatives we rejected get lost.

## Considered Options

* Michael Nygard's ADR format: Title, Status, Context, Decision, Consequences.
* MADR (Markdown Architectural Decision Records), version 4.
* Free-form notes in the README.

## Decision Outcome

We chose **MADR**, stored as `docs/decisions/NNNN-title-with-dashes.md`. This is the location the MADR project recommends since version 3.0.

MADR has an explicit "Considered Options" section with pros and cons. That is the part a research report needs most, because it answers "why not X?".

We use the minimal MADR sections: the front matter, Context, Considered Options, Decision Outcome, Consequences and More Information. A section is left out when it adds nothing.

### Consequences

* Good: every method choice can be cited from the report, e.g. "see ADR-0004".
* Good: each record states the evidence behind the choice, such as prototype numbers.
* Bad: the records need to be kept current. When a decision changes, we add a new ADR that supersedes the old one, and set the old one's status to "superseded by ADR-NNNN".

## More Information

* MADR: <https://adr.github.io/madr/>
* Nygard, "Documenting Architecture Decisions" (2011). Overview: <https://www.martinfowler.com/bliki/ArchitectureDecisionRecord.html>
* Template: [adr-template.md](adr-template.md)
