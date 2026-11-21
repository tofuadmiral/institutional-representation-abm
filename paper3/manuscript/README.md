# Vetoes and missed agreements in language-model bargaining

[Working paper (PDF)](main.pdf) · [Companion blog draft](blog.md) · [LaTeX source](main.tex)

In 60 games with a unanimous voting rule, two proposers saw the same request and payoffs. Giving one proposer a count of how many constituencies gained from each plan raised mutually beneficial agreements from 6 to 31. The paired comparison includes 26 games that improved, one that switched in the other direction, five that passed in both conditions, and 28 that passed in neither.

## Reproduce the results

From this directory, run the following with Python, SciPy, Matplotlib, and a LaTeX installation that includes latexmk.

~~~sh
python reproduce.py
python figure.py
latexmk -pdf main.tex
~~~

The first command verifies the four compressed action files, reconstructs offers and votes, checks the game-level tables, and prints the paired differences, intervals and exact tests for the Qwen studies. The second draws [the figure](bargaining-outcomes.pdf) from the same files. All three steps run offline.

## Read the games

| Study | Unit of comparison | Released decisions | Game-level data |
| --- | --- | ---: | --- |
| GPT-4.1 voting rules | 18 games under two rules and two message conditions | [396 actions](data/voting-rules.jsonl.gz) | [72 branches](data/voting-rules.csv) |
| GPT-4.1 offer replay | Four new offers on each of 36 saved histories | [144 actions](data/offer-replay.jsonl.gz) | [Offer scores](data/offer-replay.csv) |
| Qwen count display and threshold reminder | 60 paired games plus 24 qualification items | [564 actions](data/counts-and-reminder.jsonl.gz) | [Paired games](data/qwen-games.csv) |
| Qwen counts with a matched reminder | 60 fresh paired games using the same qualified model | [540 actions](data/matched-reminder.jsonl.gz) | [Paired games](data/qwen-games.csv) |

Each compressed file contains one JSON object per call, with the messages, generation settings, tool definition and returned action. The payoff menu and fallback are in the structured user message. The two Qwen cohorts have separate study identifiers in the shared CSV. Each game has one shared request, two offers and six binding ballots. The two GPT-4.1 studies reuse the same 18 games.

The [provenance record](data/provenance.json) gives the protocol, audited report and public export hashes. The [30B screen](data/qwen30b-screen.csv) and [80B screen](data/qwen80b-screen.csv) tabulate qualification outcomes. The 24 calls for the 30B candidate that did not qualify are additional to the 1,644 calls in the table.
