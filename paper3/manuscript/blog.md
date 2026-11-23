# What happens when everyone has a veto but only one gets to pick the deal?

*Fuad Ali · Draft*

In one of my bargaining games, three AI representatives had to agree on a plan. If the vote failed, their groups got 41, 42 and 42 points. The representative who got to pick the plan put forward a plan that paid 77 to its own group, 33 to the second and 71 to the third.

The second representative voted no. Fair enough. Who wants to give up nine points so somebody else can have 36 more?

What interested me was what happened *before* that vote. The second representative had already asked for a deal that paid 51, 58 and 60. Everyone would have come out ahead. The other compromise paid the proposer 57, six points more than the requested deal. Both were on the same four-line menu. Neither got a vote.

I started this experiment because of something I'd seen in an earlier one. I ran 12 games under each voting rule, once with the representatives' messages and once with only the plans they nominated. When two votes were enough, GPT-4.1 representatives passed 15 deals in those 24 runs. All 15 left somebody worse off. When I gave each representative a veto, the harmful deals disappeared. So did most of the agreements. Only two passed, even though every game had a deal that could leave everyone better off.

Was the problem the vote, or what kept getting put to a vote? I tried something fairly small. In the final experiment I ran 60 new games with Qwen playing all three roles. Each representative was told to get the best payoff for its own group. In each game I gave two copies of the proposer the same decision in separate conversations. Same payoffs, same request from the representative whose group stood to lose, same reminder that it needed three yes votes. One version also got a number beside each plan showing how many groups would earn more than if the vote failed.

With the reminder alone, **6 of 60** games ended in a deal that helped everyone. With the counts, **31 of 60** did. The voters never saw the counts. Across both versions, all 37 offers that helped everyone passed, and the representative who stood to lose voted down all 83 offers that would have cost it points.

The game I opened with was one of the stubborn ones. The proposer picked the 77-point plan even with a 2 beside it and a 3 beside each of the two compromises. In another game, the two versions chose different plans. The proposer picked a deal that gave its group 67 instead of the 45 it would get if the vote failed. The group that had asked for 72 got 58, four better than its fallback. It voted yes. That's a bargain I'd recognize.

How impressed should we be by 31 out of 60? Two of the four plans helped everyone in every game. Picking a plan out of a hat would put one of those on the ballot half the time on average. And when I went back through the requests, the group facing a loss had asked for a deal that helped everyone in **all 60 games**. The proposer had a suggestion it could use before I gave it a single count. When the version with counts chose a compromise, I can’t tell from the offer whether it worked through the votes or just picked a plan marked 3.

That's the part I'd carry over to designing a system like this. I'd keep the veto. It worked for the group that needed it. I'd also save what the other representatives asked for alongside the offer that actually went to a vote. Looking at the failed votes alone, I'd have spent my time trying to fix the voter.

[Working paper (PDF)](main.pdf) · [Data and analysis](README.md)
