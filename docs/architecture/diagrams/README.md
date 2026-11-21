# Diagrams

Open the HTML files in a browser. Each is a standalone page.

| Diagram | Shows |
| --- | --- |
| [platform-overview.html](platform-overview.html) | The runtime components on Azure and Microsoft Foundry, and what talks to what |
| [discovery-stage.html](discovery-stage.html) | From a request to an approved requirement: options, clarification, consultation, Definition of Ready and the human gate |
| [assignment-flow.html](assignment-flow.html) | How one assignment moves through the five functions and the human gates |
| [agent-lifecycle.html](agent-lifecycle.html) | The states a temporary specialist passes through, including suspension |

GitHub shows HTML files as source text. Clone the repository and open them in a browser. Flows that
must be readable on GitHub are also drawn in Mermaid in `delivery-lifecycle.md` and `runtime-design.md`.

All four passed the diagram tool's automated checks. They have not been visually reviewed by a person.

The lifecycle diagram merges five early states into "Provisioned" to stay readable. The exact
transition table is in `reference/contracts.py` (`ALLOWED_TRANSITIONS`).

## Changing a diagram

The sources are in [src/](src/). They are Archify candidates. Edit the JSON and regenerate, from the repository root:

```bash
node <archify>/bin/archify.mjs finalize <type> docs/architecture/diagrams/src/<name>.<type>.json \
  docs/architecture/diagrams/<name>.html --quality showcase --json
```

`<type>` is `architecture`, `workflow` or `lifecycle`. Commit only the HTML and the JSON source.
