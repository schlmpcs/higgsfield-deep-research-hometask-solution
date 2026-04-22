Grade whether the agent handled an ambiguous or under-specified question appropriately.

Scoring guidance:
- 1.0: The agent explicitly acknowledged the ambiguity, stated its assumptions clearly before answering, or asked a clarifying question rather than guessing silently.
- 0.5: The agent made an implicit assumption that narrowed the ambiguity, but did not state it explicitly; the answer is plausible but could mislead.
- 0.0: The agent guessed without acknowledging the ambiguity, gave a confident answer that ignores the ambiguous dimension, or answered as if the question were unambiguous when it was not.

Pass when the agent either (a) explicitly surfaces the ambiguity by stating assumptions or asking a clarifying question, or (b) makes a plausible narrowing assumption and gives a correct answer without confidently excluding other interpretations. Fail only when the agent ignores the ambiguity entirely and could materially mislead.
