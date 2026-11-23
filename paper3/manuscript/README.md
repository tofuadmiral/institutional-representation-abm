# Vetoes and missed agreements in language-model bargaining

[Working paper (PDF)](main.pdf) · [Companion blog draft](blog.md) · [LaTeX source](main.tex)

In 60 games with a unanimous voting rule, two proposers saw the same request and payoffs. Giving one proposer a count of how many constituencies gained from each plan raised mutually beneficial agreements from 6 to 31. The paired comparison includes 26 games that improved, one that switched in the other direction, five that passed in both conditions, and 28 that passed in neither.

## Reproduce the results

From the repository root, run `python paper3/manuscript/reproduce.py` with the dependencies in `requirements.txt` installed. To also rebuild the figure and paper, change into `paper3/manuscript/` and run the following with LaTeX and latexmk installed.

~~~sh
python figure.py
latexmk -pdf main.tex
~~~

The analysis verifies the four compressed action files against their recorded hashes, reconstructs offers and votes, and checks the game-level tables. For the GPT-4.1 comparisons it averages within each of the 18 games and computes marginal percentile intervals from the full empirical game-bootstrap distribution. This removes Monte Carlo variation in the earlier draft’s lower bounds for minimum payoff (2.78 to 2.72) and proposer concession (−12.50 to −12.42). It enumerates game-level sign flips and applies the original Bonferroni family sizes of four for voting rules and three for replay. For each Qwen cohort it reports the paired table, conservative interval and exact two-sided binomial test on discordant pairs.

The figure script draws [the figure](bargaining-outcomes.pdf) from the same files. All three steps run offline.

## Prepare the arXiv source archive

From `paper3/manuscript/`, run `tar -czf arxiv-submission.tar.gz main.tex bargaining-outcomes.pdf`. The bibliography is in `main.tex`. To check the upload locally, extract the archive into an empty directory and run `latexmk -pdf main.tex` there.

## Read the games

| Study | Unit of comparison | Released decisions | Game-level data |
| --- | --- | ---: | --- |
| GPT-4.1 voting rules | 18 games under two rules and two message conditions | [396 actions](data/voting-rules.jsonl.gz) | [72 branches](data/voting-rules.csv) |
| GPT-4.1 offer replay | Four new offers on each of 36 saved histories | [144 actions](data/offer-replay.jsonl.gz) | [Offer scores](data/offer-replay.csv) |
| Qwen count display and threshold reminder | 60 paired games plus 24 qualification items | [564 actions](data/counts-and-reminder.jsonl.gz) | [Paired games](data/qwen-games.csv) |
| Qwen counts with a matched reminder | 60 fresh paired games using the same qualified model | [540 actions](data/matched-reminder.jsonl.gz) | [Paired games](data/qwen-games.csv) |

Each compressed file contains one JSON object per call, with the messages, generation settings, tool definition and returned action. The payoff menu and fallback are in the structured user message. The two Qwen cohorts have separate study identifiers in the shared CSV. Each game has one shared request, two offers and six binding ballots. The two GPT-4.1 studies reuse the same 18 games.

The [provenance record](data/provenance.json) gives the protocol, audited report and public export hashes. The [30B screen](data/qwen30b-screen.csv) and [80B screen](data/qwen80b-screen.csv) tabulate qualification outcomes. The 24 calls for the 30B candidate that did not qualify are additional to the 1,644 calls in the table.
