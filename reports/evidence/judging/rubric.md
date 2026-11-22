Every retrieved chunk, for every question, is judged at one of three levels. The judge reads **the question and the full chunk text only**, with no document name, no score and no version label.

| Level | Meaning | Example (Q2, "How will the project reduce mercury use in artisanal gold mining?") |
|---|---|---|
| **useful** (2) | The chunk text itself states information that directly answers the question, or a main part of the answer, and can be read without the surrounding page | "The project will promote mercury-free processing technologies, train miners in gravity concentration and support formalisation ..." |
| **partial** (1) | On topic and contains some relevant information, but it does not answer the question on its own: only background, a heading with little text, a fragment, an answer buried in noise, or an answer to a neighbouring question | A paragraph about the scale of mercury use in the sector with no description of how the project reduces it |
| **not useful** (0) | Off topic, template instruction text, table of contents, a footer, a title page, or content from a project that cannot answer the question | "Provide a brief summary description of the project, including: (i) what is the problem ..." |

Rules for edge cases:

* For the unscoped questions (9 to 12) a chunk from **any** document can be useful if it answers the question for the project it belongs to.
* Table text counts as useful if the needed cell values are readable from the chunk text alone.
* When unsure between two levels, choose the lower one.
